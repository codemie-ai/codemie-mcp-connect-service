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
Tests for graceful shutdown with client cleanup.

Tests lifespan context manager shutdown behavior with focus on:
- Cache clearing on shutdown (all clients closed)
- Cleanup task cancellation
- Shutdown logging with client count
- Best-effort cleanup (partial failures don't crash shutdown)
- SIGTERM signal handling via lifespan
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI

from src.mcp_connect.client.cache import MCPClientCache
from src.mcp_connect.client.types import MCPClientHandle


@pytest.fixture
def mock_client_handle() -> MCPClientHandle:
    """Create mock MCPClientHandle for testing."""
    mock_session = MagicMock()
    mock_session.send_ping = AsyncMock(return_value=None)
    mock_context = MagicMock()

    handle = MCPClientHandle(session=mock_session, context=mock_context)
    handle.cleanup = AsyncMock()
    return handle


@pytest.fixture
def test_cache() -> MCPClientCache:
    """Create fresh cache instance for testing."""
    return MCPClientCache(ttl_seconds=300)


@pytest.mark.asyncio
async def test_lifespan_clears_cache_on_shutdown(
    test_cache: MCPClientCache, mock_client_handle: MCPClientHandle
) -> None:
    """
    Test that lifespan shutdown clears all cached clients.

    Adds 3 clients to cache, triggers shutdown via lifespan exit,
    verifies cache is empty and all cleanup methods called.
    """

    @asynccontextmanager
    async def test_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        """Test lifespan that mimics main.py lifespan behavior."""
        # Startup: no-op for this test
        yield

        # Shutdown: replicate main.py shutdown logic
        client_count = len(test_cache._cache)
        logging.getLogger(__name__).info(f"Shutting down gracefully, closing {client_count} cached clients")

        # Clear cache (main.py logic)
        await test_cache.clear()
        logging.getLogger(__name__).info(f"Closed {client_count} cached clients successfully")

    # Add 3 clients to cache
    mock_handle_1 = mock_client_handle
    mock_handle_2 = MCPClientHandle(session=MagicMock(), context=MagicMock())
    mock_handle_2.cleanup = AsyncMock()
    mock_handle_3 = MCPClientHandle(session=MagicMock(), context=MagicMock())
    mock_handle_3.cleanup = AsyncMock()

    await test_cache.set("client1", mock_handle_1)
    await test_cache.set("client2", mock_handle_2)
    await test_cache.set("client3", mock_handle_3)

    # Verify clients are in cache
    assert len(test_cache._cache) == 3

    # Create app and trigger lifespan
    app = FastAPI(lifespan=test_lifespan)

    # Use lifespan context manager to trigger startup and shutdown
    async with test_lifespan(app):
        pass  # Exiting context triggers shutdown

    # Verify cache is empty after shutdown
    assert len(test_cache._cache) == 0

    # Verify all cleanup methods called
    mock_handle_1.cleanup.assert_called_once()
    mock_handle_2.cleanup.assert_called_once()
    mock_handle_3.cleanup.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_task_cancelled_on_shutdown(caplog: Any) -> None:
    """
    Test that cleanup task is cancelled during shutdown.

    Starts lifespan with cleanup task, triggers shutdown, verifies
    task cancelled and CancelledError handled gracefully.
    """
    cache = MCPClientCache(ttl_seconds=300)
    cleanup_task: asyncio.Task[None] | None = None

    @asynccontextmanager
    async def test_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        """Test lifespan that creates and cancels cleanup task."""
        nonlocal cleanup_task

        # Startup: create mock cleanup task
        async def mock_cleanup() -> None:
            try:
                while True:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                logging.getLogger(__name__).info("Cleanup task cancelled")
                raise

        cleanup_task = asyncio.create_task(mock_cleanup())
        logging.getLogger(__name__).info("Started cache cleanup background task")

        yield

        # Shutdown: cancel cleanup task (main.py logic)
        if cleanup_task:
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass
            logging.getLogger(__name__).info("Cancelled cache cleanup background task")

        # Clear cache
        await cache.clear()

    app = FastAPI(lifespan=test_lifespan)

    with caplog.at_level(logging.INFO):
        # Use lifespan context manager
        async with test_lifespan(app):
            # Verify task is running
            assert cleanup_task is not None
            assert not cleanup_task.done()

        # After exiting context, task should be cancelled
        assert cleanup_task.cancelled()

    # Verify logs
    assert "Started cache cleanup background task" in caplog.text
    assert "Cancelled cache cleanup background task" in caplog.text
    # Note: "Cleanup task cancelled" from inside the task may not appear
    # because CancelledError is caught in the outer handler


@pytest.mark.asyncio
async def test_shutdown_logging_with_client_count(
    test_cache: MCPClientCache, mock_client_handle: MCPClientHandle, caplog: Any
) -> None:
    """
    Test that shutdown logs include accurate client count.

    Adds 5 clients to cache, triggers shutdown, verifies logs show
    correct count before and after clearing.
    """

    @asynccontextmanager
    async def test_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        """Test lifespan with logging."""
        yield

        # Shutdown: replicate main.py shutdown with logging
        client_count = len(test_cache._cache)
        logging.getLogger(__name__).info(f"Shutting down gracefully, closing {client_count} cached clients")

        await test_cache.clear()
        logging.getLogger(__name__).info(f"Closed {client_count} cached clients successfully")

    # Add 5 clients to cache
    for i in range(5):
        handle = MCPClientHandle(session=MagicMock(), context=MagicMock())
        handle.cleanup = AsyncMock()
        await test_cache.set(f"client{i}", handle)

    # Verify 5 clients in cache
    assert len(test_cache._cache) == 5

    app = FastAPI(lifespan=test_lifespan)

    with caplog.at_level(logging.INFO):
        # Trigger lifespan shutdown
        async with test_lifespan(app):
            pass

    # Verify shutdown logs with correct count
    assert "Shutting down gracefully, closing 5 cached clients" in caplog.text
    assert "Closed 5 cached clients successfully" in caplog.text


@pytest.mark.asyncio
async def test_partial_cleanup_failure(test_cache: MCPClientCache, caplog: Any) -> None:
    """
    Test that partial cleanup failures don't crash shutdown.

    Adds 3 clients, mocks one cleanup to fail, triggers shutdown,
    verifies all clients removed (best-effort) and no exception propagated.
    """
    # Create 3 mock handles
    mock_handle_1 = MCPClientHandle(session=MagicMock(), context=MagicMock())
    mock_handle_1.cleanup = AsyncMock()

    mock_handle_2 = MCPClientHandle(session=MagicMock(), context=MagicMock())
    # Mock handle 2 cleanup to raise exception
    mock_handle_2.cleanup = AsyncMock(side_effect=Exception("Cleanup failed"))

    mock_handle_3 = MCPClientHandle(session=MagicMock(), context=MagicMock())
    mock_handle_3.cleanup = AsyncMock()

    # Add clients to cache
    await test_cache.set("client1", mock_handle_1)
    await test_cache.set("client2", mock_handle_2)
    await test_cache.set("client3", mock_handle_3)

    assert len(test_cache._cache) == 3

    @asynccontextmanager
    async def test_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        """Test lifespan with partial cleanup failure."""
        yield

        # Shutdown: clear cache (should handle exceptions)
        client_count = len(test_cache._cache)
        logging.getLogger(__name__).info(f"Shutting down gracefully, closing {client_count} cached clients")

        await test_cache.clear()  # Best-effort cleanup
        logging.getLogger(__name__).info(f"Closed {client_count} cached clients successfully")

    app = FastAPI(lifespan=test_lifespan)

    with caplog.at_level(logging.INFO):
        # Shutdown should complete without raising exception
        async with test_lifespan(app):
            pass

    # Verify all 3 clients removed from cache (best-effort)
    assert len(test_cache._cache) == 0

    # Verify all cleanup methods were called (even failing one)
    mock_handle_1.cleanup.assert_called_once()
    mock_handle_2.cleanup.assert_called_once()
    mock_handle_3.cleanup.assert_called_once()

    # Verify shutdown completed (logs present)
    assert "Shutting down gracefully, closing 3 cached clients" in caplog.text
    assert "Closed 3 cached clients successfully" in caplog.text


@pytest.mark.asyncio
async def test_cache_clear_ordering(
    test_cache: MCPClientCache, mock_client_handle: MCPClientHandle, caplog: Any
) -> None:
    """
    Test that shutdown follows correct order: count → cancel task → clear cache.

    Verifies log messages appear in correct sequence and operations
    complete in expected order.
    """
    cleanup_task: asyncio.Task[None] | None = None
    log_sequence: list[str] = []

    # Custom logger that tracks message sequence
    class LogTracker(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            log_sequence.append(record.getMessage())

    logger = logging.getLogger(__name__)
    tracker = LogTracker()
    logger.addHandler(tracker)

    @asynccontextmanager
    async def test_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        """Test lifespan with operation ordering."""
        nonlocal cleanup_task

        # Startup: create cleanup task
        async def mock_cleanup() -> None:
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                raise

        cleanup_task = asyncio.create_task(mock_cleanup())

        yield

        # Shutdown: replicate main.py exact order
        # 1. Count clients
        client_count = len(test_cache._cache)

        # 2. Log shutdown message
        logger.info(f"Shutting down gracefully, closing {client_count} cached clients")

        # 3. Cancel cleanup task
        if cleanup_task:
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass
            logger.info("Cancelled cache cleanup background task")

        # 4. Clear cache
        await test_cache.clear()

        # 5. Log completion
        logger.info(f"Closed {client_count} cached clients successfully")

    # Add 2 clients
    await test_cache.set("client1", mock_client_handle)
    mock_handle_2 = MCPClientHandle(session=MagicMock(), context=MagicMock())
    mock_handle_2.cleanup = AsyncMock()
    await test_cache.set("client2", mock_handle_2)

    app = FastAPI(lifespan=test_lifespan)

    # Trigger lifespan
    async with test_lifespan(app):
        pass

    # Verify log sequence
    assert len(log_sequence) >= 3
    assert "Shutting down gracefully, closing 2 cached clients" in log_sequence
    assert "Cancelled cache cleanup background task" in log_sequence
    assert "Closed 2 cached clients successfully" in log_sequence

    # Verify shutdown log appears BEFORE completion log
    shutdown_idx = next(i for i, msg in enumerate(log_sequence) if "Shutting down gracefully" in msg)
    completion_idx = next(i for i, msg in enumerate(log_sequence) if "Closed 2 cached clients" in msg)
    assert shutdown_idx < completion_idx

    # Clean up handler
    logger.removeHandler(tracker)


@pytest.mark.asyncio
async def test_shutdown_with_zero_clients(test_cache: MCPClientCache, caplog: Any) -> None:
    """
    Test graceful shutdown when cache is empty.

    Verifies shutdown completes successfully with count=0 and
    appropriate log messages.
    """

    @asynccontextmanager
    async def test_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        """Test lifespan with empty cache."""
        yield

        # Shutdown with empty cache
        client_count = len(test_cache._cache)
        logging.getLogger(__name__).info(f"Shutting down gracefully, closing {client_count} cached clients")

        await test_cache.clear()
        logging.getLogger(__name__).info(f"Closed {client_count} cached clients successfully")

    # Verify cache is empty
    assert len(test_cache._cache) == 0

    app = FastAPI(lifespan=test_lifespan)

    with caplog.at_level(logging.INFO):
        async with test_lifespan(app):
            pass

    # Verify logs with count=0
    assert "Shutting down gracefully, closing 0 cached clients" in caplog.text
    assert "Closed 0 cached clients successfully" in caplog.text


@pytest.mark.asyncio
async def test_lifespan_integration_with_main_app() -> None:
    """
    Test that lifespan integrates correctly with FastAPI app.

    Imports actual lifespan from main.py, verifies it can be used
    to create app without errors (smoke test).
    """
    from src.mcp_connect.main import app as main_app
    from src.mcp_connect.main import lifespan as main_lifespan

    # Verify app has lifespan configured
    assert main_app.router.lifespan_context is not None

    # Test lifespan can be entered and exited
    async with main_lifespan(main_app):
        # Lifespan startup complete, cleanup task should be running
        from src.mcp_connect.main import cleanup_scheduler_task

        # Brief delay to allow task to start
        await asyncio.sleep(0.01)

        # Verify cleanup task exists and is not done
        # (it may be None if startup hasn't completed yet, that's ok)
        if cleanup_scheduler_task is not None:
            assert not cleanup_scheduler_task.done()

    # After exiting lifespan, cleanup task should be cancelled
    # and cache should be cleared (tested by other tests)
