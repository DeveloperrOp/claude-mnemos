from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient

from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.process import MnemosDaemon


def _client() -> TestClient:
    return TestClient(MnemosDaemon(DaemonConfig(boot_filter=None)).app)


def test_get_fs_home_returns_absolute_path() -> None:
    resp = _client().get("/fs/home")
    assert resp.status_code == 200
    body = resp.json()
    assert "home" in body
    assert os.path.isabs(body["home"])


def test_get_fs_home_returns_user_home() -> None:
    """Should mirror os.path.expanduser('~')."""
    resp = _client().get("/fs/home")
    assert resp.status_code == 200
    expected = os.path.expanduser("~")
    assert Path(resp.json()["home"]) == Path(expected)


def test_get_fs_browse_lists_directories(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()
    (tmp_path / "file.txt").write_text("hello")  # files filtered out

    resp = _client().get(f"/fs/browse?path={tmp_path}")
    assert resp.status_code == 200
    body = resp.json()
    assert Path(body["cwd"]) == tmp_path.resolve()
    names = [e["name"] for e in body["entries"]]
    assert names == ["alpha", "beta"]
    assert body["truncated"] is False


def test_get_fs_browse_parent_returns_parent_path(tmp_path: Path) -> None:
    sub = tmp_path / "child"
    sub.mkdir()
    resp = _client().get(f"/fs/browse?path={sub}")
    assert resp.status_code == 200
    assert Path(resp.json()["parent"]) == tmp_path.resolve()


def test_get_fs_browse_returns_400_for_relative_path() -> None:
    resp = _client().get("/fs/browse?path=relative/path")
    assert resp.status_code == 400
    assert "absolute" in resp.json()["detail"].lower()


def test_get_fs_browse_returns_400_for_missing_path(tmp_path: Path) -> None:
    resp = _client().get(f"/fs/browse?path={tmp_path / 'nonexistent'}")
    assert resp.status_code == 400


def test_get_fs_browse_returns_400_for_file_path(tmp_path: Path) -> None:
    f = tmp_path / "x.txt"
    f.write_text("hi")
    resp = _client().get(f"/fs/browse?path={f}")
    assert resp.status_code == 400
    assert "directory" in resp.json()["detail"].lower()


def test_get_fs_browse_truncates_at_limit(tmp_path: Path) -> None:
    """Folders >100 — truncated=true, entries capped at 100."""
    for i in range(105):
        (tmp_path / f"d{i:03d}").mkdir()
    resp = _client().get(f"/fs/browse?path={tmp_path}")
    body = resp.json()
    assert len(body["entries"]) == 100
    assert body["truncated"] is True


def test_get_fs_browse_sorts_case_insensitive(tmp_path: Path) -> None:
    (tmp_path / "Beta").mkdir()
    (tmp_path / "alpha").mkdir()
    resp = _client().get(f"/fs/browse?path={tmp_path}")
    names = [e["name"] for e in resp.json()["entries"]]
    assert names == ["alpha", "Beta"]


def test_post_fs_mkdir_creates_directory(tmp_path: Path) -> None:
    target = tmp_path / "new_folder"
    resp = _client().post("/fs/mkdir", json={"path": str(target)})
    assert resp.status_code == 200
    assert Path(resp.json()["path"]) == target.resolve()
    assert target.is_dir()


def test_post_fs_mkdir_returns_400_when_target_exists(tmp_path: Path) -> None:
    target = tmp_path / "exists"
    target.mkdir()
    resp = _client().post("/fs/mkdir", json={"path": str(target)})
    assert resp.status_code == 400
    assert "exists" in resp.json()["detail"].lower()


def test_post_fs_mkdir_returns_400_when_parent_missing(tmp_path: Path) -> None:
    target = tmp_path / "parent" / "child"  # parent doesn't exist
    resp = _client().post("/fs/mkdir", json={"path": str(target)})
    assert resp.status_code == 400
    assert "parent" in resp.json()["detail"].lower()


def test_post_fs_mkdir_returns_400_for_relative_path() -> None:
    resp = _client().post("/fs/mkdir", json={"path": "relative/here"})
    assert resp.status_code == 400
