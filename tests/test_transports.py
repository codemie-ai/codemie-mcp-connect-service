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
