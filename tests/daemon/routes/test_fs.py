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
