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

"""EPMCDME-14735: export prepare/strip/tools-list injection and the route hook."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
import pytest
from fastapi.responses import JSONResponse
from mcp.types import ListToolsResult, Tool

from mcp_connect.client import export
from mcp_connect.models.request import BridgeRequestBody
from mcp_connect.server import routes as routes_module
from mcp_connect.utils import workspace

STDIO = "./mock-server"
HTTP = "https://example.com/mcp"


def _req(
    method: str = "tools/call",
    server: str = STDIO,
    env: dict[str, Any] | None = None,
    params: Any = None,
    args: list[str] | None = None,
    single_usage: bool = False,
    user_id: str | None = None,
) -> BridgeRequestBody:
    return BridgeRequestBody(
        user_id=user_id,
        serverPath=server,
        method=method,
        params=params if params is not None else {"name": "t", "arguments": {"a": 1}},
        env=env,
        args=args,
        single_usage=single_usage,
    )


@pytest.mark.parametrize("value", ["true", "1", "yes", "on", "TRUE", True])
def test_switch_true_values(value: Any) -> None:
    _, ctx = export.prepare(_req(env={export.SWITCH_KEY: value}))
    assert ctx.stdio and ctx.enabled


def test_lone_surrogate_user_id_does_not_raise() -> None:
    # CR-002: prepare runs on every /bridge request; a bad user_id must not turn it into a 500
    _, ctx = export.prepare(_req(user_id="\ud800"))
    assert ctx.root is not None and ctx.root.startswith(f"{workspace.SERVER_CWD}/u-")


@pytest.mark.parametrize("env", [{export.SWITCH_KEY: "false"}, {export.SWITCH_KEY: False}, {}, None])
def test_switch_false_values(env: Any) -> None:
    _, ctx = export.prepare(_req(env=env))
    assert not ctx.enabled


@pytest.mark.parametrize("server", [STDIO, HTTP])
def test_switch_stripped_from_env_on_every_transport(server: str) -> None:
    stripped, _ = export.prepare(_req(server=server, env={export.SWITCH_KEY: "true", "K": "v"}))
    assert stripped.env == {"K": "v"}


def test_switch_not_enabled_on_http() -> None:
    _, ctx = export.prepare(_req(server=HTTP, env={export.SWITCH_KEY: "true"}))
    assert not ctx.stdio and not ctx.enabled


@pytest.mark.parametrize("enabled", [True, False])
def test_param_stripped_on_stdio_call(enabled: bool) -> None:
    env = {export.SWITCH_KEY: "true"} if enabled else None
    params = {"name": "t", "arguments": {"a": 1, export.EXPORT_PARAM: ["x.csv"], "cwd": "/home/codemie/ab"}}
    stripped, ctx = export.prepare(_req(env=env, params=params))
    assert stripped.params["arguments"] == {"a": 1, "cwd": "/home/codemie/ab"}
    assert ctx.requested == ["x.csv"]
    assert ctx.base_dir == "/home/codemie/ab"


@pytest.mark.parametrize("server", [HTTP])
def test_param_not_stripped_on_http(server: str) -> None:
    params = {"name": "t", "arguments": {export.EXPORT_PARAM: ["x"]}}
    stripped, ctx = export.prepare(_req(server=server, params=params))
    assert stripped.params == params
    assert ctx.requested is None


def test_base_dir_is_first_absolute_in_tuple_order() -> None:
    args = {"cwd": "rel", "working_directory": "/w", "directory": "/d", export.EXPORT_PARAM: ["a"]}
    _, ctx = export.prepare(_req(params={"name": "t", "arguments": args}))
    assert ctx.base_dir == "/d"


def test_original_request_not_mutated_and_dollar_reaches_handler() -> None:
    req = _req(env={export.SWITCH_KEY: "true", "X": "y"}, args=["$X"])
    stripped, _ = export.prepare(req)
    assert stripped.args == ["$X"]
    assert req.env is not None and export.SWITCH_KEY in req.env


def test_substitution_error_does_not_raise_in_prepare_and_still_strips() -> None:
    params = {"name": "t", "arguments": {export.EXPORT_PARAM: ["x"]}}
    stripped, ctx = export.prepare(_req(env={export.SWITCH_KEY: "true"}, args=["$MISSING"], params=params))
    assert not ctx.enabled
    assert stripped.env == {}
    assert export.EXPORT_PARAM not in stripped.params["arguments"]


async def test_substitution_error_still_raised_by_handler(async_client: httpx.AsyncClient) -> None:
    payload = {
        "serverPath": STDIO,
        "method": "tools/list",
        "params": {},
        "args": ["$MISSING"],
        "env": {export.SWITCH_KEY: "true"},
        "single_usage": True,
    }
    response = await async_client.post("/bridge", json=payload)
    assert response.status_code == 400
    assert "MISSING" in json.dumps(response.json())


def _tools_result() -> ListToolsResult:
    return ListToolsResult(
        tools=[
            Tool(name="a", inputSchema={"type": "object"}),
            Tool(name="b", inputSchema={"type": "object", "properties": {"x": {}}, "required": ["x"]}),
            Tool(
                name="c",
                inputSchema={"type": "object", "properties": {export.EXPORT_PARAM: {"type": "string"}}},
            ),
        ]
    )


def _ctx(stdio: bool = True, enabled: bool = True, method: str = "tools/list") -> export.ExportContext:
    return export.ExportContext(stdio, enabled, method, None, None)


async def test_tools_list_injected_every_tool() -> None:
    response = await export.apply(_ctx(), _tools_result(), {})
    tools = json.loads(bytes(response.body))["tools"]  # type: ignore[attr-defined]
    assert tools[0]["inputSchema"]["properties"][export.EXPORT_PARAM]["type"] == "array"
    assert tools[1]["inputSchema"]["properties"][export.EXPORT_PARAM]["items"] == {"type": "string"}
    assert tools[1]["inputSchema"]["required"] == ["x"]
    assert "required" not in tools[0]["inputSchema"]
    assert tools[2]["inputSchema"]["properties"][export.EXPORT_PARAM] == {"type": "string"}
    desc = tools[0]["inputSchema"]["properties"][export.EXPORT_PARAM]["description"]
    assert "/home/codemie" in desc and "directory/cwd/working_directory" in desc


async def test_tools_list_description_does_not_name_a_users_folder() -> None:
    # the backend caches tools/list across users, so the description must be the same for everyone
    ctx = export.ExportContext(True, True, "tools/list", None, None, "/home/codemie/u-0123456789abcdef")
    response = await export.apply(ctx, _tools_result(), {})
    desc = json.loads(bytes(response.body))["tools"][0]["inputSchema"]["properties"][export.EXPORT_PARAM]["description"]  # type: ignore[attr-defined]
    assert "u-0123456789abcdef" not in desc and "own folder" in desc


def test_prepare_scopes_the_root_to_the_user() -> None:
    _, a = export.prepare(_req(user_id="user-a"))
    _, b = export.prepare(_req(user_id="user-b"))
    _, a2 = export.prepare(_req(user_id=" user-a "))
    assert a.root is not None and a.root.startswith(workspace.SERVER_CWD + "/u-")
    assert len(a.root.rsplit("/", 1)[1]) == 18
    assert a.root != b.root and a.root == a2.root == workspace.user_root("user-a")


def test_prepare_maps_the_export_alias_and_creates_the_folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    # B2 (round 3): the model writes to the caller's folder before it exports, never via the shared root
    monkeypatch.setattr(workspace, "SERVER_CWD", str(tmp_path))
    a = export.alias()
    args = {
        "command": f"mkdir -p {a} && python gen.py > {a}/r.xlsx; cd {a}",
        "opts": [{"out": f"{a}/sub/r.csv"}, 3],
        "directory": a,
        export.EXPORT_PARAM: [f"{a}/r.xlsx"],
    }
    stripped, ctx = export.prepare(
        _req(env={export.SWITCH_KEY: "true"}, params={"name": "t", "arguments": args}, user_id="u")
    )
    root = workspace.user_root("u")
    assert root is not None and os.path.isdir(root)
    assert stripped.params["arguments"] == {
        "command": f"mkdir -p {root} && python gen.py > {root}/r.xlsx; cd {root}",
        "opts": [{"out": f"{root}/sub/r.csv"}, 3],
        "directory": root,
    }
    assert ctx.requested == [f"{root}/r.xlsx"] and ctx.base_dir == root


@pytest.mark.parametrize("suffix", ["_dir/r.csv", "2/r.csv", ".bak", "-old"])
def test_prepare_maps_only_the_whole_alias_component(
    suffix: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    monkeypatch.setattr(workspace, "SERVER_CWD", str(tmp_path))
    args = {"path": export.alias() + suffix}
    stripped, _ = export.prepare(
        _req(env={export.SWITCH_KEY: "true"}, params={"name": "t", "arguments": dict(args)}, user_id="u")
    )
    assert stripped.params["arguments"] == args


@pytest.mark.parametrize(("enabled", "user_id"), [(False, "u"), (True, None)])
def test_prepare_leaves_the_alias_without_opt_in_or_user(
    enabled: bool, user_id: str | None, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    monkeypatch.setattr(workspace, "SERVER_CWD", str(tmp_path))
    args = {"command": f"ls {export.alias()}"}
    env = {export.SWITCH_KEY: "true"} if enabled else None
    stripped, _ = export.prepare(_req(env=env, params={"name": "t", "arguments": dict(args)}, user_id=user_id))
    assert stripped.params["arguments"] == args
    assert list(tmp_path.iterdir()) == []  # no folder created


def test_prepare_creates_no_folder_without_the_alias(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    monkeypatch.setattr(workspace, "SERVER_CWD", str(tmp_path))
    export.prepare(_req(env={export.SWITCH_KEY: "true"}, user_id="u"))
    assert list(tmp_path.iterdir()) == []


def test_tools_list_description_names_the_alias_not_a_placeholder() -> None:
    desc = export._param_schema()["description"]
    assert export.alias() + "/report.xlsx" in desc and "{" not in desc


def test_prepare_scopes_the_root_to_the_conversation() -> None:
    # round-3 re-run: one folder per user let a conversation receive an earlier conversation's same-named file
    def root(**kw: Any) -> str | None:
        req = _req(user_id="u").model_copy(update=kw)
        return export.prepare(req)[1].root

    a, b = root(conversation_id="c1"), root(conversation_id="c2")
    assert a == workspace.user_root("u", "c1") and a != b
    assert root(workflow_execution_id="w1") == workspace.user_root("u", "w1")
    assert root(conversation_id="c1", workflow_execution_id="w1") == a
    assert root() == workspace.user_root("u")


def test_bridge_accepts_conversation_id() -> None:
    assert BridgeRequestBody(serverPath="x", method="ping", params={}, conversation_id="c1").conversation_id == "c1"


@pytest.mark.parametrize("user_id", [None, "", "   "])
def test_prepare_without_user_has_no_root(user_id: str | None) -> None:
    _, ctx = export.prepare(_req(user_id=user_id))
    assert ctx.root is None


async def test_route_skips_export_module_when_not_opted_in(
    async_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_handler(request: BridgeRequestBody, timeout_ms: int) -> Any:
        return _tools_result()

    async def boom(*a: Any, **k: Any) -> None:
        raise AssertionError("export.apply must not run")

    monkeypatch.setattr(routes_module, "_handle_cached_client_request", fake_handler)
    monkeypatch.setattr(export, "apply", boom)
    response = await async_client.post("/bridge", json={"serverPath": STDIO, "method": "tools/list", "params": {}})
    assert response.status_code == 200
    assert export.EXPORT_PARAM not in response.json()["tools"][0]["inputSchema"].get("properties", {})


@pytest.mark.parametrize("ctx", [_ctx(enabled=False), _ctx(stdio=False, enabled=False)])
async def test_tools_list_unchanged_when_disabled_or_http(ctx: export.ExportContext) -> None:
    result = _tools_result()
    expected = JSONResponse(content=result.model_dump(mode="json", exclude_none=True), status_code=200, headers={})
    response = await export.apply(ctx, result, {})
    assert response.body == expected.body  # type: ignore[attr-defined]


async def test_route_hands_prepared_request_to_handler(
    async_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[BridgeRequestBody] = []

    async def fake_handler(request: BridgeRequestBody, timeout_ms: int) -> Any:
        seen.append(request)
        return _tools_result()

    monkeypatch.setattr(routes_module, "_handle_cached_client_request", fake_handler)
    payload = {"serverPath": STDIO, "method": "tools/list", "params": {}, "env": {export.SWITCH_KEY: "true"}}
    response = await async_client.post("/bridge", json=payload)

    assert response.status_code == 200
    assert seen[0].env == {}
    assert export.EXPORT_PARAM in response.json()["tools"][0]["inputSchema"]["properties"]
