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

"""Unit tests for the MCP method router."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from mcp.shared.exceptions import McpError
from mcp.types import INVALID_PARAMS, CallToolResult, ErrorData, PaginatedRequestParams

from src.mcp_connect.client.methods import invoke_mcp_method


@pytest.fixture
def session():
    """Provide a fake MCP session with AsyncMock methods."""

    class FakeSession:
        pass

    fake_session = FakeSession()

    def _set_mock(name: str) -> None:
        setattr(fake_session, name, AsyncMock(return_value={"called": name}))

    for method_name in (
        "list_tools",
        "call_tool",
        "list_prompts",
        "get_prompt",
        "list_resources",
        "read_resource",
        "list_resource_templates",
        "subscribe_resource",
        "unsubscribe_resource",
        "complete",
        "set_logging_level",
        "send_ping",
    ):
        _set_mock(method_name)

    return fake_session


@pytest.mark.asyncio
async def test_tools_list_without_cursor(session) -> None:
    result = await invoke_mcp_method(session, "tools/list", None)

    assert result == {"called": "list_tools"}
    session.list_tools.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_tools_list_with_cursor(session) -> None:
    session.list_tools.return_value = {"cursor": "next"}

    result = await invoke_mcp_method(session, "tools/list", {"cursor": "abc"})

    assert result == {"cursor": "next"}
    session.list_tools.assert_awaited_once()
    _args, kwargs = session.list_tools.await_args
    assert isinstance(kwargs["params"], PaginatedRequestParams)
    assert kwargs["params"].cursor == "abc"


@pytest.mark.asyncio
async def test_tools_call_requires_name(session) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await invoke_mcp_method(session, "tools/call", {})

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == {"error": "Missing required parameter: name"}


@pytest.mark.asyncio
async def test_tools_call_with_arguments(session) -> None:
    await invoke_mcp_method(session, "tools/call", {"name": "echo", "arguments": {"text": "hi"}})

    session.call_tool.assert_awaited_once_with("echo", {"text": "hi"})


@pytest.mark.asyncio
async def test_tools_call_strips_null_arguments(session) -> None:
    """Null optional fields must be omitted — MCP servers with strict Zod schemas reject explicit nulls."""
    await invoke_mcp_method(
        session,
        "tools/call",
        {"name": "query_prometheus", "arguments": {"query": "up", "endTime": None, "stepSeconds": None}},
    )

    session.call_tool.assert_awaited_once_with("query_prometheus", {"query": "up"})


@pytest.mark.asyncio
async def test_tools_call_strips_null_arguments_nested(session) -> None:
    await invoke_mcp_method(
        session,
        "tools/call",
        {"name": "my_tool", "arguments": {"filter": {"active": True, "namespace": None}, "limit": None}},
    )

    session.call_tool.assert_awaited_once_with("my_tool", {"filter": {"active": True}})


@pytest.mark.asyncio
async def test_tools_call_preserves_falsy_non_none_values(session) -> None:
    await invoke_mcp_method(
        session,
        "tools/call",
        {"name": "my_tool", "arguments": {"count": 0, "label": "", "active": False}},
    )

    session.call_tool.assert_awaited_once_with("my_tool", {"count": 0, "label": "", "active": False})


@pytest.mark.asyncio
async def test_tools_call_mcp_error_returns_iserror_result(session) -> None:
    """EPMCDME-11351: a downstream MCP protocol error must surface as an isError tool
    result (not propagate to a generic HTTP 500)."""
    session.call_tool.side_effect = McpError(
        ErrorData(code=INVALID_PARAMS, message="Invalid params: unexpected key 'sql1'")
    )

    result = await invoke_mcp_method(session, "tools/call", {"name": "query", "arguments": {"sql": "SELECT 1"}})

    assert isinstance(result, CallToolResult)
    assert result.isError is True
    assert len(result.content) == 1
    text = result.content[0].text
    assert "query" in text
    assert "Invalid params: unexpected key 'sql1'" in text
    assert str(INVALID_PARAMS) in text


@pytest.mark.asyncio
async def test_tools_call_non_mcp_error_propagates(session) -> None:
    """EPMCDME-11351: only McpError is converted — other failures (timeout, connection,
    transport/auth) must propagate so the route maps them to 503/504/4xx/500."""
    session.call_tool.side_effect = ConnectionError("connection refused")

    with pytest.raises(ConnectionError):
        await invoke_mcp_method(session, "tools/call", {"name": "query", "arguments": {"sql": "SELECT 1"}})


@pytest.mark.asyncio
async def test_prompts_list_without_cursor(session) -> None:
    result = await invoke_mcp_method(session, "prompts/list", None)

    assert result == {"called": "list_prompts"}
    session.list_prompts.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_prompts_list_with_cursor(session) -> None:
    session.list_prompts.return_value = {"prompts": [], "cursor": "next"}

    result = await invoke_mcp_method(session, "prompts/list", {"cursor": "xyz"})

    assert result == {"prompts": [], "cursor": "next"}
    session.list_prompts.assert_awaited_once()
    _args, kwargs = session.list_prompts.await_args
    assert isinstance(kwargs["params"], PaginatedRequestParams)
    assert kwargs["params"].cursor == "xyz"


@pytest.mark.asyncio
async def test_prompts_get_validates_required_params(session) -> None:
    await invoke_mcp_method(
        session,
        "prompts/get",
        {"name": "main", "arguments": {"topic": "news"}},
    )

    session.get_prompt.assert_awaited_once_with("main", {"topic": "news"})


@pytest.mark.asyncio
async def test_resources_list_without_cursor(session) -> None:
    result = await invoke_mcp_method(session, "resources/list", None)

    assert result == {"called": "list_resources"}
    session.list_resources.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_resources_list_with_cursor(session) -> None:
    session.list_resources.return_value = {"resources": [], "cursor": "token123"}

    result = await invoke_mcp_method(session, "resources/list", {"cursor": "token123"})

    assert result == {"resources": [], "cursor": "token123"}
    session.list_resources.assert_awaited_once()
    _args, kwargs = session.list_resources.await_args
    assert isinstance(kwargs["params"], PaginatedRequestParams)
    assert kwargs["params"].cursor == "token123"


@pytest.mark.asyncio
async def test_resources_read_requires_uri(session) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await invoke_mcp_method(session, "resources/read", {})

    assert exc_info.value.detail == {"error": "Missing required parameter: uri"}


@pytest.mark.asyncio
async def test_resources_read_calls_sdk(session) -> None:
    await invoke_mcp_method(session, "resources/read", {"uri": "file://readme"})

    session.read_resource.assert_awaited_once_with("file://readme")


@pytest.mark.asyncio
async def test_resources_templates_list_with_cursor(session) -> None:
    await invoke_mcp_method(
        session,
        "resources/templates/list",
        {"cursor": "token"},
    )

    session.list_resource_templates.assert_awaited_once()
    _args, kwargs = session.list_resource_templates.await_args
    assert isinstance(kwargs["params"], PaginatedRequestParams)


@pytest.mark.asyncio
async def test_resources_subscribe(session) -> None:
    await invoke_mcp_method(session, "resources/subscribe", {"uri": "file://logs"})

    session.subscribe_resource.assert_awaited_once_with("file://logs")


@pytest.mark.asyncio
async def test_resources_unsubscribe(session) -> None:
    await invoke_mcp_method(session, "resources/unsubscribe", {"uri": "file://logs"})

    session.unsubscribe_resource.assert_awaited_once_with("file://logs")


@pytest.mark.asyncio
async def test_completion_complete_includes_context(session) -> None:
    params = {
        "ref": {"type": "ref/resource", "uri": "example"},
        "argument": {"name": "owner", "value": "codemie"},
        "context": {"owner": "codemie"},
    }

    await invoke_mcp_method(session, "completion/complete", params)

    session.complete.assert_awaited_once_with(
        params["ref"],
        params["argument"],
        context_arguments=params["context"],
    )


@pytest.mark.asyncio
async def test_logging_set_level_requires_level(session) -> None:
    await invoke_mcp_method(session, "logging/setLevel", {"level": "debug"})

    session.set_logging_level.assert_awaited_once_with("debug")


@pytest.mark.asyncio
async def test_ping_invokes_send_ping(session) -> None:
    response = await invoke_mcp_method(session, "ping", None)

    assert response == {"called": "send_ping"}
    session.send_ping.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_unsupported_method_raises_http_exception(session) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await invoke_mcp_method(session, "unknown/method", {})

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == {"error": "Unsupported method: unknown/method"}


@pytest.mark.asyncio
async def test_non_mapping_params_raise_error(session) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await invoke_mcp_method(session, "tools/call", ["invalid"])

    assert "Invalid params" in exc_info.value.detail["error"]
