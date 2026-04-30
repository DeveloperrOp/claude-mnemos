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


def test_get_fs_drives_unix_returns_root(monkeypatch) -> None:
    """On Unix, /fs/drives returns single root entry."""
    monkeypatch.setattr("claude_mnemos.daemon.routes.fs.sys.platform", "linux")
    resp = _client().get("/fs/drives")
    assert resp.status_code == 200
    body = resp.json()
    assert body["drives"] == [{"name": "/", "path": "/"}]


def test_get_fs_drives_windows_returns_drive_letters(monkeypatch) -> None:
    """On Windows, /fs/drives returns letter-drive list filtered by exists()."""
    monkeypatch.setattr("claude_mnemos.daemon.routes.fs.sys.platform", "win32")
    real_exists = Path.exists

    def fake_exists(self: Path) -> bool:
        s = str(self)
        if s in ("C:\\", "D:\\"):
            return True
        if len(s) == 3 and s[1:] == ":\\":
            return False
        return real_exists(self)

    monkeypatch.setattr(Path, "exists", fake_exists)
    resp = _client().get("/fs/drives")
    assert resp.status_code == 200
    drives = [d["path"] for d in resp.json()["drives"]]
    assert "C:\\" in drives
    assert "D:\\" in drives


def test_get_fs_browse_with_include_files_returns_files_too(tmp_path: Path) -> None:
    (tmp_path / "subdir").mkdir()
    (tmp_path / "file.md").write_text("hello")
    (tmp_path / "image.png").write_bytes(b"\x00")

    resp = _client().get(f"/fs/browse?path={tmp_path}&include_files=true")
    assert resp.status_code == 200
    entries = resp.json()["entries"]
    types = {e["name"]: e["type"] for e in entries}
    assert types == {"subdir": "directory", "file.md": "file", "image.png": "file"}


def test_get_fs_browse_without_include_files_returns_only_directories(
    tmp_path: Path,
) -> None:
    """Default behaviour unchanged — only directories."""
    (tmp_path / "subdir").mkdir()
    (tmp_path / "file.md").write_text("hi")
    resp = _client().get(f"/fs/browse?path={tmp_path}")
    body = resp.json()
    names = [e["name"] for e in body["entries"]]
    assert names == ["subdir"]
    # type field present (default "directory") for backward-compat
    types = {e["type"] for e in body["entries"]}
    assert types == {"directory"}
