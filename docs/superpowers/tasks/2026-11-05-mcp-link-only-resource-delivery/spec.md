# EPMCDME-14735: Deliver link-only MCP files (delta on explicit export, MR !314)

Delta on `docs/superpowers/tasks/2026-11-03-epmcdme-14735-capture-generated-files/spec.md` (the "!314 spec"). Story: `story.md` here (Approved, D1-D15). The !314 spec stands unless amended below.

## Intent

A stdio tool result may carry a `resource_link` instead of the file; the backend shows "not delivered" (`toolkit.py:400-404`). On an opted-in stdio server, MCP-Connect reads the linked file with the !314 reading code and puts it in the result as an ordinary embedded `resource`, so backend and UI need no change.

## Behavior

- **Where.** `export.apply` on the finished `tools/call` result, for `ctx.stdio and ctx.enabled`; no `routes.py` change, no session needed. The scan runs on every opted-in stdio call, with or without `codemie_export_files`. A result with no link and no export request takes today's plain path.
- **Items.** Only `type == "resource_link"` dumped items of that result. `isError` results: links stay as is, no note (a requested export still gets today's "export skipped").
- **Address.** Strict `file:///<absolute path>`. Refused with a note: host (incl. `localhost`), query, fragment, relative form, encoded slash/dot/NUL, invalid UTF-8. Otherwise percent-decoded once (strict UTF-8), then `_check_path` unchanged. Strictness applies to the string `apply` sees; where `AnyUrl` already normalised a form, the normalised path is checked (it still passes every guard). Extraction and decoding (and the `isError` rule) are one pure, table-driven function.
- **Reading.** Same `_check_path`, `O_NOFOLLOW`/`O_NONBLOCK` open, `fstat` regular-file check, limits and pod-wide budget as export, off the event loop, released after send. A declared `size` over the per-file limit is refused before opening, in the per-link step; `fstat` is authoritative. No file-type restriction. Root is the calling user's folder under `/home/codemie` (amended 16 Nov); the reason names it.
- **Seam (AR-1).** Split the `_collect_into` loop body (`export.py:203-267`) into a per-link step over a small per-call state (byte total, count, delivered real paths, reservation). One new entry point takes explicit paths, then link candidates, as a single job and returns the aggregate plus one outcome per link (item, note, already delivered). `collect_exports` keeps its signature, so its tests and the `slow_collect` fake stay. `apply` enters the export function when a request or a link is present (condition at `:313`) and runs that one job under the existing shield and release (`:328-335`): no second job, no branch beside it.
- **One budget.** Explicit files first, then links in content order: one byte total, one count, one pod-wide reservation.
- **Outcome per link, in place.** Success: the link becomes the embedded file item. Refused, over limit, not found, read failure: one text item `"<path as given>: <reason>"`. Removed with no note only when its real path was already delivered in this call. Identity is the real path. A different file with the same basename is delivered too (the backend names the second `name (2).ext`; amended after review of !314). A link to a file the server already returned as an embedded `resource` (matched by full path when its URI carries one, else by bare name) becomes a note. An empty file becomes a note, "file is empty". One helper builds every `"path: reason"` text, explicit refusals included. Links past `MAX_LINKS` (constant, 50) are not read; one summary note replaces them. Other server content is untouched; explicit items and the refusal list append as today; the budget-releasing response class is used when any file was embedded. The `Export:` log line gains link-sourced count and bytes.
- **Docs.** README export section and `architecture.md`: links resolve on opted-in servers under the same switch, so servers already opted in gain link reading on deploy; "opt in only servers whose output you also trust to name files", and a stdio proxy to a remote server does not meet that; the server must return the link after the file is complete (a file still being written is delivered as is).

## Amendments to the !314 spec (D15, D6) - carry into plan and MR text

- Intent / README "exported only when the model names it" becomes "named by the model or returned by the server as a link".
- Criterion 10 gains "except `resource_link` items resolved or refused by link delivery"; other content, images included, stays byte-identical. Its absent/`null`/`[]` sub-bullet becomes "returns exactly today's result unless it contains a `resource_link` item".
- Criterion 11 / Isolation (D6): ~~holds for model-named paths; links accepted as same-uid residual, no per-user enforcement~~ Superseded 16 Nov: links use the same per-user root as model-named paths (see the !314 spec, Isolation), so a link into another user's folder becomes a note.
- Criteria 1-9, 12 and the "Inferring generated files" non-goal stand: a link is a structured item, not scanned text.

## Acceptance criteria

L1. Opted-in stdio server, link to an allowed xlsx, csv, json, zip, pdf: the link becomes an embedded `resource` with `uri file:///<name>`, correct `mimeType`, base64 `blob`.
L2. Single-use and cached/expired-process paths deliver an existing file; a removed file gives a "not found" note in place.
L3. Links built with the SDK `ResourceLink`. For each form (host, `localhost`, query, fragment, relative, `%2f`, `%2e`, `%00`, invalid UTF-8) the test asserts the observed normalised string and outcome. After one run the accepted/refused table goes into the MR text, naming each D4 form that ends "accepted as normalised"; a raw dict carries the exact string and every form is refused.
L4. A link outside `/home/codemie` (`/tmp` too; note names the root), through a symlink, to a hidden path, or to a non-regular file (directory, FIFO, without blocking) is not read and becomes one note.
L5. Declared size over the per-file limit: refused without opening. An opened file over it, or over the per-call, count or pod-wide limit: note, no "retry later". Budget released even when send fails.
L6. Explicit export plus links: explicit first, links use the rest; a link to the same real path as a delivered file is removed with no note.
L7. A read failure leaves the rest intact; the link becomes a note naming file and reason.
L8. An `isError` result with a link is byte-identical to today.
L9. Non-opted-in or non-stdio servers: result with a link byte-identical to today.
L10. Results with no link, including explicit-export calls returning none, are byte-identical to today.
L11. Links are read only from the tool result; arguments and other text supply none.
L12. A purpose-built stdio test server returning SDK-typed links runs end-to-end against `/bridge` (D8).
L13. Cancelling during a link read releases the whole reservation (pod-wide in-flight returns to its prior value); a link-only result enters the same shielded job.
L14. Two links named `report.xlsx` in different folders: both delivered; a link to a path the server already returned as an embedded `resource`: a note; two links to one real path: one item, no note.
L15. More than `MAX_LINKS` links: excess unread, one summary note; the `Export:` log line shows link-sourced count and bytes.

## Non-goals

- Plugin MCP tools (EPMCDME-16353) and the Radar proxy.
- A `resource` with only an address (SDK rejects it first).
- HTTP/SSE servers; files outside `/home/codemie` (`/tmp` is no second root).
- Reading through the MCP server (`resources/read`).
- Content checks on delivered files.
- Per-conversation enforcement; OS-level isolation (per-user root added 16 Nov, !314 spec).
- File size in the chip; an attach tool; artifact retention.
- A separate switch for links; a link-only cap beyond `MAX_LINKS`.
- Backend, UI, or `/bridge` schema changes.
- Inferring files from text.

## Decisions

- Link items resolved in `export.apply` on the finished result, over `resources/read` in-session — user, D2
- One shared switch, `CODEMIE_EXPORT_FILES`, for export and links — user, D5
- Servers already opted in gain link reading on deploy, over a separate value — user, answers AR-3
- README says a stdio proxy to a remote server does not meet "output you also trust to name files" — user, answers AR-3
- Strict `file:///<abs path>`, decoded once, over accepting `file://localhost` or encoded separators — user, D4
- L3 asserts the observed form per case and the table goes to the MR, over only dumping forms — user, answers AR-4
- Replace the link in place by the file or one note, over appending only — user, D15
- Per-link step with one single-job entry point, over a workaround in `apply` — user, answers AR-1
- Silent removal only for the same real path, a note otherwise — user, answers AR-1
- ~~A second link with an equal basename is refused with a note~~ Superseded after review of !314: dedupe by real path only, since the backend keeps both files as `name (2).ext` and a basename check dropped a different file
- Files under `/home/codemie` only, `/tmp` no second root, the note names the root — user, answers AR-2
- Links in `isError` results left as is, over a note — D12
- Declared size over the limit refused before open; `fstat` authoritative — D11
- Explicit files take budget first, then links — D5
- Residual same-uid exposure and server-named paths accepted, with the README trust sentence — user, D6
- No file-type restriction on links — D14
- Link reads run after the timeout window, as export does — D13
- Strict UTF-8 decoding, over `errors="replace"` — my call
- A link note names the decoded path as given, over the link's `name` — my call
- Scan on every opted-in stdio call, over only calls with `codemie_export_files` — my call, required by L1-L2
- `MAX_LINKS` 50 with one summary note, over uncapped notes — my call
- One pure table-driven extraction/decoding function, over inline checks — my call

## Risks

- `AnyUrl` normalisation unverified (analysis §2): the L3 run fixes the strict list.
- Links share the pod budget with no own cap; revisit if the new log counts show starvation.
- Memory: the existing ~5x budget; two concurrent 50 MiB reads unmeasured.
- Backend behaviour for two embedded files sharing `file:///<name>` unverified; links avoid it, explicit export does not.
- Symlink/TOCTOU on intermediate directories: same as export.
