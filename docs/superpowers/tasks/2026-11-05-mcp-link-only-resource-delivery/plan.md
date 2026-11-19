# Link-only resource delivery (delta on !314) Implementation Plan

**Goal:** In `export.apply`, resolve `resource_link` items of an opted-in stdio `tools/call` result into embedded files (or one note each), in place, through the !314 reading code under one shared budget.

**Spec:** `spec.md` here (delta on the !314 spec). **Analysis:** `technical-analysis.md`. Work on branch `EPMCDME-14735_capture-generated-files`; no new branch. Commit per task using the repository's existing convention (`EPMCDME-14735:` prefix). Gates are run by the calling flow, not by a task. Before Task 1, re-check the export switch handling (`prepare`) and the result shape (`apply`/`_export_call`) against the !314 head; if they differ from `export.py` as read, stop and report.

**Seam (AR-1), applies to Tasks 3-5:** `collect_exports(paths, base_dir, skip_names, links=None)` stays the single shielded job. `links` is a trailing optional list, so existing callers, `test_export_collect.py` and the `slow_collect(*a, **k)` fake (`test_export_apply.py:191`) keep working. `Collected` gains defaulted fields only.

**Negative constraints (checked):** no `resources/read` (T5 reads from disk only); no `/tmp` root (T4 uses `_check_path` unchanged); no file-type restriction (none added); links in `isError` and non-opted-in/non-stdio results untouched (T2, T5); no second job/shield beside `_export_call` (T5); no schema key, backend or `routes.py` change; links only from the result (T2); `errors="replace"` not used (T2).

### Task 1: AnyUrl normalisation characterization (L3)

**Files:** Create `tests/test_export_links.py` (class `TestAnyUrlNormalisation`).

Test-first: no. It characterizes the pinned SDK and adds no production code; its observed table fixes the strict list used by Task 2.

Build `mcp.types.ResourceLink(name="x", uri=...)` for each form: host, `localhost`, query, fragment, relative (`file:x`, `file:/x`), `%2f`, `%2e`, `%2e%2e`, `%00`, invalid UTF-8 (`%ff`), backslash, plain `file:///home/codemie/a%20b.csv`. Dump with `model_dump(mode="json", exclude_none=True)` and assert the observed `uri` string per case (parametrized table). Run once and keep the table for the MR text. Also assert a raw dict link keeps its exact string.

### Task 2: Pure link extraction and address decoding

**Files:** Modify `src/mcp_connect/client/export.py` (new `MAX_LINKS = int(os.getenv("MCP_CONNECT_EXPORT_MAX_LINKS", "50"))` beside `:50-54`; new function after `_check_path`). Extend `tests/test_export_links.py`.

Test-first: yes. Failing test: a parametrized table over `extract_links(content, is_error)` rows, e.g. `file:///home/codemie/a.csv` -> candidate; `file://host/...`, `file://localhost/...`, query, fragment, `file:x`, `%2f`, `%2e`, `%00`, `%ff` -> refusal text; `is_error=True` -> no candidates; non-link and non-`resource_link` items ignored; links past `MAX_LINKS` -> one summary refusal at the first excess index. Expected strings for SDK-normalised forms come from Task 1.

`extract_links(content: list[Any], is_error: bool) -> list[LinkCandidate]` where `LinkCandidate` is a frozen dataclass `(index, given, path | None, reason | None, size | None)`. Only items with `type == "resource_link"` and a str `uri`. Percent-decode once with `unquote(..., errors="strict")` after the strictness checks; `UnicodeDecodeError` becomes a refusal. `given` is the decoded path (note text names it, not `name`). Decoded paths still go through `_check_path` unchanged in Task 4.

### Task 3: Split the collect loop into a per-link step (refactor)

**Files:** Modify `src/mcp_connect/client/export.py:203-267`.

Test-first: no. Behaviour-preserving refactor; `tests/test_export_collect.py` and `test_export_apply.py` are the safety net and must pass unchanged.

Move the body of the loop after `_check_path` (open, fstat, limit ladder, read, item build) into `_read_one(out, state, given, p, name, size_hint=None, link=False) -> tuple[str, Any]` returning `("item", EmbeddedResource)`, `("note", text)`. `state` is a small per-call dataclass holding `total`, `seen`, `delivered: dict[real_path, name]`. Add one helper `_why(given, reason) -> str` (`f"{given}: {reason}"`) used by every refusal, explicit included. Reason texts for per-file limit stay in one place. Explicit-path behaviour (silent dedupe on `seen`/`skip_names`, refusal list) is unchanged.

### Task 4: Links through the same job, one outcome per link

**Files:** Modify `src/mcp_connect/client/export.py` (`Collected`, `collect_exports`, `_read_one`). Extend `tests/test_export_collect.py`.

Test-first: yes. Failing tests (monkeypatching `EXPORT_ROOT`, `MAX_*`, `_inflight` as the existing `root` fixture does):
- explicit file then link in one call: link uses the remaining `MAX_CALL_BYTES`/`MAX_FILES`; `_inflight` equals the sum of both afterwards (L6).
- link to the same real path as a delivered file -> outcome "dup", no item, no note; two links to one path -> one item (L6, L14).
- link whose basename equals a file delivered from another path, or a `skip_names` entry -> note; two `report.xlsx` in different folders -> first item, second note (L14).
- link to a path refused earlier as an explicit path gets its own note (not silent).
- declared `size` over `MAX_FILE_BYTES` -> note, file never opened (patch `os.open` to fail the test); `fstat` size over the limit, per-call, count and busy limits -> note, and the busy text for a link has no "retry later" (L5).
- outside root, `/tmp`, symlink, hidden, directory, FIFO (no block), missing file, read error -> one note each, rest intact (L2, L4, L7).
- `Collected.reserved` released when the job raises mid-way (existing behaviour kept).

Add `links: list[LinkCandidate] | None = None` to `collect_exports` and defaulted `Collected.outcomes: list[LinkOutcome]` (kind `item|note|dup`, item or text, per link `index`), `link_files: int`, `link_bytes: int`. After explicit paths, run each non-refused candidate (`path` already decoded) through `_check_path` then `_read_one(link=True)`; candidates already refused by Task 2 become `note` outcomes. The same `state` is used for both phases (one total, one count, one `delivered`).

### Task 5: Wire `apply` / `_export_call`: in-place replacement

**Files:** Modify `src/mcp_connect/client/export.py:303-353`. Extend `tests/test_export_apply.py`.

Test-first: yes. Failing tests (use real `CallToolResult` with SDK `ResourceLink`):
- link-only result, no `codemie_export_files`, opted-in stdio: the link item is replaced in place by the embedded `resource` (`file:///<name>`, mime, blob); other content byte-identical and in order (L1, L10-L11).
- result with no link and no request -> plain path, body byte-identical (existing tests stay green).
- `isError` result with a link and no request -> byte-identical; with a request -> only the "export skipped" note, link untouched (L8).
- non-opted-in / non-stdio with a link -> byte-identical (L9).
- links in arguments or text supply none (L11).
- more than `MAX_LINKS` links -> excess left unread, one summary note replaces them (L15); `Export:` log line (caplog) shows link-sourced count and bytes.
- cancel during a link-only read: `_inflight` returns to its prior value (mirror `test_budget_released_when_cancelled_during_collection`, `:188`); send failure also releases (L5, L13).
- explicit + link: explicit items and "Files not exported:" list append as today; replaced links sit in their positions.

Change the branch condition at `:313` to enter `_export_call` when `ctx.requested` is non-empty or `extract_links` finds a candidate. In `_export_call` call `collect_exports(..., links=...)` inside the existing shield and `_release_when_done` (no second job); rebuild `content` by replacing each link index with its item or `_text(note)` (a `dup` outcome drops it); use the `ExportJSONResponse` path when any file was embedded; plain `JSONResponse` when all outcomes are notes. `_existing_resource_names(content)` still feeds `skip_names`. A link-only result with a non-list or missing request skips the "expected a list" note.

### Task 6: Purpose-built stdio test server and end-to-end test (L12)

**Files:** Create `tests/fixtures/link_server.py` (FastMCP stdio server, SDK-typed `ResourceLink` results); Create `tests/test_export_links_e2e.py`.

Test-first: no. The task is the test itself, written against the finished wiring; it must fail if Task 5 is reverted.

The server exposes tools that write a file under a directory given by an env var and return `ResourceLink(uri=Path(...).as_uri(), name=...)` (existing file, missing file, outside-root file, two same-named files, a link plus text). Confirm the FastMCP/`ResourceLink` API with ctx7 before writing. The test patches `export.EXPORT_ROOT` to `tmp_path.resolve()`, posts to `/bridge` with the `async_client` fixture (`tests/conftest.py:30`), `serverPath=sys.executable`, args `[fixture path]`, `env` with `CODEMIE_EXPORT_FILES=true`, once with `single_usage: true` and once cached (L2, L12). Assert the response items, not the log.

### Task 7: README and architecture guide

**Files:** Modify `README.md:493-536` and `:555-562`; `.ai-run/guides/architecture/architecture.md:232-235`.

Test-first: no. Docs only.

Document: links resolve on opted-in stdio servers under the same `CODEMIE_EXPORT_FILES` switch, so servers already opted in gain link reading on deploy; the trust sentence "opt in only servers whose output you also trust to name files; a stdio proxy to a remote server does not meet this"; the server must return the link after the file is complete (a file still being written is delivered as is); `MAX_LINKS` and its env var in both env tables; refused/removed/note behaviour and the `/home/codemie`-only root. Reword `README.md:532` "A file is exported only when the model names it" to "named by the model or returned by the server as a link". `isError` links stay as is.

### Task 8: Amend the !314 spec text; MR-text checklist

**Files:** Modify `docs/superpowers/tasks/2026-11-03-epmcdme-14735-capture-generated-files/spec.md` (Intent, criteria 10 at `:102-105` and 11 at `:106`, Isolation/D6).

Test-first: no. Docs only.

- Intent / "exported only when the model names it" -> "named by the model or returned by the server as a link".
- Criterion 10 gains "except `resource_link` items resolved or refused by link delivery"; its absent/`null`/`[]` bullet becomes "returns exactly today's result unless it contains a `resource_link` item".
- Criterion 11 / Isolation: holds for model-named paths; on an opted-in server without reach into `/home/codemie` the server can name any non-hidden shared file by link, accepted same-uid residual.

MR text (carry to mr-creator; not a committed file): the L3 accepted/refused table from Task 1 naming each D4 form that ends "accepted as normalised"; a note to the ticket owner that AC #6 is only partly covered; the !314-head re-check result; servers already opted in gain link reading on deploy.
