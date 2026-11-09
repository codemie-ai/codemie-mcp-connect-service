"""Tests for MCP server instruction capture and attachment."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.types import EmptyResult, ListToolsResult

from mcp_connect.client.instructions import (
    TRUNCATION_MARKER,
    SessionHandshake,
    _read_max_chars,
    attach_server_instructions,
    extract_instructions,
    initialize_session,
    sanitize_instructions,
)


class _NoInstructions:
    """Stand-in for an SDK result that predates the instructions field."""


def test_extract_instructions_reads_the_field() -> None:
    class _Init:
        instructions = "Call with sysparm_help=true first."

    assert extract_instructions(_Init()) == "Call with sysparm_help=true first."


def test_extract_instructions_returns_none_when_absent() -> None:
    assert extract_instructions(_NoInstructions()) is None
    assert extract_instructions(None) is None


def test_attach_adds_field_to_pydantic_tools_list_result() -> None:
    result = ListToolsResult(tools=[])

    attached = attach_server_instructions(result, "tools/list", "read me first")

    assert attached.model_dump(mode="json", exclude_none=True) == {
        "tools": [],
        "instructions": "read me first",
    }


def test_attach_adds_field_to_plain_dict_result() -> None:
    result: dict[str, Any] = {"tools": []}

    attached = attach_server_instructions(result, "tools/list", "read me first")

    assert attached == {"tools": [], "instructions": "read me first"}
    assert result == {"tools": []}, "input dict must not be mutated"


def test_attach_is_a_noop_without_instructions() -> None:
    result = ListToolsResult(tools=[])

    attached = attach_server_instructions(result, "tools/list", None)

    assert attached.model_dump(mode="json", exclude_none=True) == {"tools": []}


def test_attach_is_a_noop_for_other_methods() -> None:
    result = EmptyResult()

    attached = attach_server_instructions(result, "ping", "read me first")

    assert attached.model_dump(mode="json", exclude_none=True) == {}


def test_attach_tolerates_whitespace_around_the_method_name() -> None:
    result: dict[str, Any] = {"tools": []}

    attached = attach_server_instructions(result, " tools/list ", "read me first")

    assert attached == {"tools": [], "instructions": "read me first"}


def test_attach_leaves_unknown_result_types_alone() -> None:
    sentinel = _NoInstructions()

    assert attach_server_instructions(sentinel, "tools/list", "read me first") is sentinel


def test_session_handshake_carries_both_values() -> None:
    handshake = SessionHandshake(session="fake-session", instructions="read me first")

    assert handshake.session == "fake-session"
    assert handshake.instructions == "read me first"


def test_attach_ignores_non_string_instructions() -> None:
    """A stray non-string (e.g. an auto-attribute on a mock) must not reach the payload."""
    result: dict[str, Any] = {"tools": []}

    assert attach_server_instructions(result, "tools/list", object()) == {"tools": []}  # type: ignore[arg-type]


def test_attach_ignores_empty_instructions() -> None:
    result: dict[str, Any] = {"tools": []}

    assert attach_server_instructions(result, "tools/list", "   ") == {"tools": []}


# --- CR-001: third-party text is bounded and cleaned when it is captured ---


def test_sanitize_hard_cuts_when_the_limit_is_shorter_than_the_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("mcp_connect.client.instructions.MAX_INSTRUCTIONS_CHARS", 10)

    assert sanitize_instructions("x" * 50) == "x" * 10


def test_sanitize_truncation_cuts_at_a_word_boundary_and_marks_the_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("mcp_connect.client.instructions.MAX_INSTRUCTIONS_CHARS", 60)

    assert sanitize_instructions("word " * 30) == "word word word word" + TRUNCATION_MARKER


def test_sanitize_truncation_never_exceeds_the_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("mcp_connect.client.instructions.MAX_INSTRUCTIONS_CHARS", 100)

    cleaned = sanitize_instructions("y" * 500)

    assert cleaned is not None
    assert len(cleaned) == 100
    assert cleaned.endswith(TRUNCATION_MARKER)


def test_sanitize_leaves_short_text_unmarked() -> None:
    assert sanitize_instructions("read me first") == "read me first"


def test_control_characters_are_stripped_but_newlines_and_tabs_survive() -> None:
    assert sanitize_instructions("a\x00b\x1b[31mc\nd\te") == "ab[31mc\nd\te"


def test_bidi_and_invisible_format_characters_are_stripped() -> None:
    text = "a‮b⁦c​d⁠e﻿ f\U000e0041g"

    assert sanitize_instructions(text) == "abcdefg"


def test_zero_width_joiner_survives_for_emoji_sequences() -> None:
    text = "family \U0001f468‍\U0001f469"

    assert sanitize_instructions(text) == text


def test_instructions_that_are_only_control_characters_are_dropped() -> None:
    assert sanitize_instructions("\x00\x07\x1b​﻿") is None


def test_extract_returns_the_cleaned_and_capped_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("mcp_connect.client.instructions.MAX_INSTRUCTIONS_CHARS", 10)

    class _Init:
        instructions = "a\x00" + "x" * 50

    assert extract_instructions(_Init()) == "a" + "x" * 9


def test_truncation_is_logged_once_per_handshake_not_per_tools_list_call(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr("mcp_connect.client.instructions.MAX_INSTRUCTIONS_CHARS", 10)

    class _Init:
        instructions = "x" * 50

    cleaned = extract_instructions(_Init())
    for _ in range(5):
        attach_server_instructions({"tools": []}, "tools/list", cleaned)

    truncation_warnings = [r for r in caplog.records if "Truncating MCP server instructions" in r.getMessage()]
    assert len(truncation_warnings) == 1


@pytest.mark.parametrize("raw", ["0", "-5", "8k"])
def test_invalid_max_chars_setting_falls_back_to_the_default(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    monkeypatch.setenv("MCP_CONNECT_MAX_INSTRUCTIONS_CHARS", raw)

    assert _read_max_chars() == 8192


def test_max_chars_setting_accepts_a_positive_integer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_CONNECT_MAX_INSTRUCTIONS_CHARS", "4096")

    assert _read_max_chars() == 4096


def test_max_chars_defaults_when_the_setting_is_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MCP_CONNECT_MAX_INSTRUCTIONS_CHARS", raising=False)

    assert _read_max_chars() == 8192


async def test_initialize_session_returns_the_cleaned_handshake_text() -> None:
    class _Init:
        instructions = "a\x00b"

    session = MagicMock()
    session.initialize = AsyncMock(return_value=_Init())

    assert await initialize_session(session, 5.0) == "ab"


# --- CR-002: never overwrite what the server itself put on the result ---


def test_a_server_supplied_instructions_key_is_not_overwritten_dict() -> None:
    result: dict[str, Any] = {"tools": [], "instructions": "from-server"}

    attached = attach_server_instructions(result, "tools/list", "from-handshake")

    assert attached["instructions"] == "from-server"


def test_a_server_supplied_instructions_key_is_not_overwritten_pydantic() -> None:
    result = ListToolsResult.model_validate({"tools": [], "instructions": "from-server"})

    attached = attach_server_instructions(result, "tools/list", "from-handshake")

    assert attached.model_dump(mode="json", exclude_none=True)["instructions"] == "from-server"


# --- CR-003: a stricter SDK model must never turn a good response into a 500 ---


def test_a_model_that_forbids_extra_fields_is_returned_unchanged() -> None:
    from pydantic import BaseModel, ConfigDict

    class _StrictResult(BaseModel):
        model_config = ConfigDict(extra="forbid")

        tools: list[Any] = []

    result = _StrictResult()

    attached = attach_server_instructions(result, "tools/list", "read me first")

    assert attached is result
    assert attached.model_dump(mode="json", exclude_none=True) == {"tools": []}


def test_a_frozen_model_is_returned_unchanged() -> None:
    from pydantic import BaseModel, ConfigDict

    class _FrozenResult(BaseModel):
        model_config = ConfigDict(extra="allow", frozen=True)

        tools: list[Any] = []

    result = _FrozenResult()

    attached = attach_server_instructions(result, "tools/list", "read me first")

    assert attached is result
