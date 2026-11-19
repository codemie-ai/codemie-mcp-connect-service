# Technical Research

**Task**: tools-call result capture, stdio client cache, bridge request schema, output directory
**Generated**: 2026-11-03
**Research path**: codegraph

---

## 1. Original Context

EPMCDME-14735 in codemie-mcp-connect-service. Branch: EPMCDME-14735_capture-generated-files.

## Goal
MCP-Connect captures files that stdio MCP servers (shell, filesystem, ...) generate during a `tools/call` and returns them in the tool result as embedded MCP resources (`{"type":"resource","resource":{"uri","mimeType","blob"}}`). The CodeMie backend already turns such items into downloadable chat artifacts, so the user gets a Download chip without the model having to read the file back. The code review meeting asked for this.

## Why (evidence, verified 2026-11-03)
- Ticket repro (shared conversation geRh9NHtq5Pj, RADAR CLI assistant): the `radar-cli` skill, a shell MCP server (`shell_execute` with `command[]`, `directory`, `timeout`) and `@modelcontextprotocol/server-filesystem`. Both run as **stdio processes inside MCP-Connect**. Files are written to `/home/codemie/<32-hex session>/`, and `/home/codemie` is MCP-Connect's WORKDIR.
- The model asked for a link called only `get_file_info` and invented a dead link. Only when it called `read_media_file` did the server return an embedded resource. Prod CodeMie dropped it; backend branch `EPMCDME-14735_downloadable-mcp-artifacts` fixes that.
- Reproduced locally with the "mcp-connect smoke test" assistant (filesystem server over `/tmp`): `write_file` returns only `Successfully wrote to <path>`, no chip, nothing published. `read_media_file` on the same csv/json/xlsx produces working chips stored under workspace `artifacts/<turn>/`.

## What exists already
- CodeMie backend → MCP-Connect `POST /bridge` body: `method`, `serverPath`, `args`, `params`, `env`, `mcp_headers`, `single_usage`, `user_id`, `assistant_id`, `project_name`, `workflow_execution_id`, optional `user_context` (forwarded as `_meta` on tools/call, EPMCDME-14847). `conversation_id` and `request_uuid` are **not** sent (`exclude=True` in backend `codemie/src/codemie/service/mcp/models.py` `MCPExecutionContext`).
- MCP-Connect caches stdio clients by config (`client/cache.py`, `client/manager.py`). One process may serve many users, so a per-call `cwd` cannot simply be set on a cached process. `single_usage` spawns per request (`client/single_usage.py`).
- Backend publisher limits: `FILES_STORAGE_MAX_UPLOAD_SIZE` (100 MB); zip-container validation for `.docx .odp .ods .odt .pptx .xlsb .xlsm .xlsx .zip`. A `resource_link` item is shown as "stays on the MCP server" with no link.

## Requirements (ticket ACs this serves: #1, #3, #4, #5, #6, #7)
1. Files created or modified during a `tools/call` in the call's output directory come back appended to the result as embedded `resource` items (base64 `blob`, `file://` uri with the file name, best-guess mimeType). The server's own content is untouched, so existing image behavior is unchanged.
2. Per-user (and if possible per-conversation) output directory on the shared host. No file of another user is ever captured or returned (AC #6). Decide how the directory reaches the MCP server: `cwd`, an env var such as `CODEMIE_OUTPUT_DIR`, or both. Also decide how it works with cached clients.
3. Limits: max file size and max total per call (aligned with the backend's 100 MB), a file-count cap, a skip list (`node_modules/`, hidden files, scripts the model wrote such as `*.py`?). Over-limit files are reported as text, not silently dropped.
4. Opt-in or opt-out per server config. Off for servers where it makes no sense, for example remote HTTP servers.
5. Per-conversation scoping needs a contract change in both repos, in this order:
   a. MCP-Connect `BridgeRequestBody` (`src/mcp_connect/models/request.py`, `extra="forbid"`) accepts optional `conversation_id` and `request_uuid`.
   b. Then the backend (`~/codemie-dev/codemie`, branch `EPMCDME-14735_downloadable-mcp-artifacts`) sends them. Today both are `exclude=True` in `MCPExecutionContext` (`src/codemie/service/mcp/models.py`, also excluded in `to_request_fields`), and `MCPToolInvocationRequest` has no such fields.
   Sending before (a) is deployed makes every MCP call fail with 422. Make the deploy order explicit in both MRs. Keep the backend change minimal and update its `spec.md` "Follow-up" section, which currently says "not done yet".

## Open questions for brainstorming
- Directory-diff capture vs. only files under a dedicated output dir. Diffing a shared workdir is how "auto-capture" was rejected for CodeMie's own shell tool in run 2. Decide why it is acceptable here, or narrow the scope.
- Retention/cleanup of per-session dirs on the MCP-Connect host.
- Whether it duplicates files the model also returns via `read_media_file`. The backend then publishes `name (2).ext`.

## Verify
- Unit tests in this repo.
- End to end locally (docker in `~/codemie-dev/`; rebuild the `codemie-mcp-connect-1` container): with the smoke-test assistant, "write closed_positions_analysis.csv/.json/.xlsx and give me the files" shows Download chips **without** a `read_media_file` call. A second user cannot get the first user's files.

## Related
- Backend spec: `~/codemie-dev/codemie/docs/superpowers/tasks/2026-09-14-epmcdme-14735-downloadable-mcp-artifacts/spec.md`
- UI run: `~/codemie-dev/codemie-ui/docs/superpowers/tasks/2026-09-21-epmcdme-14735-downloadable-artifacts-ui/`
- AC #8 (explicit attach tool) is being dropped from the ticket. Do not reintroduce it.

---

## 2. Codebase Findings

### Existing Implementations

**P1 — Return files a stdio tool wrote to the caller as embedded resources.**
- None found in `src/`. Searched: embedded resource, base64 blob, mimetype, file capture, output directory. Nothing in `src/` reads files from disk, builds `EmbeddedResource`/`BlobResourceContents`, or uses `mimetypes`.
- Nearest mechanism — tool result passthrough: `invoke_mcp_method` `src/mcp_connect/client/methods.py:54`, `tools/call` branch `:90-124` returns the SDK `CallToolResult` unmodified (`session.call_tool`, `:107-109`). Only rewrite of a result today: `_mcp_error_to_tool_result` `methods.py:191` (McpError → `CallToolResult(isError=True, [TextContent])`, EPMCDME-11351).
- Callers of `invoke_mcp_method`: cached path `invoke_with_timeout` `src/mcp_connect/client/manager.py:39` (wraps in `asyncio.wait_for`); single-usage `_execute_stdio_request` `src/mcp_connect/client/single_usage.py:117` (+ http `:201`, sse `:267`), all via function-local import.
- Serialization to HTTP: `bridge_endpoint` `src/mcp_connect/server/routes.py:303`, `:358-369` → `result.model_dump(mode="json", exclude_none=True)` → `JSONResponse(200)`. No size cap on the response.
- `src/mcp_connect/utils/process.py` (`StreamCaptureWrapper`, `capture_stream_output`) captures subprocess stdout/stderr lines into 50-line deques for error diagnostics — not files.

**P2 — Per-user/per-conversation output directory that reaches the MCP server process.**
- Stdio spawn sites, three, all build `StdioServerParameters(command, args, env)` with **no `cwd`**:
  - cached: `ManagedClient._run_stdio_client` `src/mcp_connect/client/managed.py:227-240`
  - single-usage: `_execute_stdio_request` `single_usage.py:139-143` (env defaults to `{}`)
  - `get_transport_ctx` stdio branch `src/mcp_connect/client/transports.py:53-62`
- SDK (`.venv/.../mcp/client/stdio/__init__.py:72-129`): `StdioServerParameters` has `cwd: str | Path | None` (`:86`), passed to the process (`:129`). Env given → `{**get_default_environment(), **server.env}`; default env inherits only `HOME LOGNAME PATH SHELL TERM USER` (`:44,51-69`). With `cwd=None` the child inherits MCP-Connect's cwd, i.e. `WORKDIR /home/codemie` (`Dockerfile:311`).
- Per-request identity in MCP-Connect today: `user_id`, `assistant_id`, `project_name`, `workflow_execution_id` on `BridgeRequestBody` (`src/mcp_connect/models/request.py:47-50`), used only for logging context (`extract_request_context` `src/mcp_connect/utils/context.py:38-72`). `user_context` (`request.py:41`) forwarded as `_meta["codemie.ai/user-context"]` on tools/call only.

**P3 — Isolation of one user's files from another (AC #6) under cached clients.**
- Cache key `generate_cache_key` `src/mcp_connect/client/cache.py:210-235`: SHA-256 of `serverPath`, sorted `args`, sorted `env` items, sorted `mcp_headers`, `http_transport_type`. **`user_id`, `user_context`, `single_usage` are not in the key.** Key is computed after `apply_substitutions` (`manager.py:160-163`), so substituted values count. Consequence (fact): two users with identical server config share one process and its cwd; anything placed in `env` partitions the cache per distinct value.
- Cache: `MCPClientCache.get` `cache.py:107` (TTL sliding, ping-validated), TTL `MCP_CONNECT_CLIENT_CACHE_TTL` default 300000 ms (`cache.py:100`); cleanup loop `MCP_CONNECT_CACHE_CLEANUP_INTERVAL` (`src/mcp_connect/main.py:107`).

**P4 — Per-server opt-in/out; off for remote HTTP.**
- Transport decided by `detect_transport_type` `manager.py:93-118`: `http(s)://` → streamable-http/sse, `ws(s)://` → 400, else stdio. No per-server feature toggle exists; per-server config arrives only as `serverPath/args/env/mcp_headers/http_transport_type`.

**Other touched code**
- `bridge_endpoint`, `_handle_single_usage_request` `routes.py:182`, `_handle_cached_client_request` `routes.py:223`, `_build_user_context_meta` `routes.py:58` (the EPMCDME-14847 pattern: request field → computed per call in the route → passed as `meta=` kwarg through `invoke_with_timeout`/`execute_single_usage_request` → `invoke_mcp_method`).
- `request_validation_exception_handler` `src/mcp_connect/main.py:218-226`.

### Decisions Already in the Code
- `BridgeRequestBody` is `extra="forbid"` (`request.py:27`); unknown field → **HTTP 400** (not 422) via `main.py:223-224` (`extra_forbidden` → 400). Tested: `tests/test_bridge_validation.py:102` `test_unknown_field_returns_400`.
- Cached clients keyed by config, not by user (`cache.py:223-229`); reason recorded in docstring: "all parameters that affect client configuration". Alternative (per-user key) not taken.
- Per-request data travels as a kwarg through the client layer, not into the cached process (convention, EPMCDME-14847: `meta` param on `invoke_with_timeout` `manager.py:44`, `execute_single_usage_request` `single_usage.py:55`, `invoke_mcp_method` `methods.py:58`; "Opaque here" docstrings). Meta passed only when truthy to keep the SDK call shape (`methods.py:105-109`).
- New request fields are optional with `None` default and logging-only unless explicitly wired (`request.py:46-50`).
- Response uses `exclude_none=True` (`routes.py:357-359`), "matches TypeScript behavior".
- Child env is whitelisted by the SDK, not inherited (`stdio/__init__.py:44`) — MCP-Connect's own env (e.g. `ACCESS_TOKEN`) does not reach servers.
- Deployment: `readOnlyRootFilesystem: true` (`deploy-templates/values.yaml:55`); only `/tmp` and `/home/codemie` are writable, each an `emptyDir` (`deploy-templates/templates/statefulset.yaml:70-82`); `ephemeral-storage` limit 2Gi (`values.yaml:73,77`); `replicaCount: 1` StatefulSet (`values.yaml:6`).
- Data direction: tool results are produced by the server and passed through; the task needs MCP-Connect to read the server's filesystem side effects after the call — data not reported by the server today. Usual alternative: the server itself returns content (`read_media_file`).

### Task Statements Checked Against the Code
- "`/home/codemie` is MCP-Connect's WORKDIR" — holds (`Dockerfile:310-311`, `USER codemie`).
- "Files are written to `/home/codemie/<32-hex session>/`" — unverified: nothing in this repo creates a 32-hex dir; children run with cwd `/home/codemie` (no `cwd` set). Origin (shell server arg, backend `args`/`directory`) would settle it.
- "Backend sends method…user_context; conversation_id/request_uuid not sent" — holds: backend `MCPToolInvocationRequest` (`codemie/src/codemie/service/mcp/models.py:521-556`) has no such fields; `MCPExecutionContext` `:114-125` both `exclude=True`.
- "also excluded in `to_request_fields`" — partly: `conversation_id` is in the explicit exclude set (`models.py:196`); `request_uuid` is not listed there, excluded only by `Field(exclude=True)` (`:122`).
- "MCP-Connect caches stdio clients by config; one process may serve many users" — holds (`cache.py:223-229`, no user in key).
- "`single_usage` spawns per request" — holds (`single_usage.py:139-147`).
- "Sending before (a) is deployed makes every MCP call fail with 422" — contradicted: extra field → 400 (`main.py:223-224`, `tests/test_bridge_validation.py:102`). Every call still fails.
- "Server's own content is untouched, existing image behavior unchanged" — holds today: result passes through unmodified (`methods.py:107-109`, `routes.py:358`).
- "Off for remote HTTP servers" — no existing toggle; transport is derived from `serverPath` (`manager.py:93`).
- "Backend already turns such items into artifacts; spec Follow-up says not done yet" — holds per backend `spec.md:152-155`; backend-side behavior unverified here (other repo).

### Consumers of Changed Contracts
- `BridgeRequestBody` (83 refs). Readers by field: `generate_cache_key` `cache.py:210` (explicit field list — new fields are not in the key unless added); `apply_substitutions` `src/mcp_connect/utils/substitution.py:82` (`model_copy(deep=True)` — new fields copied, not substituted); `extract_request_context` `context.py:38` (explicit fields); `_debug_log_bridge_payload` `routes.py:84`; three `StdioServerParameters` builders above; tests `tests/test_bridge_validation.py`, `test_cache.py`, `test_context_propagation.py`, `test_substitution.py`, `test_single_usage.py`, `test_managed_lifecycle_errors.py`. Backend caller `MCPToolInvocationRequest` must stay a subset (`extra="forbid"`).
- `CallToolResult` returned by `invoke_mcp_method`: `invoke_with_timeout` `manager.py:69-74`, `_execute_stdio/http/sse_request` (single_usage), `bridge_endpoint` `routes.py:358`; external consumer backend `MCPToolInvocationResponse`/`MCPToolContentItem` (`models.py:~500-518`, `resource` support per spec.md:25).
- `invoke_mcp_method` signature (`meta` kwarg) mocked by recorders in `tests/test_single_usage.py:798-911` (`recording_invoke(session, method, params, meta=None)`) — a new kwarg would break these fakes.

### Architecture and Layers Affected
- API/route: `server/routes.py`; schema: `models/request.py`; client layer: `client/methods.py`, `client/manager.py`, `client/single_usage.py`, `client/managed.py`, `client/cache.py`, `client/transports.py`; deploy: `Dockerfile`, `deploy-templates/`.

### Integration Points
- MCP Python SDK `stdio_client`/`StdioServerParameters`, `ClientSession.call_tool`, `mcp.types` (`CallToolResult`, `TextContent`; `EmbeddedResource`/`BlobResourceContents` available, unused).
- CodeMie backend `POST /bridge` caller (`~/codemie-dev/codemie/src/codemie/service/mcp/models.py`).

### Patterns and Conventions
- Optional field + route-level builder + `meta`-style kwarg threading (EPMCDME-14847). Ticket-tagged comments (`# EPMCDME-NNNNN:`). Logging via `utils/logger.py`, masking via `utils/masking.py` (`mask_user_context`, `mask_dict_values`). Env-configured limits read with `int(os.getenv(NAME, default))` at module level.

---

## 3. Documentation Findings

### Guides and Architecture Docs
- `.ai-run/guides/architecture/architecture.md` — cache TTL + config-based hashed keys (`:65,90-94,267`), env table (`:229`). No mention of cwd or output dirs.
- `.ai-run/guides/testing/testing-patterns.md`, `development/development-practices.md`, `quality-gates.md` apply (not specific to this domain).

### Architectural Decisions
- WebSocket rejected (ADR-007, `manager.py:107`). EPMCDME-11351 McpError → isError result. EPMCDME-14847 meta only on tools/call. AGENTS.md: changing `/bridge` request/response schema is "Ask first".

### Derived Conventions
- Per-call data never mutates the cached `ManagedClient`; only the cache key partitions processes.

---

## 4. Testing Landscape

### Existing Coverage
- `tests/test_mcp_methods.py` — `invoke_mcp_method` routing, tools/call args, null stripping, McpError mapping.
- `tests/test_bridge_validation.py` — schema validation, extra field → 400, `user_context` meta forwarding (cached + single-usage, `:150-234`).
- `tests/test_cache.py`, `tests/test_client_manager_cache.py`, `tests/test_cache_cleanup.py` — cache get/set/TTL, key generation.
- `tests/test_single_usage.py` — single-usage transports, `TestMetaForwarding` (`:798`).
- `tests/test_client_name.py`, `tests/test_managed_lifecycle_errors.py` — stdio spawn params, lifecycle.
- `tests/test_process_output.py`, `tests/test_transports.py`, `tests/test_main_error_handling.py`.

### Testing Framework and Patterns
- pytest + pytest-asyncio (`pytestmark = pytest.mark.asyncio`), httpx `async_client` and `mock_mcp_client` fixtures, `monkeypatch` of function-local import targets (`src.mcp_connect.client.methods.invoke_mcp_method`), `FakeContext`/`DummySession` fakes for stdio.

### Coverage Gaps
- No test asserts `StdioServerParameters.cwd` (never set). No filesystem-based tests exist. `tests/integration/` is empty (AGENTS.md trap) — no real stdio server E2E in this repo.

---

## 5. Configuration and Environment

### Environment Variables
- `MCP_CONNECT_DEFAULT_TIMEOUT` (routes.py:46), `MCP_CONNECT_INIT_TIMEOUT`/`HTTP_TIMEOUT`/`SSE_READ_TIMEOUT` (managed.py:41-43, single_usage.py:45-47), `MCP_CONNECT_CLIENT_CACHE_TTL` (cache.py:100), `MCP_CONNECT_CACHE_CLEANUP_INTERVAL` (main.py:107), `DEBUG_LOG_BRIDGE_PAYLOAD`, `ACCESS_TOKEN`, `MCP_CLIENT_NAME`, `LOG_LEVEL`, `LOG_FORMAT`, `PORT`. No output-dir or capture variable exists.

### Configuration Files
- `Dockerfile` (`USER codemie`, `WORKDIR /home/codemie`, `:310-311`); `deploy-templates/values.yaml`, `templates/statefulset.yaml`.

### Feature Flags and Deployment Concerns
- No feature-flag mechanism. Writable paths limited to `emptyDir` `/tmp` and `/home/codemie`; 2Gi ephemeral-storage limit; single replica.

---

## 6. Risk Indicators

- No existing file-capture code: entirely new mechanism in `client/methods.py` result path (P1).
- Cache key excludes user identity (`cache.py:223-229`): one cached stdio process with one cwd serves all users with the same config — the core AC #6 constraint (P3).
- Speculative: putting a per-user/per-conversation value into `env` would partition the cache per value, multiplying live processes (each held up to TTL 5 min) — affects memory on a 1Gi pod.
- Speculative: an LLM-driven shell/filesystem server can write anywhere it is permitted (`/tmp`, `/home/codemie`); a cwd/env hint does not confine it.
- Response size: base64 inflates ~33%; `bridge_endpoint` builds the whole JSON in memory, no cap (`routes.py:358-369`); pod memory limit 1Gi vs. backend 100 MB file limit.
- Storage: `/home/codemie` is a 2Gi-limited `emptyDir`; no cleanup/retention mechanism for files exists.
- Concurrency: cached sessions are shared; two concurrent tools/calls on one process share any directory snapshot window.
- Contract: task says pre-deploy backend send fails with 422; code returns 400 (`main.py:223`). Deploy-order note in MRs should cite the right status.
- Test fakes `recording_invoke(..., meta=None)` in `tests/test_single_usage.py:809,906` break if `invoke_mcp_method` gains a required/extra kwarg.
- Origin of the `<32-hex session>` directory is unverified in this repo.
- No integration tests (`tests/integration/` empty); E2E only manual via docker.

---

## 7. Summary for Complexity Assessment

The task touches the request schema (`models/request.py`), the route layer (`server/routes.py`), and the client layer at every stdio spawn site (`client/managed.py:236`, `client/single_usage.py:139`, `client/transports.py:55`) plus the tools/call result path (`client/methods.py:90-124`) and possibly the cache key (`client/cache.py:210`). Deployment constraints (`Dockerfile:311`, read-only root FS with `emptyDir` `/home/codemie` and `/tmp`, 2Gi ephemeral storage, 1Gi memory, 1 replica) bound where files can live. A small coordinated change is also expected in the backend repo (`MCPExecutionContext`/`MCPToolInvocationRequest`, spec.md Follow-up).

Novelty is high: no code in `src/` reads files, builds embedded resources, or sets a child process cwd; the only existing precedent is the EPMCDME-14847 `user_context` → `meta` threading pattern, which shows how a per-request value flows from route to `invoke_mcp_method` without touching the cached process. The central tension is factual: cached stdio processes are keyed by config only and shared across users, while AC #6 requires per-user file isolation.

Test posture is good for the surrounding code (methods, cache, validation, meta forwarding, single-usage fakes) with established fixtures, but there are no filesystem tests, no cwd assertions and no integration tests; E2E is manual. Key risks: cross-user isolation under the shared cache, memory/size of base64 payloads, storage retention on a 2Gi emptyDir, and the cross-repo deploy order (400, not 422, on early send).

---

## 8. External References

- `~/codemie-dev/codemie/src/codemie/service/mcp/models.py` — resolved. `MCPExecutionContext` (`:89`): `conversation_id` (`:114-119`, `exclude=True`, "Local-only assistant conversation identifier for auth recovery retry scoping"), `request_uuid` (`:120-125`, `exclude=True`, "Local-only turn identifier; MCP artifacts are published under artifacts/<request_uuid>/."). `to_request_fields` (`:175-202`) = `model_dump(exclude={"auth_headers","conversation_id","oauth2_token_data","oauth2_auth_config_id","oauth2_auth_config","user_context":{"extra_attributes"}})` — `request_uuid` not listed (field-level exclude only). `MCPToolInvocationRequest` (`:521-556`) fields: `method, serverPath, args, params, env, mcp_headers, http_transport_type, single_usage, user_id, assistant_id, project_name, workflow_execution_id, request_headers, user_context` — no `conversation_id`/`request_uuid`.
- `~/codemie-dev/codemie/docs/superpowers/tasks/2026-09-14-epmcdme-14735-downloadable-mcp-artifacts/spec.md` — resolved. `:152` "## Follow-up: MCP-Connect captures generated files"; `:155` "Backend prerequisite, **not done yet**: per-conversation scoping needs `conversation_id` and `request_uuid` on the bridge request ... sending them before MCP-Connect accepts them makes every MCP call fail with 422. Order: MCP-Connect accepts the fields first, then this backend sends them." `:25-26` deliverable = embedded resource with `blob` or `text` (text UTF-8). `:35` publish location `artifacts/<turn-id>/<last-segment-of-name>`. `:142` workdir diffing rejected in backend run 2. `:148` enterprise delegate may lack `request_uuid`; enterprise `ToolConsumer` strips `resource`/`uri`/`name` (EPMCDME-16353).
- `~/codemie-dev/codemie-ui/docs/superpowers/tasks/2026-09-21-.../` — not read (UI; not needed for this repo's facts).

## Facts Added by Review

Researched for the names the spec relies on, after the analysis above was written. Read like the facts layer; where a line here contradicts one above, this one was read later.

- `start.sh:22` `exec uvicorn ...` with no `cd` → service cwd is `/home/codemie`.
- All three stdio spawn sites build `StdioServerParameters(command, args, env)` with **no `cwd`**: `client/transports.py:55-59`, `client/managed.py:236-240`, `client/single_usage.py:139-143`. Stdio servers (and anything they run, these scripts included) start with cwd `/home/codemie`.
- Scripts root-owned 755 in `/usr/local/bin` so `codemie` (UID 1001) cannot modify them — `Dockerfile:295-298`, `README.md:250-264`. Alternative: ship under `/home/codemie`. Reason recorded: tamper-proofing.
- Absolute-path-only arguments — both scripts; README calls it "prevents directory traversal" (`README.md:334,367`). No containment to a root dir exists.
- `Dockerfile:297-298` (install), `README.md:256-257,305-429` (docs, examples using `/home/codemie/<project>`), `run_in_python_venv.sh:46` (references the other script).
- No Python code, test, Helm template or MCP server config in this repo calls them. Runtime consumers are model-driven shell MCP servers (README example: `uvx cli-mcp-server` with `ALLOWED_DIR=/home/codemie`, `README.md:380-396`) — outside this repo.
- MCP-Connect `src/mcp_connect/client/methods.py:86-88` `invoke_mcp_method`: `tools/list` -> `_call_with_optional_cursor(session.list_tools, payload)` (`:287-303`). Cursor present -> `list_tools(params=PaginatedRequestParams(cursor=str(cursor)))`; absent -> `list_tools()`. Exactly one page per `/bridge` call; MCP-Connect never follows `nextCursor` itself. Returns the SDK `ListToolsResult` (pydantic) untouched.
- Signature `invoke_mcp_method(session, method, params, meta=None)` (`methods.py:54-59`) carries no transport type and no request object. Transport is decided upstream from `request.serverPath`/`request.http_transport_type` via `detect_transport_type` (`client/manager.py`, `client/single_usage.py:96-99`, `client/managed.py:200`).
- Callers: `invoke_with_timeout` (`client/manager.py:39-74`, cached path) and `_execute_stdio_request`/`_execute_http_request`/`_execute_sse_request` (`client/single_usage.py:105-159`, single_usage path). Both return the result unchanged.
- `src/mcp_connect/server/routes.py:356-369` `bridge_endpoint`: `result.model_dump(mode="json", exclude_none=True)` then `JSONResponse`. No per-tool processing.
- MCP SDK `.venv/.../mcp/client/session.py:532-562` `ClientSession.list_tools` records only `tool.outputSchema` per tool name (`_tool_output_schemas`, `:151`, `:562`); `call_tool` (`:386-425`) uses it to validate structured output. Nothing in the SDK client reads `inputSchema`.
- **No code in `src/` reads or modifies `inputSchema`** (grep `inputSchema|input_schema|ListToolsResult` in `src/`: only `methods.py:88`).
- `codemie/src/codemie/service/mcp/client.py:136-176` `MCPConnectClient.list_tools`: posts `method="tools/list"`, `params={}` (no cursor ever) and parses with `MCPListToolsResponse` (`service/mcp/models.py:398-409`, only field `tools`; `nextCursor` is ignored). So only the first page of tools reaches the backend.
- `MCPToolDefinition.inputSchema: dict[str, Any]` (`models.py:380-395`). Only consumer: `toolkit.py:550-551` `_create_args_schema` -> `json_schema_to_model(tool_def.inputSchema)`; empty schema -> bare `create_model`. On any exception, `_create_tools` (`toolkit.py:594-601`) falls back to an empty args schema for that tool.
- LangChain `langchain_core/tools/base.py:711-759` `_parse_input`: `model_validate(tool_input)`, `model_dump()`, then keeps only keys `if k in tool_input` (`:741`, `:759`). A provided `codemie_export_files` value is kept; an omitted one is not sent.
- `codemie_tools/base/codemie_tool.py:142-147` `_run` -> `MCPTool.execute(**kwargs)` (`toolkit.py:254`, `:352`) -> `_aexecute_with_context` (`toolkit.py:142-191`) -> `mcp_client.invoke_tool(tool_args=kwargs)` -> `params={"name": tool_name, "arguments": tool_args}` (`client.py:236-241`). **The value is forwarded verbatim in `arguments`.**
- Direct-invoke path `tool_execution_service.py:87-93` validates `tool.args_schema(**tool_args)` then `execute_tool` (`:80-84`).
- `toolkit.py:167-170`: `response.isError` -> `MCPToolExecutionError("MCP tool execution failed: " + joined item.text)`. `item.text` is read on every content item.
- MCP-Connect side of tools/call: `methods.py:90-109` takes `arguments` via `_optional_mapping_param`, `_strip_none_values` (`:244-252`, recursive, dicts only), passes to `session.call_tool`. No other argument filtering exists.
- Null stripping on tools/call (`methods.py:244-252`) exists because Zod-strict servers reject explicit nulls. This is the one existing place that edits `arguments`.
- `/bridge` response serialization uses `exclude_none=True` (`routes.py:359`). The intent, per `tests/test_bridge_validation.py:315-377`, is to drop SDK-level null fields (`nextCursor`, `_meta`, `outputSchema`). `inputSchema` is a `dict[str, Any]` on `mcp.types.Tool`. Unverified here: whether Pydantic's `exclude_none` also drops `null` values inside that dict (e.g. `"default": null`). No test covers it.
- Backend toolkit cache: `MCPToolkitFactory._toolkit_cache = TTLCache(ttl=MCP_TOOLKIT_FACTORY_CACHE_TTL)` (`toolkit.py:722-726`), default **600 s** (`configs/config.py:606`), keyed by `_generate_cache_key(server_config)` (`toolkit.py:847+`; command, args, env, headers, auth). A cached toolkit is returned as-is (`:755-765`), so a schema change is seen only after expiry or a config change. `MCPToolkitService._instances_cache` TTL is **3600 s** (`config.py:602`, `toolkit_service.py:171-172`) and caches service instances by base_url, not schemas.
- "injects into each stdio tool's inputSchema on tools/list": no injection point exists today. `invoke_mcp_method` has no transport info (`methods.py:54-59`), and transport is known only where the request is (routes/manager/single_usage). This is a fact about where the information is available, not a recommendation.
- "strips it on tools/call": consistent with an existing precedent, `_strip_none_values` on `arguments` (`methods.py:93`).
- "optional array-of-strings survives json_schema_to_model": holds (`json_schema_utils.py:388-395`, `:788-800`).
- "value forwarded in tool_args": holds (LangChain `base.py:741`; `client.py:240`).
- "pagination": backend never sends a cursor (`client.py:163`) and ignores `nextCursor`. Only tools on page one get the property.
- `inputSchema` in the tools/list response: backend `_create_args_schema` only (grep `inputSchema` in `codemie/src`: `models.py:395`, `toolkit.py:550-551`). Other `/bridge` clients outside these two repos: unverified.
- tools/call `arguments`: the downstream MCP server (receives it after any strip) and `_mask_params_recursive` logging (`methods.py:99-103`).
