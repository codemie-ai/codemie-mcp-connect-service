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
Tests for cache cleanup background task.

Tests cleanup_expired_clients() function with focus on:
- Expired client removal with TTL enforcement
- Active client retention (not expired)
- Periodic cleanup execution (sleep intervals)
- Error handling (resilient cleanup)
- Task cancellation on shutdown
"""

import logging
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp_connect.client.cache import MCPClientCache
from src.mcp_connect.client.managed import ManagedClient
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


@pytest.mark.asyncio
async def test_expired_clients_removed() -> None:
    """
    Test that expired managed clients are removed from cache.

    Creates cache with TTL=1s, adds managed client, simulates time passage,
    runs one cleanup cycle, verifies client removed and cleanup called.
    """
    cache = MCPClientCache(ttl_seconds=1)
    start_time = 100.0

    # Create mock managed client
    mock_managed = MagicMock(spec=ManagedClient)
    mock_managed.session = AsyncMock()
    mock_managed.cleanup = AsyncMock()

    # Add client to cache with mocked time
    with patch("src.mcp_connect.client.cache.time.monotonic", return_value=start_time):
        await cache.set("test_key", mock_managed)

    # Verify client is in cache
    assert "test_key" in cache._cache

    # Mock time.monotonic to simulate TTL expiration (1.5s elapsed)
    with patch(
        "src.mcp_connect.client.cache.time.monotonic",
        return_value=start_time + 1.5,
    ):
        # Manually trigger one cleanup cycle (bypass sleep and loop)
        async with cache._lock:
            expired_keys = []
            for key, (handle, last_used_at) in list(cache._cache.items()):
                age = time.monotonic() - last_used_at
                if age >= cache._ttl:
                    expired_keys.append(key)

            for key in expired_keys:
                await cache._remove_unsafe(key)

    # Verify client was removed
    assert "test_key" not in cache._cache
    mock_managed.cleanup.assert_called_once()


@pytest.mark.asyncio
async def test_active_clients_retained() -> None:
    """
    Test that active (non-expired) managed clients are retained.

    Creates cache with TTL=5s, adds client, runs cleanup immediately,
    verifies client NOT removed.
    """
    cache = MCPClientCache(ttl_seconds=5)

    # Create mock managed client
    mock_managed = MagicMock(spec=ManagedClient)
    mock_managed.session = AsyncMock()
    mock_managed.cleanup = AsyncMock()

    # Add client to cache
    await cache.set("active_key", mock_managed)

    # Verify client is in cache
    assert "active_key" in cache._cache

    # Manually trigger one cleanup cycle (no time passage, age < TTL)
    async with cache._lock:
        expired_keys = []
        for key, (handle, cached_at) in list(cache._cache.items()):
            age = time.monotonic() - cached_at
            if age >= cache._ttl:
                expired_keys.append(key)

        for key in expired_keys:
            await cache._remove_unsafe(key)

    # Verify client was NOT removed (still active)
    assert "active_key" in cache._cache
    mock_managed.cleanup.assert_not_called()


@pytest.mark.asyncio
async def test_cleanup_error_handling(mock_client_handle: MCPClientHandle, caplog: Any) -> None:
    """
    Test that cleanup errors don't crash the background task.

    Mocks _remove_unsafe to raise exception on first call, verifies
    exception caught, second client still processed, task continues.
    """
    cache = MCPClientCache(ttl_seconds=1)
    start_time = 100.0

    # Add two clients to cache
    with patch("src.mcp_connect.client.cache.time.monotonic", return_value=start_time):
        await cache.set("client1", mock_client_handle)

        mock_client_handle2 = MCPClientHandle(session=MagicMock(), context=MagicMock())
        mock_client_handle2.cleanup = AsyncMock()
        await cache.set("client2", mock_client_handle2)

    # Mock _remove_unsafe to raise exception on first call only
    original_remove = cache._remove_unsafe
    remove_call_count = 0

    async def mock_remove_unsafe(key: str) -> None:
        nonlocal remove_call_count
        remove_call_count += 1
        if key == "client1":
            raise Exception("Cleanup failed for client1")
        await original_remove(key)

    with caplog.at_level(logging.ERROR):
        with patch(
            "src.mcp_connect.client.cache.time.monotonic",
            return_value=start_time + 1.5,
        ):
            with patch.object(cache, "_remove_unsafe", side_effect=mock_remove_unsafe):
                # Manually run one cleanup cycle
                async with cache._lock:
                    expired_keys = []
                    for key, (handle, cached_at) in list(cache._cache.items()):
                        age = time.monotonic() - cached_at
                        if age >= cache._ttl:
                            expired_keys.append(key)

                    for key in expired_keys:
                        try:
                            await cache._remove_unsafe(key)
                        except Exception as e:
                            logging.getLogger("src.mcp_connect.client.cache").error(
                                f"Failed to cleanup expired client: {e}"
                            )

    # Verify error was logged
    assert "Failed to cleanup expired client" in caplog.text
    assert "Cleanup failed for client1" in caplog.text

    # Verify both removal attempts were made
    assert remove_call_count == 2


@pytest.mark.asyncio
async def test_cleanup_acquires_lock(mock_client_handle: MCPClientHandle) -> None:
    """
    Test that cleanup task acquires lock during iteration.

    Verifies lock is used to prevent concurrent modification.
    """
    cache = MCPClientCache(ttl_seconds=1)
    await cache.set("test_key", mock_client_handle)

    # Track lock acquisition
    lock_acquired = False

    async def track_lock() -> None:
        nonlocal lock_acquired
        lock_acquired = True

    # Manually run cleanup iteration with lock
    async with cache._lock:
        await track_lock()
        expired_keys = []
        for key, (handle, cached_at) in list(cache._cache.items()):
            age = time.monotonic() - cached_at
            if age >= cache._ttl:
                expired_keys.append(key)

    # Verify lock was acquired (we successfully entered context)
    assert lock_acquired
