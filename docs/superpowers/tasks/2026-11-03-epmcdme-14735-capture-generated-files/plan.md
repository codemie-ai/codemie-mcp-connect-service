# EPMCDME-14735 Explicit File Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** On opted-in stdio servers, inject an optional `codemie_export_files` tool parameter and append the files it names to the `tools/call` result as embedded `resource` items.

**Architecture:** A new module, `src/mcp_connect/client/export.py`, is called twice from `bridge_endpoint` (`server/routes.py:303-369`). `prepare` runs before the handler and `apply` runs after it. `invoke_mcp_method`, the handlers and the `/bridge` schema do not change.

**Tech Stack:** Python 3.12, FastAPI/Starlette, `mcp.types` (`EmbeddedResource`, `BlobResourceContents`, `TextContent`), stdlib `os`, `stat`, `mimetypes`, `base64`, `threading`, `asyncio.to_thread`.

**Spec:** `spec.md` (same dir). Technical analysis: `technical-analysis.md`.

## Global Constraints

- mypy --strict clean. Add no new dependency. Do not touch `poetry.lock`. Do not change the `/bridge` request or response schema.
- All file access, base64 encoding and the rendering of a response that carries exports run in `asyncio.to_thread`.
- Log through `utils/logger.py`. Never log file contents.
- Tag new code comments with `# EPMCDME-14735:`. Commit per task using the repository's existing convention.
- Env limits are read as `int(os.getenv(NAME, default))` at module level:
  - `MCP_CONNECT_EXPORT_MAX_FILE_BYTES` = 50 MiB
  - `MCP_CONNECT_EXPORT_MAX_CALL_BYTES` = 50 MiB
  - `MCP_CONNECT_EXPORT_MAX_FILES` = 20
  - `MCP_CONNECT_EXPORT_MAX_INFLIGHT_BYTES` = 100 MiB. Rationale for the default: base64 plus JSON costs about 5× the file size, so 100 MiB of files is about 500 MiB of memory on a 1Gi pod.
- Constants:
  - `EXPORT_ROOT = "/home/codemie"`
  - `WORKDIR_ARG_NAMES = ("directory", "cwd", "working_directory")`
  - `EXPORT_PARAM = "codemie_export_files"`
  - `SWITCH_KEY = "CODEMIE_EXPORT_FILES"`
  - The description string is built from `EXPORT_ROOT` and `WORKDIR_ARG_NAMES`, and its wording is the spec's (spec l.25).

## Review Focus

- A substitution error raised inside `prepare` must surface exactly as it does today. `prepare` catches it, treats export as off, still strips the switch and the parameter, and lets the handler raise. Test in Task 1.
- File names with spaces or non-ASCII characters in `uri`. Percent-encode the name with `urllib.parse.quote`. Test in Task 3.
- A file that is truncated or grows between `fstat` and read. Read at most `st_size` bytes and export what was read. Test in Task 2.
- The same path listed twice in one call. It is exported once. Test in Task 2.
- A handler exception after `prepare` holds no reservation, because reservations are taken only in `apply`. Covered by Task 3's release test.

---

### Task 1: Export module: prepare, switch, strip, tools/list injection, route hook

**Files:**
- Create: `src/mcp_connect/client/export.py`
- Modify: `src/mcp_connect/server/routes.py:350-369`
- Test: `tests/test_export_prepare.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class ExportContext`, with fields `stdio: bool`, `enabled: bool`, `method: str`, `requested: Any`, `base_dir: str | None`.
    - `requested` is the raw parameter value, or `None` when the parameter is absent.
    - `base_dir` is the first absolute string argument named in `WORKDIR_ARG_NAMES`, checked in tuple order.
  - `def prepare(request: BridgeRequestBody) -> tuple[BridgeRequestBody, ExportContext]`
  - `async def apply(ctx: ExportContext, result: Any, headers: dict[str, str]) -> Response`
- Consumes: `apply_substitutions` (`utils/substitution.py:82`) and `detect_transport_type` (`client/manager.py:93`).

Test-first: yes. The failing tests:
- `test_switch_true_values`: the switch is on for `true`, `1`, `yes`, `on`, `TRUE` and a JSON `true`, and off for `false` or when unset.
- `test_switch_stripped_from_env_on_every_transport`: the key never reaches the handler's request, so it is in neither the cache key nor the child env (AC 8).
- `test_param_stripped_on_stdio_call_when_disabled`: the server receives exactly the other arguments (AC 2).
- `test_param_not_stripped_on_http`: http and sse requests reach the handler unchanged.
- `test_dollar_value_reaches_handler_unchanged`: `args=["$X"]` reaches the handler literally.
- `test_substitution_error_still_raised_by_handler`
- `test_tools_list_injected_every_tool`:
  - The property is created when `properties` is missing.
  - It is never added to `required`.
  - An existing `codemie_export_files` entry is left untouched (AC 1).
- `test_tools_list_unchanged_when_disabled_or_http`: the response body is byte-identical to today's `JSONResponse` (AC 9).

- [ ] Write the tests. Use the `async_client` fixture and monkeypatch the route's handler functions to capture the request they receive.
- [ ] Run `poetry run pytest tests/test_export_prepare.py -v`. Expected: FAIL (module missing).
- [ ] Implement `prepare`:
  1. Run `apply_substitutions` on the request. Use the substituted copy only to read the switch (`str(v).strip().lower() in {"true","1","yes","on"}`) and the transport. On a substitution exception, set `enabled=False` and still strip.
  2. Return `request.model_copy(deep=True)` with the switch key popped from the original `env`.
  3. On stdio `tools/call`, also pop `EXPORT_PARAM` from `params["arguments"]`.
- [ ] Implement `apply`, `tools/list` branch: when `ctx.stdio and ctx.enabled`, set `tool.inputSchema.setdefault("properties", {}).setdefault(EXPORT_PARAM, prop)` on every tool. In every case that is not an export, return today's `JSONResponse(result.model_dump(mode="json", exclude_none=True) if hasattr(...) else result, headers=headers)`.
- [ ] In `routes.py:350-369`, call `prepare` before handler dispatch. Pass the returned request to the handler, and replace the dump and return with `return await apply(ctx, result, headers)`.
- [ ] Run the tests above, plus `tests/test_bridge_validation.py` and `tests/test_single_usage.py`. Expected: PASS.

### Task 2: File collection: path checks, limits, budget, mime

**Files:**
- Modify: `src/mcp_connect/client/export.py`
- Test: `tests/test_export_collect.py`

**Interfaces:**
- Produces:
  - `@dataclass class Collected`, with fields `items: list[EmbeddedResource]`, `refusals: list[str]` (each entry is `"<given path>: <reason>"`) and `reserved: int`.
  - `def collect_exports(paths: list[str], base_dir: str | None, skip_names: set[str]) -> Collected`. It is synchronous and is run through `asyncio.to_thread`.
  - `def release(n: int) -> None`. It decrements the pod-wide counter. The counter is a module `int` guarded by a `threading.Lock`.

Test-first: yes. The failing tests monkeypatch `EXPORT_ROOT` to `tmp_path.resolve()`:
- Each AC 6 case is refused, with its reason in `refusals`. The FIFO case must return without blocking. Cases:
  - outside the root
  - a path with a `..` segment
  - a final-component symlink inside the root
  - a symlink pointing outside
  - a non-hidden linked folder pointing into `.hidden/`
  - a FIFO
  - a directory
  - a missing file
  - `.ssh/x`
- A relative path resolves against `base_dir`, else against the root.
- The `mimeType` is correct for xlsx, csv, json, zip and pdf, and is `application/octet-stream` for an unknown extension (AC 5).
- Each limit refuses with a named reason: the per-file limit, the per-call limit, the 21st file and the budget (AC 7).
- A duplicate path is exported once. A name in `skip_names` is skipped.
- A file truncated after `fstat` yields only the bytes that were read.

- [ ] Write the tests.
- [ ] Run `poetry run pytest tests/test_export_collect.py -v`. Expected: FAIL.
- [ ] Implement `collect_exports`. Per AR-30, follow this order for each path:
  1. Refuse a non-string entry, an empty entry, or any path with a `..` segment.
  2. Compute `p = os.path.normpath(os.path.join(base_dir or EXPORT_ROOT, given))`.
  3. Refuse when `os.path.realpath(p) != p`, which means a symlink in some component.
  4. Refuse when `p` is outside `EXPORT_ROOT` (check with `os.path.commonpath`), or when any segment below the root starts with `.`.
  5. Call `os.open(p, O_RDONLY|O_NOFOLLOW|O_NONBLOCK)`, then `fstat`. Refuse anything where `S_ISREG` is false.
  6. Apply the limits in this order: per-file, count, per-call, then reserve the size against the budget.
  7. Read up to `st_size` bytes.
  8. Build `EmbeddedResource(type="resource", resource=BlobResourceContents(uri="file:///"+quote(basename(given)), mimeType=..., blob=b64))`.

  Use explicit mime entries for the AC 5 types before `mimetypes.guess_type`. Close the file descriptor in a `finally`.
- [ ] Run the tests. Expected: PASS.

### Task 3: tools/call apply, releasing response, off-loop render

**Files:**
- Modify: `src/mcp_connect/client/export.py`
- Test: `tests/test_export_apply.py`

**Interfaces:**
- Consumes: `collect_exports` and `release` (Task 2), `ExportContext` (Task 1).
- Produces: `class ExportJSONResponse(JSONResponse)`, created with a `reserved: int` argument. Its `async __call__` does `try: await super().__call__(...) finally: release(self.reserved)`.

Test-first: yes. The failing tests:
- With an absent, `null` or `[]` value, the body is byte-identical to today's (AC 10).
- A value that is not a list of strings gives one refusal note, and the call result is otherwise intact.
- With `isError=True` and a non-empty request:
  - the content is unchanged
  - one `TextContent` saying `"export skipped: the call failed"` is appended
  - `collect_exports` is never called
- `isError=True` with no request is byte-identical, including the `_mcp_error_to_tool_result` output (AC 10).
- Accepted files are appended after the server content, which stays byte-identical, images included. Refusals are appended as one text item listing each path with its reason.
- A file whose basename already appears as a `resource` uri in the server result is not appended.
- The `uri` of a name with spaces is percent-encoded.
- The budget returns to 0 after a successful send, and also when the ASGI `send` raises (AC 7).
- When `JSONResponse` construction raises inside `apply`, the reservation is released.
- When export is disabled or the transport is http, the result is not modified.

- [ ] Write the tests. Drive `ExportJSONResponse` with a fake `send` that raises.
- [ ] Run `poetry run pytest tests/test_export_apply.py -v`. Expected: FAIL.
- [ ] Implement the `tools/call` branch of `apply`. It acts only when `ctx.stdio and ctx.enabled and ctx.requested not in (None, [])`. Collect via `await asyncio.to_thread(collect_exports, ...)` and append to `result.content`. Build the response with `await asyncio.to_thread(ExportJSONResponse, content=dump, headers=headers, reserved=c.reserved)` so the render runs off the loop. If anything raises before the response exists, call `release(c.reserved)` and re-raise.
- [ ] Run all `tests/test_export_*.py`. Expected: PASS.

### Task 4: README and architecture guide

**Files:**
- Modify: `README.md` (the env and config section, plus the shell and Filesystem server examples near `:380-396`)
- Modify: `.ai-run/guides/architecture/architecture.md` (env table near `:229`)

Test-first: no. This is docs only.

- [ ] Document the following, in the spec's wording:
  - the `CODEMIE_EXPORT_FILES` opt-in, with shell and Filesystem server examples over `/home/codemie`
  - that opt-in is "not an access control", and the read reach it gives a server without file reach
  - the four limit env vars and their defaults
  - the path rules: relative-path base, hidden segments, symlinks refused
  - the known behaviors: named files only, earlier-turn files, duplicate chips across calls, up to 600 s for the backend cache
  - the reserved-name risk
  - the assistant-instruction line "When you create files for the user, list them in codemie_export_files."

  AC 3, 4 and 12 rely on this text.

### Task 5: Backend spec follow-up (other repo, docs only)

**Files:**
- Modify: `~/codemie-dev/codemie/docs/superpowers/tasks/2026-09-14-epmcdme-14735-downloadable-mcp-artifacts/spec.md:152-155`

Test-first: no. This is docs only, in another repo, on a separate MR.

- [ ] Rewrite the Follow-up section to say that MCP-Connect uses explicit export through `codemie_export_files`, so no new bridge fields are needed. Correct "422" to "400".
