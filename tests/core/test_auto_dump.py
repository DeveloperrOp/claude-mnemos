"""Tests for claude_mnemos.core.auto_dump.

v0.0.10: auto_dump_stale only fires on stale (>24h) sessions and only when
the project has ``dump_stale_after_24h`` opted in (per-project or via
``GlobalSettings.auto_ingest_defaults``). Pre-v0.0.10 it triggered on
"cooling" (30min–24h) sessions silently.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from claude_mnemos.core.auto_dump import auto_dump_stale
from claude_mnemos.state.jobs import JOBS_DB_FILENAME, JobStore
from claude_mnemos.state.projects import ProjectMapEntry, ProjectStore
from claude_mnemos.state.settings import (
    AutoIngestDefaults,
    AutoIngestSettings,
    GlobalSettings,
    ProjectSettings,
)


@pytest.fixture(autouse=True)
def _clear_transcripts_cache():
    from claude_mnemos.core.transcript_scanner import invalidate_transcripts_cache
    invalidate_transcripts_cache()
    yield
    invalidate_transcripts_cache()


def _settings_store_with_global(glob: GlobalSettings) -> MagicMock:
    """Build a SettingsStore stub that returns ``glob`` from get_global()."""
    store = MagicMock()
    store.get_global.return_value = glob
    return store


_OPT_IN_GLOB = GlobalSettings(
    auto_ingest_defaults=AutoIngestDefaults(dump_stale_after_24h=True)
)


class _FakeRuntime:
    def __init__(
        self,
        name: str,
        vault: Path,
        *,
        settings: ProjectSettings | None = None,
    ) -> None:
        self.name = name
        self.vault_root = vault
        self.job_store = JobStore(vault / JOBS_DB_FILENAME)
        self.job_worker = None
        # ProjectSettings() yields auto_ingest with all None — i.e. inherits
        # from global. Tests opt-in by passing a non-default GlobalSettings
        # to auto_dump_stale's settings_store kwarg, or by overriding
        # ``settings.auto_ingest`` per-project.
        self.settings = settings or ProjectSettings()


def _stale_jsonl(root: Path, name: str, cwd: str, hours_ago: float) -> Path:
    p = root / f"{name}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(json.dumps({"cwd": cwd, "sid": name}).encode("utf-8"))
    ts = (datetime.now(tz=UTC) - timedelta(hours=hours_ago)).timestamp()
    os.utime(p, (ts, ts))
    return p


@pytest.fixture
def projects_with_alpha(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    """Register project 'alpha' with cwd_patterns matching tmp_path/work."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    work = tmp_path / "work"
    work.mkdir()
    vault = tmp_path / "vault-alpha"
    vault.mkdir()
    map_path = home / ".claude-mnemos" / "project-map.json"
    store = ProjectStore(map_path=map_path)
    store.add(ProjectMapEntry(
        name="alpha",
        vault_root=vault,
        cwd_patterns=[str(work)],
    ))
    return vault, str(work)


@pytest.mark.asyncio
async def test_auto_dump_stale_enqueues_when_opted_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, projects_with_alpha: tuple[Path, str]
) -> None:
    """Stale (>24h) session in registered project + dump_stale_after_24h=True → enqueue."""
    vault, cwd = projects_with_alpha
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(transcripts))
    _stale_jsonl(transcripts, "sess-stale", cwd, hours_ago=25)  # past 24h cutoff

    runtime = _FakeRuntime("alpha", vault)
    queued = await auto_dump_stale(
        {"alpha": runtime},
        settings_store=_settings_store_with_global(_OPT_IN_GLOB),
    )

    assert queued == 1
    counts = runtime.job_store.count_by_status()
    assert sum(counts.values()) == 1
    runtime.job_store.close()


@pytest.mark.asyncio
async def test_auto_dump_default_opted_in_dumps_with_no_extract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, projects_with_alpha: tuple[Path, str]
) -> None:
    """Fresh GlobalSettings: dump_stale_after_24h defaults to True (free
    safety net), extract_after_dump defaults to False (no LLM). So a stale
    session in a registered project IS enqueued, but as a raw dump."""
    vault, cwd = projects_with_alpha
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(transcripts))
    _stale_jsonl(transcripts, "sess-stale", cwd, hours_ago=48)

    runtime = _FakeRuntime("alpha", vault)
    queued = await auto_dump_stale(
        {"alpha": runtime},
        settings_store=_settings_store_with_global(GlobalSettings()),
    )

    assert queued == 1
    rows = runtime.job_store.list_by_status("queued")
    assert rows[0].payload["extract"] is False
    runtime.job_store.close()


@pytest.mark.asyncio
async def test_auto_dump_explicit_opt_out_skips_everything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, projects_with_alpha: tuple[Path, str]
) -> None:
    """Per-project ``dump_stale_after_24h=False`` overrides the True global
    default. Power user can fully silence the cron for that project."""
    vault, cwd = projects_with_alpha
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(transcripts))
    _stale_jsonl(transcripts, "sess-stale", cwd, hours_ago=48)

    project_settings = ProjectSettings(
        auto_ingest=AutoIngestSettings(dump_stale_after_24h=False),
    )
    runtime = _FakeRuntime("alpha", vault, settings=project_settings)
    queued = await auto_dump_stale(
        {"alpha": runtime},
        settings_store=_settings_store_with_global(GlobalSettings()),
    )

    assert queued == 0
    runtime.job_store.close()


@pytest.mark.asyncio
async def test_auto_dump_skips_unassigned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, projects_with_alpha: tuple[Path, str]
) -> None:
    """A stale session whose cwd matches no project must never be enqueued —
    daemon has no project context to attribute it to."""
    vault, _cwd = projects_with_alpha
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(transcripts))
    _stale_jsonl(transcripts, "orphan", "D:\\nowhere", hours_ago=48)

    runtime = _FakeRuntime("alpha", vault)
    queued = await auto_dump_stale(
        {"alpha": runtime},
        settings_store=_settings_store_with_global(_OPT_IN_GLOB),
    )

    assert queued == 0
    runtime.job_store.close()


@pytest.mark.asyncio
async def test_auto_dump_skips_recent_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, projects_with_alpha: tuple[Path, str]
) -> None:
    """Sessions within the cooling window (<24h) must NOT be enqueued — even
    if dump_stale_after_24h is opted in. They may still be active (resume).

    Regression for the v0.0.9 bug where 'cooling' status (30min-24h) was a
    trigger for auto-dump, dumping mid-session transcripts.
    """
    vault, cwd = projects_with_alpha
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(transcripts))
    _stale_jsonl(transcripts, "fresh", cwd, hours_ago=0.05)  # 3 min ago — hot
    _stale_jsonl(transcripts, "cooling", cwd, hours_ago=2)   # 2h ago — cooling
    _stale_jsonl(transcripts, "cooling-far", cwd, hours_ago=20)  # 20h — still cooling

    runtime = _FakeRuntime("alpha", vault)
    queued = await auto_dump_stale(
        {"alpha": runtime},
        settings_store=_settings_store_with_global(_OPT_IN_GLOB),
    )

    assert queued == 0
    runtime.job_store.close()


@pytest.mark.asyncio
async def test_auto_dump_caps_at_max_per_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, projects_with_alpha: tuple[Path, str]
) -> None:
    vault, cwd = projects_with_alpha
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(transcripts))
    for i in range(5):
        _stale_jsonl(transcripts, f"s{i}", cwd, hours_ago=25 + i)  # all stale

    runtime = _FakeRuntime("alpha", vault)
    queued = await auto_dump_stale(
        {"alpha": runtime},
        settings_store=_settings_store_with_global(_OPT_IN_GLOB),
        max_per_run=2,
    )

    assert queued == 2
    runtime.job_store.close()


@pytest.mark.asyncio
async def test_auto_dump_extract_inherits_from_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, projects_with_alpha: tuple[Path, str]
) -> None:
    """The job's ``extract`` payload field is decided by the resolved
    ``extract_after_dump`` flag — default False (raw dump only, zero LLM)."""
    vault, cwd = projects_with_alpha
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(transcripts))
    _stale_jsonl(transcripts, "auto", cwd, hours_ago=25)

    runtime = _FakeRuntime("alpha", vault)
    await auto_dump_stale(
        {"alpha": runtime},
        settings_store=_settings_store_with_global(_OPT_IN_GLOB),
    )

    rows = runtime.job_store.list_by_status("queued")
    assert len(rows) == 1
    assert rows[0].payload["extract"] is False  # default — no LLM
    assert rows[0].payload["transcript_path"].endswith("auto.jsonl")
    runtime.job_store.close()


@pytest.mark.asyncio
async def test_auto_dump_extract_true_when_explicitly_opted_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, projects_with_alpha: tuple[Path, str]
) -> None:
    """When project explicitly opts into extract_after_dump=True, the job
    payload sets extract=True so the worker runs LLM extraction."""
    vault, cwd = projects_with_alpha
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(transcripts))
    _stale_jsonl(transcripts, "extract-me", cwd, hours_ago=25)

    project_settings = ProjectSettings(
        auto_ingest=AutoIngestSettings(extract_after_dump=True),
    )
    runtime = _FakeRuntime("alpha", vault, settings=project_settings)
    await auto_dump_stale(
        {"alpha": runtime},
        settings_store=_settings_store_with_global(_OPT_IN_GLOB),
    )

    rows = runtime.job_store.list_by_status("queued")
    assert len(rows) == 1
    assert rows[0].payload["extract"] is True
    runtime.job_store.close()
