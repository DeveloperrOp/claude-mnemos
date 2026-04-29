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
        health = await client.get("/health")
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
        health = await client.get("/health")
    assert root.status_code == 200
    assert "html" in root.text.lower()
    assert health.status_code == 200
