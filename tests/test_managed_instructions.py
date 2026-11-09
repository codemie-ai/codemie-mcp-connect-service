"""The managed client keeps what the handshake disclosed."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from mcp_connect.client.instructions import MAX_INSTRUCTIONS_CHARS, TRUNCATION_MARKER
from mcp_connect.client.managed import ManagedClient
from mcp_connect.models.request import BridgeRequestBody


class _InitResult:
    def __init__(self, instructions: str | None) -> None:
        self.instructions = instructions


class _DummySession:
    """Minimal stand-in for ClientSession over a fake transport."""

    def __init__(self, read: Any, write: Any, client_info: Any = None) -> None:
        self.initialize = AsyncMock(return_value=_InitResult("read me first"))

    async def __aenter__(self) -> _DummySession:
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None


class _DummyTransport:
    async def __aenter__(self) -> tuple[str, str]:
        return ("read", "write")

    async def __aexit__(self, *_: Any) -> None:
        return None


@pytest.fixture
def http_request() -> BridgeRequestBody:
    return BridgeRequestBody(serverPath="https://example.test/mcp", method="tools/list", params={})


@pytest.mark.parametrize(
    "transport",
    ["_run_stdio_client", "_run_streamable_http_client", "_run_sse_client"],
)
async def test_every_transport_carries_the_handshake(
    monkeypatch: pytest.MonkeyPatch, http_request: BridgeRequestBody, transport: str
) -> None:
    """All three transport bodies must capture the handshake, not just one.

    A body that reverts to ready_future.set_result(session) does not fail loudly:
    it hangs spawn for its 30-second timeout. Only per-transport coverage catches that.
    """
    monkeypatch.setattr("mcp_connect.client.managed.ClientSession", _DummySession)
    monkeypatch.setattr("mcp_connect.client.transports.get_transport_ctx", lambda *_a, **_k: _DummyTransport())
    monkeypatch.setattr("mcp.client.stdio.stdio_client", lambda *_a, **_k: _DummyTransport())
    monkeypatch.setattr("mcp_connect.client.managed.sse_client", lambda *_a, **_k: _DummyTransport())

    cleanup_event = asyncio.Event()
    ready_future: asyncio.Future[Any] = asyncio.Future()

    task = asyncio.create_task(getattr(ManagedClient, transport)(http_request, cleanup_event, ready_future))
    handshake = await asyncio.wait_for(asyncio.shield(ready_future), 5.0)

    assert handshake.instructions == "read me first"
    assert isinstance(handshake.session, _DummySession)

    cleanup_event.set()
    await asyncio.wait_for(task, 5.0)


async def test_spawn_stores_instructions_on_the_client(
    monkeypatch: pytest.MonkeyPatch, http_request: BridgeRequestBody
) -> None:
    monkeypatch.setattr("mcp_connect.client.managed.ClientSession", _DummySession)
    monkeypatch.setattr("mcp_connect.client.transports.get_transport_ctx", lambda *_a, **_k: _DummyTransport())

    client = await ManagedClient.spawn(http_request)

    assert client.instructions == "read me first"
    assert isinstance(client.session, _DummySession)

    await client.cleanup()


async def test_spawn_caps_oversized_instructions_at_capture(
    monkeypatch: pytest.MonkeyPatch, http_request: BridgeRequestBody
) -> None:
    class _VerboseSession(_DummySession):
        def __init__(self, read: Any, write: Any, client_info: Any = None) -> None:
            self.initialize = AsyncMock(return_value=_InitResult("x" * 20000))

    monkeypatch.setattr("mcp_connect.client.managed.ClientSession", _VerboseSession)
    monkeypatch.setattr("mcp_connect.client.transports.get_transport_ctx", lambda *_a, **_k: _DummyTransport())

    client = await ManagedClient.spawn(http_request)

    assert client.instructions is not None
    assert len(client.instructions) <= MAX_INSTRUCTIONS_CHARS
    assert client.instructions.endswith(TRUNCATION_MARKER)

    await client.cleanup()


async def test_instructions_are_none_when_the_server_sends_none(
    monkeypatch: pytest.MonkeyPatch, http_request: BridgeRequestBody
) -> None:
    class _SilentSession(_DummySession):
        def __init__(self, read: Any, write: Any, client_info: Any = None) -> None:
            self.initialize = AsyncMock(return_value=_InitResult(None))

    monkeypatch.setattr("mcp_connect.client.managed.ClientSession", _SilentSession)
    monkeypatch.setattr("mcp_connect.client.transports.get_transport_ctx", lambda *_a, **_k: _DummyTransport())

    client = await ManagedClient.spawn(http_request)

    assert client.instructions is None

    await client.cleanup()
