import sys
from pathlib import Path

import pytest

from claude_mnemos.tray.single_instance import get_single_instance


def test_acquire_returns_true_first_time(tmp_path):
    si = get_single_instance("com.yarik.claude-mnemos.test1", lock_dir=tmp_path)
    try:
        assert si.acquire() is True
    finally:
        si.release()


def test_second_acquire_returns_false(tmp_path):
    a = get_single_instance("com.yarik.claude-mnemos.test2", lock_dir=tmp_path)
    b = get_single_instance("com.yarik.claude-mnemos.test2", lock_dir=tmp_path)
    try:
        assert a.acquire() is True
        assert b.acquire() is False
    finally:
        a.release()
        b.release()


def test_release_allows_reacquire(tmp_path):
    a = get_single_instance("com.yarik.claude-mnemos.test3", lock_dir=tmp_path)
    b = get_single_instance("com.yarik.claude-mnemos.test3", lock_dir=tmp_path)
    assert a.acquire() is True
    a.release()
    try:
        assert b.acquire() is True
    finally:
        b.release()


def test_factory_picks_correct_backend():
    si = get_single_instance("dummy", lock_dir=Path("."))
    if sys.platform == "win32":
        assert type(si).__name__ == "WindowsSingleInstance"
    else:
        assert type(si).__name__ == "PosixSingleInstance"
