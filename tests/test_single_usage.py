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

"""Unit tests for single-usage MCP client implementation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.mcp_connect.client.single_usage import (
    execute_single_usage_request,
)
from src.mcp_connect.models.request import BridgeRequestBody


@dataclass
class FakeContext:
    """Minimal async context manager to simulate MCP transports."""

    return_value: tuple[Any, ...]
    exited: bool = False

    async def __aenter__(self) -> tuple[Any, ...]:
        return self.return_value

    async def __aexit__(self, _exc_type, _exc, _tb) -> None:
        self.exited = True


class DummySession:
    """Fake ClientSession used to avoid real client calls."""

    def __init__(self, read: Any, write: Any, client_info: Any = None) -> None:
        self.read = read
        self.write = write
        self.client_info = client_info
        self.initialized = False
        self.entered = False
        self.exited = False
        # Method mocks
        self.list_tools = AsyncMock(return_value={"tools": []})
        self.call_tool = AsyncMock(return_value={"content": [{"type": "text", "text": "hello"}]})
        self.list_prompts = AsyncMock(return_value={"prompts": []})
        self.list_resources = AsyncMock(return_value={"resources": []})

    async def __aenter__(self) -> DummySession:
        """Enter session context."""
        self.entered = True
        return self

    async def __aexit__(self, _exc_type, _exc, _tb) -> None:
        """Exit session context."""
        self.exited = True

    async def initialize(self) -> None:
        self.initialized = True

    async def send_ping(self) -> dict[str, str]:
        return {"result": "ping"}


class TestExecuteSingleUsageRequest:
    """Test execute_single_usage_request routing and transport detection."""

    @pytest.mark.asyncio
    async def test_routes_to_stdio_transport(self, monkeypatch):
        """Test routing to stdio transport for command paths."""
        fake_context = FakeContext(("read-stream", "write-stream"))

        def fake_stdio_client(*args: Any, **kwargs: Any) -> FakeContext:
            return fake_context

        monkeypatch.setattr("src.mcp_connect.client.single_usage.stdio_client", fake_stdio_client)
        monkeypatch.setattr("src.mcp_connect.client.single_usage.ClientSession", DummySession)

        request = BridgeRequestBody(
            serverPath="echo",
            method="tools/list",
            params={},
            args=["hello"],
            env={"FOO": "bar"},
        )

        result = await execute_single_usage_request(request, "tools/list", {}, 5000)

        assert result == {"tools": []}
        assert fake_context.exited

    @pytest.mark.asyncio
    async def test_routes_to_http_transport(self, monkeypatch):
        """Test routing to streamable-http transport for HTTP URLs."""
        fake_context = FakeContext(("read-stream", "write-stream", lambda: "cleanup"))

        def fake_http_client(*args: Any, **kwargs: Any) -> FakeContext:
            return fake_context

        monkeypatch.setattr("src.mcp_connect.client.single_usage.get_transport_ctx", fake_http_client)
        monkeypatch.setattr("src.mcp_connect.client.single_usage.ClientSession", DummySession)

        request = BridgeRequestBody(
            serverPath="http://example.com/mcp",
            method="tools/list",
            params={},
            mcp_headers={"Authorization": "Bearer token"},
        )

        result = await execute_single_usage_request(request, "tools/list", {}, 5000)

        assert result == {"tools": []}
        assert fake_context.exited

    @pytest.mark.asyncio
    async def test_routes_to_sse_transport(self, monkeypatch):
        """Test routing to SSE transport when explicitly requested."""
        fake_context = FakeContext(("read-stream", "write-stream"))

        def fake_sse_client(*args: Any, **kwargs: Any) -> FakeContext:
            return fake_context

        monkeypatch.setattr("src.mcp_connect.client.single_usage.sse_client", fake_sse_client)
        monkeypatch.setattr("src.mcp_connect.client.single_usage.ClientSession", DummySession)

        request = BridgeRequestBody(
            serverPath="https://example.com/mcp",
            method="tools/list",
            params={},
            http_transport_type="sse",
            mcp_headers={"X-Custom": "value"},
        )

        result = await execute_single_usage_request(request, "tools/list", {}, 5000)

        assert result == {"tools": []}
        assert fake_context.exited

    @pytest.mark.asyncio
    async def test_rejects_unsupported_transport(self):
        """Test that unsupported transport types raise HTTPException."""
        request = BridgeRequestBody(
            serverPath="ws://example.com/mcp",  # WebSocket not supported
            method="tools/list",
            params={},
        )

        with pytest.raises(HTTPException) as exc_info:
            await execute_single_usage_request(request, "tools/list", {}, 5000)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_applies_substitutions(self, monkeypatch):
        """Test that request substitutions are applied before execution."""
        fake_context = FakeContext(("read-stream", "write-stream"))
        substitutions_called = []

        def fake_apply_substitutions(request):
            substitutions_called.append(True)
            return request

        def fake_stdio_client(*args: Any, **kwargs: Any) -> FakeContext:
            return fake_context

        monkeypatch.setattr("src.mcp_connect.client.single_usage.apply_substitutions", fake_apply_substitutions)
        monkeypatch.setattr("src.mcp_connect.client.single_usage.stdio_client", fake_stdio_client)
        monkeypatch.setattr("src.mcp_connect.client.single_usage.ClientSession", DummySession)

        request = BridgeRequestBody(
            serverPath="echo",
            method="tools/list",
            params={},
            env={"TOKEN": "$env:MY_TOKEN"},
            request_headers={"X-Auth": "Bearer secret"},
        )

        await execute_single_usage_request(request, "tools/list", {}, 5000)

        assert substitutions_called  # Verify substitutions were applied


class TestStdioRequest:
    """Test _execute_stdio_request implementation."""

    @pytest.mark.asyncio
    async def test_stdio_success_path(self, monkeypatch):
        """Test successful stdio request execution."""
        fake_context = FakeContext(("read-stream", "write-stream"))

        def fake_stdio_client(*args: Any, **kwargs: Any) -> FakeContext:
            return fake_context

        monkeypatch.setattr("src.mcp_connect.client.single_usage.stdio_client", fake_stdio_client)
        monkeypatch.setattr("src.mcp_connect.client.single_usage.ClientSession", DummySession)

        request = BridgeRequestBody(
            serverPath="python",
            method="tools/call",
            params={"name": "echo", "arguments": {"text": "hello"}},
            args=["-m", "mcp_server"],
            env={"DEBUG": "true"},
        )

        result = await execute_single_usage_request(request, "tools/call", request.params, 5000)

        assert result == {"content": [{"type": "text", "text": "hello"}]}
        assert fake_context.exited

    @pytest.mark.asyncio
    async def test_stdio_timeout_error(self, monkeypatch):
        """Test timeout handling in stdio request."""
        # Set init timeout to 1 second for this test
        monkeypatch.setenv("MCP_CONNECT_INIT_TIMEOUT", "1000")

        # Force reimport to pick up env var
        import importlib

        import src.mcp_connect.client.single_usage as single_usage_module

        importlib.reload(single_usage_module)

        class SlowDummySession(DummySession):
            async def initialize(self) -> None:
                await asyncio.sleep(10)  # Longer than timeout
                self.initialized = True

        fake_context = FakeContext(("read-stream", "write-stream"))

        def fake_stdio_client(*args: Any, **kwargs: Any) -> FakeContext:
            return fake_context

        monkeypatch.setattr("src.mcp_connect.client.single_usage.stdio_client", fake_stdio_client)
        monkeypatch.setattr("src.mcp_connect.client.single_usage.ClientSession", SlowDummySession)

        request = BridgeRequestBody(
            serverPath="slow_command",
            method="tools/call",
            params={"name": "slow_tool"},
            args=[],
        )

        with pytest.raises(HTTPException) as exc_info:
            await single_usage_module.execute_single_usage_request(request, "tools/call", request.params, 5000)

        assert exc_info.value.status_code == 504
        assert "timeout" in exc_info.value.detail["error"].lower()
        assert exc_info.value.detail["method"] == "tools/call"

        # Clean up by reloading with default env
        monkeypatch.delenv("MCP_CONNECT_INIT_TIMEOUT", raising=False)
        importlib.reload(single_usage_module)

    @pytest.mark.asyncio
    async def test_init_timeout_configurable_via_env(self, monkeypatch):
        """Test that MCP_CONNECT_INIT_TIMEOUT environment variable is respected."""
        # Set custom init timeout to 2 seconds
        monkeypatch.setenv("MCP_CONNECT_INIT_TIMEOUT", "2000")

        # Force reimport to pick up env var
        import importlib

        import src.mcp_connect.client.single_usage as single_usage_module

        importlib.reload(single_usage_module)

        class ModeratelySlowDummySession(DummySession):
            async def initialize(self) -> None:
                # Sleep 1.5 seconds - should succeed with 2s timeout
                await asyncio.sleep(1.5)
                self.initialized = True

        fake_context = FakeContext(("read-stream", "write-stream"))

        def fake_stdio_client(*args: Any, **kwargs: Any) -> FakeContext:
            return fake_context

        monkeypatch.setattr("src.mcp_connect.client.single_usage.stdio_client", fake_stdio_client)
        monkeypatch.setattr("src.mcp_connect.client.single_usage.ClientSession", ModeratelySlowDummySession)

        request = BridgeRequestBody(
            serverPath="slow_init_command",
            method="tools/list",
            params={},
            args=[],
        )

        # Should succeed because init timeout is 2s and init takes 1.5s
        result = await single_usage_module.execute_single_usage_request(request, "tools/list", {}, 5000)

        assert result == {"tools": []}

        # Clean up by reloading with default env
        monkeypatch.delenv("MCP_CONNECT_INIT_TIMEOUT", raising=False)
        importlib.reload(single_usage_module)

    @pytest.mark.asyncio
    async def test_stdio_generic_exception(self, monkeypatch):
        """Test generic exception handling in stdio request."""

        class FailingDummySession(DummySession):
            async def initialize(self) -> None:
                raise RuntimeError("Connection failed")

        fake_context = FakeContext(("read-stream", "write-stream"))

        def fake_stdio_client(*args: Any, **kwargs: Any) -> FakeContext:
            return fake_context

        monkeypatch.setattr("src.mcp_connect.client.single_usage.stdio_client", fake_stdio_client)
        monkeypatch.setattr("src.mcp_connect.client.single_usage.ClientSession", FailingDummySession)

        request = BridgeRequestBody(
            serverPath="failing_command",
            method="tools/call",
            params={},
        )

        with pytest.raises(HTTPException) as exc_info:
            await execute_single_usage_request(request, "tools/call", {}, 5000)

        assert exc_info.value.status_code == 500
        assert "Failed to execute MCP request" in exc_info.value.detail["error"]

    @pytest.mark.asyncio
    async def test_stdio_method_timeout(self, monkeypatch):
        """Test timeout during method execution (not initialization)."""
        fake_context = FakeContext(("read-stream", "write-stream"))

        def fake_stdio_client(*args: Any, **kwargs: Any) -> FakeContext:
            return fake_context

        async def slow_invoke(*args, **kwargs):
            await asyncio.sleep(10)  # Longer than timeout
            return {"tools": []}

        monkeypatch.setattr("src.mcp_connect.client.single_usage.stdio_client", fake_stdio_client)
        monkeypatch.setattr("src.mcp_connect.client.single_usage.ClientSession", DummySession)
        monkeypatch.setattr("src.mcp_connect.client.methods.invoke_mcp_method", slow_invoke)

        request = BridgeRequestBody(
            serverPath="slow_method_command",
            method="tools/list",
            params={},
        )

        with pytest.raises(HTTPException) as exc_info:
            await execute_single_usage_request(request, "tools/list", {}, 1000)

        assert exc_info.value.status_code == 504


class TestHttpRequest:
    """Test _execute_http_request implementation."""

    @pytest.mark.asyncio
    async def test_http_success_path(self, monkeypatch):
        """Test successful HTTP request execution."""
        fake_context = FakeContext(("read-stream", "write-stream", lambda: "cleanup"))

        def fake_http_client(*args: Any, **kwargs: Any) -> FakeContext:
            return fake_context

        monkeypatch.setattr("src.mcp_connect.client.single_usage.get_transport_ctx", fake_http_client)
        monkeypatch.setattr("src.mcp_connect.client.single_usage.ClientSession", DummySession)

        request = BridgeRequestBody(
            serverPath="https://mcp.example.com/endpoint",
            method="prompts/list",
            params={},
            mcp_headers={"Authorization": "Bearer token123"},
        )

        result = await execute_single_usage_request(request, "prompts/list", {}, 5000)

        assert result == {"prompts": []}
        assert fake_context.exited

    @pytest.mark.asyncio
    async def test_http_timeout_error(self, monkeypatch):
        """Test timeout handling in HTTP request."""
        fake_context = FakeContext(("read-stream", "write-stream", lambda: "cleanup"))

        def fake_http_client(*args: Any, **kwargs: Any) -> FakeContext:
            return fake_context

        async def slow_invoke(*args, **kwargs):
            await asyncio.sleep(10)
            return {"tools": []}

        monkeypatch.setattr("src.mcp_connect.client.single_usage.get_transport_ctx", fake_http_client)
        monkeypatch.setattr("src.mcp_connect.client.single_usage.ClientSession", DummySession)
        monkeypatch.setattr("src.mcp_connect.client.methods.invoke_mcp_method", slow_invoke)

        request = BridgeRequestBody(
            serverPath="http://slow.example.com/mcp",
            method="tools/list",
            params={},
        )

        with pytest.raises(HTTPException) as exc_info:
            await execute_single_usage_request(request, "tools/list", {}, 2000)

        assert exc_info.value.status_code == 504
        assert "2000ms" in exc_info.value.detail["error"]

    @pytest.mark.asyncio
    async def test_http_generic_exception(self, monkeypatch):
        """Test generic exception handling in HTTP request."""
        fake_context = FakeContext(("read-stream", "write-stream", lambda: "cleanup"))

        def fake_http_client(*args: Any, **kwargs: Any) -> FakeContext:
            return fake_context

        async def failing_invoke(*args, **kwargs):
            raise ValueError("Invalid response")

        monkeypatch.setattr("src.mcp_connect.client.single_usage.get_transport_ctx", fake_http_client)
        monkeypatch.setattr("src.mcp_connect.client.single_usage.ClientSession", DummySession)
        monkeypatch.setattr("src.mcp_connect.client.methods.invoke_mcp_method", failing_invoke)

        request = BridgeRequestBody(
            serverPath="http://broken.example.com/mcp",
            method="tools/list",
            params={},
        )

        with pytest.raises(HTTPException) as exc_info:
            await execute_single_usage_request(request, "tools/list", {}, 5000)

        assert exc_info.value.status_code == 500


class TestSseRequest:
    """Test _execute_sse_request implementation."""

    @pytest.mark.asyncio
    async def test_sse_success_path(self, monkeypatch):
        """Test successful SSE request execution with deprecation warning."""
        fake_context = FakeContext(("read-stream", "write-stream"))

        def fake_sse_client(*args: Any, **kwargs: Any) -> FakeContext:
            return fake_context

        monkeypatch.setattr("src.mcp_connect.client.single_usage.sse_client", fake_sse_client)
        monkeypatch.setattr("src.mcp_connect.client.single_usage.ClientSession", DummySession)

        request = BridgeRequestBody(
            serverPath="https://sse.example.com/mcp",
            method="resources/list",
            params={},
            http_transport_type="sse",
            mcp_headers={"X-API-Key": "secret"},
        )

        result = await execute_single_usage_request(request, "resources/list", {}, 5000)

        assert result == {"resources": []}
        assert fake_context.exited

    @pytest.mark.asyncio
    async def test_sse_timeout_error(self, monkeypatch):
        """Test timeout handling in SSE request."""
        fake_context = FakeContext(("read-stream", "write-stream"))

        def fake_sse_client(*args: Any, **kwargs: Any) -> FakeContext:
            return fake_context

        async def slow_invoke(*args, **kwargs):
            await asyncio.sleep(10)
            return {"tools": []}

        monkeypatch.setattr("src.mcp_connect.client.single_usage.sse_client", fake_sse_client)
        monkeypatch.setattr("src.mcp_connect.client.single_usage.ClientSession", DummySession)
        monkeypatch.setattr("src.mcp_connect.client.methods.invoke_mcp_method", slow_invoke)

        request = BridgeRequestBody(
            serverPath="https://slow-sse.example.com/mcp",
            method="tools/list",
            params={},
            http_transport_type="sse",
        )

        with pytest.raises(HTTPException) as exc_info:
            await execute_single_usage_request(request, "tools/list", {}, 3000)

        assert exc_info.value.status_code == 504
        assert "3000ms" in exc_info.value.detail["error"]

    @pytest.mark.asyncio
    async def test_sse_generic_exception(self, monkeypatch):
        """Test generic exception handling in SSE request."""
        fake_context = FakeContext(("read-stream", "write-stream"))

        def fake_sse_client(*args: Any, **kwargs: Any) -> FakeContext:
            return fake_context

        async def failing_invoke(*args, **kwargs):
            raise ConnectionError("SSE connection failed")

        monkeypatch.setattr("src.mcp_connect.client.single_usage.sse_client", fake_sse_client)
        monkeypatch.setattr("src.mcp_connect.client.single_usage.ClientSession", DummySession)
        monkeypatch.setattr("src.mcp_connect.client.methods.invoke_mcp_method", failing_invoke)

        request = BridgeRequestBody(
            serverPath="https://broken-sse.example.com/mcp",
            method="tools/list",
            params={},
            http_transport_type="sse",
        )

        with pytest.raises(HTTPException) as exc_info:
            await execute_single_usage_request(request, "tools/list", {}, 5000)

        assert exc_info.value.status_code == 500
