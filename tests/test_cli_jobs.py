from pathlib import Path

from claude_mnemos.cli import build_parser, main


def test_parser_jobs_list(tmp_path: Path):
    args = build_parser().parse_args(["jobs", "list", "--vault", str(tmp_path)])
    assert args.command == "jobs"
    assert args.jobs_cmd == "list"


def test_parser_jobs_show(tmp_path: Path):
    args = build_parser().parse_args(
        ["jobs", "show", "abc", "--vault", str(tmp_path)]
    )
    assert args.jobs_cmd == "show"
    assert args.job_id == "abc"


def test_parser_jobs_cancel(tmp_path: Path):
    args = build_parser().parse_args(
        ["jobs", "cancel", "abc", "--vault", str(tmp_path)]
    )
    assert args.jobs_cmd == "cancel"


def test_main_jobs_list_empty(tmp_path: Path, capsys):
    rc = main(["jobs", "list", "--vault", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "0 jobs" in out or "no jobs" in out.lower()


def test_main_jobs_list_after_create(tmp_path: Path, capsys):
    from claude_mnemos.state.jobs import JOBS_DB_FILENAME, JobStore

    with JobStore(tmp_path / JOBS_DB_FILENAME) as store:
        store.create(kind="ingest", payload={"transcript_path": "/x"})
    rc = main(["jobs", "list", "--vault", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "queued" in out


def test_main_jobs_show_404(tmp_path: Path, capsys):
    rc = main(["jobs", "show", "nonexistent", "--vault", str(tmp_path)])
    assert rc == 86
    err = capsys.readouterr().err
    assert "not found" in err.lower()
