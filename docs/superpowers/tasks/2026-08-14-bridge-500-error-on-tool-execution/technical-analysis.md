# Technical Research

**Task**: bridge endpoint error-handling mcp method execution tools/call HTTP 500 exception mapping
**Generated**: 2026-08-14
**Research path**: filesystem

---

## 1. Original Context

MCP Connect Service fails with 500 Internal Server Error on tool execution.

When attempting to execute tools via the MCP integration in CodeMie (e.g., SQL queries, plugin operations), the MCP Connect Service returns a HTTP 500 Internal Server Error on the /bridge endpoint. This results in all dependent features failing. Example error output from the caller:

  Error calling tool: query with arguments {'sql': "SELECT ts.step_id ... LIKE '%forgot%password%' ..."}
  The root cause is: {} This is not an AI/Run CodeMie error. The Error has been thrown in the MCP server.
  Error executing MCP tool: query: HTTPStatusError: Server error '500 Internal Server Error' for url 'http://codemie-mcp-connect-service-headless:3000/bridge'.

The error originates from the backend MCP service (this repo). It blocks all tool usage.

Acceptance criteria:
- MCP Connect Service returns successful responses for valid tool execution requests
- No generic HTTP 500 errors occur for standard tool requests
- MCP service operational status can be validated from CodeMie frontend
- Users are able to execute MCP-dependent features without backend failures
- Root cause of error is identified, documented, and resolved (config, availability, or code regression)
- Error handling logs sufficient detail for diagnosis without exposing internal details to users

Steps to reproduce: initiate an MCP-backed tool operation (e.g. a SQL query) → request goes to /bridge → returns HTTP 500 and failed tool output.

NOTE: The repo root contains an untracked example_sql.json repro payload. Its structure is:
{ serverPath: 'npx', args: ['-y','@modelcontextprotocol/server-postgres', 'postgresql://...'], method: 'tools/call', params: { name: 'query', arguments: { sql: '...', sql1: '...', sql2: '...' } } }
Note the arguments object carries EXTRA keys (sql1, sql2) beyond what the postgres 'query' tool accepts — this may be a clue for the reproduction (an underlying MCP tool call raising an error, or a malformed/unexpected request shape).

---

## 2. Codebase Findings

### Existing Implementations

**Primary /bridge endpoint**: `src/mcp_connect/server/routes.py`:240-314
- `@router.post("/bridge")` — main entry point for all MCP method invocations
- Accepts `BridgeRequestBody` (Pydantic model), optional `timeout` query param, bearer token auth
- Delegates to `_handle_single_usage_request` if `request.single_usage == True`
- Delegates to `_handle_cached_client_request` otherwise (default cached mode)
- Returns `JSONResponse` with status 200 on success, includes X-Request-ID header

**Request handler paths**:
- `_handle_single_usage_request` (`routes.py`:122-160) — single-usage mode, no caching
- `_handle_cached_client_request` (`routes.py`:162-237) — cached client mode (default)

**MCP method execution**: `src/mcp_connect/client/methods.py`:53-165
- `invoke_mcp_method` — routes MCP method strings (`tools/call`, `tools/list`, etc.) to SDK calls
- `tools/call` handler (lines 86-100):
  - Extracts `name` (required) and `arguments` (optional mapping)
  - Strips `None` values from arguments via `_strip_none_values` (lines 209-217)
  - Calls `session.call_tool(name, clean_arguments)`
  - **Returns result directly from MCP SDK — no inspection of `isError` field**

**Result flow**: `methods.py`:100 calls `session.call_tool()`, which returns a `CallToolResult` from the MCP SDK. This result includes:
- `content: list[ContentBlock]` — tool output
- `structuredContent: dict[str, Any] | None` — optional structured result
- `isError: bool = False` — **indicates if tool execution failed**

**Current behavior**: The service passes `CallToolResult` directly to the caller, converting Pydantic models to JSON via `model_dump()` (routes.py:304). There is **no code path that inspects `isError`** and converts it to an HTTP error status.

**Single-usage request execution**: `src/mcp_connect/client/single_usage.py`:50-333
- `execute_single_usage_request` — routes to stdio/HTTP/SSE handlers
- `_execute_stdio_request` (lines 114-194)
- `_execute_http_request` (lines 197-259)
- `_execute_sse_request` (lines 262-332)
- All three handlers call `invoke_mcp_method` (from `methods.py`) and return the result unchanged

### Architecture and Layers Affected

**Layers touched**:
1. **API / Server Layer** (`src/mcp_connect/server/`):
   - `routes.py` — /bridge endpoint, request routing, error formatting
   - `middleware.py` — auth, logging, global exception handling

2. **Service / Client Layer** (`src/mcp_connect/client/`):
   - `manager.py` — client creation, caching, transport detection, timeout enforcement
   - `single_usage.py` — single-usage client execution (no caching)
   - `methods.py` — **MCP method routing and invocation** (key file for tools/call)
   - `managed.py` — cached client lifecycle

3. **Models Layer** (`src/mcp_connect/models/`):
   - `request.py` — `BridgeRequestBody` schema (the API contract)

4. **Utilities Layer** (`src/mcp_connect/utils/`):
   - `errors.py` — error detail extraction, HTTP status error handling, response formatting
   - `logger.py` — structured JSON logging
   - `masking.py` — sensitive data masking
   - `context.py` — request context propagation

**Key file for investigation**: `src/mcp_connect/client/methods.py` — the `tools/call` handler passes the MCP SDK result through without checking `isError`.

### Integration Points

**Internal dependencies**:
- `routes.py` imports `manager.py` (get_or_create_client, invoke_with_timeout) and `single_usage.py` (execute_single_usage_request)
- Both handler paths call `invoke_mcp_method` from `methods.py`
- `methods.py` imports `mcp.ClientSession` from the MCP Python SDK
- `routes.py` uses error utilities from `utils/errors.py` (format_error_response, extract_http_status_error, build_downstream_error_response)

**External dependencies**:
- MCP Python SDK (`mcp`) — provides `ClientSession.call_tool()` which returns `CallToolResult`
- FastAPI — HTTP framework, `HTTPException` for error responses
- Pydantic 2 — request/response model validation

**MCP SDK call flow**:
```
/bridge endpoint
  → invoke_with_timeout (manager.py:39-87)
    → invoke_mcp_method (methods.py:53-165)
      → session.call_tool(name, arguments) [MCP SDK]
        → returns CallToolResult (has isError field)
  → result returned as-is to caller
```

### Patterns and Conventions

**Error handling patterns** (`routes.py`, `single_usage.py`):
- `HTTPException` raised for client errors (4xx), server errors (500), timeouts (504), service unavailable (503)
- `format_error_response` (routes.py:52-119) builds structured error response with:
  - `error` message
  - `details` dict (extracted from exception attributes)
  - `request_id` (for tracing)
  - `stacktrace` (only in debug mode)
- `extract_http_status_error` (errors.py:184-205) extracts `httpx.HTTPStatusError` from nested `ExceptionGroup` instances
- `build_downstream_error_response` (errors.py:227-262) builds detail dict and forwarding headers from downstream HTTP errors

**Null value handling** (`methods.py`:209-217):
- `_strip_none_values` recursively removes `None` values from arguments dict
- **Rationale**: MCP servers with strict schemas (e.g. Zod) reject explicitly-null optional fields
- **Applied to tools/call**: lines 88-89 strip nulls before calling `session.call_tool`

**Extra keys in arguments**: The example_sql.json payload includes `sql1` and `sql2` keys alongside `sql`. The `_strip_none_values` function does NOT remove keys — it only removes keys with `None` values. **Extra keys are passed through to the MCP server unchanged.**

**Exception handling in routes.py**:
- `_handle_cached_client_request` (lines 203-237) catches:
  - `HTTPException` → re-raise
  - `ValidationError` → 422
  - `ConnectionError` → 503
  - `asyncio.TimeoutError` → 504
  - `Exception` (catch-all) → check for `httpx.HTTPStatusError`, else 500
- `_handle_single_usage_request` (lines 136-159) catches:
  - `HTTPException` → re-raise
  - `ValidationError` → 422
  - `Exception` (catch-all) → check for `httpx.HTTPStatusError`, else 500

**Current 500 trigger**: Any unhandled exception in the method execution path raises HTTPException(status_code=500) with detail from `format_error_response`.

---

## 3. Documentation Findings

### Guides and Architecture Docs

**Found in `.ai-run/guides/`**:
- `README.md` — guide index, routing table
- `project.md` — project identity, ticket/MR adapters
- `architecture/architecture.md` — **system design, data flow, error handling strategy**
- `testing/testing-patterns.md` — test organization, TDD workflow
- `development/development-practices.md` — type hints, async patterns, error handling conventions
- `quality-gates.md` — lint, format, type-check, test gates
- `standards/git-workflow.md` — branch naming, commits, MR creation
- `security/README.md` — CVE remediation process
- `build/README.md` — container images, build stages
- `build/dependencies.md` — package manifest ownership

**Relevant to this task**:
- `architecture/architecture.md` lines 183-196 — **Error Handling Strategy**:
  - Custom exceptions in `utils/errors.py`
  - Global error handler in `server/middleware.py`
  - Structured JSON error responses
  - Full traceback logging
- `development/development-practices.md` lines 43-62 — **Error Handling Conventions**:
  - Use domain-specific exceptions
  - Always include context
  - Log errors before re-raising

### Architectural Decisions

**Error handling strategy** (from `architecture.md`):
- All errors should include context (config, state, error details)
- Global exception handler catches unhandled exceptions and returns structured JSON
- Full tracebacks logged for debugging

**API contract stability** (from `AGENTS.md`):
- `/bridge` request/response schema is a **binding API contract** — deployed clients depend on it
- Breaking changes require coordination with callers
- Current response format: JSON body with `model_dump(mode="json", exclude_none=True)`

**MCP protocol semantics** (inferred from MCP SDK types):
- `CallToolResult.isError` field indicates tool-level execution failure
- **This is not a transport error** — the MCP call succeeded, but the tool itself failed
- Example: SQL query with syntax error → MCP call succeeds, returns `CallToolResult(isError=True, content=[...])`

### Derived Conventions

**From code exploration**:
1. **Successful MCP method calls always return 200** — even if the tool itself failed (e.g., SQL syntax error)
2. **HTTP 500 is reserved for service/transport failures** — client creation, timeout, connection errors
3. **Tool-level errors (isError=True) are passed through to caller as 200 responses** — caller must inspect `isError` field
4. **The service does not currently distinguish between**:
   - Tool execution success (`isError=False`) → 200
   - Tool execution failure (`isError=True`) → **currently also 200**, caller sees error in response body

---

## 4. Testing Landscape

### Existing Coverage

**Test files related to /bridge and tools/call**:
- `tests/test_main_error_handling.py` — error handler tests for /bridge (validation, HTTP exceptions, downstream errors)
- `tests/test_mcp_methods.py` — unit tests for `invoke_mcp_method` routing
- `tests/test_bridge_validation.py` — request validation tests
- `tests/test_context_propagation.py` — request context and error responses
- `tests/test_timeout.py` — timeout handling for MCP methods
- `tests/test_single_usage.py` — single-usage client execution

**Specific tools/call tests** (`test_mcp_methods.py`):
- Line 81-87: `test_tools_call_requires_name` — validates required `name` parameter
- Line 90-94: `test_tools_call_with_arguments` — validates arguments passing
- Line 97-106: `test_tools_call_strips_null_arguments` — validates null stripping
- Line 108-117: `test_tools_call_strips_null_arguments_nested` — validates nested null stripping
- Line 120-128: `test_tools_call_preserves_falsy_non_none_values` — validates falsy value preservation

**Coverage gaps**:
- **No test for CallToolResult.isError handling** — no test verifies behavior when MCP server returns `isError=True`
- **No test for extra keys in arguments** — the example_sql.json has `sql1`, `sql2` alongside `sql`; no test validates behavior
- **No test for tool-level errors vs transport errors** — tests mock transport failures but not tool-level failures

### Testing Framework and Patterns

**Framework**: pytest with pytest-asyncio (auto mode)
**Configuration**: `pyproject.toml`:50-59
- `asyncio_mode = "auto"` — auto-detect async tests
- `testpaths = ["tests"]`
- `python_files = ["test_*.py"]`
- `addopts = "-m 'not integration'"` — excludes integration tests by default

**Patterns**:
- AsyncMock for MCP session methods (conftest.py:46: `session.call_tool = AsyncMock(return_value={"result": "tools/call"})`)
- TestClient from FastAPI for endpoint testing
- Patch decorators for dependency injection mocking
- Fixtures in conftest.py for shared setup

**Current test mocks return dict, not CallToolResult** — conftest.py:46 returns `{"result": "tools/call"}`, not a real `CallToolResult` instance with `isError` field.

### Coverage Gaps

1. **Tool-level error handling**: No test verifies that `CallToolResult(isError=True, ...)` is handled correctly
2. **Extra argument keys**: No test validates behavior when arguments dict has extra keys not accepted by tool schema
3. **MCP server rejection of strict schema**: No test simulates Zod schema validation failure from downstream MCP server
4. **Downstream error response parsing**: Tests cover HTTP status errors, but not MCP protocol-level errors in response body
5. **Integration with real MCP servers**: `tests/integration/` contains only `__init__.py` — no integration tests exist

---

## 5. Configuration and Environment

### Environment Variables

**Relevant to /bridge endpoint** (from `AGENTS.md`, `architecture.md`):
- `ACCESS_TOKEN` — bearer auth token (auth disabled if unset)
- `MCP_CONNECT_DEFAULT_TIMEOUT` — default method timeout in ms (default: 120000)
- `MCP_CONNECT_INIT_TIMEOUT` — client init timeout in ms (default: 30000)
- `LOG_LEVEL` — logging level (default: INFO; debug enables stacktraces in error responses)
- `DEBUG_LOG_BRIDGE_PAYLOAD` — log complete bridge payload if "true" (default: false)

**Error response behavior**:
- `LOG_LEVEL=debug` includes `stacktrace` field in error responses (routes.py:106-109)
- Production mode (LOG_LEVEL != debug) omits stacktraces from client-facing responses

### Configuration Files

**Request model** (`src/mcp_connect/models/request.py`):
- `BridgeRequestBody` (lines 24-69) — **API contract**:
  - Required: `serverPath`, `method`, `params`
  - Optional: `args`, `env`, `mcp_headers`, `request_headers`, `http_transport_type`, `single_usage`
  - Context fields: `user_id`, `assistant_id`, `project_name`, `workflow_execution_id`
  - **`model_config = ConfigDict(extra="forbid")`** (line 27) — rejects extra fields at request level
  - **`params: Any`** (line 32) — allows any structure for MCP method parameters

**Critical constraint**: `params` is typed as `Any`, so extra keys in `params.arguments` are **not rejected by Pydantic validation**.

### Feature Flags and Deployment Concerns

**No feature flags** for error handling behavior — all requests use same error handling logic.

**Deployment-level concerns**:
- Service deployed as container (`Dockerfile` at repo root)
- Accessed via `http://codemie-mcp-connect-service-headless:3000/bridge` (from ticket context)
- No circuit breaker or retry logic in the service — caller must handle retries

---

## 6. Risk Indicators

- **No code path inspects `CallToolResult.isError`** — tool-level failures (e.g., SQL syntax errors) return 200 with error details in response body, not HTTP 4xx/5xx. Caller must parse response to detect tool failure.

- **Extra keys in `arguments` dict are passed through unchanged** — `example_sql.json` has `sql1`, `sql2` alongside `sql`. If the MCP server's Zod schema is strict (additionalProperties: false), it may reject the request, raising an exception that becomes a 500.

- **MCP server exception during `call_tool` execution becomes HTTP 500** — if the MCP server raises an exception (schema validation, internal error), it propagates as generic 500. No specific handling distinguishes "tool schema violation" from "service failure".

- **`_strip_none_values` only removes keys with `None` values** — does not remove extra keys. If caller sends `{sql: "...", sql1: "...", sql2: "..."}` and `sql1`/`sql2` are not null, they are passed to the MCP server.

- **No test coverage for `CallToolResult.isError` handling** — current tests mock `call_tool` return value as dict, not as real `CallToolResult` instances with `isError` field. Gap: behavior when tool returns `isError=True` is untested.

- **No integration tests** — `tests/integration/` contains only `__init__.py`. Real MCP server interactions (stdio subprocess, HTTP transport) are not covered by tests.

- **API contract stability risk** — changing error response structure (e.g., returning 4xx for tool-level errors) could break deployed clients that expect 200 for all successful MCP calls.

- **`BridgeRequestBody` validation rejects extra top-level fields** (`extra="forbid"`), but `params` is `Any` — extra keys in `params.arguments` pass validation and reach the MCP server.

- **Downstream MCP server errors are wrapped in generic 500** — if the MCP server (e.g., `@modelcontextprotocol/server-postgres`) throws on schema validation, the exception message may not surface clearly to the caller. Error detail extraction depends on exception attributes.

- **Empty root cause message** — ticket shows `"The root cause is: {}"` — suggests `extract_root_cause_message` or error formatting may not be capturing MCP server error details from ExceptionGroup.

---

## 7. Summary for Complexity Assessment

The task touches **two architectural layers** directly: the **API/Server layer** (`routes.py`) and the **Service/Client layer** (`methods.py`). The Models layer (`request.py`) may require inspection but likely no changes (API contract stability). **Estimated file change surface: 2-3 files** (`methods.py`, `routes.py`, possibly error utilities in `utils/errors.py`).

**Technical novelty**: The issue involves **MCP protocol semantics** that are not currently handled — distinguishing transport-level success (HTTP 200) from tool-level failure (`CallToolResult.isError=True`). This is a **gap in the existing error handling pattern**, not a bug in implemented logic. The service correctly returns 200 for successful MCP calls, but callers expect HTTP status codes to reflect tool-level failure.

**Potential solutions**:
1. **Option A**: Inspect `isError` in `methods.py` after `call_tool` returns, raise `HTTPException(status_code=4xx)` for tool-level errors. **Breaks API contract** — deployed clients expect 200.
2. **Option B**: Keep 200 response, add `isError` field to top-level response body for caller visibility. **No contract break**, but requires caller changes to check new field.
3. **Option C**: Return `CallToolResult` structure unchanged (current behavior), document that callers must parse `isError` from response. **No code change**, documentation update only.

**Risk factors**:
- **API contract change risk**: Option A breaks backward compatibility. Any change to response structure must be coordinated with deployed clients.
- **MCP server schema validation**: If the root cause is strict schema rejection (extra keys `sql1`, `sql2`), the fix may involve **request sanitization** (strip keys not in tool schema) rather than error handling changes.
- **Sparse error context**: The ticket shows `"root cause: {}"` — may indicate that exception details from MCP server are not being extracted/logged properly. Error formatting code in `utils/errors.py` may need inspection.

**Test coverage posture**: The affected area has **unit test coverage for happy paths** (tools/call with valid arguments) but **zero coverage for error cases** (tool returns `isError=True`, extra keys in arguments, schema validation failures). Integration tests are **completely absent** — no real MCP server interactions tested.

**Key decision point**: Whether to treat `isError=True` as an HTTP error (4xx) or keep it in the response body (200). This is a **protocol design question**, not a pure implementation bug. The MCP specification may have guidance on this — should be consulted before making changes.

**Complexity drivers**:
1. **API contract stability** — any response structure change affects deployed clients
2. **MCP protocol semantics** — must understand MCP specification's intent for `isError` field
3. **Backward compatibility** — existing callers depend on current 200-for-all-MCP-success behavior
4. **Error detail propagation** — ensuring MCP server error messages reach the caller in useful form
5. **Test coverage gap** — no existing tests for the code paths that will change
