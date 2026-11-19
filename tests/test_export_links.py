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

"""EPMCDME-14735: L3 - how the pinned MCP SDK normalises resource_link URIs.

Characterization only: the observed table fixes the strict URI list that the
link resolver refuses or accepts-as-normalised.
"""

from __future__ import annotations

import pytest
from mcp.types import ResourceLink

from mcp_connect.client import export

NOT_FILE = (None, "not a file:/// URI")
QUERY = (None, "query or fragment not allowed")
ENCODED = (None, "encoded '/', '.' or NUL not allowed")
NOT_CANON = (None, "path is not canonical")

# (id, uri, SDK-dumped string, extract_links outcome of the dumped string, outcome of the raw dict string)
# An outcome is (path, refusal reason); exactly one of the two is None.
CASES = [
    ("host", "file://host/x.csv", "file://host/x.csv", NOT_FILE, NOT_FILE),
    (
        "localhost",
        "file://localhost/home/codemie/a.csv",
        "file:///home/codemie/a.csv",
        ("/home/codemie/a.csv", None),
        NOT_FILE,
    ),
    ("query", "file:///home/codemie/a.csv?x=1", "file:///home/codemie/a.csv?x=1", QUERY, QUERY),
    ("fragment", "file:///home/codemie/a.csv#frag", "file:///home/codemie/a.csv#frag", QUERY, QUERY),
    ("relative", "file:x", "file:///x", ("/x", None), NOT_FILE),
    ("relative-slash", "file:/x", "file:///x", ("/x", None), NOT_FILE),
    ("pct-slash", "file:///a%2fb.csv", "file:///a%2fb.csv", ENCODED, ENCODED),
    ("pct-dot", "file:///a%2eb.csv", "file:///a%2eb.csv", ENCODED, ENCODED),
    ("pct-dotdot", "file:///home/%2e%2e/etc/passwd", "file:///etc/passwd", ("/etc/passwd", None), ENCODED),
    ("dotdot", "file:///home/codemie/../etc/passwd", "file:///home/etc/passwd", ("/home/etc/passwd", None), NOT_CANON),
    ("dot", "file:///home/codemie/./a.csv", "file:///home/codemie/a.csv", ("/home/codemie/a.csv", None), NOT_CANON),
    ("pct-nul", "file:///a%00b.csv", "file:///a%00b.csv", ENCODED, ENCODED),
    (
        "pct-invalid-utf8",
        "file:///a%ffb.csv",
        "file:///a%ffb.csv",
        (None, "path is not valid UTF-8"),
        (None, "path is not valid UTF-8"),
    ),
    ("backslash", "file:///a\\b.csv", "file:///a/b.csv", ("/a/b.csv", None), (None, "backslash not allowed")),
    (
        "four-slashes",
        "file:////home/codemie/a.csv",
        "file:///home/codemie/a.csv",
        ("/home/codemie/a.csv", None),
        NOT_CANON,
    ),
    (
        "plain",
        "file:///home/codemie/a%20b.csv",
        "file:///home/codemie/a%20b.csv",
        ("/home/codemie/a b.csv", None),
        ("/home/codemie/a b.csv", None),
    ),
]


def _outcome(uri: str) -> tuple[str | None, str | None]:
    [c] = export.extract_links([{"type": "resource_link", "name": "x", "uri": uri}], False)
    return c.path, c.reason


class TestAnyUrlNormalisation:
    """Production feeds extract_links the SDK-normalised string; the raw dict keeps the exact one."""

    @pytest.mark.parametrize(
        ("uri", "dumped", "sdk_outcome", "raw_outcome"), [c[1:] for c in CASES], ids=[c[0] for c in CASES]
    )
    def test_sdk_link_dump_and_outcome(
        self,
        uri: str,
        dumped: str,
        sdk_outcome: tuple[str | None, str | None],
        raw_outcome: tuple[str | None, str | None],
    ) -> None:
        link = ResourceLink(type="resource_link", name="x", uri=uri)  # type: ignore[arg-type]
        got = link.model_dump(mode="json", exclude_none=True)["uri"]
        assert got == dumped
        assert _outcome(got) == sdk_outcome
        assert _outcome(uri) == raw_outcome

    def test_raw_dict_link_keeps_exact_string(self) -> None:
        uri = "file:///home/%2e%2e/etc/passwd"
        # The SDK model collapses it; only the dict form preserves it, so only the dict form is refused.
        sdk = ResourceLink.model_validate({"type": "resource_link", "name": "x", "uri": uri}).model_dump(mode="json")[
            "uri"
        ]
        assert sdk != uri
        assert _outcome(uri) == ENCODED


def _link(uri: object, **extra: object) -> dict[str, object]:
    return {"type": "resource_link", "name": "x", "uri": uri, **extra}


class TestExtractLinks:
    @pytest.mark.parametrize(
        ("uri", "path"),
        [
            ("file:///home/codemie/a.csv", "/home/codemie/a.csv"),
            ("file:///home/codemie/a%20b.csv", "/home/codemie/a b.csv"),
            ("file:///home/codemie/%C3%A9.csv", "/home/codemie/é.csv"),
            ("file:///home/codemie/a%25b.csv", "/home/codemie/a%b.csv"),
        ],
    )
    def test_accepted(self, uri: str, path: str) -> None:
        [c] = export.extract_links([_link(uri)], False)
        assert (c.index, c.given, c.path, c.reason, c.size) == (0, path, path, None, None)

    @pytest.mark.parametrize(
        ("uri", "reason"),
        [
            ("http://example.com/a.csv", "not a file:/// URI"),
            ("file://host/home/codemie/a.csv", "not a file:/// URI"),
            ("file://localhost/home/codemie/a.csv", "not a file:/// URI"),
            ("file:x", "not a file:/// URI"),
            ("file:/home/codemie/a.csv", "not a file:/// URI"),
            ("file:///home/codemie/a.csv?x=1", "query or fragment not allowed"),
            ("file:///home/codemie/a.csv#frag", "query or fragment not allowed"),
            ("file:///home/codemie/a\\b.csv", "backslash not allowed"),
            ("file:///home/codemie/a%2fb.csv", "encoded '/', '.' or NUL not allowed"),
            ("file:///home/codemie/a%2Eb.csv", "encoded '/', '.' or NUL not allowed"),
            ("file:///home/%2e%2e/etc/passwd", "encoded '/', '.' or NUL not allowed"),
            ("file:///home/codemie/a%00b.csv", "encoded '/', '.' or NUL not allowed"),
            ("file:///home/codemie/../etc/passwd", "path is not canonical"),
            ("file:///home/codemie/./a.csv", "path is not canonical"),
            ("file:////home/codemie/a.csv", "path is not canonical"),
            ("file:///home/codemie/dir/", "path is not canonical"),
            ("file:///home/codemie/a%ffb.csv", "path is not valid UTF-8"),
        ],
    )
    def test_refused(self, uri: str, reason: str) -> None:
        [c] = export.extract_links([_link(uri)], False)
        assert (c.index, c.given, c.path, c.reason) == (0, uri, None, reason)

    def test_error_result_yields_nothing(self) -> None:
        assert export.extract_links([_link("file:///home/codemie/a.csv")], True) == []

    def test_other_items_ignored(self) -> None:
        content = [
            {"type": "text", "text": "file:///home/codemie/a.csv"},
            {"type": "resource", "resource": {"uri": "file:///home/codemie/a.csv"}},
            _link(None),
            _link(5),
            "junk",
            _link("file:///home/codemie/b.csv"),
        ]
        assert [(c.index, c.path) for c in export.extract_links(content, False)] == [(5, "/home/codemie/b.csv")]

    def test_size_taken_only_from_int(self) -> None:
        got = export.extract_links(
            [
                _link("file:///home/codemie/a", size=7),
                _link("file:///home/codemie/b", size="7"),
                _link("file:///home/codemie/c", size=True),
            ],
            False,
        )
        assert [c.size for c in got] == [7, None, None]

    def test_links_past_limit_become_one_summary_refusal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(export, "MAX_LINKS", 2)
        content = [{"type": "text", "text": "t"}] + [_link(f"file:///home/codemie/{n}.csv") for n in range(5)]
        got = export.extract_links(content, False)
        assert [(c.index, c.path) for c in got[:2]] == [(1, "/home/codemie/0.csv"), (2, "/home/codemie/1.csv")]
        assert len(got) == 3
        assert (got[2].index, got[2].path, got[2].reason) == (3, None, "exceeds limit of 2 links per call")
