"""Test that every route returns 503 with no_vault_registered when vault_root is None.

TDD test for Task 17 of Plan #13b-β1: _vault helpers must guard against None primary.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from claude_mnemos.daemon.app import create_app


@pytest.fixture
def client():
    app = create_app(vault_root=None, daemon=None)
    return TestClient(app)


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/snapshots"),
        ("GET", "/activity"),
        ("PATCH", "/pages/some-page"),  # pages has no GET; use PATCH
        ("GET", "/trash"),
        ("GET", "/lint/results"),
        ("GET", "/suggestions"),
        ("GET", "/lost-sessions"),
        ("GET", "/metrics/usage"),
        ("GET", "/vault/info"),
    ],
)
def test_routes_return_503_when_no_primary(
    client: TestClient, method: str, path: str
) -> None:
    r = client.request(method, path, json={})
    assert r.status_code == 503, (method, path, r.text)
    body = r.json()
    assert body.get("detail", {}).get("error") == "no_vault_registered", (
        method,
        path,
        body,
    )


def test_health_works_without_primary(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200


def test_projects_works_without_primary(client: TestClient) -> None:
    r = client.get("/projects")
    assert r.status_code == 200


def test_dead_letter_503_without_daemon(client: TestClient) -> None:
    """dead-letter returns 503 for a different reason (no jobs subsystem),
    which is fine — it already has its own guard."""
    r = client.get("/dead-letter")
    assert r.status_code == 503
