# Plan — EPMCDME-11351: /bridge returns 500 on tool execution

## Root cause (verified against installed MCP SDK)

`tools/call` on `/bridge` reaches `ClientSession.call_tool` (`methods.py:100`). The SDK
(`.venv/.../mcp/client/session.py:386-415`) **raises** on two paths that this service does
not handle:

1. **`McpError`** — when the downstream MCP server returns a JSON-RPC error (invalid params,
   e.g. a strict schema rejecting the extra `sql1`/`sql2` keys in the repro payload; unknown
   tool; server internal error). `send_request` raises it.
2. `RuntimeError` from `_validate_tool_result` when a tool declares an output schema but returns
   missing/invalid structured content (secondary path).

Both fall through to `except Exception` in `routes.py` → `HTTPException(500)`. For `McpError`,
`extract_error_details` returns `{}` (it is not OSError/ValidationError/TimeoutError) → the bare,
detail-less 500 that the ticket shows as *"root cause: {}"*. Tool-level failures (a bad SQL query)
already return `isError=True` and produce a 200 — so the 500 is specifically the protocol-error path.

## Decision (user-approved, contract-affecting)

**Option B**: convert a downstream MCP protocol error on `tools/call` into a **200 response**
carrying a `CallToolResult`-shaped body with `isError=True` and the error text in `content`. The
caller's MCP client then sees a normal tool-error result (which the model can relay/self-correct on)
instead of a generic HTTP 500.

Scope: `tools/call` only — the `isError` `CallToolResult` shape is meaningful only for tool calls.
Other methods keep existing behavior. Catch is narrowed to `McpError` so timeouts (504),
connection errors (503), and downstream `httpx` auth errors (401/403 passthrough, already tested)
are **not** swallowed.

## Tasks

### Task 1 — Convert `McpError` from `tools/call` into an `isError` `CallToolResult`
- **Test-first: yes** — unit test in `tests/test_mcp_methods.py`: `invoke_mcp_method(session, "tools/call", {"name": "query", "arguments": {"sql": "..."}})` where `session.call_tool` raises `McpError(ErrorData(code=-32602, message="Invalid params: unexpected key sql1"))` returns a `CallToolResult` with `isError is True` and the message + code in `content[0].text`. Fails today (exception propagates).
- Implement in `src/mcp_connect/client/methods.py`:
  - Import `McpError` (`mcp.shared.exceptions`) and `CallToolResult`, `ErrorData`, `TextContent` (`mcp.types`).
  - Add helper `_mcp_error_to_tool_result(name, error) -> CallToolResult` building `CallToolResult(isError=True, content=[TextContent(type="text", text=f"MCP tool '{name}' failed (code {error.code}): {error.message}")])`.
  - Wrap `await session.call_tool(...)` in `try/except McpError`; log a `warning` with `code` + `message` (server-side diagnosis; do **not** surface `error.data` to the caller), return the helper result.
  - Comment references `EPMCDME-11351` (plain ticket comment — this is a bugfix, not a `# Security` pin).

### Task 2 — Regression guard: non-`McpError` still propagates
- **Test-first: yes** — unit test: `session.call_tool` raising a non-`McpError` (e.g. `ConnectionError`) from `tools/call` propagates out of `invoke_mcp_method` unchanged (so the route still maps it to 503/504/500). Guards against over-broad catching.
- No new implementation beyond Task 1 (the narrow `except McpError` already satisfies it); the test locks the boundary.

### Task 3 — End-to-end `/bridge` returns 200 isError body
- **Test-first: yes** — test in `tests/test_main_error_handling.py`: patch `invoke_with_timeout` (cached path) / `execute_single_usage_request` to surface the synthesized `CallToolResult`, POST a `tools/call` to `/bridge`, assert `status_code == 200`, body `isError is True`, and `content[0]["text"]` carries the downstream message. (The unit path in Task 1 is the primary proof; this asserts serialization through `routes.py:303-314`.)

## Non-goals / explicitly out of scope
- Output-schema `RuntimeError` conversion (secondary path) — not the ticket's reproduction; catching bare `RuntimeError` would be over-broad.
- `McpError` from non-`tools/call` methods — no `isError` shape applies; unchanged.
- `UrlElicitationRequiredError` (an `McpError` subclass) — falls into the same conversion; acceptable, elicitation is unused here.
- The `/bridge` request schema and success-path response for non-error calls — unchanged.

## Gates
`poetry run ruff check` · `poetry run black --check src/ tests/` · `poetry run mypy src/` · `poetry run pytest tests/` (each run individually, per quality-gates.md).
