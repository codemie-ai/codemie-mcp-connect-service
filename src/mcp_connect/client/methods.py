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

"""MCP method routing utilities for the bridge endpoint."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Awaitable, Callable

from fastapi import HTTPException
from mcp import ClientSession
from mcp.types import PaginatedRequestParams

from ..utils.logger import get_logger
from ..utils.masking import REDACTED_VALUE, is_sensitive_key

logger = get_logger(__name__)


def _mask_params_recursive(data: Any) -> Any:
    """Recursively mask sensitive values in parameters for logging.

    Args:
        data: Any data structure (dict, list, primitive, etc.)

    Returns:
        Copy of data with sensitive values masked
    """
    if data is None:
        return None
    if isinstance(data, dict):
        return {k: REDACTED_VALUE if is_sensitive_key(k) else _mask_params_recursive(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_mask_params_recursive(item) for item in data]
    if isinstance(data, (str, int, float, bool)):
        return data
    # For other types (objects, etc.), convert to string representation
    return str(type(data).__name__)


async def invoke_mcp_method(
    session: ClientSession,
    method: str,
    params: Any,
) -> Any:
    """Route MCP method strings to the appropriate ClientSession API.

    Args:
        session: Initialized MCP ClientSession.
        method: MCP method identifier (e.g., "tools/list").
        params: Method-specific parameters supplied by the request body.

    Returns:
        The raw MCP SDK response for the invoked method.

    Raises:
        HTTPException: If parameters are invalid or the method is unsupported.
    """
    # Log incoming MCP method call with masked parameters
    masked_params = _mask_params_recursive(params)
    logger.info(
        "Invoking MCP method: %s",
        method,
        extra={"method": method, "params": masked_params},
    )

    normalized_method = method.strip()
    payload = _ensure_mapping(params, normalized_method)

    if normalized_method == "tools/list":
        logger.info("Calling tools/list with cursor: %s", payload.get("cursor"))
        return await _call_with_optional_cursor(session.list_tools, payload)

    if normalized_method == "tools/call":
        name = _require_param(payload, "name")
        arguments = _optional_mapping_param(payload, "arguments")
        logger.info(
            "Calling tool: %s with arguments: %s",
            name,
            _mask_params_recursive(arguments),
        )
        return await session.call_tool(name, arguments)

    if normalized_method == "prompts/list":
        logger.debug("Calling prompts/list with cursor: %s", payload.get("cursor"))
        return await _call_with_optional_cursor(session.list_prompts, payload)

    if normalized_method == "prompts/get":
        name = _require_param(payload, "name")
        arguments = _optional_mapping_param(payload, "arguments")
        logger.debug(
            "Getting prompt: %s with arguments: %s",
            name,
            _mask_params_recursive(arguments),
        )
        return await session.get_prompt(name, arguments)

    if normalized_method == "resources/list":
        logger.debug("Calling resources/list with cursor: %s", payload.get("cursor"))
        return await _call_with_optional_cursor(session.list_resources, payload)

    if normalized_method == "resources/read":
        uri = _require_param(payload, "uri")
        logger.debug("Reading resource: %s", uri)
        return await session.read_resource(uri)

    if normalized_method == "resources/templates/list":
        logger.debug("Calling resources/templates/list with cursor: %s", payload.get("cursor"))
        return await _call_with_optional_cursor(session.list_resource_templates, payload)

    if normalized_method == "resources/subscribe":
        uri = _require_param(payload, "uri")
        logger.debug("Subscribing to resource: %s", uri)
        return await session.subscribe_resource(uri)

    if normalized_method == "resources/unsubscribe":
        uri = _require_param(payload, "uri")
        logger.debug("Unsubscribing from resource: %s", uri)
        return await session.unsubscribe_resource(uri)

    if normalized_method == "completion/complete":
        ref = _require_param(payload, "ref")
        argument = _require_param(payload, "argument")
        context_arguments = _optional_mapping_param(payload, "context")
        logger.debug(
            "Completing: ref=%s, argument=%s, context=%s",
            _mask_params_recursive(ref),
            _mask_params_recursive(argument),
            _mask_params_recursive(context_arguments),
        )
        return await session.complete(ref, argument, context_arguments=context_arguments or None)

    if normalized_method == "logging/setLevel":
        level = _require_param(payload, "level")
        logger.debug("Setting MCP server logging level to: %s", level)
        return await session.set_logging_level(level)

    if normalized_method == "ping":
        logger.debug("Sending ping to MCP server")
        return await session.send_ping()

    logger.warning("Unsupported MCP method requested: %s", method)
    raise HTTPException(
        status_code=400,
        detail={"error": f"Unsupported method: {method}"},
    )


def _ensure_mapping(params: Any, method: str) -> dict[str, Any]:
    """Ensure params is a mapping for downstream processing."""
    logger.debug(
        "Ensuring params is mapping for method: %s, params_type: %s",
        method,
        type(params).__name__,
    )

    if params is None:
        logger.debug("Params is None, returning empty dict")
        return {}
    if isinstance(params, Mapping):
        logger.debug("Params is valid mapping with %d keys", len(params))
        return dict(params)

    logger.warning(
        "Invalid params type for method %s: expected object, got %s",
        method,
        type(params).__name__,
    )
    raise HTTPException(
        status_code=400,
        detail={"error": f"Invalid params for {method}: expected object"},
    )


def _require_param(params: dict[str, Any], key: str) -> Any:
    """Return a required parameter or raise HTTP 400 when missing."""
    if key not in params or params[key] is None:
        logger.warning("Missing required parameter: %s", key)
        raise HTTPException(
            status_code=400,
            detail={"error": f"Missing required parameter: {key}"},
        )

    # Mask the value if it's sensitive before logging
    value = params[key]
    masked_value = REDACTED_VALUE if is_sensitive_key(key) else _mask_params_recursive(value)
    logger.debug("Retrieved required parameter: %s = %s", key, masked_value)
    return value


def _optional_mapping_param(params: dict[str, Any], key: str) -> dict[str, Any]:
    """Return a mapping parameter, defaulting to an empty dict."""
    value = params.get(key)

    if value is None:
        logger.debug("Optional mapping parameter '%s' not provided, using empty dict", key)
        return {}

    if isinstance(value, Mapping):
        masked_value = _mask_params_recursive(value)
        logger.debug(
            "Retrieved optional mapping parameter: %s with %d keys: %s",
            key,
            len(value),
            masked_value,
        )
        return dict(value)

    logger.warning(
        "Invalid parameter '%s': expected object, got %s",
        key,
        type(value).__name__,
    )
    raise HTTPException(
        status_code=400,
        detail={"error": f"Invalid parameter '{key}': expected object"},
    )


PaginatedCaller = Callable[..., Awaitable[Any]]


async def _call_with_optional_cursor(
    func: PaginatedCaller,
    params: dict[str, Any],
) -> Any:
    """Invoke list-style methods with optional cursor pagination."""
    cursor = params.get("cursor")

    if cursor:
        logger.debug(
            "Calling paginated method with cursor: %s",
            _mask_params_recursive(cursor),
        )
        pagination = PaginatedRequestParams(cursor=str(cursor))
        return await func(params=pagination)

    logger.debug("Calling paginated method without cursor (first page)")
    return await func()


__all__ = ["invoke_mcp_method"]
