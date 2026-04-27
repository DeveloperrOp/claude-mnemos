from pathlib import Path

from claude_mnemos.cli import build_parser, main


def test_parser_jobs_list():
    args = build_parser().parse_args(["jobs", "list", "--project", "p"])
    assert args.command == "jobs"
    assert args.jobs_cmd == "list"
    assert args.project == "p"


def test_parser_jobs_show():
    args = build_parser().parse_args(
        ["jobs", "show", "abc", "--project", "p"]
    )
    assert args.jobs_cmd == "show"
    assert args.job_id == "abc"


def test_parser_jobs_cancel():
    args = build_parser().parse_args(
        ["jobs", "cancel", "abc", "--project", "p"]
    )
    assert args.jobs_cmd == "cancel"


def test_main_jobs_list_empty(tmp_path: Path, capsys, register_project):
    vault = tmp_path / "v"
    register_project("p", vault)
    rc = main(["jobs", "list", "--project", "p"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "0 jobs" in out or "no jobs" in out.lower()


def test_main_jobs_list_after_create(tmp_path: Path, capsys, register_project):
    from claude_mnemos.state.jobs import JOBS_DB_FILENAME, JobStore

    vault = tmp_path / "v"
    register_project("p", vault)
    with JobStore(vault / JOBS_DB_FILENAME) as store:
        store.create(kind="ingest", payload={"transcript_path": "/x"})
    rc = main(["jobs", "list", "--project", "p"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "queued" in out


def test_main_jobs_show_404(tmp_path: Path, capsys, register_project):
    vault = tmp_path / "v"
    register_project("p", vault)
    rc = main(["jobs", "show", "nonexistent", "--project", "p"])
    assert rc == 86
    err = capsys.readouterr().err
    assert "not found" in err.lower()
