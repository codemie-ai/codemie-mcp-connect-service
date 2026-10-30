# Technical Research

**Task**: mcp bridge user-context meta masking cache
**Generated**: 2026-09-09
**Research path**: codegraph

---

## 1. Original Context

EPMCDME-14847 (sub-task of EPMCDME-13260) — MCP-Connect: accept `user_context` on /bridge and forward it to downstream MCP tools as MCP `_meta`.

Repository: codemie-mcp-connect-service (this repo). Assume the CodeMie backend already sends the field; the backend-side change is tracked on EPMCDME-13260 and is OUT OF SCOPE here.

PROBLEM
`/bridge` currently rejects `user_context` because `BridgeRequestBody` sets `model_config = ConfigDict(extra="forbid")` (src/mcp_connect/models/request.py). That rejection is why EPMCDME-13546 stripped the field on the backend and why the MCP half of the parent story was never delivered.
Separately — and this is the crux — `/bridge` does NOT forward the request body verbatim to the MCP server. It parses `method` + `params` and makes a typed MCP SDK call in `src/mcp_connect/client/methods.py:54` `invoke_mcp_method`. So merely accepting the field is not enough; it must be explicitly threaded into the SDK call.

CONTRACT (already agreed with the backend team — do not redesign it)
- Backend sends `user_context` as a plain top-level field on the /bridge body. Backend does NOT know about MCP `_meta`.
- MCP-Connect translates it into `_meta` under the namespaced key `codemie.ai/user-context`, on `tools/call` ONLY.
- Downstream tool reads `params._meta["codemie.ai/user-context"]`; servers ignoring `_meta` are unaffected (backward compatible).
- SDK support verified in the pinned mcp 1.30.0: `ClientSession.call_tool(name, arguments, read_timeout_seconds=None, progress_callback=None, *, meta: dict[str, Any] | None = None)` which becomes `CallToolRequestParams._meta` via `RequestParams.Meta(**meta)`. `ClientSession.list_tools(cursor=None, *, params: PaginatedRequestParams | None)` has NO meta kwarg — hence tools/call only.

PLANNED CHANGE SURFACE (verify these against current code; correct me if any line/symbol has moved)
1. src/mcp_connect/models/request.py — add `user_context: dict[str, Any] | None` to BridgeRequestBody. KEEP extra="forbid". Permissive dict, NOT a typed model, so backend profile-field changes never force a lockstep release here.
2. src/mcp_connect/server/routes.py — forward from both `_handle_single_usage_request` and `_handle_cached_client_request` (call site around routes.py:205).
3. src/mcp_connect/server/routes.py — the DEBUG_LOG_BRIDGE_PAYLOAD block (~routes.py:276-283) masks request_headers and env but would dump user_context UNMASKED.
4. src/mcp_connect/client/manager.py `invoke_with_timeout` and src/mcp_connect/client/single_usage.py (`execute_single_usage_request` + `_execute_stdio_request` / `_execute_http_request` / `_execute_sse_request`) — thread a generic `meta` param through.
5. src/mcp_connect/client/methods.py `invoke_mcp_method` — new `meta` param passed to `session.call_tool()` in the tools/call branch ONLY. Keep methods.py generic: it takes a `meta` dict, not a `user_context`; the route layer builds the namespaced key.
6. src/mcp_connect/utils/masking.py — new `mask_user_context()`.
7. README.md — document the field.

HARD CONSTRAINTS
- DO NOT add user_context to `generate_cache_key` (src/mcp_connect/client/cache.py:210). It is per-invocation; adding it would give every user a private cached client and destroy reuse. A test must pin this.
- extra="forbid" stays; other unknown fields must still be rejected (EPMCDME-13546 regression guard).
- No $env/$headers substitution on user_context — backend-resolved data, not a template. Check `apply_substitutions` (src/mcp_connect/utils/substitution.py:82) carries the new field through untouched via model_copy(deep=True).
- Must not disturb the McpError -> isError mapping from EPMCDME-11351 (methods.py:103-117).
- Field absent => no meta passed => behaviour byte-identical to today.
- mypy --strict must stay clean; there is no CI in this repo.

LOG MASKING REQUIREMENT
Real values on the wire, masked in logs. Mask email, name, picture, partially username. Keep id, roles, is_admin, is_maintainer, is_auditor, user_type, project_names, admin_project_names readable so authz failures stay diagnosable. Mask DEFENSIVELY: user_context is opaque here, so mask any nested dict or unrecognised key wholesale rather than allowlisting known field names. Do NOT widen SENSITIVE_PATTERNS (src/mcp_connect/utils/masking.py:22) — it is applied to arbitrary tool arguments via `_mask_params_recursive` and `name` is a common legitimate tool-argument key; widening it would over-mask real payloads.

RESEARCH I NEED FROM YOU
- Exact current signatures and call chain from `bridge_endpoint` down to `session.call_tool`, with every intermediate function that must gain the new parameter.
- How the three transports in single_usage.py reach invoke_mcp_method, and whether managed.py/ManagedClient has a parallel path that also needs threading.
- Existing test files and patterns that will need new cases (test_mcp_methods.py, test_bridge_validation.py, test_client_manager_cache.py, test_masking.py, test_single_usage.py) — how they mock ClientSession, so new assertions match house style.
- Whether anything else already reads or would collide with a `meta` kwarg.
- Risk indicators: places where adding an optional field could change behaviour unexpectedly (serialization, model_copy, cache key, logging).

Full pre-written breakdown is at repo root: EPMCDME-13260-mcp-connect-task.md — NOTE it is currently stashed (git stash@{0}) so it is not on disk right now; do not try to read it.

---

## 2. Codebase Findings

All line numbers below were re-derived from current on-disk source. Every symbol and line
reference named in the task's "PLANNED CHANGE SURFACE" was verified; corrections are called out
explicitly.

### Existing Implementations

**Request model**
- `src/mcp_connect/models/request.py:24` — `BridgeRequestBody(BaseModel)`. `model_config = ConfigDict(extra="forbid")` at line 27. Required: `serverPath: str` (30), `method: str` (31), `params: Any` (32). Optional config: `args: list[str] | None` (35), `env: dict[str, Any] | None` (36), `mcp_headers: dict[str, str] | None` (37), `request_headers: dict[str, str] | None` (38), `http_transport_type: str | None` (39), `single_usage: bool = False` (40). Context/observability block: `user_id`, `assistant_id`, `project_name`, `workflow_execution_id` — all `str | None`, lines 43-46. One validator: `convert_env_values_to_strings` (`field_validator("env", mode="before")`, line 48). **There is no `user_context` field and no `meta` field today.** The file is 69 lines; the model is small and flat.

**Route layer**
- `src/mcp_connect/server/routes.py:241` — `async def bridge_endpoint(request: BridgeRequestBody, timeout: int | None = Query(...), _verified: None = Depends(verify_token)) -> JSONResponse`.
- `routes.py:273` — `await setup_request_context(request)`.
- `routes.py:276-283` — the `DEBUG_LOG_BRIDGE_PAYLOAD` block. **Confirmed exactly at the lines the task predicted.** It calls `request.model_dump(mode="json", exclude_none=True)` and then masks only two keys by name: `request_headers` (`mask_dict_values(..., mask_all=True)`) and `env` (`mask_dict_values(..., mask_all=False)`). Every other field in the dump is logged verbatim.
- `routes.py:296-299` — the mode fork: `if request.single_usage: _handle_single_usage_request(request, timeout_ms) else: _handle_cached_client_request(request, timeout_ms)`.
- `routes.py:303-306` — response serialization: `result.model_dump(mode="json", exclude_none=True)` if the result has `model_dump`, else pass through.
- `routes.py:122` — `async def _handle_single_usage_request(request: BridgeRequestBody, timeout_ms: int) -> Any`. Body at line 137: `result = await execute_single_usage_request(request, request.method, request.params, timeout_ms)` — four positional args.
- `routes.py:162` — `async def _handle_cached_client_request(request: BridgeRequestBody, timeout_ms: int) -> Any`. Line 179: `handle, session = await get_or_create_client(request)`. Line 205: `result = await invoke_with_timeout(session, request.method, request.params, timeout_ms)` — **the task's "call site around routes.py:205" is exactly right.**

**Client layer — cached path**
- `src/mcp_connect/client/manager.py:39` — `async def invoke_with_timeout(session: ClientSession, method: str, params: Any, timeout_ms: int) -> Any`. Line 67-70 wraps `invoke_mcp_method(session, method, params)` in `asyncio.wait_for`. Only two callers, both in routes.py.
- `manager.py:118` — `async def get_or_create_client(request: BridgeRequestBody) -> tuple[ManagedClient, ClientSession]`. Line 157 `apply_substitutions(request)`, line 160 `generate_cache_key(processed_request)`, line 179 `ManagedClient.spawn(processed_request)`.
- `manager.py:90` — `detect_transport_type(server_path, http_transport_type) -> str` returning `"stdio" | "streamable-http" | "sse"`; rejects `ws://`/`wss://` with HTTP 400.

**Client layer — single-usage path**
- `src/mcp_connect/client/single_usage.py:50` — `async def execute_single_usage_request(request: BridgeRequestBody, method: str, params: Any, timeout_ms: int) -> Any`. Line 88 `apply_substitutions(request)`, line 93 `detect_transport_type(...)`, lines 101-111 dispatch to one of three private helpers, each called with `(processed_request, method, params, timeout_sec)`.
- `single_usage.py:114` — `_execute_stdio_request(request, method, params, timeout_sec)`. Reaches the SDK at line 143-155: `stdio_client(server_params)` → `ClientSession(read, write, client_info=get_client_info())` → `session.initialize()` → `asyncio.wait_for(invoke_mcp_method(session, method, params), timeout=timeout_sec)`.
- `single_usage.py:197` — `_execute_http_request(request, method, params, timeout_sec)`. Same shape, lines 208-220, via `get_transport_ctx(request, headers)`.
- `single_usage.py:262` — `_execute_sse_request(request, method, params, timeout_sec)`. Same shape (deprecated transport).
- All three call `invoke_mcp_method` through a **function-local import** (`from .methods import invoke_mcp_method` at lines 149 and 214) rather than a module-level one. This is why existing tests monkeypatch `src.mcp_connect.client.methods.invoke_mcp_method` and not the `single_usage` namespace.

**Method dispatch — where `_meta` would land**
- `src/mcp_connect/client/methods.py:54` — `async def invoke_mcp_method(session: ClientSession, method: str, params: Any) -> Any`. Confirmed signature; no `meta` parameter exists.
- Line 73: `masked_params = _mask_params_recursive(params)` then `logger.info("Invoking MCP method: %s", method, extra={"method": method, "params": masked_params})`.
- Line 81: `payload = _ensure_mapping(params, normalized_method)`.
- Lines 83-175: a flat if-chain over 12 methods — `tools/list`, `tools/call`, `prompts/list`, `prompts/get`, `resources/list`, `resources/read`, `resources/templates/list`, `resources/subscribe`, `resources/unsubscribe`, `completion/complete`, `logging/setLevel`, `ping`. Unrecognized method → HTTP 400 at line 178.
- **`tools/call` branch, lines 87-117**: `name = _require_param(payload, "name")`; `arguments = _optional_mapping_param(payload, "arguments")`; `clean_arguments = _strip_none_values(arguments)`; then line 102 `return await session.call_tool(name, clean_arguments)` — **two positional args only, no kwargs today.** Wrapped in `try/except McpError` at lines 103-117 (the EPMCDME-11351 mapping), which logs a warning and returns `_mcp_error_to_tool_result(name, exc.error)`.
- `methods.py:184` — `_mcp_error_to_tool_result(name: str, error: ErrorData) -> CallToolResult`, returning `CallToolResult(isError=True, content=[TextContent(type="text", text=...)])`. The task's cited range "methods.py:103-117" is exact for the try/except; the helper itself is at 184-192.
- `methods.py:33` — `_mask_params_recursive(data: Any) -> Any`. Recursive: dict → `REDACTED_VALUE if is_sensitive_key(k) else recurse`; list → elementwise; `str|int|float|bool` → passthrough; anything else → `str(type(data).__name__)`. Imports `REDACTED_VALUE, is_sensitive_key` from `..utils.masking` at line 28.
- Helpers: `_ensure_mapping:195`, `_require_param:221`, `_optional_mapping_param:248`, `_call_with_optional_cursor:280`, `_strip_none_values` (referenced at line 90).

**Masking utilities**
- `src/mcp_connect/utils/masking.py` is 91 lines total and exports exactly four names: `SENSITIVE_PATTERNS` (line 22, a compiled case-insensitive regex over `authorization|api[-_]?key|x-api-key|token|auth|bearer|secret|password|access[-_]?token|refresh[-_]?token|x-auth-token`), `REDACTED_VALUE = "********"` (27), `is_sensitive_key(key: str) -> bool` (30), `mask_dict_values(data: dict[str, str], mask_all: bool = False) -> dict[str, str]` (51), `mask_sensitive_headers(headers: dict[str, str] | None) -> dict[str, str]` (74).
- Both public maskers are **flat and `str`-typed** — `dict[str, str]` in, `dict[str, str]` out. Neither recurses. The only recursive masker in the codebase is the private `_mask_params_recursive` in methods.py. There is no partial-masking helper (nothing that preserves a prefix/suffix of a value) anywhere.
- `SENSITIVE_PATTERNS` is consumed by `is_sensitive_key`, which is consumed by `mask_dict_values` **and** by `_mask_params_recursive` over arbitrary tool arguments — the coupling the task's constraint refers to is real and confirmed.

**Cache key**
- `src/mcp_connect/client/cache.py:210` — `generate_cache_key(request: BridgeRequestBody) -> str`. Verified: the key dict at lines 223-229 contains exactly five entries — `server_path`, `args` (sorted), `env` (sorted items), `mcp_headers` (sorted items), `http_transport_type` (or `"default"`) — then `json.dumps(..., sort_keys=True)` and SHA-256 hexdigest. It is a **whitelist, not a model dump**: it does not iterate model fields, so a new optional field on `BridgeRequestBody` is inert here by construction unless someone edits this function.
- `MCPClientCache` at `cache.py:67`, keyed `dict[str, tuple[ManagedClient, float]]`, sliding-window TTL from `MCP_CONNECT_CLIENT_CACHE_TTL`, ping-validated on `get`.

**Substitution**
- `src/mcp_connect/utils/substitution.py:82` — `apply_substitutions(request: BridgeRequestBody) -> BridgeRequestBody`. Line 120: `substituted = request.model_copy(deep=True)`. It then rewrites exactly three fields: `serverPath` (122), `args` if truthy (129), `mcp_headers` if truthy (137). **Confirmed: it is an allowlist over three fields on a deep copy**, so any new field is carried through byte-identical without needing a code change.

### Architecture and Layers Affected

The service is a four-layer bridge; the `/bridge` path crosses all four.

| Layer | Components on this path |
|---|---|
| **HTTP / route** (`server/`) | `routes.py` `bridge_endpoint:241`, `_handle_single_usage_request:122`, `_handle_cached_client_request:162`, `format_error_response:52`; `middleware.py` `setup_request_context:69`; `verify_token` auth dependency |
| **Contract / model** (`models/`) | `request.py` `BridgeRequestBody:24` |
| **Client orchestration** (`client/`) | `manager.py` `invoke_with_timeout:39`, `get_or_create_client:118`, `detect_transport_type:90`; `single_usage.py` `execute_single_usage_request:50` + 3 transport helpers; `managed.py` `ManagedClient.spawn:79` and lifecycle; `cache.py` `MCPClientCache` + `generate_cache_key:210`; `methods.py` `invoke_mcp_method:54` |
| **Utilities** (`utils/`) | `masking.py`, `substitution.py` `apply_substitutions:82`, `context.py` `extract_request_context:38`, `logger.py` |

**The verified call chain from HTTP entry to `session.call_tool` — two distinct branches:**

Cached branch (default, `single_usage` false):
```
bridge_endpoint (routes.py:241)
  -> _handle_cached_client_request (routes.py:162)
       -> get_or_create_client (manager.py:118)          [returns (ManagedClient, ClientSession)]
       -> invoke_with_timeout (manager.py:39)            [routes.py:205, 4 positional args]
            -> invoke_mcp_method (methods.py:54)         [manager.py:68]
                 -> session.call_tool(name, clean_arguments)   [methods.py:102]
```

Single-usage branch:
```
bridge_endpoint (routes.py:241)
  -> _handle_single_usage_request (routes.py:122)
       -> execute_single_usage_request (single_usage.py:50)   [routes.py:137, 4 positional args]
            -> _execute_stdio_request  (single_usage.py:114)  -> invoke_mcp_method (line 153)
            -> _execute_http_request   (single_usage.py:197)  -> invoke_mcp_method (line 218)
            -> _execute_sse_request    (single_usage.py:262)  -> invoke_mcp_method
                 -> session.call_tool(name, clean_arguments)   [methods.py:102]
```

The two branches converge only at `invoke_mcp_method`. There are exactly **six** functions strictly
between `bridge_endpoint` and `session.call_tool` across both branches: `_handle_cached_client_request`,
`invoke_with_timeout`, `_handle_single_usage_request`, `execute_single_usage_request`, the three
`_execute_*` helpers (one per request), and `invoke_mcp_method`.

**`ManagedClient` (managed.py) does NOT have a parallel invocation path.** This is the single most
important structural finding for scoping. `ManagedClient.spawn:79` → `_run_client_lifecycle:166` →
one of `_run_stdio_client:227` / `_run_streamable_http_client:264` / `_run_sse_client:296`. Each of
those three constructs the transport and `ClientSession`, calls `session.initialize()`, publishes
the live session via `ready_future.set_result(session)`, and then parks on `await cleanup_event.wait()`
for the cache TTL. **None of them ever calls `invoke_mcp_method` or `session.call_tool`.** The
dedicated task owns only the connection lifecycle; per-request invocation happens back in the caller's
task via the session handed out through `get_or_create_client`. So `managed.py` sees no per-request
data and is not on the parameter-threading path.

### Integration Points

- **MCP Python SDK** — `ClientSession` (`from mcp import ClientSession`), transports `stdio_client`, `streamablehttp_client`, `sse_client`, types `Implementation`, `CallToolResult`, `TextContent`, `ErrorData`, and `McpError`. `session.call_tool` is invoked at exactly one place in the whole repository: `methods.py:102`.
- **Transport selection** — `client/transports.py` `get_transport_ctx:40` is shared by `single_usage._execute_http_request` and `managed._run_streamable_http_client`.
- **AWS SigV4** — `client/streamable_http_sigv4.py` and `utils/signer.py` wrap Streamable HTTP for `bedrock-agentcore` URLs. On the transport axis, orthogonal to method params.
- **Request-context propagation** — `utils/context.py:38` `extract_request_context` reads four named fields off `BridgeRequestBody` (`user_id`, `assistant_id`, `project_name`, `workflow_execution_id`) into a `ContextVar`. It is an **explicit per-field allowlist** (lines 61-68), so it neither picks up nor breaks on a new field. Invoked from `server/middleware.py:69` `setup_request_context`.
- **FastAPI validation handler** — `main.py:218` `request_validation_exception_handler` maps `RequestValidationError` to 422, except when any error has `type == "extra_forbidden"`, which becomes **400**. This is the mechanism the EPMCDME-13546 regression guard depends on.

### Patterns and Conventions

- **Positional-argument call convention throughout the invocation chain.** `execute_single_usage_request(request, request.method, request.params, timeout_ms)` and `invoke_with_timeout(session, request.method, request.params, timeout_ms)` are both called with bare positionals, and the three `_execute_*` helpers likewise. Nothing on this path uses keyword-only parameters today.
- **Method dispatch is a flat if-chain on `normalized_method`** in `invoke_mcp_method`, each branch extracting its own params via `_require_param` / `_optional_mapping_param` and returning the SDK result directly. Adding behaviour to one method means editing one branch.
- **Optional params are extracted, never assumed.** `_optional_mapping_param` returns `{}` for a missing key and raises HTTP 400 for a non-mapping value; `_require_param` raises HTTP 400 with `{"error": "Missing required parameter: <k>"}`.
- **Masking at the log call site, not in the data.** Real values stay on the request object; every logging statement wraps its argument (`mask_dict_values`, `mask_sensitive_headers`, `_mask_params_recursive`). Maskers are pure and return new dicts — `test_masking.py` has dedicated immutability tests asserting the input is unmutated.
- **Deferred/function-local imports** inside `single_usage.py`, `managed.py`, and `manager.py` to break import cycles between `client` submodules (`from .methods import invoke_mcp_method`, `from .manager import detect_transport_type`, `from .transports import get_transport_ctx`).
- **Ticket-referenced comments on behavioural carve-outs.** `methods.py:104-109` explains the EPMCDME-11351 `McpError` carve-out inline, including why only `McpError` is caught. Security pins carry `# Security (EPMCDME-...)`.
- **Allowlist over reflection** for anything derived from `BridgeRequestBody` — `generate_cache_key`, `apply_substitutions`, and `extract_request_context` each enumerate the fields they care about. Only `routes.py:277` (`model_dump`) and `routes.py:304` reflect over the whole model.
- **Every module carries the EPAM Apache-2.0 header** (14 lines) and `from __future__ import annotations`.

---

## 3. Documentation Findings

### Guides and Architecture Docs

Eleven guides exist under `.ai-run/guides/`:
`README.md`, `project.md`, `architecture/architecture.md`, `setup.md`, `quality-gates.md`,
`security/README.md`, `build/README.md`, `build/dependencies.md`,
`standards/git-workflow.md`, `testing/testing-patterns.md`, `development/development-practices.md`.

Read for this task: `testing/testing-patterns.md`. Relevant content:
- `asyncio_mode = "auto"` (`pyproject.toml:51`) — async tests need no decorator, though much of the existing suite still carries an explicit `@pytest.mark.asyncio`.
- Discovery: `testpaths = ["tests"]`, `python_files = ["test_*.py"]`, `python_classes = ["Test*"]`, `python_functions = ["test_*"]`; `addopts = "-m 'not integration'"`.
- Shared fixtures belong in `tests/conftest.py`.
- Coverage policy: "All new code must have tests"; "Critical paths require 100% coverage (authentication, client lifecycle, **MCP protocol calls**)" — `tools/call` is explicitly named as a critical path.
- Best-practice table: behaviour-describing test names, one assertion focus per test, Arrange-Act-Assert.
- **Documented trap**: `poetry run pytest tests/ -m integration` collects nothing and exits 5. `tests/integration/` holds only `__init__.py` and no test carries the marker. The guide states plainly that any document presenting this as a mandatory gate is wrong — and `README.md:159` does exactly that inside its "Pre-commit Quality Check (REQUIRED)" `&&` chain.

`AGENTS.md` (repo root, loaded as project instructions) additionally states: `/bridge` request or
response schema changes are an **"Ask first"** item — "Deployed clients depend on it."

### Architectural Decisions

- **ADR-007, WebSocket not supported** — cited inline at `manager.py:104` (`# Reject WebSocket transports explicitly (not supported per ADR-007)`) and restated in `AGENTS.md` under "Never".
- **EPMCDME-11351** — downstream MCP protocol errors become `isError` tool results rather than HTTP 500. Recorded as a 6-line inline comment at `methods.py:104-109` and pinned by two tests in `test_mcp_methods.py`, one of which (`test_tools_call_non_mcp_error_propagates`) exists specifically to assert the carve-out is *narrow*.
- **Per-client dedicated tasks** — documented as a docstring ADR in `get_or_create_client` (`manager.py:127-133`) and `_run_client_lifecycle` (`managed.py:171-184`): context managers must be entered and exited in the same asyncio task to preserve anyio cancel-scope integrity. This is the reason `ManagedClient` holds only the connection and hands the session out.
- **Story-numbered provenance comments** throughout `routes.py` (Story 3.2 cache-first, Story 3.6 timeouts, Story 4.3 context propagation).
- No `docs/adr/` directory; decisions live in inline comments, docstrings, and `AGENTS.md`.

### Derived Conventions

- **A new optional field on `BridgeRequestBody` is inert by default.** Three of the four consumers (`generate_cache_key`, `apply_substitutions`, `extract_request_context`) allowlist fields explicitly. The only reflective consumer is `routes.py:277` `model_dump(mode="json", exclude_none=True)` in the debug-payload block, which masks by hardcoded key name.
- **`exclude_none=True` on both dump sites** means a `None` optional field is absent from the debug log and from the response body, not present-and-null.
- Type hints are complete and `mypy --strict` is clean with no CI to catch regressions — the strictness is enforced only by the local gate.
- Log formatting uses `%`-style lazy interpolation with `logger.debug("...: %s", value)`, plus `extra={...}` for structured fields.

---

## 4. Testing Landscape

### Existing Coverage

| File | Covers |
|---|---|
| `tests/conftest.py` | `async_client` (httpx `ASGITransport` over the real FastAPI `app`) and `mock_mcp_client` fixtures |
| `tests/test_mcp_methods.py` | `invoke_mcp_method` for all 12 methods; `tools/call` name requirement, argument passthrough, null-stripping (flat + nested), falsy-value preservation, `McpError`→`isError` conversion, non-`McpError` propagation |
| `tests/test_bridge_validation.py` | `/bridge` request validation end-to-end: missing `serverPath`/`method`/`params` → 422; wrong types → 422; **unknown field → 400 with `type == "extra_forbidden"`**; valid minimal and all-optional-fields requests → 200; `?timeout=` accepted; null-field exclusion from response; `env` coercion for bool/int/float/None/mixed |
| `tests/test_single_usage.py` | All three transports via `FakeContext` + `DummySession`; downstream 401/403 propagation; timeout → 504; context exit assertions |
| `tests/test_masking.py` | `is_sensitive_key` (case-insensitivity, hyphen/underscore variants, all patterns, non-sensitive keys), `mask_dict_values` both modes incl. empty dicts, immutability of inputs, `mask_sensitive_headers` |
| `tests/test_cache.py` | `MCPClientCache` hit/miss/expiry; `generate_cache_key` consistency, difference, order-insensitivity, 64-char digest length |
| `tests/test_client_manager_cache.py` | `get_or_create_client` cache hit/miss, storage after creation, hit/miss logging, HTTP transport caching, cache-key consistency/difference |
| `tests/test_client_name.py`, `tests/test_user_agent_header.py` | `client_info` / User-Agent injection across transports; `make_capturing_session_class` pattern for capturing `ClientSession` kwargs |
| `tests/test_context_propagation.py` | `extract_request_context` field extraction and omission, `ContextVar` set/get, `get_request_id` |
| Others | `test_error_responses.py`, `test_cache_cleanup.py`, `test_graceful_shutdown.py`, `test_types_cleanup_errors.py`, `test_managed_lifecycle_errors.py`, `test_substitution.py`, `test_logger.py`, `test_main_error_handling.py` |

### Testing Framework and Patterns

- **pytest + pytest-asyncio (`asyncio_mode = "auto"`) + pytest-cov.** Full suite ~90s.
- **Three distinct `ClientSession` mocking styles, matched to layer** — new assertions should follow whichever layer they target:
  1. **`test_mcp_methods.py:29` `session` fixture** — a bare local `class FakeSession: pass` with each of the 12 SDK methods set to `AsyncMock(return_value={"called": name})` via a `_set_mock` loop. Assertions are `assert_awaited_once_with(...)` against the exact positional args, e.g. `session.call_tool.assert_awaited_once_with("echo", {"text": "hi"})` (line 94) and `session.call_tool.assert_awaited_once_with("query_prometheus", {"query": "up"})` (line 106). This is the natural home for a `_meta` assertion, and it pins argument shape exactly — an added kwarg changes these call records.
  2. **`test_single_usage.py:33` `FakeContext` dataclass + `DummySession`** — monkeypatched over `src.mcp_connect.client.single_usage.stdio_client` / `.sse_client` / `.ClientSession`, with `invoke_mcp_method` patched at `src.mcp_connect.client.methods.invoke_mcp_method` (the *defining* module, because single_usage imports it function-locally). Fakes accept `*args, **kwargs` and so tolerate signature growth.
  3. **`test_client_name.py:45` `make_capturing_session_class(capture_list)`** — a `CapturingSession` whose `__init__(self, read, write, **kwargs)` appends `kwargs.get("client_info")` to a list. The established pattern for asserting on a kwarg passed into the SDK.
- **`tests/conftest.py:41` `mock_mcp_client`** patches *both* invocation paths at their import sites in the route module: `mcp_connect.server.routes.get_or_create_client` and `mcp_connect.server.routes.execute_single_usage_request`. The single-usage mock is a **`side_effect` function with the fixed positional signature `single_usage_side_effect(request, method, params, timeout_ms)`** (line 80) that dispatches on `method` and returns `{"result": <method>}`.
- **Import style is inconsistent across the suite** — `tests/conftest.py:25` uses `from mcp_connect.main import app` while `test_masking.py:19`, `test_cache.py:25`, and others use `from src.mcp_connect...`. Both resolve; match the neighbouring file.
- Endpoint-level tests drive the real app through `async_client.post("/bridge", json=payload)` and assert on `response.status_code` and `response.json()`, with a `_base_payload()` helper (`test_bridge_validation.py:29`) returning the three required fields.

### Coverage Gaps

- **`bridge_endpoint`, `_handle_single_usage_request` and `_handle_cached_client_request` have no direct unit tests.** Codegraph blast-radius reports "no tests found within 3 caller hops" for all three. They are exercised only indirectly, through `test_bridge_validation.py` against the full ASGI app with both downstream calls mocked out — meaning **the argument-passing behaviour of the route handlers themselves is currently unasserted**.
- **The `DEBUG_LOG_BRIDGE_PAYLOAD` block (`routes.py:276-283`) has zero test coverage.** `DEBUG_LOG_BRIDGE_PAYLOAD` is read once at module import (line 49), so it is not monkeypatchable per-test without reloading or patching the module attribute; no existing test does either. Its masking of `request_headers` and `env` is unverified by any test.
- **No test asserts that a field is *absent* from `generate_cache_key`.** `test_cache.py` and `test_client_manager_cache.py` assert only that listed fields do/do not change the key. The task's "a test must pin this" requirement has no existing precedent to copy — it would be the first negative cache-key test.
- No test covers `_mask_params_recursive` directly (only via `invoke_mcp_method` callers).
- `tests/integration/` contains no tests; integration coverage of the real MCP handshake is absent, not passing.

---

## 5. Configuration and Environment

### Environment Variables

Read via `os.getenv` in or adjacent to this feature area:

| Variable | Read at | Purpose |
|---|---|---|
| `DEBUG_LOG_BRIDGE_PAYLOAD` | `routes.py:49` | Module-import-time flag; truthy values `true`/`1`/`yes` (lowercased). Gates the full-payload debug dump at `routes.py:276-283` |
| `MCP_CONNECT_DEFAULT_TIMEOUT` | `routes.py:46` | Default request timeout ms (default `120000`); overridable per-request by the `?timeout=` query param (bounded `0 < t <= 300000`) |
| `ACCESS_TOKEN` | auth dependency (`verify_token`) | Bearer token. **Auth is a no-op when unset** — per `AGENTS.md` |
| `LOG_LEVEL` | `utils/logger.py` `get_log_level:157` | When `"debug"`, `format_error_response` adds a `stacktrace` to the HTTP error body (`routes.py:106-109`) |
| `LOG_FORMAT` | `utils/logger.py` | `json` or text output |
| `MCP_CONNECT_CLIENT_CACHE_TTL` | `cache.py:100` | Cached-client TTL in ms (default `300000` → 300s) |
| `MCP_CONNECT_CACHE_CLEANUP_INTERVAL` | `main.py` cleanup scheduler | Sweep interval for expired clients |
| `MCP_CONNECT_INIT_TIMEOUT` | `single_usage.py:45`, `managed.py:41` | Session `initialize()` timeout (default `30000` ms) |
| `MCP_CONNECT_HTTP_TIMEOUT` | `single_usage.py:46`, `managed.py:42` | HTTP transport timeout (default `30000` ms) |
| `MCP_CONNECT_SSE_READ_TIMEOUT` | `single_usage.py:47`, `managed.py:43` | SSE read timeout (default `300000` ms) |
| `MCP_CLIENT_NAME` | `client_info.py:30` | Client `Implementation.name` sent at handshake and the injected `User-Agent` (default `mcp-bridge`) |
| `PORT` | `main.py:166` | Listen port (default `3000`) |
| `AWS_SERVICE`, `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` | `utils/signer.py:33-63` | Read from the **request's `env` dict**, not the process environment, for SigV4 signing |

### Configuration Files

- `pyproject.toml` — dependency constraints (including the `mcp` pin, most recently moved to 1.30.0 by commit `602ec8d`), `[tool.pytest.ini_options]` (`asyncio_mode`, `testpaths`, `python_files`, `markers`, `addopts`), mypy/black/ruff settings, and the binding `[tool.pip-licenses]` allow list.
- `poetry.lock` — never regenerate or hand-edit; targeted updates only, committed alongside the manifest.
- `README.md` — the only user-facing `/bridge` documentation. **It contains no per-field request-body schema table.** The body is documented purely by JSON examples: `README.md:181-189` (single-usage example with `serverPath`/`method`/`args`/`params`/`single_usage`) and `README.md:215-237` (CodeMie assistant MCP-server config with `command`/`args`/`env`/`auth_token`). There is no existing list of optional fields such as `user_id` or `request_headers` to append to.
- `deploy-templates/` — the Helm chart deploying the root `Dockerfile` image.

### Feature Flags and Deployment Concerns

- `DEBUG_LOG_BRIDGE_PAYLOAD` is the only feature-flag-like toggle on this path, and it is **evaluated once at module import** — flipping it requires a process restart, and it cannot be toggled per-test without patching the module attribute.
- There is no per-tenant or per-request flag mechanism; behaviour is switched by request fields (`single_usage`, `http_transport_type`) or process env only.
- Secrets reach the service two ways — the `ACCESS_TOKEN` bearer for inbound auth, and per-request `env` / `mcp_headers` / `request_headers` carrying downstream credentials. Both are masked at log sites rather than scrubbed from the data.
- No CI pipeline exists in this repository. `mypy --strict`, ruff, black, pytest and gitleaks are enforced only by the local pre-commit gate run; nothing re-checks after merge.

---

## 6. Risk Indicators

Predictions and design statements are confined to this section and prefixed `Speculative:`.

1. **`tests/conftest.py:80` `single_usage_side_effect(request, method, params, timeout_ms)` is a fixed-arity positional function.** It is the `side_effect` of the `AsyncMock` replacing `execute_single_usage_request` for the whole endpoint test suite. *Speculative:* if the route layer starts passing an additional argument to `execute_single_usage_request`, this side_effect raises `TypeError` and every single-usage endpoint test in `test_bridge_validation.py` fails at once, with a failure message that points at the fixture rather than at the change. This is the highest-probability source of a confusing red suite.

2. **`test_mcp_methods.py` pins `session.call_tool` call shape exactly.** Lines 94, 106, 117 and 128 all use `assert_awaited_once_with("<tool>", {...})` with two positional args and no kwargs. *Speculative:* any change that makes `call_tool` receive an extra keyword — even `meta=None` passed unconditionally — invalidates all four assertions. Passing the kwarg only when a value is present keeps them green; passing it always does not.

3. **`routes.py:276-283` masks by hardcoded key name over a full `model_dump`.** Only `request_headers` and `env` are handled; every other key in the dump is logged verbatim. Any field added to `BridgeRequestBody` is logged in the clear under `DEBUG_LOG_BRIDGE_PAYLOAD` unless this block is extended. The block has **no test coverage**, so a miss here is silent. This is the sharpest live risk in the whole area: it is a data-exposure path, it is untested, and it is opt-in-by-env so it will not show up in normal runs.

4. **`SENSITIVE_PATTERNS` (`masking.py:22`) is shared between header masking and arbitrary tool-argument masking.** `is_sensitive_key` feeds both `mask_dict_values` and `_mask_params_recursive`, the latter applied to every `tools/call` argument dict. Widening the regex to catch personal-data key names would redact legitimate tool arguments — `name` in particular is a common tool-argument key. `test_masking.py:67` already asserts a specific non-sensitive set (`content-type`, `accept`, `host`, `user-agent`, `connection`) that a widened pattern could break.

5. **No partial-masking helper exists.** `mask_dict_values` and `mask_sensitive_headers` are flat `dict[str, str]` → `dict[str, str]` and produce only the all-or-nothing `REDACTED_VALUE`. The only recursive masker, `_mask_params_recursive`, is private to `methods.py` and lives in the client layer rather than `utils/`. *Speculative:* a masker that preserves some keys, redacts others, and partially redacts a third group would be a genuinely new shape for this module, not a variation on an existing one — and would want its own test block since `test_masking.py` has no precedent for nested or partial cases.

6. **Two branches must be changed in lockstep, and only one of them is reachable in the default configuration.** The single-usage branch (`single_usage: true`) is a completely separate three-transport path. *Speculative:* threading a value through the cached branch alone would produce a change that works in default deployments and silently drops the value for single-usage callers, with no test failure — because no test asserts what the route handlers pass downstream.

7. **`invoke_mcp_method` is reached through function-local imports.** `single_usage.py:149` and `:214` do `from .methods import invoke_mcp_method` inside the function body to break a cycle. Any test that patches this must target `src.mcp_connect.client.methods.invoke_mcp_method`, as the existing tests do; patching the `single_usage` namespace silently does nothing.

8. **`generate_cache_key` is safe by construction but unpinned by any negative test.** The five-key allowlist at `cache.py:223-229` means a new model field cannot leak into the key accidentally. There is, however, no test that would fail if someone later added one — the task's requirement to pin this has no existing pattern to copy.

9. **`AGENTS.md` classifies `/bridge` schema changes as "Ask first."** "Deployed clients depend on it." Any modification to `BridgeRequestBody` sits in the explicit review-required band regardless of backward compatibility.

10. **The `extra="forbid"` → HTTP 400 mapping runs through `main.py:223`, not the model.** The 400 (rather than 422) depends on the exception handler matching `type == "extra_forbidden"` in `exc.errors()`. `test_bridge_validation.py:97` pins this. The EPMCDME-13546 regression guard therefore has two moving parts — the model config and the handler — and only the pair together produces the observed behaviour.

11. **`mypy --strict` with no CI.** A typing regression on a `dict[str, Any] | None` field or on a threaded optional parameter is caught only if the local gate is actually run. `AGENTS.md`: "There is no CI to catch it later."

12. **The `README.md` pre-merge chain at lines 153-161 cannot pass as written.** It includes `poetry run pytest tests/ -m integration`, which collects nothing and exits 5, and it is a single `&&` chain that reports only the first failure. `quality-gates.md` documents this trap; the README was not corrected. Anyone following the README to prove the change is green will get a false red.

13. **`README.md:51` states "MCP Python SDK v1.21.0+"** while the pin was moved to `mcp` 1.30.0 in commit `602ec8d`. The README's stack section is already stale on the exact dependency whose API this task depends on.

14. **The SDK signature quoted in the task could not be verified on disk.** No `mcp/client/session.py` was reachable under the project tree (the virtualenv is not inside the repo or not visible to the file tools). The `call_tool` `meta` kwarg and the `list_tools` lack of one are taken from the task description, not confirmed against the installed package. Per `AGENTS.md` § Working agreements, library APIs are to be verified against current documentation (context7 MCP) rather than memory before code is written.

15. **`routes.py:303-306` serializes the result with `model_dump(mode="json", exclude_none=True)` guarded by `hasattr(result, "model_dump")`.** Response shape is derived from whatever the SDK returns; `test_bridge_validation.py` has a `test_null_fields_excluded_from_response` case pinning the `exclude_none` behaviour. Changes affecting what `call_tool` returns would surface here.

16. **`apply_substitutions` is called twice on two different paths** — `manager.py:157` for the cached branch and `single_usage.py:88` for the single-usage branch — each producing its own `model_copy(deep=True)`. A new field is carried through untouched by the three-field allowlist at `substitution.py:122-143`, but the deep copy means the object reaching the transport helpers is not the object the route handler holds.

---

## 7. Summary for Complexity Assessment

**Layers and file surface.** The task crosses all four layers of the service. The verified call
chain from `bridge_endpoint` (`routes.py:241`) to the sole `session.call_tool` invocation
(`methods.py:102`) forks into two independent branches that reconverge only at `invoke_mcp_method`:
a cached branch of two intermediates (`_handle_cached_client_request:162` → `invoke_with_timeout`
`manager.py:39`) and a single-usage branch of two-plus-one (`_handle_single_usage_request:122` →
`execute_single_usage_request` `single_usage.py:50` → one of `_execute_stdio_request:114` /
`_execute_http_request:197` / `_execute_sse_request:262`). Every line and symbol reference in the
task's planned change surface was verified correct against current source, including the
`routes.py:205` call site, the `routes.py:276-283` debug block, `cache.py:210`,
`substitution.py:82`, and `methods.py:103-117`. One structural finding materially reduces scope
versus the task's stated uncertainty: **`managed.py` / `ManagedClient` has no parallel invocation
path.** `_run_stdio_client:227`, `_run_streamable_http_client:264` and `_run_sse_client:296` build
the transport, initialize the session, publish it through `ready_future`, then park on
`cleanup_event.wait()` — none of them ever calls `invoke_mcp_method` or `session.call_tool`. Per-request
invocation happens in the caller's task using the session handed out by `get_or_create_client`, so
`managed.py` sees no per-request data and needs no threading. The touched-file set is therefore the
six source files named in the task plus `tests/conftest.py`, whose fixed-arity `single_usage_side_effect`
sits directly on the changed signature.

**Technical novelty and constraints.** The mechanics are conventional for this codebase — an
optional Pydantic field, a threaded optional parameter, one new branch condition in an existing
if-chain. Three properties of the surrounding code make it easier than it looks: `generate_cache_key`
(`cache.py:223-229`), `apply_substitutions` (`substitution.py:122-143`) and `extract_request_context`
(`context.py:61-68`) are all explicit field allowlists rather than reflective dumps, so a new model
field is inert in all three by construction. The genuinely novel element is the masking work: the
`utils/masking.py` module is 91 lines exporting four flat `dict[str, str]` → `dict[str, str]`
functions with no recursion, no nesting, and no partial-redaction capability anywhere, and the one
recursive masker in the repo (`_mask_params_recursive`) is private to `methods.py` in a different
layer. A masker with per-key policy and partial redaction would be a new shape for this module. The
`SENSITIVE_PATTERNS` coupling the task flags is real and confirmed: `is_sensitive_key` feeds both
header masking and arbitrary tool-argument masking. Two facts remain unverified and should be
settled before implementation — the `mcp` SDK `call_tool` signature could not be read from disk (no
`mcp/client/session.py` reachable under the project tree), and `README.md:51` already misstates the
SDK version as 1.21.0+ against a 1.30.0 pin.

**Test posture and risk concentration.** The suite is broad — 20+ files, pytest with
`asyncio_mode = "auto"` — and each layer has an established mocking idiom to copy: the `session`
fixture with per-method `AsyncMock`s in `test_mcp_methods.py:29`, `FakeContext`/`DummySession` with
`invoke_mcp_method` patched at its defining module in `test_single_usage.py`, the
`make_capturing_session_class` kwarg-capture pattern in `test_client_name.py:45`, and ASGI-level
`async_client.post("/bridge", ...)` in `test_bridge_validation.py`. Coverage stops precisely where
this task works, though. The three route handlers have **no direct tests** (codegraph: "no tests
found within 3 caller hops"), so nothing today asserts what they pass downstream. The
`DEBUG_LOG_BRIDGE_PAYLOAD` block has **zero coverage** and is read once at module import, making it
awkward to test and easy to miss — and it is the one place where a new top-level field would be
logged in the clear, which makes it the sharpest live risk in the area. There is no precedent for a
negative cache-key test. Two brittleness points will bite mechanically if unaddressed:
`conftest.py:80`'s four-positional-arg side_effect, which would `TypeError` the whole endpoint
suite, and the four `assert_awaited_once_with("<tool>", {...})` assertions in `test_mcp_methods.py`
that pin `call_tool`'s exact two-positional call shape. Both are cheap to handle once known and
confusing to diagnose if not. Governance adds friction rather than complexity: `AGENTS.md` puts
`/bridge` schema changes in the "Ask first" band, `mypy --strict` is enforced only locally with no
CI, and the `README.md:153-161` pre-merge chain cannot pass as written because it includes an
integration selector that exits 5.

---

## 8. External References

The task named one external reference: **`EPMCDME-13260-mcp-connect-task.md`** at the repository
root — described as "Full pre-written breakdown," with the explicit instruction *"NOTE it is
currently stashed (git stash@{0}) so it is not on disk right now; do not try to read it."*

- **Resolved path**: `C:\Users\Yauheni_Hil\repos\codemie-dev\codemie-mcp-connect-service\EPMCDME-13260-mcp-connect-task.md`
- **Resolved**: No — absent from the working tree, confirmed by glob (`EPMCDME-13260*.md` → no
  matches), consistent with the stated stash state and with the clean `git status` on `main`. Not
  read, per the task's explicit instruction.
- **Impact on this research**: none material. The task description itself carries the contract, the
  planned change surface, the hard constraints and the masking requirement inline, and **every
  file, symbol and line reference it asserts was independently verified against current on-disk
  source** (see Section 2). The stashed document is a superset narrative, not a source of facts
  this analysis lacks.
- **Facts downstream stages need from it** — all already stated verbatim in Section 1 and verified
  in Section 2, so no stage needs to recover the file: the namespaced `_meta` key is
  `codemie.ai/user-context`; translation applies to `tools/call` only, because
  `ClientSession.list_tools` has no `meta` kwarg; `user_context` is typed as a permissive
  `dict[str, Any] | None` rather than a typed model, deliberately, so backend profile-field changes
  never force a lockstep release here; `extra="forbid"` stays; `user_context` must not enter
  `generate_cache_key`; no `$env`/`$headers` substitution applies to it; the EPMCDME-11351
  `McpError` → `isError` mapping must be undisturbed; absent field ⇒ no meta ⇒ byte-identical
  behaviour. Masking policy: mask `email`, `name`, `picture`, partially mask `username`; keep `id`,
  `roles`, `is_admin`, `is_maintainer`, `is_auditor`, `user_type`, `project_names`,
  `admin_project_names` readable; mask defensively — any nested dict or unrecognised key wholesale;
  do not widen `SENSITIVE_PATTERNS`.
- **If a later stage does need the original**, it is recoverable without guesswork via
  `git stash show -p stash@{0}` or `git stash list`. No transcription risk needs to be carried
  forward.
