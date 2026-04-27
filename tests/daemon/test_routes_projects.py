from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from claude_mnemos.daemon.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    vault = tmp_path / "vault"
    vault.mkdir()
    app = create_app(vault, daemon=None)
    return TestClient(app), tmp_path


def test_get_projects_empty(client):
    c, _ = client
    r = c.get("/projects")
    assert r.status_code == 200
    assert r.json() == []


def test_post_project_then_get(client):
    c, home = client
    body = {
        "name": "x",
        "vault_root": str(home / "v"),
        "cwd_patterns": ["~/code/x*"],
    }
    r = c.post("/projects", json=body)
    assert r.status_code == 201, r.text
    r2 = c.get("/projects/x")
    assert r2.status_code == 200
    data = r2.json()
    assert data["name"] == "x"
    assert "settings" in data
    assert data["settings"]["snapshots"]["retention_days"] == 180


def test_post_duplicate_returns_409(client):
    c, home = client
    body = {"name": "x", "vault_root": str(home / "v"), "cwd_patterns": []}
    c.post("/projects", json=body)
    r = c.post("/projects", json=body)
    assert r.status_code == 409


def test_post_invalid_name_returns_422(client):
    c, home = client
    body = {"name": "Bad Name", "vault_root": str(home / "v"), "cwd_patterns": []}
    r = c.post("/projects", json=body)
    assert r.status_code == 422


def test_get_unknown_returns_404(client):
    c, _ = client
    assert c.get("/projects/nope").status_code == 404


def test_patch_updates_fields(client):
    c, home = client
    c.post("/projects", json={
        "name": "x", "vault_root": str(home / "v"), "cwd_patterns": ["~/a"],
    })
    r = c.patch("/projects/x", json={"cwd_patterns": ["~/b"]})
    assert r.status_code == 200
    assert r.json()["cwd_patterns"] == ["~/b"]


def test_patch_unknown_returns_404(client):
    c, _ = client
    r = c.patch("/projects/nope", json={"cwd_patterns": []})
    assert r.status_code == 404


def test_delete_removes_entry(client):
    c, home = client
    c.post("/projects", json={
        "name": "x", "vault_root": str(home / "v"), "cwd_patterns": [],
    })
    r = c.delete("/projects/x")
    assert r.status_code == 204
    assert c.get("/projects/x").status_code == 404


def test_delete_unknown_returns_404(client):
    c, _ = client
    assert c.delete("/projects/nope").status_code == 404


def test_list_returns_all_after_multiple_adds(client):
    c, home = client
    c.post("/projects", json={"name": "a", "vault_root": str(home / "va"), "cwd_patterns": []})
    c.post("/projects", json={"name": "b", "vault_root": str(home / "vb"), "cwd_patterns": []})
    r = c.get("/projects")
    names = sorted(e["name"] for e in r.json())
    assert names == ["a", "b"]


def test_corrupt_map_returns_503(client):
    c, home = client
    f = home / ".claude-mnemos" / "project-map.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("{not json")
    r = c.get("/projects")
    assert r.status_code == 503
