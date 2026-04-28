"""Pre-multivault MnemosDaemon tests.

The original tests in this file exercised single-vault state held directly on
``MnemosDaemon`` (``daemon.tracker``, ``daemon.observer``, ``daemon.job_store``,
``daemon._start_observer`` etc.). After Task 12 (Plan #13b-β1) all of that
state moved into per-vault ``VaultRuntime`` instances inside
``MnemosDaemon.runtimes``; ``MnemosDaemon`` itself now only owns the FastAPI
app, the shared scheduler, the alerts bus, and the primary-runtime selector.

The replacement coverage lives in:

* ``tests/daemon/test_vault_runtime.py`` — observer/jobs/tracker/cron lifecycle
* ``tests/daemon/test_process_multivault.py`` — ``__init__`` + primary selection
* (forthcoming) Task 13 ``_bootstrap_runtimes``, Task 14 mount/unmount,
  Task 16 ``run()``/``_request_shutdown``.

The legacy tests below are skip-marked rather than deleted so the migration
trail is visible in git history; they should be removed once Tasks 13-16 land
their full replacements.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "Task 12 dropped MnemosDaemon's per-vault attributes "
        "(tracker/observer/job_store/_start_observer/_start_jobs_subsystem). "
        "Replacement coverage: tests/daemon/test_vault_runtime.py + "
        "tests/daemon/test_process_multivault.py. Full lifecycle coverage "
        "lands with Tasks 13/14/16."
    )
)


def test_legacy_process_tests_replaced() -> None:
    """Placeholder so pytest reports a single skip line for this module."""
