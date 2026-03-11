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

"""Shared pytest fixtures for MCP Connect tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio

from mcp_connect.main import app


@pytest_asyncio.fixture
async def async_client() -> httpx.AsyncClient:
    """HTTPX client backed by the FastAPI application."""

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        yield client


@pytest.fixture
def mock_mcp_client():
    """Mock MCP client creation to avoid spawning real subprocesses in tests."""

    session = MagicMock()
    session.list_tools = AsyncMock(return_value={"result": "tools/list"})
    session.call_tool = AsyncMock(return_value={"result": "tools/call"})
    session.list_prompts = AsyncMock(return_value={"result": "prompts/list"})
    session.get_prompt = AsyncMock(return_value={"result": "prompts/get"})
    session.list_resources = AsyncMock(return_value={"result": "resources/list"})
    session.read_resource = AsyncMock(return_value={"result": "resources/read"})
    session.list_resource_templates = AsyncMock(return_value={"result": "resources/templates/list"})
    session.subscribe_resource = AsyncMock(return_value={"result": "resources/subscribe"})
    session.unsubscribe_resource = AsyncMock(return_value={"result": "resources/unsubscribe"})
    session.complete = AsyncMock(return_value={"result": "completion/complete"})
    session.set_logging_level = AsyncMock(return_value={"result": "logging/setLevel"})
    session.send_ping = AsyncMock(return_value={"result": "pong"})

    mock_handle = MagicMock()
    mock_handle.session = session
    mock_handle.cleanup = AsyncMock(return_value=None)

    # Mock both cached and single-usage paths
    with (
        patch(
            "mcp_connect.server.routes.get_or_create_client",
            new_callable=AsyncMock,
        ) as mock_create,
        patch(
            "mcp_connect.server.routes.execute_single_usage_request",
            new_callable=AsyncMock,
        ) as mock_single_usage,
    ):
        # get_or_create_client now returns tuple (handle, session)
        mock_create.return_value = (mock_handle, session)
        mock_create.session = session
        mock_create.handle = mock_handle

        # execute_single_usage_request returns the result directly
        # Use side_effect to return different results based on method
        def single_usage_side_effect(request, method, params, timeout_ms):
            if method == "tools/call":
                return {"result": "tools/call"}
            elif method == "tools/list":
                return {"result": "tools/list"}
            elif method == "prompts/list":
                return {"result": "prompts/list"}
            elif method == "prompts/get":
                return {"result": "prompts/get"}
            elif method == "resources/list":
                return {"result": "resources/list"}
            elif method == "resources/read":
                return {"result": "resources/read"}
            elif method == "resources/templates/list":
                return {"result": "resources/templates/list"}
            elif method == "resources/subscribe":
                return {"result": "resources/subscribe"}
            elif method == "resources/unsubscribe":
                return {"result": "resources/unsubscribe"}
            elif method == "completion/complete":
                return {"result": "completion/complete"}
            elif method == "logging/setLevel":
                return {"result": "logging/setLevel"}
            elif method == "ping":
                return {"result": "pong"}
            else:
                return {"result": method}

        mock_single_usage.side_effect = single_usage_side_effect

        yield mock_create
