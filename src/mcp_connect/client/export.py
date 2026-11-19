# Copyright 2026 EPAM Systems, Inc. ("EPAM")
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Explicit file export from opted-in stdio MCP servers (EPMCDME-14735).

On servers whose ``env`` sets ``CODEMIE_EXPORT_FILES`` to a true value, every tool
gets an optional ``codemie_export_files`` parameter. The model lists the files the
user should receive and, after ``tools/call``, they are appended to the result as
embedded ``resource`` items. ``bridge_endpoint`` calls :func:`prepare` before the
handler and :func:`apply` after it.
"""

from __future__ import annotations

import asyncio
import base64
import mimetypes
import os
import re
import stat
import threading
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, unquote

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from mcp.types import BlobResourceContents, EmbeddedResource
from starlette.responses import Response
from starlette.types import Receive, Scope, Send

from ..models import BridgeRequestBody
from ..utils import workspace
from ..utils.logger import get_logger
from ..utils.substitution import apply_substitutions
from .manager import detect_transport_type

logger = get_logger(__name__)

# EPMCDME-14735: limits are read once at import; tests monkeypatch the module attributes.
MAX_FILE_BYTES = int(os.getenv("MCP_CONNECT_EXPORT_MAX_FILE_BYTES", str(50 * 1024 * 1024)))
MAX_CALL_BYTES = int(os.getenv("MCP_CONNECT_EXPORT_MAX_CALL_BYTES", str(50 * 1024 * 1024)))
MAX_FILES = int(os.getenv("MCP_CONNECT_EXPORT_MAX_FILES", "20"))
MAX_LINKS = int(os.getenv("MCP_CONNECT_EXPORT_MAX_LINKS", "50"))
# Base64 plus JSON costs about 5x the file size: 50 MiB of files is about 250 MiB on a 1Gi pod that also
# holds the warm stdio servers. Raise it only after measuring peak RSS with a typical number of servers.
MAX_INFLIGHT_BYTES = int(os.getenv("MCP_CONNECT_EXPORT_MAX_INFLIGHT_BYTES", str(50 * 1024 * 1024)))

ALIAS_NAME = "codemie_export"  # SERVER_CWD/ALIAS_NAME stands for the caller's folder in the arguments (prepare)


def alias() -> str:
    """The path the model writes to; a path, not a placeholder, because models resolve placeholders themselves."""
    return f"{workspace.SERVER_CWD}/{ALIAS_NAME}"


WORKDIR_ARG_NAMES = ("directory", "cwd", "working_directory")
EXPORT_PARAM = "codemie_export_files"
SWITCH_KEY = "CODEMIE_EXPORT_FILES"

_TRUE_VALUES = {"true", "1", "yes", "on"}

_MIME_OVERRIDES = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
    ".json": "application/json",
    ".zip": "application/zip",
    ".pdf": "application/pdf",
}
_SKIPPED_NOTE = "export skipped: the call failed"


def _param_schema() -> dict[str, Any]:
    # The backend caches tools/list across users, so this text must not name a user's folder.
    return {
        "type": "array",
        "items": {"type": "string"},
        "description": (
            f"When this call creates files the user asked for, write them under {alias()} (for example "
            f"{alias()}/report.xlsx) and list the same paths here, so the user receives them as downloads. "
            f"{alias()} is the user's own folder: use it as it is in every argument, including directories and "
            "shell commands. Only files in that folder can be exported, including an existing file the user asks for. "
            f"Relative paths resolve against this call's {'/'.join(WORKDIR_ARG_NAMES)} argument, "
            f"otherwise {workspace.SERVER_CWD}."
        ),
    }


_inflight = 0
_inflight_lock = threading.Lock()


@dataclass(frozen=True)
class ExportContext:
    """What :func:`prepare` learned about a request, handed to :func:`apply`."""

    stdio: bool
    enabled: bool
    method: str
    requested: Any
    base_dir: str | None
    root: str | None = None  # workspace.user_root; None when the call names no user: nothing is read

    @property
    def active(self) -> bool:
        """Whether :func:`apply` has anything to do (stdio and opted in)."""
        return self.stdio and self.enabled


@dataclass(frozen=True)
class LinkOutcome:
    """What became of one ``resource_link``: ``item``, ``note`` (``text``) or ``dup`` (nothing)."""

    index: int
    kind: str
    item: EmbeddedResource | None = None
    text: str | None = None


@dataclass
class Collected:
    """Outcome of :func:`collect_exports`."""

    items: list[EmbeddedResource] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)
    reserved: int = 0
    outcomes: list[LinkOutcome] = field(default_factory=list)  # one per link, in candidate order
    link_files: int = 0
    link_bytes: int = 0


def _first_workdir(arguments: dict[str, Any]) -> str | None:
    for name in WORKDIR_ARG_NAMES:
        value = arguments.get(name)
        if isinstance(value, str) and os.path.isabs(value):
            return value
    return None


def _fill(value: Any, root: str) -> Any:
    """``value`` with the alias replaced by ``root`` in its strings (dicts and lists walked).

    Only the whole path component is mapped: ``codemie_export_dir`` or ``codemie_export2`` stay as written.
    """
    if isinstance(value, str):
        return re.sub(re.escape(alias()) + r"(?![\w.-])", lambda _: root, value)
    if isinstance(value, list):
        return [_fill(v, root) for v in value]
    if isinstance(value, dict):
        return {k: _fill(v, root) for k, v in value.items()}
    return value


def prepare(request: BridgeRequestBody) -> tuple[BridgeRequestBody, ExportContext]:
    """Decide whether export applies and strip the switch and the parameter.

    Substitution runs on a throwaway copy, only to read the transport; the handlers
    receive the original request (so ``$`` values reach them unchanged and substitution
    is not applied twice) with ``CODEMIE_EXPORT_FILES`` removed from ``env`` and, on a
    stdio ``tools/call``, ``codemie_export_files`` removed from the arguments. On an opted-in call
    with a user, the alias in the arguments and the export list becomes the user's folder, which
    is created first, so the model writes there before it exports (the description cannot name it).
    """
    method = request.method.strip()
    env = request.env or {}
    try:
        substituted = apply_substitutions(request)
        stdio = detect_transport_type(substituted.serverPath, request.http_transport_type) == "stdio"
        enabled = stdio and str(env.get(SWITCH_KEY, "")).strip().lower() in _TRUE_VALUES
    except HTTPException:
        # The handler raises the same error; just strip so the key never leaks.
        stdio = not request.serverPath.startswith(("http://", "https://", "ws://", "wss://"))
        enabled = False

    stripped = request.model_copy(deep=True)
    if stripped.env is not None:
        stripped.env.pop(SWITCH_KEY, None)

    requested: Any = None
    base_dir: str | None = None
    root = workspace.user_root(request.user_id, request.conversation_id or request.workflow_execution_id)
    if stdio and method == "tools/call" and isinstance(stripped.params, dict):
        arguments = stripped.params.get("arguments")
        if isinstance(arguments, dict):
            requested = arguments.pop(EXPORT_PARAM, None)
            if enabled and root is not None:
                filled = _fill(arguments, root)
                if filled != arguments:
                    _make_root(root)
                    stripped.params["arguments"] = arguments = filled
                requested = _fill(requested, root)
            base_dir = _first_workdir(arguments)
    return stripped, ExportContext(stdio, enabled, method, requested, base_dir, root)


def _make_root(root: str) -> None:
    try:
        os.makedirs(root, exist_ok=True)
    except OSError as exc:  # the tool then fails to write there and says so; export refuses nothing extra
        logger.warning("Export folder %s not created: %s", root, exc)


def release(n: int) -> None:
    """Return ``n`` bytes to the pod-wide in-flight budget."""
    global _inflight
    with _inflight_lock:
        _inflight = max(0, _inflight - n)


def _reserve(n: int) -> bool:
    global _inflight
    with _inflight_lock:
        if _inflight + n > MAX_INFLIGHT_BYTES:
            return False
        _inflight += n
        return True


def _mime(name: str) -> str:
    ext = os.path.splitext(name)[1].lower()
    return _MIME_OVERRIDES.get(ext) or mimetypes.guess_type(name)[0] or "application/octet-stream"


def _check_path(given: Any, base_dir: str | None, root: str) -> tuple[str | None, str | None]:
    """Return ``(resolved_path, None)`` or ``(None, refusal_reason)``; ``root`` is the containment root."""
    if not isinstance(given, str) or not given:
        return None, "not a non-empty string path"
    if "\x00" in given:
        return None, "NUL bytes are not allowed"
    if ".." in given.split("/"):
        return None, "'..' segments are not allowed"
    # Relative paths resolve where the server writes (its cwd, workspace.SERVER_CWD), never in the user's folder,
    # so a bare name cannot pick up an older same-named file there; ``root`` only gates.
    p = os.path.normpath(os.path.join(base_dir or workspace.SERVER_CWD, given))
    try:
        real = os.path.realpath(p)
    except ValueError:  # UnicodeEncodeError: a lone surrogate cannot be encoded for the filesystem
        return None, "path is not valid UTF-8"
    if real != p:
        return None, "symlinks are not allowed"
    try:
        inside = os.path.commonpath([p, root]) == root
    except ValueError:
        inside = False
    if not inside or p == root:
        return None, f"outside {root}; write the file there again (under {alias()}) and export it"
    if any(seg.startswith(".") for seg in os.path.relpath(p, root).split(os.sep)):
        return None, "hidden paths are not allowed"
    return p, None


@dataclass(frozen=True)
class LinkCandidate:
    """One ``resource_link`` item: a decoded path to read, or the reason it was refused."""

    index: int
    given: str
    path: str | None
    reason: str | None
    size: int | None


_FILE_PREFIX = "file:///"
_ENCODED = ("%2f", "%2e", "%00")
_REASON_SCHEME = "not a file:/// URI"
_REASON_QUERY = "query or fragment not allowed"
_REASON_BACKSLASH = "backslash not allowed"
_REASON_ENCODED = "encoded '/', '.' or NUL not allowed"
_REASON_CANONICAL = "path is not canonical"
_REASON_UTF8 = "path is not valid UTF-8"


def _link_path(uri: str) -> tuple[str | None, str | None]:
    """Return ``(decoded_path, None)`` or ``(None, refusal_reason)`` for a link URI."""
    if not uri.startswith(_FILE_PREFIX):
        return None, _REASON_SCHEME
    if "?" in uri or "#" in uri:
        return None, _REASON_QUERY
    if "\\" in uri:
        return None, _REASON_BACKSLASH
    raw = uri[len("file://") :]
    if any(token in raw.lower() for token in _ENCODED):
        return None, _REASON_ENCODED
    if any(seg in ("", ".", "..") for seg in raw.split("/")[1:]):
        return None, _REASON_CANONICAL
    try:
        return unquote(raw, errors="strict"), None
    except UnicodeDecodeError:
        return None, _REASON_UTF8


def extract_links(content: list[Any], is_error: bool) -> list[LinkCandidate]:
    """Turn ``resource_link`` items of a result into candidates; refusals carry a reason.

    Links past ``MAX_LINKS`` collapse into one refusal at the first excess index.
    """
    out: list[LinkCandidate] = []
    if is_error:
        return out
    for index, item in enumerate(content):
        if not isinstance(item, dict) or item.get("type") != "resource_link":
            continue
        uri = item.get("uri")
        if not isinstance(uri, str):
            continue
        if len(out) >= MAX_LINKS:
            out.append(LinkCandidate(index, uri, None, f"exceeds limit of {MAX_LINKS} links per call", None))
            break
        path, reason = _link_path(uri)
        size = item.get("size")
        out.append(
            LinkCandidate(
                index,
                path if path is not None else uri,
                path,
                reason,
                size if isinstance(size, int) and not isinstance(size, bool) else None,
            )
        )
    return out


def collect_exports(
    paths: list[str],
    base_dir: str | None,
    skip: set[str],
    links: list[LinkCandidate] | None = None,
    root: str | None = None,
) -> Collected:
    """Read the named files. Synchronous: run it through ``asyncio.to_thread``.

    Every refusal is recorded with its reason; nothing is dropped silently except
    a duplicate real path or a file the server already returned under its full path
    (``skip``: full paths, or bare names when the server's URI carried no folder; a
    bare-name match gets a refusal, since it may be a different file). ``links`` are read
    after ``paths`` under the same limits; each gets one entry in ``Collected.outcomes``.
    """
    out = Collected()
    try:
        _collect_into(out, paths, base_dir, skip, links or [], root or workspace.SERVER_CWD)
    except BaseException:
        release(out.reserved)  # the caller never sees `out`; free what earlier files reserved
        raise
    return out


@dataclass
class _State:
    """Per-call bookkeeping shared by every file read in one :func:`collect_exports`."""

    total: int = 0
    seen: set[str] = field(default_factory=set)
    delivered: set[str] = field(default_factory=set)  # real paths


def _why(given: str, reason: str) -> str:
    safe = str(given).encode("utf-8", "backslashreplace").decode("utf-8")  # a lone surrogate must not break JSON
    return f"{safe}: {reason}"


def _collect_into(
    out: Collected, paths: list[str], base_dir: str | None, skip: set[str], links: list[LinkCandidate], root: str
) -> None:
    state = _State()
    _make_root(root)  # so the model can write there after a refusal
    for given in paths:
        p, reason = _check_path(given, base_dir, root)
        if p is None:
            out.refusals.append(_why(given, str(reason)))
            continue
        name = os.path.basename(p)
        if p in state.seen or p in skip:
            continue
        if name in skip:  # only the name matched: it may be another file, so say so rather than drop it
            out.refusals.append(_why(given, f"a file named {name} is already attached"))
            continue
        state.seen.add(p)
        kind, value = _read_one(out, state, given, p, name)
        if kind == "item":
            out.items.append(value)
        else:
            out.refusals.append(value)
    for candidate in links:
        out.outcomes.append(_link_outcome(out, state, candidate, skip, root))


def _link_outcome(out: Collected, state: _State, c: LinkCandidate, skip: set[str], root: str) -> LinkOutcome:
    p, reason = (None, c.reason) if c.reason else _check_path(c.path, None, root)
    if p is None:
        return LinkOutcome(c.index, "note", text=_why(c.given, str(reason)))
    if p in state.delivered:
        return LinkOutcome(c.index, "dup")
    name = os.path.basename(p)
    if p in skip or name in skip:
        return LinkOutcome(c.index, "note", text=_why(c.given, f"a file named {name} is already attached"))
    before = state.total
    kind, value = _read_one(out, state, c.given, p, name, c.size, link=True)
    if kind == "note":
        return LinkOutcome(c.index, "note", text=value)
    out.link_files += 1
    out.link_bytes += state.total - before
    return LinkOutcome(c.index, "item", item=value)


def _read_one(
    out: Collected,
    state: _State,
    given: str,
    p: str,
    name: str,
    size_hint: int | None = None,  # declared size of a link, refused before opening
    link: bool = False,  # a link cannot be retried by the model, so its busy text says no "retry later"
) -> tuple[str, Any]:
    """Open and read one checked path: ``("item", EmbeddedResource)`` or ``("note", text)``."""
    if size_hint is not None and size_hint > MAX_FILE_BYTES:
        return "note", _why(given, f"exceeds per-file limit of {MAX_FILE_BYTES} bytes")
    try:
        # shortcut: O_NOFOLLOW guards only the last component, so a directory swapped for a symlink after
        # _check_path is followed out of the user's root; per-user roots (EPMCDME-16903) do not close this.
        # It gains nothing while stdio servers run as MCP-Connect's own uid (they can read the file themselves);
        # verify containment after open (realpath of /proc/self/fd/<fd>) if servers ever run as another uid.
        fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return "note", _why(given, "file not found")
    except OSError as exc:
        return "note", _why(given, f"cannot be opened ({exc.strerror})")
    except ValueError:  # UnicodeEncodeError: a name os.open cannot encode
        return "note", _why(given, "path is not valid UTF-8")
    reserved_here = 0
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            return "note", _why(given, "not a regular file")
        size = st.st_size
        if size > MAX_FILE_BYTES:
            return "note", _why(given, f"exceeds per-file limit of {MAX_FILE_BYTES} bytes")
        if len(state.delivered) >= MAX_FILES:  # explicit and link items share the count
            return "note", _why(given, f"exceeds limit of {MAX_FILES} files per call")
        if state.total + size > MAX_CALL_BYTES:
            return "note", _why(given, f"exceeds per-call limit of {MAX_CALL_BYTES} bytes")
        if not _reserve(size):
            return "note", _why(
                given, "server export capacity is busy" if link else "server export capacity is busy, retry later"
            )
        reserved_here = size
        chunks: list[bytes] = []
        remaining = size
        while remaining > 0:
            chunk = os.read(fd, min(remaining, 1 << 20))
            if not chunk:  # truncated after fstat: export what was read
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if not data:  # the backend refuses an empty blob; say why here instead of sending one
            return "note", _why(given, "file is empty")
        blob = base64.b64encode(data).decode("ascii")
        item = EmbeddedResource(
            type="resource",
            resource=BlobResourceContents(
                uri="file:///" + quote(name),  # type: ignore[arg-type]
                mimeType=_mime(name),
                blob=blob,
            ),
        )
        state.total += size
        out.reserved += size
        reserved_here = 0
        state.delivered.add(p)
        return "item", item
    except OSError as exc:
        return "note", _why(given, f"read failed ({exc.strerror})")
    except ValueError:  # UnicodeEncodeError from quote(): the on-disk name is not valid UTF-8
        return "note", _why(given, "file name is not valid UTF-8")
    finally:
        if reserved_here:
            release(reserved_here)
        os.close(fd)


class ExportJSONResponse(JSONResponse):
    """JSONResponse that returns its budget reservation once the send ends."""

    def __init__(self, content: Any, reserved: int, **kwargs: Any) -> None:
        self._reserved = reserved
        super().__init__(content=content, **kwargs)  # a failure here is released by the caller

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            release(self._reserved)


def _text(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def _existing_resources(content: list[Any], root: str) -> set[str]:
    """Files the server already returned: the full path when its URI names one under ``root``, else the bare name."""
    found: set[str] = set()
    for item in content:
        if isinstance(item, dict) and item.get("type") == "resource":
            uri = (item.get("resource") or {}).get("uri")
            if isinstance(uri, str):
                path, _ = _link_path(uri)
                found.add(path if path and path.startswith(root + "/") else unquote(uri.rsplit("/", 1)[-1]))
    return found


def _release_when_done(fut: asyncio.Future[Collected]) -> None:
    if not fut.cancelled() and fut.exception() is None:
        release(fut.result().reserved)


async def apply(ctx: ExportContext, result: Any, headers: dict[str, str]) -> Response:
    """Build the ``/bridge`` response, injecting or appending export data when enabled."""
    dump = result.model_dump(mode="json", exclude_none=True) if hasattr(result, "model_dump") else result

    if ctx.stdio and ctx.enabled and isinstance(dump, dict):
        if ctx.method == "tools/list":
            for tool in dump.get("tools") or []:
                schema = tool.get("inputSchema") if isinstance(tool, dict) else None
                if isinstance(schema, dict) and isinstance(schema.setdefault("properties", {}), dict):
                    schema["properties"].setdefault(EXPORT_PARAM, _param_schema())
        elif (
            ctx.method == "tools/call"
            and isinstance(dump.get("content"), list)
            and (ctx.requested not in (None, []) or extract_links(dump["content"], dump.get("isError") is True))
        ):
            return await _export_call(ctx, dump, headers)

    return JSONResponse(content=dump, status_code=200, headers=headers)


async def _export_call(ctx: ExportContext, dump: dict[str, Any], headers: dict[str, str]) -> Response:
    content: list[Any] = dump["content"]
    requested = ctx.requested
    if dump.get("isError") is True:
        content.append(_text(_SKIPPED_NOTE))  # links of a failed call stay untouched
        return JSONResponse(content=dump, status_code=200, headers=headers)
    if ctx.root is None:  # fail closed: without a user there is no folder to read from; links stay as they are
        if requested not in (None, []):
            content.append(_text(f"{EXPORT_PARAM}: the call names no user, nothing exported"))
        return JSONResponse(content=dump, status_code=200, headers=headers)
    links = extract_links(content, False)
    paths: list[str] = []
    if isinstance(requested, list) and all(isinstance(p, str) for p in requested):
        paths = requested
    elif requested is not None:
        content.append(_text(f"{EXPORT_PARAM}: expected a list of file path strings, nothing exported"))
        if not links:
            return JSONResponse(content=dump, status_code=200, headers=headers)
    root = ctx.root
    fut = asyncio.ensure_future(
        asyncio.to_thread(
            collect_exports, paths, ctx.base_dir, _existing_resources(content, root), links=links, root=root
        )
    )
    original = list(content)
    try:
        collected = await asyncio.shield(fut)
    except asyncio.CancelledError:
        fut.add_done_callback(_release_when_done)  # the thread keeps running; free its reservation
        raise
    except Exception:
        logger.exception("Export failed; returning the tool result unchanged")
        return JSONResponse(content=dump, status_code=200, headers=headers)
    reserved = collected.reserved
    try:
        by_index = {o.index: o for o in collected.outcomes}
        # links past MAX_LINKS after the summary note are dropped: the note stands for them
        cut = links[-1].index if len(links) > MAX_LINKS else len(content)
        rebuilt: list[Any] = []
        for i, item in enumerate(content):
            o = by_index.get(i)
            if o is None:
                if not (i > cut and isinstance(item, dict) and item.get("type") == "resource_link"):
                    rebuilt.append(item)
            elif o.kind == "item" and o.item is not None:
                rebuilt.append(o.item.model_dump(mode="json", exclude_none=True))
            elif o.kind == "note":
                rebuilt.append(_text(str(o.text)))
        content[:] = rebuilt
        content.extend(item.model_dump(mode="json", exclude_none=True) for item in collected.items)
        if collected.refusals:
            content.append(_text("Files not exported:\n" + "\n".join(collected.refusals)))
        logger.info(
            "Export: %d file(s) attached, %d refused, %d bytes (%d from links, %d bytes)",
            len(collected.items) + collected.link_files,
            len(collected.refusals) + sum(o.kind == "note" for o in collected.outcomes),
            reserved,
            collected.link_files,
            collected.link_bytes,
        )
        if not paths and not collected.link_files:
            return JSONResponse(content=dump, status_code=200, headers=headers)
        return await asyncio.to_thread(
            ExportJSONResponse, content=dump, reserved=reserved, status_code=200, headers=headers
        )
    except Exception:
        release(reserved)  # export must never lose the tool result: fall back to the original
        logger.exception("Export failed; returning the tool result unchanged")
        content[:] = original
        return JSONResponse(content=dump, status_code=200, headers=headers)
    except BaseException:
        release(reserved)
        raise
