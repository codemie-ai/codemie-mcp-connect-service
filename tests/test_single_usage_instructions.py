"""Single-usage requests expose server instructions too."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from mcp_connect.client.single_usage import execute_single_usage_request
from mcp_connect.models.request import BridgeRequestBody


class _InitResult:
    def __init__(self, instructions: str | None) -> None:
        self.instructions = instructions


class _DummySession:
    def __init__(self, read: Any, write: Any, client_info: Any = None) -> None:
        self.initialize = AsyncMock(return_value=_InitResult("read me first"))
        self.list_tools = AsyncMock(return_value={"tools": []})
        self.send_ping = AsyncMock(return_value={"result": "ping"})

    async def __aenter__(self) -> _DummySession:
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None


class _DummyTransport:
    async def __aenter__(self) -> tuple[str, str]:
        return ("read", "write")

    async def __aexit__(self, *_: Any) -> None:
        return None


@pytest.fixture(autouse=True)
def _fake_http_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("mcp_connect.client.single_usage.ClientSession", _DummySession)
    monkeypatch.setattr("mcp_connect.client.transports.get_transport_ctx", lambda *_a, **_k: _DummyTransport())
    monkeypatch.setattr("mcp_connect.client.single_usage.stdio_client", lambda *_a, **_k: _DummyTransport())
    monkeypatch.setattr("mcp_connect.client.single_usage.sse_client", lambda *_a, **_k: _DummyTransport())


@pytest.mark.parametrize(
    ("server_path", "http_transport_type"),
    [
        ("some-command", None),
        ("https://example.test/mcp", "streamable-http"),
        ("https://example.test/sse", "sse"),
    ],
    ids=["stdio", "streamable-http", "sse"],
)
async def test_single_usage_tools_list_carries_instructions(server_path: str, http_transport_type: str | None) -> None:
    """All three single-usage transport bodies must capture and attach."""
    request = BridgeRequestBody(
        serverPath=server_path,
        method="tools/list",
        params={},
        single_usage=True,
        http_transport_type=http_transport_type,
    )

    result = await execute_single_usage_request(request, "tools/list", {}, 5000)

    assert result == {"tools": [], "instructions": "read me first"}


async def test_single_usage_ping_is_untouched() -> None:
    request = BridgeRequestBody(serverPath="https://example.test/mcp", method="ping", params={}, single_usage=True)

    result = await execute_single_usage_request(request, "ping", {}, 5000)

    assert result == {"result": "ping"}
