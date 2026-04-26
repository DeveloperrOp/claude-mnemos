from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from claude_mnemos.mcp.vault_access import resolve_page_path

PageType = str  # "entity" | "concept" | "source"

_TYPE_DIRS: dict[str, str] = {
    "entity": "wiki/entities",
    "concept": "wiki/concepts",
    "source": "wiki/sources",
}


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split markdown into (frontmatter dict, body string).

    Returns ({}, full_text) if there is no leading YAML frontmatter.
    """
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, text
    yaml_block = "".join(lines[1:end])
    body = "".join(lines[end + 1 :])
    try:
        data = yaml.safe_load(yaml_block) or {}
    except yaml.YAMLError:
        return {}, text
    if not isinstance(data, dict):
        return {}, text
    return data, body


def _page_summary(vault: Path, page_path: Path) -> dict[str, Any]:
    rel = page_path.relative_to(vault).as_posix()
    try:
        text = page_path.read_text(encoding="utf-8")
    except OSError as exc:
        return {
            "path": rel,
            "title": None,
            "type": None,
            "flavor": [],
            "error": str(exc),
        }
    fm, _body = _split_frontmatter(text)
    return {
        "path": rel,
        "title": fm.get("title"),
        "type": fm.get("type"),
        "flavor": fm.get("flavor", []) or [],
        "mtime": page_path.stat().st_mtime,
    }


def list_pages(
    vault: Path,
    *,
    type: str | None = None,
    flavor: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List wiki pages, optionally filtered by type and flavor.

    Sorted newest mtime first, capped to `limit`.
    """
    if type is not None:
        if type not in _TYPE_DIRS:
            return []
        roots = [vault / _TYPE_DIRS[type]]
    else:
        roots = [vault / d for d in _TYPE_DIRS.values()]

    summaries: list[dict[str, Any]] = []
    for root in roots:
        if not root.is_dir():
            continue
        for page_path in root.glob("*.md"):
            if page_path.is_file():
                summaries.append(_page_summary(vault, page_path))

    if flavor is not None:
        summaries = [s for s in summaries if flavor in (s.get("flavor") or [])]

    summaries.sort(key=lambda s: s.get("mtime", 0.0), reverse=True)

    # Drop mtime from output (it was just for sorting)
    for s in summaries:
        s.pop("mtime", None)

    return summaries[:limit]


def read_page(vault: Path, page_ref: str) -> dict[str, Any]:
    """Read a page by reference. Raises PageRefError if unsafe / not found."""
    page_path = resolve_page_path(vault, page_ref)
    text = page_path.read_text(encoding="utf-8")
    fm, body = _split_frontmatter(text)
    return {
        "path": page_path.relative_to(vault.resolve()).as_posix(),
        "frontmatter": fm,
        "body": body,
    }


def _snippet(text: str, query: str, *, around: int = 80) -> str:
    idx = text.lower().find(query.lower())
    if idx < 0:
        return ""
    start = max(0, idx - around)
    end = min(len(text), idx + len(query) + around)
    s = text[start:end].replace("\n", " ").strip()
    if start > 0:
        s = "…" + s
    if end < len(text):
        s = s + "…"
    return s


def search_pages(
    vault: Path,
    query: str,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Case-insensitive substring search across wiki page filenames + body."""
    if not query:
        return []
    q = query.lower()
    matches: list[dict[str, Any]] = []

    for root_name in ("wiki", "raw"):
        root = vault / root_name
        if not root.is_dir():
            continue
        for page_path in root.rglob("*.md"):
            if not page_path.is_file():
                continue
            try:
                text = page_path.read_text(encoding="utf-8")
            except OSError:
                continue
            in_name = q in page_path.name.lower()
            in_body = q in text.lower()
            if not (in_name or in_body):
                continue
            matches.append(
                {
                    "path": page_path.relative_to(vault).as_posix(),
                    "matched_in_name": in_name,
                    "matched_in_body": in_body,
                    "snippet": _snippet(text, query) if in_body else "",
                }
            )

    return matches[:limit]
