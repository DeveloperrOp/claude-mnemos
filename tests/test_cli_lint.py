from pathlib import Path

from claude_mnemos.cli import build_parser, main


def _seed(vault: Path, rel: str, body: str = "body\n") -> None:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "---\n"
        "title: T\n"
        "type: entity\n"
        "created: 2026-04-26\n"
        "updated: 2026-04-26\n"
        "agent_written: true\n"
        "---\n" + body,
        encoding="utf-8",
    )


# ─── parser ────────────────────────────────────────────────────────────────


def test_parser_lint_run():
    args = build_parser().parse_args(["lint", "run", "--project", "p"])
    assert args.command == "lint"
    assert args.lint_cmd == "run"
    assert args.project == "p"


def test_parser_lint_results():
    args = build_parser().parse_args(
        ["lint", "results", "--project", "p", "--severity", "warning"]
    )
    assert args.lint_cmd == "results"
    assert args.severity == "warning"


def test_parser_lint_autofix_dry_run():
    args = build_parser().parse_args(
        ["lint", "autofix", "--project", "p", "--dry-run"]
    )
    assert args.lint_cmd == "autofix"
    assert args.dry_run is True


# ─── execution ─────────────────────────────────────────────────────────────


def test_main_lint_run(tmp_path: Path, capsys, register_project):
    vault = tmp_path / "v"
    register_project("p", vault)
    _seed(vault, "wiki/entities/foo.md")
    rc = main(["lint", "run", "--project", "p"])
    assert rc == 0
    out = capsys.readouterr().out.lower()
    assert "findings" in out
    assert (vault / ".lint-results.json").is_file()


def test_main_lint_results_no_run(tmp_path: Path, capsys, register_project):
    vault = tmp_path / "v"
    register_project("p", vault)
    rc = main(["lint", "results", "--project", "p"])
    assert rc == 0
    assert "no lint run yet" in capsys.readouterr().out.lower()


def test_main_lint_autofix_dry_run(tmp_path: Path, capsys, register_project):
    vault = tmp_path / "v"
    register_project("p", vault)
    _seed(vault, "wiki/entities/foo.md", body="x  \n")
    main(["lint", "run", "--project", "p"])
    capsys.readouterr()  # drain
    rc = main(["lint", "autofix", "--project", "p", "--dry-run"])
    assert rc == 0
    assert "would fix" in capsys.readouterr().out.lower()
    assert "x  " in (vault / "wiki/entities/foo.md").read_text(encoding="utf-8")


def test_main_lint_autofix_applies(tmp_path: Path, register_project):
    vault = tmp_path / "v"
    register_project("p", vault)
    _seed(vault, "wiki/entities/foo.md", body="x  \n")
    main(["lint", "run", "--project", "p"])
    rc = main(["lint", "autofix", "--project", "p"])
    assert rc == 0
    assert "x  " not in (vault / "wiki/entities/foo.md").read_text(encoding="utf-8")
