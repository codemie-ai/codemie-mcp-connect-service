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

"""EPMCDME-14735: /bridge end-to-end over a real stdio server returning ``resource_link`` items."""

from __future__ import annotations

import base64
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from mcp_connect.client import export
from mcp_connect.client import manager as manager_module
from mcp_connect.client.cache import MCPClientCache
from mcp_connect.utils import workspace

SERVER = str(Path(__file__).parent / "fixtures" / "link_server.py")
USER = "e2e-user"


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The calling user's folder; the server writes there, as an assistant told to save in it would."""
    resolved = tmp_path.resolve() / "root"
    resolved.mkdir()
    monkeypatch.setattr(workspace, "SERVER_CWD", str(resolved))
    monkeypatch.setattr(export, "_inflight", 0)
    mine = Path(str(workspace.user_root(USER)))
    mine.mkdir()
    return mine


@pytest.fixture
async def cache() -> AsyncIterator[MCPClientCache]:
    """ASGITransport skips the app lifespan, so install the cache and stop its clients afterwards."""
    cache = MCPClientCache()
    manager_module._client_cache = cache
    yield cache
    await cache.clear()
    manager_module._client_cache = None


async def _call(
    client: httpx.AsyncClient, root: Path, tool: str, single_usage: bool, outside: Path | None = None
) -> list[dict[str, Any]]:
    env = {"CODEMIE_EXPORT_FILES": "true", "LINK_SERVER_DIR": str(root)}
    if outside is not None:
        env["LINK_SERVER_OUTSIDE"] = str(outside)
    response = await client.post(
        "/bridge",
        json={
            "serverPath": sys.executable,
            "args": [SERVER],
            "env": env,
            "method": "tools/call",
            "params": {"name": tool, "arguments": {}},
            "single_usage": single_usage,
            "user_id": USER,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert not body.get("isError"), body
    return body["content"]  # type: ignore[no-any-return]


@pytest.mark.parametrize("single_usage", [True, False])
async def test_link_becomes_embedded_resource(
    async_client: httpx.AsyncClient, root: Path, cache: MCPClientCache, single_usage: bool
) -> None:
    content = await _call(async_client, root, "write_one", single_usage)
    assert [c["type"] for c in content] == ["resource"]
    resource = content[0]["resource"]
    assert resource["uri"] == "file:///report.csv" and resource["mimeType"] == "text/csv"
    assert base64.b64decode(resource["blob"]) == b"x,y"


@pytest.mark.parametrize("single_usage", [True, False])
async def test_missing_and_outside_root_links_become_notes(
    async_client: httpx.AsyncClient, root: Path, cache: MCPClientCache, tmp_path: Path, single_usage: bool
) -> None:
    missing = await _call(async_client, root, "link_missing", single_usage)
    assert len(missing) == 1 and missing[0]["type"] == "text" and "file not found" in missing[0]["text"]

    secret = tmp_path / "secret.txt"
    secret.write_bytes(b"s3cret")
    outside = await _call(async_client, root, "link_outside_root", single_usage, outside=secret)
    assert len(outside) == 1 and outside[0]["type"] == "text" and "outside" in outside[0]["text"]
    assert "blob" not in str(outside)


async def test_link_between_text_keeps_position(
    async_client: httpx.AsyncClient, root: Path, cache: MCPClientCache
) -> None:
    content = await _call(async_client, root, "link_and_text", True)
    assert [c["type"] for c in content] == ["text", "resource", "text"]
    assert base64.b64decode(content[1]["resource"]["blob"]) == b"hi"


async def test_same_named_second_link_is_delivered_too(
    async_client: httpx.AsyncClient, root: Path, cache: MCPClientCache
) -> None:
    content = await _call(async_client, root, "write_same_name", True)
    assert [c["type"] for c in content] == ["resource", "resource"]
    assert [base64.b64decode(c["resource"]["blob"]) for c in content] == [b"1", b"2"]
