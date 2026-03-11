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
Tests for MCP client manager cache integration (Story 3.2).

Verifies cache-first pattern, single-usage bypass, and cache key generation.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.mcp_connect.client import manager as manager_module
from src.mcp_connect.client.cache import MCPClientCache
from src.mcp_connect.client.manager import get_or_create_client
from src.mcp_connect.client.types import MCPClientHandle
from src.mcp_connect.models.request import BridgeRequestBody


@pytest.fixture
async def cache():
    """Create a fresh cache for each test."""
    cache = MCPClientCache()
    manager_module._client_cache = cache
    yield cache
    await cache.clear()
    manager_module._client_cache = None


@pytest.fixture
def mock_client_handle():
    """Create a mock MCPClientHandle for testing."""
    mock_handle = AsyncMock(spec=MCPClientHandle)
    mock_handle.session = AsyncMock()
    mock_handle.context = AsyncMock()
    mock_handle.cleanup = AsyncMock()
    return mock_handle


@pytest.fixture
def sample_request():
    """Create a sample bridge request for testing."""
    return BridgeRequestBody(
        serverPath="npx",
        method="ping",
        params={},
        args=["-y", "@modelcontextprotocol/server-everything"],
        env={"NODE_ENV": "test"},
    )


@pytest.mark.asyncio
async def test_cache_miss_creates_and_caches_client(cache, mock_client_handle, sample_request):
    """Test cache miss: creates new managed client and stores in cache."""
    with patch(
        "src.mcp_connect.client.managed.ManagedClient.spawn",
        return_value=AsyncMock(session=mock_client_handle.session),
    ) as mock_spawn:
        # First call should be a cache miss
        handle, session = await get_or_create_client(sample_request)

        # Verify client was created
        assert mock_spawn.called
        assert mock_spawn.call_count == 1
        assert session == mock_client_handle.session


@pytest.mark.asyncio
async def test_cache_hit_returns_cached_client(cache, mock_client_handle, sample_request):
    """Test cache hit: second call with same request returns cached session."""
    mock_managed = AsyncMock()
    mock_managed.session = mock_client_handle.session

    with patch(
        "src.mcp_connect.client.managed.ManagedClient.spawn",
        return_value=mock_managed,
    ) as mock_spawn:
        # First call - cache miss
        handle1, session1 = await get_or_create_client(sample_request)
        assert mock_spawn.call_count == 1

        # Second call with same request - should be cache hit
        handle2, session2 = await get_or_create_client(sample_request)

        # Verify spawn was NOT called again
        assert mock_spawn.call_count == 1
        # Both sessions should be the same
        assert session2 == session1


@pytest.mark.asyncio
async def test_cache_key_consistency(mock_client_handle):
    """Test that same request parameters generate same cache key."""
    from src.mcp_connect.client.cache import generate_cache_key

    request1 = BridgeRequestBody(
        serverPath="npx",
        method="ping",
        params={},
        args=["-y", "@modelcontextprotocol/server-everything"],
        env={"NODE_ENV": "test"},
    )

    request2 = BridgeRequestBody(
        serverPath="npx",
        method="ping",
        params={},
        args=["-y", "@modelcontextprotocol/server-everything"],
        env={"NODE_ENV": "test"},
    )

    # Same parameters should generate same key
    key1 = generate_cache_key(request1)
    key2 = generate_cache_key(request2)

    assert key1 == key2


@pytest.mark.asyncio
async def test_different_requests_generate_different_keys():
    """Test that different request parameters generate different cache keys."""
    from src.mcp_connect.client.cache import generate_cache_key

    request1 = BridgeRequestBody(
        serverPath="npx",
        method="ping",
        params={},
        args=["-y", "@modelcontextprotocol/server-everything"],
    )

    request2 = BridgeRequestBody(
        serverPath="python",  # Different serverPath
        method="ping",
        params={},
        args=["-m", "mcp_server_test"],
    )

    request3 = BridgeRequestBody(
        serverPath="npx",
        method="ping",
        params={},
        args=["-y", "@modelcontextprotocol/server-everything"],
        env={"NODE_ENV": "production"},  # Different env
    )

    # Different parameters should generate different keys
    key1 = generate_cache_key(request1)
    key2 = generate_cache_key(request2)
    key3 = generate_cache_key(request3)

    assert key1 != key2
    assert key1 != key3
    assert key2 != key3


@pytest.mark.asyncio
async def test_cache_hit_logging(cache, mock_client_handle, sample_request, caplog):
    """Test that cache hit generates appropriate log message."""
    import logging

    caplog.set_level(logging.INFO, logger="src.mcp_connect.client.manager")

    mock_managed = AsyncMock()
    mock_managed.session = mock_client_handle.session

    with patch(
        "src.mcp_connect.client.managed.ManagedClient.spawn",
        return_value=mock_managed,
    ):
        # First call - cache miss
        await get_or_create_client(sample_request)

        # Second call - cache hit
        caplog.clear()
        await get_or_create_client(sample_request)

        # Verify cache hit log message
        assert any("Cache HIT" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_cache_miss_logging(cache, mock_client_handle, sample_request, caplog):
    """Test that cache miss generates appropriate log message."""
    import logging

    caplog.set_level(logging.INFO, logger="src.mcp_connect.client.manager")

    mock_managed = AsyncMock()
    mock_managed.session = mock_client_handle.session

    with patch(
        "src.mcp_connect.client.managed.ManagedClient.spawn",
        return_value=mock_managed,
    ):
        # First call - cache miss
        caplog.clear()
        await get_or_create_client(sample_request)

        # Verify cache miss log message
        assert any("Cache MISS" in record.message for record in caplog.records)
        assert any("creating new managed client" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_cache_stores_handle_after_creation(cache, mock_client_handle, sample_request):
    """Test that newly created managed client is stored in cache."""
    from src.mcp_connect.client.cache import generate_cache_key

    cache_key = generate_cache_key(sample_request)
    mock_managed = AsyncMock()
    mock_managed.session = mock_client_handle.session

    with patch(
        "src.mcp_connect.client.managed.ManagedClient.spawn",
        return_value=mock_managed,
    ):
        # Cache should be empty initially
        cached_client = await cache.get(cache_key)
        assert cached_client is None

        # Create client (cache miss)
        await get_or_create_client(sample_request)

        # Cache should now contain the managed client
        cached_client = await cache.get(cache_key)
        assert cached_client == mock_managed


@pytest.mark.asyncio
async def test_http_transport_cached_correctly(cache, mock_client_handle):
    """Test that HTTP transport requests are cached correctly."""
    request = BridgeRequestBody(
        serverPath="https://example.com/mcp",
        method="ping",
        params={},
        mcp_headers={"Authorization": "Bearer test-token"},
    )

    mock_managed = AsyncMock()
    mock_managed.session = mock_client_handle.session

    with patch(
        "src.mcp_connect.client.managed.ManagedClient.spawn",
        return_value=mock_managed,
    ) as mock_spawn:
        # First call
        handle1, session1 = await get_or_create_client(request)
        assert mock_spawn.call_count == 1

        # Second call - should use cache
        handle2, session2 = await get_or_create_client(request)
        assert mock_spawn.call_count == 1  # Not called again
        assert session2 == session1
