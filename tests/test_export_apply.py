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

"""EPMCDME-14735: tools/call export apply, releasing response, off-loop render."""

from __future__ import annotations

import asyncio
import base64
import json
import threading
from pathlib import Path
from typing import Any

import pytest
from fastapi.responses import JSONResponse
from mcp.types import (
    CallToolResult,
    EmbeddedResource,
    ImageContent,
    ResourceLink,
    TextContent,
    TextResourceContents,
)

from mcp_connect.client import export
from mcp_connect.client.methods import _mcp_error_to_tool_result
from mcp_connect.utils import workspace


@pytest.fixture(autouse=True)
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    resolved = tmp_path.resolve()
    monkeypatch.setattr(workspace, "SERVER_CWD", str(resolved))
    monkeypatch.setattr(export, "_inflight", 0)
    return resolved


def _ctx(
    requested: Any, enabled: bool = True, stdio: bool = True, base_dir: str | None = None, root: str | None = "test"
) -> export.ExportContext:
    # "test" stands for the fixture's root, read at call time; None is a call without a user
    return export.ExportContext(
        stdio, enabled, "tools/call", requested, base_dir, workspace.SERVER_CWD if root == "test" else root
    )


def _result(is_error: bool = False) -> CallToolResult:
    return CallToolResult(
        content=[
            TextContent(type="text", text="done"),
            ImageContent(type="image", data="AAAA", mimeType="image/png"),
        ],
        isError=is_error,
    )


def _today(result: Any) -> bytes:
    return JSONResponse(content=result.model_dump(mode="json", exclude_none=True), status_code=200, headers={}).body  # type: ignore[return-value]


async def _body(ctx: export.ExportContext, result: Any) -> dict[str, Any]:
    response = await export.apply(ctx, result, {})
    return json.loads(bytes(response.body))  # type: ignore[attr-defined]


@pytest.mark.parametrize("requested", [None, []])
async def test_nothing_requested_is_byte_identical(requested: Any) -> None:
    response = await export.apply(_ctx(requested), _result(), {})
    assert response.body == _today(_result())  # type: ignore[attr-defined]


@pytest.mark.parametrize("ctx", [_ctx(["a"], enabled=False), _ctx(["a"], enabled=False, stdio=False)])
async def test_disabled_or_http_not_modified(ctx: export.ExportContext) -> None:
    response = await export.apply(ctx, _result(), {})
    assert response.body == _today(_result())  # type: ignore[attr-defined]


@pytest.mark.parametrize("bad", ["a.txt", [1], {"a": 1}, 5])
async def test_invalid_value_gives_one_note(bad: Any) -> None:
    body = await _body(_ctx(bad), _result())
    assert body["content"][:2] == _result().model_dump(mode="json", exclude_none=True)["content"]
    assert len(body["content"]) == 3 and "expected a list" in body["content"][2]["text"]


async def test_error_result_with_request_adds_skip_note_and_never_collects(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a: Any, **k: Any) -> None:
        raise AssertionError("collect_exports must not run")

    monkeypatch.setattr(export, "collect_exports", boom)
    body = await _body(_ctx(["a.txt"]), _result(is_error=True))
    assert body["isError"] is True
    assert body["content"][:2] == _result().model_dump(mode="json", exclude_none=True)["content"]
    assert body["content"][2] == {"type": "text", "text": "export skipped: the call failed"}
    assert len(body["content"]) == 3


async def test_error_result_without_request_is_byte_identical() -> None:
    from mcp.shared.exceptions import McpError
    from mcp.types import ErrorData

    for result in (
        _result(is_error=True),
        _mcp_error_to_tool_result("t", McpError(ErrorData(code=-32602, message="m")).error),
    ):
        response = await export.apply(_ctx(None), result, {})
        assert response.body == _today(result)  # type: ignore[attr-defined]


async def test_files_appended_after_server_content(root: Path) -> None:
    (root / "a b.csv").write_bytes(b"x,y")
    body = await _body(_ctx(["a b.csv", "missing.txt"]), _result())
    content = body["content"]
    assert content[:2] == _result().model_dump(mode="json", exclude_none=True)["content"]
    assert content[2]["type"] == "resource"
    assert content[2]["resource"]["uri"] == "file:///a%20b.csv"
    assert content[2]["resource"]["mimeType"] == "text/csv"
    assert base64.b64decode(content[2]["resource"]["blob"]) == b"x,y"
    assert content[3]["type"] == "text" and "missing.txt: file not found" in content[3]["text"]
    assert len(content) == 4


async def test_relative_path_uses_base_dir(root: Path) -> None:
    (root / "w").mkdir()
    (root / "w" / "r.json").write_bytes(b"{}")
    body = await _body(_ctx(["r.json"], base_dir=str(root / "w")), _result())
    assert body["content"][2]["resource"]["uri"] == "file:///r.json"


async def test_name_already_returned_by_server_is_not_appended(root: Path) -> None:
    (root / "a.txt").write_bytes(b"1")
    result = CallToolResult(
        content=[
            EmbeddedResource(
                type="resource",
                resource=TextResourceContents(uri="file:///a.txt", text="1"),  # type: ignore[arg-type]
            )
        ]
    )
    body = await _body(_ctx(["a.txt"]), result)
    assert len(body["content"]) == 2 and "a file named a.txt is already attached" in body["content"][1]["text"]


async def test_budget_returns_to_zero_after_send(root: Path) -> None:
    (root / "a.txt").write_bytes(b"123")
    response = await export.apply(_ctx(["a.txt"]), _result(), {})
    assert export._inflight == 3

    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request"}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await response({"type": "http", "method": "GET"}, receive, send)
    assert export._inflight == 0
    assert sent[0]["status"] == 200


async def test_budget_released_when_send_raises(root: Path) -> None:
    (root / "a.txt").write_bytes(b"123")
    response = await export.apply(_ctx(["a.txt"]), _result(), {})

    async def receive() -> dict[str, Any]:
        return {"type": "http.request"}

    async def send(message: dict[str, Any]) -> None:
        raise ConnectionError("client gone")

    with pytest.raises(ConnectionError):
        await response({"type": "http", "method": "GET"}, receive, send)
    assert export._inflight == 0


async def test_response_construction_failure_falls_back_to_original_result(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (root / "a.txt").write_bytes(b"123")

    class Broken(export.ExportJSONResponse):
        def __init__(self, *a: Any, **k: Any) -> None:
            raise RuntimeError("render failed")

    monkeypatch.setattr(export, "ExportJSONResponse", Broken)
    response = await export.apply(_ctx(["a.txt"]), _result(), {})  # export never loses the tool result
    assert response.body == _today(_result())  # type: ignore[attr-defined]
    assert export._inflight == 0


async def test_collection_failure_falls_back_to_original_result(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a: Any, **k: Any) -> export.Collected:
        raise UnicodeEncodeError("utf-8", "\ud800", 0, 1, "surrogates not allowed")

    monkeypatch.setattr(export, "collect_exports", boom)
    response = await export.apply(_ctx(["\ud800.txt"]), _result(), {})
    assert response.body == _today(_result())  # type: ignore[attr-defined]
    assert export._inflight == 0


async def test_budget_released_when_cancelled_during_collection(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    started, proceed = threading.Event(), threading.Event()

    def slow_collect(*a: Any, **k: Any) -> export.Collected:
        assert export._reserve(7)
        started.set()
        proceed.wait(5)
        return export.Collected(reserved=7)

    monkeypatch.setattr(export, "collect_exports", slow_collect)
    task = asyncio.create_task(export.apply(_ctx(["a.txt"]), _result(), {}))
    while not started.is_set():
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert export._inflight == 7
    proceed.set()
    for _ in range(100):
        if export._inflight == 0:
            break
        await asyncio.sleep(0.01)
    assert export._inflight == 0


async def test_release_when_done_ignores_failed_or_cancelled_future() -> None:
    failed: asyncio.Future[export.Collected] = asyncio.get_running_loop().create_future()
    failed.set_exception(RuntimeError("x"))
    cancelled: asyncio.Future[export.Collected] = asyncio.get_running_loop().create_future()
    cancelled.cancel()
    export._inflight = 5
    export._release_when_done(failed)
    export._release_when_done(cancelled)
    assert export._inflight == 5
    failed.exception()


# --- resource_link items resolved in place (link-only delivery) ---


def _link(path: Path | str) -> ResourceLink:
    return ResourceLink(type="resource_link", name="f", uri=f"file://{path}")  # type: ignore[arg-type]


def _linked(*links: ResourceLink, is_error: bool = False) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text="before"), *links, TextContent(type="text", text="after")],
        isError=is_error,
    )


async def test_link_only_replaced_in_place(root: Path) -> None:
    (root / "a b.csv").write_bytes(b"x,y")
    result = _linked(_link(root / "a%20b.csv"))
    body = await _body(_ctx(None), result)
    content = body["content"]
    assert content[0] == {"type": "text", "text": "before"} and content[2] == {"type": "text", "text": "after"}
    assert content[1]["type"] == "resource"
    assert content[1]["resource"]["uri"] == "file:///a%20b.csv"
    assert content[1]["resource"]["mimeType"] == "text/csv"
    assert base64.b64decode(content[1]["resource"]["blob"]) == b"x,y"
    assert len(content) == 3


async def test_link_refused_becomes_note_in_place(root: Path) -> None:
    result = _linked(_link(root / "missing.txt"))
    response = await export.apply(_ctx([]), result, {})
    assert type(response) is JSONResponse
    content = json.loads(bytes(response.body))["content"]
    assert len(content) == 3 and "missing.txt: file not found" in content[1]["text"]


async def test_error_result_with_link(root: Path) -> None:
    (root / "a.txt").write_bytes(b"1")
    result = _linked(_link(root / "a.txt"), is_error=True)
    response = await export.apply(_ctx(None), result, {})
    assert response.body == _today(result)  # type: ignore[attr-defined]
    body = await _body(_ctx(["a.txt"]), result)
    assert body["content"][:3] == result.model_dump(mode="json", exclude_none=True)["content"]
    assert body["content"][3] == {"type": "text", "text": "export skipped: the call failed"}
    assert len(body["content"]) == 4


@pytest.mark.parametrize("ctx", [_ctx(None, enabled=False), _ctx(None, enabled=False, stdio=False)])
async def test_link_disabled_or_http_not_modified(root: Path, ctx: export.ExportContext) -> None:
    (root / "a.txt").write_bytes(b"1")
    result = _linked(_link(root / "a.txt"))
    response = await export.apply(ctx, result, {})
    assert response.body == _today(result)  # type: ignore[attr-defined]


async def test_link_in_text_supplies_nothing(root: Path) -> None:
    (root / "a.txt").write_bytes(b"1")
    result = CallToolResult(content=[TextContent(type="text", text=f"file://{root / 'a.txt'}")])
    response = await export.apply(_ctx(None), result, {})
    assert response.body == _today(result)  # type: ignore[attr-defined]


async def test_links_over_limit_get_one_note_and_log(
    root: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(export, "MAX_LINKS", 2)
    for n in range(4):
        (root / f"{n}.txt").write_bytes(b"12")
    result = _linked(*(_link(root / f"{n}.txt") for n in range(4)))
    with caplog.at_level("INFO"):
        body = await _body(_ctx(None), result)
    content = body["content"]
    assert [c["type"] for c in content] == ["text", "resource", "resource", "text", "text"]
    assert "exceeds limit of 2 links per call" in content[3]["text"]
    assert content[4] == {"type": "text", "text": "after"}
    assert any("2 from links, 4 bytes" in r.getMessage() for r in caplog.records)


async def test_explicit_and_link(root: Path) -> None:
    (root / "a.txt").write_bytes(b"1")
    (root / "b.txt").write_bytes(b"22")
    result = _linked(_link(root / "b.txt"))
    body = await _body(_ctx(["a.txt", "missing.txt"]), result)
    content = body["content"]
    assert content[0]["text"] == "before" and content[2]["text"] == "after"
    assert content[1]["resource"]["uri"] == "file:///b.txt"
    assert content[3]["resource"]["uri"] == "file:///a.txt"
    assert "Files not exported:\nmissing.txt: file not found" == content[4]["text"]
    assert len(content) == 5


async def test_link_to_explicit_path_is_removed_silently(root: Path) -> None:
    (root / "a.txt").write_bytes(b"1")
    body = await _body(_ctx(["a.txt"]), _linked(_link(root / "a.txt")))
    content = body["content"]
    assert [c["type"] for c in content] == ["text", "text", "resource"]
    assert [content[0]["text"], content[1]["text"]] == ["before", "after"]
    assert content[2]["resource"]["uri"] == "file:///a.txt"


async def test_two_links_to_one_path_give_one_resource_at_first_link(root: Path) -> None:
    (root / "a.txt").write_bytes(b"1")
    body = await _body(_ctx(None), _linked(_link(root / "a.txt"), _link(root / "a.txt")))
    content = body["content"]
    assert [c["type"] for c in content] == ["text", "resource", "text"]
    assert content[1]["resource"]["uri"] == "file:///a.txt"
    assert content[2]["text"] == "after"


async def test_link_with_invalid_request_keeps_note_and_resolves(root: Path) -> None:
    (root / "a.txt").write_bytes(b"1")
    body = await _body(_ctx("a.txt"), _linked(_link(root / "a.txt")))
    content = body["content"]
    assert content[1]["type"] == "resource" and "expected a list" in content[3]["text"]
    assert len(content) == 4


async def test_link_budget_released_when_send_raises(root: Path) -> None:
    (root / "a.txt").write_bytes(b"123")
    response = await export.apply(_ctx(None), _linked(_link(root / "a.txt")), {})
    assert export._inflight == 3

    async def receive() -> dict[str, Any]:
        return {"type": "http.request"}

    async def send(message: dict[str, Any]) -> None:
        raise ConnectionError("client gone")

    with pytest.raises(ConnectionError):
        await response({"type": "http", "method": "GET"}, receive, send)
    assert export._inflight == 0


async def test_link_budget_released_when_cancelled_during_collection(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started, proceed = threading.Event(), threading.Event()
    seen: list[Any] = []

    def slow_collect(*a: Any, **k: Any) -> export.Collected:
        seen.append(k.get("links"))
        assert export._reserve(7)
        started.set()
        proceed.wait(5)
        return export.Collected(reserved=7)

    monkeypatch.setattr(export, "collect_exports", slow_collect)
    export._inflight = 4
    task = asyncio.create_task(export.apply(_ctx(None), _linked(_link(root / "a.txt")), {}))
    for _ in range(100):
        if started.is_set() or task.done():
            break
        await asyncio.sleep(0.01)
    assert started.is_set(), "a link-only result must enter the shielded collect job"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert seen and seen[0]
    proceed.set()
    for _ in range(100):
        if export._inflight == 4:
            break
        await asyncio.sleep(0.01)
    assert export._inflight == 4


async def test_call_without_user_exports_nothing_and_says_why(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    def boom(*a: Any, **k: Any) -> None:
        raise AssertionError("collect_exports must not run")

    monkeypatch.setattr(export, "collect_exports", boom)
    (root / "a.txt").write_text("x")
    body = await _body(_ctx(["a.txt"], root=None), _result())
    assert body["content"][:2] == _result().model_dump(mode="json", exclude_none=True)["content"]
    assert len(body["content"]) == 3 and "no user" in body["content"][2]["text"]


async def test_call_without_user_leaves_links_untouched(root: Path) -> None:
    (root / "a.txt").write_text("x")
    result = _linked(_link(root / "a.txt"))
    response = await export.apply(_ctx(None, root=None), result, {})
    assert response.body == _today(result)  # type: ignore[attr-defined]


async def test_other_users_file_is_refused_and_note_names_own_folder(root: Path) -> None:
    mine, theirs = workspace.user_root("me"), workspace.user_root("them")
    Path(theirs).mkdir()
    (Path(theirs) / "closed_positions_analysis.xlsx").write_bytes(b"PK")
    body = await _body(
        _ctx([f"{theirs}/closed_positions_analysis.xlsx"], root=mine), _linked(_link(Path(theirs) / "x.csv"))
    )
    texts = [c["text"] for c in body["content"] if c["type"] == "text"]
    assert "blob" not in json.dumps(body)
    refused = [t for t in texts if "outside" in t]
    assert len(refused) == 2 and all(
        mine in t and "write the file there again" in t and export.alias() in t for t in refused
    )
    assert Path(mine).is_dir()  # created so the model can write there before it retries
