# EPMCDME-14735: Explicit file export from stdio MCP tools

## Intent

When a stdio MCP server (shell, filesystem, ...) writes files during a `tools/call`, the user should get Download chips without the model reading the files back. The CodeMie backend already publishes embedded MCP resources (`{"type":"resource","resource":{"uri","mimeType","blob"}}`) as chat artifacts (backend spec `2026-09-14-epmcdme-14735-downloadable-mcp-artifacts/spec.md:25-35`). This serves ticket ACs #1, #3, #4, #5, #6 and #7. AC #6 holds on servers that already reach `/home/codemie` and were opted in by whoever writes the server's env: the catalog admin, or the assistant author for custom configs (see Isolation).

**Approach: the model names the files (or the server returns them as `resource_link` items), MCP-Connect delivers them.** Inferring generated files from shared file state did not converge, so nothing is inferred. On opted-in servers, MCP-Connect adds an optional `codemie_export_files` parameter to every tool. The model lists the files the user should receive. MCP-Connect reads them after the call and attaches them. This mirrors CodeMie's Code Executor: `export_files` (`codemie_tools/.../code_executor_tool.py:159-164`) and `_validate_export_paths` (`:674-686`).

This is not ticket AC #8, the dropped attach tool. The export is a parameter on the call that generates the files, not a separate tool or a second call.

Verified from the ticket's RADAR conversation: every `shell_execute` passes `"directory": "/home/codemie/<hex>"`, a folder that persists across turns, and writes files with relative names.

## Behavior

**Opt-in (AR-21).** Export applies only to stdio servers (`detect_transport_type`, `client/manager.py:93-118`) whose `env` sets `CODEMIE_EXPORT_FILES` to `true`, `1`, `yes` or `on`, in any case. The value may arrive as a string or as a JSON boolean. Export is off by default.
- The key is read once from a substituted copy of the request. It is always stripped before the cache key is computed and before the server is spawned.
- HTTP and SSE servers never get the parameter.
- The README documents setting the key on the shell server and on the Filesystem server over `/home/codemie`. It also states that opt-in only decides where the parameter appears and is not an access control.
- When export is off, `tools/list` and `tools/call` behave exactly as today, with one exception: `codemie_export_files` is still stripped from every stdio `tools/call`. The backend can cache a schema for up to 600 s, so an earlier opt-in could otherwise push the key to a server that no longer has export.

**`tools/list`.** For each tool, on every page, MCP-Connect adds an optional property to `inputSchema.properties`, creating `properties` if it is missing. The property is never added to `required`. Its description is built from the path constants:

```json
"codemie_export_files": {"type": "array", "items": {"type": "string"},
  "description": "When this call creates files the user asked for, write them under /home/codemie/codemie_export (for example /home/codemie/codemie_export/report.xlsx) and list the same paths here, so the user receives them as downloads. /home/codemie/codemie_export is the user's own folder: use it as it is in every argument, including directories and shell commands. Only files in that folder can be exported, including an existing file the user asks for. Relative paths resolve against this call's directory/cwd/working_directory argument, otherwise /home/codemie."}
```

The name is reserved and prefixed, so `tools/call` can strip it without keeping state. If a tool already defines this name, its schema entry is left alone, but the value is still stripped (see risks).

**`tools/call`.**
- **Strip.** `codemie_export_files` is removed from `arguments`, so the server never sees it.
- **Folder alias (amended 17 Nov, round-3 review and re-run).** On an opted-in call with a `user_id`, the path `/home/codemie/codemie_export` in any string of `arguments` (nested dicts and lists included) and of `codemie_export_files` is mapped to the caller's folder, and the folder is created before the tool runs. Only the whole path component is mapped (`/home/codemie/codemie_export_dir`, `/home/codemie/codemie_export2` stay as written), in every string, file contents included. Without opt-in or without a user the arguments are untouched.
- **Nothing requested (AR-24).** An absent value, `null` or an empty list means no export and no note. Any other value that is not a list of strings is refused with a note, and the call still runs.
- **Error results (AR-22).** When the result has `isError=true` and a non-empty export list was requested, the error content stays unchanged, nothing is exported, and one text item is added: "export skipped: the call failed". This is safe for the backend, because it reads `item.text` on every item of an error result (`toolkit.py:168`). An error result for a call that requested no export is left untouched.
- **Path checks.** Each path is resolved and checked:
  - A relative path resolves against the first absolute string argument named `directory`, `cwd` or `working_directory`. If there is none, it resolves against `/home/codemie`, the server process cwd (`Dockerfile:311`). Absolute paths are accepted.
  - The checks run on the resolved realpath, and that resolved path is what gets opened. The realpath must stay inside `/home/codemie`, and a hidden segment anywhere below `/home/codemie` is refused (protecting `.ssh`, `.npmrc` and similar).
  - The file is opened with `O_RDONLY|O_NOFOLLOW|O_NONBLOCK` and checked with `fstat`. Only regular files are accepted, so symlinks, FIFOs, devices, directories and missing files are refused without blocking (AR-25).
- **Appending.** Each accepted file is appended after the server's own content, which stays byte-identical (AC #7). The item carries:
  - the file as a base64 `blob`
  - `uri` = `file:///<file name>`
  - a `mimeType` from `mimetypes`, with explicit entries for xlsx, csv, json, zip and pdf (AC #5), and `application/octet-stream` for anything else

  A file whose name already appears as a `resource` in the server's result is not appended again.

**Limits.** All are configurable through env vars: 50 MB per file, 50 MB per call, 20 files per call, and a pod-wide in-flight budget, `MCP_CONNECT_EXPORT_MAX_INFLIGHT_BYTES`.
- The budget counts file bytes from `fstat`, and each read stops at that size.
- A reservation is released in a `finally` after the response is sent, because Starlette's background hook is skipped when a send fails.
- The default comes from measured memory: base64 plus JSON costs about 5× the file size, on a 1Gi pod.
- The budget is pod-wide only while the service runs one worker and one replica, which is today's deployment.

**Refusals are reported.** Every refused or over-limit file is listed with its reason in one appended `text` item. Nothing is dropped silently.

**Isolation (AC #6).**
- **Per-user root (amended 16 Nov, after review of !314).** The PO did not accept that two users writing the same path could receive each other's file (EPMCDME-14735, comment of 13 Nov). `prepare` sets the root to `/home/codemie/u-<first 16 hex of sha256(user_id)>`, using the `user_id` that `/bridge` already carries. That id is the person who made the call: since 17 Nov the backend sends `user_context.id` as `user_id` whenever it has one, so a global assistant or workflow no longer keys the folder on its creator (codemie !4252). The model learns the folder through the `/home/codemie/codemie_export` alias before it writes (see `tools/call`). Model-named paths and links outside it are refused, and the note names the folder, so the model writes the file there again and exports it. The folder is created when the alias is mapped or on the first export attempt. Relative paths still resolve against the `directory`/`cwd`/`working_directory` argument, else `/home/codemie` (the server's cwd): the folder only gates, so a bare name the server wrote in `/home/codemie` is refused instead of matching an older same-named file in the folder (found in the AC 3 re-run, 16 Nov). A call without `user_id` exports nothing (one note) and leaves links untouched. The `tools/list` description names no folder, because the backend caches it across users. The name is a plain hash, not a secret: it separates same-named files, while deliberate reading of another user's folder through a server with reach stays the accepted same-uid residual. Since 17 Nov the root is per conversation inside the user's folder (see Per-conversation root).
- **Per-conversation root (17 Nov, after the round-3 re-run).** `/bridge` accepts an optional `conversation_id`, and the root becomes `u-<user>/c-<first 16 hex of sha256(conversation_id)>`; a workflow run without a conversation uses `workflow_execution_id`, and a request with neither (an older backend) keeps the per-user root. In the re-run the model listed export paths before its script wrote them, and the shared per-user folder delivered a same-named report from an earlier conversation (3 of 5 shell runs). A per-call freshness check was tried and reverted: it also refused files a script wrote one call before the export (shell delivery 3/10).
- **Reach.** Export and links read only the caller's folder; a server that itself reaches `/home/codemie` can still read other users' folders (same uid, EPMCDME-16903).
- **Who opts in.** Whoever writes the server's env decides: the catalog admin for catalog servers, or the assistant author for custom configs.
- **Precondition: only the backend calls `/bridge`.** The folder is chosen by the request body's `user_id`; `ACCESS_TOKEN` is unset in the chart by default and, when set, is not tied to a user. A caller that can reach the Service could name any user's id. It could already run commands as the service user, so this is a precondition rather than a new exposure; the README states it (restrict the Service to the backend, or set `ACCESS_TOKEN`).
- **Shared processes.** The client cache key has no user, so one cached process serves several users. Export state is per call. `cli-mcp-server` keeps no working folder between calls (measured 17 Nov: `cd` in one call, `pwd` in the next returns `/home/codemie`).
- **Not an access control.** Opt-in adds no reach beyond the same-uid residual, because the same author can already run a Filesystem server over `/home/codemie`.
- **Links.** Link delivery uses the same root and budgets. On an opted-in server without reach into `/home/codemie`, the server can name any non-hidden shared file by link; this is the accepted same-uid residual.
- **Same uid.** Every server runs as uid 1001. EPMCDME-16903 owns per-user OS identity and server processes, with the process cache keyed by the initiator and each server's working folder created inside the user's folder at spawn (the export relative base moves with it, both in `utils/workspace.py`); the intermediate-symlink check; and whether the `CODEMIE_EXPORT_FILES` opt-in stays.

**Known behavior (README).**
- A file is exported only when it is named by the model or returned by the server as a link.
- A file from an earlier turn can be exported by naming it in a later call, or delivered through `read_media_file`.
- Exporting the same file in two calls produces two chips (`name (2).ext`).
- The README offers an assistant-instruction line: "When you create files for the user, write them under /home/codemie/codemie_export and list the same paths in codemie_export_files."
- Per-user folders are not cleaned up; they live on the `/home/codemie` volume until the pod restarts (README sizing note).

**Deploy note.** The parameter appears only after the backend's toolkit cache expires, which takes up to 600 s. The backend reads only the first `tools/list` page, but injection still applies to every page.

## Contract

The `/bridge` request gains one optional field, `conversation_id` (17 Nov), which scopes the export folder. Deploy order: MCP-Connect first, because an older one rejects the unknown field with 400 (`extra="forbid"`), then the backend that sends it. `request_uuid` is still not sent. The response shape does not change either: the new items sit inside the existing `CallToolResult` and `tools/list` results.

## Backend follow-up (separate MR in `~/codemie-dev/codemie`)

Docs only. Update the backend spec's "Follow-up" section (`:152-155`) to say MCP-Connect uses explicit export and needs no new bridge fields, and correct its "422" to "400".

## Constraints for the plan

- **One export module.** `bridge_endpoint` (`server/routes.py:303`) calls a single export module twice: once to prepare (inject or strip) and once to apply. `invoke_mcp_method` keeps its signature, so the test fakes at `tests/test_single_usage.py:809,906` keep working.
- **Prepare.** Prepare substitutes only to decide the transport and to read the switch. It hands the handlers the original request with the switch and the parameter stripped, which avoids running substitution twice. A test checks that a value containing `$` reaches the server unchanged.
- **Budget release.** The export module owns the response class whose send releases the budget in a `finally`.
- **Off the event loop.** All file access sits in one function. It and the encoding and rendering of a response that carries exports run off the event loop. If the rendering stays on the loop, the measured lag for one 50 MB export is recorded as accepted.
- **Shared constants.** One constant holds the export root `/home/codemie` and another holds the working-folder argument names. The model-facing description is built from both.

## Acceptance criteria

1. On an opted-in stdio server, `tools/list` adds the optional `codemie_export_files` array to every tool on every page. It is not required.
2. `tools/call` strips `codemie_export_files` on every stdio call, opted in or not. The server receives exactly the other arguments.
3. Real model, assistant instructions unchanged, Filesystem server allowed `/home/codemie` and opted in: the brief's prompt ("write closed_positions_analysis.csv/.json/.xlsx and give me the files") shows the chips in the same turn without `read_media_file`. Run it 5 times, record the rate, and pass at 4 of 5. Below 4 of 5, add the README instruction line and rerun. It then passes at 4 of 5 with the line, and the MR records both rates.
4. Real model, no assistant change, shell server opted in: the RADAR prompt returns xlsx/csv/json chips through `shell_execute` with `directory=/home/codemie/<hex>` and relative export names. Run it 5 times, record the rate, and pass at 4 of 5. Below 4 of 5, add the README instruction line and rerun. It then passes at 4 of 5 with the line, and the MR records both rates.
5. xlsx, csv, json, zip and pdf get their correct mimeTypes.
6. Each of the following is refused and listed in the text item:
   - outside `/home/codemie`
   - `../` traversal
   - a symlink, including one inside `/home/codemie` that points outside
   - a non-hidden linked folder pointing into a hidden one
   - a FIFO, without blocking the request
   - a directory
   - a missing file
   - a hidden path
7. Files over the per-file, per-call, count or budget limit are listed in the text item. The budget reservation is released even when the send fails.
8. Without `CODEMIE_EXPORT_FILES` set to a true value, there is no injection and no export. The key never reaches the child env.
9. For HTTP and SSE servers, `tools/list` and `tools/call` results are byte-identical to today.
10. The server's own content, images included, is byte-identical, except `resource_link` items resolved or refused by link delivery.
    - A call with an absent, `null` or `[]` value returns exactly today's result unless it contains a `resource_link` item.
    - An `isError` result for a call that requested a non-empty export keeps its content and gains only the "export skipped" text item.
    - An error result for a call that requested no export is byte-identical to today, including one produced by MCP-Connect's own protocol-error mapping.
11. Export and link delivery read only inside the folder of the person who made the call and of this conversation (`/home/codemie/u-<hash of the initiator's id>/c-<hash of conversation_id>`), never the credential owner's or another conversation's. Given one user's two conversations that each write `closed_positions_analysis.xlsx`, each conversation exports its own file. A path or link into another user's folder or elsewhere under `/home/codemie` is refused with a note naming the caller's folder. A call without `user_id` exports nothing. Given a global workflow created by user A and run by user B, B's run exports only from B's folder (backend sends B's id, codemie !4252).
12. With a real model, when the user asks in a later turn for a file created earlier, the file is delivered as a chip, either through `codemie_export_files` or through `read_media_file`.
13. On an opted-in call with a user, the path `/home/codemie/codemie_export` (whole component only) in the arguments and in `codemie_export_files` becomes the caller's folder, which exists before the tool runs; without opt-in or a user the arguments reach the server unchanged.

## Non-goals

- A separate attach tool or second call (ticket AC #8, dropped).
- Inferring generated files (snapshots, directory diffs, path scanning).
- Follow-up, not here: EPMCDME-16903 owns per-user OS identity and server processes, with the process cache keyed by the initiator and each server's working folder created inside the user's folder at spawn (the export relative base moves with it, both in `utils/workspace.py`); the intermediate-symlink check; and whether the `CODEMIE_EXPORT_FILES` opt-in stays. Per-user folders are in scope since 16 Nov.
- `request_uuid` on `/bridge`.
- Export for HTTP or SSE servers, or from outside `/home/codemie`.
- Cloud-storage artifact retention, and the byte size in the chip (AC #2).
- Changes to the `/bridge` response schema, or request fields beyond the optional `conversation_id`.

## Decisions

- Explicit export through a tool parameter, modeled on Code Executor, over inferring files from file state — user
- Export opt-in per server with `CODEMIE_EXPORT_FILES=true`, over on by default — user, answers AR-21
- One switch key, `CODEMIE_EXPORT_FILES`, replacing `CODEMIE_CAPTURE_FILES` with no alias (never shipped)
- On `isError`, skip export and add one text note, over exporting from failed calls — user, answers AR-22
- Accept the model-compliance risk, mitigated by a directive description, a README instruction hint and end-to-end real-model criteria — user, answers AR-23
- Drop `conversation_id`/`request_uuid` (brief requirement 5); the backend follow-up is docs only — user
- Per-user export root from the existing `user_id`, over a per-conversation root that needs a new `/bridge` field — user, after the PO rejected the same-path collision (16 Nov); superseded 17 Nov by the next line
- Per-conversation root from a new optional `conversation_id` on `/bridge`, over a per-call freshness check (tried, reverted) and over leaving the same-user collision to EPMCDME-16903 — user, after the round-3 re-run (17 Nov)
- The folder is keyed on the initiator: the backend sends `user_context.id` as `user_id`, over documenting the credential owner as the key — user, round-3 review (17 Nov)
- A fixed path alias, `/home/codemie/codemie_export`, mapped by MCP-Connect in the arguments, over the refusal note as the only way the model learns its folder — user, round-3 review (17 Nov). This differs from the superseded "no injected hint" decision because the hint is fixed and user-neutral: the cached description stays the same for everyone, and the hash rule stays in MCP-Connect.
- The alias is a path, over a `{codemie_export_dir}` placeholder — user, after the 17 Nov re-run: gpt-4.1 never passed the placeholder in shell work (0/15 first writes) and turned it into a real folder of its own (`/home/codemie/codemie_export_dir/...`), so the mapping never applied.
- `SERVER_CWD` and `user_root` in `utils/workspace.py`, with `SERVER_CWD` passed as `cwd` at the three stdio spawn sites when it exists (inherit otherwise, as in local runs), over the image `WORKDIR` alone — user, round-3 review (17 Nov)
- Folder created with default permissions; `0700` is dropped, since it has no effect while every server runs as one uid — round-3 review (17 Nov)
- Plain `sha256(user_id)[:16]` folder name, over an HMAC with a pod secret: every server runs as one uid and can list the root, so a secret name adds nothing — user (16 Nov)
- Refusal note names the user's folder and the folder is created on the first attempt, over naming it in the cached `tools/list` description — 16 Nov
- Relative paths keep `/home/codemie` as their base and the user's folder only gates, over resolving them in the folder, which delivered a stale file in the AC 3 re-run — 16 Nov
- The residual same-uid exposure is accepted and stated, with OS-level isolation as a follow-up — user, answers AR-1
- Accept duplicate chips across calls, deduping within one call only — user, answers AR-4
- Retarget the smoke-test Filesystem server to `/home/codemie`, over adding `/tmp` to capture scope — user, answers AR-12
- Absent, `null` or `[]` means no export and no note, over refusing `null` — answers AR-24
- `O_NONBLOCK` open with regular files only, over a blocking open — answers AR-25
- Add the "export skipped" note only when a non-empty export was requested, over adding it to every error result — answers AR-26
- Below 4 of 5, rerun with the README instruction line and record both rates, over leaving the outcome undefined — answers AR-27
- Containment and hidden-segment checks run on the resolved path, which is the path opened, over checking the path as given — answers AR-28
- Strip `codemie_export_files` on every stdio call whatever the switch, over stripping only on opted-in servers
- Description also covers existing files the user asks for, over created files only
- End-to-end criteria pass at 4 of 5 runs, over a single run
- Reserved name `codemie_export_files`, always stripped, over `export_files` with per-tool collision tracking
- A tool that already defines the reserved name keeps its schema entry but loses the value, over a fallback name
- Relative paths resolve against `directory`/`cwd`/`working_directory`, else `/home/codemie`, over absolute-only paths
- Absolute paths allowed inside `/home/codemie`, over Code Executor's relative-only rule
- Refuse hidden path segments, over an extension skip list
- In-flight budget counted from `fstat` bytes, released in `finally`, default measured, over an unmeasured 100 MB
- 50 MB per file and per call, plus 20 files, over 100 MB limits
- `uri` uses the file name, over the absolute host path
- `mimetypes` plus explicit entries for the AC #5 types, over relying on the container's mime tables
- One export module (prepare/apply) hooked in `bridge_endpoint`, over hooking into `invoke_mcp_method`

### Superseded (kept as recorded)

- Export on by default for stdio, with `CODEMIE_CAPTURE_FILES=false` to opt out, over opt-in per server — user
- One cached process per user and conversation, reused for the 5-minute TTL, over a fresh process per call — user
- Relative paths plus an optional line in the assistant instructions, documented in the README, over a hint injected by MCP-Connect or the backend — user
- Capture on by default for stdio once `conversation_id` arrives, with `CODEMIE_CAPTURE_FILES=false` to opt out, over opt-in per server — user, answers AR-6
- Delete folders idle for 1 h (configurable) in the existing cleanup loop over deleting files right after capture — user
- Skip `.py`/`.sh`/`.js` by default through a configurable list over capturing scripts — user
- Unguessable HMAC folder names with a per-process secret over `sha256(user_id)` folders — user, answers AR-1
- Folder mode `0700` and a root that cannot be listed over default permissions — user, answers AR-1
- Output root `/home/codemie/.mcp-connect-outputs` over `/tmp` — user
- Named-path capture returns only files created during the call, over created-or-changed — user, answers AR-11
- Named-path candidates taken from the call's arguments only, over arguments plus result text — user, answers AR-13
- Before/after snapshot of named paths, capturing only files that did not exist before, over an mtime test — user, answers AR-13
- Exclude directories named by another user and conversation, over requiring this conversation to have created the directory — user, answers AR-14
- Verify `search_files` next to the `0311` root and fall back to `0711` if it breaks — user
- Named-path capture under `/home/codemie` for paths in the arguments or result that changed during the call, over relying on assistant or skill changes — user, answers AR-3
- Named files always eligible, over dropping result-text candidates — user, answers AR-8
- Named directories contribute files only when this conversation created them, over any named directory — user, answers AR-8

## Assumptions and risks

- **Model compliance (AR-23, accepted).** If the model does not fill the parameter, no chip appears, which is the ticket's original symptom. Below 4 of 5 runs, AC 3 and AC 4 add the README instruction line and rerun.
- **Opt-in on a server without file reach.** The assistant gets read access to `/home/codemie` by name. This is documented. Opt-in is not an access control.
- **Same uid.** Every server runs as uid 1001. OS isolation is EPMCDME-16903.
- **A model that ignores the alias.** It writes outside the user's folder (RADAR's `directory=/home/codemie/<hex>`), gets a refusal note naming the folder, and has to write the file there again; this can happen in every conversation, not once after deploy. AC 3 and AC 4 are re-run under EPMCDME-17167 with the alias, counting a refusal plus its retry as one run, and record what the model does after a refusal (rewrite or copy) and zero cross-user deliveries. The merge waits on that re-run.
- **Reserved name.** A server parameter named `codemie_export_files` is lost on every stdio server.
- **RADAR errors.** Unverified whether RADAR's `shell_execute` returns `isError` on a non-zero exit. If it does, those calls skip export.
- **Unmeasured.** Peak memory for a 50 MB export and backend acceptance of a ~67 MB response.
- **Enterprise path.** It strips resources until EPMCDME-16353.
