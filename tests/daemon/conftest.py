"""Shared fixtures for tests/daemon/test_app_*.py.

Two helpers live here so each REST test stops re-implementing the same
``_FakeRuntime`` / ``_FakeDaemon`` boilerplate from scratch:

* ``fake_runtime_factory`` — callable that builds a permissive shim mimicking
  ``VaultRuntime``. Accepts overrides via kwargs so tests can plug in their
  own ``project``, ``tracker``, ``lost_sessions_cache`` etc. without paying
  for a full VaultRuntime mount.
* ``fake_daemon_factory`` — companion that exposes ``runtimes`` /
  ``alerts`` / ``alerts_store`` / ``scheduler_jobs_info`` so the
  ``get_runtime`` / ``all_runtimes`` helpers and route handlers find what
  they expect on ``app.state.daemon``.

Currently consumed by:
  - tests/daemon/test_app_lost_sessions.py
  - tests/daemon/test_app_inject_preview.py

(``tests/daemon/test_app_health_alerts.py`` is in the migration scope but
constructs the app with ``daemon=None`` to exercise the route's
load-from-disk fallback path; nothing to factor out there.)

Other ``test_app_*.py`` files still keep their own bespoke shims; opt-in
by replacing your local ``_FakeRuntime``/``_FakeDaemon`` definitions with
``runtime = fake_runtime_factory(vault, ...)`` and
``daemon = fake_daemon_factory(runtime, ...)``. Set whatever attributes the
specific routes under test need via kwargs (``tracker=...``,
``project=...``, ``lost_sessions_cache=...``).

These fixtures intentionally do NOT touch ``alerts.json`` on disk — the
``AlertsStore`` singleton is loaded from the patched ``HOME`` so tests
that need fresh state should also use ``isolated_home``.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from claude_mnemos.daemon.alerts import Alerts


class _FakeRuntime:
    """Permissive VaultRuntime shim — any kwarg becomes an attribute."""

    def __init__(self, vault: Path, *, name: str, **attrs: Any) -> None:
        self.name = name
        self.vault_root = vault
        for k, v in attrs.items():
            setattr(self, k, v)


class _FakeDaemon:
    """Permissive MnemosDaemon shim — exposes ``runtimes`` plus any extras."""

    def __init__(
        self,
        runtimes: dict[str, _FakeRuntime],
        **attrs: Any,
    ) -> None:
        self.runtimes = runtimes
        self.alerts = attrs.pop("alerts", Alerts())
        self.started_at_monotonic = attrs.pop("started_at_monotonic", 0.0)
        for k, v in attrs.items():
            setattr(self, k, v)

    def scheduler_jobs_info(self) -> list[object]:
        return []


@pytest.fixture
def fake_runtime_factory() -> Callable[..., _FakeRuntime]:
    """Return a callable ``(vault, *, name="default", **attrs) -> _FakeRuntime``.

    Example::

        rt = fake_runtime_factory(tmp_path, name="alpha", project=entry,
                                   tracker=OurWritesTracker(ttl_s=60.0))
    """

    def _make(vault: Path, *, name: str = "default", **attrs: Any) -> _FakeRuntime:
        return _FakeRuntime(vault, name=name, **attrs)

    return _make


@pytest.fixture
def fake_daemon_factory() -> Callable[..., _FakeDaemon]:
    """Return a callable ``(runtime_or_runtimes, **attrs) -> _FakeDaemon``.

    Pass either a single ``_FakeRuntime`` or a ``{name: _FakeRuntime}`` dict.
    Any extra kwargs (e.g. ``alerts_store``) are attached as attributes so
    routes that read ``daemon.alerts_store`` etc. find them.
    """

    def _make(
        runtime_or_runtimes: _FakeRuntime | dict[str, _FakeRuntime],
        **attrs: Any,
    ) -> _FakeDaemon:
        if isinstance(runtime_or_runtimes, dict):
            runtimes = runtime_or_runtimes
        else:
            runtimes = {runtime_or_runtimes.name: runtime_or_runtimes}
        return _FakeDaemon(runtimes, **attrs)

    return _make
