"""Shared helpers for cross-vault uningested-session aggregation.

Three places compute "uningested transcripts across all mounted vaults":

* :mod:`claude_mnemos.daemon.routes.lost_sessions` — full lost-sessions
  list with ``LostSessionsIgnore`` applied, served from per-vault
  ``LostSessionsCache``. Returns ``LostSessionItem`` dicts.
* :mod:`claude_mnemos.daemon.routes.dashboard` — count for the KPI bar.
  Reads via global ``scan_transcripts`` (no per-vault cache, no ignore
  list).
* :mod:`claude_mnemos.core.active_sessions` — recent transcripts
  (mtime > now - cooling_threshold) projected into ``ActiveSession`` for
  the operational Overview. Reads via ``scan_transcripts``, no ignore.

The three pipelines diverge enough (different cache layers, different
object shapes, different filters) that a single ``scan_uningested``
function would either be a leaky abstraction or force behaviour changes.
What every caller _does_ share is "the union of ingested SHAs across all
mounted vaults" — so that one piece is extracted here.

Full unification is deferred until either:

* the lost-sessions cache is dropped in favour of the global
  ``transcript_scanner`` cache, OR
* ``ActiveSession`` and ``LostSessionItem`` collapse into one DTO.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from claude_mnemos.state.manifest import Manifest

if TYPE_CHECKING:
    from claude_mnemos.daemon.vault_runtime import VaultRuntime


def global_ingested_shas(runtimes: list["VaultRuntime"]) -> set[str]:
    """Union of ingested SHAs across every mounted vault.

    A SHA present in ANY vault's manifest is considered globally
    ingested — i.e. NOT lost / NOT active. Manifests that fail to load
    are skipped silently; the caller treats their vaults as contributing
    no ingested SHAs (conservative — false positives are preferable to
    silent loss).
    """
    out: set[str] = set()
    for rt in runtimes:
        try:
            manifest = Manifest.load(rt.vault_root)
        except Exception:
            continue
        out.update(manifest.ingested.keys())
    return out
