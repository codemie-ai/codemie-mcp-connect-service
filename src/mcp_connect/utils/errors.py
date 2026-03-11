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

"""Error detail extraction and formatting utilities.

This module provides utilities for extracting detailed context from exceptions
and formatting consistent error responses with request tracing support.

Key features:
- Extract error details from OSError, ConnectionError, ValidationError, etc.
- Safe attribute extraction using getattr pattern
- Stack trace capture for debug mode
- Integration with request context for error tracing

Usage:
    from .utils.errors import extract_error_details, get_stacktrace_string

    try:
        # Some operation
        pass
    except Exception as e:
        details = extract_error_details(e)
        stacktrace = get_stacktrace_string()
"""

import asyncio
import traceback
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError


def extract_error_details(exception: Exception) -> dict[str, Any]:
    """Extract detailed error context from exception attributes.

    Safely extracts diagnostic information from various exception types including
    OSError (connection errors, file operations), ValidationError (Pydantic),
    and TimeoutError. Uses safe attribute access to prevent AttributeError.

    Args:
        exception: Exception to extract details from

    Returns:
        Dictionary with error details (errno, syscall, address, port, etc.)
        Empty dict if no extractable details

    Examples:
        >>> err = OSError(111, "Connection refused")
        >>> err.syscall = "connect"
        >>> err.filename = "/path/to/file"
        >>> extract_error_details(err)
        {'errno': 111, 'strerror': 'Connection refused', 'syscall': 'connect', ...}

        >>> err = ValidationError.from_exception_data('Test', [])
        >>> details = extract_error_details(err)
        >>> 'errors' in details
        True
    """
    if isinstance(exception, OSError):
        return _extract_oserror_details(exception)
    elif isinstance(exception, ValidationError):
        return _extract_validation_error_details(exception)
    elif isinstance(exception, asyncio.TimeoutError):
        return {}  # TimeoutError has no context attributes
    else:
        return {}


def _extract_oserror_details(exception: OSError) -> dict[str, Any]:
    """Extract details from OSError and subclasses (ConnectionError, FileNotFoundError, etc.)."""
    details: dict[str, Any] = {}

    # Standard OSError attributes - add only if present and meaningful
    _safe_add_attribute(details, exception, "errno", lambda v: v is not None)
    _safe_add_attribute(details, exception, "strerror")
    _safe_add_attribute(details, exception, "syscall")
    _safe_add_attribute(details, exception, "filename")

    # Socket-specific attributes (address/port from args)
    _extract_socket_address(details, exception)

    return details


def _extract_validation_error_details(exception: ValidationError) -> dict[str, Any]:
    """Extract details from Pydantic ValidationError."""
    errors = exception.errors()
    if not errors:
        return {}

    first_error = errors[0]
    details: dict[str, Any] = {
        "field": ".".join(str(loc) for loc in first_error.get("loc", [])),
        "message": first_error.get("msg", ""),
        "type": first_error.get("type", ""),
    }

    if "input" in first_error:
        details["received"] = str(first_error["input"])[:100]  # Limit length

    return details


def _safe_add_attribute(
    details: dict[str, Any],
    exception: Exception,
    attr: str,
    validator: Callable[[Any], bool] | None = None,
) -> None:
    """Safely add exception attribute to details dict if it exists and passes validation.

    Args:
        details: Dictionary to add attribute to
        exception: Exception to extract attribute from
        attr: Attribute name to extract
        validator: Optional callable to validate the value (defaults to truthy check)
    """
    if not hasattr(exception, attr):
        return

    value = getattr(exception, attr)
    if validator is None:
        # Default: add if truthy
        if value:
            details[attr] = value
    elif validator(value):
        # Custom validation
        details[attr] = value


def _extract_socket_address(details: dict[str, Any], exception: OSError) -> None:
    """Extract socket address/port from OSError args if available.

    Some socket errors store address/port in args[1] as (address, port) tuple.
    """
    if not hasattr(exception, "args") or len(exception.args) < 2:
        return

    addr_info = exception.args[1]
    if isinstance(addr_info, tuple) and len(addr_info) == 2:
        details["address"] = addr_info[0]
        details["port"] = addr_info[1]


def get_stacktrace_string() -> str:
    """Get formatted stacktrace string for current exception.

    Captures the full stack trace of the currently handled exception using
    traceback.format_exc(). Should be called within an exception handler.

    Returns:
        Formatted stacktrace string including exception type, message, and call stack
        Returns "No traceback available" if called outside exception handler

    Examples:
        >>> try:
        ...     raise ValueError("test error")
        ... except:
        ...     trace = get_stacktrace_string()
        ...     assert "ValueError: test error" in trace
        ...     assert "Traceback" in trace
    """
    trace = traceback.format_exc()
    # format_exc() returns 'NoneType: None\n' if no exception is being handled
    if trace.startswith("NoneType:"):
        return "No traceback available"
    return trace


def extract_root_cause_message(exception: Exception) -> str:
    """Extract the most informative error message from an exception, including nested ExceptionGroups.

    Traverses nested BaseExceptionGroup/ExceptionGroup instances to find the root cause.
    This is particularly useful for handling exceptions from async task groups (anyio, asyncio)
    that wrap the actual error in an ExceptionGroup.

    Args:
        exception: Exception to extract root cause from

    Returns:
        Descriptive error message including exception type and message.
        For ExceptionGroups, returns the root cause message.

    Examples:
        >>> exc = ValueError("test error")
        >>> extract_root_cause_message(exc)
        'ValueError: test error'

        >>> # ExceptionGroup with nested error
        >>> inner = ConnectionError("Connection refused")
        >>> group = BaseExceptionGroup("task errors", [inner])
        >>> extract_root_cause_message(group)
        'ConnectionError: Connection refused'
    """
    # Handle BaseExceptionGroup and ExceptionGroup (Python 3.11+)
    if isinstance(exception, BaseExceptionGroup):
        # Traverse to find the deepest nested exception
        current: BaseException = exception
        while isinstance(current, BaseExceptionGroup) and current.exceptions:
            # Get first exception from the group
            first_exception = current.exceptions[0]
            # If it's another group, keep drilling down
            if isinstance(first_exception, BaseExceptionGroup):
                current = first_exception
            else:
                # Found the actual root cause
                return f"{type(first_exception).__name__}: {str(first_exception)}"
        # Fallback if we only have groups
        return f"{type(exception).__name__}: {str(exception)}"

    # For regular exceptions, return type and message
    exception_type = type(exception).__name__
    exception_message = str(exception)

    if exception_message:
        return f"{exception_type}: {exception_message}"
    else:
        return exception_type
