"""cwd → ProjectMapEntry resolver via fnmatch + most-specific-wins.

Reads ~/.claude-mnemos/project-map.json fresh on each call (no cache in
Plan #13b-α — performance optimization deferred to #13b-β if needed).
"""

from __future__ import annotations

import fnmatch
import functools
import shutil
import subprocess
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


@functools.lru_cache(maxsize=512)
def _git_toplevel(cwd: Path) -> Path | None:
    """Return the git working-tree root for *cwd*, or None if not a repo / git
    unavailable. Used as a fallback when a session's cwd matches no project
    pattern: the repo root often DOES (you registered the project at the repo
    root but ran Claude from a sibling path or an uncovered subdir).

    Cached per resolved cwd (a lost-sessions scan resolves the same handful of
    repos for dozens of unassigned sessions — without the cache that is dozens
    of git subprocesses, each blocking up to the timeout on a dead/unmounted
    path). Repo membership doesn't change within a process run, so caching is
    safe; maxsize bounds memory.
    """
    git = shutil.which("git")
    if git is None:
        return None
    try:
        out = subprocess.run(
            [git, "-C", str(cwd), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    top = out.stdout.strip()
    if not top:
        return None
    try:
        return Path(top)
    except (ValueError, OSError):
        return None


class ProjectResolver:
    def __init__(
        self,
        store: ProjectStore | None = None,
        *,
        entries: list[ProjectMapEntry] | None = None,
    ) -> None:
        self._store = store if store is not None else ProjectStore()
        self._entries: list[ProjectMapEntry] | None = entries

    def _get_entries(self) -> list[ProjectMapEntry]:
        return self._entries if self._entries is not None else self._store.list_all()

    def list_all(self) -> list[ProjectMapEntry]:
        return self._get_entries()

    def resolve_by_name(self, name: str) -> ProjectMapEntry | None:
        for e in self._get_entries():
            if e.name == name:
                return e
        return None

    def resolve_by_vault(self, vault_root: Path) -> ProjectMapEntry | None:
        target = Path(vault_root).expanduser().resolve()
        for e in self._get_entries():
            try:
                if Path(e.vault_root).expanduser().resolve() == target:
                    return e
            except OSError:
                continue
        return None

    def resolve_by_cwd(
        self, cwd: Path, *, git_fallback: bool = False
    ) -> ProjectMapEntry | None:
        """Resolve cwd → project via cwd_patterns (most-specific-wins).

        With ``git_fallback=True``, if cwd matches nothing, retry against the
        cwd's git working-tree root before giving up. This rescues sessions
        run from an uncovered path of a repo whose root IS registered — the
        single largest source of "unassigned" lost sessions. Off by default so
        the pure pattern semantics (and CLI callers) are unchanged.
        """
        direct = self._match_cwd(cwd)
        if direct is not None or not git_fallback:
            return direct
        top = _git_toplevel(cwd)
        if top is None or _normalize(top) == _normalize(cwd):
            return None
        return self._match_cwd(top)

    def _match_cwd(self, cwd: Path) -> ProjectMapEntry | None:
        cwd_norm = _normalize(cwd)
        candidates: list[tuple[ProjectMapEntry, str, int]] = []
        for entry in self._get_entries():
            for pattern in entry.cwd_patterns:
                pat_norm = _normalize(pattern)
                # Recursive form: trailing \* or \** means "this folder and any
                # descendant". Without this expansion, fnmatch treats \* as
                # "exactly one path segment of any chars" — which fails for
                # cwd === base folder (no trailing segment) and for nested
                # subdirectories. We canonicalize: strip the wildcard and
                # match if cwd equals base or sits under base/.
                base = pat_norm
                if base.endswith(("\\**", "/**")):
                    base = base[:-3]
                elif base.endswith(("\\*", "/*")):
                    base = base[:-2]
                if base != pat_norm:  # had a trailing wildcard
                    if cwd_norm == base or cwd_norm.startswith(base + "\\") or cwd_norm.startswith(base + "/"):
                        candidates.append((entry, pattern, len(pat_norm)))
                elif fnmatch.fnmatchcase(cwd_norm, pat_norm):
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
