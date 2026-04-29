"""Tests for the frontend static-files mount in create_app."""

from __future__ import annotations

from pathlib import Path

import httpx
from httpx import ASGITransport

from claude_mnemos.daemon.app import create_app

# Location of the real static dir that app.py inspects.
_STATIC_DIR = Path(__file__).parents[2] / "claude_mnemos" / "daemon" / "static"


async def test_static_mount_skipped_when_no_index_html() -> None:
    """create_app must succeed (and REST routes still work) when index.html is absent."""
    index = _STATIC_DIR / "index.html"
    # Ensure fixture file is not present before the test.
    if index.exists():
        index.unlink()

    app = create_app()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/health")
    assert r.status_code == 200


async def test_static_mount_serves_index_when_present() -> None:
    """When index.html exists in static/, GET / returns 200 with the HTML content."""
    index = _STATIC_DIR / "index.html"
    try:
        index.write_text("<!doctype html><html><body>hello</body></html>", encoding="utf-8")
        app = create_app()
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            r = await client.get("/")
        assert r.status_code == 200
        assert "html" in r.text.lower()
    finally:
        if index.exists():
            index.unlink()
