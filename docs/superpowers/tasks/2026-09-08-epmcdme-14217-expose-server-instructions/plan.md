# EPMCDME-14217 — Expose MCP server instructions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture the `instructions` field an MCP server returns in its `InitializeResult` handshake and expose it on the `/bridge` `tools/list` response, so the CodeMie backend can inject it into the assistant system prompt.

**Architecture:** `session.initialize()` returns an `InitializeResult` whose value is currently discarded at all seven call sites. Capture it at each site. On the managed (pooled) path, carry the value out of the lifecycle task in a new `SessionHandshake` dataclass and store it as a defaulted field on `ManagedClient`, where it inherits session lifetime and cache residency. On the single-usage path, the value is local to the request. Both paths then call one shared helper that attaches `instructions` to the result of `tools/list` only, so the two paths emit identical JSON.

**Tech Stack:** Python 3.12, FastAPI, `mcp` SDK pinned at 1.28.1, pydantic v2, pytest 8.4.2 with `asyncio_mode = "auto"`, poetry, mypy `--strict`.

## Global Constraints

- Branch: `EPMCDME-14217_expose-server-instructions`. Commit format: `EPMCDME-14217: <imperative description>`.
- Python 3.12 built-in generics only — `str | None`, never `typing.Optional`.
- Every function fully annotated. `mypy --strict` must stay clean; `mcp.*` is `ignore_missing_imports`, so types coming from the SDK need explicit annotations.
- All I/O async. Logging via `utils/logger.py`. No new dependency may be added (AGENTS.md "Ask first").
- The `/bridge` response change is **additive only**: a server with no instructions produces no `instructions` key. Approved with the ticket; the MR description must state the schema change explicitly.
- `instructions` rides **every page** of a paginated `tools/list`, not only the first (decision recorded in `decisions.jsonl`).
- The JSON key is exactly `instructions`, top level of the `tools/list` result body. The paired CodeMie backend MR depends on this exact name and nesting.
- `ManagedClient` is constructed positionally at `managed.py:127` — any new field must be defaulted and last.
- Never attach the field to any result other than `tools/list`. `EmptyResult`, ping results and others share the same `extra="allow"` base.
- Verified empirically before planning: `ListToolsResult(tools=[]).instructions = "x"` survives `model_dump(mode="json", exclude_none=True)`, and an unset field is absent from the dump. This is the mechanism the whole change rests on.

---

### Task 1: Handshake value object and the attach helper

**Files:**
- Create: `src/mcp_connect/client/instructions.py`
- Test: `tests/test_instructions.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `SessionHandshake` — frozen dataclass with `session: ClientSession` and `instructions: str | None`.
  - `extract_instructions(init_result: Any) -> str | None`
  - `attach_server_instructions(result: Any, method: str, instructions: str | None) -> Any`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for MCP server instruction capture and attachment."""

from __future__ import annotations

from typing import Any

from mcp.types import EmptyResult, ListToolsResult

from mcp_connect.client.instructions import (
    SessionHandshake,
    attach_server_instructions,
    extract_instructions,
)


class _NoInstructions:
    """Stand-in for an SDK result that predates the instructions field."""


def test_extract_instructions_reads_the_field() -> None:
    class _Init:
        instructions = "Call with sysparm_help=true first."

    assert extract_instructions(_Init()) == "Call with sysparm_help=true first."


def test_extract_instructions_returns_none_when_absent() -> None:
    assert extract_instructions(_NoInstructions()) is None
    assert extract_instructions(None) is None


def test_attach_adds_field_to_pydantic_tools_list_result() -> None:
    result = ListToolsResult(tools=[])

    attached = attach_server_instructions(result, "tools/list", "read me first")

    assert attached.model_dump(mode="json", exclude_none=True) == {
        "tools": [],
        "instructions": "read me first",
    }


def test_attach_adds_field_to_plain_dict_result() -> None:
    result: dict[str, Any] = {"tools": []}

    attached = attach_server_instructions(result, "tools/list", "read me first")

    assert attached == {"tools": [], "instructions": "read me first"}
    assert result == {"tools": []}, "input dict must not be mutated"


def test_attach_is_a_noop_without_instructions() -> None:
    result = ListToolsResult(tools=[])

    attached = attach_server_instructions(result, "tools/list", None)

    assert attached.model_dump(mode="json", exclude_none=True) == {"tools": []}


def test_attach_is_a_noop_for_other_methods() -> None:
    result = EmptyResult()

    attached = attach_server_instructions(result, "ping", "read me first")

    assert attached.model_dump(mode="json", exclude_none=True) == {}


def test_attach_tolerates_whitespace_around_the_method_name() -> None:
    result: dict[str, Any] = {"tools": []}

    attached = attach_server_instructions(result, " tools/list ", "read me first")

    assert attached == {"tools": [], "instructions": "read me first"}


def test_attach_leaves_unknown_result_types_alone() -> None:
    sentinel = _NoInstructions()

    assert attach_server_instructions(sentinel, "tools/list", "read me first") is sentinel


def test_session_handshake_carries_both_values() -> None:
    handshake = SessionHandshake(session="fake-session", instructions="read me first")

    assert handshake.session == "fake-session"
    assert handshake.instructions == "read me first"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_instructions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mcp_connect.client.instructions'`

- [ ] **Step 3: Write minimal implementation**

```python
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

"""Capture and expose MCP server-side instructions (EPMCDME-14217).

An MCP server may return an ``instructions`` string in its ``initialize``
handshake, describing how its tools are meant to be used. The MCP SDK returns
that value from ``ClientSession.initialize()`` and then keeps nothing, so it has
to be captured at the call site. This module holds the value object used to
carry it out of the managed client's lifecycle task, and the single helper both
the managed and single-usage paths use to attach it to a ``tools/list``
response.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mcp import ClientSession

from ..utils.logger import get_logger

logger = get_logger(__name__)

TOOLS_LIST_METHOD = "tools/list"


@dataclass(frozen=True)
class SessionHandshake:
    """An initialized session plus what its handshake disclosed.

    Attributes:
        session: The initialized MCP ClientSession.
        instructions: Server-side usage instructions, or None when the server
            sends none.
    """

    session: ClientSession
    instructions: str | None


def extract_instructions(init_result: Any) -> str | None:
    """Read the instructions field off an InitializeResult.

    Args:
        init_result: The value returned by ``ClientSession.initialize()``.

    Returns:
        The instructions string, or None when the server sent none or the
        result carries no such field.
    """
    instructions = getattr(init_result, "instructions", None)
    return instructions if isinstance(instructions, str) else None


def attach_server_instructions(result: Any, method: str, instructions: str | None) -> Any:
    """Attach server instructions to a tools/list result.

    Every other method is returned untouched: the SDK's Result base class allows
    extra fields, so an unguarded attach would leak the key onto ping and other
    responses.

    Args:
        result: The raw result of the MCP method call.
        method: The MCP method that produced the result.
        instructions: Instructions captured at handshake, or None.

    Returns:
        The result, with ``instructions`` attached when there is something to
        attach. Dict results are copied rather than mutated.
    """
    if instructions is None or method.strip() != TOOLS_LIST_METHOD:
        return result

    if isinstance(result, dict):
        return {**result, "instructions": instructions}

    if hasattr(result, "model_dump"):
        result.instructions = instructions
        logger.debug("Attached server instructions to tools/list response")
        return result

    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_instructions.py -v`
Expected: PASS — 9 passed

- [ ] **Step 5: Commit**

```bash
git add src/mcp_connect/client/instructions.py tests/test_instructions.py
git commit -m "EPMCDME-14217: Add server-instruction value object and attach helper"
```

**Test-first: yes** — `tests/test_instructions.py` fails on a missing module before the helper exists.

---

### Task 2: Capture the handshake on the managed (cached) path

**Files:**
- Modify: `src/mcp_connect/client/managed.py` — dataclass fields (`:70-77`), `spawn` (`:78-129`), `_run_client_lifecycle` (`:165-224`), and the three transport bodies (`:225-328`)
- Test: `tests/test_managed_instructions.py`

**Interfaces:**
- Consumes: `SessionHandshake`, `extract_instructions` from Task 1.
- Produces: `ManagedClient.instructions: str | None` — defaulted, declared last. `ready_future` is retyped from `asyncio.Future[ClientSession]` to `asyncio.Future[SessionHandshake]` at all six declaration sites (`managed.py:76, 96, 169, 230, 267, 299`).

- [ ] **Step 1: Write the failing test**

```python
"""The managed client keeps what the handshake disclosed (EPMCDME-14217)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from mcp_connect.client.managed import ManagedClient
from mcp_connect.models.request import BridgeRequestBody


class _InitResult:
    def __init__(self, instructions: str | None) -> None:
        self.instructions = instructions


class _DummySession:
    """Minimal stand-in for ClientSession over a fake transport."""

    def __init__(self, read: Any, write: Any, client_info: Any = None) -> None:
        self.initialize = AsyncMock(return_value=_InitResult("read me first"))

    async def __aenter__(self) -> _DummySession:
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None


class _DummyTransport:
    async def __aenter__(self) -> tuple[str, str]:
        return ("read", "write")

    async def __aexit__(self, *_: Any) -> None:
        return None


@pytest.fixture
def http_request() -> BridgeRequestBody:
    return BridgeRequestBody(serverPath="https://example.test/mcp", method="tools/list")


async def test_ready_future_carries_the_handshake(monkeypatch: pytest.MonkeyPatch, http_request: BridgeRequestBody) -> None:
    monkeypatch.setattr("mcp_connect.client.managed.ClientSession", _DummySession)
    monkeypatch.setattr("mcp_connect.client.transports.get_transport_ctx", lambda *_a, **_k: _DummyTransport())

    cleanup_event = asyncio.Event()
    ready_future: asyncio.Future[Any] = asyncio.Future()

    task = asyncio.create_task(
        ManagedClient._run_streamable_http_client(http_request, cleanup_event, ready_future)
    )
    handshake = await asyncio.wait_for(asyncio.shield(ready_future), 5.0)

    assert handshake.instructions == "read me first"
    assert isinstance(handshake.session, _DummySession)

    cleanup_event.set()
    await asyncio.wait_for(task, 5.0)


async def test_spawn_stores_instructions_on_the_client(monkeypatch: pytest.MonkeyPatch, http_request: BridgeRequestBody) -> None:
    monkeypatch.setattr("mcp_connect.client.managed.ClientSession", _DummySession)
    monkeypatch.setattr("mcp_connect.client.transports.get_transport_ctx", lambda *_a, **_k: _DummyTransport())

    client = await ManagedClient.spawn(http_request)

    assert client.instructions == "read me first"
    assert isinstance(client.session, _DummySession)

    await client.cleanup()


async def test_instructions_are_none_when_the_server_sends_none(
    monkeypatch: pytest.MonkeyPatch, http_request: BridgeRequestBody
) -> None:
    class _SilentSession(_DummySession):
        def __init__(self, read: Any, write: Any, client_info: Any = None) -> None:
            self.initialize = AsyncMock(return_value=_InitResult(None))

    monkeypatch.setattr("mcp_connect.client.managed.ClientSession", _SilentSession)
    monkeypatch.setattr("mcp_connect.client.transports.get_transport_ctx", lambda *_a, **_k: _DummyTransport())

    client = await ManagedClient.spawn(http_request)

    assert client.instructions is None

    await client.cleanup()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_managed_instructions.py -v`
Expected: FAIL — `AttributeError: 'ManagedClient' object has no attribute 'instructions'`, and the handshake assertion fails because `ready_future` still resolves to a bare session.

- [ ] **Step 3: Write minimal implementation**

In `src/mcp_connect/client/managed.py`, add the import:

```python
from .instructions import SessionHandshake, extract_instructions
```

Retype the future and add the field on the dataclass:

```python
    # Public interface
    session: ClientSession  # For making MCP calls

    # Internal state
    _cleanup_event: asyncio.Event  # Signal to exit contexts
    _task: asyncio.Task[None]  # Dedicated task running contexts
    _ready_future: asyncio.Future[SessionHandshake]  # Signals initialization complete

    # Captured at handshake (EPMCDME-14217); None when the server sends none
    instructions: str | None = None
```

In `spawn`:

```python
        cleanup_event = asyncio.Event()
        ready_future: asyncio.Future[SessionHandshake] = asyncio.Future()
```

```python
            handshake = await asyncio.wait_for(ready_future, timeout=30.0)
```

```python
        return cls(
            session=handshake.session,
            _cleanup_event=cleanup_event,
            _task=task,
            _ready_future=ready_future,
            instructions=handshake.instructions,
        )
```

In `_run_client_lifecycle` and each of `_run_stdio_client`, `_run_streamable_http_client`, `_run_sse_client`, change the parameter annotation:

```python
        ready_future: asyncio.Future[SessionHandshake],
```

In each of the three transport bodies, replace the discarded initialize and the ready signal:

```python
                # Initialize session, keeping what the handshake disclosed
                init_result = await asyncio.wait_for(session.initialize(), timeout=INIT_TIMEOUT_SECONDS)

                # Signal ready - caller can now use session
                ready_future.set_result(
                    SessionHandshake(session=session, instructions=extract_instructions(init_result))
                )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_managed_instructions.py -v`
Expected: PASS — 3 passed

- [ ] **Step 5: Repair the existing managed-path tests**

These drive the statics directly and await a bare session on `ready_future`. Update each to unpack the handshake:

Run: `poetry run pytest tests/test_user_agent_header.py tests/test_client_name.py tests/test_managed_lifecycle_errors.py -v`
Expected before the edit: FAIL on assertions that treat the future's value as a session.
Fix: in those tests replace `session = await asyncio.wait_for(asyncio.shield(ready_future), 5.0)` with `handshake = await asyncio.wait_for(asyncio.shield(ready_future), 5.0)` plus `session = handshake.session`, and make every fake `initialize()` return an object with an `instructions` attribute (`AsyncMock(return_value=_InitResult(None))`) instead of `None`.
Expected after the edit: PASS

- [ ] **Step 6: Commit**

```bash
git add src/mcp_connect/client/managed.py tests/test_managed_instructions.py tests/test_user_agent_header.py tests/test_client_name.py tests/test_managed_lifecycle_errors.py
git commit -m "EPMCDME-14217: Capture handshake instructions on the managed client"
```

**Test-first: yes** — `test_spawn_stores_instructions_on_the_client` fails with `AttributeError` before the field exists.

---

### Task 3: Serve the captured instructions on the cached `/bridge` path

**Files:**
- Modify: `src/mcp_connect/server/routes.py` — `_handle_cached_client_request` (`:160-238`, the handle is already bound and ignored at `:179`)
- Test: `tests/test_bridge_instructions.py`

**Interfaces:**
- Consumes: `ManagedClient.instructions` from Task 2, `attach_server_instructions` from Task 1.
- Produces: `/bridge` `tools/list` responses carrying a top-level `instructions` key when the upstream server sent one.

- [ ] **Step 1: Write the failing test**

```python
"""The /bridge tools/list response carries server instructions (EPMCDME-14217)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from mcp_connect.main import app


@pytest.fixture
async def async_client() -> Any:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


def _session_returning(tools_payload: dict[str, Any]) -> MagicMock:
    session = MagicMock()
    session.list_tools = AsyncMock(return_value=tools_payload)
    return session


async def test_tools_list_includes_instructions_from_the_cached_client(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    handle = MagicMock()
    handle.instructions = "Call with sysparm_help=true first."
    session = _session_returning({"tools": []})
    monkeypatch.setattr(
        "mcp_connect.server.routes.get_or_create_client",
        AsyncMock(return_value=(handle, session)),
    )

    response = await async_client.post(
        "/bridge",
        json={"serverPath": "https://example.test/mcp", "method": "tools/list"},
    )

    assert response.status_code == 200
    assert response.json() == {"tools": [], "instructions": "Call with sysparm_help=true first."}


async def test_tools_list_omits_instructions_when_the_server_sends_none(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    handle = MagicMock()
    handle.instructions = None
    session = _session_returning({"tools": []})
    monkeypatch.setattr(
        "mcp_connect.server.routes.get_or_create_client",
        AsyncMock(return_value=(handle, session)),
    )

    response = await async_client.post(
        "/bridge",
        json={"serverPath": "https://example.test/mcp", "method": "tools/list"},
    )

    assert response.json() == {"tools": []}


async def test_other_methods_never_receive_instructions(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    handle = MagicMock()
    handle.instructions = "Call with sysparm_help=true first."
    session = MagicMock()
    session.send_ping = AsyncMock(return_value={"result": "ping"})
    monkeypatch.setattr(
        "mcp_connect.server.routes.get_or_create_client",
        AsyncMock(return_value=(handle, session)),
    )

    response = await async_client.post(
        "/bridge",
        json={"serverPath": "https://example.test/mcp", "method": "ping"},
    )

    assert response.json() == {"result": "ping"}


async def test_instructions_ride_every_page_of_a_paginated_listing(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    handle = MagicMock()
    handle.instructions = "Call with sysparm_help=true first."
    session = _session_returning({"tools": [], "nextCursor": "page-3"})
    monkeypatch.setattr(
        "mcp_connect.server.routes.get_or_create_client",
        AsyncMock(return_value=(handle, session)),
    )

    response = await async_client.post(
        "/bridge",
        json={"serverPath": "https://example.test/mcp", "method": "tools/list", "params": {"cursor": "page-2"}},
    )

    body = response.json()
    assert body["instructions"] == "Call with sysparm_help=true first."
    assert body["nextCursor"] == "page-3"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_bridge_instructions.py -v`
Expected: FAIL — three of four tests fail with `assert {'tools': []} == {'tools': [], 'instructions': ...}`; the `ping` and the `None` cases already pass.

- [ ] **Step 3: Write minimal implementation**

In `src/mcp_connect/server/routes.py`, add the import:

```python
from ..client.instructions import attach_server_instructions
```

At the end of `_handle_cached_client_request`, where the result is returned, wrap it:

```python
    result = await invoke_with_timeout(session, request.method, request.params, timeout_ms)
    return attach_server_instructions(result, request.method, handle.instructions)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_bridge_instructions.py -v`
Expected: PASS — 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/mcp_connect/server/routes.py tests/test_bridge_instructions.py
git commit -m "EPMCDME-14217: Return server instructions on cached tools/list responses"
```

**Test-first: yes** — the response body assertion fails before the attach call exists.

---

### Task 4: Same behavior on the single-usage path

**Files:**
- Modify: `src/mcp_connect/client/single_usage.py` — `_execute_stdio_request` (`:114-195`), `_execute_http_request` (`:197-260`), `_execute_sse_request` (`:262-330`)
- Test: `tests/test_single_usage_instructions.py`

**Interfaces:**
- Consumes: `extract_instructions`, `attach_server_instructions` from Task 1.
- Produces: identical JSON to the cached path — a client must not see a different shape depending on the `single_usage` flag.

- [ ] **Step 1: Write the failing test**

```python
"""Single-usage requests expose server instructions too (EPMCDME-14217)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from mcp_connect.client.single_usage import execute_single_usage_request
from mcp_connect.models.request import BridgeRequestBody


class _InitResult:
    def __init__(self, instructions: str | None) -> None:
        self.instructions = instructions


class _DummySession:
    def __init__(self, read: Any, write: Any, client_info: Any = None) -> None:
        self.initialize = AsyncMock(return_value=_InitResult("read me first"))
        self.list_tools = AsyncMock(return_value={"tools": []})
        self.send_ping = AsyncMock(return_value={"result": "ping"})

    async def __aenter__(self) -> _DummySession:
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None


class _DummyTransport:
    async def __aenter__(self) -> tuple[str, str]:
        return ("read", "write")

    async def __aexit__(self, *_: Any) -> None:
        return None


@pytest.fixture(autouse=True)
def _fake_http_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("mcp_connect.client.single_usage.ClientSession", _DummySession)
    monkeypatch.setattr("mcp_connect.client.transports.get_transport_ctx", lambda *_a, **_k: _DummyTransport())


async def test_single_usage_tools_list_carries_instructions() -> None:
    request = BridgeRequestBody(serverPath="https://example.test/mcp", method="tools/list", single_usage=True)

    result = await execute_single_usage_request(request, "tools/list", {}, 5000)

    assert result == {"tools": [], "instructions": "read me first"}


async def test_single_usage_ping_is_untouched() -> None:
    request = BridgeRequestBody(serverPath="https://example.test/mcp", method="ping", single_usage=True)

    result = await execute_single_usage_request(request, "ping", {}, 5000)

    assert result == {"result": "ping"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_single_usage_instructions.py -v`
Expected: FAIL — `assert {'tools': []} == {'tools': [], 'instructions': 'read me first'}`

- [ ] **Step 3: Write minimal implementation**

In `src/mcp_connect/client/single_usage.py`, add the import:

```python
from .instructions import attach_server_instructions, extract_instructions
```

In each of the three transport helpers, capture the handshake and attach before returning:

```python
                # Initialize with timeout, keeping what the handshake disclosed
                init_result = await asyncio.wait_for(session.initialize(), timeout=INIT_TIMEOUT_SECONDS)

                # Import method invocation utility
                from .methods import invoke_mcp_method

                # Execute method with timeout
                result = await asyncio.wait_for(
                    invoke_mcp_method(session, method, params),
                    timeout=timeout_sec,
                )

                return attach_server_instructions(result, method, extract_instructions(init_result))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_single_usage_instructions.py -v`
Expected: PASS — 2 passed

- [ ] **Step 5: Repair the existing single-usage fakes**

`tests/test_single_usage.py:46` `DummySession.initialize` returns `None`, which `extract_instructions` must tolerate — confirm rather than assume.

Run: `poetry run pytest tests/test_single_usage.py tests/test_bridge_validation.py tests/test_timeout.py tests/test_mcp_methods.py -v`
Expected: PASS unchanged. If any route test asserts exact dict-equality on a `tools/list` body and now sees an extra key, that means a fake started returning instructions — update that fake, not the assertion.

- [ ] **Step 6: Commit**

```bash
git add src/mcp_connect/client/single_usage.py tests/test_single_usage_instructions.py
git commit -m "EPMCDME-14217: Return server instructions on single-usage tools/list responses"
```

**Test-first: yes** — `test_single_usage_tools_list_carries_instructions` fails on the missing key.

---

### Task 5: Integration test against a real MCP server

**Files:**
- Create: `tests/integration/test_real_server_instructions.py`
- Test: the same file

**Interfaces:**
- Consumes: the full stack from Tasks 1-4.
- Produces: the only coverage that validates the change against real SDK types rather than hand-rolled fakes. `tests/integration/` is an empty scaffold today; `addopts = "-m 'not integration'"` keeps it out of the default run.

- [ ] **Step 1: Write the failing test**

```python
"""End-to-end check against a real MCP server declaring instructions (EPMCDME-14217)."""

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
                "single_usage": True,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["instructions"] == SERVER_INSTRUCTIONS
    assert [tool["name"] for tool in body["tools"]] == ["echo"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/integration/test_real_server_instructions.py -m integration -v`
Expected: FAIL before Tasks 1-4 are in place (`KeyError: 'instructions'`). Run it after them to confirm the real handshake is genuinely covered.

- [ ] **Step 3: Write minimal implementation**

No source change. If the test fails after Tasks 1-4, the capture is wrong on a real handshake — fix the source, never the assertion.

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/integration/test_real_server_instructions.py -m integration -v`
Expected: PASS — 1 passed

Then confirm the default run still excludes it:

Run: `poetry run pytest -q`
Expected: the integration test is deselected; every other test passes.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_real_server_instructions.py
git commit -m "EPMCDME-14217: Add integration coverage for real server instructions"
```

**Test-first: yes** — the assertion on `body["instructions"]` fails against the unpatched stack.

---

### Task 6: Document the response-schema addition

**Files:**
- Modify: `README.md` — the `/bridge` response section
- Modify: `docs/superpowers/tasks/2026-09-08-epmcdme-14217-expose-server-instructions/decisions.jsonl` (append; created by the SDLC gates)

**Interfaces:**
- Consumes: the shipped behavior from Tasks 1-5.
- Produces: the written contract the paired CodeMie backend MR reads.

- [ ] **Step 1: Add the README section**

Under the `/bridge` response documentation, add:

```markdown
#### Server instructions on `tools/list`

An MCP server may return an `instructions` string in its `initialize` handshake,
describing how its tools are meant to be used. For the `tools/list` method the
bridge attaches that string to the response as a top-level `instructions` field:

```json
{
  "tools": [{ "name": "echo", "description": "Echo the given text." }],
  "instructions": "Always call the tool with sysparm_help=true before first use."
}
```

The field is additive and optional. A server that sends no instructions produces
a response with no `instructions` key, exactly as before. Instructions are
attached to every page of a paginated `tools/list`, and to no other method.
```

- [ ] **Step 2: Verify the documented shape matches the tests**

Run: `poetry run pytest tests/test_instructions.py tests/test_bridge_instructions.py -q`
Expected: PASS — the documented JSON is the shape those tests assert.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "EPMCDME-14217: Document the instructions field on tools/list responses"
```

**Test-first: no** — documentation only; the behavior it describes is already covered by Tasks 1-5.

---

### Task 7: Run the manual quality gates

**Files:**
- No source change.

**Interfaces:**
- Consumes: everything above. There is no CI in this repository — every gate in `.ai-run/guides/quality-gates.md` is manual, so a skipped gate ships.

- [ ] **Step 1: Full test suite**

Run: `poetry run pytest`
Expected: PASS, no regressions against the pre-change baseline.

- [ ] **Step 2: Type checking**

Run: `poetry run mypy --strict src`
Expected: no errors. `InitializeResult` is untyped to mypy (`ignore_missing_imports` for `mcp.*`), so `extract_instructions` taking `Any` and returning `str | None` is the boundary that keeps strict mode clean.

- [ ] **Step 3: Lint and format**

Run: `poetry run ruff check src tests && poetry run ruff format --check src tests`
Expected: clean.

- [ ] **Step 4: Secret scan**

Run: `make gitleaks`
Expected: no findings.

- [ ] **Step 5: Commit any fixes**

```bash
git add -A
git commit -m "EPMCDME-14217: Fix quality gate findings"
```

**Test-first: no** — verification only.

---

## Self-Review

**Spec coverage.** Capture at the handshake — Task 2 (managed) and Task 4 (single-usage), covering all seven call sites. Store next to the session — Task 2, `ManagedClient.instructions`, defaulted and last, so the positional construction at `managed.py:127` keeps working, and cached entries carry it for free. Return on `tools/list` — Tasks 3 and 4 through one shared helper, so both paths emit identical JSON. Backward compatibility — Task 1's `test_attach_is_a_noop_without_instructions` plus Task 3's `test_tools_list_omits_instructions_when_the_server_sends_none`. Every page of a paginated listing — Task 3's `test_instructions_ride_every_page_of_a_paginated_listing`; the helper keys off the method alone and never inspects the cursor. No leakage onto other methods — `test_other_methods_never_receive_instructions` and `test_attach_is_a_noop_for_other_methods`.

**Deliberately not done.** `MCPClientHandle` (`client/types.py:33`) is left alone: its name invites the change but it is dead in both live paths, so a field there would review well and do nothing. No sanitizing or length-capping of the instruction text happens here — the bridge is a transport and must not silently alter payloads; that guard belongs in the consuming backend MR, before the text reaches a system prompt.

**Placeholder scan.** Every code step carries the real code; every run step carries the real command and its expected output. No TBDs.

**Type consistency.** `SessionHandshake(session, instructions)`, `extract_instructions(init_result) -> str | None`, and `attach_server_instructions(result, method, instructions) -> Any` are defined in Task 1 and used with those exact names and argument orders in Tasks 2, 3 and 4. `ready_future` is `asyncio.Future[SessionHandshake]` in every one of the six sites Task 2 lists.

**Known risk not eliminated.** Task 2 retypes `ready_future` across six sites and three transport bodies. Miss one and `spawn` does not fail loudly — it hangs until the hardcoded 30-second timeout at `managed.py:103`. Step 5 of that task exists precisely to catch it, since the existing managed-path tests await that future directly.
