# Technical Research

**Task**: mcp-connect export resource_link file link strict file URI export.apply collect limits budget stdio (design v3)
**Generated**: 2026-11-05
**Research path**: codegraph
**Workspace root**: /home/aliaksei_chumakou/codemie-dev
**Repository**: codemie-mcp-connect-service, branch `EPMCDME-14735_capture-generated-files` (`.git/HEAD`; `export.py` present on disk; commit not re-resolved, v2 recorded `4563dc12ebe2`). Index bound to that root. Backend `codemie` read-only for wire acceptance.
**Valid from v2 (not redone)**: `v2-read-resource-in-session/technical-analysis.md` Sections 2-5 for SDK types, cache/single-usage, `_check_path` semantics, README/guide locations. Only v3-specific facts below.

---

## 1. Original Context

EPMCDME-14735 AC #1 for LINK-ONLY MCP resources (`resource_link {uri,name,mimeType?,size?}`), revised design (v3). MCP-Connect delivers a linked file by treating a strict `file:///<absolute path>` link in a stdio tools/call result as one more EXPORT path: it reads the file itself from the pod's local disk with the existing explicit-export file-reading code (MR !314: src/mcp_connect/client/export.py on branch EPMCDME-14735_capture-generated-files: _check_path realpath + hidden-segment checks under /home/codemie, open with O_RDONLY|O_NOFOLLOW|O_NONBLOCK, fstat regular-file check, limits 50 MB/file, 50 MB/call, 20 files, pod-wide in-flight budget, reservation released in finally after response send, refusals listed in one appended text item, items appended as embedded `resource {uri file:///<name>, mimeType, blob}`), NOT via `session.read_resource`. Rationale: stdio servers run in the same pod, so the file is on the same disk; the bridge (not the MCP server) opens the file so all export guards apply; no live session is needed so the step can run in export.apply after single-use sessions close. Previous design (v2, read via `session.read_resource` inside the session) is archived with its analysis at /home/aliaksei_chumakou/codemie-dev/docs/stories/2026-11-04-mcp-link-only-resource-delivery/v2-read-resource-in-session/technical-analysis.md (read it for facts; do not redo what is still valid). The completed !314 run artifacts are at /home/aliaksei_chumakou/codemie-dev/codemie-mcp-connect-service/docs/superpowers/tasks/2026-11-03-epmcdme-14735-capture-generated-files/ (spec.md is the approved design: opt-in CODEMIE_EXPORT_FILES, stdio only, same uid 1001 residual accepted, criterion 11 "export reaches nothing the server could not already read", non-goals: per-user/conversation folders, OS isolation). Constraints decided with the user: only resource_link items (a `resource` with only a uri fails SDK parsing and is out of scope); only strict `file:///<absolute path>` links (no host, query, fragment, encoded slashes or dots; decode once, then same checks as export); only links present in that call's result; same opt-in switch as export (already opted-in servers also get links resolved); a refused/failed link item is replaced by one note; tool result never lost; delivered inside MR !314 (not a separate MR); no backend or UI change (backend receives ordinary embedded resource items); plugin path and Radar out of scope; AC #6 stays the accepted same-uid residual (criterion 11), no per-user folder enforcement. Questions to answer: (1) where link scanning hooks in relative to export.prepare/apply in routes.py bridge_endpoint, and whether it can run purely in export.apply on the finished CallToolResult (including single_usage and cached paths, isError results, results where the SDK has already parsed ResourceLink objects vs dicts); (2) how to feed link paths into the existing collect/limit/budget/note code with minimal change (what in _collect_into / limits / accounting / refusal-note building is reusable as is; how to share the per-call budget with codemie_export_files paths, ordering: explicit export first), and how an explicit export of the same file and a link to it dedupe (the existing within-call dedupe by name); (3) URI -> path decoding rules for strict file:///: where decode happens, what is refused, and how this interacts with _check_path (which does not percent-decode) and relative paths; (4) what replaces the link item (note text item) and effect on the backend which reads item.text (toolkit.py:168 notes) and on `resource_link` items for non-opted-in servers (unchanged); (5) the declared `size` on ResourceLink: use for early refusal; (6) blast radius within the repo: files, tests (about which test files; ExportContext positional construction in test_export_apply.py:43 and test_export_prepare.py:143), README and architecture-guide sections, deploy values; (7) risks incl. memory, event-loop, symlink/TOCTOU, remote transports (stdio only), non-stdio servers returning file links, and what is unverified. Repo conventions: codemie-mcp-connect-service/AGENTS.md.

---

## 2. Codebase Findings

Repository impact: `codemie-mcp-connect-service` = **affected**. Backend `codemie` = **not_affected** by the proposed change (read-only check of wire acceptance below). UI, plugin, Radar = out of scope, not examined.

### Existing Implementations

Purpose A - "A file the tool hands over as a `resource_link` reaches the user as a download."
- Nothing in MCP-Connect handles links today: `resource_link|ResourceLink` has zero matches in `src/` and `tests/`. A link passes `export.apply` as dumped by the SDK.
- Backend: `codemie:src/codemie/service/mcp/toolkit.py:390-409` publishes embedded `resource` with blob/text; a `resource_link` (type listed at :416) or a blob-less resource becomes `` `<name>` stays on the MCP server and was not delivered `` (:400-404). `MCPToolContentItem` (`codemie:.../mcp/models.py:421-446`) has optional `text`, `uri`, `name`.
- Explicit export (same purpose, other trigger; all in `export.py`, the file the change extends):
  - `prepare` :112-142: strips switch and `codemie_export_files`; `ExportContext(stdio, enabled, method, requested, base_dir)` frozen dataclass :84-92.
  - `apply` :303-316: dumps with `model_dump(mode="json", exclude_none=True)` if `hasattr(result,"model_dump")`, else uses the object as is (:305); acts only if `ctx.stdio and ctx.enabled and isinstance(dump, dict)`; for `tools/call` enters `_export_call` only when `ctx.requested not in (None, [])` and `dump["content"]` is a list (:313); otherwise a plain `JSONResponse` (:316). A call with no export request therefore never reaches code that could see links.
  - `_export_call` :319-353: `isError` -> appends "export skipped: the call failed" and nothing else (:323-324); non-list request -> one note; else `asyncio.to_thread(collect_exports, requested, base_dir, _existing_resource_names(content))` shielded (:328-335), extends `content` with item dumps, appends one `"Files not exported:\n" + "\n".join(refusals)` text item (:339-340), builds `ExportJSONResponse` in a thread (:347) which releases `reserved` after send (:270-281); `except BaseException: release(reserved)`.
  - `collect_exports` :188-200 creates `Collected(items, refusals, reserved)` and releases `out.reserved` on any exception; `_collect_into` :203-267 is the loop. Per path: `_check_path(given, base_dir)`; `name = basename(p)`; `if p in seen or name in skip_names: continue` (silent, no item, no refusal) :211-213; `os.open(O_RDONLY|O_NOFOLLOW|O_NONBLOCK)`; `fstat` regular-file; then limit ladder in this order: per-file `size > MAX_FILE_BYTES`, `len(out.items) >= MAX_FILES`, `total + size > MAX_CALL_BYTES`, `_reserve(size)` (:230-237); read loop, base64, `EmbeddedResource(uri="file:///"+quote(name), mimeType=_mime(name), blob)`; `total += size; out.reserved += size`. Refusal strings are `f"{given}: <reason>"`.
  - State local to one `_collect_into` invocation: `seen` (set of resolved paths) and `total`. Shared through `out`: `out.items` (count limit uses `len(out.items)`), `out.refusals`, `out.reserved`. `out.reserved` is incremented with `total` on every success (:259-260), so it equals `total` at the end of each call to `_collect_into`.
  - `Collected` carries no mapping from an input path to its resulting item or refusal; a deduplicated path yields neither.
  - Pod-wide budget: `_inflight` + lock, `_reserve`/`release` :145-158, limits read at import :50-54.
  - Dependents: `routes.py:352,368` only; tests `test_export_prepare.py`, `test_export_collect.py`, `test_export_apply.py`.
- Link types: `ResourceLink(Resource)` with `type="resource_link"`, `uri: AnyUrl` (host not required), `name`, optional `mimeType`, `size`, `description`, `annotations`, `meta` (`mcp/types.py:767-1204`). `ContentBlock` includes it (:1206). Dumped with `exclude_none=True` and no `by_alias`: `size`/`mimeType` appear only when set, `_meta` appears as `meta`.

Purpose B - "Result is final and the session is gone when links are looked at."
- `bridge_endpoint` `routes.py:303-368`: `export.prepare` (:352) -> `_handle_single_usage_request` or `_handle_cached_client_request` (:355-358, each wraps `wait_for`; v2 §2 Purpose C) -> `export.apply` (:368). Both paths return the same `CallToolResult` (or a mock/dict in tests) to `apply`; single-usage sessions and the child process are already closed there; cached processes stay alive up to a sliding 5 min TTL.
- `apply` runs outside the request `timeout` window (`wait_for` wraps only the handler).
- `_mcp_error_to_tool_result` (`methods.py:191-199`) builds `CallToolResult(isError=True, content=[TextContent])`; it contains no link.

Other touched code: `README.md:493-536` (export section) and :555-562 (env table); `.ai-run/guides/architecture/architecture.md:232-235` (env table). None found in `deploy-templates/values.yaml`, `.env.example`, `example_requests.http` (searched `export|EXPORT`).

### Decisions Already in the Code

- Convention: guards live in `_check_path` (string and `realpath`) and `_collect_into` (`open`/`fstat`/limits); refusals are listed, never dropped (README:527) except duplicates (`:212`). Limits are module attributes monkeypatched in tests; tests patch `export.EXPORT_ROOT` and `_inflight` via an autouse `root` fixture (`test_export_apply.py:34-39`, `test_export_collect.py:28-33`).
- Export APPENDS to server content and never rewrites it (`_export_call` :338-340); spec criterion 10 (`spec.md:102`): "The server's own content, images included, is byte-identical", with sub-bullets for absent/`[]`/error results. Replacing a link item in place would change server content for opted-in links; spec criterion 9 (`:101`) covers only HTTP/SSE.
- Reason `isError` results are not exported: "export skipped" note, spec `:104`.
- `_check_path` (:166-185): rejects non-str/empty, NUL, literal `".."` segment of `given.split("/")`, non-canonical (`realpath(p) != p`, any symlink incl. missing intermediate components resolve lexically), outside `EXPORT_ROOT` or root itself, any hidden segment. It does no percent-decoding and no existence check. For an absolute `given`, `os.path.join(base, given)` yields `given`, so `base_dir` is irrelevant.
- `_existing_resource_names` (:288-295) collects basenames only from `type == "resource"` dumped items with a str `uri`; a `resource_link` is not counted.
- Data form: the link carries a URI string; `_collect_into` takes plain filesystem paths. Today a path comes from the model as-is; nothing in `export.py` decodes URIs. `unquote` is imported (:34) and used only for name matching (:294).
- `ExportJSONResponse` + `to_thread(ExportJSONResponse,...)` renders the large body off the event loop (:347); the plain `JSONResponse(content=dump)` at :316/:353 renders on the loop.

### Task Statements Checked Against the Code

- "export.apply can run purely on the finished result" - holds for what is in `apply`: it receives the same finished object on cached and single-usage paths (`routes.py:355-368`); no session handle needed. Today `apply` only inspects `content` when `requested` is non-empty (`:313`), so the link branch is a new condition on the same `tools/call` branch.
- "SDK has parsed ResourceLink objects vs dicts" - `apply` normalises both: objects through `model_dump`, mock/dict results used as is; either way link items are dicts with `type == "resource_link"` and `uri` a str (`export.py:305`; tests pass `CallToolResult` in `test_export_apply.py:46`, mocks elsewhere). Real-SDK `ResourceLink` fixtures: none found.
- "reads the file with existing explicit-export code, all guards apply" - holds for `_check_path`, `O_NOFOLLOW`, `fstat`, per-file/call/count/budget limits; the guards run on a path string and have no notion of a URI.
- "the existing within-call dedupe by name" - partly: by resolved path, `seen`, per `_collect_into` call; by basename only against server-returned `resource` items via `skip_names`. A link to a file also named in `codemie_export_files` is not deduplicated if explicit and link paths go through two `_collect_into` invocations (fresh `seen`/`total`). Two files with equal basename in different directories both export with the same `file:///<name>` uri (no check).
- "decode once, then same checks as export" - `_check_path` rejects `".."` and NUL only after decoding is done by the caller; a decoded `%2f` introduces new segments, `%00` becomes NUL, `%2e%2e` becomes `..` - all caught by the existing checks if decoding happens first. Invalid UTF-8: `urllib.parse.unquote` default `errors="replace"` substitutes U+FFFD and succeeds; `errors="strict"` raises `UnicodeDecodeError`.
- "a `resource` with only a uri fails SDK parsing" - holds per v2 §2 (`EmbeddedResource.resource` is `TextResourceContents | BlobResourceContents`, `types.py:1185-1186`); not re-run.
- "strict `file:///` (no host, query, fragment, encoded slashes or dots)" - unverified against the dumped value: `ResourceLink.uri` is pydantic `AnyUrl`; `str()` of it is the normalised URL (pydantic-core / Rust `url` crate, WHATWG). Likely effects, NOT run: `file:/x` -> `file:///x`; `.`/`..` and `%2e`/`%2e%2e` path segments collapsed; backslash read as `/` in a file URL; `file://localhost/x` host dropped; spaces and non-ASCII percent-encoded. If so the dumped string cannot show what the server sent, and strictness checks apply to the normalised form only. What would settle it: one test dumping `ResourceLink(uri=...)` for each form. A raw dict (non-SDK result) carries the exact string.
- "backend receives ordinary embedded resource items; no backend change" - holds: export items are already `{"type":"resource","resource":{"uri","mimeType","blob"}}` and published by `toolkit.py:396-399`; filename from the last URI segment (v2 §2).
- "refused link is replaced by a note; non-opted-in links unchanged" - non-opted-in: holds trivially (`apply` returns `JSONResponse(dump)` at :316 when `enabled` is false; byte-identical test `test_export_apply.py:71-74`). Backend then shows "not delivered" (:400-404). Replacement is new behaviour (see Decisions: export appends).
- "keeps an existing mechanism in place": the explicit-export append/refusal-note shape and its `isError` rule (`_export_call`) - consumers: `routes.py:368`, the three export test files, README:524-529.

### Consumers of Changed Contracts

- `ExportContext` fields (adding a field or changing meaning): built `export.py:142`; positional in `tests/test_export_apply.py:43` (`ExportContext(stdio, enabled, "tools/call", requested, base_dir)`) and `tests/test_export_prepare.py:143` (`ExportContext(stdio, enabled, method, None, None)`). A trailing field with a default avoids touching them; none needed if links use only `stdio`/`enabled`/`method` (all present).
- `apply` branch condition (:313): `test_nothing_requested_is_byte_identical` (`test_export_apply.py:65-68`, `_result()` has text and image only), `test_disabled_or_http_not_modified` (:71-74), `test_error_result_without_request_is_byte_identical` (:96-105), `test_tools_list_unchanged_when_disabled_or_http` (`test_export_prepare.py:158-163`). They hold as long as results with no link stay on the plain path.
- `Collected` / `collect_exports(paths, base_dir, skip_names)` / `_collect_into(out, paths, base_dir, skip_names)`: called at `export.py:196, 329`; tests call `collect_exports` directly in `test_export_collect.py` (~25 tests, e.g. `:49, :70, :174, :180`, `slow_collect` monkeypatch in `test_export_apply.py:191-195` returns `Collected(reserved=7)`) and read `.items`, `.refusals`, `.reserved`.
- `_existing_resource_names`: `export.py:329` and indirectly `test_name_already_returned_by_server_is_not_appended` (`test_export_apply.py:128-139`).
- `ExportJSONResponse(content, reserved, ...)`, `release`, `_reserve`, `_release_when_done`: `export.py` and `test_export_apply.py:142-221`.
- `/bridge` response for `tools/call`: only consumer is the backend. `toolkit.py:167-168`: for `isError` responses it does `[item.text for item in response.content]` then `"\n".join(...)`; `text` is optional on `MCPToolContentItem`, so a non-text item (image, link) in an error result makes that join fail on `None` - existing behaviour, not caused by this change; a text-note replacement would avoid it. `_format_content_item` (`toolkit.py:435-452`) returns `item.text` for text items, so a note is shown to the model.
- Docs: `README.md:495,524-528,559-562`, `architecture.md:232-235`.

### Architecture and Layers Affected

Route pipeline (`server/routes.py` - no change needed per Purpose B) and `client/export.py` (prepare/apply/collect/accounting). `client/methods.py`, `manager.py`, `single_usage.py` are not on the path. SDK types `mcp.types.ResourceLink`, `EmbeddedResource`.

### Integration Points

`POST /bridge` -> stdio child (same container FS, `/home/codemie` volume `statefulset.yaml:75`, v2 §2) -> `export.apply` reads the local file -> JSON -> backend `toolkit.py:390-409`. No new external service or dependency.

### Patterns and Conventions

mypy strict; blocking file work through `asyncio.to_thread`; log through `utils/logger`; limits at import from `MCP_CONNECT_EXPORT_*`; `EPMCDME-NNNNN:` commits; tests with the change; README + architecture env table for user-facing variables; changing `/bridge` schema keys needs asking first (`AGENTS.md`) - replacing an item or adding `content` items adds no key.

---

## 3. Documentation Findings

### Guides and Architecture Docs
`README.md:493-536` documents explicit export only (path rules :524-529, known behaviour :531-536, "opt-in is not an access control" :522); no mention of links. `.ai-run/guides/architecture/architecture.md:232-235` env table. Spec: `docs/superpowers/tasks/2026-11-03-epmcdme-14735-capture-generated-files/spec.md` (criteria 8-11, non-goals :109-118).

### Architectural Decisions
Recorded in `spec.md` Decisions (:120+, superseded list :150) and README. Spec criterion 10 and non-goal "Changes to the `/bridge` request or response schema" are the entries a link feature touches.

### Derived Conventions
Section 2 Patterns.

---

## 4. Testing Landscape

### Existing Coverage
`test_export_collect.py` (path refusals, limits, dedupe, budget, ~25 tests), `test_export_apply.py` (append, byte-identical, error skip, budget release, cancellation), `test_export_prepare.py` (switch, strip, tools/list, one route test via `async_client`).

### Testing Framework and Patterns
pytest `<9`, pytest-asyncio auto mode, `tmp_path` resolved + `monkeypatch.setattr(export, "EXPORT_ROOT"|"MAX_*"|"_inflight")`, `JSONResponse(...).body` equality for byte-identical checks.

### Coverage Gaps
No test builds a `ResourceLink`; none exercises URI decoding, link replacement, a mixed explicit+link call, links in `isError` results, or link on a non-opted-in/HTTP server. No real stdio server returning a link.

---

## 5. Configuration and Environment

### Environment Variables
`CODEMIE_EXPORT_FILES` (server `env`, stripped by `prepare`); `MCP_CONNECT_EXPORT_MAX_FILE_BYTES|MAX_CALL_BYTES|MAX_FILES|MAX_INFLIGHT_BYTES` (`export.py:50-54`; defaults 50 MiB, 50 MiB, 20, 100 MiB).

### Configuration Files
`deploy-templates/values.yaml`: memory 1Gi, ephemeral 2Gi, read-only root FS; no export variables (searched). `.env.example`: none.

### Feature Flags and Deployment Concerns
Per-server `env` switch only. Link handling would be gated by the same switch: `ctx.enabled` already holds it (`prepare` :125). Unlike `codemie_export_files`, it does not depend on `tools/list` or the backend toolkit cache (README:535).

---

## 6. Risk Indicators

- Keeps in place: the explicit-export append-only shape and spec criterion 10 (server content byte-identical) - replacing link items edits server content on opted-in servers; see Task Statements and Decisions.
- Speculative: `apply` reaches `_export_call` only when `requested` is non-empty (`:313`); link scanning on every opted-in `tools/call` is a new always-on scan of the content list (cheap, no I/O unless a link is present).
- Speculative: `seen`/`total` are local to `_collect_into`; feeding explicit paths and link paths through separate invocations resets dedupe and the 50 MB per-call total (count limit alone is shared via `out.items`). One invocation over a combined list (explicit first) or passing `seen`/`out.reserved` forward keeps one budget.
- Speculative: `Collected` has no path-to-outcome mapping and `continue` on dedupe yields neither item nor refusal; in-place replacement needs per-link outcome (item / note / "already delivered") that the current return shape does not carry.
- Speculative: `_check_path` is called with the decoded path; decode must precede it (decoded `%2f`, `%00`, `%2e%2e` are caught by it only then); `unquote` default `errors="replace"` would turn invalid bytes into U+FFFD and the file then simply is not found.
- Unverified (SDK/URL normalisation, not run): `AnyUrl` may already collapse `..`, `%2e%2e`, backslashes and `file:/x` before `apply` sees the string, so the "strict" refusals can only be enforced on the normalised form for SDK-parsed results.
- `ResourceLink.size` is optional, advisory and server-declared (`types.py:776`); the authoritative size is `fstat`. A declared size above `MAX_FILE_BYTES` could be refused before `open`; a false small declaration changes nothing since `fstat` limits still apply (`_collect_into` :229-237).
- Memory: whole file is read, base64'd and JSON-rendered; export already budgets ~5x (`export.py:53`); up to 20 files and 50 MiB per call, 100 MiB pod-wide. Links add a second source of paths under the same budget; a server can emit many links, each refusal text grows `content`.
- Event loop: file reads must run in `to_thread` like `collect_exports`; the plain `JSONResponse` path at :316 renders on the loop - fine for link-free results, not for results gaining blobs (use `ExportJSONResponse` path :347).
- Timeout: `apply` runs after the `wait_for` window; reading links is not covered by `timeout` (explicit export has the same property).
- Single-usage: process and its tempfiles may be gone before `apply`; a server that deletes its output at exit makes the link "file not found" (refusal note). Whether any target MCP server does so: not checked.
- TOCTOU/symlink: `_check_path` `realpath` then `open(O_NOFOLLOW)` guards only the final component; an intermediate directory swapped between check and open is not covered (same as explicit export). Same uid 1001 as every server (README:522); AC #6 residual accepted per spec criterion 11.
- Trust boundary shift: explicit export paths come from the model's arguments; link paths come from the MCP server's output (possibly derived from remote/untrusted content for fetch-style servers). Criterion 11 ("reaches nothing the server could not already read") is stated for paths named by the model; whether it holds for server-named links on a server whose tools do not reach `/home/codemie` (the link is an assertion, not a read) is not covered by the spec text.
- Non-stdio servers returning `file:` links: `enabled` is false when not stdio (`prepare` :125) and `apply` returns the plain dump, so links stay untouched; unchanged by design.
- `isError` results: `_export_call` deliberately does not export; links in an error result have no rule today. Backend `toolkit.py:168` joins `item.text` of every error item and `text` is None for links/images (existing TypeError risk, `models.py:440`).
- Test blast: `test_export_apply.py:43` and `test_export_prepare.py:143` break only if `ExportContext` gains a required field; `Collected`/`collect_exports` signature changes touch `test_export_collect.py` (~25 tests) and the `slow_collect` fake (`test_export_apply.py:191-197`).
- Landing: change lives in the same file and README sections as !314 (branch is checked out); `main` containment not checked.

---

## 7. Summary for Complexity Assessment

One repository, one module: the work sits in `client/export.py` (`apply`, `_export_call`, `_collect_into`/`Collected`, URI decoding) plus README, the architecture-guide env/behaviour text, and three existing test files extended (`test_export_apply.py`, `test_export_collect.py`, optionally `test_export_prepare.py` for a route case). `routes.py`, `methods.py`, `manager.py`, `single_usage.py` stay untouched because `apply` already receives the finished result on every path and `ctx.enabled`/`ctx.stdio` are already there. No deploy-value, schema-key, backend or UI change.

Novelty is low to moderate: reading, limits, budget and release reuse existing code unchanged; new are the link scan, strict URI-to-path decoding, per-link outcome mapping (existing `Collected` returns no per-path result and dedupes silently), in-place replacement (export only appends), and one shared budget across explicit and link paths (`seen`/`total` are call-local). Test posture around export is strong (three files, budget/cancellation covered) but no test or fixture exists for `ResourceLink` or URI forms.

Key risks: the unverified SDK `AnyUrl` normalisation (strictness can only be enforced on the normalised string for SDK-parsed results), the conflict with spec criterion 10 (server content byte-identical) when a link is replaced, the always-on scan on opted-in calls, the trust shift from model-named to server-named paths against criterion 11, and links in `isError` results having no rule.

---

## 8. External References

- `v2-read-resource-in-session/technical-analysis.md`: resolved and read. Facts reused: SDK types (`ResourceLink`, `EmbeddedResource`), `_check_path` semantics, cache/single-usage behaviour, backend acceptance `toolkit.py:390-409`, README/guide locations, test infrastructure.
- `codemie-mcp-connect-service/docs/superpowers/tasks/2026-11-03-epmcdme-14735-capture-generated-files/spec.md`: resolved, read in part (Acceptance criteria 8-11 at :100-106, Non-goals :109-118). Facts: criterion 10 server content byte-identical (error and absent/`[]` sub-bullets), criterion 11 reach, non-goals per-user folders/OS isolation/schema changes. Other run artifacts in that folder: not read.
- MR !314 itself: remote, not read; `export.py` read from the checked-out branch on disk.
