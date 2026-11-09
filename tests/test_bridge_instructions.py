"""The /bridge tools/list response carries server instructions."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from mcp_connect.main import app


@pytest.fixture
async def async_client() -> Any:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


def _session_returning(tools_payload: Any) -> MagicMock:
    session = MagicMock()
    session.list_tools = AsyncMock(return_value=tools_payload)
    return session


async def test_tools_list_includes_instructions_from_the_cached_client(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    handle = MagicMock()
    handle.instructions = "Call with sysparm_help=true first."
    session = _session_returning({"tools": []})
    monkeypatch.setattr(
        "mcp_connect.server.routes.get_or_create_client",
        AsyncMock(return_value=(handle, session)),
    )

    response = await async_client.post(
        "/bridge",
        json={"serverPath": "https://example.test/mcp", "method": "tools/list", "params": {}},
    )

    assert response.status_code == 200
    assert response.json() == {"tools": [], "instructions": "Call with sysparm_help=true first."}


async def test_tools_list_omits_instructions_when_the_server_sends_none(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    handle = MagicMock()
    handle.instructions = None
    session = _session_returning({"tools": []})
    monkeypatch.setattr(
        "mcp_connect.server.routes.get_or_create_client",
        AsyncMock(return_value=(handle, session)),
    )

    response = await async_client.post(
        "/bridge",
        json={"serverPath": "https://example.test/mcp", "method": "tools/list", "params": {}},
    )

    assert response.json() == {"tools": []}


async def test_other_methods_never_receive_instructions(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    handle = MagicMock()
    handle.instructions = "Call with sysparm_help=true first."
    session = MagicMock()
    session.send_ping = AsyncMock(return_value={"result": "ping"})
    monkeypatch.setattr(
        "mcp_connect.server.routes.get_or_create_client",
        AsyncMock(return_value=(handle, session)),
    )

    response = await async_client.post(
        "/bridge",
        json={"serverPath": "https://example.test/mcp", "method": "ping", "params": {}},
    )

    assert response.json() == {"result": "ping"}


async def test_instructions_ride_every_page_of_a_paginated_listing(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    handle = MagicMock()
    handle.instructions = "Call with sysparm_help=true first."
    session = _session_returning({"tools": [], "nextCursor": "page-3"})
    monkeypatch.setattr(
        "mcp_connect.server.routes.get_or_create_client",
        AsyncMock(return_value=(handle, session)),
    )

    response = await async_client.post(
        "/bridge",
        json={
            "serverPath": "https://example.test/mcp",
            "method": "tools/list",
            "params": {"cursor": "page-2"},
        },
    )

    body = response.json()
    assert body["instructions"] == "Call with sysparm_help=true first."
    assert body["nextCursor"] == "page-3"


async def test_tools_list_with_a_real_sdk_result_survives_serialization(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Production returns ListToolsResult, not a dict — cover that branch end to end.

    Every other bridge test stubs a plain dict, which exercises a helper branch
    that never runs in production and skips the route's model_dump(exclude_none)
    that the backward-compatibility argument rests on.
    """
    from mcp.types import ListToolsResult

    handle = MagicMock()
    handle.instructions = "Call with sysparm_help=true first."
    session = _session_returning(ListToolsResult(tools=[]))
    monkeypatch.setattr(
        "mcp_connect.server.routes.get_or_create_client",
        AsyncMock(return_value=(handle, session)),
    )

    response = await async_client.post(
        "/bridge",
        json={"serverPath": "https://example.test/mcp", "method": "tools/list", "params": {}},
    )

    assert response.status_code == 200
    assert response.json() == {"tools": [], "instructions": "Call with sysparm_help=true first."}


async def test_real_sdk_result_without_instructions_is_byte_identical(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcp.types import ListToolsResult

    handle = MagicMock()
    handle.instructions = None
    session = _session_returning(ListToolsResult(tools=[]))
    monkeypatch.setattr(
        "mcp_connect.server.routes.get_or_create_client",
        AsyncMock(return_value=(handle, session)),
    )

    response = await async_client.post(
        "/bridge",
        json={"serverPath": "https://example.test/mcp", "method": "tools/list", "params": {}},
    )

    assert response.json() == {"tools": []}
