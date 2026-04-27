"""CLI tests for `mnemos metrics {usage,top-sessions,timeline}` (Plan #13a Task 11)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from claude_mnemos.cli import build_parser, main
from claude_mnemos.state.manifest import IngestRecord, Manifest

# ─── parser tests ─────────────────────────────────────────────────────────


def test_parser_metrics_usage(tmp_path: Path) -> None:
    args = build_parser().parse_args(
        ["metrics", "usage", "--vault", str(tmp_path), "--period", "7d"]
    )
    assert args.command == "metrics"
    assert args.metrics_cmd == "usage"
    assert args.period == "7d"


def test_parser_metrics_top_sessions(tmp_path: Path) -> None:
    args = build_parser().parse_args(
        ["metrics", "top-sessions", "--vault", str(tmp_path), "--limit", "3"]
    )
    assert args.metrics_cmd == "top-sessions"
    assert args.limit == 3


def test_parser_metrics_timeline_default_period(tmp_path: Path) -> None:
    args = build_parser().parse_args(
        ["metrics", "timeline", "--vault", str(tmp_path)]
    )
    assert args.metrics_cmd == "timeline"
    assert args.period == "30d"


# ─── helpers ──────────────────────────────────────────────────────────────


def _ingest_record(
    sid: str,
    *,
    ingested_at: datetime,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    raw_transcript_bytes: int | None = None,
) -> IngestRecord:
    return IngestRecord(
        session_id=sid,
        ingested_at=ingested_at,
        raw_path=f"raw/chats/{sid}.md",
        source_path=f"wiki/sources/{sid}.md",
        created_pages=[],
        skipped_collisions=[],
        model=None,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        transcript_path=None,
        raw_transcript_bytes=raw_transcript_bytes,
    )


def _seed_manifest(vault: Path) -> None:
    m = Manifest()
    m.add(
        "sha-a",
        _ingest_record(
            "sid-a",
            ingested_at=datetime.now(UTC),
            input_tokens=100,
            output_tokens=200,
            raw_transcript_bytes=10_000,
        ),
    )
    m.add(
        "sha-b",
        _ingest_record(
            "sid-b",
            ingested_at=datetime.now(UTC),
            input_tokens=300,
            output_tokens=400,
            raw_transcript_bytes=20_000,
        ),
    )
    m.save(vault)


# ─── usage ────────────────────────────────────────────────────────────────


def test_main_metrics_usage_empty(tmp_path: Path, capsys) -> None:
    rc = main(["metrics", "usage", "--vault", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "period_days: 30" in out
    assert "sessions_covered: 0" in out
    assert "tokens_input: 0" in out
    assert "compression_ratio: —" in out


def test_main_metrics_usage_with_seeded_manifest(tmp_path: Path, capsys) -> None:
    _seed_manifest(tmp_path)
    rc = main(["metrics", "usage", "--vault", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "sessions_covered: 2" in out
    assert "tokens_input: 400" in out  # 100 + 300
    assert "tokens_output: 600" in out  # 200 + 400
    assert "tokens_injected: 1000" in out


def test_main_metrics_usage_invalid_period_returns_90(
    tmp_path: Path, capsys
) -> None:
    rc = main(["metrics", "usage", "--vault", str(tmp_path), "--period", "bogus"])
    assert rc == 90
    err = capsys.readouterr().err
    assert "period" in err.lower()


def test_main_metrics_usage_corrupt_manifest_returns_93(
    tmp_path: Path, capsys
) -> None:
    (tmp_path / ".manifest.json").write_text("{not valid", encoding="utf-8")
    rc = main(["metrics", "usage", "--vault", str(tmp_path)])
    assert rc == 93
    err = capsys.readouterr().err
    assert "manifest" in err.lower()


# ─── top-sessions ─────────────────────────────────────────────────────────


def test_main_metrics_top_sessions_empty(tmp_path: Path, capsys) -> None:
    rc = main(["metrics", "top-sessions", "--vault", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "no sessions" in out


def test_main_metrics_top_sessions_sorted(tmp_path: Path, capsys) -> None:
    _seed_manifest(tmp_path)
    rc = main(
        ["metrics", "top-sessions", "--vault", str(tmp_path), "--limit", "5"]
    )
    assert rc == 0
    out = capsys.readouterr().out
    # sid-b has bigger total (300+400=700) than sid-a (100+200=300) → b first.
    pos_b = out.find("sid-b")
    pos_a = out.find("sid-a")
    assert pos_b != -1 and pos_a != -1
    assert pos_b < pos_a
    assert "total=700" in out
    assert "total=300" in out


# ─── timeline ─────────────────────────────────────────────────────────────


def test_main_metrics_timeline_prints_period_days(tmp_path: Path, capsys) -> None:
    rc = main(
        ["metrics", "timeline", "--vault", str(tmp_path), "--period", "5d"]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "5 days" in out
    # Each line should look like: <iso-date>  sessions=0 tokens_in=0 tokens_out=0
    assert out.count("sessions=0") >= 5


def test_main_metrics_timeline_invalid_period_returns_90(
    tmp_path: Path, capsys
) -> None:
    rc = main(["metrics", "timeline", "--vault", str(tmp_path), "--period", "x"])
    assert rc == 90
