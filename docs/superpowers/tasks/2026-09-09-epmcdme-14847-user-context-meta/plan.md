# EPMCDME-14847 — Forward `user_context` to MCP tools as `_meta`

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to implement task-by-task. Steps use `- [ ]`.

**Goal:** Accept an optional `user_context` on `/bridge` and forward it to downstream MCP tools as
`_meta` under `codemie.ai/user-context`, on `tools/call` only, with defensive masking in logs.

**Architecture:** A permissive `dict[str, Any] | None` field on `BridgeRequestBody`; a generic
`meta` parameter threaded through the six functions between `bridge_endpoint` and
`session.call_tool` on both the cached and single-usage branches; the namespaced key is built at
the route layer so `client/methods.py` stays user-context-agnostic. `managed.py` is not on the
invocation path and is untouched.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, `mcp` 1.30.0 SDK, pytest (`asyncio_mode = "auto"`).

**Spec:** `docs/superpowers/tasks/2026-09-09-epmcdme-14847-user-context-meta/spec.md`

## Global Constraints

- `extra="forbid"` stays on `BridgeRequestBody`; other unknown fields must still be rejected 400
  with `type == "extra_forbidden"` (EPMCDME-13546 regression guard, `main.py:218`).
- The `meta` kwarg reaches `session.call_tool` **only when a value is present** — never
  `meta=None`. This keeps the four `assert_awaited_once_with("<tool>", {...})` assertions in
  `test_mcp_methods.py` (lines 94, 106, 117, 128) valid. Do not rewrite them.
- Field absent, or `{}` ⇒ no `meta` ⇒ behaviour byte-identical to current `main`.
- `SENSITIVE_PATTERNS` (`masking.py:22`) is not widened; `_mask_params_recursive` is untouched.
- `cache.py`, `substitution.py`, `context.py` and `managed.py` are **not** edited.
- The EPMCDME-11351 `McpError` → `isError` mapping (`methods.py:103-117`) is untouched.
- `mypy --strict` must stay clean; there is no CI. Every new parameter and helper is fully typed.
- Tests patch `invoke_mcp_method` at **`src.mcp_connect.client.methods.invoke_mcp_method`** —
  `single_usage.py` imports it function-locally (lines 149, 214), so patching the `single_usage`
  namespace silently does nothing.
- Commit per task using the repository's existing convention (`EPMCDME-14847:` prefix).

**Negative constraints honored** (spec § Non-goals, checked task-by-task):
`_meta` on non-`tools/call` methods — gated in Task 4, pinned by a `tools/list` test · backend
change — none, no file outside this repo · interpreting `extra_attributes` — Task 3 redacts it
wholesale, wire value untouched · typing `user_context` as a model — Task 1 uses a plain dict ·
relaxing `extra="forbid"` — Task 1 keeps it, pinned · widening `SENSITIVE_PATTERNS` /
user-context-aware `_mask_params_recursive` — Task 3 adds a new function only · `user_context` in
`generate_cache_key` — Task 1 adds the negative pin, `cache.py` untouched · `$env`/`$headers`
substitution — `substitution.py` untouched, its three-field allowlist carries the field through ·
WebSocket — not touched · recursive masking into nested containers — Task 3 replaces them wholesale,
pinned.

---

### Task 1: Accept `user_context` on the `/bridge` contract

**Files:**
- Modify: `src/mcp_connect/models/request.py:35-46` (optional-field block)
- Modify: `README.md` (the `/bridge` request-body example at `README.md:181-189`)
- Test: `tests/test_bridge_validation.py`, `tests/test_client_manager_cache.py`

**Interfaces:**
- Produces: `BridgeRequestBody.user_context: dict[str, Any] | None = None`.

**Test-first: yes** — `POST /bridge` with a body containing `user_context` currently returns 400
`extra_forbidden`; the new test asserts it is accepted (200).

- [ ] **Step 1:** In `tests/test_bridge_validation.py`, add three cases built on the existing
      `_base_payload()` helper (line 29): a payload with `user_context` returns 200; a payload with
      an unrelated unknown field still returns 400 with `type == "extra_forbidden"`; a `None`
      `user_context` is excluded from the echoed response (`exclude_none`). Run them, confirm the
      first fails 400.
- [ ] **Step 2:** Add the field to `BridgeRequestBody` alongside the other optional config fields,
      typed `dict[str, Any] | None = None` with a `Field(default=None, description=...)` matching
      the neighbours' style. Do not touch `model_config`. Re-run — all three pass.
- [ ] **Step 3:** Add the first negative cache-key test to `tests/test_client_manager_cache.py`:
      two `BridgeRequestBody` instances identical except for `user_context` produce the same
      `generate_cache_key`. It passes immediately — `cache.py:223-229` is a five-key allowlist — and
      exists to pin that inertness against a later edit.
- [ ] **Step 4:** Document the field in `README.md`'s `/bridge` request example plus one sentence:
      optional, opaque, forwarded to `tools/call` as `_meta["codemie.ai/user-context"]`, ignored by
      servers that do not read `_meta`.
- [ ] **Step 5:** Commit.

---

### Task 2: Make the shared endpoint fixture tolerate the new signature

**Files:**
- Modify: `tests/conftest.py:80` (`single_usage_side_effect`)

**Interfaces:**
- Produces: a `side_effect` accepting `(*args: Any, **kwargs: Any)` that still dispatches on the
  `method` argument and returns `{"result": <method>}`, so later tasks can assert on
  `mock.call_args` without breaking existing tests.

**Test-first: no** — pure test-infrastructure change with no behaviour of its own. It is sequenced
here deliberately: the fixture's fixed four-positional arity sits directly on the signature Task 6
changes, and leaving it would `TypeError` every single-usage endpoint test at once, with a failure
message pointing at `conftest.py` rather than at the change.

- [ ] **Step 1:** Widen `single_usage_side_effect` to `(*args: Any, **kwargs: Any)`, reading
      `method` as `args[1]` when positional or `kwargs["method"]` otherwise, keeping the existing
      per-method return mapping unchanged. Run `poetry run pytest tests/test_bridge_validation.py`
      and confirm it is green exactly as before. Commit.

---

### Task 3: `mask_user_context` in `utils/masking.py`

**Files:**
- Modify: `src/mcp_connect/utils/masking.py` (append; do not edit lines 22-91)
- Test: `tests/test_masking.py`

**Interfaces:**
- Produces: `mask_user_context(user_context: dict[str, Any] | None) -> dict[str, Any] | None`, and
  module constant `KEEP_READABLE_KEYS: frozenset[str]`.

**Test-first: yes** — `from src.mcp_connect.utils.masking import mask_user_context` fails with
ImportError; the new tests then pin the type guard (a keep-readable key whose value is a dict, or a
list containing a dict, is redacted).

- [ ] **Step 1:** Add a `TestMaskUserContext` block to `tests/test_masking.py` covering: the eight
      keep-readable keys emitted verbatim for scalar and all-scalar-list values; `roles` as a dict
      redacted; `project_names` as `["a", {"x": 1}]` redacted; `username="jdoe"` → `"j***"`;
      `username="j"`, `username=None` and `username={"a": 1}` → `REDACTED_VALUE`; `email`, `name`,
      `picture`, `extra_attributes` and an unrecognised key redacted; a nested dict value redacted
      wholesale rather than traversed; `None` in → `None` out; `{}` in → `{}` out; and input
      immutability, matching the existing immutability tests in this file. Run — ImportError.
- [ ] **Step 2:** Implement at the end of `masking.py`, reusing the existing `REDACTED_VALUE`:

```python
KEEP_READABLE_KEYS = frozenset({
    "id", "roles", "is_admin", "is_maintainer", "is_auditor",
    "user_type", "project_names", "admin_project_names",
})


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _is_keepable(value: Any) -> bool:
    """Scalar, or a list whose every element is a scalar. Nothing else."""
    if _is_scalar(value):
        return True
    if isinstance(value, list):
        return all(_is_scalar(item) for item in value)
    return False


def _mask_username(value: Any) -> str:
    """First character plus a fixed suffix, so no length is leaked."""
    if not isinstance(value, str) or len(value) < 2:
        return REDACTED_VALUE
    return f"{value[0]}***"


def mask_user_context(user_context: dict[str, Any] | None) -> dict[str, Any] | None:
    """Mask a user-context object for logging. Pure; returns a new dict.

    Defensive by design: only a known-safe key with a known-safe value type is
    emitted verbatim, so a backend type change cannot widen the allowlist.
    """
    if user_context is None:
        return None
    masked: dict[str, Any] = {}
    for key, value in user_context.items():
        if key == "username":
            masked[key] = _mask_username(value)
        elif key in KEEP_READABLE_KEYS and _is_keepable(value):
            masked[key] = list(value) if isinstance(value, list) else value
        else:
            masked[key] = REDACTED_VALUE
    return masked
```

- [ ] **Step 3:** Run `poetry run pytest tests/test_masking.py -v`. All pass, including the
      pre-existing non-sensitive-key assertions at `test_masking.py:67` — `SENSITIVE_PATTERNS` was
      not touched. Commit.

---

### Task 4: `invoke_mcp_method` passes `meta` on `tools/call` only

**Files:**
- Modify: `src/mcp_connect/client/methods.py:54` (signature) and `:102` (the `call_tool` call)
- Test: `tests/test_mcp_methods.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `invoke_mcp_method(session: ClientSession, method: str, params: Any, meta: dict[str, Any] | None = None) -> Any`.

**Test-first: yes** — a new test calling `invoke_mcp_method(session, "tools/call", {...}, meta={"codemie.ai/user-context": {"id": "u1"}})` fails with `TypeError: unexpected keyword argument 'meta'`.

- [ ] **Step 1:** Add to `tests/test_mcp_methods.py`, using the existing `session` fixture (line 29):
      (a) `tools/call` with a `meta` dict asserts
      `session.call_tool.assert_awaited_once_with("echo", {"text": "hi"}, meta={...})`;
      (b) `tools/call` with `meta=None` asserts `assert_awaited_once_with("echo", {"text": "hi"})` —
      no kwarg at all; (c) `tools/list` with a `meta` dict asserts `list_tools` is awaited with its
      current arguments and receives no `meta`. Run — (a) fails on the unexpected kwarg.
- [ ] **Step 2:** Add the `meta` parameter to the signature at `methods.py:54` with default `None`,
      and change the call at `methods.py:102` to pass `meta=meta` only when `meta` is truthy —
      branch on it and make two call expressions rather than passing `meta=meta` unconditionally.
      Leave the surrounding `try/except McpError` (lines 103-117) and every other method branch
      exactly as they are. Add a one-line `# EPMCDME-14847:` comment stating why the kwarg is
      conditional.
- [ ] **Step 3:** Run `poetry run pytest tests/test_mcp_methods.py -v`. New tests pass and all four
      pre-existing `assert_awaited_once_with("<tool>", {...})` assertions are still green. Commit.

---

### Task 5: Thread `meta` through the client layer, both branches

**Files:**
- Modify: `src/mcp_connect/client/manager.py:39` (signature) and `:67-70` (the wrapped call)
- Modify: `src/mcp_connect/client/single_usage.py:50` (signature), `:101-111` (dispatch),
  `:114`, `:197`, `:262` (the three transport helpers and their `invoke_mcp_method` calls at
  `:153`, `:218` and the SSE equivalent)
- Test: `tests/test_single_usage.py`

**Interfaces:**
- Consumes: `invoke_mcp_method(..., meta=...)` from Task 4.
- Produces: `invoke_with_timeout(session, method, params, timeout_ms, meta: dict[str, Any] | None = None) -> Any`;
  `execute_single_usage_request(request, method, params, timeout_ms, meta: dict[str, Any] | None = None) -> Any`;
  each `_execute_*_request(request, method, params, timeout_sec, meta: dict[str, Any] | None = None)`.

**Test-first: yes** — for each of stdio, streamable-http and sse, a test asserting the
`invoke_mcp_method` patched at `src.mcp_connect.client.methods.invoke_mcp_method` receives the meta
dict; all three fail today because the parameter does not exist.

- [ ] **Step 1:** In `tests/test_single_usage.py`, extend the existing `FakeContext`/`DummySession`
      setup with one test per transport that calls `execute_single_usage_request(..., meta={"codemie.ai/user-context": {"id": "u1"}})` and asserts the recorded
      `invoke_mcp_method` call carries that meta; plus one asserting the default omits it. Add one
      test for `invoke_with_timeout` forwarding `meta` to `invoke_mcp_method`. Run — all fail.
- [ ] **Step 2:** Add `meta: dict[str, Any] | None = None` as a trailing defaulted parameter to
      `invoke_with_timeout`, `execute_single_usage_request` and all three `_execute_*` helpers, and
      pass it down at each call site. Keep the existing positional call convention for the first
      four arguments; pass `meta` as a keyword. Defaulting it keeps every existing caller and test
      valid.
- [ ] **Step 3:** Run `poetry run pytest tests/test_single_usage.py -v` and
      `poetry run mypy src/`. Green. Commit.

---

### Task 6: Build the namespaced key at the route layer and forward it

**Files:**
- Modify: `src/mcp_connect/server/routes.py` — new helper near the module constants,
  `_handle_single_usage_request:122` (call at `:137`), `_handle_cached_client_request:162`
  (call at `:205`)
- Test: `tests/test_bridge_validation.py`

**Interfaces:**
- Consumes: `mask_user_context` (Task 3); the widened signatures from Task 5; the tolerant fixture
  from Task 2.
- Produces: module constant `USER_CONTEXT_META_KEY = "codemie.ai/user-context"` and
  `_build_user_context_meta(request: BridgeRequestBody) -> dict[str, Any] | None`, returning
  `{USER_CONTEXT_META_KEY: request.user_context}` when `request.user_context` is truthy, else `None`.

**Test-first: yes** — endpoint tests asserting that a `/bridge` request carrying `user_context`
results in `execute_single_usage_request` (and `invoke_with_timeout`) receiving
`meta={"codemie.ai/user-context": {...}}`; today they receive no such argument.

- [ ] **Step 1:** In `tests/test_bridge_validation.py`, using the `mock_mcp_client` fixture, add:
      single-usage mode with `user_context` → the recorded call carries the namespaced meta;
      cached mode with `user_context` → same via the `get_or_create_client`/`invoke_with_timeout`
      mocks; field omitted → no meta; `user_context={}` → no meta (treated as absent); and a
      `caplog` assertion that the route INFO line contains the masked object and neither the raw
      `email` value nor the raw `username`. Run — the forwarding cases fail.
- [ ] **Step 2:** Add `USER_CONTEXT_META_KEY` and `_build_user_context_meta` to `routes.py`. The
      helper emits one INFO line through the module logger carrying
      `mask_user_context(request.user_context)` in `extra=` — the masked object only, never the raw
      one — and returns the namespaced dict. Falsy `user_context` returns `None` and logs nothing.
- [ ] **Step 3:** Call the helper once in each of `_handle_single_usage_request` and
      `_handle_cached_client_request`, passing the result as the `meta` keyword to
      `execute_single_usage_request` (`routes.py:137`) and `invoke_with_timeout` (`routes.py:205`).
      `methods.py` gains no user-context knowledge.
- [ ] **Step 4:** Run `poetry run pytest tests/test_bridge_validation.py -v`. New tests pass and the
      pre-existing endpoint suite is still green — Task 2 removed the arity trap. Commit.

---

### Task 7: Mask `user_context` in the debug payload dump, and read its flag per request

**Files:**
- Modify: `src/mcp_connect/server/routes.py:49` (module-level flag read) and `:276-283` (the
  `DEBUG_LOG_BRIDGE_PAYLOAD` block)
- Test: `tests/test_debug_payload_logging.py` (create)

**Interfaces:**
- Consumes: `mask_user_context` (Task 3).
- Produces: `_debug_log_bridge_payload(request: BridgeRequestBody) -> None`, which reads the
  `DEBUG_LOG_BRIDGE_PAYLOAD` env var per call and returns immediately when it is not truthy.

**Test-first: yes** — a test that `monkeypatch.setenv("DEBUG_LOG_BRIDGE_PAYLOAD", "true")` and calls
the helper cannot even be written today: the flag is read once at import (`routes.py:49`), so the
block is unreachable per-test, and no test has ever exercised it.

- [ ] **Step 1:** Create `tests/test_debug_payload_logging.py` with `monkeypatch.setenv` plus
      `caplog`: with the flag unset nothing is logged; with it set to `"true"` the dump is logged
      and its `user_context` entry equals `mask_user_context(payload["user_context"])`, with the raw
      `email` value absent from the whole record; `request_headers` and `env` masking behave exactly
      as the current block does (first-ever coverage of that behaviour); flipping the env var
      between two calls changes the outcome without reimporting the module. Run — fails.
- [ ] **Step 2:** Extract the block at `routes.py:276-283` into `_debug_log_bridge_payload`, reading
      the env var inside the function with the same truthy set as line 49 (`true`/`1`/`yes`,
      lowercased). Keep the existing `request_headers` and `env` masking identical, and add
      `user_context` masked via `mask_user_context` when the key is present in the dump. Call it
      from `bridge_endpoint` where the inline block used to be. Note in a short comment that the
      flag is now dynamic — a deliberate, documented behaviour change.
- [ ] **Step 3:** Run `poetry run pytest tests/test_debug_payload_logging.py -v` and
      `poetry run mypy src/`. Green. Commit.
