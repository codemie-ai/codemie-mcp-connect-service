# User-Agent Header from MCP_CLIENT_NAME Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every HTTP request the MCP client sends to HTTP MCP servers (streamable-http, SSE, SigV4-signed streamable-http) carries a `User-Agent` header set to the value of `MCP_CLIENT_NAME` (default `"mcp-bridge"`), always overriding any caller-supplied value.

**Architecture:** One pure helper function `apply_user_agent_header()` in `client_info.py` builds the final headers dict (strips any case-variant of an existing `User-Agent` key, then sets the canonical key from the same env-var read `get_client_info()` already performs). It is wired in at the 4 existing call sites that build the `headers` dict before invoking a transport (`managed.py` x2, `single_usage.py` x2). `transports.py`'s internal dead fallback branch and the pre-existing SSE call-site duplication are left untouched — out of scope.

**Tech Stack:** Python 3.12, MCP Python SDK (`mcp.client.sse`, `mcp.client.streamable_http`), httpx (via SDK transports), pytest + pytest-asyncio, `unittest.mock`.

## Global Constraints

- stdio transport is out of scope (no HTTP headers).
- `MCP_CLIENT_NAME`-derived value always wins over any caller-supplied `User-Agent`/`user-agent` in `request.mcp_headers` — no merge, no duplicate header key.
- No refactor of the pre-existing SSE call-site duplication or of `transports.py`'s dead `headers or (request.mcp_headers or {})` fallback — keep the diff surgical.
- Reuse `get_client_info()`'s existing env-var read and default (`"mcp-bridge"`) — do not add a second `os.getenv("MCP_CLIENT_NAME", ...)` call site.
- All new/modified functions keep full type hints (mypy strict).

---

### Task 1: Add `apply_user_agent_header()` helper to `client_info.py`

**Files:**
- Modify: `src/mcp_connect/client/client_info.py`
- Test: `tests/test_user_agent_header.py` (new file)

**Interfaces:**
- Consumes: `get_client_info() -> Implementation` (already exists in this file; `.name` attribute holds the `MCP_CLIENT_NAME`-derived value).
- Produces: `apply_user_agent_header(headers: dict[str, str] | None) -> dict[str, str]` — used by Task 2 and Task 3.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_user_agent_header.py
"""Tests for injecting MCP_CLIENT_NAME into the User-Agent HTTP header."""

from __future__ import annotations

import pytest


class TestApplyUserAgentHeader:
    """Test apply_user_agent_header() merge/override semantics."""

    def test_default_env_value_when_no_existing_headers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With no MCP_CLIENT_NAME set and no existing headers, User-Agent defaults to 'mcp-bridge'."""
        monkeypatch.delenv("MCP_CLIENT_NAME", raising=False)
        from src.mcp_connect.client.client_info import apply_user_agent_header

        result = apply_user_agent_header(None)

        assert result == {"User-Agent": "mcp-bridge"}

    def test_custom_env_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With MCP_CLIENT_NAME set, User-Agent uses that value."""
        monkeypatch.setenv("MCP_CLIENT_NAME", "codemie-client")
        from src.mcp_connect.client.client_info import apply_user_agent_header

        result = apply_user_agent_header({})

        assert result == {"User-Agent": "codemie-client"}

    def test_overrides_existing_user_agent_exact_case(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A caller-supplied 'User-Agent' value is replaced, not preserved."""
        monkeypatch.setenv("MCP_CLIENT_NAME", "codemie-client")
        from src.mcp_connect.client.client_info import apply_user_agent_header

        result = apply_user_agent_header({"User-Agent": "some-caller-value"})

        assert result == {"User-Agent": "codemie-client"}

    def test_overrides_existing_user_agent_lowercase_no_duplicate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A caller-supplied 'user-agent' (any case) is replaced by the canonical key, no duplicate."""
        monkeypatch.setenv("MCP_CLIENT_NAME", "codemie-client")
        from src.mcp_connect.client.client_info import apply_user_agent_header

        result = apply_user_agent_header({"user-agent": "some-caller-value"})

        assert result == {"User-Agent": "codemie-client"}
        assert len(result) == 1

    def test_preserves_unrelated_headers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Unrelated headers pass through unchanged alongside the injected User-Agent."""
        monkeypatch.setenv("MCP_CLIENT_NAME", "codemie-client")
        from src.mcp_connect.client.client_info import apply_user_agent_header

        result = apply_user_agent_header({"Authorization": "Bearer token123", "X-Custom": "value"})

        assert result == {
            "Authorization": "Bearer token123",
            "X-Custom": "value",
            "User-Agent": "codemie-client",
        }

    def test_does_not_mutate_input_dict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """apply_user_agent_header() returns a new dict; the caller's dict is untouched."""
        monkeypatch.setenv("MCP_CLIENT_NAME", "codemie-client")
        from src.mcp_connect.client.client_info import apply_user_agent_header

        original = {"X-Custom": "value"}
        apply_user_agent_header(original)

        assert original == {"X-Custom": "value"}
```

**Test-first: yes — `apply_user_agent_header` does not exist yet, so every test above fails with `ImportError: cannot import name 'apply_user_agent_header'`.**

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && poetry run pytest tests/test_user_agent_header.py::TestApplyUserAgentHeader -v`
Expected: FAIL (ImportError) for all 6 tests.

- [ ] **Step 3: Implement the helper**

In `src/mcp_connect/client/client_info.py`, add below `get_client_info()`:

```python
def apply_user_agent_header(headers: dict[str, str] | None) -> dict[str, str]:
    """Return a new headers dict with User-Agent set from MCP_CLIENT_NAME.

    Any existing header matching "user-agent" case-insensitively is removed
    first so the env-var-derived value always wins with no duplicate key.
    """
    merged = {key: value for key, value in (headers or {}).items() if key.lower() != "user-agent"}
    merged["User-Agent"] = get_client_info().name
    return merged
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && poetry run pytest tests/test_user_agent_header.py::TestApplyUserAgentHeader -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add src/mcp_connect/client/client_info.py tests/test_user_agent_header.py
git commit -m "EPMCDME-11515: Add apply_user_agent_header helper for MCP_CLIENT_NAME"
```

---

### Task 2: Wire helper into `managed.py` (streamable-http and SSE)

**Files:**
- Modify: `src/mcp_connect/client/managed.py:270` (`_run_streamable_http_client`), `src/mcp_connect/client/managed.py:304` (`_run_sse_client`)
- Test: `tests/test_user_agent_header.py` (extend)

**Interfaces:**
- Consumes: `apply_user_agent_header(headers: dict[str, str] | None) -> dict[str, str]` (Task 1).
- Produces: nothing new consumed by later tasks — Task 3 wires the same helper independently into `single_usage.py`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_user_agent_header.py`:

```python
import asyncio
from typing import Any
from unittest.mock import patch


class FakeTransportContext:
    """Minimal async context manager simulating a transport (read, write) pair."""

    def __init__(self, streams: tuple[Any, ...]) -> None:
        self.streams = streams

    async def __aenter__(self) -> tuple[Any, ...]:
        return self.streams

    async def __aexit__(self, *_: Any) -> None:
        pass


class DummySession:
    """Minimal ClientSession stand-in that ignores client_info and completes immediately."""

    def __init__(self, read: Any, write: Any, **kwargs: Any) -> None:
        self._inner = _make_async_mock_session()

    async def __aenter__(self) -> Any:
        return self._inner

    async def __aexit__(self, *_: Any) -> None:
        pass


def _make_async_mock_session() -> Any:
    from unittest.mock import AsyncMock

    inner = AsyncMock()
    inner.initialize = AsyncMock()
    return inner


class TestManagedUserAgentHeader:
    """Test that ManagedClient transport methods inject User-Agent into headers."""

    @pytest.mark.asyncio
    async def test_streamable_http_injects_user_agent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_run_streamable_http_client passes headers with injected User-Agent to get_transport_ctx."""
        monkeypatch.setenv("MCP_CLIENT_NAME", "managed-http-ua")

        captured: list[dict[str, str] | None] = []

        def fake_get_transport_ctx(request: Any, headers: dict[str, str] | None) -> FakeTransportContext:
            captured.append(headers)
            return FakeTransportContext(("r", "w", None))

        monkeypatch.setattr("src.mcp_connect.client.managed.ClientSession", DummySession)

        from src.mcp_connect.client.managed import ManagedClient
        from src.mcp_connect.models.request import BridgeRequestBody

        request = BridgeRequestBody(
            serverPath="https://example.com/mcp",
            method="tools/list",
            params={},
            mcp_headers={"user-agent": "caller-value", "X-Custom": "keep-me"},
        )

        cleanup_event = asyncio.Event()
        ready_future: asyncio.Future[Any] = asyncio.Future()

        with patch("src.mcp_connect.client.transports.get_transport_ctx", side_effect=fake_get_transport_ctx):
            task = asyncio.create_task(
                ManagedClient._run_streamable_http_client(request, cleanup_event, ready_future)
            )
            await asyncio.wait_for(asyncio.shield(ready_future), timeout=5.0)
            cleanup_event.set()
            await asyncio.wait_for(task, timeout=5.0)

        assert len(captured) == 1
        assert captured[0] == {"X-Custom": "keep-me", "User-Agent": "managed-http-ua"}

    @pytest.mark.asyncio
    async def test_sse_injects_user_agent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_run_sse_client passes headers with injected User-Agent to sse_client."""
        monkeypatch.setenv("MCP_CLIENT_NAME", "managed-sse-ua")

        captured: list[dict[str, str] | None] = []

        def fake_sse_client(*, url: str, headers: dict[str, str] | None, **kwargs: Any) -> FakeTransportContext:
            captured.append(headers)
            return FakeTransportContext(("r", "w"))

        monkeypatch.setattr("src.mcp_connect.client.managed.sse_client", fake_sse_client)
        monkeypatch.setattr("src.mcp_connect.client.managed.ClientSession", DummySession)

        from src.mcp_connect.client.managed import ManagedClient
        from src.mcp_connect.models.request import BridgeRequestBody

        request = BridgeRequestBody(
            serverPath="https://sse.example.com/mcp",
            method="tools/list",
            params={},
            http_transport_type="sse",
            mcp_headers={"User-Agent": "caller-value"},
        )

        cleanup_event = asyncio.Event()
        ready_future: asyncio.Future[Any] = asyncio.Future()

        task = asyncio.create_task(ManagedClient._run_sse_client(request, cleanup_event, ready_future))
        await asyncio.wait_for(asyncio.shield(ready_future), timeout=5.0)
        cleanup_event.set()
        await asyncio.wait_for(task, timeout=5.0)

        assert len(captured) == 1
        assert captured[0] == {"User-Agent": "managed-sse-ua"}
```

Note: `_run_sse_client` currently does `from mcp.client.sse import sse_client` as a local import inside the function body, so it is not patchable as `src.mcp_connect.client.managed.sse_client` yet. Step 3 below moves that import to module level (a required change, not a style choice) so the test's `monkeypatch.setattr` target exists.

**Test-first: yes — both tests fail because `managed.py` still does `headers = request.mcp_headers or {}`, so the caller-supplied `user-agent`/`User-Agent` value reaches the transport unchanged instead of being replaced by the env-derived value; the SSE test additionally fails with `AttributeError` until the import is moved to module level in Step 3.**

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && poetry run pytest tests/test_user_agent_header.py::TestManagedUserAgentHeader -v`
Expected: FAIL (assertion mismatch on `test_streamable_http_injects_user_agent`; `AttributeError` on `test_sse_injects_user_agent`).

- [ ] **Step 3: Implement the wiring**

In `src/mcp_connect/client/managed.py`:

1. Add the import near the top (module-level, alongside existing imports):

```python
from .client_info import apply_user_agent_header, get_client_info
```

(replacing the existing `from .client_info import get_client_info` line).

2. Move the SSE client import to module level. Replace:

```python
    @staticmethod
    async def _run_sse_client(
        request: BridgeRequestBody,
        cleanup_event: asyncio.Event,
        ready_future: asyncio.Future[ClientSession],
    ) -> None:
        """Run SSE transport client in dedicated task (deprecated)."""
        from mcp.client.sse import sse_client

        logger.warning("SSE transport is deprecated. Please migrate to Streamable HTTP.")
```

with:

```python
    @staticmethod
    async def _run_sse_client(
        request: BridgeRequestBody,
        cleanup_event: asyncio.Event,
        ready_future: asyncio.Future[ClientSession],
    ) -> None:
        """Run SSE transport client in dedicated task (deprecated)."""
        logger.warning("SSE transport is deprecated. Please migrate to Streamable HTTP.")
```

and add `from mcp.client.sse import sse_client` to the module-level imports (alongside `from mcp import ClientSession`).

3. In `_run_streamable_http_client`, replace:

```python
        headers = request.mcp_headers or {}
```

with:

```python
        headers = apply_user_agent_header(request.mcp_headers)
```

4. In `_run_sse_client`, replace:

```python
        headers = request.mcp_headers or {}
```

with:

```python
        headers = apply_user_agent_header(request.mcp_headers)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && poetry run pytest tests/test_user_agent_header.py -v`
Expected: PASS (all tests so far, including Task 1's).

Also re-run the pre-existing suite to confirm no regression:

Run: `source .venv/bin/activate && poetry run pytest tests/test_client_name.py -v`
Expected: PASS (unchanged behavior — `client_info=get_client_info()` forwarding is untouched).

- [ ] **Step 5: Commit**

```bash
git add src/mcp_connect/client/managed.py tests/test_user_agent_header.py
git commit -m "EPMCDME-11515: Inject User-Agent header in ManagedClient HTTP and SSE paths"
```

---

### Task 3: Wire helper into `single_usage.py` (streamable-http and SSE)

**Files:**
- Modify: `src/mcp_connect/client/single_usage.py:204` (`_execute_http_request`), `src/mcp_connect/client/single_usage.py:271` (`_execute_sse_request`)
- Test: `tests/test_user_agent_header.py` (extend)

**Interfaces:**
- Consumes: `apply_user_agent_header(headers: dict[str, str] | None) -> dict[str, str]` (Task 1).
- Produces: nothing further downstream — this completes the header-injection wiring for all in-scope transports.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_user_agent_header.py`:

```python
class TestSingleUsageUserAgentHeader:
    """Test that single-usage transport functions inject User-Agent into headers."""

    @pytest.mark.asyncio
    async def test_http_injects_user_agent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_execute_http_request passes headers with injected User-Agent to get_transport_ctx."""
        monkeypatch.setenv("MCP_CLIENT_NAME", "single-http-ua")

        captured: list[dict[str, str] | None] = []

        def fake_get_transport_ctx(request: Any, headers: dict[str, str] | None) -> FakeTransportContext:
            captured.append(headers)
            return FakeTransportContext(("r", "w", None))

        monkeypatch.setattr("src.mcp_connect.client.single_usage.get_transport_ctx", fake_get_transport_ctx)
        monkeypatch.setattr("src.mcp_connect.client.single_usage.ClientSession", DummySession)

        from src.mcp_connect.client.single_usage import execute_single_usage_request
        from src.mcp_connect.models.request import BridgeRequestBody

        request = BridgeRequestBody(
            serverPath="https://example.com/mcp",
            method="tools/list",
            params={},
            mcp_headers={"user-agent": "caller-value", "X-Custom": "keep-me"},
        )
        await execute_single_usage_request(request, "tools/list", {}, 5000)

        assert len(captured) == 1
        assert captured[0] == {"X-Custom": "keep-me", "User-Agent": "single-http-ua"}

    @pytest.mark.asyncio
    async def test_sse_injects_user_agent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_execute_sse_request passes headers with injected User-Agent to sse_client."""
        monkeypatch.setenv("MCP_CLIENT_NAME", "single-sse-ua")

        captured: list[dict[str, str] | None] = []

        def fake_sse_client(*, url: str, headers: dict[str, str] | None, **kwargs: Any) -> FakeTransportContext:
            captured.append(headers)
            return FakeTransportContext(("r", "w"))

        monkeypatch.setattr("src.mcp_connect.client.single_usage.sse_client", fake_sse_client)
        monkeypatch.setattr("src.mcp_connect.client.single_usage.ClientSession", DummySession)

        from src.mcp_connect.client.single_usage import execute_single_usage_request
        from src.mcp_connect.models.request import BridgeRequestBody

        request = BridgeRequestBody(
            serverPath="https://sse.example.com/mcp",
            method="tools/list",
            params={},
            http_transport_type="sse",
            mcp_headers={"User-Agent": "caller-value"},
        )
        await execute_single_usage_request(request, "tools/list", {}, 5000)

        assert len(captured) == 1
        assert captured[0] == {"User-Agent": "single-sse-ua"}
```

**Test-first: yes — both tests fail because `single_usage.py` still does `headers = request.mcp_headers or {}`, so the caller-supplied value reaches the transport unchanged instead of being replaced by the env-derived value.**

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && poetry run pytest tests/test_user_agent_header.py::TestSingleUsageUserAgentHeader -v`
Expected: FAIL (assertion mismatch on both tests — captured headers still contain the caller's original value).

- [ ] **Step 3: Implement the wiring**

In `src/mcp_connect/client/single_usage.py`:

1. Update the import:

```python
from .client_info import apply_user_agent_header, get_client_info
```

(replacing the existing `from .client_info import get_client_info` line).

2. In `_execute_http_request`, replace:

```python
    headers = request.mcp_headers or {}
```

with:

```python
    headers = apply_user_agent_header(request.mcp_headers)
```

3. In `_execute_sse_request`, replace:

```python
    headers = request.mcp_headers or {}
```

with:

```python
    headers = apply_user_agent_header(request.mcp_headers)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && poetry run pytest tests/test_user_agent_header.py -v`
Expected: PASS (all tests across all three task classes).

Also re-run the full pre-existing suite to confirm no regression:

Run: `source .venv/bin/activate && poetry run pytest tests/test_client_name.py tests/test_transports.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/mcp_connect/client/single_usage.py tests/test_user_agent_header.py
git commit -m "EPMCDME-11515: Inject User-Agent header in single-usage HTTP and SSE paths"
```

---

## Post-plan verification (not a task — run once all 3 tasks are committed)

Run the full pre-commit quality gate before requesting review:

```bash
source .venv/bin/activate && \
poetry run ruff format && \
poetry run ruff check && \
poetry run mypy src/ && \
poetry run black --check src/ tests/ && \
poetry run pytest tests/ --cov=src --cov-report=term-missing
```

All checks must pass (exit code 0).
