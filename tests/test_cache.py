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
Tests for MCP Client Cache with TTL
"""

import asyncio
import os
from unittest.mock import AsyncMock, patch

import pytest

from src.mcp_connect.client.cache import MCPClientCache, generate_cache_key
from src.mcp_connect.models.request import BridgeRequestBody


@pytest.mark.asyncio
async def test_cache_get_hit():
    """Test cache returns client when within TTL."""
    cache = MCPClientCache(ttl_seconds=10)
    mock_client = AsyncMock()
    mock_client.session.send_ping = AsyncMock(return_value=None)

    await cache.set("test_key", mock_client)
    result = await cache.get("test_key")

    assert result is mock_client


@pytest.mark.asyncio
async def test_cache_get_miss():
    """Test cache returns None for non-existent key."""
    cache = MCPClientCache(ttl_seconds=10)

    result = await cache.get("non_existent_key")

    assert result is None


@pytest.mark.asyncio
async def test_cache_get_expired():
    """Test cache returns None and removes expired client."""
    cache = MCPClientCache(ttl_seconds=1)
    mock_client = AsyncMock()
    mock_client.session.send_ping = AsyncMock(return_value=None)

    await cache.set("test_key", mock_client)

    # Wait for TTL to expire
    await asyncio.sleep(1.1)

    result = await cache.get("test_key")

    assert result is None
    # Verify client was removed from cache
    assert "test_key" not in cache._cache


@pytest.mark.asyncio
async def test_cache_set():
    """Test cache stores client with timestamp."""
    cache = MCPClientCache(ttl_seconds=10)
    mock_client = AsyncMock()

    await cache.set("test_key", mock_client)

    # Verify stored in cache
    assert "test_key" in cache._cache
    stored_client, timestamp = cache._cache["test_key"]
    assert stored_client is mock_client
    assert isinstance(timestamp, float)
    assert timestamp > 0


@pytest.mark.asyncio
async def test_cache_remove():
    """Test cache removes specific client."""
    cache = MCPClientCache(ttl_seconds=10)
    mock_client = AsyncMock()

    await cache.set("test_key", mock_client)
    await cache.remove("test_key")

    # Verify removed from cache
    assert "test_key" not in cache._cache


@pytest.mark.asyncio
async def test_cache_clear():
    """Test cache removes all clients."""
    cache = MCPClientCache(ttl_seconds=10)
    mock_client1 = AsyncMock()
    mock_client2 = AsyncMock()
    mock_client3 = AsyncMock()

    await cache.set("key1", mock_client1)
    await cache.set("key2", mock_client2)
    await cache.set("key3", mock_client3)

    await cache.clear()

    # Verify all removed
    assert len(cache._cache) == 0


@pytest.mark.asyncio
async def test_generate_cache_key_consistency():
    """Test same request parameters produce same cache key."""
    request1 = BridgeRequestBody(
        serverPath="/usr/local/bin/mcp-server",
        method="tools/list",
        params={},
        args=["--port", "8080"],
        env={"API_KEY": "test123"},
        mcp_headers={"Authorization": "Bearer token"},
        http_transport_type="streamable-http",
    )

    request2 = BridgeRequestBody(
        serverPath="/usr/local/bin/mcp-server",
        method="tools/list",
        params={},
        args=["--port", "8080"],
        env={"API_KEY": "test123"},
        mcp_headers={"Authorization": "Bearer token"},
        http_transport_type="streamable-http",
    )

    key1 = generate_cache_key(request1)
    key2 = generate_cache_key(request2)

    assert key1 == key2
    assert len(key1) == 64  # SHA-256 hex digest length


@pytest.mark.asyncio
async def test_generate_cache_key_different():
    """Test different parameters produce different keys."""
    request1 = BridgeRequestBody(
        serverPath="/usr/local/bin/mcp-server",
        method="tools/list",
        params={},
    )

    request2 = BridgeRequestBody(
        serverPath="/usr/local/bin/other-server",
        method="tools/list",
        params={},
    )

    key1 = generate_cache_key(request1)
    key2 = generate_cache_key(request2)

    assert key1 != key2


@pytest.mark.asyncio
async def test_generate_cache_key_sorted():
    """Test sorting ensures same key regardless of order."""
    request1 = BridgeRequestBody(
        serverPath="/usr/local/bin/mcp-server",
        method="tools/list",
        params={},
        args=["--port", "8080", "--host", "localhost"],
        env={"API_KEY": "test123", "ENV": "prod"},
    )

    request2 = BridgeRequestBody(
        serverPath="/usr/local/bin/mcp-server",
        method="tools/list",
        params={},
        args=["--host", "localhost", "--port", "8080"],  # Different order
        env={"ENV": "prod", "API_KEY": "test123"},  # Different order
    )

    key1 = generate_cache_key(request1)
    key2 = generate_cache_key(request2)

    assert key1 == key2


@pytest.mark.asyncio
async def test_cache_thread_safety():
    """Test concurrent cache operations don't cause race conditions."""
    cache = MCPClientCache(ttl_seconds=10)

    # Create multiple mock clients
    clients = [AsyncMock() for _ in range(10)]
    for client in clients:
        client.session.send_ping = AsyncMock(return_value=None)

    # Concurrent set operations
    async def set_client(idx: int) -> None:
        await cache.set(f"key_{idx}", clients[idx])

    # Concurrent get operations
    async def get_client(idx: int) -> None:
        result = await cache.get(f"key_{idx}")
        # May be None if get happens before set
        if result is not None:
            assert result is clients[idx]

    # Run concurrent operations
    set_tasks = [set_client(i) for i in range(10)]
    get_tasks = [get_client(i) for i in range(10)]
    all_tasks = set_tasks + get_tasks

    await asyncio.gather(*all_tasks)

    # Verify all clients were stored
    assert len(cache._cache) == 10


@pytest.mark.asyncio
async def test_env_var_ttl_default():
    """Test default TTL when env var not set."""
    # Clear env var if set
    original_value = os.environ.pop("MCP_CONNECT_CLIENT_CACHE_TTL", None)

    try:
        cache = MCPClientCache()
        assert cache._ttl == 300  # 300 seconds = 5 minutes
    finally:
        # Restore original env var if it existed
        if original_value is not None:
            os.environ["MCP_CONNECT_CLIENT_CACHE_TTL"] = original_value


@pytest.mark.asyncio
async def test_env_var_ttl_custom():
    """Test custom TTL from env var."""
    # Set custom env var (in milliseconds)
    os.environ["MCP_CONNECT_CLIENT_CACHE_TTL"] = "60000"  # 60 seconds

    try:
        cache = MCPClientCache()
        assert cache._ttl == 60  # Converted to seconds
    finally:
        # Clean up env var
        os.environ.pop("MCP_CONNECT_CLIENT_CACHE_TTL", None)


@pytest.mark.asyncio
async def test_env_var_ttl_override():
    """Test constructor parameter overrides env var."""
    # Set env var
    os.environ["MCP_CONNECT_CLIENT_CACHE_TTL"] = "60000"

    try:
        cache = MCPClientCache(ttl_seconds=120)
        assert cache._ttl == 120  # Constructor param wins
    finally:
        os.environ.pop("MCP_CONNECT_CLIENT_CACHE_TTL", None)


@pytest.mark.asyncio
async def test_ttl_edge_case():
    """Test sliding window TTL - accessing cache resets expiration timer."""
    cache = MCPClientCache(ttl_seconds=1)
    mock_client = AsyncMock()
    mock_client.session.send_ping = AsyncMock(return_value=None)

    await cache.set("test_key", mock_client)

    # Wait just under TTL, then access (resets timer)
    await asyncio.sleep(0.9)
    result1 = await cache.get("test_key")
    assert result1 is mock_client  # Still valid

    # Wait 0.2s more (total 1.1s from initial set, but only 0.2s since last access)
    await asyncio.sleep(0.2)
    result2 = await cache.get("test_key")
    assert result2 is mock_client  # Still valid due to sliding window

    # Wait past TTL without accessing
    await asyncio.sleep(1.1)  # Now 1.1s since last access
    result3 = await cache.get("test_key")
    assert result3 is None  # Expired


@pytest.mark.asyncio
async def test_sliding_window_ttl():
    """Test that accessing cached client updates last_used_at timestamp."""
    cache = MCPClientCache(ttl_seconds=2)
    mock_client = AsyncMock()
    mock_client.session.send_ping = AsyncMock(return_value=None)

    start_time = 100.0

    # Set initial cache entry at t=100
    with patch("src.mcp_connect.client.cache.time.monotonic", return_value=start_time):
        await cache.set("test_key", mock_client)

    # Verify last_used_at is initial time
    _, last_used_at = cache._cache["test_key"]
    assert last_used_at == start_time

    # Access cache at t=101 (1 second later)
    with patch("src.mcp_connect.client.cache.time.monotonic", return_value=start_time + 1.0):
        result = await cache.get("test_key")
        assert result is mock_client

    # Verify last_used_at was updated to t=101
    _, last_used_at_after_access = cache._cache["test_key"]
    assert last_used_at_after_access == start_time + 1.0

    # At t=102.5, entry should still be valid (1.5s since last access < 2s TTL)
    with patch("src.mcp_connect.client.cache.time.monotonic", return_value=start_time + 2.5):
        result = await cache.get("test_key")
        assert result is mock_client  # Still valid

    # At t=104.6, entry should be expired (2.1s since last access > 2s TTL)
    with patch("src.mcp_connect.client.cache.time.monotonic", return_value=start_time + 4.6):
        result = await cache.get("test_key")
        assert result is None  # Expired


@pytest.mark.asyncio
async def test_remove_nonexistent_key():
    """Test removing non-existent key doesn't raise error."""
    cache = MCPClientCache(ttl_seconds=10)

    # Should not raise exception
    await cache.remove("non_existent_key")


@pytest.mark.asyncio
async def test_clear_empty_cache():
    """Test clearing empty cache doesn't raise error."""
    cache = MCPClientCache(ttl_seconds=10)

    # Should not raise exception
    await cache.clear()
    assert len(cache._cache) == 0


@pytest.mark.asyncio
async def test_client_cleanup_on_remove():
    """Test client cleanup is attempted on remove."""
    cache = MCPClientCache(ttl_seconds=10)
    mock_handle = AsyncMock()
    mock_handle.cleanup = AsyncMock()

    await cache.set("test_key", mock_handle)
    await cache.remove("test_key")

    # Verify cleanup() was called
    mock_handle.cleanup.assert_called_once()


@pytest.mark.asyncio
async def test_client_cleanup_on_expiration():
    """Test client cleanup is attempted on TTL expiration."""
    cache = MCPClientCache(ttl_seconds=1)
    mock_handle = AsyncMock()
    mock_handle.cleanup = AsyncMock()
    mock_handle.session.send_ping = AsyncMock(return_value=None)

    await cache.set("test_key", mock_handle)
    await asyncio.sleep(1.1)

    # Access to trigger expiration cleanup
    await cache.get("test_key")

    # Verify cleanup() was called
    mock_handle.cleanup.assert_called_once()


@pytest.mark.asyncio
async def test_client_cleanup_error_suppressed():
    """Test cleanup errors are suppressed gracefully."""
    cache = MCPClientCache(ttl_seconds=10)
    mock_handle = AsyncMock()
    mock_handle.cleanup = AsyncMock()

    # Make cleanup raise exception
    mock_handle.cleanup.side_effect = Exception("Cleanup failed")

    await cache.set("test_key", mock_handle)

    # Should not raise exception
    await cache.remove("test_key")

    # Verify client was still removed from cache
    assert "test_key" not in cache._cache
