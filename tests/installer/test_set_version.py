"""installer/set_version.py — stamps the git-tag version into every artifact.

Tests run against COPIES OF THE REAL FILES so the regexes are proven against
actual repo content, not synthetic fixtures.
"""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

_spec = importlib.util.spec_from_file_location(
    "set_version", REPO / "installer" / "set_version.py"
)
assert _spec is not None and _spec.loader is not None
set_version = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(set_version)

STAMPED_FILES = (
    "claude_mnemos/__init__.py",
    "pyproject.toml",
    "installer/windows/mnemos.iss",
    "installer/macos/setup.py",
    ".claude-plugin/plugin.json",
)


@pytest.fixture()
def repo_copy(tmp_path: Path) -> Path:
    for rel in STAMPED_FILES:
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, dst)
    return tmp_path


def test_stamp_rewrites_all_version_sites(repo_copy: Path) -> None:
    set_version.stamp(repo_copy, "1.2.3")

    enc = {"encoding": "utf-8"}
    assert '__version__ = "1.2.3"' in (repo_copy / "claude_mnemos/__init__.py").read_text(**enc)
    assert 'version = "1.2.3"' in (repo_copy / "pyproject.toml").read_text(**enc)
    iss = (repo_copy / "installer/windows/mnemos.iss").read_text(**enc)
    assert '#define MyAppVersion "1.2.3"' in iss
    mac = (repo_copy / "installer/macos/setup.py").read_text(**enc)
    assert '"CFBundleVersion": "1.2.3"' in mac
    assert '"CFBundleShortVersionString": "1.2.3"' in mac
    assert '"version": "1.2.3"' in (repo_copy / ".claude-plugin/plugin.json").read_text(**enc)


def test_stamp_writes_windows_version_resource(repo_copy: Path) -> None:
    set_version.stamp(repo_copy, "1.2.3")

    res = (repo_copy / "installer/pyinstaller/version_info.txt").read_text(encoding="utf-8")
    assert "filevers=(1, 2, 3, 0)" in res
    assert "FileVersion" in res and "1.2.3.0" in res
    assert "claude-mnemos" in res


def test_stamp_rejects_garbage_version(repo_copy: Path) -> None:
    with pytest.raises(ValueError):
        set_version.stamp(repo_copy, "main")
    with pytest.raises(ValueError):
        set_version.stamp(repo_copy, "1.2.3; rm -rf /")


def test_stamp_fails_loudly_when_pattern_missing(repo_copy: Path) -> None:
    """A refactor that moves a version site must break the stamp, not skip it."""
    (repo_copy / "claude_mnemos/__init__.py").write_text("# no version here\n")
    with pytest.raises(RuntimeError, match="__init__"):
        set_version.stamp(repo_copy, "1.2.3")


def test_repo_init_carries_stampable_version() -> None:
    """The site must stay in the regex-matched shape stamp() expects.

    Not pinned to the literal 0.0.1 placeholder: on CI tag builds this test
    runs AFTER the stamp step, when the file already carries the tag.
    """
    import re

    text = (REPO / "claude_mnemos/__init__.py").read_text(encoding="utf-8")
    assert re.search(r'__version__ = "\d+\.\d+\.\d+"', text)
