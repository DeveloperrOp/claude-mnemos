"""CLI tests for `mnemos trash {list,restore,dismiss,empty}` subgroup."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx

from claude_mnemos.cli import build_parser, main

# ─── parser tests ─────────────────────────────────────────────────────────


def test_parser_trash_list() -> None:
    args = build_parser().parse_args(["trash", "list", "--project", "p"])
    assert args.command == "trash"
    assert args.trash_cmd == "list"


def test_parser_trash_restore() -> None:
    args = build_parser().parse_args(
        ["trash", "restore", "deleted-foo-x", "--project", "p"]
    )
    assert args.trash_cmd == "restore"
    assert args.trash_id == "deleted-foo-x"


def test_parser_trash_dismiss() -> None:
    args = build_parser().parse_args(
        ["trash", "dismiss", "deleted-bar-y", "--project", "p"]
    )
    assert args.trash_cmd == "dismiss"
    assert args.trash_id == "deleted-bar-y"


def test_parser_trash_empty() -> None:
    args = build_parser().parse_args(["trash", "empty", "--project", "p"])
    assert args.trash_cmd == "empty"
    assert args.yes is False


def test_parser_trash_empty_yes() -> None:
    args = build_parser().parse_args(
        ["trash", "empty", "--yes", "--project", "p"]
    )
    assert args.yes is True


# ─── helpers ──────────────────────────────────────────────────────────────


def _mock_response(status_code: int = 200, json_body: Any = None, text: str = "") -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text or (json.dumps(json_body) if json_body is not None else "")
    resp.json = MagicMock(return_value=json_body if json_body is not None else {})
    return resp


def _seed_trash_dir(
    vault: Path,
    name: str,
    *,
    original_path: str = "wiki/entities/foo.md",
    page_basename: str = "foo.md",
    deleted_at: str = "2026-04-27T12:00:00+00:00",
) -> Path:
    d = vault / ".trash" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / page_basename).write_text("# foo", encoding="utf-8")
    (d / ".reason.txt").write_text("test", encoding="utf-8")
    (d / ".metadata.json").write_text(
        json.dumps(
            {
                "version": 1,
                "trash_id": name,
                "original_path": original_path,
                "deleted_at": deleted_at,
                "operation_id": "op-1",
                "operation_type": "manual_delete",
            }
        ),
        encoding="utf-8",
    )
    return d


# ─── trash list (direct DB read) ──────────────────────────────────────────


def test_main_trash_list_empty(tmp_path: Path, capsys, register_project) -> None:
    vault = tmp_path / "v"
    register_project("p", vault)
    rc = main(["trash", "list", "--project", "p"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "no trash entries" in out


def test_main_trash_list_after_delete(
    tmp_path: Path, capsys, register_project
) -> None:
    """list reads .trash/ directly (no daemon needed)."""
    vault = tmp_path / "v"
    register_project("p", vault)
    _seed_trash_dir(vault, "deleted-foo-2026-04-27-12-00-00-aaaaaaaa")
    rc = main(["trash", "list", "--project", "p"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "deleted-foo-2026-04-27-12-00-00-aaaaaaaa" in out
    assert "wiki/entities/foo.md" in out
    assert "restorable" in out


def test_main_trash_list_unrestorable(
    tmp_path: Path, capsys, register_project
) -> None:
    """Entries without metadata are flagged blocked."""
    vault = tmp_path / "v"
    register_project("p", vault)
    d = vault / ".trash" / "deleted-bar-no-meta"
    d.mkdir(parents=True)
    (d / "bar.md").write_text("# bar", encoding="utf-8")
    rc = main(["trash", "list", "--project", "p"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "deleted-bar-no-meta" in out
    assert "blocked" in out


# ─── trash restore (via daemon REST) ──────────────────────────────────────


def test_main_trash_restore(tmp_path: Path, capsys, register_project) -> None:
    vault = tmp_path / "v"
    register_project("p", vault)
    captured: dict[str, Any] = {}

    def fake_request(method: str, url: str, **kwargs: Any) -> MagicMock:
        captured["method"] = method
        captured["url"] = url
        return _mock_response(
            200,
            {
                "success": True,
                "snapshot_path": "snap",
                "activity_id": "a1",
                "restored_path": "wiki/entities/foo.md",
            },
        )

    with patch("claude_mnemos.cli.httpx.request", side_effect=fake_request):
        rc = main(
            ["trash", "restore", "deleted-foo-x", "--project", "p"]
        )

    assert rc == 0
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/trash/deleted-foo-x/restore")


def test_main_trash_restore_collision(
    tmp_path: Path, capsys, register_project
) -> None:
    vault = tmp_path / "v"
    register_project("p", vault)

    def fake_request(*args: Any, **kwargs: Any) -> MagicMock:
        return _mock_response(409, {"error": "collision"}, text='{"error":"collision"}')

    with patch("claude_mnemos.cli.httpx.request", side_effect=fake_request):
        rc = main(
            ["trash", "restore", "deleted-foo-x", "--project", "p"]
        )

    assert rc == 89


def test_main_trash_restore_daemon_offline(
    tmp_path: Path, capsys, register_project
) -> None:
    vault = tmp_path / "v"
    register_project("p", vault)

    def fake_request(*args: Any, **kwargs: Any) -> MagicMock:
        raise httpx.ConnectError("refused")

    with patch("claude_mnemos.cli.httpx.request", side_effect=fake_request):
        rc = main(
            ["trash", "restore", "deleted-foo-x", "--project", "p"]
        )

    assert rc == 87


# ─── trash dismiss (via daemon REST) ──────────────────────────────────────


def test_main_trash_dismiss(tmp_path: Path, capsys, register_project) -> None:
    vault = tmp_path / "v"
    register_project("p", vault)
    captured: dict[str, Any] = {}

    def fake_request(method: str, url: str, **kwargs: Any) -> MagicMock:
        captured["method"] = method
        captured["url"] = url
        return _mock_response(204, text="")

    with patch("claude_mnemos.cli.httpx.request", side_effect=fake_request):
        rc = main(
            ["trash", "dismiss", "deleted-bar-y", "--project", "p"]
        )

    assert rc == 0
    assert captured["method"] == "DELETE"
    assert captured["url"].endswith("/trash/deleted-bar-y")
    out = capsys.readouterr().out
    assert "deleted-bar-y" in out


def test_main_trash_dismiss_404(tmp_path: Path, capsys, register_project) -> None:
    vault = tmp_path / "v"
    register_project("p", vault)

    def fake_request(*args: Any, **kwargs: Any) -> MagicMock:
        return _mock_response(404, {"error": "not_found"}, text='{"error":"not_found"}')

    with patch("claude_mnemos.cli.httpx.request", side_effect=fake_request):
        rc = main(
            ["trash", "dismiss", "deleted-missing", "--project", "p"]
        )

    assert rc == 88


# ─── trash empty (with confirmation) ──────────────────────────────────────


def test_main_trash_empty_with_yes_skips_prompt(
    tmp_path: Path, capsys, monkeypatch, register_project
) -> None:
    """`--yes` flag skips stdin prompt and goes straight to DELETE /trash."""
    vault = tmp_path / "v"
    register_project("p", vault)
    captured: dict[str, Any] = {}

    def fake_request(method: str, url: str, **kwargs: Any) -> MagicMock:
        captured["method"] = method
        captured["url"] = url
        return _mock_response(
            200, {"removed_count": 3, "removed_ids": ["a", "b", "c"], "errors": []}
        )

    # If we accidentally read stdin, blow up
    class _NoReadStdin:
        def readline(self) -> str:
            raise AssertionError("--yes should bypass stdin")

    monkeypatch.setattr("sys.stdin", _NoReadStdin())

    with patch("claude_mnemos.cli.httpx.request", side_effect=fake_request):
        rc = main(["trash", "empty", "--yes", "--project", "p"])

    assert rc == 0
    assert captured["method"] == "DELETE"
    assert captured["url"].endswith("/trash")


def test_main_trash_empty_typed_delete_proceeds(
    tmp_path: Path, capsys, monkeypatch, register_project
) -> None:
    """Without --yes, typing 'delete' on stdin triggers DELETE /trash."""
    vault = tmp_path / "v"
    register_project("p", vault)
    captured: dict[str, Any] = {}

    def fake_request(method: str, url: str, **kwargs: Any) -> MagicMock:
        captured["method"] = method
        captured["url"] = url
        return _mock_response(
            200, {"removed_count": 0, "removed_ids": [], "errors": []}
        )

    monkeypatch.setattr("sys.stdin", io.StringIO("delete\n"))

    with patch("claude_mnemos.cli.httpx.request", side_effect=fake_request):
        rc = main(["trash", "empty", "--project", "p"])

    assert rc == 0
    assert captured["method"] == "DELETE"
    assert captured["url"].endswith("/trash")


def test_main_trash_empty_wrong_input_aborts(
    tmp_path: Path, capsys, monkeypatch, register_project
) -> None:
    """Without --yes, anything other than 'delete' aborts (no daemon call)."""
    vault = tmp_path / "v"
    register_project("p", vault)

    def fake_request(*args: Any, **kwargs: Any) -> MagicMock:
        raise AssertionError("daemon should not be called when user aborts")

    monkeypatch.setattr("sys.stdin", io.StringIO("yes\n"))

    with patch("claude_mnemos.cli.httpx.request", side_effect=fake_request):
        rc = main(["trash", "empty", "--project", "p"])

    assert rc == 1
    err = capsys.readouterr().err
    assert "abort" in err.lower() or "confirmation" in err.lower()
