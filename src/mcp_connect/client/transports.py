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

"""Reusable transport context managers for MCP clients.

Provides `get_transport_ctx()` which selects the correct transport
context manager (stdio, streamable-http, SSE) and yields the underlying
client context tuple returned by the MCP SDK transport context managers.

This centralizes SigV4 logic so both single-usage and managed clients can
reuse the same decision and avoid duplicated code.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamablehttp_client

from mcp_connect.client.streamable_http_sigv4 import streamablehttp_client_with_sigv4
from mcp_connect.utils.signer import SigV4Manager


@asynccontextmanager
async def get_transport_ctx(request: Any, headers: dict[str, str] | None = None) -> Any:
    """Return an async context manager for the correct transport.

    Yields the *exact* tuple returned by the underlying transport context
    managers so callers can unpack (read, write) or (read, write, get_session_id).
    """
    headers = headers or (request.mcp_headers or {})

    # Detect stdio vs http/sse based on serverPath/http_transport_type
    from .manager import detect_transport_type

    transport_type = detect_transport_type(request.serverPath, request.http_transport_type)

    if transport_type == "stdio":
        # For stdio we construct StdioServerParameters and yield the stdio client
        server_params = StdioServerParameters(
            command=request.serverPath,
            args=request.args or [],
            env=request.env,
        )

        async with stdio_client(server_params) as client_tuple:
            yield client_tuple

    elif transport_type == "streamable-http":
        # Choose SigV4-enabled transport when required
        if SigV4Manager.needs_signing(request.serverPath):
            service = SigV4Manager.extract_service(request.serverPath, request.env or {})
            region = SigV4Manager.extract_region(request.serverPath, request.env or {})
            credentials = SigV4Manager.extract_credentials(request.env or {})

            async with streamablehttp_client_with_sigv4(
                url=request.serverPath,
                credentials=credentials,
                service=service,
                region=region,
                headers=headers,
                timeout=int(os.getenv("MCP_CONNECT_HTTP_TIMEOUT", "30000")) / 1000.0,
                sse_read_timeout=int(os.getenv("MCP_CONNECT_SSE_READ_TIMEOUT", "300000")) / 1000.0,
            ) as client_tuple:
                yield client_tuple

        else:
            async with streamablehttp_client(
                url=request.serverPath,
                headers=headers,
                timeout=int(os.getenv("MCP_CONNECT_HTTP_TIMEOUT", "30000")) / 1000.0,
                sse_read_timeout=int(os.getenv("MCP_CONNECT_SSE_READ_TIMEOUT", "300000")) / 1000.0,
            ) as client_tuple:
                yield client_tuple

    elif transport_type == "sse":
        async with sse_client(
            url=request.serverPath,
            headers=headers,
            timeout=int(os.getenv("MCP_CONNECT_HTTP_TIMEOUT", "30000")) / 1000.0,
            sse_read_timeout=int(os.getenv("MCP_CONNECT_SSE_READ_TIMEOUT", "300000")) / 1000.0,
        ) as client_tuple:
            yield client_tuple

    else:
        raise ValueError(f"Unsupported transport type: {transport_type}")
