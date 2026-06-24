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

"""Tests for MCP_CLIENT_NAME environment variable support."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from mcp.types import Implementation

# ---------------------------------------------------------------------------
# Helpers shared across test classes
# ---------------------------------------------------------------------------


class FakeTransportContext:
    """Minimal async context manager simulating a transport (read, write) pair."""

    def __init__(self, streams: tuple[Any, ...]) -> None:
        self.streams = streams
        self.exited = False

    async def __aenter__(self) -> tuple[Any, ...]:
        return self.streams

    async def __aexit__(self, *_: Any) -> None:
        self.exited = True


def make_capturing_session_class(capture_list: list[Implementation | None]) -> type:
    """Return a DummySession subclass that records the client_info argument."""

    class CapturingSession:
        def __init__(self, read: Any, write: Any, **kwargs: Any) -> None:
            capture_list.append(kwargs.get("client_info"))
            self._inner = AsyncMock()
            self._inner.initialize = AsyncMock()
            self._inner.list_tools = AsyncMock(return_value={"tools": []})
            self._inner.call_tool = AsyncMock(return_value={"content": []})

        async def __aenter__(self) -> Any:
            return self._inner

        async def __aexit__(self, *_: Any) -> None:
            pass

    return CapturingSession


# ---------------------------------------------------------------------------
# Tests for get_client_info()
# ---------------------------------------------------------------------------


class TestGetClientInfo:
    """Test that get_client_info() reads MCP_CLIENT_NAME from the environment."""

    def test_default_name_is_mcp_bridge(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When MCP_CLIENT_NAME is not set, the default name is 'mcp-bridge'."""
        monkeypatch.delenv("MCP_CLIENT_NAME", raising=False)
        from src.mcp_connect.client.client_info import get_client_info

        info = get_client_info()
        assert info.name == "mcp-bridge"

    def test_custom_name_from_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When MCP_CLIENT_NAME is set, that name is returned."""
        monkeypatch.setenv("MCP_CLIENT_NAME", "my-custom-client")
        from src.mcp_connect.client.client_info import get_client_info

        info = get_client_info()
        assert info.name == "my-custom-client"

    def test_returns_implementation_type(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """get_client_info() returns an mcp.types.Implementation instance."""
        monkeypatch.delenv("MCP_CLIENT_NAME", raising=False)
        from src.mcp_connect.client.client_info import get_client_info

        info = get_client_info()
        assert isinstance(info, Implementation)

    def test_different_values_each_call_with_env_change(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """get_client_info() reads the env var fresh on each call."""
        monkeypatch.setenv("MCP_CLIENT_NAME", "first-name")
        from src.mcp_connect.client.client_info import get_client_info

        assert get_client_info().name == "first-name"

        monkeypatch.setenv("MCP_CLIENT_NAME", "second-name")
        assert get_client_info().name == "second-name"


# ---------------------------------------------------------------------------
# Tests for single_usage.py – client_info is passed to ClientSession
# ---------------------------------------------------------------------------


class TestSingleUsageClientName:
    """Test that single-usage transport functions forward client_info to ClientSession."""

    @pytest.mark.asyncio
    async def test_stdio_passes_default_client_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ClientSession receives client_info with default name 'mcp-bridge' for stdio."""
        monkeypatch.delenv("MCP_CLIENT_NAME", raising=False)

        captured: list[Implementation | None] = []
        CapturingSession = make_capturing_session_class(captured)

        fake_ctx = FakeTransportContext(("r", "w"))
        monkeypatch.setattr("src.mcp_connect.client.single_usage.stdio_client", lambda *a, **kw: fake_ctx)
        monkeypatch.setattr("src.mcp_connect.client.single_usage.ClientSession", CapturingSession)

        from src.mcp_connect.client.single_usage import execute_single_usage_request
        from src.mcp_connect.models.request import BridgeRequestBody

        request = BridgeRequestBody(serverPath="echo", method="tools/list", params={})
        await execute_single_usage_request(request, "tools/list", {}, 5000)

        assert len(captured) == 1
        assert captured[0] is not None
        assert captured[0].name == "mcp-bridge"

    @pytest.mark.asyncio
    async def test_stdio_passes_env_client_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ClientSession receives client_info with name from MCP_CLIENT_NAME for stdio."""
        monkeypatch.setenv("MCP_CLIENT_NAME", "codemie-client")

        captured: list[Implementation | None] = []
        CapturingSession = make_capturing_session_class(captured)

        fake_ctx = FakeTransportContext(("r", "w"))
        monkeypatch.setattr("src.mcp_connect.client.single_usage.stdio_client", lambda *a, **kw: fake_ctx)
        monkeypatch.setattr("src.mcp_connect.client.single_usage.ClientSession", CapturingSession)

        from src.mcp_connect.client.single_usage import execute_single_usage_request
        from src.mcp_connect.models.request import BridgeRequestBody

        request = BridgeRequestBody(serverPath="echo", method="tools/list", params={})
        await execute_single_usage_request(request, "tools/list", {}, 5000)

        assert len(captured) == 1
        assert captured[0] is not None
        assert captured[0].name == "codemie-client"

    @pytest.mark.asyncio
    async def test_http_passes_env_client_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ClientSession receives client_info with name from MCP_CLIENT_NAME for HTTP."""
        monkeypatch.setenv("MCP_CLIENT_NAME", "http-codemie")

        captured: list[Implementation | None] = []
        CapturingSession = make_capturing_session_class(captured)

        fake_ctx = FakeTransportContext(("r", "w", None))
        monkeypatch.setattr("src.mcp_connect.client.single_usage.get_transport_ctx", lambda *a, **kw: fake_ctx)
        monkeypatch.setattr("src.mcp_connect.client.single_usage.ClientSession", CapturingSession)

        from src.mcp_connect.client.single_usage import execute_single_usage_request
        from src.mcp_connect.models.request import BridgeRequestBody

        request = BridgeRequestBody(serverPath="https://example.com/mcp", method="tools/list", params={})
        await execute_single_usage_request(request, "tools/list", {}, 5000)

        assert len(captured) == 1
        assert captured[0] is not None
        assert captured[0].name == "http-codemie"

    @pytest.mark.asyncio
    async def test_sse_passes_env_client_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ClientSession receives client_info with name from MCP_CLIENT_NAME for SSE."""
        monkeypatch.setenv("MCP_CLIENT_NAME", "sse-codemie")

        captured: list[Implementation | None] = []
        CapturingSession = make_capturing_session_class(captured)

        fake_ctx = FakeTransportContext(("r", "w"))
        monkeypatch.setattr("src.mcp_connect.client.single_usage.sse_client", lambda *a, **kw: fake_ctx)
        monkeypatch.setattr("src.mcp_connect.client.single_usage.ClientSession", CapturingSession)

        from src.mcp_connect.client.single_usage import execute_single_usage_request
        from src.mcp_connect.models.request import BridgeRequestBody

        request = BridgeRequestBody(
            serverPath="https://sse.example.com/mcp",
            method="tools/list",
            params={},
            http_transport_type="sse",
        )
        await execute_single_usage_request(request, "tools/list", {}, 5000)

        assert len(captured) == 1
        assert captured[0] is not None
        assert captured[0].name == "sse-codemie"


# ---------------------------------------------------------------------------
# Tests for managed.py – client_info is passed to ClientSession
# ---------------------------------------------------------------------------


class TestManagedClientName:
    """Test that ManagedClient transport methods forward client_info to ClientSession."""

    @pytest.mark.asyncio
    async def test_stdio_passes_client_info_to_session(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ManagedClient._run_stdio_client passes client_info with env name to ClientSession."""
        monkeypatch.setenv("MCP_CLIENT_NAME", "managed-stdio-client")

        captured: list[Implementation | None] = []
        CapturingSession = make_capturing_session_class(captured)

        cleanup_event = asyncio.Event()
        ready_future: asyncio.Future[Any] = asyncio.Future()

        fake_stdio_ctx = FakeTransportContext(("r", "w"))

        monkeypatch.setattr("src.mcp_connect.client.managed.ClientSession", CapturingSession)

        from src.mcp_connect.client.managed import ManagedClient
        from src.mcp_connect.models.request import BridgeRequestBody

        request = BridgeRequestBody(serverPath="echo", method="tools/list", params={})

        with patch("mcp.client.stdio.stdio_client", return_value=fake_stdio_ctx):
            task = asyncio.create_task(ManagedClient._run_stdio_client(request, cleanup_event, ready_future))

            # Wait for session to become ready (initialization complete)
            await asyncio.wait_for(asyncio.shield(ready_future), timeout=5.0)

            # Signal cleanup and wait for task to finish
            cleanup_event.set()
            await asyncio.wait_for(task, timeout=5.0)

        assert len(captured) == 1
        assert captured[0] is not None
        assert captured[0].name == "managed-stdio-client"

    @pytest.mark.asyncio
    async def test_http_passes_client_info_to_session(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ManagedClient._run_streamable_http_client passes client_info with env name to ClientSession."""
        monkeypatch.setenv("MCP_CLIENT_NAME", "managed-http-client")

        captured: list[Implementation | None] = []
        CapturingSession = make_capturing_session_class(captured)

        cleanup_event = asyncio.Event()
        ready_future: asyncio.Future[Any] = asyncio.Future()

        fake_http_ctx = FakeTransportContext(("r", "w", None))

        monkeypatch.setattr("src.mcp_connect.client.managed.ClientSession", CapturingSession)

        from src.mcp_connect.client.managed import ManagedClient
        from src.mcp_connect.models.request import BridgeRequestBody

        request = BridgeRequestBody(serverPath="https://example.com/mcp", method="tools/list", params={})

        with patch("src.mcp_connect.client.transports.get_transport_ctx", return_value=fake_http_ctx):
            task = asyncio.create_task(ManagedClient._run_streamable_http_client(request, cleanup_event, ready_future))

            await asyncio.wait_for(asyncio.shield(ready_future), timeout=5.0)

            cleanup_event.set()
            await asyncio.wait_for(task, timeout=5.0)

        assert len(captured) == 1
        assert captured[0] is not None
        assert captured[0].name == "managed-http-client"
