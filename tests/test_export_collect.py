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

"""EPMCDME-14735: export file collection, path checks, limits and mime types."""

from __future__ import annotations

import base64
import os
from pathlib import Path

import pytest

from mcp_connect.client import export
from mcp_connect.utils import workspace


@pytest.fixture(autouse=True)
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    resolved = tmp_path.resolve()
    monkeypatch.setattr(workspace, "SERVER_CWD", str(resolved))
    monkeypatch.setattr(export, "_inflight", 0)
    return resolved


def _write(path: Path, data: bytes = b"data") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _refused(c: export.Collected, fragment: str) -> None:
    assert c.items == []
    assert len(c.refusals) == 1 and fragment in c.refusals[0]


def test_accepts_regular_file(root: Path) -> None:
    f = _write(root / "a b.csv", b"x,y")
    c = export.collect_exports([str(f)], None, set())
    assert c.refusals == []
    item = c.items[0].resource
    assert str(item.uri) == "file:///a%20b.csv"
    assert base64.b64decode(item.blob) == b"x,y"  # type: ignore[union-attr]
    assert c.reserved == 3


def test_non_ascii_name_is_percent_encoded(root: Path) -> None:
    f = _write(root / "отчёт.txt")
    c = export.collect_exports([str(f)], None, set())
    assert str(c.items[0].resource.uri) == "file:///" + "%D0%BE%D1%82%D1%87%D1%91%D1%82.txt"


def test_outside_root_refused(root: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    other = _write(tmp_path_factory.mktemp("other").resolve() / "f.txt")
    _refused(export.collect_exports([str(other)], None, set()), "outside")


def test_dotdot_refused(root: Path) -> None:
    _write(root / "f.txt")
    _refused(export.collect_exports(["sub/../f.txt"], None, set()), "'..'")


def test_final_symlink_refused(root: Path) -> None:
    target = _write(root / "t.txt")
    (root / "l.txt").symlink_to(target)
    _refused(export.collect_exports([str(root / "l.txt")], None, set()), "symlink")


def test_symlink_pointing_outside_refused(root: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    outside = _write(tmp_path_factory.mktemp("out").resolve() / "s.txt")
    (root / "l.txt").symlink_to(outside)
    _refused(export.collect_exports([str(root / "l.txt")], None, set()), "symlink")


def test_linked_folder_into_hidden_refused(root: Path) -> None:
    _write(root / ".hidden" / "k")
    (root / "folder").symlink_to(root / ".hidden")
    _refused(export.collect_exports([str(root / "folder" / "k")], None, set()), "symlink")


def test_hidden_path_refused(root: Path) -> None:
    _write(root / ".ssh" / "x")
    _refused(export.collect_exports([str(root / ".ssh" / "x")], None, set()), "hidden")
    _refused(export.collect_exports([".ssh/x"], None, set()), "hidden")


def test_fifo_refused_without_blocking(root: Path) -> None:
    fifo = root / "pipe"
    os.mkfifo(fifo)
    _refused(export.collect_exports([str(fifo)], None, set()), "not a regular file")


def test_directory_refused(root: Path) -> None:
    (root / "d").mkdir()
    _refused(export.collect_exports([str(root / "d")], None, set()), "not a regular file")


def test_root_itself_refused(root: Path) -> None:
    _refused(export.collect_exports([str(root)], None, set()), "outside")


def test_missing_file_refused(root: Path) -> None:
    _refused(export.collect_exports([str(root / "nope.txt")], None, set()), "not found")


@pytest.mark.parametrize("bad", ["", None, 5])
def test_non_string_or_empty_refused(bad: object) -> None:
    c = export.collect_exports([bad], None, set())  # type: ignore[list-item]
    assert c.items == [] and len(c.refusals) == 1


def test_relative_resolves_against_base_dir_else_root(root: Path) -> None:
    _write(root / "w" / "r.txt", b"1")
    _write(root / "r.txt", b"22")
    assert export.collect_exports(["r.txt"], str(root / "w"), set()).reserved == 1
    assert export.collect_exports(["r.txt"], None, set()).reserved == 2


@pytest.mark.parametrize(
    ("name", "mime"),
    [
        ("a.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("a.CSV", "text/csv"),
        ("a.json", "application/json"),
        ("a.zip", "application/zip"),
        ("a.pdf", "application/pdf"),
        ("a.unknownext", "application/octet-stream"),
    ],
)
def test_mime_types(root: Path, name: str, mime: str) -> None:
    f = _write(root / name)
    assert export.collect_exports([str(f)], None, set()).items[0].resource.mimeType == mime


def test_per_file_limit(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(export, "MAX_FILE_BYTES", 3)
    f = _write(root / "big", b"1234")
    _refused(export.collect_exports([str(f)], None, set()), "per-file limit")


def test_per_call_limit(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(export, "MAX_CALL_BYTES", 5)
    a, b = _write(root / "a", b"123"), _write(root / "b", b"456")
    c = export.collect_exports([str(a), str(b)], None, set())
    assert len(c.items) == 1 and "per-call limit" in c.refusals[0]


def test_count_limit_refuses_21st_file(root: Path) -> None:
    paths = [str(_write(root / f"f{i}")) for i in range(21)]
    c = export.collect_exports(paths, None, set())
    assert len(c.items) == 20 and "20 files" in c.refusals[0]


def test_budget_limit_and_release(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(export, "MAX_INFLIGHT_BYTES", 5)
    a, b = _write(root / "a", b"123"), _write(root / "b", b"456")
    c = export.collect_exports([str(a), str(b)], None, set())
    assert len(c.items) == 1 and "capacity" in c.refusals[0]
    assert export._inflight == 3
    export.release(c.reserved)
    assert export._inflight == 0


def test_duplicate_path_exported_once(root: Path) -> None:
    f = _write(root / "a.txt")
    c = export.collect_exports([str(f), "a.txt"], None, set())
    assert len(c.items) == 1 and c.refusals == []


def test_skip_names_are_refused_with_a_note(root: Path) -> None:
    # CR-003: a bare-name match may be an unrelated file, so it is reported, not dropped silently
    f = _write(root / "a.txt")
    _refused(export.collect_exports([str(f)], None, {"a.txt"}), "a file named a.txt is already attached")


def test_unrelated_server_resource_with_same_name_is_reported(root: Path) -> None:
    f = _write(root / "out" / "report.csv")
    content = [{"type": "resource", "resource": {"uri": "s3://bucket/report.csv", "text": "x"}}]
    skip = export._existing_resources(content, str(root))
    _refused(export.collect_exports([str(f)], None, skip), "report.csv is already attached")


def test_server_returned_path_skips_only_that_file(root: Path) -> None:
    mine, other = _write(root / "out" / "report.csv"), _write(root / "other" / "report.csv")
    assert export.collect_exports([str(mine)], None, {str(other)}).items[0].resource.blob  # type: ignore[union-attr]
    assert export.collect_exports([str(other)], None, {str(other)}).items == []
    c = export.collect_exports([], None, {str(other)}, [_link(0, other), _link(1, mine)])
    assert _kinds(c) == ["note", "item"]


def test_truncated_after_fstat_exports_what_was_read(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = _write(root / "t.txt", b"abcdef")
    real_read = os.read
    calls = {"n": 0}

    def short_read(fd: int, n: int) -> bytes:
        calls["n"] += 1
        return real_read(fd, 3) if calls["n"] == 1 else b""

    monkeypatch.setattr(export.os, "read", short_read)
    c = export.collect_exports([str(f)], None, set())
    assert base64.b64decode(c.items[0].resource.blob) == b"abc"  # type: ignore[union-attr]


def test_trailing_slash_path_keeps_its_name(root: Path) -> None:
    _write(root / "report.csv", b"x")
    c = export.collect_exports(["report.csv/"], None, set())
    assert str(c.items[0].resource.uri) == "file:///report.csv"
    assert export.collect_exports(["report.csv/"], None, {"report.csv"}).items == []


def test_empty_file_is_refused_with_reason(root: Path) -> None:
    f = _write(root / "e.csv", b"")
    _refused(export.collect_exports([str(f)], None, set()), "empty")
    assert export._inflight == 0
    c = export.collect_exports([], None, set(), [_link(0, f)])
    assert _kinds(c) == ["note"] and "empty" in str(c.outcomes[0].text)


def test_default_inflight_budget_is_one_max_file() -> None:
    assert export.MAX_INFLIGHT_BYTES == export.MAX_FILE_BYTES == 50 * 1024 * 1024


def test_root_comes_from_the_call_not_the_constant(root: Path, tmp_path: Path) -> None:
    mine = _write(root / "u1" / "a.txt")
    narrow = str(root / "u2")
    c = export.collect_exports([str(mine)], None, set(), root=narrow)
    assert c.items == [] and "outside" in c.refusals[0] and narrow in c.refusals[0]


def test_nul_byte_path_refused_after_good_file(root: Path) -> None:
    good = _write(root / "a.txt", b"123")
    c = export.collect_exports([str(good), "bad\x00.txt"], None, set())
    assert len(c.items) == 1 and "NUL" in c.refusals[0]
    export.release(c.reserved)
    assert export._inflight == 0


def test_mid_loop_failure_releases_earlier_reservations(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    a, b = _write(root / "a.txt", b"123"), _write(root / "b.txt", b"456")
    real_mime = export._mime

    def flaky(name: str) -> str:
        if name == "b.txt":
            raise MemoryError("boom")
        return real_mime(name)

    monkeypatch.setattr(export, "_mime", flaky)
    with pytest.raises(MemoryError):
        export.collect_exports([str(a), str(b)], None, set())
    assert export._inflight == 0


# --- resource_link candidates (link-only delivery) ---


def _link(index: int, path: str | Path, size: int | None = None) -> export.LinkCandidate:
    return export.LinkCandidate(index, str(path), str(path), None, size)


def _kinds(c: export.Collected) -> list[str]:
    return [o.kind for o in c.outcomes]


def test_link_shares_budget_with_explicit_files(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(export, "MAX_CALL_BYTES", 5)
    a, b, d = _write(root / "a", b"123"), _write(root / "b", b"45"), _write(root / "d", b"6")
    c = export.collect_exports([str(a)], None, set(), [_link(1, b), _link(2, d)])
    assert len(c.items) == 1 and _kinds(c) == ["item", "note"]
    assert "per-call limit" in str(c.outcomes[1].text)
    assert c.outcomes[0].index == 1 and c.outcomes[0].item is not None
    assert (c.link_files, c.link_bytes, c.reserved) == (1, 2, 5)
    assert export._inflight == 5


def test_link_uses_remaining_file_count(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(export, "MAX_FILES", 1)
    a, b = _write(root / "a"), _write(root / "b")
    c = export.collect_exports([str(a)], None, set(), [_link(0, b)])
    assert _kinds(c) == ["note"] and "1 files" in str(c.outcomes[0].text)


def test_link_to_delivered_path_is_dup(root: Path) -> None:
    a = _write(root / "a.txt")
    c = export.collect_exports([str(a)], None, set(), [_link(0, a), _link(1, a)])
    assert len(c.items) == 1 and _kinds(c) == ["dup", "dup"] and c.refusals == []
    assert c.outcomes[0].item is None and c.outcomes[0].text is None


def test_two_links_to_one_path_give_one_item(root: Path) -> None:
    a = _write(root / "a.txt")
    c = export.collect_exports([], None, set(), [_link(0, a), _link(3, a)])
    assert _kinds(c) == ["item", "dup"] and c.link_files == 1


def test_same_basename_in_different_folders_is_not_a_duplicate(root: Path) -> None:
    x, y = _write(root / "x" / "report.xlsx", b"1"), _write(root / "y" / "report.xlsx", b"2")
    c = export.collect_exports([], None, set(), [_link(0, x), _link(1, y)])
    assert _kinds(c) == ["item", "item"] and c.refusals == []
    c2 = export.collect_exports([str(x)], None, set(), [_link(0, y)])
    assert len(c2.items) == 1 and _kinds(c2) == ["item"]
    c3 = export.collect_exports([str(x), str(y)], None, set())
    assert len(c3.items) == 2 and c3.refusals == []


def test_link_name_in_skip_names_is_noted(root: Path) -> None:
    a = _write(root / "a.txt")
    c = export.collect_exports([], None, {"a.txt"}, [_link(0, a)])
    assert _kinds(c) == ["note"] and "a.txt" in str(c.outcomes[0].text)


def test_link_to_path_refused_as_explicit_gets_own_note(root: Path) -> None:
    missing = root / "nope.txt"
    c = export.collect_exports([str(missing)], None, set(), [_link(0, missing)])
    assert len(c.refusals) == 1 and _kinds(c) == ["note"] and "not found" in str(c.outcomes[0].text)


def test_prerefused_candidate_becomes_note() -> None:
    cand = export.LinkCandidate(4, "http://x/y", None, "not a file:/// URI", None)
    c = export.collect_exports([], None, set(), [cand])
    assert c.outcomes == [export.LinkOutcome(4, "note", text="http://x/y: not a file:/// URI")]


def test_declared_size_over_limit_never_opens(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(export, "MAX_FILE_BYTES", 3)
    a = _write(root / "a", b"1")

    def no_open(*a: object, **k: object) -> int:
        raise AssertionError("opened")

    monkeypatch.setattr(export.os, "open", no_open)
    c = export.collect_exports([], None, set(), [_link(0, a, size=4)])
    assert _kinds(c) == ["note"] and "per-file limit" in str(c.outcomes[0].text)


def test_link_fstat_size_over_limit(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(export, "MAX_FILE_BYTES", 3)
    a = _write(root / "a", b"1234")
    c = export.collect_exports([], None, set(), [_link(0, a, size=1)])
    assert _kinds(c) == ["note"] and "per-file limit" in str(c.outcomes[0].text)


def test_link_busy_text_has_no_retry(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(export, "MAX_INFLIGHT_BYTES", 2)
    a = _write(root / "a", b"123")
    text = str(export.collect_exports([], None, set(), [_link(0, a)]).outcomes[0].text)
    assert "busy" in text and "retry" not in text
    assert "retry later" in export.collect_exports([str(a)], None, set()).refusals[0]


def test_bad_links_each_get_a_note_rest_intact(root: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    other = _write(tmp_path_factory.mktemp("other").resolve() / "f.txt")
    target = _write(root / "t.txt")
    (root / "l.txt").symlink_to(target)
    _write(root / ".ssh" / "k")
    (root / "d").mkdir()
    os.mkfifo(root / "pipe")
    good = _write(root / "good.txt", b"ok")
    bad = [other, "/tmp", root / "l.txt", root / ".ssh" / "k", root / "d", root / "pipe", root / "nope"]
    links = [_link(i, p) for i, p in enumerate(bad)] + [_link(len(bad), good)]
    c = export.collect_exports([], None, set(), links)
    assert _kinds(c) == ["note"] * len(bad) + ["item"]
    for frag, o in zip(["outside", "outside", "symlink", "hidden", "regular", "regular", "not found"], c.outcomes):
        assert frag in str(o.text)
    assert [o.index for o in c.outcomes] == list(range(len(links)))


def test_link_read_error_is_noted(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    a, b = _write(root / "a", b"1"), _write(root / "b", b"2")

    def bad_read(fd: int, n: int) -> bytes:
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(export.os, "read", bad_read)
    c = export.collect_exports([], None, set(), [_link(0, a), _link(1, b)])
    assert _kinds(c) == ["note", "note"] and "read failed" in str(c.outcomes[0].text)
    assert export._inflight == 0


def test_link_failure_mid_way_releases_reservations(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    a, b = _write(root / "a.txt", b"123"), _write(root / "b.txt", b"456")
    real_mime = export._mime

    def flaky(name: str) -> str:
        if name == "b.txt":
            raise MemoryError("boom")
        return real_mime(name)

    monkeypatch.setattr(export, "_mime", flaky)
    with pytest.raises(MemoryError):
        export.collect_exports([str(a)], None, set(), [_link(0, b)])
    assert export._inflight == 0


# MR !314 note 2513257: a name that is not valid UTF-8 must be refused per file, never raised.
def test_lone_surrogate_path_is_refused_not_raised(root: Path) -> None:
    c = export.collect_exports(["\ud800.txt"], None, set())
    assert c.items == [] and len(c.refusals) == 1
    c.refusals[0].encode("utf-8")  # the note itself must be encodable


def test_non_utf8_file_name_is_refused_not_raised(root: Path) -> None:
    bad = os.path.join(os.fsencode(root), b"\xff.txt")
    with open(bad, "wb") as fh:
        fh.write(b"data")
    c = export.collect_exports([os.fsdecode(bad)], None, set())
    assert c.items == [] and len(c.refusals) == 1
    c.refusals[0].encode("utf-8")
    assert export._inflight == 0 and c.reserved == 0


def test_existing_resources_keep_the_folder_when_the_uri_has_one(root: Path) -> None:
    def res(uri: str) -> dict[str, object]:
        return {"type": "resource", "resource": {"uri": uri, "blob": "AA=="}}

    content = [
        res(f"file://{root}/out/a%20b.csv"),
        res("file:///c.csv"),
        res("file:///elsewhere/d.csv"),
        {"type": "text"},
    ]
    assert export._existing_resources(content, str(root)) == {f"{root}/out/a b.csv", "c.csv", "d.csv"}


def test_relative_path_resolves_where_the_server_writes_not_in_the_user_folder(root: Path) -> None:
    # The server's cwd is EXPORT_ROOT: a bare name it wrote there must not pick up a same-named
    # older file from the user's folder (found in the AC 3 re-run, 16 Nov).
    _write(root / "report.csv", b"new")
    user = root / "u-0123456789abcdef"
    _write(user / "report.csv", b"stale")
    _refused(export.collect_exports(["report.csv"], None, set(), root=str(user)), "outside")


def test_relative_path_with_workdir_inside_user_folder_is_exported(root: Path) -> None:
    user = root / "u-0123456789abcdef"
    _write(user / "s" / "report.csv", b"x")
    c = export.collect_exports(["report.csv"], str(user / "s"), set(), root=str(user))
    assert len(c.items) == 1 and c.refusals == []
