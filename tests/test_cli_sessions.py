"""CLI tests for `mnemos sessions {list,show,ingest}` subgroup (Plan #13a Task 9)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx

from claude_mnemos.cli import build_parser, main
from claude_mnemos.state.manifest import IngestRecord, Manifest

# ─── parser tests ─────────────────────────────────────────────────────────


def test_parser_sessions_list() -> None:
    args = build_parser().parse_args(
        ["sessions", "list", "--project", "p", "--status", "queued", "--limit", "5"]
    )
    assert args.command == "sessions"
    assert args.sessions_cmd == "list"
    assert args.status == "queued"
    assert args.limit == 5


def test_parser_sessions_show() -> None:
    args = build_parser().parse_args(
        ["sessions", "show", "abc-sid", "--project", "p"]
    )
    assert args.sessions_cmd == "show"
    assert args.session_id == "abc-sid"


def test_parser_sessions_ingest(tmp_path: Path) -> None:
    transcript = tmp_path / "abc.jsonl"
    transcript.write_text("{}\n", encoding="utf-8")
    args = build_parser().parse_args(
        ["sessions", "ingest", str(transcript), "--project", "p"]
    )
    assert args.sessions_cmd == "ingest"
    assert Path(args.transcript_path) == transcript


# ─── helpers ──────────────────────────────────────────────────────────────


def _ingest_record(
    sid: str,
    *,
    ingested_at: datetime,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
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
        raw_transcript_bytes=None,
    )


def _mock_response(status_code: int = 200, json_body: Any = None, text: str = "") -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text or (json.dumps(json_body) if json_body is not None else "")
    resp.json = MagicMock(return_value=json_body if json_body is not None else {})
    return resp


# ─── direct-read: sessions list ───────────────────────────────────────────


def test_main_sessions_list_empty(
    tmp_path: Path, capsys, register_project
) -> None:
    vault = tmp_path / "v"
    register_project("p", vault)
    rc = main(["sessions", "list", "--project", "p"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "no sessions" in out.lower()


def test_main_sessions_list_with_seeded_manifest(
    tmp_path: Path, capsys, register_project
) -> None:
    vault = tmp_path / "v"
    register_project("p", vault)
    m = Manifest()
    m.add(
        "sha-1",
        _ingest_record(
            "alpha-sid",
            ingested_at=datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC),
            input_tokens=100,
            output_tokens=200,
        ),
    )
    m.save(vault)

    rc = main(["sessions", "list", "--project", "p"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "alpha-sid" in out
    assert "succeeded" in out


def test_main_sessions_show_existing(
    tmp_path: Path, capsys, register_project
) -> None:
    vault = tmp_path / "v"
    register_project("p", vault)
    m = Manifest()
    m.add(
        "sha-1",
        _ingest_record(
            "real-sid",
            ingested_at=datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC),
        ),
    )
    m.save(vault)

    rc = main(["sessions", "show", "real-sid", "--project", "p"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "real-sid" in out


def test_main_sessions_show_missing_returns_91(
    tmp_path: Path, capsys, register_project
) -> None:
    vault = tmp_path / "v"
    register_project("p", vault)
    rc = main(["sessions", "show", "missing-sid", "--project", "p"])
    assert rc == 91
    err = capsys.readouterr().err
    assert "missing-sid" in err


def test_main_sessions_corrupt_manifest_returns_93(
    tmp_path: Path, capsys, register_project
) -> None:
    vault = tmp_path / "v"
    register_project("p", vault)
    (vault / ".manifest.json").write_text("{not valid", encoding="utf-8")
    rc = main(["sessions", "list", "--project", "p"])
    assert rc == 93
    err = capsys.readouterr().err
    assert "manifest" in err.lower()


# ─── ingest (via daemon REST) ─────────────────────────────────────────────


def test_main_sessions_ingest_posts_to_daemon(
    tmp_path: Path, capsys, register_project
) -> None:
    vault = tmp_path / "v"
    register_project("p", vault)
    transcript = tmp_path / "my-session.jsonl"
    transcript.write_text("{}\n", encoding="utf-8")
    captured: dict[str, Any] = {}

    def fake_request(method: str, url: str, **kwargs: Any) -> MagicMock:
        captured["method"] = method
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return _mock_response(201, {"id": "job-123", "status": "queued"})

    with patch("claude_mnemos.cli.httpx.request", side_effect=fake_request):
        rc = main(
            ["sessions", "ingest", str(transcript), "--project", "p"]
        )

    assert rc == 0
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/sessions/my-session/ingest")
    body = captured["json"]
    assert isinstance(body, dict)
    assert body["transcript_path"] == str(transcript.resolve())


def test_main_sessions_ingest_daemon_offline_returns_87(
    tmp_path: Path, capsys, register_project
) -> None:
    vault = tmp_path / "v"
    register_project("p", vault)
    transcript = tmp_path / "x.jsonl"
    transcript.write_text("{}\n", encoding="utf-8")

    def fake_request(*args: Any, **kwargs: Any) -> MagicMock:
        raise httpx.ConnectError("refused")

    with patch("claude_mnemos.cli.httpx.request", side_effect=fake_request):
        rc = main(
            ["sessions", "ingest", str(transcript), "--project", "p"]
        )

    assert rc == 87
