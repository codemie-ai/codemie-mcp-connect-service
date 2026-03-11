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

"""Simple single-usage MCP client implementation using SDK patterns.

This module provides a simplified client creation pattern for single-usage scenarios,
eliminating complexity related to caching, lifecycle management, and ping validation.
Follows the straightforward context manager pattern from the MCP Python SDK.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from fastapi import HTTPException
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.types import Implementation

from ..models.request import BridgeRequestBody
from ..utils import apply_substitutions, mask_dict_values, mask_sensitive_headers
from ..utils.logger import get_logger

# Reuse the shared transport context manager to avoid duplication
from .transports import get_transport_ctx

logger = get_logger(__name__)

CLIENT_INFO = Implementation(name="mcp-bridge", version="1.0.0")

# Timeout constants - configurable via environment variables
# Read from env vars with defaults (in milliseconds), convert to seconds for SDK usage
INIT_TIMEOUT_SECONDS = int(os.getenv("MCP_CONNECT_INIT_TIMEOUT", "30000")) / 1000.0
HTTP_TIMEOUT_SECONDS = int(os.getenv("MCP_CONNECT_HTTP_TIMEOUT", "30000")) / 1000.0
SSE_READ_TIMEOUT_SECONDS = int(os.getenv("MCP_CONNECT_SSE_READ_TIMEOUT", "300000")) / 1000.0


async def execute_single_usage_request(
    request: BridgeRequestBody,
    method: str,
    params: Any,
    timeout_ms: int,
) -> Any:
    """
    Execute single-usage MCP request using simple SDK pattern.

    Creates MCP client, executes method, and cleans up automatically using
    context managers. No caching, no lifecycle management, no ping validation.
    Much simpler than the cached client path.

    Pattern follows SDK best practices:
    ```python
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("tool_name", {...})
    ```

    Args:
        request: Bridge request with serverPath, method, params, args, env
        method: MCP method name (e.g., "tools/call", "prompts/list")
        params: Method parameters
        timeout_ms: Timeout in milliseconds

    Returns:
        Method result from MCP server

    Raises:
        HTTPException: If client creation, initialization, or method execution fails

    Note:
        All cleanup is automatic via context managers. No manual cleanup needed.
        This function is self-contained and stateless.
    """
    # Apply environment variable substitution and header substitution
    processed_request = apply_substitutions(request)

    # Detect transport type
    from .manager import detect_transport_type

    transport_type = detect_transport_type(
        processed_request.serverPath,
        processed_request.http_transport_type,
    )

    timeout_sec = timeout_ms / 1000.0

    # Route to appropriate transport handler
    if transport_type == "stdio":
        return await _execute_stdio_request(processed_request, method, params, timeout_sec)
    elif transport_type == "streamable-http":
        return await _execute_http_request(processed_request, method, params, timeout_sec)
    elif transport_type == "sse":
        return await _execute_sse_request(processed_request, method, params, timeout_sec)
    else:
        raise HTTPException(
            status_code=400,
            detail={"error": f"Unsupported transport type: {transport_type}"},
        )


async def _execute_stdio_request(
    request: BridgeRequestBody,
    method: str,
    params: Any,
    timeout_sec: float,
) -> Any:
    """Execute single-usage stdio request using simple SDK pattern."""
    # Extract command and parameters
    command = request.serverPath
    args = request.args or []
    env = request.env or {}

    # Log with masked env (all values sensitive)
    logger.debug(
        "Single-usage stdio: command=%s, args=%s, env=%s",
        command,
        args,
        mask_dict_values(env, mask_all=True),
    )

    # Build server parameters
    server_params = StdioServerParameters(
        command=command,
        args=args,
        env=env,
    )

    try:
        # Simple SDK pattern - context managers handle all cleanup
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write, client_info=CLIENT_INFO) as session:
                # Initialize with timeout
                await asyncio.wait_for(session.initialize(), timeout=INIT_TIMEOUT_SECONDS)

                # Import method invocation utility
                from .methods import invoke_mcp_method

                # Execute method with timeout
                result = await asyncio.wait_for(
                    invoke_mcp_method(session, method, params),
                    timeout=timeout_sec,
                )

                return result

    except asyncio.TimeoutError as exc:
        logger.error("Single-usage request timeout: method=%s, timeout=%0.1fs", method, timeout_sec)
        raise HTTPException(
            status_code=504,
            detail={
                "error": f"Request timeout after {int(timeout_sec * 1000)}ms",
                "method": method,
            },
        ) from exc
    except Exception as exc:
        from ..utils.errors import extract_root_cause_message

        error_message = extract_root_cause_message(exc)
        logger.error("Single-usage stdio request failed: %s", error_message, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": f"Failed to execute MCP request: {error_message}"},
        ) from exc


async def _execute_http_request(
    request: BridgeRequestBody,
    method: str,
    params: Any,
    timeout_sec: float,
) -> Any:
    """Execute single-usage HTTP request using simple SDK pattern."""
    headers = request.mcp_headers or {}
    logger.debug("Single-usage HTTP: headers=%s", mask_sensitive_headers(headers))

    try:
        async with get_transport_ctx(request, headers) as (read, write, *rest):
            async with ClientSession(read, write, client_info=CLIENT_INFO) as session:
                # Initialize with timeout
                await asyncio.wait_for(session.initialize(), timeout=INIT_TIMEOUT_SECONDS)

                # Import method invocation utility
                from .methods import invoke_mcp_method

                # Execute method with timeout
                result = await asyncio.wait_for(
                    invoke_mcp_method(session, method, params),
                    timeout=timeout_sec,
                )

                return result

    except asyncio.TimeoutError as exc:
        logger.error("Single-usage request timeout: method=%s, timeout=%0.1fs", method, timeout_sec)
        raise HTTPException(
            status_code=504,
            detail={
                "error": f"Request timeout after {int(timeout_sec * 1000)}ms",
                "method": method,
            },
        ) from exc
    except Exception as exc:
        from ..utils.errors import extract_root_cause_message

        error_message = extract_root_cause_message(exc)
        logger.error("Single-usage HTTP request failed: %s", error_message, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": f"Failed to execute MCP request: {error_message}"},
        ) from exc


async def _execute_sse_request(
    request: BridgeRequestBody,
    method: str,
    params: Any,
    timeout_sec: float,
) -> Any:
    """Execute single-usage SSE request using simple SDK pattern."""
    logger.warning("SSE transport is deprecated. Please migrate to Streamable HTTP.")

    headers = request.mcp_headers or {}
    logger.debug("Single-usage SSE: headers=%s", mask_sensitive_headers(headers))

    try:
        # Simple SDK pattern - context managers handle all cleanup
        async with sse_client(
            url=request.serverPath,
            headers=headers,
            timeout=HTTP_TIMEOUT_SECONDS,
            sse_read_timeout=SSE_READ_TIMEOUT_SECONDS,
        ) as (read, write):
            async with ClientSession(read, write, client_info=CLIENT_INFO) as session:
                # Initialize with timeout
                await asyncio.wait_for(session.initialize(), timeout=INIT_TIMEOUT_SECONDS)

                # Import method invocation utility
                from .methods import invoke_mcp_method

                # Execute method with timeout
                result = await asyncio.wait_for(
                    invoke_mcp_method(session, method, params),
                    timeout=timeout_sec,
                )

                return result

    except asyncio.TimeoutError as exc:
        logger.error("Single-usage request timeout: method=%s, timeout=%0.1fs", method, timeout_sec)
        raise HTTPException(
            status_code=504,
            detail={
                "error": f"Request timeout after {int(timeout_sec * 1000)}ms",
                "method": method,
            },
        ) from exc
    except Exception as exc:
        from ..utils.errors import extract_root_cause_message

        error_message = extract_root_cause_message(exc)
        logger.error("Single-usage SSE request failed: %s", error_message, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": f"Failed to execute MCP request: {error_message}"},
        ) from exc
