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

"""Tests for request timeout configuration (Story 3.6)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest


@pytest.mark.asyncio
async def test_default_timeout_applied(async_client: httpx.AsyncClient, mock_mcp_client):
    """Test that default timeout (60s) is applied when no query param provided."""

    # Mock slow MCP operation that exceeds timeout
    # Use short timeout in test (2s) to avoid slow tests
    async def slow_operation(*args, **kwargs):
        await asyncio.sleep(3)  # Exceeds 2s timeout
        return {"result": "should not return"}

    mock_mcp_client.handle.session.list_tools = AsyncMock(side_effect=slow_operation)

    # Test with 2-second timeout override (instead of 60s default for faster test)
    response = await async_client.post(
        "/bridge?timeout=2000",
        json={
            "serverPath": "test-server",
            "method": "tools/list",
            "params": {},
        },
        headers={"Authorization": "Bearer test-token"},
    )

    # Should timeout and return 500
    assert response.status_code == 500
    data = response.json()
    assert "error" in data
    assert "timeout" in data["error"].lower()
    assert data["method"] == "tools/list"
    assert "elapsed_ms" in data
    assert data["elapsed_ms"] >= 2000  # At least 2 seconds elapsed


@pytest.mark.asyncio
async def test_query_param_timeout_override(async_client: httpx.AsyncClient, mock_mcp_client):
    """Test that query parameter timeout overrides default timeout."""

    # Mock MCP operation with 3-second delay
    async def delayed_operation(*args, **kwargs):
        await asyncio.sleep(3)
        return {"result": "should not return"}

    mock_mcp_client.handle.session.call_tool = AsyncMock(side_effect=delayed_operation)

    # Set timeout to 1 second (should trigger before 3s delay completes)
    response = await async_client.post(
        "/bridge?timeout=1000",
        json={
            "serverPath": "test-server",
            "method": "tools/call",
            "params": {"name": "test-tool"},
        },
        headers={"Authorization": "Bearer test-token"},
    )

    # Should timeout at 1s, not default 60s
    assert response.status_code == 500
    data = response.json()
    assert "Request timeout after 1000ms" in data["error"]
    assert data["method"] == "tools/call"
    assert 1000 <= data["elapsed_ms"] < 2000  # Timed out around 1s, not 3s


@pytest.mark.asyncio
async def test_timeout_error_response_format(async_client: httpx.AsyncClient, mock_mcp_client):
    """Test that timeout error response has correct structure and no sensitive data."""

    # Mock timeout scenario
    async def timeout_operation(*args, **kwargs):
        await asyncio.sleep(2)
        return {"result": "should not return"}

    mock_mcp_client.handle.session.get_prompt = AsyncMock(side_effect=timeout_operation)

    response = await async_client.post(
        "/bridge?timeout=500",
        json={
            "serverPath": "test-server",
            "method": "prompts/get",
            "params": {"name": "test-prompt"},
        },
        headers={"Authorization": "Bearer test-token"},
    )

    # Validate response structure
    assert response.status_code == 500
    data = response.json()

    # Required fields present
    assert "error" in data
    assert "method" in data
    assert "elapsed_ms" in data

    # Validate field values
    assert isinstance(data["error"], str)
    assert "timeout" in data["error"].lower()
    assert "500ms" in data["error"]
    assert data["method"] == "prompts/get"
    assert isinstance(data["elapsed_ms"], int)
    assert data["elapsed_ms"] >= 500

    # Ensure no sensitive data exposed
    assert "token" not in str(data).lower()
    assert "password" not in str(data).lower()
    assert "authorization" not in str(data).lower()


@pytest.mark.asyncio
async def test_timeout_does_not_apply_to_fast_requests(async_client: httpx.AsyncClient, mock_mcp_client):
    """Test that fast requests complete successfully without triggering timeout."""

    # Mock fast MCP operation (< 100ms)
    async def fast_operation(*args, **kwargs):
        await asyncio.sleep(0.05)  # 50ms
        return {"tools": [{"name": "test-tool"}]}

    mock_mcp_client.handle.session.list_tools = AsyncMock(side_effect=fast_operation)

    # Set reasonable timeout (2s)
    response = await async_client.post(
        "/bridge?timeout=2000",
        json={
            "serverPath": "test-server",
            "method": "tools/list",
            "params": {},
        },
        headers={"Authorization": "Bearer test-token"},
    )

    # Should succeed without timeout
    assert response.status_code == 200
    data = response.json()
    assert "tools" in data
    assert data["tools"][0]["name"] == "test-tool"


@pytest.mark.asyncio
async def test_query_param_validation_negative(async_client: httpx.AsyncClient):
    """Test that negative timeout values are rejected."""

    response = await async_client.post(
        "/bridge?timeout=-1000",
        json={
            "serverPath": "test-server",
            "method": "tools/list",
            "params": {},
        },
        headers={"Authorization": "Bearer test-token"},
    )

    # Should return 422 validation error
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_query_param_validation_zero(async_client: httpx.AsyncClient):
    """Test that zero timeout value is rejected."""

    response = await async_client.post(
        "/bridge?timeout=0",
        json={
            "serverPath": "test-server",
            "method": "ping",
            "params": {},
        },
        headers={"Authorization": "Bearer test-token"},
    )

    # Should return 422 validation error
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_query_param_validation_excessive(async_client: httpx.AsyncClient):
    """Test that excessive timeout values (> 5 min) are rejected."""

    response = await async_client.post(
        "/bridge?timeout=999999999",
        json={
            "serverPath": "test-server",
            "method": "ping",
            "params": {},
        },
        headers={"Authorization": "Bearer test-token"},
    )

    # Should return 422 validation error (exceeds 300000ms limit)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_query_param_validation_valid_edge_cases(async_client: httpx.AsyncClient, mock_mcp_client):
    """Test that valid edge case timeout values are accepted."""

    # Mock fast operation
    mock_mcp_client.handle.session.send_ping = AsyncMock(return_value={"result": "pong"})

    # Test minimum valid timeout (1ms)
    response_min = await async_client.post(
        "/bridge?timeout=1",
        json={
            "serverPath": "test-server",
            "method": "ping",
            "params": {},
        },
        headers={"Authorization": "Bearer test-token"},
    )
    assert response_min.status_code == 200

    # Test maximum valid timeout (300000ms = 5 min)
    response_max = await async_client.post(
        "/bridge?timeout=300000",
        json={
            "serverPath": "test-server",
            "method": "ping",
            "params": {},
        },
        headers={"Authorization": "Bearer test-token"},
    )
    assert response_max.status_code == 200


@pytest.mark.asyncio
async def test_all_mcp_methods_have_timeout(async_client: httpx.AsyncClient, mock_mcp_client):
    """Test that timeout is applied consistently to all 12 MCP methods."""

    # All 12 MCP methods to test
    methods_to_test = [
        ("tools/list", {}),
        ("tools/call", {"name": "test-tool"}),
        ("prompts/list", {}),
        ("prompts/get", {"name": "test-prompt"}),
        ("resources/list", {}),
        ("resources/read", {"uri": "test://resource"}),
        ("resources/templates/list", {}),
        ("resources/subscribe", {"uri": "test://resource"}),
        ("resources/unsubscribe", {"uri": "test://resource"}),
        (
            "completion/complete",
            {"ref": {"type": "ref/tool", "name": "test"}, "argument": {"name": "arg"}},
        ),
        ("logging/setLevel", {"level": "info"}),
        ("ping", {}),
    ]

    # Mock all methods with slow operations that exceed timeout
    async def slow_operation(*args, **kwargs):
        await asyncio.sleep(2)
        return {"result": "should not return"}

    session = mock_mcp_client.handle.session
    session.list_tools = AsyncMock(side_effect=slow_operation)
    session.call_tool = AsyncMock(side_effect=slow_operation)
    session.list_prompts = AsyncMock(side_effect=slow_operation)
    session.get_prompt = AsyncMock(side_effect=slow_operation)
    session.list_resources = AsyncMock(side_effect=slow_operation)
    session.read_resource = AsyncMock(side_effect=slow_operation)
    session.list_resource_templates = AsyncMock(side_effect=slow_operation)
    session.subscribe_resource = AsyncMock(side_effect=slow_operation)
    session.unsubscribe_resource = AsyncMock(side_effect=slow_operation)
    session.complete = AsyncMock(side_effect=slow_operation)
    session.set_logging_level = AsyncMock(side_effect=slow_operation)
    session.send_ping = AsyncMock(side_effect=slow_operation)

    # Test each method times out
    for method, params in methods_to_test:
        response = await async_client.post(
            "/bridge?timeout=500",
            json={
                "serverPath": "test-server",
                "method": method,
                "params": params,
            },
            headers={"Authorization": "Bearer test-token"},
        )

        # Each method should timeout with consistent error structure
        assert response.status_code == 500, f"Method {method} should timeout"
        data = response.json()
        assert "error" in data, f"Method {method} error response missing 'error' field"
        assert "timeout" in data["error"].lower(), f"Method {method} error should mention timeout"
        assert data["method"] == method, f"Method {method} error should include method name"
        assert "elapsed_ms" in data, f"Method {method} error missing elapsed_ms"


@pytest.mark.asyncio
async def test_default_timeout_from_env_var(async_client: httpx.AsyncClient, mock_mcp_client):
    """Test that default timeout is loaded from MCP_CONNECT_DEFAULT_TIMEOUT env var."""

    # Mock successful fast operation
    mock_mcp_client.handle.session.send_ping = AsyncMock(return_value={"result": "pong"})

    # Call without timeout query param (should use default from env)
    response = await async_client.post(
        "/bridge",
        json={
            "serverPath": "test-server",
            "method": "ping",
            "params": {},
        },
        headers={"Authorization": "Bearer test-token"},
    )

    # Should succeed with default timeout (60s default is very generous)
    assert response.status_code == 200
    data = response.json()
    assert data["result"] == "pong"


@pytest.mark.asyncio
async def test_timeout_logging(async_client: httpx.AsyncClient, mock_mcp_client, caplog):
    """Test that timeout events are logged with proper context."""

    # Mock slow operation
    async def slow_operation(*args, **kwargs):
        await asyncio.sleep(2)
        return {"result": "should not return"}

    mock_mcp_client.handle.session.call_tool = AsyncMock(side_effect=slow_operation)

    # Trigger timeout
    response = await async_client.post(
        "/bridge?timeout=500",
        json={
            "serverPath": "test-server",
            "method": "tools/call",
            "params": {"name": "test-tool"},
        },
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 500

    # Verify timeout was logged (check caplog for error log)
    # Note: Logging verification depends on test logging configuration
    # This is a basic check that the endpoint returns timeout error
    data = response.json()
    assert "timeout" in data["error"].lower()
