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

"""Utilities for substituting environment variables and headers in bridge requests."""

from __future__ import annotations

import logging
import re
from typing import Iterable

from fastapi import HTTPException

from ..models.request import BridgeRequestBody
from .masking import REDACTED_VALUE

logger = logging.getLogger(__name__)

ENV_VAR_PATTERN = re.compile(r"\$([A-Za-z0-9_]+)")
HEADER_VAR_PATTERN = re.compile(r"\$headers\.([A-Za-z0-9_-]+)", re.IGNORECASE)
SUBSTITUTION_PATTERN = re.compile(r"(?i:\$headers\.(?P<header_name>[A-Za-z0-9_-]+))|\$(?P<env_name>[A-Za-z0-9_]+)")


def substitute_variables(
    text: str,
    env: dict[str, str],
    request_headers: dict[str, str] | None = None,
) -> str:
    """
    Replace $VAR_NAME or $headers.NAME patterns using the provided mappings.

    Args:
        text: Input string that may contain substitution expressions.
        env: Mapping of environment variables available for substitution.
        request_headers: Mapping of request headers available for substitution.

    Returns:
        String with all substitution patterns replaced by their values.

    Raises:
        HTTPException: When a referenced variable does not exist.
    """

    if not text:
        return text

    headers = request_headers or {}
    headers_lower = {key.lower(): value for key, value in headers.items()}

    def _replace(match: re.Match[str]) -> str:
        header_name = match.group("header_name")
        if header_name:
            lookup = header_name.lower()
            value = headers_lower.get(lookup)
            if value is None:
                raise _missing_header_exception(header_name, headers)
            return value

        var_name = match.group("env_name")
        if var_name is None:
            return match.group(0)

        value = env.get(var_name)
        if value is None:
            raise _missing_variable_exception(var_name, env)
        return value

    return SUBSTITUTION_PATTERN.sub(_replace, text)


def apply_substitutions(request: BridgeRequestBody) -> BridgeRequestBody:
    """
    Apply environment and header substitution to bridge request fields.

    Ensures the original request instance remains unchanged by operating on a copy.

    Args:
        request: Incoming bridge request.

    Returns:
        Copy of the request with substitutions applied to serverPath, args, and mcp_headers.

    Raises:
        HTTPException: Propagated from substitute_variables for missing variables.
    """

    env = request.env or {}
    env_keys = sorted(env.keys())
    if env_keys:
        logger.debug("Env keys available for substitution: %s", env_keys)
        logger.debug(
            "Env values masked for logging: %s",
            _mask_env_values(env_keys),
        )
    else:
        logger.debug("No environment variables provided for substitution.")

    request_headers = request.request_headers or {}
    header_keys = sorted(request_headers.keys(), key=lambda k: k.lower())
    if header_keys:
        logger.debug("Request headers available for substitution: %s", header_keys)
        logger.debug(
            "Request headers masked for logging: %s",
            _mask_header_values(request_headers),
        )
    else:
        logger.debug("No request headers provided for substitution.")

    substituted = request.model_copy(deep=True)

    substituted.serverPath = _substitute_required_field(
        substituted.serverPath,
        env,
        request_headers,
        field_name="serverPath",
    )

    if substituted.args:
        substituted.args = _substitute_iterable(
            substituted.args,
            env,
            request_headers,
            field_name="args",
        )

    if substituted.mcp_headers:
        substituted.mcp_headers = _substitute_mapping(
            substituted.mcp_headers,
            env,
            request_headers,
            field_name="mcp_headers",
        )

    return substituted


def _substitute_required_field(
    value: str,
    env: dict[str, str],
    request_headers: dict[str, str],
    field_name: str,
) -> str:
    has_env = bool(ENV_VAR_PATTERN.search(value))
    has_headers = bool(HEADER_VAR_PATTERN.search(value))
    if not (has_env or has_headers):
        return value

    if has_env:
        logger.debug("Substituting env variables in %s", field_name)
    if has_headers:
        logger.debug("Substituting headers in %s", field_name)
    return substitute_variables(value, env, request_headers)


def _substitute_iterable(
    values: Iterable[str],
    env: dict[str, str],
    request_headers: dict[str, str],
    field_name: str,
) -> list[str]:
    substituted_values: list[str] = []
    env_substitutions = 0
    header_substitutions = 0
    for value in values:
        has_env = bool(ENV_VAR_PATTERN.search(value))
        has_headers = bool(HEADER_VAR_PATTERN.search(value))
        if has_env or has_headers:
            env_substitutions += int(has_env)
            header_substitutions += int(has_headers)
            substituted_values.append(substitute_variables(value, env, request_headers))
        else:
            substituted_values.append(value)

    if env_substitutions:
        logger.debug(
            "Substituting env variables in %s (%d items)",
            field_name,
            env_substitutions,
        )
    if header_substitutions:
        logger.debug(
            "Substituting headers in %s (%d items)",
            field_name,
            header_substitutions,
        )
    return substituted_values


def _substitute_mapping(
    mapping: dict[str, str],
    env: dict[str, str],
    request_headers: dict[str, str],
    field_name: str,
) -> dict[str, str]:
    substituted: dict[str, str] = {}
    env_substitutions = 0
    header_substitutions = 0
    for key, value in mapping.items():
        has_env = bool(ENV_VAR_PATTERN.search(value))
        has_headers = bool(HEADER_VAR_PATTERN.search(value))
        if has_env or has_headers:
            env_substitutions += int(has_env)
            header_substitutions += int(has_headers)
            substituted[key] = substitute_variables(value, env, request_headers)
        else:
            substituted[key] = value

    if env_substitutions:
        logger.debug(
            "Substituting env variables in %s (%d values)",
            field_name,
            env_substitutions,
        )
    if header_substitutions:
        logger.debug(
            "Substituting headers in %s (%d values)",
            field_name,
            header_substitutions,
        )
    return substituted


def _missing_variable_exception(var_name: str, env: dict[str, str]) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "error": f"Variable '{var_name}' not found in env",
            "available": sorted(env.keys()),
        },
    )


def _missing_header_exception(
    header_name: str,
    request_headers: dict[str, str],
) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "error": f"Header '{header_name}' not found in request_headers",
            "available": sorted(request_headers.keys(), key=lambda k: k.lower()),
        },
    )


def _mask_env_values(env_keys: Iterable[str]) -> dict[str, str]:
    return {key: REDACTED_VALUE for key in env_keys}


def _mask_header_values(headers: dict[str, str]) -> dict[str, str]:
    return {key: REDACTED_VALUE for key in headers.keys()}
