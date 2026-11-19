"""Stdio MCP server whose tools return SDK-typed ``ResourceLink`` items (EPMCDME-14735 e2e)."""

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ContentBlock, ResourceLink, TextContent

mcp = FastMCP("link-server")


def _dir() -> Path:
    return Path(os.environ["LINK_SERVER_DIR"])


def _link(path: Path, name: str = "f") -> ResourceLink:
    return ResourceLink(type="resource_link", name=name, uri=path.as_uri())  # type: ignore[arg-type]


@mcp.tool()
def write_one() -> list[ContentBlock]:
    path = _dir() / "report.csv"
    path.write_bytes(b"x,y")
    return [_link(path)]


@mcp.tool()
def link_missing() -> list[ContentBlock]:
    return [_link(_dir() / "missing.txt")]


@mcp.tool()
def link_outside_root() -> list[ContentBlock]:
    return [_link(Path(os.environ["LINK_SERVER_OUTSIDE"]))]


@mcp.tool()
def write_same_name() -> list[ContentBlock]:
    paths = []
    for sub, data in (("a", b"1"), ("b", b"2")):
        (_dir() / sub).mkdir(exist_ok=True)
        paths.append(_dir() / sub / "same.txt")
        paths[-1].write_bytes(data)
    return [_link(p) for p in paths]


@mcp.tool()
def link_and_text() -> list[ContentBlock]:
    path = _dir() / "note.txt"
    path.write_bytes(b"hi")
    return [TextContent(type="text", text="before"), _link(path), TextContent(type="text", text="after")]


if __name__ == "__main__":
    mcp.run("stdio")
