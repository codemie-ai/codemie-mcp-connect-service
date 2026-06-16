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

"""Tests for main.py error handling and edge cases."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.mcp_connect.main import app


@pytest.mark.asyncio
async def test_validation_error_handler():
    """Test validation error handler returns 422."""
    client = TestClient(app)

    # Invalid request body (missing required fields)
    response = client.post("/bridge", json={})

    assert response.status_code == 422
    response_json = response.json()
    assert "detail" in response_json


@pytest.mark.asyncio
async def test_generic_exception_handler():
    """Test generic exception handler returns 500."""
    from unittest.mock import patch

    client = TestClient(app)

    # Trigger a generic exception by patching verify_token
    with patch("src.mcp_connect.server.middleware.verify_token", side_effect=RuntimeError("Test error")):
        response = client.post(
            "/bridge",
            json={
                "serverPath": "uvx",
                "method": "ping",
                "params": {},
            },
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 500


@pytest.mark.asyncio
async def test_http_exception_handler():
    """Test HTTP exception handler preserves status code."""
    from unittest.mock import AsyncMock, patch

    from fastapi import HTTPException

    client = TestClient(app)

    # Trigger HTTPException
    with patch("src.mcp_connect.server.routes.get_or_create_client", new_callable=AsyncMock) as mock:
        mock.side_effect = HTTPException(status_code=503, detail="Service unavailable")

        response = client.post(
            "/bridge",
            json={
                "serverPath": "test",
                "method": "ping",
                "params": {},
            },
        )

    assert response.status_code == 503
    assert "Service unavailable" in response.text


def _make_http_status_error(
    status_code: int,
    body: bytes = b"",
    headers: dict[str, str] | None = None,
) -> Any:
    import httpx

    request = httpx.Request("POST", "https://downstream.example.com/mcp")
    response = httpx.Response(status_code, content=body, headers=headers or {}, request=request)
    return httpx.HTTPStatusError(f"Client error '{status_code}'", request=request, response=response)


@pytest.mark.asyncio
async def test_cached_client_propagates_401_from_downstream_on_init():
    """Downstream 401 during client init (ExceptionGroup) → HTTP 401 response."""
    from unittest.mock import AsyncMock, patch

    exc = _make_http_status_error(401)
    group = BaseExceptionGroup("unhandled errors in a TaskGroup (1 sub-exception)", [exc])

    client = TestClient(app)
    with patch("src.mcp_connect.server.routes.get_or_create_client", new_callable=AsyncMock) as mock:
        mock.side_effect = group

        response = client.post(
            "/bridge",
            json={"serverPath": "https://downstream.example.com/mcp", "method": "tools/list", "params": {}},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_cached_client_propagates_403_from_downstream_on_init():
    """Downstream 403 during client init → HTTP 403 response."""
    from unittest.mock import AsyncMock, patch

    exc = _make_http_status_error(403)

    client = TestClient(app)
    with patch("src.mcp_connect.server.routes.get_or_create_client", new_callable=AsyncMock) as mock:
        mock.side_effect = exc

        response = client.post(
            "/bridge",
            json={"serverPath": "https://downstream.example.com/mcp", "method": "tools/list", "params": {}},
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_cached_client_propagates_401_from_downstream_on_method_call():
    """Downstream 401 during method call (ExceptionGroup) → HTTP 401 response."""
    from unittest.mock import AsyncMock, MagicMock, patch

    exc = _make_http_status_error(401)
    group = BaseExceptionGroup("unhandled errors in a TaskGroup (1 sub-exception)", [exc])

    mock_session = MagicMock()
    mock_managed = MagicMock()

    client = TestClient(app)
    with patch("src.mcp_connect.server.routes.get_or_create_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = (mock_managed, mock_session)
        with patch("src.mcp_connect.server.routes.invoke_with_timeout", new_callable=AsyncMock) as mock_invoke:
            mock_invoke.side_effect = group

            response = client.post(
                "/bridge",
                json={"serverPath": "https://downstream.example.com/mcp", "method": "tools/list", "params": {}},
            )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_cached_client_propagates_404_from_downstream_on_method_call():
    """Downstream 404 during method call → HTTP 404 response."""
    from unittest.mock import AsyncMock, MagicMock, patch

    exc = _make_http_status_error(404)

    mock_session = MagicMock()
    mock_managed = MagicMock()

    client = TestClient(app)
    with patch("src.mcp_connect.server.routes.get_or_create_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = (mock_managed, mock_session)
        with patch("src.mcp_connect.server.routes.invoke_with_timeout", new_callable=AsyncMock) as mock_invoke:
            mock_invoke.side_effect = exc

            response = client.post(
                "/bridge",
                json={"serverPath": "https://downstream.example.com/mcp", "method": "tools/list", "params": {}},
            )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cached_client_detail_includes_error_info_on_downstream_error():
    """Response detail includes error and url fields when downstream returns HTTP error."""
    from unittest.mock import AsyncMock, patch

    exc = _make_http_status_error(401)
    group = BaseExceptionGroup("unhandled errors in a TaskGroup (1 sub-exception)", [exc])

    client = TestClient(app)
    with patch("src.mcp_connect.server.routes.get_or_create_client", new_callable=AsyncMock) as mock:
        mock.side_effect = group

        response = client.post(
            "/bridge",
            json={"serverPath": "https://downstream.example.com/mcp", "method": "tools/list", "params": {}},
        )

    assert response.status_code == 401
    body = response.json()
    assert "error" in body
    assert "url" in body


@pytest.mark.asyncio
async def test_cleanup_scheduler_error_handling():
    """Test cleanup scheduler handles errors gracefully."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from src.mcp_connect.client.cache import MCPClientCache
    from src.mcp_connect.main import _cleanup_scheduler

    cache = MCPClientCache(ttl_seconds=1)

    # Add a client that will fail during cleanup
    mock_managed = MagicMock()
    mock_managed.cleanup = AsyncMock(side_effect=RuntimeError("Cleanup failed"))

    with patch("time.monotonic", side_effect=[100.0, 102.0]):  # Simulate time passing
        await cache.set("test_key", mock_managed)

    # Mock sleep to exit after one iteration
    sleep_count = 0

    async def mock_sleep(delay):
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count > 1:
            raise asyncio.CancelledError()

    with patch("asyncio.sleep", side_effect=mock_sleep):
        with patch("time.monotonic", return_value=110.0):  # Client expired
            try:
                await _cleanup_scheduler(cache)
            except asyncio.CancelledError:
                pass

    # Scheduler should have handled the error and continued
    assert sleep_count >= 1


@pytest.mark.asyncio
async def test_cleanup_scheduler_cancellation():
    """Test cleanup scheduler handles cancellation."""
    import asyncio
    from unittest.mock import patch

    from src.mcp_connect.client.cache import MCPClientCache
    from src.mcp_connect.main import _cleanup_scheduler

    cache = MCPClientCache(ttl_seconds=10)

    # Mock sleep to raise CancelledError immediately
    with patch("asyncio.sleep", side_effect=asyncio.CancelledError()):
        # Should exit gracefully
        await _cleanup_scheduler(cache)


@pytest.mark.asyncio
async def test_downstream_401_forwards_www_authenticate_header():
    """WWW-Authenticate from downstream 401 is forwarded as response header."""
    from unittest.mock import AsyncMock, patch

    exc = _make_http_status_error(
        401,
        body=b'{"error": "invalid_token"}',
        headers={"WWW-Authenticate": 'Bearer realm="example"'},
    )

    client = TestClient(app)
    with patch("src.mcp_connect.server.routes.get_or_create_client", new_callable=AsyncMock) as mock:
        mock.side_effect = exc

        response = client.post(
            "/bridge",
            json={"serverPath": "https://downstream.example.com/mcp", "method": "tools/list", "params": {}},
        )

    assert response.status_code == 401
    assert "www-authenticate" in {k.lower() for k in response.headers}


@pytest.mark.asyncio
async def test_downstream_401_forwards_response_body_in_detail():
    """JSON body from downstream 401 is included in the error response body."""
    from unittest.mock import AsyncMock, patch

    exc = _make_http_status_error(
        401,
        body=b'{"error": "invalid_token", "error_description": "Token expired"}',
    )

    client = TestClient(app)
    with patch("src.mcp_connect.server.routes.get_or_create_client", new_callable=AsyncMock) as mock:
        mock.side_effect = exc

        response = client.post(
            "/bridge",
            json={"serverPath": "https://downstream.example.com/mcp", "method": "tools/list", "params": {}},
        )

    assert response.status_code == 401
    body = response.json()
    assert "response" in body
    assert body["response"]["error"] == "invalid_token"


@pytest.mark.asyncio
async def test_downstream_401_method_call_forwards_www_authenticate_header():
    """WWW-Authenticate from downstream 401 during method call is forwarded."""
    from unittest.mock import AsyncMock, MagicMock, patch

    exc = _make_http_status_error(
        401,
        headers={"WWW-Authenticate": 'Bearer realm="example"'},
    )
    group = BaseExceptionGroup("unhandled errors in a TaskGroup (1 sub-exception)", [exc])

    mock_session = MagicMock()
    mock_managed = MagicMock()

    client = TestClient(app)
    with patch("src.mcp_connect.server.routes.get_or_create_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = (mock_managed, mock_session)
        with patch("src.mcp_connect.server.routes.invoke_with_timeout", new_callable=AsyncMock) as mock_invoke:
            mock_invoke.side_effect = group

            response = client.post(
                "/bridge",
                json={"serverPath": "https://downstream.example.com/mcp", "method": "tools/list", "params": {}},
            )

    assert response.status_code == 401
    assert "www-authenticate" in {k.lower() for k in response.headers}


@pytest.mark.asyncio
async def test_downstream_401_method_call_forwards_response_body_in_detail():
    """single_usage=false: JSON body from downstream 401 during method call included in detail."""
    from unittest.mock import AsyncMock, MagicMock, patch

    exc = _make_http_status_error(
        401,
        body=b'{"error": "invalid_token", "error_description": "Token expired"}',
    )
    group = BaseExceptionGroup("unhandled errors in a TaskGroup (1 sub-exception)", [exc])

    mock_session = MagicMock()
    mock_managed = MagicMock()

    client = TestClient(app)
    with patch("src.mcp_connect.server.routes.get_or_create_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = (mock_managed, mock_session)
        with patch("src.mcp_connect.server.routes.invoke_with_timeout", new_callable=AsyncMock) as mock_invoke:
            mock_invoke.side_effect = group

            response = client.post(
                "/bridge",
                json={"serverPath": "https://downstream.example.com/mcp", "method": "tools/list", "params": {}},
            )

    assert response.status_code == 401
    body = response.json()
    assert "response" in body
    assert body["response"]["error"] == "invalid_token"


@pytest.mark.asyncio
async def test_single_usage_true_downstream_401_forwards_www_authenticate_header():
    """single_usage=true: WWW-Authenticate from downstream 401 forwarded to client."""
    from unittest.mock import AsyncMock, patch

    exc = _make_http_status_error(
        401,
        headers={"WWW-Authenticate": 'Bearer realm="example"'},
    )

    client = TestClient(app)
    with patch("src.mcp_connect.server.routes.execute_single_usage_request", new_callable=AsyncMock) as mock:
        mock.side_effect = exc

        response = client.post(
            "/bridge",
            json={
                "serverPath": "https://downstream.example.com/mcp",
                "method": "tools/list",
                "params": {},
                "single_usage": True,
            },
        )

    assert response.status_code == 401
    assert "www-authenticate" in {k.lower() for k in response.headers}


@pytest.mark.asyncio
async def test_single_usage_true_downstream_401_forwards_response_body_in_detail():
    """single_usage=true: JSON body from downstream 401 included in error response."""
    from unittest.mock import AsyncMock, patch

    exc = _make_http_status_error(
        401,
        body=b'{"error": "invalid_token", "error_description": "Token expired"}',
    )

    client = TestClient(app)
    with patch("src.mcp_connect.server.routes.execute_single_usage_request", new_callable=AsyncMock) as mock:
        mock.side_effect = exc

        response = client.post(
            "/bridge",
            json={
                "serverPath": "https://downstream.example.com/mcp",
                "method": "tools/list",
                "params": {},
                "single_usage": True,
            },
        )

    assert response.status_code == 401
    body = response.json()
    assert "response" in body
    assert body["response"]["error"] == "invalid_token"
