import json
from datetime import UTC, datetime
from pathlib import Path

import pytest


@pytest.fixture
def cache_path(tmp_path: Path, monkeypatch) -> Path:
    p = tmp_path / "update-check.json"
    monkeypatch.setattr("claude_mnemos.core.update_check._CACHE_PATH", p)
    return p


def test_check_returns_has_update_when_newer_remote(monkeypatch, cache_path: Path) -> None:
    monkeypatch.setattr(
        "claude_mnemos.core.update_check._fetch_latest_release",
        lambda: {"tag_name": "v0.0.5", "html_url": "https://github.com/x/y/releases/tag/v0.0.5"},
    )
    monkeypatch.setattr("claude_mnemos.core.update_check._current_version", lambda: "0.0.1")

    from claude_mnemos.core.update_check import check_for_update

    result = check_for_update(force=True)
    assert result.has_update is True
    assert result.current == "0.0.1"
    assert result.latest == "0.0.5"
    assert result.download_url.endswith("/v0.0.5")


def test_check_returns_no_update_when_same_version(monkeypatch, cache_path: Path) -> None:
    monkeypatch.setattr(
        "claude_mnemos.core.update_check._fetch_latest_release",
        lambda: {"tag_name": "v0.0.1", "html_url": "x"},
    )
    monkeypatch.setattr("claude_mnemos.core.update_check._current_version", lambda: "0.0.1")

    from claude_mnemos.core.update_check import check_for_update
    result = check_for_update(force=True)
    assert result.has_update is False


def test_check_uses_cache_when_recent(monkeypatch, cache_path: Path) -> None:
    cache_path.write_text(
        json.dumps({
            "checked_at": datetime.now(tz=UTC).isoformat(),
            "current": "0.0.1",
            "latest": "0.0.7",
            "download_url": "https://example.com/v0.0.7",
            "dismissed_until": None,
        }),
        encoding="utf-8",
    )

    fetched = {"calls": 0}
    def fake_fetch():
        fetched["calls"] += 1
        return {"tag_name": "v0.0.99", "html_url": "x"}
    monkeypatch.setattr("claude_mnemos.core.update_check._fetch_latest_release", fake_fetch)
    monkeypatch.setattr("claude_mnemos.core.update_check._current_version", lambda: "0.0.1")

    from claude_mnemos.core.update_check import check_for_update
    result = check_for_update(force=False)
    assert fetched["calls"] == 0
    assert result.latest == "0.0.7"


def test_dismiss_records_until_timestamp(monkeypatch, cache_path: Path) -> None:
    monkeypatch.setattr(
        "claude_mnemos.core.update_check._fetch_latest_release",
        lambda: {"tag_name": "v0.0.5", "html_url": "x"},
    )
    monkeypatch.setattr("claude_mnemos.core.update_check._current_version", lambda: "0.0.1")

    from claude_mnemos.core.update_check import check_for_update, dismiss_for_days

    check_for_update(force=True)
    dismiss_for_days(7)

    data = json.loads(cache_path.read_text(encoding="utf-8"))
    assert data["dismissed_until"] is not None


def test_check_returns_no_update_on_network_error(monkeypatch, cache_path: Path) -> None:
    def fake_fetch():
        raise OSError("offline")
    monkeypatch.setattr("claude_mnemos.core.update_check._fetch_latest_release", fake_fetch)
    monkeypatch.setattr("claude_mnemos.core.update_check._current_version", lambda: "0.0.1")

    from claude_mnemos.core.update_check import check_for_update
    result = check_for_update(force=True)
    assert result.has_update is False
    assert result.error is not None
