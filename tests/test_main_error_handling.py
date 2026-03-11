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
                "serverPath": "test",
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
