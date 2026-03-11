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

"""Tests for environment variable substitution utilities."""

from __future__ import annotations

import logging

import pytest
from fastapi import HTTPException

from src.mcp_connect.models.request import BridgeRequestBody
from src.mcp_connect.utils.substitution import apply_substitutions, substitute_variables


def test_substitute_single_variable() -> None:
    env = {"HOST": "example.com"}
    result = substitute_variables("https://$HOST/path", env)
    assert result == "https://example.com/path"


def test_substitute_multiple_variables() -> None:
    env = {"PROTO": "https", "HOST": "api.local", "PORT": "8080"}
    result = substitute_variables("$PROTO://$HOST:$PORT", env)
    assert result == "https://api.local:8080"


def test_substitute_variables_without_matches_returns_input() -> None:
    env = {"TOKEN": "secret"}
    result = substitute_variables("no placeholders here", env)
    assert result == "no placeholders here"


def test_substitute_stops_at_invalid_variable_characters() -> None:
    env = {"TOKEN": "secret"}
    template = "$TOKEN-NAME"
    result = substitute_variables(template, env)
    assert result == "secret-NAME"


def test_apply_substitutions_updates_fields_and_preserves_original_request() -> None:
    request = BridgeRequestBody(
        serverPath="https://$HOST:$PORT/mcp",
        args=["--api-key=$TOKEN", "start"],
        mcp_headers={"Authorization": "Bearer $TOKEN"},
        env={"HOST": "api.example.com", "PORT": "3000", "TOKEN": "secret123"},
        method="ping",
        params={},
    )

    substituted = apply_substitutions(request)

    assert substituted.serverPath == "https://api.example.com:3000/mcp"
    assert substituted.args == ["--api-key=secret123", "start"]
    assert substituted.mcp_headers == {"Authorization": "Bearer secret123"}

    # Original request must remain unchanged
    assert request.serverPath == "https://$HOST:$PORT/mcp"
    assert request.args == ["--api-key=$TOKEN", "start"]
    assert request.mcp_headers == {"Authorization": "Bearer $TOKEN"}


def test_apply_substitutions_skips_fields_without_patterns() -> None:
    request = BridgeRequestBody(
        serverPath="npx",
        args=["--config", "local.json"],
        mcp_headers={"Content-Type": "application/json"},
        env={"TOKEN": "value"},
        method="ping",
        params={},
    )

    substituted = apply_substitutions(request)

    assert substituted.serverPath == "npx"
    assert substituted.args == ["--config", "local.json"]
    assert substituted.mcp_headers == {"Content-Type": "application/json"}


def test_missing_variable_raises_http_exception() -> None:
    request = BridgeRequestBody(
        serverPath="https://$HOST/mcp",
        env={},
        method="ping",
        params={},
    )

    with pytest.raises(HTTPException) as excinfo:
        apply_substitutions(request)

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == {
        "error": "Variable 'HOST' not found in env",
        "available": [],
    }


def test_logging_masks_env_values(caplog: pytest.LogCaptureFixture) -> None:
    request = BridgeRequestBody(
        serverPath="https://$HOST/mcp",
        env={"HOST": "api.internal", "TOKEN": "supersecret"},
        method="ping",
        params={},
    )

    caplog.set_level(logging.DEBUG, logger="src.mcp_connect.utils.substitution")

    apply_substitutions(request)

    log_messages = " ".join(record.getMessage() for record in caplog.records)
    assert "supersecret" not in log_messages
    assert "api.internal" not in log_messages
    assert "HOST" in log_messages
    assert "TOKEN" in log_messages
    assert "********" in log_messages


def test_substitute_single_header() -> None:
    result = substitute_variables(
        "https://$headers.host/path",
        env={},
        request_headers={"host": "example.com"},
    )
    assert result == "https://example.com/path"


def test_substitute_multiple_headers() -> None:
    result = substitute_variables(
        "$headers.proto://$headers.host:$headers.port/path",
        env={},
        request_headers={"proto": "https", "host": "api.com", "port": "443"},
    )
    assert result == "https://api.com:443/path"


def test_header_case_insensitive() -> None:
    upper_placeholder = substitute_variables(
        "$headers.Host",
        env={},
        request_headers={"host": "example.com"},
    )
    lower_placeholder = substitute_variables(
        "$headers.host",
        env={},
        request_headers={"Host": "example.com"},
    )
    assert upper_placeholder == "example.com"
    assert lower_placeholder == "example.com"


def test_missing_header_raises_http_exception() -> None:
    with pytest.raises(HTTPException) as excinfo:
        substitute_variables(
            "https://$headers.target/mcp",
            env={},
            request_headers={"host": "example.com"},
        )

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == {
        "error": "Header 'target' not found in request_headers",
        "available": ["host"],
    }


def test_mixed_env_and_header_substitution() -> None:
    result = substitute_variables(
        "https://$HOST:$PORT/api?token=$headers.auth_token",
        env={"HOST": "mcp.example.com", "PORT": "8080"},
        request_headers={"auth_token": "secret"},
    )
    assert result == "https://mcp.example.com:8080/api?token=secret"


def test_header_substitution_in_args() -> None:
    request = BridgeRequestBody(
        serverPath="tool",
        args=["--region=$headers.region", "--token=$headers.token"],
        request_headers={"Region": "us-east-1", "token": "abc123"},
        method="ping",
        params={},
    )

    substituted = apply_substitutions(request)

    assert substituted.args == ["--region=us-east-1", "--token=abc123"]


def test_header_substitution_in_mcp_headers() -> None:
    request = BridgeRequestBody(
        serverPath="tool",
        mcp_headers={"Authorization": "Bearer $headers.api_token"},
        request_headers={"api_token": "super-secret"},
        method="ping",
        params={},
    )

    substituted = apply_substitutions(request)

    assert substituted.mcp_headers == {"Authorization": "Bearer super-secret"}


def test_logging_masks_header_values(caplog: pytest.LogCaptureFixture) -> None:
    request = BridgeRequestBody(
        serverPath="https://example.com",
        request_headers={"X-API-Key": "secret-key", "Region": "us-east-1"},
        method="ping",
        params={},
    )

    caplog.set_level(logging.DEBUG, logger="src.mcp_connect.utils.substitution")

    apply_substitutions(request)

    log_messages = " ".join(record.getMessage() for record in caplog.records)
    assert "secret-key" not in log_messages
    assert "us-east-1" not in log_messages
    assert "X-API-Key" in log_messages
    assert "Region" in log_messages
    assert "********" in log_messages
