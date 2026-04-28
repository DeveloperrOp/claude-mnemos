from __future__ import annotations

import json
from pathlib import Path

from claude_mnemos.daemon.runtime_state import DaemonRuntimeState


def test_load_legacy_alpha_file_with_vault_root(tmp_path: Path) -> None:
    """α users have ~/.claude-mnemos/daemon.config.json with vault_root.
    β1 ignores the field silently (extra='ignore')."""
    p = tmp_path / "daemon.config.json"
    p.write_text(json.dumps({
        "vault_root": "/some/old/path",
        "host": "127.0.0.1",
        "port": 5757,
        "pid_file": "/x/daemon.pid",
    }))
    state = DaemonRuntimeState.load(p)
    assert state is not None
    assert state.host == "127.0.0.1"
    assert state.port == 5757
    assert state.pid_file == Path("/x/daemon.pid")
    assert not hasattr(state, "vault_root")


def test_save_does_not_emit_vault_root(tmp_path: Path) -> None:
    p = tmp_path / "daemon.config.json"
    DaemonRuntimeState(host="127.0.0.1", port=5757, pid_file=Path("/x/p")).save(p)
    data = json.loads(p.read_text())
    assert "vault_root" not in data
