"""Shared pytest fixtures for claude-mnemos tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_cli_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate every test from real user state.

    - HOME/USERPROFILE → tmp_path so Path.home() doesn't read ~/.claude-mnemos.
    - MNEMOS_DAEMON_URL → dead URL so CLI write commands skip the daemon-first
      branch (which on dev machines hits the running daemon and pollutes the
      real project map). Tests that need a real-daemon transport use ASGI
      directly and ignore this env var.
    - Drop env vars that vary per developer.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("MNEMOS_DAEMON_URL", "http://127.0.0.1:1")
    monkeypatch.delenv("MNEMOS_VAULT_ROOT", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture
def register_project(tmp_path, monkeypatch):
    """Register a project pointing at a tmp vault, isolating ~/.claude-mnemos/.

    Returns a callable: ``register_project(name, vault, *, cwd_patterns=None)``
    that creates the vault dir and adds an entry to the (isolated) project-map.

    Side effects:
        - Sets HOME and USERPROFILE to ``tmp_path`` so ``Path.home()`` resolves
          there (isolates ~/.claude-mnemos/ writes from the real user dir).
        - Deletes ``MNEMOS_VAULT_ROOT`` to enforce the post-#13b-α hard-cut.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("MNEMOS_VAULT_ROOT", raising=False)

    def _register(
        name: str,
        vault: Path,
        *,
        cwd_patterns: list[str] | None = None,
    ) -> None:
        from claude_mnemos.state.projects import ProjectMapEntry, ProjectStore

        vault.mkdir(parents=True, exist_ok=True)
        ProjectStore().add(
            ProjectMapEntry(
                name=name,
                vault_root=vault,
                cwd_patterns=cwd_patterns or [],
            )
        )

    return _register
