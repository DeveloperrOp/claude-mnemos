"""CLI tests for `mnemos page {edit,verify,archive,delete}` subgroup."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx

from claude_mnemos.cli import build_parser, main

# ─── parser tests ─────────────────────────────────────────────────────────


def test_parser_page_edit() -> None:
    args = build_parser().parse_args(
        [
            "page",
            "edit",
            "wiki/entities/foo",
            "--project",
            "p",
            "--frontmatter",
            '{"status": "verified"}',
        ]
    )
    assert args.command == "page"
    assert args.page_cmd == "edit"
    assert args.page_ref == "wiki/entities/foo"
    assert args.frontmatter == '{"status": "verified"}'
    assert args.body_file is None


def test_parser_page_edit_with_body_file(tmp_path: Path) -> None:
    body = tmp_path / "new_body.md"
    body.write_text("new body", encoding="utf-8")
    args = build_parser().parse_args(
        [
            "page",
            "edit",
            "foo",
            "--project",
            "p",
            "--body-file",
            str(body),
        ]
    )
    assert args.page_cmd == "edit"
    assert args.body_file == body


def test_parser_page_verify() -> None:
    args = build_parser().parse_args(
        ["page", "verify", "foo", "--project", "p"]
    )
    assert args.page_cmd == "verify"
    assert args.page_ref == "foo"


def test_parser_page_archive() -> None:
    args = build_parser().parse_args(
        ["page", "archive", "foo", "--project", "p"]
    )
    assert args.page_cmd == "archive"


def test_parser_page_delete() -> None:
    args = build_parser().parse_args(
        ["page", "delete", "foo", "--project", "p"]
    )
    assert args.page_cmd == "delete"


# ─── main dispatch tests with mocked httpx ────────────────────────────────


def _mock_response(status_code: int = 200, json_body: Any = None, text: str = "") -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text or (json.dumps(json_body) if json_body is not None else "")
    resp.json = MagicMock(return_value=json_body if json_body is not None else {})
    return resp


def test_main_page_edit_with_frontmatter_json(
    tmp_path: Path, capsys, register_project
) -> None:
    """`--frontmatter '{"status": "verified"}'` parses JSON and PATCHes daemon."""
    vault = tmp_path / "v"
    register_project("p", vault)
    captured: dict[str, Any] = {}

    def fake_request(method: str, url: str, **kwargs: Any) -> MagicMock:
        captured["method"] = method
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return _mock_response(
            200, {"success": True, "snapshot_path": "snap", "activity_id": "a1"}
        )

    with patch("claude_mnemos.cli.httpx.request", side_effect=fake_request):
        rc = main(
            [
                "page",
                "edit",
                "wiki/entities/foo",
                "--project",
                "p",
                "--frontmatter",
                '{"status": "verified"}',
            ]
        )

    assert rc == 0
    assert captured["method"] == "PATCH"
    assert captured["url"].endswith("/pages/wiki/entities/foo")
    assert captured["json"] == {"frontmatter": {"status": "verified"}, "body": None}


def test_main_page_edit_with_body_file(
    tmp_path: Path, capsys, register_project
) -> None:
    """`--body-file` reads content from disk and includes in PATCH body."""
    vault = tmp_path / "v"
    register_project("p", vault)
    body = tmp_path / "new.md"
    body.write_text("hello body\n", encoding="utf-8")

    captured: dict[str, Any] = {}

    def fake_request(method: str, url: str, **kwargs: Any) -> MagicMock:
        captured["json"] = kwargs.get("json")
        return _mock_response(200, {"success": True, "activity_id": "a1"})

    with patch("claude_mnemos.cli.httpx.request", side_effect=fake_request):
        rc = main(
            [
                "page",
                "edit",
                "foo",
                "--project",
                "p",
                "--body-file",
                str(body),
            ]
        )

    assert rc == 0
    assert captured["json"] == {"frontmatter": None, "body": "hello body\n"}


def test_main_page_edit_invalid_frontmatter_json(
    tmp_path: Path, capsys, register_project
) -> None:
    """Bad JSON in --frontmatter exits with rc=90 (validation)."""
    vault = tmp_path / "v"
    register_project("p", vault)
    rc = main(
        [
            "page",
            "edit",
            "foo",
            "--project",
            "p",
            "--frontmatter",
            "not json",
        ]
    )
    assert rc == 90
    assert "frontmatter" in capsys.readouterr().err.lower()


def test_main_page_verify(tmp_path: Path, capsys, register_project) -> None:
    vault = tmp_path / "v"
    register_project("p", vault)
    captured: dict[str, Any] = {}

    def fake_request(method: str, url: str, **kwargs: Any) -> MagicMock:
        captured["method"] = method
        captured["url"] = url
        return _mock_response(200, {"success": True, "activity_id": "a1"})

    with patch("claude_mnemos.cli.httpx.request", side_effect=fake_request):
        rc = main(["page", "verify", "foo", "--project", "p"])

    assert rc == 0
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/pages/foo/verify")


def test_main_page_archive(tmp_path: Path, capsys, register_project) -> None:
    vault = tmp_path / "v"
    register_project("p", vault)
    captured: dict[str, Any] = {}

    def fake_request(method: str, url: str, **kwargs: Any) -> MagicMock:
        captured["url"] = url
        return _mock_response(200, {"success": True, "activity_id": "a2"})

    with patch("claude_mnemos.cli.httpx.request", side_effect=fake_request):
        rc = main(["page", "archive", "foo", "--project", "p"])

    assert rc == 0
    assert captured["url"].endswith("/pages/foo/archive")


def test_main_page_delete(tmp_path: Path, capsys, register_project) -> None:
    vault = tmp_path / "v"
    register_project("p", vault)
    captured: dict[str, Any] = {}

    def fake_request(method: str, url: str, **kwargs: Any) -> MagicMock:
        captured["method"] = method
        captured["url"] = url
        return _mock_response(
            200, {"success": True, "trash_id": "deleted-foo-x", "activity_id": "a3"}
        )

    with patch("claude_mnemos.cli.httpx.request", side_effect=fake_request):
        rc = main(["page", "delete", "foo", "--project", "p"])

    assert rc == 0
    assert captured["method"] == "DELETE"
    assert captured["url"].endswith("/pages/foo")
    out = capsys.readouterr().out
    assert "deleted-foo-x" in out


def test_main_page_daemon_offline(tmp_path: Path, capsys, register_project) -> None:
    """If daemon unreachable, exit 87."""
    vault = tmp_path / "v"
    register_project("p", vault)

    def fake_request(*args: Any, **kwargs: Any) -> MagicMock:
        raise httpx.ConnectError("connection refused")

    with patch("claude_mnemos.cli.httpx.request", side_effect=fake_request):
        rc = main(["page", "verify", "foo", "--project", "p"])

    assert rc == 87
    err = capsys.readouterr().err
    assert "daemon" in err.lower()


def test_main_page_404_pageref(tmp_path: Path, capsys, register_project) -> None:
    """If daemon returns 404, exit 88 (PageRefError)."""
    vault = tmp_path / "v"
    register_project("p", vault)

    def fake_request(*args: Any, **kwargs: Any) -> MagicMock:
        return _mock_response(404, {"error": "not_found"}, text='{"error":"not_found"}')

    with patch("claude_mnemos.cli.httpx.request", side_effect=fake_request):
        rc = main(["page", "verify", "nope", "--project", "p"])

    assert rc == 88


def test_main_page_422_validation(tmp_path: Path, capsys, register_project) -> None:
    """If daemon returns 422, exit 90 (ValidationError)."""
    vault = tmp_path / "v"
    register_project("p", vault)

    def fake_request(*args: Any, **kwargs: Any) -> MagicMock:
        return _mock_response(422, {"error": "invalid"}, text='{"error":"invalid"}')

    with patch("claude_mnemos.cli.httpx.request", side_effect=fake_request):
        rc = main(
            [
                "page",
                "edit",
                "foo",
                "--project",
                "p",
                "--frontmatter",
                '{"status": "weird"}',
            ]
        )

    assert rc == 90
