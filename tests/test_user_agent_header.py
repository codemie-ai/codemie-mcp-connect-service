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

"""Tests for injecting MCP_CLIENT_NAME into the User-Agent HTTP header."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest


class TestApplyUserAgentHeader:
    """Test apply_user_agent_header() merge/override semantics."""

    def test_default_env_value_when_no_existing_headers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With no MCP_CLIENT_NAME set and no existing headers, User-Agent defaults to 'mcp-bridge'."""
        monkeypatch.delenv("MCP_CLIENT_NAME", raising=False)
        from src.mcp_connect.client.client_info import apply_user_agent_header

        result = apply_user_agent_header(None)

        assert result == {"User-Agent": "mcp-bridge"}

    def test_custom_env_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With MCP_CLIENT_NAME set, User-Agent uses that value."""
        monkeypatch.setenv("MCP_CLIENT_NAME", "codemie-client")
        from src.mcp_connect.client.client_info import apply_user_agent_header

        result = apply_user_agent_header({})

        assert result == {"User-Agent": "codemie-client"}

    def test_overrides_existing_user_agent_exact_case(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A caller-supplied 'User-Agent' value is replaced, not preserved."""
        monkeypatch.setenv("MCP_CLIENT_NAME", "codemie-client")
        from src.mcp_connect.client.client_info import apply_user_agent_header

        result = apply_user_agent_header({"User-Agent": "some-caller-value"})

        assert result == {"User-Agent": "codemie-client"}

    def test_overrides_existing_user_agent_lowercase_no_duplicate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A caller-supplied 'user-agent' (any case) is replaced by the canonical key, no duplicate."""
        monkeypatch.setenv("MCP_CLIENT_NAME", "codemie-client")
        from src.mcp_connect.client.client_info import apply_user_agent_header

        result = apply_user_agent_header({"user-agent": "some-caller-value"})

        assert result == {"User-Agent": "codemie-client"}
        assert len(result) == 1

    def test_preserves_unrelated_headers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Unrelated headers pass through unchanged alongside the injected User-Agent."""
        monkeypatch.setenv("MCP_CLIENT_NAME", "codemie-client")
        from src.mcp_connect.client.client_info import apply_user_agent_header

        result = apply_user_agent_header({"Authorization": "Bearer token123", "X-Custom": "value"})

        assert result == {
            "Authorization": "Bearer token123",
            "X-Custom": "value",
            "User-Agent": "codemie-client",
        }

    def test_does_not_mutate_input_dict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """apply_user_agent_header() returns a new dict; the caller's dict is untouched."""
        monkeypatch.setenv("MCP_CLIENT_NAME", "codemie-client")
        from src.mcp_connect.client.client_info import apply_user_agent_header

        original = {"X-Custom": "value"}
        apply_user_agent_header(original)

        assert original == {"X-Custom": "value"}


class FakeTransportContext:
    """Minimal async context manager simulating a transport (read, write) pair."""

    def __init__(self, streams: tuple[Any, ...]) -> None:
        self.streams = streams

    async def __aenter__(self) -> tuple[Any, ...]:
        return self.streams

    async def __aexit__(self, *_: Any) -> None:
        pass


class DummySession:
    """Minimal ClientSession stand-in that ignores client_info and completes immediately."""

    def __init__(self, read: Any, write: Any, **kwargs: Any) -> None:
        self._inner = _make_async_mock_session()

    async def __aenter__(self) -> Any:
        return self._inner

    async def __aexit__(self, *_: Any) -> None:
        pass


def _make_async_mock_session() -> Any:
    from unittest.mock import AsyncMock

    inner = AsyncMock()
    inner.initialize = AsyncMock()
    return inner


class TestManagedUserAgentHeader:
    """Test that ManagedClient transport methods inject User-Agent into headers."""

    @pytest.mark.asyncio
    async def test_streamable_http_injects_user_agent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_run_streamable_http_client passes headers with injected User-Agent to get_transport_ctx."""
        monkeypatch.setenv("MCP_CLIENT_NAME", "managed-http-ua")

        captured: list[dict[str, str] | None] = []

        def fake_get_transport_ctx(request: Any, headers: dict[str, str] | None) -> FakeTransportContext:
            captured.append(headers)
            return FakeTransportContext(("r", "w", None))

        monkeypatch.setattr("src.mcp_connect.client.managed.ClientSession", DummySession)

        from src.mcp_connect.client.managed import ManagedClient
        from src.mcp_connect.models.request import BridgeRequestBody

        request = BridgeRequestBody(
            serverPath="https://example.com/mcp",
            method="tools/list",
            params={},
            mcp_headers={"user-agent": "caller-value", "X-Custom": "keep-me"},
        )

        cleanup_event = asyncio.Event()
        ready_future: asyncio.Future[Any] = asyncio.Future()

        with patch("src.mcp_connect.client.transports.get_transport_ctx", side_effect=fake_get_transport_ctx):
            task = asyncio.create_task(ManagedClient._run_streamable_http_client(request, cleanup_event, ready_future))
            await asyncio.wait_for(asyncio.shield(ready_future), timeout=5.0)
            cleanup_event.set()
            await asyncio.wait_for(task, timeout=5.0)

        assert len(captured) == 1
        assert captured[0] == {"X-Custom": "keep-me", "User-Agent": "managed-http-ua"}

    @pytest.mark.asyncio
    async def test_sse_injects_user_agent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_run_sse_client passes headers with injected User-Agent to sse_client."""
        monkeypatch.setenv("MCP_CLIENT_NAME", "managed-sse-ua")

        captured: list[dict[str, str] | None] = []

        def fake_sse_client(*, url: str, headers: dict[str, str] | None, **kwargs: Any) -> FakeTransportContext:
            captured.append(headers)
            return FakeTransportContext(("r", "w"))

        monkeypatch.setattr("src.mcp_connect.client.managed.sse_client", fake_sse_client)
        monkeypatch.setattr("src.mcp_connect.client.managed.ClientSession", DummySession)

        from src.mcp_connect.client.managed import ManagedClient
        from src.mcp_connect.models.request import BridgeRequestBody

        request = BridgeRequestBody(
            serverPath="https://sse.example.com/mcp",
            method="tools/list",
            params={},
            http_transport_type="sse",
            mcp_headers={"User-Agent": "caller-value"},
        )

        cleanup_event = asyncio.Event()
        ready_future: asyncio.Future[Any] = asyncio.Future()

        task = asyncio.create_task(ManagedClient._run_sse_client(request, cleanup_event, ready_future))
        await asyncio.wait_for(asyncio.shield(ready_future), timeout=5.0)
        cleanup_event.set()
        await asyncio.wait_for(task, timeout=5.0)

        assert len(captured) == 1
        assert captured[0] == {"User-Agent": "managed-sse-ua"}


class TestSingleUsageUserAgentHeader:
    """Test that single-usage transport functions inject User-Agent into headers."""

    @pytest.mark.asyncio
    async def test_http_injects_user_agent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_execute_http_request passes headers with injected User-Agent to get_transport_ctx."""
        monkeypatch.setenv("MCP_CLIENT_NAME", "single-http-ua")

        captured: list[dict[str, str] | None] = []

        def fake_get_transport_ctx(request: Any, headers: dict[str, str] | None) -> FakeTransportContext:
            captured.append(headers)
            return FakeTransportContext(("r", "w", None))

        monkeypatch.setattr("src.mcp_connect.client.single_usage.get_transport_ctx", fake_get_transport_ctx)
        monkeypatch.setattr("src.mcp_connect.client.single_usage.ClientSession", DummySession)

        from src.mcp_connect.client.single_usage import execute_single_usage_request
        from src.mcp_connect.models.request import BridgeRequestBody

        request = BridgeRequestBody(
            serverPath="https://example.com/mcp",
            method="tools/list",
            params={},
            mcp_headers={"user-agent": "caller-value", "X-Custom": "keep-me"},
        )
        await execute_single_usage_request(request, "tools/list", {}, 5000)

        assert len(captured) == 1
        assert captured[0] == {"X-Custom": "keep-me", "User-Agent": "single-http-ua"}

    @pytest.mark.asyncio
    async def test_sse_injects_user_agent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_execute_sse_request passes headers with injected User-Agent to sse_client."""
        monkeypatch.setenv("MCP_CLIENT_NAME", "single-sse-ua")

        captured: list[dict[str, str] | None] = []

        def fake_sse_client(*, url: str, headers: dict[str, str] | None, **kwargs: Any) -> FakeTransportContext:
            captured.append(headers)
            return FakeTransportContext(("r", "w"))

        monkeypatch.setattr("src.mcp_connect.client.single_usage.sse_client", fake_sse_client)
        monkeypatch.setattr("src.mcp_connect.client.single_usage.ClientSession", DummySession)

        from src.mcp_connect.client.single_usage import execute_single_usage_request
        from src.mcp_connect.models.request import BridgeRequestBody

        request = BridgeRequestBody(
            serverPath="https://sse.example.com/mcp",
            method="tools/list",
            params={},
            http_transport_type="sse",
            mcp_headers={"User-Agent": "caller-value"},
        )
        await execute_single_usage_request(request, "tools/list", {}, 5000)

        assert len(captured) == 1
        assert captured[0] == {"User-Agent": "single-sse-ua"}


class TestSigV4UserAgentHeader:
    """Test that the SigV4-signed streamable-http branch inside get_transport_ctx
    receives the injected User-Agent header.

    Unlike the other tests above, this does NOT mock get_transport_ctx itself —
    it exercises the real SigV4 routing in transports.py so the assertion covers
    the actual branch selection, not just the call sites that invoke it.
    """

    @pytest.mark.asyncio
    async def test_sigv4_streamable_http_injects_user_agent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_execute_http_request's headers, with User-Agent injected, reach streamablehttp_client_with_sigv4."""
        monkeypatch.setenv("MCP_CLIENT_NAME", "single-sigv4-ua")

        captured: list[dict[str, str] | None] = []

        def fake_streamablehttp_client_with_sigv4(
            *, url: str, credentials: Any, service: str, region: str, headers: dict[str, str] | None, **kwargs: Any
        ) -> FakeTransportContext:
            captured.append(headers)
            return FakeTransportContext(("r", "w", None))

        monkeypatch.setattr(
            "src.mcp_connect.client.transports.streamablehttp_client_with_sigv4",
            fake_streamablehttp_client_with_sigv4,
        )
        monkeypatch.setattr("src.mcp_connect.client.single_usage.ClientSession", DummySession)

        from src.mcp_connect.client.single_usage import execute_single_usage_request
        from src.mcp_connect.models.request import BridgeRequestBody

        request = BridgeRequestBody(
            serverPath="https://bedrock-agentcore.us-east-1.amazonaws.com/mcp",
            method="tools/list",
            params={},
            mcp_headers={"user-agent": "caller-value", "X-Custom": "keep-me"},
            env={"AWS_ACCESS_KEY_ID": "test-key", "AWS_SECRET_ACCESS_KEY": "test-secret"},
        )
        await execute_single_usage_request(request, "tools/list", {}, 5000)

        assert len(captured) == 1
        assert captured[0] == {"X-Custom": "keep-me", "User-Agent": "single-sigv4-ua"}
