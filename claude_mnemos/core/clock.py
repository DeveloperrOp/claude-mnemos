"""Single source of truth for ``datetime.now(tz=UTC)``.

Centralised so detectors, stores, and tests share one helper instead of each
module redefining ``_utcnow``.
"""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(tz=UTC)
