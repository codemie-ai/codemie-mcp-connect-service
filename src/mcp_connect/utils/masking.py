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

"""Utilities for masking sensitive values before logging."""

from __future__ import annotations

import re
from typing import Any

# Sensitive key patterns (case-insensitive, supports hyphen/underscore variants)
SENSITIVE_PATTERNS: re.Pattern[str] = re.compile(
    r"(authorization|api[-_]?key|x-api-key|token|auth|bearer|"
    r"secret|password|access[-_]?token|refresh[-_]?token|x-auth-token)",
    re.IGNORECASE,
)
REDACTED_VALUE = "********"


def is_sensitive_key(key: str) -> bool:
    """
    Check if key matches sensitive pattern.

    Args:
        key: Dictionary key to check

    Returns:
        True if key matches sensitive pattern (case-insensitive)

    Examples:
        >>> is_sensitive_key("Authorization")
        True
        >>> is_sensitive_key("api-key")
        True
        >>> is_sensitive_key("content-type")
        False
    """
    return bool(SENSITIVE_PATTERNS.search(key))


def mask_dict_values(data: dict[str, str], mask_all: bool = False) -> dict[str, str]:
    """
    Mask sensitive values in dictionary.

    Args:
        data: Dictionary with string keys and values
        mask_all: If True, mask all values. If False, mask only sensitive keys.

    Returns:
        New dictionary with masked values (original unchanged)

    Examples:
        >>> mask_dict_values({"API_KEY": "secret"}, mask_all=True)
        {'API_KEY': '********'}
        >>> mask_dict_values({"token": "abc", "host": "example.com"}, mask_all=False)
        {'token': '********', 'host': 'example.com'}
    """
    if mask_all:
        return {k: REDACTED_VALUE for k in data}
    else:
        return {k: REDACTED_VALUE if is_sensitive_key(k) else v for k, v in data.items()}


def mask_sensitive_headers(headers: dict[str, str] | None) -> dict[str, str]:
    """
    Mask sensitive headers (convenience wrapper for mcp_headers).

    Args:
        headers: Dictionary of HTTP headers

    Returns:
        New dictionary with sensitive header values masked

    Examples:
        >>> mask_sensitive_headers({"Authorization": "Bearer xyz", "Content-Type": "json"})
        {'Authorization': '********', 'Content-Type': 'json'}
    """
    if not headers:
        return {}
    return mask_dict_values(headers, mask_all=False)


# Keys of a user-context object safe to log verbatim, provided their value is a
# scalar or an all-scalar list. Everything else in the object is redacted.
KEEP_READABLE_KEYS: frozenset[str] = frozenset(
    {
        "id",
        "roles",
        "is_admin",
        "is_maintainer",
        "is_auditor",
        "user_type",
        "project_names",
        "admin_project_names",
    }
)


def _is_scalar(value: Any) -> bool:
    """True for None and the primitive JSON scalar types."""
    return value is None or isinstance(value, (str, int, float, bool))


def _is_keepable(value: Any) -> bool:
    """Scalar, or a list whose every element is a scalar. Nothing else.

    A dict, or a list containing any non-scalar, is rejected so a backend type
    change outside this service cannot silently widen the allowlist.
    """
    if _is_scalar(value):
        return True
    if isinstance(value, list):
        return all(_is_scalar(item) for item in value)
    return False


def _mask_username(value: Any) -> str:
    """First character plus a fixed suffix, so no length is leaked."""
    if not isinstance(value, str) or len(value) < 2:
        return REDACTED_VALUE
    return f"{value[0]}***"


def mask_user_context(
    user_context: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Mask a user-context object for logging. Pure; returns a new dict.

    Defensive by design: only a known-safe key with a known-safe value type is
    emitted verbatim, so a backend type change cannot widen the allowlist.
    Nested dict values are redacted wholesale, never traversed.

    Args:
        user_context: The raw user-context object, or None.

    Returns:
        A new dict with values masked, or None if the input was None.
    """
    if user_context is None:
        return None
    masked: dict[str, Any] = {}
    for key, value in user_context.items():
        if key == "username":
            masked[key] = _mask_username(value)
        elif key in KEEP_READABLE_KEYS and _is_keepable(value):
            masked[key] = list(value) if isinstance(value, list) else value
        else:
            masked[key] = REDACTED_VALUE
    return masked
