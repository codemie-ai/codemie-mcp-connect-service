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

"""
Managed MCP Client - wraps client in dedicated task for lifecycle management.

This module provides ManagedClient class that ensures MCP client context managers
are entered and exited in continuous execution within a dedicated asyncio task,
preserving anyio cancel scope stack integrity.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

from mcp import ClientSession

from ..models.request import BridgeRequestBody
from ..utils.logger import get_logger
from ..utils.masking import mask_sensitive_headers

logger = get_logger(__name__)

# Timeout constants - configurable via environment variables
# Read from env vars with defaults (in milliseconds), convert to seconds for SDK usage
INIT_TIMEOUT_SECONDS = int(os.getenv("MCP_CONNECT_INIT_TIMEOUT", "30000")) / 1000.0
HTTP_TIMEOUT_SECONDS = int(os.getenv("MCP_CONNECT_HTTP_TIMEOUT", "30000")) / 1000.0
SSE_READ_TIMEOUT_SECONDS = int(os.getenv("MCP_CONNECT_SSE_READ_TIMEOUT", "300000")) / 1000.0


@dataclass
class ManagedClient:
    """
    Managed MCP client that runs in dedicated task.

    Ensures context managers are entered and exited in continuous execution
    within the same task, preserving anyio cancel scope stack integrity.

    This solves the anyio task affinity issue where cancel scopes must be
    entered and exited in LIFO order without intervening context changes.

    Lifecycle:
    1. spawn() creates task and waits for ready signal
    2. Task enters contexts, signals ready, waits for cleanup
    3. cleanup() signals task to exit contexts
    4. Task exits contexts and completes

    Attributes:
        session: ClientSession for making MCP protocol calls
        _cleanup_event: Event to signal when to exit contexts
        _task: Dedicated asyncio task running context managers
        _ready_future: Future that signals initialization complete
    """

    # Public interface
    session: ClientSession  # For making MCP calls

    # Internal state
    _cleanup_event: asyncio.Event  # Signal to exit contexts
    _task: asyncio.Task[None]  # Dedicated task running contexts
    _ready_future: asyncio.Future[ClientSession]  # Signals initialization complete

    @classmethod
    async def spawn(cls, request: BridgeRequestBody) -> ManagedClient:
        """
        Spawn a new managed client in dedicated task.

        Returns when client is ready to use (contexts entered, session initialized).

        Args:
            request: Bridge request with MCP server configuration

        Returns:
            ManagedClient instance with active session

        Raises:
            asyncio.TimeoutError: If client initialization takes > 30 seconds
            Exception: If client initialization fails
        """
        cleanup_event = asyncio.Event()
        ready_future: asyncio.Future[ClientSession] = asyncio.Future()

        # Spawn dedicated task
        task = asyncio.create_task(cls._run_client_lifecycle(request, cleanup_event, ready_future))

        # Wait for initialization to complete
        try:
            session = await asyncio.wait_for(ready_future, timeout=30.0)
            logger.info(
                "Managed client spawned successfully",
                extra={"server_path": request.serverPath[:50]},
            )
        except asyncio.TimeoutError:
            logger.error("Client initialization timeout - cleaning up task")
            cleanup_event.set()  # Signal task to cleanup
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            raise Exception("Client initialization timeout after 30 seconds")
        except Exception as e:
            logger.error(f"Client initialization failed: {e}", exc_info=True)
            cleanup_event.set()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            raise

        return cls(
            session=session,
            _cleanup_event=cleanup_event,
            _task=task,
            _ready_future=ready_future,
        )

    async def cleanup(self) -> None:
        """
        Request cleanup and wait for task to complete.

        Signals dedicated task to exit contexts and waits for completion.
        Times out after 10 seconds to prevent hanging.

        Note:
            This method is safe to call from any task. It only signals
            the dedicated task to exit contexts - the actual context exit
            happens in the dedicated task itself.
        """
        logger.debug("Requesting managed client cleanup")

        # Signal task to exit contexts
        self._cleanup_event.set()

        # Wait for task to complete
        try:
            await asyncio.wait_for(self._task, timeout=10.0)
            logger.debug("Managed client cleaned up successfully")
        except asyncio.TimeoutError:
            logger.error("Cleanup timeout (10s) - force cancelling task")
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                logger.warning("Task cancelled after timeout")
        except Exception as e:
            logger.error(f"Error during managed client cleanup: {e}", exc_info=True)

    @staticmethod
    async def _run_client_lifecycle(
        request: BridgeRequestBody,
        cleanup_event: asyncio.Event,
        ready_future: asyncio.Future[ClientSession],
    ) -> None:
        """
        Dedicated task that owns client lifecycle.

        This method runs in its own asyncio.Task for the lifetime of the
        cached client. It enters context managers, signals ready, waits for
        cleanup signal, then exits contexts - all in continuous execution
        to preserve cancel scope stack integrity.

        This is the core solution to the anyio task affinity issue:
        - Context managers entered in this task
        - Task waits (no other context operations)
        - Context managers exited in this task
        - Cancel scope stack preserved throughout

        Args:
            request: Bridge request with MCP server config
            cleanup_event: Event to signal when to exit contexts
            ready_future: Future to signal when session is ready
        """
        logger.info(
            "Starting managed client lifecycle task",
            extra={"server_path": request.serverPath[:50]},
        )

        try:
            # Import detect_transport_type to determine which transport to use
            from .manager import detect_transport_type

            # Determine transport based on serverPath and http_transport_type
            transport_type = detect_transport_type(request.serverPath, request.http_transport_type)

            logger.debug(f"Transport type: {transport_type}")
            # Route to appropriate transport implementation
            if transport_type == "stdio":
                await ManagedClient._run_stdio_client(request, cleanup_event, ready_future)
            elif transport_type == "streamable-http":
                await ManagedClient._run_streamable_http_client(request, cleanup_event, ready_future)
            elif transport_type == "sse":
                await ManagedClient._run_sse_client(request, cleanup_event, ready_future)
            else:
                raise ValueError(f"Unsupported transport type: {transport_type}")

        except asyncio.CancelledError:
            logger.info("Managed client task cancelled")
            if not ready_future.done():
                ready_future.set_exception(asyncio.CancelledError())
            raise

        except Exception as e:
            logger.error(f"Error in managed client lifecycle: {e}", exc_info=True)
            if not ready_future.done():
                ready_future.set_exception(e)

        logger.debug("Managed client lifecycle task completed")

    @staticmethod
    async def _run_stdio_client(
        request: BridgeRequestBody,
        cleanup_event: asyncio.Event,
        ready_future: asyncio.Future[ClientSession],
    ) -> None:
        """Run stdio transport client in dedicated task."""
        from mcp.client.stdio import StdioServerParameters, stdio_client

        # Prepare server parameters
        server_params = StdioServerParameters(
            command=request.serverPath,
            args=request.args or [],
            env=request.env,
        )

        logger.debug(f"Starting stdio client: {server_params.command}")

        # Enter contexts - these will stay open until cleanup signal
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                # Initialize session
                await asyncio.wait_for(session.initialize(), timeout=INIT_TIMEOUT_SECONDS)

                # Signal ready - caller can now use session
                ready_future.set_result(session)

                logger.debug("Session ready, waiting for cleanup signal")

                # Wait for cleanup signal - keep contexts open
                await cleanup_event.wait()

                logger.debug("Cleanup signal received - exiting contexts")
                # Contexts will exit here in LIFO order (session, then stdio)
                # This happens in the same task with no intervening contexts
                # Cancel scope stack preserved!

    @staticmethod
    async def _run_streamable_http_client(
        request: BridgeRequestBody,
        cleanup_event: asyncio.Event,
        ready_future: asyncio.Future[ClientSession],
    ) -> None:
        """Run Streamable HTTP transport client in dedicated task."""

        headers = request.mcp_headers or {}
        logger.info("Sending headers to MCP server: %s", mask_sensitive_headers(headers))

        logger.debug(f"Starting Streamable HTTP client: {request.serverPath}")

        # Use shared transport context manager to select the correct transport
        from .transports import get_transport_ctx

        async with get_transport_ctx(request, headers) as (read, write, *rest):
            async with ClientSession(read, write) as session:
                # Initialize session
                await asyncio.wait_for(session.initialize(), timeout=INIT_TIMEOUT_SECONDS)

                # Signal ready
                ready_future.set_result(session)

                logger.debug("Session ready, waiting for cleanup signal")

                # Wait for cleanup signal
                await cleanup_event.wait()

                logger.debug("Cleanup signal received - exiting contexts")
                # Contexts exit in LIFO order

    @staticmethod
    async def _run_sse_client(
        request: BridgeRequestBody,
        cleanup_event: asyncio.Event,
        ready_future: asyncio.Future[ClientSession],
    ) -> None:
        """Run SSE transport client in dedicated task (deprecated)."""
        from mcp.client.sse import sse_client

        logger.warning("SSE transport is deprecated. Please migrate to Streamable HTTP.")
        headers = request.mcp_headers or {}
        logger.info("Sending headers to MCP server: %s", mask_sensitive_headers(headers))

        logger.debug(f"Starting SSE client: {request.serverPath}")

        # Enter contexts - these will stay open until cleanup signal
        async with sse_client(
            url=request.serverPath,
            headers=headers,
            timeout=HTTP_TIMEOUT_SECONDS,
            sse_read_timeout=SSE_READ_TIMEOUT_SECONDS,
        ) as (read, write):
            async with ClientSession(read, write) as session:
                # Initialize session
                await asyncio.wait_for(session.initialize(), timeout=INIT_TIMEOUT_SECONDS)

                # Signal ready
                ready_future.set_result(session)

                logger.debug("Session ready, waiting for cleanup signal")

                # Wait for cleanup signal
                await cleanup_event.wait()

                logger.debug("Cleanup signal received - exiting contexts")
                # Contexts exit in LIFO order
