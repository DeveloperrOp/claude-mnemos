from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from claude_mnemos import __version__
from claude_mnemos.core.locks import LockTimeoutError
from claude_mnemos.core.undo import UndoError
from claude_mnemos.daemon.routes.health import router as health_router
from claude_mnemos.state.activity import ActivityCorruptError
from claude_mnemos.state.manifest import ManifestCorruptError


def create_app(vault_root: Path, daemon: Any | None = None) -> FastAPI:
    app = FastAPI(title="claude-mnemos daemon", version=__version__)
    app.state.vault_root = vault_root
    app.state.daemon = daemon

    app.include_router(health_router)

    @app.exception_handler(ActivityCorruptError)
    async def _activity_corrupt(_request: Request, exc: ActivityCorruptError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"error": "activity_corrupt", "detail": str(exc)},
        )

    @app.exception_handler(ManifestCorruptError)
    async def _manifest_corrupt(_request: Request, exc: ManifestCorruptError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"error": "manifest_corrupt", "detail": str(exc)},
        )

    @app.exception_handler(UndoError)
    async def _undo_error(_request: Request, exc: UndoError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"error": "undo_failed", "detail": str(exc)},
        )

    @app.exception_handler(LockTimeoutError)
    async def _lock_timeout(_request: Request, exc: LockTimeoutError) -> JSONResponse:
        return JSONResponse(
            status_code=423,
            content={"error": "vault_locked", "detail": str(exc)},
        )

    return app
