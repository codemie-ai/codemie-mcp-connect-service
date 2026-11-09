# Copyright 2026 EPAM Systems, Inc. ("EPAM")
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Capture and expose MCP server-side instructions.

An MCP server may return an ``instructions`` string in its ``initialize``
handshake, describing how its tools are meant to be used. The MCP SDK returns
that value from ``ClientSession.initialize()`` and then keeps nothing, so it has
to be captured at the call site. This module holds the value object used to
carry it out of the managed client's lifecycle task. The text is cleaned once, at capture, so
the cached value and every relayed copy are the same bounded string.

The text comes from a third-party server and ends up in a downstream LLM system
prompt. It is bounded and stripped of control and invisible-format characters
here; it is not otherwise rewritten, and escaping for a prompt context belongs
to the consumer.
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from typing import Any

from mcp import ClientSession

from ..utils.logger import get_logger

logger = get_logger(__name__)

TOOLS_LIST_METHOD = "tools/list"

DEFAULT_MAX_INSTRUCTIONS_CHARS = 8192
TRUNCATION_MARKER = "\n[instructions truncated by MCP Connect]"


def _read_max_chars() -> int:
    raw = os.getenv("MCP_CONNECT_MAX_INSTRUCTIONS_CHARS")
    if raw is None:
        return DEFAULT_MAX_INSTRUCTIONS_CHARS
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value <= 0:
        logger.warning(
            "Invalid MCP_CONNECT_MAX_INSTRUCTIONS_CHARS=%r; using %d",
            raw,
            DEFAULT_MAX_INSTRUCTIONS_CHARS,
        )
        return DEFAULT_MAX_INSTRUCTIONS_CHARS
    return value


# Upper bound on the instruction text this bridge will relay. A server is free
# to send more; anything past the limit is cut rather than cached and re-served
# on every tools/list page for the session's whole lifetime.
MAX_INSTRUCTIONS_CHARS = _read_max_chars()

# Control characters except tab, newline and carriage return, which are
# legitimate formatting in an instruction block. Also covers characters that
# render as nothing or reorder surrounding text: bidi embeddings, overrides and
# isolates; zero-width space and marks; word joiner and invisible operators; BOM;
# line and paragraph separators; and Unicode tag characters. Zero-width joiner
# and non-joiner are kept because emoji sequences and some scripts need them.
_CONTROL_AND_INVISIBLE_CHARACTERS = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f" r"​‎‏‪-‮  ⁠-⁤⁦-⁩﻿" r"\U000e0000-\U000e007f]"
)


@dataclass(frozen=True)
class SessionHandshake:
    """An initialized session plus what its handshake disclosed.

    Attributes:
        session: The initialized MCP ClientSession.
        instructions: Server-side usage instructions, or None when the server
            sends none.
    """

    session: ClientSession
    instructions: str | None


def extract_instructions(init_result: Any) -> str | None:
    """Read and clean the instructions field off an InitializeResult.

    Args:
        init_result: The value returned by ``ClientSession.initialize()``.

    Returns:
        The cleaned, capped instructions string, or None when the server sent
        none or the result carries no such field.
    """
    return sanitize_instructions(getattr(init_result, "instructions", None))


async def initialize_session(session: ClientSession, timeout_seconds: float) -> str | None:
    """Initialize an MCP session and return the cleaned instructions it disclosed.

    Args:
        session: A ClientSession whose transport is already open.
        timeout_seconds: Initialization timeout.

    Returns:
        The cleaned instructions, or None when the server sent none.
    """
    init_result = await asyncio.wait_for(session.initialize(), timeout=timeout_seconds)
    return extract_instructions(init_result)


def sanitize_instructions(instructions: Any) -> str | None:
    """Clean and bound third-party instruction text.

    Args:
        instructions: The raw value. Anything that is not a string is rejected,
            so a stray value can never reach the response payload.

    Returns:
        The cleaned text capped at ``MAX_INSTRUCTIONS_CHARS``, or None when there
        is nothing worth relaying.
    """
    if not isinstance(instructions, str):
        return None

    cleaned = _CONTROL_AND_INVISIBLE_CHARACTERS.sub("", instructions)
    if not cleaned.strip():
        return None

    if len(cleaned) <= MAX_INSTRUCTIONS_CHARS:
        return cleaned

    logger.warning(
        "Truncating MCP server instructions from %d to %d characters",
        len(cleaned),
        MAX_INSTRUCTIONS_CHARS,
    )
    return _truncate(cleaned, MAX_INSTRUCTIONS_CHARS)


def _truncate(text: str, limit: int) -> str:
    """Cut at a word boundary and mark the cut, keeping the result within ``limit``."""
    budget = limit - len(TRUNCATION_MARKER)
    if budget <= 0:
        return text[:limit]

    head = text[:budget]
    boundary = max(head.rfind(" "), head.rfind("\n"), head.rfind("\t"))
    if boundary > 0:
        head = head[:boundary]
    return head.rstrip() + TRUNCATION_MARKER


def attach_server_instructions(result: Any, method: str, instructions: str | None) -> Any:
    """Attach server instructions to a tools/list result.

    Every other method is returned untouched: the SDK's Result base class allows
    extra fields, so an unguarded attach would leak the key onto ping and other
    responses. A value the server itself put on the result wins — the bridge is
    a transparent proxy and must not overwrite server-authored content.

    Args:
        result: The raw result of the MCP method call.
        method: The MCP method that produced the result.
        instructions: Cleaned instructions from ``extract_instructions``, or None.

    Returns:
        The result, with ``instructions`` attached when there is something to
        attach and the result does not already carry it. Dict results are
        copied; pydantic results are assigned in place, and a model that
        refuses the assignment is returned unchanged.
    """
    if method.strip() != TOOLS_LIST_METHOD:
        return result

    if not isinstance(instructions, str) or not instructions.strip():
        return result

    if isinstance(result, dict):
        if result.get("instructions") is not None:
            logger.warning("tools/list result already carries instructions; keeping the server's value")
            return result
        return {**result, "instructions": instructions}

    if hasattr(result, "model_dump"):
        if getattr(result, "instructions", None) is not None:
            logger.warning("tools/list result already carries instructions; keeping the server's value")
            return result
        try:
            result.instructions = instructions
        except (ValueError, TypeError, AttributeError) as exc:
            # A model that forbids extra fields or is frozen must not turn an
            # otherwise successful tools/list into an HTTP 500.
            logger.warning("Could not attach server instructions to %s: %s", type(result).__name__, exc)
            return result
        logger.debug("Attached server instructions to tools/list response")
        return result

    logger.warning(
        "Dropping server instructions: unsupported tools/list result type %s",
        type(result).__name__,
    )
    return result
