"""Smoke test for the PyInstaller bundle.

This test does NOT run with the default pytest invocation — it requires
the bundle to exist at ./dist/claude-mnemos/claude-mnemos.exe. CI invokes
it explicitly after building. Skipped otherwise.
"""

import os
import subprocess
from pathlib import Path

import pytest

BUNDLE = Path("dist/claude-mnemos/claude-mnemos.exe")
if os.name != "nt":
    BUNDLE = Path("dist/claude-mnemos/claude-mnemos")


@pytest.mark.skipif(not BUNDLE.exists(), reason="PyInstaller bundle not built")
def test_bundle_doctor_runs() -> None:
    """The bundled exe must run `doctor` and exit (0 or 1) within 10s."""
    # Belt-and-suspenders: as of cli.py main() postinstall is gated to `tray
    # run` only, so `doctor` would not trigger init anyway — but we set the
    # env var explicitly to make this test bulletproof against a regression.
    env = os.environ.copy()
    env["MNEMOS_SKIP_POSTINSTALL"] = "1"
    proc = subprocess.run(
        [str(BUNDLE), "doctor"],
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )
    assert proc.returncode in (0, 1), f"unexpected rc={proc.returncode}; stderr={proc.stderr}"
    assert "claude_cli" in proc.stdout
    assert "hooks" in proc.stdout
