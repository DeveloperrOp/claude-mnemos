"""Pure-Python Levenshtein + slug index for the lint package."""

from __future__ import annotations

from pathlib import Path


def levenshtein_distance(a: str, b: str) -> int:
    """Edit distance between two strings (insert/delete/substitute = 1).

    Standard DP O(len(a) * len(b)). For our use case (slug lookups, max ~50
    chars × few hundred candidates) this is fast enough; no C extension needed.
    """
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            curr[j] = min(
                curr[j - 1] + 1,
                prev[j] + 1,
                prev[j - 1] + (ca != cb),
            )
        prev = curr
    return prev[-1]


_TYPE_PRIORITY = {"entities": 0, "concepts": 1, "sources": 2}


def build_slug_index(vault: Path) -> dict[str, Path]:
    """Walk wiki/{entities,concepts,sources}/ and map slug -> first file path.

    On collision, prefer entity > concept > source. Dotfile dirs (.staging,
    .backups, etc.) are excluded by virtue of starting with a dot — Path.glob
    over wiki/* never visits them; the explicit guard inside the loop is
    defense-in-depth in case someone passes a deeper pattern in the future.
    """
    index: dict[str, Path] = {}
    for type_dir in ("entities", "concepts", "sources"):
        root = vault / "wiki" / type_dir
        if not root.is_dir():
            continue
        for p in root.glob("*.md"):
            if any(part.startswith(".") for part in p.parts):
                continue
            slug = p.stem
            existing = index.get(slug)
            if existing is None:
                index[slug] = p
                continue
            existing_type = existing.parent.name
            if _TYPE_PRIORITY[type_dir] < _TYPE_PRIORITY.get(existing_type, 99):
                index[slug] = p
    return index
