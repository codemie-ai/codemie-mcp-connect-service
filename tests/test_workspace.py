"""EPMCDME-14735: stdio servers are spawned in the shared working folder when it exists."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_connect.utils import workspace


def test_server_cwd_is_the_folder_when_it_exists(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(workspace, "SERVER_CWD", str(tmp_path))
    assert workspace.server_cwd() == str(tmp_path)


def test_server_cwd_inherits_when_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(workspace, "SERVER_CWD", str(tmp_path / "absent"))
    assert workspace.server_cwd() is None


def test_user_root_lives_under_server_cwd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(workspace, "SERVER_CWD", str(tmp_path))
    root = workspace.user_root("u")
    assert root is not None and root.startswith(f"{tmp_path}/u-")


def test_scope_gets_its_own_folder_inside_the_users(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(workspace, "SERVER_CWD", str(tmp_path))
    user = workspace.user_root("u")
    a, b = workspace.user_root("u", "conv-a"), workspace.user_root("u", "conv-b")
    assert a is not None and b is not None and user is not None
    assert a.startswith(user + "/c-") and b.startswith(user + "/c-") and a != b
    assert len(a.rsplit("/", 1)[1]) == 18 and a == workspace.user_root(" u ", " conv-a ")


@pytest.mark.parametrize("scope", [None, "", "   "])
def test_no_scope_is_the_users_folder(scope: str | None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(workspace, "SERVER_CWD", str(tmp_path))
    assert workspace.user_root("u", scope) == workspace.user_root("u")


def test_scope_without_user_has_no_folder() -> None:
    assert workspace.user_root(None, "conv-a") is None
