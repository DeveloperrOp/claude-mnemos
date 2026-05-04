import sys
from pathlib import Path

import pytest


def test_is_frozen_false_in_normal_python(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    from claude_mnemos.runtime import is_frozen
    assert is_frozen() is False


def test_is_frozen_true_when_meipass_set(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    from claude_mnemos.runtime import is_frozen
    assert is_frozen() is True


def test_bundle_root_returns_meipass_when_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    from claude_mnemos.runtime import bundle_root
    assert bundle_root() == tmp_path


def test_bundle_root_returns_package_dir_in_source_mode(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    from claude_mnemos.runtime import bundle_root
    import claude_mnemos
    assert bundle_root() == Path(claude_mnemos.__file__).resolve().parent.parent


def test_static_dir_inside_bundle_when_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    (tmp_path / "claude_mnemos" / "daemon" / "static").mkdir(parents=True)
    from claude_mnemos.runtime import static_dir
    assert static_dir() == tmp_path / "claude_mnemos" / "daemon" / "static"


def test_executable_path_returns_sys_executable_when_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    fake_exe = tmp_path / "claude-mnemos.exe"
    fake_exe.touch()
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    from claude_mnemos.runtime import executable_path
    assert executable_path() == fake_exe
