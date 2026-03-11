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

"""Tests for POST /bridge request validation behavior."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from mcp.types import ListToolsResult, Tool

pytestmark = pytest.mark.asyncio


def _base_payload() -> dict[str, Any]:
    return {
        "serverPath": "./mock-server",
        "method": "ping",
        "params": {"data": "value"},
    }


async def test_missing_server_path_returns_422(
    async_client: httpx.AsyncClient,
) -> None:
    payload = _base_payload()
    payload.pop("serverPath")

    response = await async_client.post("/bridge", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == "serverPath"


async def test_missing_method_returns_422(
    async_client: httpx.AsyncClient,
) -> None:
    payload = _base_payload()
    payload.pop("method")

    response = await async_client.post("/bridge", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == "method"


async def test_missing_params_returns_422(
    async_client: httpx.AsyncClient,
) -> None:
    payload = _base_payload()
    payload.pop("params")

    response = await async_client.post("/bridge", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == "params"


async def test_invalid_type_for_server_path_returns_422(
    async_client: httpx.AsyncClient,
) -> None:
    payload = _base_payload()
    payload["serverPath"] = 123

    response = await async_client.post("/bridge", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"].endswith("string_type")


async def test_invalid_type_for_args_returns_422(
    async_client: httpx.AsyncClient,
) -> None:
    payload = _base_payload()
    payload["args"] = "not-a-list"

    response = await async_client.post("/bridge", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == "args"


async def test_unknown_field_returns_400(
    async_client: httpx.AsyncClient,
) -> None:
    payload = _base_payload()
    payload["unknownField"] = "value"

    response = await async_client.post("/bridge", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"][0]["type"] == "extra_forbidden"


async def test_valid_request_with_required_fields_returns_method_result(
    async_client: httpx.AsyncClient,
    mock_mcp_client: AsyncMock,
) -> None:
    response = await async_client.post("/bridge", json=_base_payload())

    assert response.status_code == 200
    assert response.json() == {"result": "pong"}


async def test_valid_request_with_all_optional_fields_returns_200(
    async_client: httpx.AsyncClient,
    mock_mcp_client: AsyncMock,
) -> None:
    payload = {
        "serverPath": "./mock-server",
        "method": "tools/call",
        "params": {"name": "echo", "arguments": {"text": "hi"}},
        "args": ["--flag"],
        "env": {"ENV": "value"},
        "mcp_headers": {"x-auth": "123"},
        "request_headers": {"accept": "application/json"},
        "http_transport_type": "streamable-http",
        "single_usage": True,
        "user_id": "user-123",
        "assistant_id": "assistant-456",
        "project_name": "codemie",
        "workflow_execution_id": "wf-789",
    }

    response = await async_client.post("/bridge", json=payload)

    assert response.status_code == 200
    assert response.json() == {"result": "tools/call"}


async def test_timeout_query_parameter_is_accepted(
    async_client: httpx.AsyncClient,
    mock_mcp_client: AsyncMock,
) -> None:
    response = await async_client.post("/bridge?timeout=60000", json=_base_payload())

    assert response.status_code == 200
    assert response.json() == {"result": "pong"}


async def test_null_fields_excluded_from_response(
    async_client: httpx.AsyncClient,
) -> None:
    """Verify that Pydantic model fields with null values are excluded from JSON response.

    This test ensures that when MCP SDK methods return Pydantic models with optional
    fields set to None (like meta, nextCursor, outputSchema, etc.), these null fields
    are not included in the HTTP response JSON. This matches TypeScript behavior and
    keeps responses clean.
    """
    # Create a real Pydantic model with null fields (as MCP SDK does)
    tool_with_nulls = Tool(
        name="test-tool",
        description="A test tool",
        inputSchema={"type": "object", "properties": {}},
    )

    # Create ListToolsResult with null meta and nextCursor
    result_with_nulls = ListToolsResult(
        tools=[tool_with_nulls],
        nextCursor=None,  # This should be excluded
    )

    # Mock the session to return the Pydantic model
    session = MagicMock()
    session.list_tools = AsyncMock(return_value=result_with_nulls)

    mock_handle = MagicMock()
    mock_handle.session = session
    mock_handle.cleanup = AsyncMock(return_value=None)

    with patch(
        "mcp_connect.server.routes.get_or_create_client",
        new_callable=AsyncMock,
    ) as mock_create:
        # get_or_create_client now returns tuple (handle, session)
        mock_create.return_value = (mock_handle, session)

        payload = {
            "serverPath": "./mock-server",
            "method": "tools/list",
            "params": {},
        }

        response = await async_client.post("/bridge", json=payload)

        assert response.status_code == 200
        response_json = response.json()

        # Verify null fields are NOT in the response
        assert "nextCursor" not in response_json
        assert "_meta" not in response_json

        # Verify the tools array is present
        assert "tools" in response_json
        assert len(response_json["tools"]) == 1

        # Verify tool has expected fields but not null ones
        tool = response_json["tools"][0]
        assert tool["name"] == "test-tool"
        assert tool["description"] == "A test tool"
        assert "inputSchema" in tool

        # Verify tool's null fields are also excluded
        assert "outputSchema" not in tool
        assert "icons" not in tool
        assert "annotations" not in tool


async def test_env_with_boolean_values_is_accepted_and_converted(
    async_client: httpx.AsyncClient,
    mock_mcp_client: AsyncMock,
) -> None:
    """Test that boolean values in env are auto-converted to strings."""
    payload = _base_payload()
    payload["env"] = {
        "DOCKER_CONTAINER": True,
        "PUPPETEER_SKIP_CHROMIUM_DOWNLOAD": True,
        "DEBUG_MODE": False,
    }

    response = await async_client.post("/bridge", json=payload)

    assert response.status_code == 200
    assert response.json() == {"result": "pong"}


async def test_env_with_number_values_is_accepted_and_converted(
    async_client: httpx.AsyncClient,
    mock_mcp_client: AsyncMock,
) -> None:
    """Test that numeric values in env are auto-converted to strings."""
    payload = _base_payload()
    payload["env"] = {
        "PORT": 3000,
        "TIMEOUT": 60.5,
        "MAX_RETRIES": 5,
    }

    response = await async_client.post("/bridge", json=payload)

    assert response.status_code == 200
    assert response.json() == {"result": "pong"}


async def test_env_with_null_values_is_accepted_and_converted(
    async_client: httpx.AsyncClient,
    mock_mcp_client: AsyncMock,
) -> None:
    """Test that null values in env are auto-converted to empty strings."""
    payload = _base_payload()
    payload["env"] = {
        "OPTIONAL_VAR": None,
        "ANOTHER_VAR": None,
    }

    response = await async_client.post("/bridge", json=payload)

    assert response.status_code == 200
    assert response.json() == {"result": "pong"}


async def test_env_with_mixed_types_is_accepted_and_converted(
    async_client: httpx.AsyncClient,
    mock_mcp_client: AsyncMock,
) -> None:
    """Test that mixed types in env (strings, booleans, numbers, null) all work together."""
    payload = _base_payload()
    payload["env"] = {
        "STRING_VAR": "value",
        "BOOL_VAR": True,
        "INT_VAR": 123,
        "FLOAT_VAR": 45.67,
        "NULL_VAR": None,
        "FALSE_VAR": False,
    }

    response = await async_client.post("/bridge", json=payload)

    assert response.status_code == 200
    assert response.json() == {"result": "pong"}
