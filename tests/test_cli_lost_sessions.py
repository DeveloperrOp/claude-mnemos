"""CLI tests for `mnemos lost-sessions {list,scan,import,ignore}` (Plan #13a Task 10)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx

from claude_mnemos.cli import build_parser, main

# ─── parser tests ─────────────────────────────────────────────────────────


def test_parser_lost_sessions_list() -> None:
    args = build_parser().parse_args(
        ["lost-sessions", "list", "--project", "p"]
    )
    assert args.command == "lost-sessions"
    assert args.lost_cmd == "list"


def test_parser_lost_sessions_scan() -> None:
    args = build_parser().parse_args(
        ["lost-sessions", "scan", "--project", "p"]
    )
    assert args.lost_cmd == "scan"


def test_parser_lost_sessions_import() -> None:
    args = build_parser().parse_args(
        ["lost-sessions", "import", "abc-sid", "--project", "p"]
    )
    assert args.lost_cmd == "import"
    assert args.session_id == "abc-sid"


def test_parser_lost_sessions_ignore_with_reason() -> None:
    args = build_parser().parse_args(
        [
            "lost-sessions",
            "ignore",
            "xyz-sid",
            "--project",
            "p",
            "--reason",
            "test data",
        ]
    )
    assert args.lost_cmd == "ignore"
    assert args.session_id == "xyz-sid"
    assert args.reason == "test data"


# ─── helpers ──────────────────────────────────────────────────────────────


def _mock_response(status_code: int = 200, json_body: Any = None, text: str = "") -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text or (json.dumps(json_body) if json_body is not None else "")
    resp.json = MagicMock(return_value=json_body if json_body is not None else {})
    return resp


def _seed_transcript(root: Path, project: str, name: str, content: bytes) -> tuple[Path, str]:
    proj = root / project
    proj.mkdir(parents=True, exist_ok=True)
    path = proj / f"{name}.jsonl"
    path.write_bytes(content)
    sha = hashlib.sha256(content).hexdigest()
    return path, sha


# ─── direct-read: list ────────────────────────────────────────────────────


def test_main_lost_sessions_list_empty(
    tmp_path: Path, capsys, monkeypatch, register_project
) -> None:
    vault = tmp_path / "v"
    register_project("p", vault)
    transcripts_root = tmp_path / "transcripts"
    transcripts_root.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(transcripts_root))

    rc = main(["lost-sessions", "list", "--project", "p"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "no lost sessions" in out


def test_main_lost_sessions_list_with_lost(
    tmp_path: Path, capsys, monkeypatch, register_project
) -> None:
    vault = tmp_path / "v"
    register_project("p", vault)
    transcripts_root = tmp_path / "transcripts"
    transcripts_root.mkdir()
    _, _sha = _seed_transcript(transcripts_root, "proj-a", "lonely-sid", b"alpha\n")
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(transcripts_root))

    rc = main(["lost-sessions", "list", "--project", "p"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "lonely-sid" in out
    assert "1 lost sessions" in out


def test_main_lost_sessions_list_corrupt_manifest_returns_93(
    tmp_path: Path, capsys, monkeypatch, register_project
) -> None:
    vault = tmp_path / "v"
    register_project("p", vault)
    transcripts_root = tmp_path / "transcripts"
    transcripts_root.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(transcripts_root))
    (vault / ".manifest.json").write_text("{not valid", encoding="utf-8")
    rc = main(["lost-sessions", "list", "--project", "p"])
    assert rc == 93
    err = capsys.readouterr().err
    assert "manifest" in err.lower()


# ─── scan (via daemon) ────────────────────────────────────────────────────


def test_main_lost_sessions_scan_posts_to_daemon(
    tmp_path: Path, capsys, register_project
) -> None:
    vault = tmp_path / "v"
    register_project("p", vault)
    captured: dict[str, Any] = {}

    def fake_request(method: str, url: str, **kwargs: Any) -> MagicMock:
        captured["method"] = method
        captured["url"] = url
        return _mock_response(200, {"sessions": [], "total": 0})

    with patch("claude_mnemos.cli.httpx.request", side_effect=fake_request):
        rc = main(["lost-sessions", "scan", "--project", "p"])

    assert rc == 0
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/lost-sessions/scan")


def test_main_lost_sessions_scan_daemon_offline_returns_87(
    tmp_path: Path, capsys, register_project
) -> None:
    vault = tmp_path / "v"
    register_project("p", vault)

    def fake_request(*args: Any, **kwargs: Any) -> MagicMock:
        raise httpx.ConnectError("refused")

    with patch("claude_mnemos.cli.httpx.request", side_effect=fake_request):
        rc = main(["lost-sessions", "scan", "--project", "p"])

    assert rc == 87


# ─── import (via daemon) ──────────────────────────────────────────────────


def test_main_lost_sessions_import_posts_to_daemon(
    tmp_path: Path, capsys, register_project
) -> None:
    vault = tmp_path / "v"
    register_project("p", vault)
    captured: dict[str, Any] = {}

    def fake_request(method: str, url: str, **kwargs: Any) -> MagicMock:
        captured["method"] = method
        captured["url"] = url
        return _mock_response(201, {"id": "job-99", "status": "queued"})

    with patch("claude_mnemos.cli.httpx.request", side_effect=fake_request):
        rc = main(
            ["lost-sessions", "import", "lonely-sid", "--project", "p"]
        )

    assert rc == 0
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/lost-sessions/lonely-sid/import")


def test_main_lost_sessions_import_404_returns_92(
    tmp_path: Path, capsys, register_project
) -> None:
    vault = tmp_path / "v"
    register_project("p", vault)

    def fake_request(*args: Any, **kwargs: Any) -> MagicMock:
        return _mock_response(
            404,
            {"error": "lost_session_not_found"},
            text='{"error":"lost_session_not_found"}',
        )

    with patch("claude_mnemos.cli.httpx.request", side_effect=fake_request):
        rc = main(
            ["lost-sessions", "import", "ghost-sid", "--project", "p"]
        )

    assert rc == 92
    err = capsys.readouterr().err
    assert "ghost-sid" in err


# ─── ignore (via daemon) ──────────────────────────────────────────────────


def test_main_lost_sessions_ignore_posts_to_daemon(
    tmp_path: Path, capsys, register_project
) -> None:
    vault = tmp_path / "v"
    register_project("p", vault)
    captured: dict[str, Any] = {}

    def fake_request(method: str, url: str, **kwargs: Any) -> MagicMock:
        captured["method"] = method
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return _mock_response(200, {"ignored_count": 1})

    with patch("claude_mnemos.cli.httpx.request", side_effect=fake_request):
        rc = main(
            [
                "lost-sessions",
                "ignore",
                "lonely-sid",
                "--project",
                "p",
                "--reason",
                "noise",
            ]
        )

    assert rc == 0
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/lost-sessions/lonely-sid/ignore")
    body = captured["json"]
    assert isinstance(body, dict)
    assert body.get("reason") == "noise"


def test_main_lost_sessions_ignore_404_returns_92(
    tmp_path: Path, capsys, register_project
) -> None:
    vault = tmp_path / "v"
    register_project("p", vault)

    def fake_request(*args: Any, **kwargs: Any) -> MagicMock:
        return _mock_response(
            404,
            {"error": "lost_session_not_found"},
            text='{"error":"lost_session_not_found"}',
        )

    with patch("claude_mnemos.cli.httpx.request", side_effect=fake_request):
        rc = main(
            ["lost-sessions", "ignore", "ghost-sid", "--project", "p"]
        )

    assert rc == 92
