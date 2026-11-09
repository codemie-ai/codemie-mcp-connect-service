# Technical Research

**Task**: mcp-client session-initialize tools-list bridge-response
**Generated**: 2026-09-08
**Research path**: filesystem (codegraph MCP not reachable from this agent's tool set; orientation pass + 3 parallel Explore threads)

---

## 1. Original Context

EPMCDME-14217 (part 1 of 2, repository codemie-mcp-connect-service). An MCP server returns server-side `instructions` in its `InitializeResult`, but mcp-connect throws them away: the return value of `session.initialize()` is discarded in all 7 call sites (src/mcp_connect/client/managed.py:248,282,317 and src/mcp_connect/client/single_usage.py:67,146,211,284), and the word `instructions` does not appear anywhere in src/.

Required change: capture the `InitializeResult` at handshake time, store its `instructions` next to the session (ManagedClient plus the single-usage path; sessions are cached in client/cache.py), and return it in the response to the `tools/list` method (method routing at src/mcp_connect/client/methods.py:83, response serialization at src/mcp_connect/server/routes.py:303).

Backward compatible: a server with no instructions → the field is absent from the response → behavior unchanged.

The consumer is the codemie backend (separate paired MR) which will add the field to `MCPListToolsResponse` and inject the text into the assistant system prompt.

Jira: https://jiraeu.epam.com/browse/EPMCDME-14217

Focus areas requested: ManagedClient / single-usage lifecycle and where a captured InitializeResult could live; cache key/eviction impact; managed vs single-usage divergence; how the `tools/list` bridge response is built and serialized and the cleanest backward-compatible way to attach an extra field to a raw SDK `ListToolsResult` dump, including pagination; whether the MCP SDK exposes the InitializeResult after `initialize()`; existing test structure and fake-session patterns; any response-model/validation layer that strips unknown fields; project conventions from `.ai-run/guides/`.

---

## 2. Codebase Findings

### Existing Implementations

Confirmed baseline: the only occurrence of the string `instructions` anywhere in the repo is the SDLC run's own `.state.json`. There is **no prior art** — this is a greenfield field on an existing hot path.

- `src/mcp_connect/client/managed.py:46` — `@dataclass ManagedClient`; fields `session`, `_cleanup_event`, `_task`, `_ready_future`. No defaults today.
- `managed.py:78` — `async def spawn(cls, request: BridgeRequestBody) -> ManagedClient`; creates a task running `_run_client_lifecycle` and awaits `ready_future` with a hardcoded 30s at `managed.py:103` (distinct from `INIT_TIMEOUT_SECONDS`).
- `managed.py:96` — `ready_future: asyncio.Future[ClientSession]`, the **only** channel out of the lifecycle task.
- `managed.py:245-256 / 279-290 / 309-325` — stdio / streamable-http / sse lifecycle bodies. `await asyncio.wait_for(session.initialize(), ...)` at **248, 282, 317** with the result discarded; `ready_future.set_result(session)` at **251, 285, 320**.
- `src/mcp_connect/client/single_usage.py:50` — `execute_single_usage_request(request, method, params, timeout_ms) -> Any`, the single funnel; routes to transports at 102/104/106.
- `single_usage.py:114 / 197 / 262` — `_execute_stdio_request`, `_execute_http_request`, `_execute_sse_request`. `initialize()` discarded at **146, 211, 284**; `invoke_mcp_method(...)` at **153, 218, 291** with the result returned at **152, 217, 290**.
- `src/mcp_connect/client/manager.py:118` — `get_or_create_client(request) -> tuple[ManagedClient, ClientSession]`; `manager.py:39` — `invoke_with_timeout(session, method, params, timeout_ms)`.
- `src/mcp_connect/client/methods.py:54` — `invoke_mcp_method(session, method, params) -> Any`; the tools/list branch is at **83-85**.
- `methods.py:280-296` — `_call_with_optional_cursor`, shared by tools/list, prompts/list, resources/list, resources/templates/list.
- `src/mcp_connect/server/routes.py:240-314` — `/bridge`; `routes.py:122` `_handle_single_usage_request`; `routes.py:162` `_handle_cached_client_request`.
- `src/mcp_connect/client/cache.py:103` — the cache dict; `cache.py:210` — `generate_cache_key`.
- `src/mcp_connect/client/transports.py:40` — `get_transport_ctx` (stdio / streamable-http / sigv4 / sse).
- `src/mcp_connect/client/types.py:33` — `MCPClientHandle` dataclass. **Dead for this flow**: not used by the managed or single-usage paths, only by legacy cleanup helpers. Do not add the field here despite the name suggesting otherwise.
- `src/mcp_connect/models/request.py:24` — `BridgeRequestBody`, `extra="forbid"`. Request-side only.

### Architecture and Layers Affected

Per `.ai-run/guides/architecture/architecture.md` and `CONTRIBUTING.md`, the stack is *FastAPI routes → bridge layer → MCP transport*. The change touches all three:

- **API / route layer** — `server/routes.py` (response assembly and serialization at 303-306; `_handle_cached_client_request` at 162 already binds the `ManagedClient` as `handle` at `routes.py:179` and currently ignores it).
- **Bridge / method-dispatch layer** — `client/methods.py` (`invoke_mcp_method`, the only place that knows the method is `tools/list`).
- **Client-lifecycle layer** — `client/managed.py` (pooled) and `client/single_usage.py` (stateless), plus `client/manager.py` as the managed-path facade.
- **Cache layer** — `client/cache.py` is affected only by reference: the cached value type is `ManagedClient`, so a new field rides along for free. No cache-layer code change is expected.

No DB, no persistence, no auth layer involvement.

### Integration Points

- **Upstream**: arbitrary MCP servers over stdio / streamable-http / sse / sigv4-signed http.
- **SDK**: `mcp` **exact-pinned at 1.28.1** (`pyproject.toml`, `poetry.lock` 706-708) with comment `# Security (EPMCDME-13569): pin >=1.28.1 to fix CVE-2026-52869, CVE-2026-52870, CVE-2026-59950`. mypy has `ignore_missing_imports` for `mcp`, `mcp.*` — so `InitializeResult` is untyped to mypy and must be annotated explicitly at capture sites.
- **Downstream consumer**: the codemie backend, paired MR, will add the field to `MCPListToolsResponse`. Cross-repo coupling — the two MRs must agree on the exact JSON key and nesting.
- **Cache tuple is read outside the cache module**: `main.py:61` destructures `for key, (_, last_used_at) in ...`, and `main.py:47-124` reaches into `cache._cache` / `cache._lock` / `cache._ttl` directly. The 2-tuple shape is load-bearing.

### Patterns and Conventions

- `ManagedClient` is a `@dataclass` constructed **positionally** at `managed.py:127`. A new field must be defaulted and last (or keyword-only), otherwise construction breaks.
- The single value crossing the task boundary is `ready_future`, typed in six places: `managed.py:76, 96, 169, 230, 267, 299`. Widening it to `tuple[ClientSession, InitializeResult | None]` is a coordinated six-site change; `set_exception` paths at `managed.py:216, 222` must stay consistent.
- Domain exceptions come from `utils/errors.py`; logging via `utils/logger.py`; context via `utils/context.py`; secret masking via `utils/masking.py`. Python 3.12 built-in generics only (`str | None`, never `typing.Optional`). All I/O async. Every function annotated.
- Config is bare `os.getenv` at module import time — there is no `settings.py` and no pydantic `BaseSettings`.

---

## 3. Documentation Findings

### Guides and Architecture Docs

`.ai-run/guides/` exists — 11 files, ~1915 lines.

- `README.md` — index; read only the row matching the task. A command is documented only if it was executed and its exit code observed.
- `project.md` — Jira key `EPMCDME`; remote `gitbud.epam.com/epm-cdme/codemie-mcp-connect-service`; target branch `main`; MR via `glab` through the `.claude/skills/gitlab-mr` skill.
- `quality-gates.md` — authoritative gate list (below). Rules: run gates one at a time, never as an `&&` chain; "a gate that could not run is not a gate that passed"; a test deleted or weakened to make a gate pass has failed the gate; never `rm poetry.lock`.
- `development/development-practices.md` — TDD workflow; MANDATORY context7 lookup before implementing any library feature, explicitly including the MCP SDK; PROHIBITED to write summary/validation/status documents after implementation; perf SLA ≤100ms for cached clients; backward-compatible API contract.
- `testing/testing-patterns.md` — unit tests in `tests/test_*.py`, fixtures in `tests/conftest.py`; `asyncio_mode = "auto"` so async tests need no decorator; mock the MCP SDK in unit tests (no real servers/subprocess/network); all new code needs tests, 100% on critical paths including client lifecycle and MCP protocol calls; `tests/integration/` is empty scaffolding and `pytest -m integration` exits 5 — not a gate.
- `standards/git-workflow.md` — branch `EPMCDME-XXXX[_-]short-description`; commit `EPMCDME-XXXX: Imperative description` (<72 chars); squash merge; one logical change per commit; conventional scopes include `bridge`, `cache`, `api`, `transport`, `config`, `docs`.
- `architecture/architecture.md`, `setup.md`, `security/README.md` (CVE workflow, `# Security (EPMCDME-...)` pin comments), `build/README.md`, `build/dependencies.md`.

Prior SDLC run artifacts are direct precedent: `docs/superpowers/tasks/2026-08-05-user-agent-header-mcp-client-name/` touched the same handshake area (`client_info`), and `2026-08-14-bridge-500-error-on-tool-execution/` touched the bridge response path. Each contains `technical-analysis.md`, `plan.md`, `qa-report.md`, `code-review-final.json`, `gate-plan.json`.

### Architectural Decisions

No ADR directory. The binding recorded decisions live in `AGENTS.md` (`CLAUDE.md` and `GEMINI.md` are `@AGENTS.md` shims):

- **"Ask first: Changing the `/bridge` request or response schema. Deployed clients depend on it."** This change is a `/bridge` response-schema change and therefore sits on an explicit approval boundary. Keeping it strictly additive and optional is what makes it defensible, but the gate still applies.
- Always: `EPMCDME-NNNNN:` on branch and commit; manifest + lock in the same commit; security pins keep their comment; `mypy --strict` stays clean — "there is no CI to catch it later".
- Never: regenerate or hand-edit `poetry.lock`; relax a `# Security (EPMCDME-...)` pin; fix a language-package CVE in the Dockerfile.
- `CONTRIBUTING.md` — conventional commits `feat(bridge): ...`; PR title same format; ≥1 approval; Apache 2.0 header required on all source files.

No `TODO`/`HACK`/`FIXME`/`NOTE` markers exist in `src/mcp_connect/client/` or `server/routes.py` (grep returned zero).

### Derived Conventions

Docs to update for a user-visible change: `README.md` (env table ~line 500, `tools/list` example ~line 184) and `.env.example`. Nothing else — post-implementation summary documents are prohibited by the development guide.

### External Documentation Findings

The authoritative source here is the installed SDK itself, read verbatim at `~/.cache/uv/archive-v0/MvD-4GIpnEhwYlsz/lib/python3.13/site-packages/mcp/` (mcp 1.28.1):

- `mcp/types.py:691-699` — `class InitializeResult(Result)` with `protocolVersion: str | int`, `capabilities: ServerCapabilities`, `serverInfo: Implementation`, and **`instructions: str | None = None`**. Confirmed optional.
- `mcp/client/session.py` — `async def initialize(self) -> types.InitializeResult` **returns** the result, but retains almost nothing: only `self._server_capabilities = result.capabilities` (session.py:205), then `return result`. The `__init__` attribute list (~145-155) has no `_init_result`, no `server_info`, no `instructions`; grep for `instructions|serverInfo|server_info` over that file returns zero hits. The only accessor is `get_server_capabilities()`.
  **Conclusion: the return value of `initialize()` is the only way to obtain instructions. Discarding it is unrecoverable short of re-initializing.**
- `mcp/types.py:141` — `Result` (base of `ListToolsResult`) declares `model_config = ConfigDict(extra="allow")`. Under pydantic 2.12.4, assigning `result.instructions = "..."` lands in `__pydantic_extra__` and **is** emitted by `model_dump(mode="json")`.

Note: `development-practices.md` requires a context7 lookup before implementing any MCP SDK feature. That obligation is not discharged by this analysis and should be carried into the implementation phase.

---

## 4. Testing Landscape

### Existing Coverage

24 test modules under `tests/`. Directly relevant:

- `tests/test_bridge_validation.py` — `/bridge` request validation and **the only test asserting real pydantic serialization of `ListToolsResult`** (`test_null_fields_excluded_from_response`, line 155, covering `exclude_none`).
- `tests/test_mcp_methods.py` — `invoke_mcp_method` routing for every method, including tools/list cursor handling. 24 tests, all driven by a duck-typed `FakeSession` (`test_mcp_methods.py:29`).
- `tests/test_single_usage.py` — `execute_single_usage_request` transport routing (stdio/http/sse), timeouts, downstream errors.
- `tests/test_managed_lifecycle_errors.py` — `ManagedClient.spawn`/`cleanup` error, timeout and cancellation paths; the only place the `initialize()` timeout is exercised.
- `tests/test_client_name.py` — `MCP_CLIENT_NAME` → `client_info` forwarded to `ClientSession` in both single_usage and managed. Closest precedent for a handshake-level change.
- `tests/test_user_agent_header.py` — User-Agent injection in managed + single_usage + sigv4; drives managed statics directly.
- `tests/test_cache.py`, `test_cache_cleanup.py`, `test_client_manager_cache.py`, `test_ping_validation.py` — TTL, sliding window, eviction, ping liveness.
- `tests/test_timeout.py` — default/override timeout across all methods over HTTP (all-method loop at :249).
- `tests/test_main_error_handling.py`, `test_error_responses.py`, `test_auth.py`, `test_health.py`, `test_graceful_shutdown.py`, `test_transports.py`, `test_substitution.py`, `test_masking.py`, `test_logger.py`, `test_context_propagation.py`, `test_process_output.py`, `test_types_cleanup_errors.py`.
- `tests/integration/__init__.py` — **empty scaffold, zero integration tests**.

### Testing Framework and Patterns

pytest 8.4.2 (`pytest = "<9"`), pytest-asyncio 1.2.0 with `asyncio_mode = "auto"`, pytest-cov 7.0.0, httpx 0.28.1, anyio 4.11.0 (transitive). `testpaths = ["tests"]`, `addopts = "-m 'not integration'"`. No respx, no pytest-mock, no trio.

Key fixtures:

- `async_client` (`tests/conftest.py:29`) — `httpx.AsyncClient` over `ASGITransport(app=app)`.
- `mock_mcp_client` (`tests/conftest.py:42`) — **the central seam**. Patches both `mcp_connect.server.routes.get_or_create_client` (returns a `(mock_handle, session)` tuple) and `mcp_connect.server.routes.execute_single_usage_request`. The session is a `MagicMock` whose per-method `AsyncMock`s return plain dicts `{"result": "<method>"}`.
- `session` (`tests/test_mcp_methods.py:29`), `cache` (`test_client_manager_cache.py:31`), `mock_client_handle` (`test_client_manager_cache.py:41`), `stdio_request`/`http_request` (`test_managed_lifecycle_errors.py:29,39`).

The dominant seam for handshake changes is `monkeypatch.setattr("src.mcp_connect.client.<module>.ClientSession", DummySession)` plus a hand-rolled fake transport context manager. Verbatim, `tests/test_single_usage.py:46-74`:

```python
class DummySession:
    def __init__(self, read, write, client_info=None): ...
        self.list_tools = AsyncMock(return_value={"tools": []})
    async def __aenter__(self) -> DummySession: return self
    async def __aexit__(self, *_): self.exited = True
    async def initialize(self) -> None:
        self.initialized = True
```

**Every fake `initialize()` in the suite returns `None` today.** Fakes needing updates: `DummySession` (`test_single_usage.py:46`), `CapturingSession` (`test_client_name.py:47`, `self._inner.initialize = AsyncMock()`), `DummySession`/`_make_async_mock_session` (`test_user_agent_header.py:103,116`).

Managed-path tests drive the statics directly and assert on `ready_future` — e.g. `test_user_agent_header.py:150-160` does `asyncio.create_task(ManagedClient._run_streamable_http_client(request, cleanup_event, ready_future))` then `await asyncio.wait_for(asyncio.shield(ready_future), 5.0)`. **If `ready_future` starts carrying a tuple, these break.**

Route-level tests assert dict-equality on JSON (`response.json() == {"result": "tools/list"}`) — `test_bridge_validation.py:117,141` and `test_timeout.py:249`. Adding a key to the tools/list body breaks them unless the stubs are updated.

Invocation: `poetry run pytest` (or the `poetry run test` alias → `scripts/tooling.py:run_test`); coverage run ~90s. `Makefile` has only a `gitleaks` target. **No CI pipeline exists** — `.github/` holds only issue/PR templates; no workflows, no `.gitlab-ci.yml`. Gates are manual.

### Coverage Gaps

- **The initialize return value is entirely uncovered.** Nothing asserts an `InitializeResult` is produced, stored, or that any of its fields survive. Only the timeout/error path around `asyncio.wait_for(session.initialize(), ...)` is tested.
- **`tools/list` response shape is thinly covered.** One real-serialization test (`test_bridge_validation.py:155`); everything else asserts a stub dict. No test covers the plain-dict branch of `hasattr(result, "model_dump")` at `routes.py:303` merging anything extra.
- **No cache test asserts per-entry metadata beyond the handle.** Nothing verifies that a cache *hit* still yields what initialize produced — i.e. that instructions are persisted rather than re-derived.
- No end-to-end test against a real MCP server, so the handshake is never validated against real SDK types. A single `@pytest.mark.integration` test with an in-process FastMCP server declaring `instructions=` would close this, at the cost of populating a currently-empty scaffold.

---

## 5. Configuration and Environment

### Environment Variables

All read via bare `os.getenv` at module import; there is no central settings object.

- `MCP_CONNECT_INIT_TIMEOUT` (30000ms) — `managed.py:41`, `single_usage.py:45` as `INIT_TIMEOUT_SECONDS`. **This is the timeout wrapping the exact `initialize()` calls being changed.**
- `MCP_CONNECT_CLIENT_CACHE_TTL` (300000ms) — `cache.py:100`.
- `MCP_CONNECT_DEFAULT_TIMEOUT` (120000ms) — `routes.py:46`.
- `MCP_CONNECT_CACHE_CLEANUP_INTERVAL` (60000ms) — `main.py:107`.
- `MCP_CONNECT_HTTP_TIMEOUT` (30000ms), `MCP_CONNECT_SSE_READ_TIMEOUT` (300000ms) — `transports.py:77,86,95`, `managed.py:42`, `single_usage.py:46`.
- `MCP_CLIENT_NAME` (default `mcp-bridge`) — `client_info.py:30`; undocumented in `.env.example`/README.
- `ACCESS_TOKEN` — `middleware.py:43`. `LOG_LEVEL`, `LOG_FORMAT` — `utils/logger.py`. `DEBUG_LOG_BRIDGE_PAYLOAD` — `routes.py:49`. `PORT` — `main.py:166`.
- No pool-size or session-limit variable exists.

### Configuration Files

- `pyproject.toml` — deps plus all tool config (mypy strict; black/ruff line-length 120; pytest markers; pip-licenses allow-list).
- `.env.example` (13 vars) and `README.md` lines 500-507 (env reference table) must both be updated if a var is added.
- `Makefile` (only `gitleaks`), `Dockerfile`, `start.sh`, `uv-constraints.txt`.
- `deploy-templates/` Helm chart. Env injection is generic (`values.yaml` `env:` list → `statefulset.yaml:66-69` `toYaml`), so a new env var needs no template change. No raw k8s manifests.

### Feature Flags and Deployment Concerns

Only `DEBUG_LOG_BRIDGE_PAYLOAD` (a bool-env parsed via `in ("true","1","yes")` at `routes.py:49`) and the per-request `single_usage` flag in `models/request.py`. There is no flag framework; the `routes.py:49` bool-env pattern is the precedent if this feature needs a kill switch. No deployment change is expected unless a toggle is introduced.

Quality gates that must pass (run individually, all exit 0):

1. `poetry check --lock`
2. `poetry run ruff format` (mutating; use `--check` to assert)
3. `poetry run ruff check`
4. `poetry run mypy src/`
5. `poetry run black --check src/ tests/`
6. `poetry run pytest tests/ --cov=src --cov-report=term-missing`
7. `make gitleaks`

Known non-gates that look like gates: `pytest -m integration` (exit 5, empty), `pip-licenses --allow-only` (exit 1 on dev dep `filelock`), `pre-commit run --all-files` (no `.pre-commit-config.yaml` exists despite the dev dep).

---

## 6. Risk Indicators

- **`/bridge` response-schema change sits on an explicit AGENTS.md "Ask first" boundary.** Deployed clients depend on this contract. Approval is required even though the change is additive.
- **The `initialize()` return value is the only source of instructions** (SDK stores nothing; verified in mcp 1.28.1 `client/session.py`). There is no fallback accessor — if capture is missed on one transport, that transport silently returns no instructions with no error.
- **Seven call sites across two files and three transports must change together.** An incomplete `ready_future` retype (`managed.py:76, 96, 169, 230, 267, 299` plus `set_exception` at 216, 222) deadlocks `spawn` behind its hardcoded 30s timeout at `managed.py:103`.
- **`ManagedClient` is a positionally-constructed `@dataclass`** (`managed.py:127`) with no defaults. A new field inserted in the wrong position breaks construction.
- **Cache-tuple shape is load-bearing outside the cache module** — `main.py:61` destructures `(_, last_used_at)`, and `main.py` touches `cache._cache`/`_lock`/`_ttl` directly. Instructions must ride on `ManagedClient`, not on the tuple.
- **Attach-helper must tolerate non-pydantic results.** `tests/conftest.py:44` makes `session.list_tools` return a plain dict, and `routes.py:303` already branches on `hasattr(result, "model_dump")`. A helper that assumes a pydantic model breaks roughly nine test files.
- **Risk of leaking the field onto the wrong result type.** `EmptyResult`, ping results and others also subclass `Result` with `extra="allow"`; only `tools/list` may receive it.
- **`exclude_none=True` at `routes.py:304`** silently drops `instructions: null`. That is the desired backward-compatible behavior, but it means the contract cannot express an explicit null — and flipping the flag globally would alter every other response.
- **Managed and single-usage must emit identical JSON**, or clients see a shape that varies with the `single_usage` request flag. Single-usage re-initializes per request, so it re-fetches instructions every call (functionally fine, slightly wasteful).
- **Pagination**: `tools/list` supports `cursor` (`methods.py:280-296`) and returns `nextCursor`, so a cached session can be hit repeatedly. Instructions are per-session, not per-page. Whether to attach on every page or only when `cursor` is absent is an unresolved product decision that the spec must pin down.
- **`MCPClientHandle` (`client/types.py:33`) is a decoy** — its name suggests it holds session state, but it is dead in both live paths. Adding the field there would produce a change that passes review and does nothing.
- **mypy `--strict` with `ignore_missing_imports` for `mcp.*`** means `InitializeResult` is untyped; annotations must be explicit or the gate will not catch a wrong-typed capture.
- **No CI exists.** Nothing catches a missed gate after merge; all seven gates are manual.
- **Cross-repo coupling**: the codemie backend MR must agree on the exact key name and nesting. No shared contract artifact exists between the repos.
- **Zero integration coverage** of a real handshake; the change will be validated entirely against hand-rolled fakes unless an integration test is added.
- `development-practices.md` mandates a context7 lookup before implementing any MCP SDK feature — an obligation carried forward, not discharged here.

---

## 7. Summary for Complexity Assessment

This task touches four layers — client-lifecycle (managed and single-usage), bridge method dispatch, route serialization, and by-reference the cache — but the source change is narrow and well-bounded. Expect roughly 5 source files (`client/managed.py`, `client/single_usage.py`, `client/methods.py`, `client/manager.py` or `server/routes.py`, and possibly a small helper) plus 2 docs files (`README.md`, and `.env.example` only if a toggle is added). The heavier surface is tests: the fakes in at least four test modules assert `initialize() -> None` and route-level tests assert exact dict-equality on the `tools/list` body, so 6-9 test files need updates even though the behavior change is one optional field. The research located a clean architectural fit — `instructions` belongs as a defaulted field on the `ManagedClient` dataclass, where it inherits session lifetime and cache residency for free, and reaches `routes.py:179` which already binds the handle and ignores it. The single real plumbing cost is retyping `ready_future` from `Future[ClientSession]` to carry the init result across six declaration sites and three transport bodies, all of which must change atomically or `spawn` deadlocks.

Technical novelty is low-to-moderate. The mechanism is already proven by the pydantic `extra="allow"` config on the SDK's `Result` base class, so attaching the field to `ListToolsResult` survives `model_dump(mode="json", exclude_none=True)` untouched — there is no `response_model=` anywhere in the codebase and nothing strips extra fields. Backward compatibility is therefore near-free: `exclude_none=True` drops a `None` instructions automatically, giving exactly the required "absent field, unchanged behavior". The precedent is close at hand: EPMCDME-13xxx's `MCP_CLIENT_NAME`/`client_info` work modified the same handshake area and left a full artifact set. The genuinely undecided design point is pagination — `tools/list` accepts a cursor and can be called once per page against one cached session, so the spec must state whether instructions ride every page or only the first. A second open question is process rather than code: AGENTS.md marks any `/bridge` response-schema change as "Ask first", so this needs an explicit approval step regardless of how additive it is.

Test coverage posture is mixed-trending-weak in exactly the area being changed. The surrounding machinery — cache TTL, ping validation, transports, timeouts, lifecycle errors — is densely covered, but the `initialize()` **return value** has zero coverage anywhere: every fake session returns `None`, nothing asserts a handshake result is stored, and no test verifies that a cache hit still yields what initialize produced. `tools/list` serialization has exactly one real-pydantic test; the rest are stub dicts that will break on a new key. `tests/integration/` is an empty scaffold, so nothing validates against real SDK types. Risk factors that should raise the score: the seven-call-site atomic change with a deadlock failure mode, the positional dataclass and load-bearing cache tuple as silent-breakage traps, `MCPClientHandle` as a plausible-looking wrong answer, the cross-repo contract with the codemie backend MR, and the complete absence of CI — all seven quality gates are manual, so a missed gate ships.
