"""Auto-update check against GitHub Releases.

Polls the project's GitHub Releases API once per ``_CACHE_TTL`` window and
caches the result in ``~/.claude-mnemos/update-check.json``. The cache also
remembers a user-driven ``dismissed_until`` timestamp so the UI banner can
be silenced for a few days at a time.

This module is intentionally side-effect-free apart from the cache file and
a single HTTPS call. Auto-replace via Sparkle/Squirrel is deferred until
binaries are code-signed — for now the Overview banner just opens the
release page in the browser.
"""

from __future__ import annotations

import contextlib
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from claude_mnemos import __version__

_GITHUB_LATEST_RELEASE = (
    "https://api.github.com/repos/DeveloperrOp/claude-mnemos/releases/latest"
)
_CACHE_PATH: Path = Path.home() / ".claude-mnemos" / "update-check.json"
_CACHE_TTL = timedelta(hours=24)


@dataclass
class UpdateStatus:
    current: str
    latest: str | None
    download_url: str | None
    has_update: bool
    checked_at: datetime
    asset_url: str | None = None
    dismissed_until: datetime | None = None
    error: str | None = None


def _pick_asset_url(release: dict[str, Any], asset_name: str) -> str | None:
    """Return the ``browser_download_url`` of the asset named ``asset_name``.

    Returns ``None`` when no asset with that exact name is present.
    """
    for asset in release.get("assets", []):
        if asset.get("name") == asset_name:
            url: str | None = asset.get("browser_download_url")
            return url
    return None


def _current_version() -> str:
    return __version__


def _fetch_latest_release() -> dict[str, Any]:
    req = urllib.request.Request(
        _GITHUB_LATEST_RELEASE,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "claude-mnemos",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 — fixed URL
        data: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
        return data


def _parse_version(v: str) -> tuple[int, ...]:
    raw = v.lstrip("v")
    parts: list[int] = []
    for chunk in raw.split("."):
        try:
            parts.append(int(chunk.split("-")[0]))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _load_cache() -> dict[str, Any] | None:
    if not _CACHE_PATH.exists():
        return None
    try:
        cached: dict[str, Any] = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        return cached
    except (OSError, json.JSONDecodeError):
        return None


def _save_cache(data: dict[str, Any]) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def check_for_update(*, force: bool = False) -> UpdateStatus:
    """Return current/latest version pair, hitting GitHub at most once per
    ``_CACHE_TTL`` (24h). Pass ``force=True`` to bypass the cache.

    On network failure returns ``has_update=False`` with ``error`` populated —
    callers should never block on this.
    """
    now = datetime.now(tz=UTC)
    cached = _load_cache()

    if not force and cached:
        try:
            checked_at = datetime.fromisoformat(cached["checked_at"])
            if now - checked_at < _CACHE_TTL:
                latest = cached.get("latest")
                # ``current`` is the running binary's version — always compute
                # it live, never trust the cached value. The cache may have been
                # written by an older binary (e.g. before an in-place update);
                # reusing its ``current`` would keep the "update available"
                # banner up for the rest of the TTL after the user already
                # updated.
                current = _current_version()
                has_update = bool(
                    latest and _parse_version(latest) > _parse_version(current)
                )
                return UpdateStatus(
                    current=current,
                    latest=latest,
                    download_url=cached.get("download_url"),
                    has_update=has_update,
                    checked_at=checked_at,
                    asset_url=cached.get("asset_url"),
                    dismissed_until=(
                        datetime.fromisoformat(cached["dismissed_until"])
                        if cached.get("dismissed_until")
                        else None
                    ),
                )
        except (KeyError, ValueError):
            pass

    current = _current_version()
    try:
        release = _fetch_latest_release()
        latest = release.get("tag_name", "").lstrip("v")
        download_url = release.get("html_url")
        asset_url = _pick_asset_url(release, "claude-mnemos-portable-x64.zip")
        has_update = bool(latest) and _parse_version(latest) > _parse_version(current)
        status = UpdateStatus(
            current=current,
            latest=latest or None,
            download_url=download_url,
            has_update=has_update,
            checked_at=now,
            asset_url=asset_url,
        )
    except (OSError, ValueError, urllib.error.URLError) as exc:
        status = UpdateStatus(
            current=current,
            latest=None,
            download_url=None,
            has_update=False,
            checked_at=now,
            error=str(exc),
        )

    if cached and cached.get("dismissed_until"):
        with contextlib.suppress(ValueError):
            status.dismissed_until = datetime.fromisoformat(cached["dismissed_until"])

    _save_cache(
        {
            "checked_at": status.checked_at.isoformat(),
            "current": status.current,
            "latest": status.latest,
            "download_url": status.download_url,
            "asset_url": status.asset_url,
            "dismissed_until": (
                status.dismissed_until.isoformat() if status.dismissed_until else None
            ),
        }
    )
    return status


def dismiss_for_days(days: int) -> None:
    """Snooze the update banner for ``days`` (clamped 1..30 by the route)."""
    cached = _load_cache() or {}
    cached["dismissed_until"] = (
        datetime.now(tz=UTC) + timedelta(days=days)
    ).isoformat()
    if "checked_at" not in cached:
        cached["checked_at"] = datetime.now(tz=UTC).isoformat()
    if "current" not in cached:
        cached["current"] = _current_version()
    _save_cache(cached)
