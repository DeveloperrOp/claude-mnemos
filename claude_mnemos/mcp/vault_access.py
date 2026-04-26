from __future__ import annotations

from pathlib import Path

from claude_mnemos.mcp.errors import PageRefError

_STANDARD_DIRS: tuple[str, ...] = (
    "wiki/entities",
    "wiki/concepts",
    "wiki/sources",
    "raw/chats",
)


def _is_safe_relative(page_ref: str) -> bool:
    if not page_ref or page_ref.strip() == "":
        return False
    # Posix-absolute (`/etc/passwd`) is not detected as absolute on Windows by
    # pathlib; reject leading separators explicitly.
    if page_ref.startswith(("/", "\\")):
        return False
    if Path(page_ref).is_absolute():
        return False
    parts = Path(page_ref).parts
    return ".." not in parts


def _resolve_inside_vault(vault: Path, candidate: Path) -> Path:
    vault_real = vault.resolve()
    candidate_real = candidate.resolve()
    try:
        candidate_real.relative_to(vault_real)
    except ValueError as exc:
        raise PageRefError(
            f"resolved path {candidate_real} escapes vault {vault_real}"
        ) from exc
    return candidate_real


def resolve_page_path(vault: Path, page_ref: str) -> Path:
    """Resolve `page_ref` to an absolute file path inside `vault`.

    Resolution order:
    1. Reject if empty / absolute / contains `..`.
    2. If `page_ref` ends with `.md`: try as path relative to vault.
    3. Else: try `<dir>/<page_ref>.md` for each standard wiki dir; if more
       than one matches → ambiguous.
    4. Verify final path is_relative_to vault (defence in depth).
    5. Raise `PageRefError` if not found.
    """
    if not _is_safe_relative(page_ref):
        raise PageRefError(f"unsafe page_ref: {page_ref!r}")

    if page_ref.endswith(".md"):
        candidate = vault / page_ref
        if not candidate.is_file():
            raise PageRefError(f"page not found: {page_ref}")
        return _resolve_inside_vault(vault, candidate)

    matches: list[Path] = []
    for sub in _STANDARD_DIRS:
        candidate = vault / sub / f"{page_ref}.md"
        if candidate.is_file():
            matches.append(candidate)

    if not matches:
        raise PageRefError(f"page not found: {page_ref}")
    if len(matches) > 1:
        rels = ", ".join(str(m.relative_to(vault).as_posix()) for m in matches)
        raise PageRefError(f"ambiguous page_ref {page_ref!r}: matches {rels}")

    return _resolve_inside_vault(vault, matches[0])
