# Technical Research

**Task**: mcp client user-agent header transport http
**Generated**: 2026-08-05T12:48:33Z
**Research path**: filesystem (codegraph index returned empty for all queries; see Risk Indicators)

---

## 1. Original Context

There is the env var `MCP_CLIENT_NAME` that is used to set up the client name for the MCP clients.
We need to put the value of this env var into the `user-agent` HTTP header of every request sent by the MCP Client to the HTTP MCP Servers.

---

## 2. Codebase Findings

### Existing Implementations
- `src/mcp_connect/client/client_info.py` — `get_client_info()` reads `MCP_CLIENT_NAME` env var (default `"mcp-bridge"`), returns `mcp.types.Implementation` used as `client_info=` for the MCP protocol handshake. This is session-level identity, NOT an HTTP header — the new work is additive, not a rename of existing behavior.
- `src/mcp_connect/client/transports.py` — `get_transport_ctx(request, headers)` is the single chokepoint that builds/passes the `headers: dict[str, str]` dict into `streamablehttp_client`, `streamablehttp_client_with_sigv4`, and `sse_client`. Best injection point for a User-Agent header for the streamable-http/sse path routed through it.
- `src/mcp_connect/client/managed.py` — `ManagedClient._run_streamable_http_client` goes through `get_transport_ctx`; but `_run_sse_client` calls `sse_client(...)` directly (bypasses `get_transport_ctx`), duplicating header-building logic (`headers = request.mcp_headers or {}`).
- `src/mcp_connect/client/single_usage.py` — `_execute_http_request` uses `get_transport_ctx`; `_execute_sse_request` also calls `sse_client(...)` directly, same duplication as above.
- `src/mcp_connect/client/streamable_http_sigv4.py` — `streamablehttp_client_with_sigv4` accepts `headers: dict[str, str] | None`, forwards to the SDK's `streamablehttp_client`. SigV4 auth signs over the headers dict, so the User-Agent header must be merged in *before* signing, not after.
- stdio transport has no HTTP headers — out of scope for this task (task explicitly says "HTTP MCP Servers").

### Architecture and Layers Affected
- HTTP request → `models/request.py` (`BridgeRequestBody`, has `mcp_headers`) → `client/manager.py` (`detect_transport_type`) → `client/managed.py` / `client/single_usage.py` (client lifecycle) → `client/transports.py` (`get_transport_ctx`, headers dict) → MCP SDK transport clients (`streamablehttp_client`, `sse_client`).
- Only the `client/` layer is touched. No route/model changes expected unless header precedence needs a model-level decision.

### Integration Points
- MCP Python SDK transport clients: `mcp.client.sse.sse_client`, `mcp.client.streamable_http.streamablehttp_client`, `mcp.client.stdio.stdio_client` (not applicable here).
- `httpx` underlying HTTP client used by the SDK transports — sets its own default `User-Agent` if none is supplied; needs confirming whether SDK/httpx let a supplied header override the default (context7 check required before implementation per AGENTS.md).

### Patterns and Conventions
- Env-var-driven identity precedent already exists: `client_info.py` reads `os.getenv("MCP_CLIENT_NAME", "mcp-bridge")` fresh on every call (no caching). The new User-Agent helper should follow the same fresh-read-per-call pattern for consistency, and can likely reuse `get_client_info()` or a shared read of the same env var rather than introducing a second source of truth.
- Headers are built per-call as `request.mcp_headers or {}` then passed to the transport; the natural way to add a header is to merge it into this dict at the point(s) where the dict is finalized before being handed to a transport client.
- Duplication: the SSE header-building logic is duplicated 3 times (`transports.get_transport_ctx` SSE branch, `managed._run_sse_client`, `single_usage._execute_sse_request`). Any header addition must either update all three call sites or (better, and in line with "eliminate duplication" clean-code guidance) route all SSE calls through `get_transport_ctx` as well.
- Masking helper `mask_sensitive_headers` used before logging headers — establishes the existing convention for how headers are surfaced in logs; User-Agent is not sensitive so no masking change needed, but any new logging of headers should reuse this helper rather than a new one.

---

## 3. Documentation Findings

### Guides and Architecture Docs
- `.ai-run/guides/architecture/architecture.md` — confirms module boundaries: `client/` package owns transport construction and the MCP SDK dependency boundary.
- `.ai-run/guides/development/development-practices.md` — mandates a context7 lookup before touching MCP SDK / httpx APIs, TDD (failing test first), full type hints, structured logging conventions.

### Architectural Decisions
- No specific ADR for header handling; the `headers` dict / `mcp_headers` field is the established extension point, per code convention above.

### Derived Conventions
- User-provided `request.mcp_headers` are per-request overrides today — precedent suggests any explicit user-agent value the caller sets in `mcp_headers` should take precedence over (or need an explicit decision against) the env-var default, mirroring how other header values already flow through untouched.

---

## 4. Testing Landscape

### Existing Coverage
- `tests/test_client_name.py` — tests `MCP_CLIENT_NAME` → `get_client_info()` and its use as `client_info=` for stdio/http/sse, in both single-usage and managed paths. Structurally the closest analog to mirror for a new `test_user_agent_header.py`: assert on the `headers` kwarg captured by mocks of `stdio_client`/`get_transport_ctx`/`sse_client`/`streamablehttp_client_with_sigv4`.
- `tests/test_transports.py` — only covers `detect_transport_type`; no header-content assertions today.

### Testing Framework and Patterns
- pytest + pytest-asyncio (`@pytest.mark.asyncio`), `unittest.mock.AsyncMock`/`patch`, `monkeypatch.setenv`/`delenv` for env-var tests.

### Coverage Gaps
- No existing test asserts the contents of the `headers` dict passed into HTTP/SSE/SigV4 transport clients — this is the gap the new tests must fill (default env var, custom env var, and explicit `mcp_headers` override interacting with the new header, for both managed and single-usage paths, and for `streamablehttp_client_with_sigv4`).

---

## 5. Configuration and Environment

### Environment Variables
- `MCP_CLIENT_NAME` — existing env var, currently only used for MCP protocol `Implementation.name`. Ticket requires reusing the same value for the HTTP `User-Agent` header. Default value today is `"mcp-bridge"` (from `client_info.py`).

### Configuration Files
- None specific to this feature; no config file governs headers today (env var + per-request `mcp_headers` only).

### Feature Flags and Deployment Concerns
- None. No flags gate header behavior currently.

---

## 6. Risk Indicators

- `codegraph_explore` returned empty results for every query in this session (architecture, client, header, transport, http, test, deps, config) — the `.codegraph/` index appears stale/uninitialized for this repo; all findings above came from direct file reads, not codegraph.
- SSE header-building is duplicated across 3 call sites (`transports.get_transport_ctx`, `managed._run_sse_client`, `single_usage._execute_sse_request`) — a fix must touch all three, or consolidate, or the SSE path will silently miss the new header.
- `streamablehttp_client_with_sigv4` signs over headers; the User-Agent must be merged into the headers dict before signing, not appended after — ordering bug risk if not handled carefully.
- MCP SDK / underlying `httpx` transport may already set a default `User-Agent`; needs a context7 check to confirm override-vs-merge semantics before implementing (mandatory per AGENTS.md and user's global CLAUDE.md rule).
- Precedence question: if a caller already sets `User-Agent` via `request.mcp_headers`, does the env-var-derived value override it, or should the explicit caller value win? Not stated in the ticket — flagged for Clarity Check.

---

## 7. Summary for Complexity Assessment

This task touches a single architectural layer (`client/`) but at three call sites due to pre-existing duplication of SSE header-building logic across `transports.py`, `managed.py`, and `single_usage.py`. The change itself is a small, additive header merge reusing an existing env-var-read pattern (`client_info.py`) — no new external dependency, no new config surface, no route/model changes anticipated unless header precedence needs a `mcp_headers` field-level decision.

Primary risk is correctness across all transport variants (streamable-http, SSE, SigV4-signed streamable-http) rather than raw complexity: the SigV4 signing order dependency is the sharpest edge, and the 3x SSE duplication means the fix must either be applied three times or used as an opportunity to consolidate SSE construction through `get_transport_ctx` (aligned with the project's Clean Code / no-duplication guidance). Test coverage gap is real but narrow — one new test file mirroring `test_client_name.py`'s structure covers it. Overall: low-to-moderate complexity, moderate correctness risk concentrated in transport-specific edge cases (SigV4 signing, SSE duplication, User-Agent override semantics from the SDK/httpx layer).
