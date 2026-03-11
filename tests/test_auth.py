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

"""Authentication tests for the /bridge endpoint."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

pytestmark = pytest.mark.asyncio


def _bridge_payload() -> dict[str, Any]:
    return {
        "serverPath": "./mock-server",
        "method": "ping",
        "params": {"data": "value"},
    }


async def test_missing_authorization_header_returns_401(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ACCESS_TOKEN", "expected-token")

    response = await async_client.post("/bridge", json=_bridge_payload())

    assert response.status_code == 401
    assert response.json() == {"error": "Missing Authorization header"}


@pytest.mark.parametrize(
    "header_value",
    ["Token invalid", "invalid"],
)
async def test_invalid_authorization_format_returns_401(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    header_value: str,
) -> None:
    monkeypatch.setenv("ACCESS_TOKEN", "expected-token")

    response = await async_client.post(
        "/bridge",
        json=_bridge_payload(),
        headers={"Authorization": header_value},
    )

    assert response.status_code == 401
    assert response.json() == {"error": "Invalid Authorization header format"}


async def test_wrong_token_returns_401(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ACCESS_TOKEN", "expected-token")

    response = await async_client.post(
        "/bridge",
        json=_bridge_payload(),
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert response.status_code == 401
    assert response.json() == {"error": "Invalid access token"}


async def test_valid_token_allows_request(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    mock_mcp_client: AsyncMock,
) -> None:
    monkeypatch.setenv("ACCESS_TOKEN", "expected-token")

    response = await async_client.post(
        "/bridge",
        json=_bridge_payload(),
        headers={"Authorization": "Bearer expected-token"},
    )

    assert response.status_code == 200
    assert response.json() == {"result": "pong"}


async def test_health_endpoint_requires_no_authentication(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ACCESS_TOKEN", "expected-token")

    response = await async_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_authentication_disabled_when_access_token_unset(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    mock_mcp_client: AsyncMock,
) -> None:
    monkeypatch.delenv("ACCESS_TOKEN", raising=False)

    bridge_response = await async_client.post("/bridge", json=_bridge_payload())
    health_response = await async_client.get("/health")

    assert bridge_response.status_code == 200
    assert bridge_response.json() == {"result": "pong"}
    assert health_response.status_code == 200
