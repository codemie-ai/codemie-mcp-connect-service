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
Tests for MCP Client Cache Ping Validation

Tests ping-based client validation functionality to ensure stale or
disconnected clients are detected and removed from cache before reuse.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.mcp_connect.client.cache import MCPClientCache


@pytest.mark.asyncio
async def test_successful_ping_returns_client():
    """Test cache returns client when ping succeeds."""
    cache = MCPClientCache(ttl_seconds=10)

    # Create mock client handle with session.send_ping() that succeeds
    mock_handle = AsyncMock()
    mock_handle.session.send_ping = AsyncMock(return_value=None)

    await cache.set("test_key", mock_handle)
    result = await cache.get("test_key")

    # Verify client returned
    assert result is mock_handle

    # Verify send_ping() was called
    mock_handle.session.send_ping.assert_called_once()


@pytest.mark.asyncio
async def test_failed_ping_removes_client():
    """Test cache removes client and returns None when ping fails."""
    cache = MCPClientCache(ttl_seconds=10)

    # Create mock client handle with session.send_ping() that raises exception
    mock_handle = AsyncMock()
    mock_handle.session.send_ping = AsyncMock(side_effect=Exception("Connection lost"))

    await cache.set("test_key", mock_handle)
    result = await cache.get("test_key")

    # Verify None returned (cache miss)
    assert result is None

    # Verify client removed from cache
    assert "test_key" not in cache._cache

    # Verify send_ping() was called
    mock_handle.session.send_ping.assert_called_once()

    # Verify cleanup() was called during removal
    mock_handle.cleanup.assert_called_once()


@pytest.mark.asyncio
async def test_ping_timeout_treated_as_failure():
    """Test cache treats ping timeout as validation failure."""
    cache = MCPClientCache(ttl_seconds=10)

    # Create mock client handle with session.send_ping() that times out
    mock_handle = AsyncMock()
    mock_handle.session.send_ping = AsyncMock(side_effect=asyncio.TimeoutError())

    await cache.set("test_key", mock_handle)
    result = await cache.get("test_key")

    # Verify None returned (cache miss)
    assert result is None

    # Verify client removed from cache
    assert "test_key" not in cache._cache

    # Verify send_ping() was called
    mock_handle.session.send_ping.assert_called_once()


@pytest.mark.asyncio
async def test_validation_logging_on_timeout():
    """Test warning logged when ping times out."""
    cache = MCPClientCache(ttl_seconds=10)

    # Create mock client handle with session.send_ping() that times out
    mock_handle = AsyncMock()
    mock_handle.session.send_ping = AsyncMock(side_effect=asyncio.TimeoutError())

    await cache.set("test_key", mock_handle)

    # Capture logs
    with patch("src.mcp_connect.client.cache.logger") as mock_logger:
        result = await cache.get("test_key")

        # Verify None returned
        assert result is None

        # Verify warning logged with timeout message
        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args[0]
        assert "ping timeout" in call_args[0].lower()
        assert "removing from cache" in call_args[0].lower()


@pytest.mark.asyncio
async def test_validation_logging_on_exception():
    """Test warning logged with error details when ping fails."""
    cache = MCPClientCache(ttl_seconds=10)

    # Create mock client handle with session.send_ping() that raises exception
    error_message = "Connection lost to server"
    mock_handle = AsyncMock()
    mock_handle.session.send_ping = AsyncMock(side_effect=Exception(error_message))

    await cache.set("test_key", mock_handle)

    # Capture logs
    with patch("src.mcp_connect.client.cache.logger") as mock_logger:
        result = await cache.get("test_key")

        # Verify None returned
        assert result is None

        # Verify warning logged with error details
        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert "Cached client validation failed" in call_args[0][0]
        assert error_message in str(call_args[0][1])
        assert "removing from cache" in call_args[0][0].lower()


@pytest.mark.asyncio
async def test_no_logging_on_successful_ping():
    """Test no log output when ping succeeds (reduces noise)."""
    cache = MCPClientCache(ttl_seconds=10)

    # Create mock client handle with session.send_ping() that succeeds
    mock_handle = AsyncMock()
    mock_handle.session.send_ping = AsyncMock(return_value=None)

    await cache.set("test_key", mock_handle)

    # Capture logs
    with patch("src.mcp_connect.client.cache.logger") as mock_logger:
        result = await cache.get("test_key")

        # Verify client returned
        assert result is mock_handle

        # Verify NO warning logged on success
        mock_logger.warning.assert_not_called()


@pytest.mark.asyncio
async def test_validation_with_asyncio_wait_for_timeout():
    """Test ping validation uses asyncio.wait_for with 2-second timeout."""
    cache = MCPClientCache(ttl_seconds=10)

    # Create mock handle where send_ping() hangs forever
    mock_handle = AsyncMock()

    async def slow_ping():
        # Simulate slow/stuck ping that takes forever
        await asyncio.sleep(10)

    mock_handle.session.send_ping = slow_ping

    await cache.set("test_key", mock_handle)

    # Start timer
    start_time = asyncio.get_event_loop().time()

    result = await cache.get("test_key")

    # Calculate elapsed time
    elapsed = asyncio.get_event_loop().time() - start_time

    # Verify None returned (validation failed)
    assert result is None

    # Verify timeout occurred within reasonable bounds (2 seconds + small margin)
    # Should NOT wait the full 10 seconds that slow_ping() would take
    assert elapsed < 3.0, f"Timeout took too long: {elapsed}s (expected ~2s)"

    # Verify client removed from cache
    assert "test_key" not in cache._cache


@pytest.mark.asyncio
async def test_validation_exception_types():
    """Test different exception types during ping are all treated as failures."""
    cache = MCPClientCache(ttl_seconds=10)

    # Test various exception types
    exception_types = [
        Exception("Generic error"),
        ConnectionError("Connection failed"),
        RuntimeError("Runtime error"),
        ValueError("Invalid value"),
        asyncio.TimeoutError(),
    ]

    for idx, exception in enumerate(exception_types):
        # Create mock handle with send_ping() that raises this exception
        mock_handle = AsyncMock()
        mock_handle.session.send_ping = AsyncMock(side_effect=exception)

        key = f"test_key_{idx}"
        await cache.set(key, mock_handle)

        # Try to get - should return None due to validation failure
        result = await cache.get(key)

        # Verify None returned for all exception types
        assert result is None, f"Expected None for {type(exception).__name__}"

        # Verify client removed from cache
        assert key not in cache._cache


@pytest.mark.asyncio
async def test_validation_does_not_propagate_exceptions():
    """Test ping validation never propagates exceptions to caller."""
    cache = MCPClientCache(ttl_seconds=10)

    # Create mock handle with send_ping() that raises exception
    mock_handle = AsyncMock()
    mock_handle.session.send_ping = AsyncMock(side_effect=Exception("Unexpected error"))

    await cache.set("test_key", mock_handle)

    # Should not raise exception - should return None
    result = await cache.get("test_key")
    assert result is None


@pytest.mark.asyncio
async def test_cache_miss_on_nonexistent_key():
    """Test cache returns None for non-existent key without ping validation."""
    cache = MCPClientCache(ttl_seconds=10)

    # Get non-existent key - should return None immediately
    result = await cache.get("non_existent_key")

    # Verify None returned
    assert result is None

    # No ping should have been attempted (no client to validate)


@pytest.mark.asyncio
async def test_validation_order_ttl_then_ping():
    """Test TTL check happens before ping validation."""
    cache = MCPClientCache(ttl_seconds=1)

    # Create mock handle (ping will succeed, but TTL will fail first)
    mock_handle = AsyncMock()
    mock_handle.session.send_ping = AsyncMock(return_value=None)

    await cache.set("test_key", mock_handle)

    # Wait for TTL to expire
    await asyncio.sleep(1.1)

    result = await cache.get("test_key")

    # Verify None returned (TTL expired)
    assert result is None

    # Verify send_ping() was NOT called (TTL check failed first)
    mock_handle.session.send_ping.assert_not_called()


@pytest.mark.asyncio
async def test_concurrent_validation_thread_safe():
    """Test concurrent get operations with ping validation are thread-safe."""
    cache = MCPClientCache(ttl_seconds=10)

    # Create multiple mock handles
    handles = []
    for i in range(5):
        mock_handle = AsyncMock()
        # Alternating: some succeed, some fail
        if i % 2 == 0:
            mock_handle.session.send_ping = AsyncMock(return_value=None)
        else:
            mock_handle.session.send_ping = AsyncMock(side_effect=Exception("Fail"))
        handles.append(mock_handle)
        await cache.set(f"key_{i}", mock_handle)

    # Concurrent get operations
    async def get_client(idx: int):
        return await cache.get(f"key_{idx}")

    results = await asyncio.gather(*[get_client(i) for i in range(5)])

    # Verify results match expectations
    for i, result in enumerate(results):
        if i % 2 == 0:
            # Even indices should succeed (ping succeeds)
            assert result is handles[i]
        else:
            # Odd indices should fail (ping fails)
            assert result is None


@pytest.mark.asyncio
async def test_validation_cleanup_on_failure():
    """Test best-effort cleanup called when validation fails."""
    cache = MCPClientCache(ttl_seconds=10)

    # Create mock handle with failing ping
    mock_handle = AsyncMock()
    mock_handle.session.send_ping = AsyncMock(side_effect=Exception("Connection lost"))
    mock_handle.cleanup = AsyncMock()

    await cache.set("test_key", mock_handle)
    result = await cache.get("test_key")

    # Verify None returned
    assert result is None

    # Verify cleanup() was called
    mock_handle.cleanup.assert_called_once()


@pytest.mark.asyncio
async def test_validation_cleanup_error_suppressed():
    """Test cleanup errors during validation failure are suppressed."""
    cache = MCPClientCache(ttl_seconds=10)

    # Create mock handle with failing ping AND failing cleanup
    mock_handle = AsyncMock()
    mock_handle.session.send_ping = AsyncMock(side_effect=Exception("Connection lost"))
    mock_handle.cleanup = AsyncMock(side_effect=Exception("Cleanup failed"))

    await cache.set("test_key", mock_handle)

    # Should not raise exception from cleanup
    result = await cache.get("test_key")

    # Verify None returned (validation failed)
    assert result is None

    # Verify client still removed despite cleanup failure
    assert "test_key" not in cache._cache
