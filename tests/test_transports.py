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

"""Transport detection tests for MCP client manager."""

import pytest
from fastapi import HTTPException

from src.mcp_connect.client.manager import detect_transport_type


class TestTransportDetection:
    """Verify detect_transport_type handles HTTP transports."""

    def test_http_url_defaults_to_streamable(self):
        assert detect_transport_type("http://example.com/mcp") == "streamable-http"

    def test_https_url_defaults_to_streamable(self):
        assert detect_transport_type("https://secure.example.com/mcp") == "streamable-http"

    def test_http_url_prefers_sse_when_requested(self):
        assert detect_transport_type("http://example.com/mcp", "sse") == "sse"

    def test_websocket_urls_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            detect_transport_type("ws://example.com/mcp")
        assert exc_info.value.status_code == 400
        assert "WebSocket" in exc_info.value.detail["error"]

    def test_secure_websocket_urls_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            detect_transport_type("wss://example.com/mcp")
        assert exc_info.value.status_code == 400
        assert "WebSocket" in exc_info.value.detail["error"]

    # Allowed stdio commands — must return "stdio"

    def test_uvx_command_accepted(self):
        assert detect_transport_type("uvx") == "stdio"

    def test_npx_command_accepted(self):
        assert detect_transport_type("npx") == "stdio"

    def test_absolute_path_uvx_accepted(self):
        assert detect_transport_type("/usr/local/bin/uvx") == "stdio"

    def test_mcp_server_filesystem_accepted(self):
        assert detect_transport_type("mcp-server-filesystem") == "stdio"

    def test_mcp_server_memory_accepted(self):
        assert detect_transport_type("mcp-server-memory") == "stdio"

    def test_mcp_server_sequential_thinking_accepted(self):
        assert detect_transport_type("mcp-server-sequential-thinking") == "stdio"

    def test_mcp_server_postgres_accepted(self):
        assert detect_transport_type("mcp-server-postgres") == "stdio"

    def test_mcp_server_puppeteer_accepted(self):
        assert detect_transport_type("mcp-server-puppeteer") == "stdio"

    def test_mcp_mermaid_accepted(self):
        assert detect_transport_type("mcp-mermaid") == "stdio"

    # Disallowed stdio commands — must raise HTTPException(400)

    def test_disallowed_command_bash_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            detect_transport_type("bash")
        assert exc_info.value.status_code == 400
        assert "bash" in exc_info.value.detail["error"]
        assert "not allowed" in exc_info.value.detail["error"]

    def test_disallowed_command_python_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            detect_transport_type("python")
        assert exc_info.value.status_code == 400
        assert "not allowed" in exc_info.value.detail["error"]

    def test_disallowed_command_curl_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            detect_transport_type("curl")
        assert exc_info.value.status_code == 400
        assert "not allowed" in exc_info.value.detail["error"]

    def test_empty_command_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            detect_transport_type("")
        assert exc_info.value.status_code == 400
        assert "not allowed" in exc_info.value.detail["error"]

    def test_absolute_path_disallowed_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            detect_transport_type("/usr/bin/bash")
        assert exc_info.value.status_code == 400
        assert "bash" in exc_info.value.detail["error"]
        assert "not allowed" in exc_info.value.detail["error"]
