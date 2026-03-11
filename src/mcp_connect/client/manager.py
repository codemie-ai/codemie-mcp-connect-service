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

"""MCP Client Manager utilities for detecting transports and creating clients."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import HTTPException
from mcp import ClientSession

from ..models.request import BridgeRequestBody
from ..utils import apply_substitutions
from ..utils.logger import get_logger
from .cache import MCPClientCache, generate_cache_key
from .managed import ManagedClient
from .methods import invoke_mcp_method

logger = get_logger(__name__)

# Module-level cache instance (initialized at startup)
_client_cache: MCPClientCache | None = None


async def invoke_with_timeout(
    session: ClientSession,
    method: str,
    params: Any,
    timeout_ms: int,
) -> Any:
    """
    Invoke MCP method with timeout protection.

    Wraps MCP method calls with asyncio.wait_for() to enforce request timeout.
    Tracks elapsed time and returns structured error response on timeout.

    Args:
        session: MCP client session
        method: MCP method name (e.g., "tools/call", "prompts/list")
        params: Method parameters
        timeout_ms: Timeout in milliseconds

    Returns:
        Method result from MCP server

    Raises:
        HTTPException: 500 status with timeout error details if operation exceeds timeout
    """
    timeout_sec = timeout_ms / 1000.0
    start_time = time.monotonic()

    try:
        result = await asyncio.wait_for(
            invoke_mcp_method(session, method, params),
            timeout=timeout_sec,
        )
        return result
    except asyncio.TimeoutError as exc:
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logger.error(
            "Request timeout after %dms for method %s (timeout: %dms)",
            elapsed_ms,
            method,
            timeout_ms,
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": f"Request timeout after {timeout_ms}ms",
                "method": method,
                "elapsed_ms": elapsed_ms,
            },
        ) from exc


def detect_transport_type(server_path: str, http_transport_type: str | None = None) -> str:
    """
    Detect MCP transport type from server path and optional HTTP override.

    Args:
        server_path: Command or URL for the MCP server.
        http_transport_type: Optional override ("streamable-http" or "sse") for HTTP URLs.

    Returns:
        Transport type string: "stdio", "streamable-http", or "sse".

    Raises:
        HTTPException: If WebSocket protocol detected (ws:// or wss://) - not supported.
    """
    # Reject WebSocket transports explicitly (not supported per ADR-007)
    if server_path.startswith(("ws://", "wss://")):
        raise HTTPException(
            status_code=400,
            detail={"error": "WebSocket not supported. Use Streamable HTTP instead."},
        )

    if server_path.startswith(("http://", "https://")):  # noqa: S105
        # Default to streamable-http, allow override to sse for backward compatibility
        return "sse" if http_transport_type == "sse" else "streamable-http"

    return "stdio"


async def get_or_create_client(
    request: BridgeRequestBody,
) -> tuple[ManagedClient, ClientSession]:
    """
    Get or create MCP client with caching.

    Main entry point for request handlers. Returns ClientSession for making
    MCP protocol calls.

    Architecture (Per-Client Dedicated Tasks):
    - Single-usage mode: Creates raw MCPClientHandle (not cached, immediate cleanup)
    - Cached mode: Creates ManagedClient running in dedicated task that:
      * Enters context managers in continuous execution
      * Keeps contexts open for cache TTL duration
      * Exits contexts on cleanup signal (preserves anyio task affinity)
      * Each cached client has its own asyncio.Task (~18KB overhead)

    Args:
        request: Bridge request with serverPath, method, params, args, env

    Returns:
        Tuple of (handle_or_managed_client, session):
        - For single-usage: (MCPClientHandle, session) - caller must cleanup handle
        - For cached: (ManagedClient, session) - cleanup handled by cache/scheduler

    Raises:
        HTTPException: If client creation fails
        RuntimeError: If cache not initialized

    Note:
        - Single-usage clients (request.single_usage=True) are NOT cached
        - Cached clients remain valid until TTL expires (5 minutes default)
        - Cache key includes all configuration affecting client behavior
        - ManagedClient tasks preserve anyio task affinity (contexts enter/exit in same task)
    """
    if _client_cache is None:
        raise RuntimeError("Client cache not initialized - service not started properly")

    # Apply substitutions before generating cache key
    processed_request = apply_substitutions(request)

    # Check cache first
    cache_key = generate_cache_key(processed_request)
    managed_client = await _client_cache.get(cache_key)

    if managed_client:
        logger.info(
            "Cache HIT for %s (key: %s)",
            processed_request.serverPath[:50],
            cache_key[:16],
        )
        return managed_client, managed_client.session

    # Cache miss - create new managed client
    logger.info(
        "Cache MISS for %s, creating new managed client (key: %s)",
        processed_request.serverPath[:50],
        cache_key[:16],
    )

    # Spawn managed client in dedicated task
    managed_client = await ManagedClient.spawn(processed_request)

    # Store in cache
    await _client_cache.set(cache_key, managed_client)

    return managed_client, managed_client.session
