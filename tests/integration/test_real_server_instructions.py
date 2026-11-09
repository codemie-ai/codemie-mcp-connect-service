"""End-to-end check against a real MCP server declaring instructions."""

from __future__ import annotations

import sys
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from mcp_connect.main import app

pytestmark = pytest.mark.integration

SERVER_INSTRUCTIONS = "Always call the tool with sysparm_help=true before first use."

SERVER_SOURCE = f'''
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("fixture-server", instructions={SERVER_INSTRUCTIONS!r})


@mcp.tool()
def echo(text: str) -> str:
    """Echo the given text."""
    return text


if __name__ == "__main__":
    mcp.run()
'''


@pytest.fixture
def fixture_server(tmp_path: Any) -> str:
    server_file = tmp_path / "fixture_server.py"
    server_file.write_text(SERVER_SOURCE)
    return str(server_file)


async def test_tools_list_exposes_real_server_instructions(fixture_server: str) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/bridge",
            json={
                "serverPath": sys.executable,
                "args": [fixture_server],
                "method": "tools/list",
                "params": {},
                "single_usage": True,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["instructions"] == SERVER_INSTRUCTIONS
    assert [tool["name"] for tool in body["tools"]] == ["echo"]
