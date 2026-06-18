from pathlib import Path

from claude_mnemos.core.vault_stats import count_md, vault_size


def test_count_md_counts_md_recursively(tmp_path: Path):
    (tmp_path / "a.md").write_text("hi", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.md").write_text("yo", encoding="utf-8")
    (tmp_path / "c.txt").write_text("x", encoding="utf-8")
    assert count_md(tmp_path) == 2


def test_count_md_missing_dir_returns_zero(tmp_path: Path):
    assert count_md(tmp_path / "does-not-exist") == 0


def test_vault_size_sums_bytes(tmp_path: Path):
    (tmp_path / "a.md").write_text("hello", encoding="utf-8")
    assert vault_size(tmp_path) >= 5


def test_vault_size_missing_dir_returns_zero(tmp_path: Path):
    assert vault_size(tmp_path / "does-not-exist") == 0
