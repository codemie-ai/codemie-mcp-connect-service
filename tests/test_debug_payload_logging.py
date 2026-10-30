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

"""Tests for the DEBUG_LOG_BRIDGE_PAYLOAD debug payload dump in routes.py.

First-ever coverage of that block: it was gated by a module-import-time constant
and therefore unreachable per-test. Task 7 moves the flag read into a helper
(_debug_log_bridge_payload) so it can be toggled with monkeypatch.setenv.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from mcp_connect.models.request import BridgeRequestBody
from mcp_connect.server import routes as routes_module
from mcp_connect.utils.masking import mask_user_context

FLAG = "DEBUG_LOG_BRIDGE_PAYLOAD"
LOGGER_NAME = "mcp_connect.server.routes"
DUMP_PREFIX = "Bridge endpoint payload"


def _make_request(**overrides: Any) -> BridgeRequestBody:
    payload: dict[str, Any] = {
        "serverPath": "./mock-server",
        "method": "tools/call",
        "params": {"name": "echo", "arguments": {"text": "hi"}},
    }
    payload.update(overrides)
    return BridgeRequestBody(**payload)


def _dump_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.getMessage().startswith(DUMP_PREFIX)]


def _dumped_payload(record: logging.LogRecord) -> dict[str, Any]:
    # logging collapses a lone non-empty mapping arg into record.args itself.
    args = record.args
    if isinstance(args, dict):
        return args
    assert args is not None
    return args[0]  # type: ignore[index,no-any-return]


def test_flag_unset_logs_nothing(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.delenv(FLAG, raising=False)

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        routes_module._debug_log_bridge_payload(_make_request(user_context={"email": "a@b.c"}))

    assert _dump_records(caplog) == []


def test_flag_true_dumps_masked_user_context(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv(FLAG, "true")
    raw_context = {
        "username": "alicesmith",
        "email": "alicesmith@corp.example",
        "roles": ["admin"],
    }
    request = _make_request(user_context=dict(raw_context))

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        routes_module._debug_log_bridge_payload(request)

    records = _dump_records(caplog)
    assert len(records) == 1

    dumped = _dumped_payload(records[0])
    assert dumped["user_context"] == mask_user_context(raw_context)

    whole_record = f"{records[0].getMessage()} {records[0].__dict__}"
    assert "alicesmith@corp.example" not in whole_record
    assert "alicesmith" not in whole_record


def test_flag_true_masks_request_headers_and_env(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv(FLAG, "1")
    request = _make_request(
        request_headers={"Authorization": "Bearer xyz", "Accept": "application/json"},
        env={"SECRET_KEY": "topsecret", "PLAIN_VAR": "visible"},
    )

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        routes_module._debug_log_bridge_payload(request)

    dumped = _dumped_payload(_dump_records(caplog)[0])

    # request_headers: every value redacted (mask_all=True)
    assert dumped["request_headers"] == {
        "Authorization": "********",
        "Accept": "********",
    }
    # env: only sensitive keys redacted (mask_all=False)
    assert dumped["env"] == {"SECRET_KEY": "********", "PLAIN_VAR": "visible"}


def test_user_context_absent_from_dump_when_not_supplied(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv(FLAG, "true")

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        routes_module._debug_log_bridge_payload(_make_request())

    dumped = _dumped_payload(_dump_records(caplog)[0])
    assert "user_context" not in dumped


def test_flag_toggles_between_calls_without_reimport(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    request = _make_request()

    monkeypatch.setenv(FLAG, "false")
    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        routes_module._debug_log_bridge_payload(request)
    assert _dump_records(caplog) == []

    caplog.clear()

    monkeypatch.setenv(FLAG, "yes")
    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        routes_module._debug_log_bridge_payload(request)
    assert len(_dump_records(caplog)) == 1


@pytest.mark.asyncio
async def test_bridge_endpoint_dumps_masked_user_context(
    async_client: httpx.AsyncClient,
    mock_mcp_client: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """POST /bridge itself writes the dump, with user_context already masked."""
    monkeypatch.setenv(FLAG, "true")
    raw_context = {
        "username": "alicesmith",
        "email": "alicesmith@corp.example",
        "roles": ["admin"],
    }
    payload = {
        "serverPath": "./mock-server",
        "method": "tools/call",
        "params": {"name": "echo", "arguments": {"text": "hi"}},
        "single_usage": True,
        "user_context": dict(raw_context),
    }

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        response = await async_client.post("/bridge", json=payload)

    assert response.status_code == 200
    records = _dump_records(caplog)
    assert len(records) == 1
    assert _dumped_payload(records[0])["user_context"] == mask_user_context(raw_context)
    assert "alicesmith@corp.example" not in records[0].getMessage()
