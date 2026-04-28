"""Pre-multivault MnemosDaemon settings-consumption tests.

These tests asserted that ``MnemosDaemon.__init__`` resolved the active project
via ``ProjectResolver`` and exposed ``daemon.project_settings`` /
``daemon.project_entry`` directly on the daemon, plus that
``daemon.reload_settings`` re-scheduled the (single) vault's daily-snapshot job.

Task 12 (Plan #13b-β1) removed all single-vault state from ``MnemosDaemon`` —
project resolution and per-project settings now belong to each
``VaultRuntime`` keyed by name in ``daemon.runtimes``; ``reload_settings``
moves to ``VaultRuntime.reload_settings`` (already covered in
``tests/daemon/test_vault_runtime.py``).

Replacement coverage:

* ``tests/daemon/test_vault_runtime.py`` — per-vault settings + reload
* ``tests/daemon/test_process_multivault.py`` — daemon construction +
  primary-runtime selection from global settings
* (forthcoming) Task 14 mount/unmount → settings landing in runtimes,
  Task 17 PATCH /settings/{project} → reload via daemon dispatcher.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "Task 12 dropped MnemosDaemon.{project_settings,project_entry,"
        "reload_settings} in favour of per-vault VaultRuntime state. "
        "Replacement coverage: tests/daemon/test_vault_runtime.py + "
        "tests/daemon/test_process_multivault.py. Full PATCH/reload "
        "coverage lands with Tasks 14/17."
    )
)


def test_legacy_settings_consumption_replaced() -> None:
    """Placeholder so pytest reports a single skip line for this module."""
