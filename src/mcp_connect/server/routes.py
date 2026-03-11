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

"""HTTP routes for the MCP Connect FastAPI application."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ..client.manager import get_or_create_client, invoke_with_timeout
from ..client.single_usage import execute_single_usage_request
from ..models import BridgeRequestBody
from ..utils.context import get_request_context, get_request_id
from ..utils.errors import extract_error_details, extract_root_cause_message, get_stacktrace_string
from ..utils.logger import get_log_level, get_logger
from ..utils.masking import mask_dict_values
from .middleware import setup_request_context, verify_token

router = APIRouter()
logger = get_logger(__name__)

# Load default timeout from environment (Story 3.6)
DEFAULT_TIMEOUT_MS = int(os.getenv("MCP_CONNECT_DEFAULT_TIMEOUT", "120000"))

# Debug configuration for payload logging
DEBUG_LOG_BRIDGE_PAYLOAD = os.getenv("DEBUG_LOG_BRIDGE_PAYLOAD", "false").lower() in ("true", "1", "yes")


def format_error_response(exception: Exception, base_message: str) -> dict[str, Any]:
    """Format error response with details, request_id, and optional stacktrace.

    Creates consistent error response structure with detailed context for debugging.
    Includes error details extracted from exception attributes, request_id for
    tracing, and stack trace when LOG_LEVEL=debug. For ExceptionGroup instances,
    extracts the root cause to provide meaningful error messages.

    Args:
        exception: Exception that occurred
        base_message: Human-readable error message for the response

    Returns:
        Error response dict with:
        - error: Base error message string (includes root cause for ExceptionGroups)
        - details: Error context dict (if extractable from exception)
        - request_id: UUID for request correlation (if context available)
        - stacktrace: Full stack trace string (only if LOG_LEVEL=debug)

    Examples:
        >>> err = ConnectionError("Connection refused")
        >>> err.errno = 111
        >>> format_error_response(err, "Failed to connect")
        {'error': 'Failed to connect', 'details': {'errno': 111}, 'request_id': '...'}

        >>> # With debug mode enabled
        >>> import os
        >>> os.environ['LOG_LEVEL'] = 'debug'
        >>> format_error_response(ValueError("test"), "Invalid value")
        {'error': 'Invalid value', 'request_id': '...', 'stacktrace': 'Traceback...'}
    """
    # For ExceptionGroups, extract root cause for better error reporting
    # For other exceptions, use base_message as-is (existing behavior)
    if isinstance(exception, BaseExceptionGroup):
        root_cause = extract_root_cause_message(exception)
        if root_cause and root_cause not in base_message:
            error_message = f"{base_message}: {root_cause}"
        else:
            error_message = base_message
    else:
        error_message = base_message

    response: dict[str, Any] = {"error": error_message}

    # Extract error details from exception attributes
    details = extract_error_details(exception)
    if details:
        response["details"] = details

    # Add request_id for tracing (enables log correlation)
    context = get_request_context()
    if context and "request_id" in context:
        response["request_id"] = context["request_id"]

    # Include stacktrace only in debug mode (security: don't expose internals in production)
    log_level = get_log_level()
    if log_level == "debug":
        response["stacktrace"] = get_stacktrace_string()

    # Always log full error with stack trace regardless of response detail level
    logger.error(
        "Error occurred: %s",
        error_message,
        exc_info=True,
        extra={"error_details": details} if details else {},
    )

    return response


async def _handle_single_usage_request(request: BridgeRequestBody, timeout_ms: int) -> Any:
    """Execute single-usage request with direct SDK pattern.

    Args:
        request: Bridge request with server config and method params
        timeout_ms: Timeout in milliseconds

    Returns:
        Result from MCP method execution

    Raises:
        HTTPException: On validation or execution failure
    """
    logger.info("Single-usage mode: using simple SDK pattern")
    try:
        result = await execute_single_usage_request(request, request.method, request.params, timeout_ms)
        return result
    except HTTPException:
        # Already formatted by single_usage module
        raise
    except ValidationError as exc:
        # Pydantic validation errors with field details
        error_response = format_error_response(exc, "Request validation failed")
        raise HTTPException(status_code=422, detail=error_response) from exc
    except Exception as exc:
        # Generic exception handler - don't include str(exc) for ExceptionGroups
        # as format_error_response will extract the root cause
        base_msg = "MCP method execution failed"
        if not isinstance(exc, BaseExceptionGroup):
            base_msg = f"{base_msg}: {str(exc)}"
        error_response = format_error_response(exc, base_msg)
        raise HTTPException(status_code=500, detail=error_response) from exc


async def _handle_cached_client_request(request: BridgeRequestBody, timeout_ms: int) -> Any:
    """Execute request using cached ManagedClient.

    Args:
        request: Bridge request with server config and method params
        timeout_ms: Timeout in milliseconds

    Returns:
        Result from MCP method execution

    Raises:
        HTTPException: On client creation or execution failure
    """
    logger.info("Cached mode: using ManagedClient with cache")

    # Get cached client or create new one (cache-first pattern, Story 3.2)
    try:
        handle, session = await get_or_create_client(request)
    except HTTPException as exc:
        logger.error(
            "Failed to create MCP client: status=%d, detail=%s",
            exc.status_code,
            exc.detail,
            exc_info=True,
        )
        raise
    except Exception as exc:
        # Don't include str(exc) for ExceptionGroups as format_error_response will extract root cause
        base_msg = "Failed to create MCP client"
        if not isinstance(exc, BaseExceptionGroup):
            base_msg = f"{base_msg}: {str(exc)}"
        error_response = format_error_response(exc, base_msg)
        raise HTTPException(status_code=500, detail=error_response) from exc

    # Execute method with timeout protection
    try:
        result = await invoke_with_timeout(session, request.method, request.params, timeout_ms)
        return result
    except HTTPException as exc:
        logger.error(
            "HTTPException occurred: status=%d, detail=%s",
            exc.status_code,
            exc.detail,
            exc_info=True,
        )
        raise
    except ValidationError as exc:
        error_response = format_error_response(exc, "Request validation failed")
        raise HTTPException(status_code=422, detail=error_response) from exc
    except ConnectionError as exc:
        error_response = format_error_response(exc, f"Connection error: {type(exc).__name__}")
        raise HTTPException(status_code=503, detail=error_response) from exc
    except asyncio.TimeoutError as exc:
        error_response = format_error_response(exc, f"Request timeout: {timeout_ms}ms")
        raise HTTPException(status_code=504, detail=error_response) from exc
    except Exception as exc:
        # Don't include str(exc) for ExceptionGroups as format_error_response will extract root cause
        base_msg = "MCP method execution failed"
        if not isinstance(exc, BaseExceptionGroup):
            base_msg = f"{base_msg}: {str(exc)}"
        error_response = format_error_response(exc, base_msg)
        raise HTTPException(status_code=500, detail=error_response) from exc


@router.post("/bridge")
async def bridge_endpoint(
    request: BridgeRequestBody,
    timeout: int | None = Query(
        default=None,
        description="Custom timeout override in milliseconds",
        gt=0,
        le=300000,
    ),
    _verified: None = Depends(verify_token),
) -> JSONResponse:
    """
    Bridge MCP protocol requests to MCP servers.

    Gets cached MCP client or creates new one, initializes it, and routes the
    incoming method request through the MCP Python SDK with timeout protection.

    Args:
        request: Bridge request with serverPath, method, params, args, env
        timeout: Custom timeout override in milliseconds (Story 3.6)
        _verified: Bearer token verification dependency

    Returns:
        JSON response returned directly from the MCP SDK method invocation
        with X-Request-ID header set

    Note:
        Uses cache-first pattern (Story 3.2). Single-usage clients bypass cache
        and are cleaned up immediately. Cached clients remain until TTL expires.
        Timeout protection added in Story 3.6 - defaults to 60s, overridable via query param.
        Request context propagation added in Story 4.3 - all logs include request_id.
    """
    # Setup request context for logging correlation (Story 4.3)
    await setup_request_context(request)

    # Log complete bridge payload if debug logging is enabled
    if DEBUG_LOG_BRIDGE_PAYLOAD:
        payload_dict = request.model_dump(mode="json", exclude_none=True)
        # Mask sensitive data in the payload
        if "request_headers" in payload_dict and payload_dict["request_headers"]:
            payload_dict["request_headers"] = mask_dict_values(payload_dict["request_headers"], mask_all=True)
        if "env" in payload_dict and payload_dict["env"]:
            payload_dict["env"] = mask_dict_values(payload_dict["env"], mask_all=False)
        logger.debug("Bridge endpoint payload: %s", payload_dict)

    # Log with masked request headers (all values sensitive)
    if request.request_headers:
        logger.debug(
            "Request headers: %s",
            mask_dict_values(request.request_headers, mask_all=True),
        )

    # Compute effective timeout: query param overrides default (Story 3.6)
    timeout_ms = timeout if timeout is not None else DEFAULT_TIMEOUT_MS

    # Delegate to specialized handler based on usage mode
    if request.single_usage:
        result = await _handle_single_usage_request(request, timeout_ms)
    else:
        result = await _handle_cached_client_request(request, timeout_ms)

    # Convert Pydantic models to JSON-serializable dictionaries
    # exclude_none=True removes null fields from response (matches TypeScript behavior)
    if hasattr(result, "model_dump"):
        result_dict = result.model_dump(mode="json", exclude_none=True)
    else:
        result_dict = result

    # Add X-Request-ID header for request tracing (Story 4.3)
    request_id = get_request_id()
    headers = {}
    if request_id:
        headers["X-Request-ID"] = request_id

    return JSONResponse(content=result_dict, status_code=200, headers=headers)
