"""cwd → ProjectMapEntry resolver via fnmatch + most-specific-wins.

Reads ~/.claude-mnemos/project-map.json fresh on each call (no cache in
Plan #13b-α — performance optimization deferred to #13b-β if needed).
"""

from __future__ import annotations

import fnmatch
import sys
from pathlib import Path

from claude_mnemos.state.projects import (
    ProjectMapEntry,
    ProjectMapError,
    ProjectStore,
)


class ResolverAmbiguityError(ProjectMapError):
    """Two distinct project entries match the same cwd at the same specificity."""


def _normalize(p: str | Path) -> str:
    s = str(Path(p).expanduser().resolve())
    return s.lower() if sys.platform == "win32" else s


class ProjectResolver:
    def __init__(self, store: ProjectStore | None = None) -> None:
        self._store = store if store is not None else ProjectStore()

    def list_all(self) -> list[ProjectMapEntry]:
        return self._store.list_all()

    def resolve_by_name(self, name: str) -> ProjectMapEntry | None:
        for e in self._store.list_all():
            if e.name == name:
                return e
        return None

    def resolve_by_vault(self, vault_root: Path) -> ProjectMapEntry | None:
        target = Path(vault_root).expanduser().resolve()
        for e in self._store.list_all():
            try:
                if Path(e.vault_root).expanduser().resolve() == target:
                    return e
            except OSError:
                continue
        return None

    def resolve_by_cwd(self, cwd: Path) -> ProjectMapEntry | None:
        cwd_norm = _normalize(cwd)
        candidates: list[tuple[ProjectMapEntry, str, int]] = []
        for entry in self._store.list_all():
            for pattern in entry.cwd_patterns:
                pat_norm = _normalize(pattern)
                if fnmatch.fnmatchcase(cwd_norm, pat_norm):
                    candidates.append((entry, pattern, len(pat_norm)))
        if not candidates:
            return None
        candidates.sort(key=lambda t: t[2], reverse=True)
        top_len = candidates[0][2]
        ties = [c for c in candidates if c[2] == top_len]
        unique_names = {c[0].name for c in ties}
        if len(unique_names) > 1:
            raise ResolverAmbiguityError(
                f"cwd {cwd} matches {len(unique_names)} projects at length {top_len}: "
                f"{sorted(unique_names)}"
            )
        return candidates[0][0]
