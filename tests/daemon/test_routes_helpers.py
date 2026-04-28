from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from claude_mnemos.daemon.routes._helpers import all_runtimes, get_runtime


def _request(daemon: object | None) -> object:
    """Build a fake request with .app.state.daemon."""
    req = MagicMock()
    req.app.state.daemon = daemon
    return req


def test_get_runtime_returns_runtime():
    rt = MagicMock()
    daemon = MagicMock()
    daemon.runtimes = {"alpha": rt}
    assert get_runtime(_request(daemon), "alpha") is rt


def test_get_runtime_unknown_project_returns_404():
    daemon = MagicMock()
    daemon.runtimes = {}
    with pytest.raises(HTTPException) as exc_info:
        get_runtime(_request(daemon), "ghost")
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == "unknown_project"
    assert exc_info.value.detail["project_name"] == "ghost"


def test_get_runtime_no_daemon_returns_503():
    with pytest.raises(HTTPException) as exc_info:
        get_runtime(_request(None), "alpha")
    assert exc_info.value.status_code == 503


def test_all_runtimes_sorted_by_name():
    rt_a = MagicMock()
    rt_a.name = "alpha"
    rt_b = MagicMock()
    rt_b.name = "beta"
    rt_c = MagicMock()
    rt_c.name = "charlie"
    daemon = MagicMock()
    daemon.runtimes = {"charlie": rt_c, "alpha": rt_a, "beta": rt_b}
    result = all_runtimes(_request(daemon))
    assert [r.name for r in result] == ["alpha", "beta", "charlie"]


def test_all_runtimes_empty_when_no_daemon():
    assert all_runtimes(_request(None)) == []


def test_all_runtimes_empty_when_no_runtimes():
    daemon = MagicMock()
    daemon.runtimes = {}
    assert all_runtimes(_request(daemon)) == []
