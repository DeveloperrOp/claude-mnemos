"""Tests for the frontend static-files mount in create_app.

Uses tmp_path so the real claude_mnemos/daemon/static/ dir is never mutated
(a built bundle must not be deleted by a test run).
"""

from __future__ import annotations

from pathlib import Path

import httpx
from httpx import ASGITransport

from claude_mnemos.daemon.app import create_app


async def test_static_mount_skipped_when_no_index_html(tmp_path: Path) -> None:
    """create_app must succeed (and REST routes still work) when index.html is absent."""
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    # No index.html written — mount should be skipped.

    app = create_app(static_dir=static_dir)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/api/health")
        root = await client.get("/")
    assert health.status_code == 200
    assert root.status_code == 404


async def test_static_mount_serves_index_when_present(tmp_path: Path) -> None:
    """When index.html exists, GET / returns 200 with its content; /health still wins."""
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text(
        "<!doctype html><html><body>hello</body></html>", encoding="utf-8"
    )

    app = create_app(static_dir=static_dir)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        root = await client.get("/")
        health = await client.get("/api/health")
    assert root.status_code == 200
    assert "html" in root.text.lower()
    assert health.status_code == 200


async def test_spa_fallback_for_dotted_app_routes(tmp_path: Path) -> None:
    """Application routes that contain dots (e.g. .md page paths) must
    fall back to index.html — not 404.

    Regression: previously the SPA fallback heuristic was "any segment
    with a dot is an asset", which broke direct-nav / hard-refresh on
    URLs like /project/x/pages/wiki/foo.md.
    """
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text(
        "<!doctype html><html><body>spa</body></html>", encoding="utf-8"
    )

    app = create_app(static_dir=static_dir)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # An app route whose final segment ends in .md must serve the SPA shell.
        r_md = await client.get("/project/alpha/pages/wiki/concepts/foo.md")
        # An app route with no extension also serves the SPA shell.
        r_plain = await client.get("/lost-sessions")
        # An honest missing asset (under assets/) keeps the 404.
        r_missing_asset = await client.get("/assets/missing.js")

    assert r_md.status_code == 200
    assert "spa" in r_md.text
    assert r_plain.status_code == 200
    assert "spa" in r_plain.text
    assert r_missing_asset.status_code == 404


async def test_spa_fallback_favicon_ico_serves_svg(tmp_path: Path) -> None:
    """Browsers ask for /favicon.ico; we ship favicon.svg. The fallback
    must serve the SVG file rather than returning 404 or the SPA shell."""
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text(
        "<!doctype html><html><body>spa</body></html>", encoding="utf-8"
    )
    (static_dir / "favicon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"></svg>', encoding="utf-8"
    )

    app = create_app(static_dir=static_dir)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/favicon.ico")
    assert r.status_code == 200
    assert "<svg" in r.text
