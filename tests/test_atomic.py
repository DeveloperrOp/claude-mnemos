import os
from pathlib import Path
from unittest.mock import patch

import pytest

from claude_mnemos.core.atomic import FileBusyError, atomic_write


def test_atomic_write_creates_new_file(tmp_path: Path):
    target = tmp_path / "page.md"
    atomic_write(target, "hello world")
    assert target.read_text(encoding="utf-8") == "hello world"


def test_atomic_write_overwrites(tmp_path: Path):
    target = tmp_path / "page.md"
    target.write_text("old", encoding="utf-8")
    atomic_write(target, "new")
    assert target.read_text(encoding="utf-8") == "new"


def test_atomic_write_no_partial_file_on_crash(tmp_path: Path, monkeypatch):
    target = tmp_path / "page.md"
    target.write_text("old content", encoding="utf-8")

    def boom(*args, **kwargs):
        raise RuntimeError("simulated crash mid-write")

    monkeypatch.setattr("os.replace", boom)
    with pytest.raises(RuntimeError):
        atomic_write(target, "new content")

    # Старый файл цел; никаких .tmp-обломков
    assert target.read_text(encoding="utf-8") == "old content"
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == []


def test_atomic_write_retries_on_permission_error(tmp_path: Path):
    target = tmp_path / "page.md"
    real_replace = os.replace
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError("locked by AV")
        return real_replace(src, dst)

    with patch("claude_mnemos.core.atomic.os.replace", side_effect=flaky):
        atomic_write(target, "ok", retry_base_delay=0.0)

    assert calls["n"] == 3
    assert target.read_text(encoding="utf-8") == "ok"


def test_atomic_write_raises_after_max_attempts(tmp_path: Path):
    target = tmp_path / "page.md"

    def always_fail(src, dst):
        raise PermissionError("always locked")

    with (
        patch("claude_mnemos.core.atomic.os.replace", side_effect=always_fail),
        pytest.raises(FileBusyError),
    ):
        atomic_write(target, "x", max_attempts=3, retry_base_delay=0.0)
