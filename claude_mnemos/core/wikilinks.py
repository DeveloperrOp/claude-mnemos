from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

WIKILINK_RE = re.compile(r"\[\[([^\[\]\|]+)(?:\|([^\]]+))?\]\]")


@dataclass(frozen=True)
class Wikilink:
    target: str
    alias: str | None = None


def extract_wikilinks(text: str) -> list[Wikilink]:
    """Return all `[[target]]` and `[[target|alias]]` matches in `text`.

    Order preserved. Duplicates returned as-is — caller dedupes if needed.
    """
    return [
        Wikilink(target=m.group(1).strip(), alias=(m.group(2).strip() if m.group(2) else None))
        for m in WIKILINK_RE.finditer(text)
    ]


def rewrite_wikilinks(text: str, mapping: dict[str, str]) -> str:
    """Replace `[[old]]` with `[[new]]` (and `[[old|alias]]` with `[[new|alias]]`)
    for every `old → new` in `mapping`. Targets not in mapping are left untouched.
    """
    if not mapping:
        return text

    def _replace(m: re.Match[str]) -> str:
        target = m.group(1).strip()
        alias = m.group(2)
        if target not in mapping:
            return m.group(0)
        new_target = mapping[target]
        if alias is None:
            return f"[[{new_target}]]"
        return f"[[{new_target}|{alias}]]"

    return WIKILINK_RE.sub(_replace, text)


def find_files_referencing(
    vault: Path,
    target_slug: str,
    *,
    exclude: set[Path] | None = None,
) -> list[Path]:
    """Return wiki/raw `.md` files containing `[[target_slug]]` (with or without alias).

    Skips paths in `exclude` (e.g. the file representing target_slug itself).
    """
    excluded = {p.resolve() for p in (exclude or set())}
    matches: list[Path] = []
    for root_name in ("wiki", "raw"):
        root = vault / root_name
        if not root.is_dir():
            continue
        for page in root.rglob("*.md"):
            if not page.is_file():
                continue
            if page.resolve() in excluded:
                continue
            try:
                text = page.read_text(encoding="utf-8")
            except OSError:
                continue
            for link in extract_wikilinks(text):
                if link.target == target_slug:
                    matches.append(page)
                    break
    return matches
