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

"""Tests for the /health endpoint."""

from __future__ import annotations

import time

import httpx
import pytest

pytestmark = pytest.mark.asyncio


async def test_health_endpoint_returns_200(
    async_client: httpx.AsyncClient,
) -> None:
    """Test that health endpoint returns 200 OK status code."""

    response = await async_client.get("/health")
    assert response.status_code == 200


async def test_health_endpoint_returns_correct_json(
    async_client: httpx.AsyncClient,
) -> None:
    """Test that health endpoint returns correct JSON body and content type."""

    response = await async_client.get("/health")

    # Verify JSON response body
    assert response.json() == {"status": "ok"}

    # Verify Content-Type header
    assert "application/json" in response.headers["content-type"]


async def test_health_endpoint_responds_quickly(
    async_client: httpx.AsyncClient,
) -> None:
    """Test that health endpoint responds in less than 100ms."""

    start = time.perf_counter()
    response = await async_client.get("/health")
    elapsed = time.perf_counter() - start

    # Verify response is successful
    assert response.status_code == 200

    # Verify response time is under 100ms threshold
    assert elapsed < 0.1, f"Response took {elapsed:.3f}s, expected < 0.1s"


async def test_health_endpoint_idempotent(
    async_client: httpx.AsyncClient,
) -> None:
    """Test that health endpoint returns identical responses across multiple requests."""

    # Make multiple requests
    response1 = await async_client.get("/health")
    response2 = await async_client.get("/health")
    response3 = await async_client.get("/health")

    # All should return 200 OK
    assert response1.status_code == 200
    assert response2.status_code == 200
    assert response3.status_code == 200

    # All should return identical JSON
    expected = {"status": "ok"}
    assert response1.json() == expected
    assert response2.json() == expected
    assert response3.json() == expected
