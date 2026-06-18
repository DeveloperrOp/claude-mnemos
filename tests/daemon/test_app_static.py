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


async def test_spa_route_not_treated_as_asset(tmp_path: Path) -> None:
    """A real SPA route (no file extension) must fall through to index.html
    (200), not be 404'd as a missing asset. Guards the _ASSET_EXTENSIONS
    membership check — a route segment with no known asset extension is an
    application route, never a static asset.
    """
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text(
        "<!doctype html><html><body>spa</body></html>", encoding="utf-8"
    )

    app = create_app(static_dir=static_dir)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/project/foo/lost-sessions")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert "spa" in r.text


async def test_real_missing_asset_404s(tmp_path: Path) -> None:
    """A top-level path whose extension IS in _ASSET_EXTENSIONS (e.g. a
    missing .js bundle) must 404 via the extension check rather than fall
    through to the SPA shell. This exercises the membership branch directly
    (not the assets/ prefix branch)."""
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text(
        "<!doctype html><html><body>spa</body></html>", encoding="utf-8"
    )

    app = create_app(static_dir=static_dir)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/does-not-exist-12345.js")
    assert r.status_code == 404


async def test_no_cache_on_root_and_spa_fallback(tmp_path: Path) -> None:
    """index.html must carry no-cache wherever it is served from: the literal
    /index.html, the ROOT '/', and SPA-fallback routes (/lost-sessions). Those
    last two are the actual entry points users hit — without the header the
    browser heuristic-caches a stale bundle past upgrades. Hashed assets are
    content-addressable and must NOT be forced to revalidate.
    """
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text(
        "<!doctype html><html><body>spa</body></html>", encoding="utf-8"
    )
    (static_dir / "assets").mkdir()
    (static_dir / "assets" / "index-AbCd1234.js").write_text("console.log(1)", encoding="utf-8")
    (static_dir / "locales").mkdir()
    (static_dir / "locales" / "ru.json").write_text("{}", encoding="utf-8")

    app = create_app(static_dir=static_dir)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for path in ("/", "/index.html", "/lost-sessions", "/locales/ru.json"):
            r = await client.get(path)
            assert r.status_code == 200, path
            assert "no-cache" in r.headers.get("cache-control", ""), (
                f"{path} must carry no-cache, got {r.headers.get('cache-control')!r}"
            )
        r_asset = await client.get("/assets/index-AbCd1234.js")
        assert r_asset.status_code == 200
        assert "no-cache" not in r_asset.headers.get("cache-control", "")


async def test_explicit_cache_policy_for_assets_fonts_favicon(tmp_path: Path) -> None:
    """Files outside the no-cache set must carry an explicit policy instead
    of browser heuristics: Vite-hashed assets/ are content-addressable →
    cache forever; fonts/ and the favicon are unhashed but stable → bounded
    one-day max-age (stale at most a day after an upgrade)."""
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text(
        "<!doctype html><html><body>spa</body></html>", encoding="utf-8"
    )
    (static_dir / "assets").mkdir()
    (static_dir / "assets" / "index-AbCd1234.js").write_text("console.log(1)", encoding="utf-8")
    (static_dir / "fonts").mkdir()
    (static_dir / "fonts" / "Geist-Variable.woff2").write_bytes(b"\x00\x01")
    (static_dir / "favicon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"></svg>', encoding="utf-8"
    )

    app = create_app(static_dir=static_dir)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r_asset = await client.get("/assets/index-AbCd1234.js")
        r_font = await client.get("/fonts/Geist-Variable.woff2")
        r_favicon = await client.get("/favicon.svg")
        r_favicon_ico = await client.get("/favicon.ico")  # served via svg fallback

    assert r_asset.headers["cache-control"] == "public, max-age=31536000, immutable"
    for r in (r_font, r_favicon, r_favicon_ico):
        assert r.status_code == 200
        assert r.headers["cache-control"] == "public, max-age=86400", r.request.url


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
