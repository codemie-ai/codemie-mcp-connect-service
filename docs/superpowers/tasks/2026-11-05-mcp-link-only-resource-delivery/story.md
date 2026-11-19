---
schema_version: 1
id: mcp-link-only-resource-delivery
mode: single
repository: codemie-mcp-connect-service
---
# Deliver link-only MCP files as downloadable chat artifacts, resolved in MCP-Connect — Story

**Date**: 2026-11-04
**Status**: Approved
**Architecture review**: intent, 2026-11-05, 3cf748c64e33
**Ticket**: EPMCDME-14735 (AC #1, "exposes or returns"; extends MCP-Connect MR !314; follow-up to MR !4252)

---

## Context

- MR !4252 already publishes files that an MCP server returns embedded in its tool result (with the file bytes) into the conversation workspace, and the chat shows them as a download chip. The backend and the UI need no change for that.
- A tool result that only points to a file (a resource link) is not delivered today. The user sees "`<name>` stays on the MCP server and was not delivered", as plain text with no fake link.
- MCP-Connect, the bridge between the platform and MCP servers, runs local (stdio) MCP servers in the same container, so a file such as `/home/codemie/<folder>/report.xlsx` that a link points to is on MCP-Connect's own disk.
- MR !314 (not merged yet) adds explicit file export to MCP-Connect: an opt-in per server, safe file reading (no symlinks, no hidden folders, regular files only, folder containment), size limits, and a list of refusals. This story reuses that file reading, path checking and limits, and adds link detection, address decoding, per-link outcomes, in-place replacement and a shared per-call budget. It is delivered inside that MR (D9).
- Assistants using plugin MCP tools, and the Radar proxy, are separate paths this story does not touch.

---

## Complexity

**Size**: M (16/36) · **Recommended flow**: sdlc-standard

One repository and one module, reusing the explicit-export reading, limits and budget code; technical risk is the largest dimension because link paths come from server output and the address normalisation is unverified.

---

## Story

**As an** assistant user, **I want** a file that an MCP tool only points to (rather than embeds) to arrive as a working download in the chat **so that** I get the generated report whichever way the MCP server hands it over.

---

## Background

Ticket EPMCDME-14735 promises that a generated non-image file "exposed or returned" by an MCP tool becomes a user-facing download. Today that holds for embedded files and, with MR !314, for files the model names in an explicit export. For servers that return a link to the file, the user gets a "not delivered" message. MCP-Connect can treat such a link like one more exported file and read it itself with the same safe reading code; the platform backend then receives an ordinary embedded file and delivers it as it already does. A link is a structured item of the tool result, not text scanned for paths, so the earlier decision not to infer files from text is not reopened.

---

## Acceptance Criteria

- [ ] Given a local MCP server is opted in to file export, and a tool result contains a link to a file inside the allowed folder (any file type; the ticket requires at least xlsx, csv, json, zip and pdf), when the tool call completes, then MCP-Connect reads the file itself and the link item is replaced by the file embedded in the result, with its name and type, and the chat shows the same working download chip as for any embedded file.
- [ ] Given the server starts a fresh process per call (single-use), or its cached process has expired, when the call completes and the file is still on disk, then the file is delivered; if the server removed the file, the link item is replaced by a note that the file was not found.
- [ ] Given a link in a tool result is not a strict `file:///<absolute path>` address (refused forms are those still visible after the MCP library has parsed the result: a host, a query, a fragment, a relative form, encoded slashes or dots; the exact list is fixed by the address-normalisation check in Constraints), when the call completes, then it is not read; the link item is replaced by one note stating why.
- [ ] Given a link points outside the allowed folder, through a symbolic link, to a hidden path, or to something that is not a regular file, when the call completes, then it is not read, without blocking the call; the link item is replaced by one note stating why.
- [ ] Given a link declares a file size over the per-file limit, or the opened file turns out over it, or the files in one call exceed the per-call, file-count or pod-wide limits, when the call completes, then the excess files are not delivered and a note states why.
- [ ] Given one call both names files for explicit export and returns links, when the call completes, then the exported files are delivered first and links use the remaining per-call budget; a file named both ways is delivered once.
- [ ] Given reading a linked file fails, when the call completes, then the tool's own result is still returned in full, the link item is replaced by a note naming the file and the reason, and no link is shown.
- [ ] Given a tool result with `isError` set contains a link, when the call completes, then the link is left as is.
- [ ] Given an MCP server is not opted in, or is not a local (stdio) server, when a tool result contains a link, then the result is unchanged from today (the platform shows "not delivered").
- [ ] Given a tool result with embedded files, images or text and no links, or a call using explicit export that returns no link, when the call completes, then the result is unchanged from today, and the platform backend receives the same result shape it already handles.
- [ ] Given the model or the user separately supplies another address, when the call completes, then only links in the tool result are read.

---

## Out of Scope

- Plugin MCP tools (the enterprise package fix, EPMCDME-16353). No current production path is known to return links through MCP-Connect (D8): the Radar proxy, the only known link source, has no owner for a resolver of its own.
- The Radar proxy (`mcp-proxy`) handling of resource reads.
- A result item that is an embedded resource with only an address and no file content: the MCP library in MCP-Connect rejects this shape before MCP-Connect can act on it.
- Remote (HTTP/SSE) MCP servers and files outside the container's allowed folder: explicit export has the same restriction.
- Reading linked files through the MCP server (`resources/read`).
- Content checks on the delivered file beyond what the platform already does.
- Per-user or per-conversation enforcement for these files, and OS-level isolation between users (D6): the same accepted limits as explicit export, plus the narrower fact for opted-in servers without reach. The ticket owner should be told ticket AC #6 is partly covered and why.
- Showing file size in the chip (dropped from AC #2) and the explicit attach tool (dropped from AC #8).
- Retention of stored artifacts.
- Changes to the platform backend and the chat UI.

---

## Decisions

- D1: Scope of "AC #1 fully": core MCP path only → plugin and Radar stay separate tickets — user
- D2: How is a link delivered? → MCP-Connect reads the linked file itself from its own disk with the explicit-export reading code and puts it in the result as an embedded file; it does not ask the MCP server to read it — user (accepted the proposal after comparing with the !314 spec)
- D3: Which link shapes? → resource links only; a resource that has only an address stays out of scope — user
- D4: Which addresses? → only strict `file:///<absolute path>` (no host, query, fragment, encoded slashes or dots), decoded once and then checked like an export path; `file://localhost/...` is not accepted; only links in that call's result — user
- D5: Opt-in, folder checks and limits → the explicit-export switch, path checks and limits of MR !314, one shared budget per call with explicit-export files first; every server already opted in for export also gets its links resolved, stated in the README requirement together with "opt in only servers whose output you also trust to name files" — user (one shared switch) and proposed by PO (budget order)
- D6 *(superseded 16 Nov: links use the per-user root of the !314 spec; 17 Nov: keyed on the initiator. EPMCDME-16903 owns per-user OS identity and server processes, with MCP-Connect's process cache keyed by the initiator and each server's working folder created inside the user's folder at spawn; the intermediate-symlink check; and whether the `CODEMIE_EXPORT_FILES` opt-in stays.)*: Per-user isolation (ticket AC #6) → the same accepted limits as explicit export (AR-1 of that run): every server runs as the same OS user and the allowed folder is shared, and there is no per-user folder enforcement. On servers that already reach `/home/codemie`, a link exposes nothing new. On an opted-in server that does not (a fetch-style or subfolder-confined one), the server, not the model, can name any non-hidden shared file, and a link built from third-party content can bring another user's file into this user's chat; accepted, with the README requirement "opt in only servers whose output you also trust to name files", and the ticket owner is told this narrower fact — user
- D7: Failure behaviour → the tool's own result is never lost; a refused or failed link is replaced by one note — proposed by PO
- D8: No production server returns link-only results today → the change is planned to be verified against a purpose-built test MCP server — user
- D9: How is this delivered? → added to MCP-Connect MR !314 (explicit export, branch `EPMCDME-14735_capture-generated-files`), not as a separate change; !314's review scope grows accordingly — user
- D10: Remote-transport servers → out of scope, same as export — proposed by PO
- D11: Size → the size of the opened file is authoritative; a declared size over the per-file limit is refused before opening — proposed by PO
- D12: Links in an error result → left as is, matching export's "skip on error"; the backend's handling of an item without text in an error result is existing behaviour and accepted — proposed by PO
- D15: Replace or keep the link item? → on opted-in local servers the link item is replaced by the file on success and by one note when refused or failed; !314 is amended accordingly: its criterion 10 reads "except links resolved or refused by this feature", its sub-bullet for an absent or empty export value is adjusted, and its intent and README sentence "a file is exported only when the model names it" reads "named by the model or returned by the server as a link" — user (option a)
- D14: No file-type restriction on links → any file type is read like an export path; the ticket requires "at least" xlsx, csv, json, zip and pdf — proposed by PO: architecture review (AR-4); ticket AC #5
- D13: Time → link reads happen after the call's timeout window, as explicit export does — proposed by PO

---

## Open Questions

- None

---

## Sources

- https://jiraeu.epam.com/browse/EPMCDME-14735 · ticket (fetched 2026-11-04)
- https://gitbud.epam.com/epm-cdme/codemie/-/merge_requests/4252#note_2493180 · MR comment (fetched 2026-11-04)
- docs/stories/2026-11-04-mcp-link-only-resource-delivery/technical-analysis.md · analysis (MCP-Connect)
- codemie-mcp-connect-service/docs/superpowers/tasks/2026-11-03-epmcdme-14735-capture-generated-files/ · MR !314 spec, decisions and architecture review (documents)
- docs/stories/2026-11-04-mcp-link-only-resource-delivery/v1-backend-approach/ and v2-read-resource-in-session/ · earlier approaches, analyses and estimates

---

## Constraints

- Amendments to MR !314's own text (D15): spec criterion 10 and its absent/empty-value sub-bullet, the spec Intent, and the README sentence at the "A file is exported only when the model names it" line.
- Landing: inside MR !314 (D9), so there is no separate landing order. Re-check the export switch handling and the shape of results against !314's current head before planning.
- No platform backend or UI change; the backend must keep receiving the same result shape.
- Precondition for the address criterion: dump how the MCP library normalises each refused address form (strictness can only be enforced on the normalised form for results it has parsed), and have the test MCP server return links through the library's own type, not raw data.
- No `AGENTS.md`/`CLAUDE.md` at the workspace root: owner approvals and landing rules not found.
