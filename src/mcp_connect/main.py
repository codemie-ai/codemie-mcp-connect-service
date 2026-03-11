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

"""FastAPI application entry point for MCP Connect Service.

This module provides the main FastAPI application instance that will be used
by Uvicorn to serve the MCP bridge HTTP endpoints.

The service enables AI agents to communicate with Model Context Protocol (MCP)
servers over HTTP, providing a bridge between HTTP requests and various MCP
transport protocols (stdio, Streamable HTTP, SSE).
"""

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .client import manager as client_manager_module
from .client.cache import MCPClientCache
from .server import router as server_router
from .utils.logger import get_logger, setup_logging

# Initialize structured logging at application startup
setup_logging()
logger = get_logger(__name__)

# Global references for lifecycle management
cleanup_scheduler_task: asyncio.Task[None] | None = None


async def _find_expired_cache_keys(cache: MCPClientCache) -> list[str]:
    """
    Identify cache keys that have exceeded TTL.

    Args:
        cache: MCPClientCache instance to check for expired entries

    Returns:
        List of expired cache keys
    """
    import time

    expired_keys = []
    async with cache._lock:
        for key, (_, last_used_at) in list(cache._cache.items()):
            age = time.monotonic() - last_used_at
            if age >= cache._ttl:
                expired_keys.append(key)

    return expired_keys


async def _remove_expired_clients(cache: MCPClientCache, expired_keys: list[str]) -> None:
    """
    Remove expired clients from cache with error handling.

    Args:
        cache: MCPClientCache instance to remove clients from
        expired_keys: List of cache keys to remove
    """
    import time

    if not expired_keys:
        return

    logger.info(f"Found {len(expired_keys)} expired clients")

    cleanup_start = time.monotonic()
    for key in expired_keys:
        try:
            await cache.remove(key)
        except Exception as e:
            logger.error(f"Failed to cleanup client {key[:16]}: {e}", exc_info=True)

    cleanup_duration = time.monotonic() - cleanup_start
    logger.info(f"Removed {len(expired_keys)} expired clients in {cleanup_duration:.2f}s")


async def _cleanup_scheduler(cache: MCPClientCache) -> None:
    """
    Periodic scheduler that removes expired clients from cache.

    Runs continuously until cancelled. Checks cache for expired clients
    at regular intervals and signals their dedicated tasks to cleanup.
    Interval is configurable via MCP_CONNECT_CACHE_CLEANUP_INTERVAL env var.

    Args:
        cache: MCPClientCache instance to clean up expired clients from
    """
    # Read cleanup interval from env var (default: 60 seconds)
    interval_ms = int(os.getenv("MCP_CONNECT_CACHE_CLEANUP_INTERVAL", "60000"))
    interval_seconds = interval_ms / 1000

    logger.info(f"Cleanup scheduler started, interval: {interval_seconds}s, TTL: {cache._ttl}s")

    while True:
        try:
            await asyncio.sleep(interval_seconds)
            logger.debug("Running cleanup cycle")

            expired_keys = await _find_expired_cache_keys(cache)
            await _remove_expired_clients(cache, expired_keys)

        except asyncio.CancelledError:
            logger.info("Cleanup scheduler cancelled")
            break
        except Exception as e:
            logger.error(f"Error in cleanup scheduler: {e}", exc_info=True)


def _print_startup_banner() -> None:
    """Print CodeMie MCP Connect startup banner."""
    banner = """
     ██████╗ ██████╗ ██████╗ ███████╗███╗   ███╗██╗███████╗
    ██╔════╝██╔═══██╗██╔══██╗██╔════╝████╗ ████║██║██╔════╝
    ██║     ██║   ██║██║  ██║█████╗  ██╔████╔██║██║█████╗
    ██║     ██║   ██║██║  ██║██╔══╝  ██║╚██╔╝██║██║██╔══╝
    ╚██████╗╚██████╔╝██████╔╝███████╗██║ ╚═╝ ██║██║███████╗
     ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝╚═╝     ╚═╝╚═╝╚══════╝

    ███╗   ███╗ ██████╗██████╗      ██████╗ ██████╗ ███╗   ██╗███╗   ██╗███████╗ ██████╗████████╗
    ████╗ ████║██╔════╝██╔══██╗    ██╔════╝██╔═══██╗████╗  ██║████╗  ██║██╔════╝██╔════╝╚══██╔══╝
    ██╔████╔██║██║     ██████╔╝    ██║     ██║   ██║██╔██╗ ██║██╔██╗ ██║█████╗  ██║        ██║
    ██║╚██╔╝██║██║     ██╔═══╝     ██║     ██║   ██║██║╚██╗██║██║╚██╗██║██╔══╝  ██║        ██║
    ██║ ╚═╝ ██║╚██████╗██║         ╚██████╗╚██████╔╝██║ ╚████║██║ ╚████║███████╗╚██████╗   ██║
    ╚═╝     ╚═╝ ╚═════╝╚═╝          ╚═════╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝  ╚═══╝╚══════╝ ╚═════╝   ╚═╝
    """
    # Print banner in cyan color using ANSI escape codes
    print(f"\033[36m{banner}\033[0m")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    FastAPI lifespan context manager for startup and shutdown operations.

    Starts cache and cleanup scheduler on startup.
    Stops scheduler and cleans up all cached clients on shutdown.

    Each cached client runs in its own dedicated task, ensuring context
    managers are entered and exited in continuous execution (preserving
    anyio task affinity).
    """
    global cleanup_scheduler_task

    # Print startup banner
    _print_startup_banner()

    # Get port from environment or use default
    port = os.getenv("PORT", "3000")
    local_url = f"http://localhost:{port}"

    # Log server information
    logger.info(f"Server listening on port {port}")
    logger.info(f"Local: {local_url}")
    logger.info(f"Health check URL: {local_url}/health")
    logger.info(f"MCP Bridge URL: {local_url}/bridge")

    # Startup: create cache
    cache = MCPClientCache()
    logger.info("Created client cache with TTL=%ds", cache._ttl)

    # Initialize module-level cache reference
    client_manager_module._client_cache = cache

    # Start cleanup scheduler
    cleanup_scheduler_task = asyncio.create_task(_cleanup_scheduler(cache))
    logger.info("Started cleanup scheduler")

    yield

    # Shutdown: stop scheduler first
    logger.info("Shutting down gracefully...")

    if cleanup_scheduler_task:
        cleanup_scheduler_task.cancel()
        try:
            await cleanup_scheduler_task
        except asyncio.CancelledError:
            pass
        logger.info("Stopped cleanup scheduler")

    # Clear all cached clients (signals all dedicated tasks to cleanup)
    logger.info("Clearing all cached clients...")
    await cache.clear()
    logger.info("All cached clients cleaned up")

    logger.info("Shutdown complete")


# Create FastAPI application instance with lifespan
app = FastAPI(
    title="MCP Connect Service",
    description="HTTP bridge service for Model Context Protocol (MCP) clients",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(server_router)


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Translate validation errors to appropriate HTTP status codes."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    if any(error.get("type") == "extra_forbidden" for error in exc.errors()):
        status_code = status.HTTP_400_BAD_REQUEST

    return JSONResponse(status_code=status_code, content={"detail": exc.errors()})


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Return consistent JSON body for HTTP exceptions."""

    content: Any
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        content = exc.detail
    else:
        content = {"detail": exc.detail}

    return JSONResponse(
        status_code=exc.status_code,
        content=content,
        headers=exc.headers,
    )


@app.get("/health")
async def health_check() -> dict[str, str]:
    """
    Health check endpoint for Kubernetes liveness/readiness probes.

    Returns a simple status indicator without checking external dependencies.
    This endpoint is intentionally lightweight to ensure reliable probe responses.

    Returns:
        dict: Status object with "ok" value
    """
    # Public endpoint for Kubernetes probes
    return {"status": "ok"}


# Additional endpoints will be added in Epic 2
# - POST /bridge - MCP protocol bridge endpoint
