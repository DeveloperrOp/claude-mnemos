"""Test route behaviour when vault_root is None / daemon is None.

TDD test for Task 17 of Plan #13b-β1: _vault helpers must guard against None primary.
Updated in Task 10 of Plan #13b-β2: /lost-sessions is now cross-vault and returns
200 with empty list when daemon is None (no runtimes to iterate).
Updated in Task 13 of Plan #13b-β2: /metrics/* are now cross-vault and return
200 with zero-totals / empty lists when daemon is None (consistent with other
cross-vault endpoints).

Note: /trash, /lint, /ontology, /activity and /vault routes now require a {project}
path segment and are guarded by get_runtime (returns 503 when daemon is None), tested
separately in their respective test_app_*.py files.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from claude_mnemos.daemon.app import create_app


@pytest.fixture
def client():
    app = create_app(daemon=None)
    return TestClient(app)


def test_metrics_usage_returns_zeros_when_no_daemon(client: TestClient) -> None:
    """/metrics/usage returns 200 with zero-totals when daemon is None.

    β2 behaviour: cross-vault route iterates all_runtimes() which returns []
    when daemon is None — no error, just an empty aggregation.
    """
    r = client.get("/api/metrics/usage")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sessions_covered"] == 0
    assert body["tokens_injected"] == 0


def test_lost_sessions_returns_empty_when_no_daemon(client: TestClient) -> None:
    """/lost-sessions returns 200 with empty list when daemon is None.

    β2 behaviour: cross-vault route iterates all_runtimes() which returns []
    when daemon is None — no error, just an empty result.
    """
    r = client.get("/api/lost-sessions")
    assert r.status_code == 200, r.text
    assert r.json() == {"sessions": [], "total": 0}


def test_vault_project_route_503_without_daemon(client: TestClient) -> None:
    """GET /vault/{project} returns 503 when daemon is None."""
    r = client.get("/api/vault/alpha")
    assert r.status_code == 503
    body = r.json()
    assert body.get("detail", {}).get("error") == "daemon_unavailable"


def test_health_works_without_primary(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200


def test_projects_works_without_primary(client: TestClient) -> None:
    r = client.get("/api/projects")
    assert r.status_code == 200


def test_dead_letter_empty_without_daemon(client: TestClient) -> None:
    """GET /dead-letter returns 200 + empty list when daemon is None.

    Cross-vault aggregation via all_runtimes() gracefully returns [] when no
    daemon is registered — no 503, consistent with /jobs behaviour.
    """
    r = client.get("/api/dead-letter")
    assert r.status_code == 200
    assert r.json() == {"jobs": []}


def test_trash_project_route_503_without_daemon(client: TestClient) -> None:
    """GET /trash/{project} returns 503 when daemon is None."""
    r = client.get("/api/trash/alpha")
    assert r.status_code == 503
    body = r.json()
    assert body.get("detail", {}).get("error") == "daemon_unavailable"


def test_lint_project_route_503_without_daemon(client: TestClient) -> None:
    """GET /lint/{project}/results returns 503 when daemon is None."""
    r = client.get("/api/lint/alpha/results")
    assert r.status_code == 503
    body = r.json()
    assert body.get("detail", {}).get("error") == "daemon_unavailable"


def test_ontology_project_route_503_without_daemon(client: TestClient) -> None:
    """GET /ontology/{project}/suggestions returns 503 when daemon is None."""
    r = client.get("/api/ontology/alpha/suggestions")
    assert r.status_code == 503
    body = r.json()
    assert body.get("detail", {}).get("error") == "daemon_unavailable"


def test_activity_project_route_503_without_daemon(client: TestClient) -> None:
    """GET /activity/{project} returns 503 when daemon is None."""
    r = client.get("/api/activity/alpha")
    assert r.status_code == 503
    body = r.json()
    assert body.get("detail", {}).get("error") == "daemon_unavailable"
