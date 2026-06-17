"""windowless_creationflags(): CREATE_NO_WINDOW on Windows, 0 elsewhere.

Regression (2026-06-17): the windowed desktop exe shelled out to the
``claude`` CLI / ``git`` without CREATE_NO_WINDOW, so every probe flashed a
conhost window that lingered on screen.
"""

from __future__ import annotations

import subprocess

import pytest

from claude_mnemos import runtime


def test_windowless_flags_on_win32(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runtime.sys, "platform", "win32")
    assert runtime.windowless_creationflags() == subprocess.CREATE_NO_WINDOW


@pytest.mark.parametrize("plat", ["linux", "darwin"])
def test_windowless_flags_zero_off_win32(
    plat: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runtime.sys, "platform", plat)
    assert runtime.windowless_creationflags() == 0
