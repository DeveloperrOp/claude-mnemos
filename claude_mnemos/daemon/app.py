from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from claude_mnemos import __version__
from claude_mnemos.core.locks import LockTimeoutError
from claude_mnemos.core.ontology_apply import OntologyError
from claude_mnemos.core.page_apply import PageRestoreCollisionError
from claude_mnemos.core.pages import PageRefError
from claude_mnemos.core.trash import TrashEntryNotFoundError
from claude_mnemos.core.undo import UndoError
from claude_mnemos.daemon.routes.activity import router as activity_router
from claude_mnemos.daemon.routes.alerts import router as alerts_router
from claude_mnemos.daemon.routes.dead_letter import router as dead_letter_router
from claude_mnemos.daemon.routes.health import router as health_router
from claude_mnemos.daemon.routes.jobs import router as jobs_router
from claude_mnemos.daemon.routes.lint import router as lint_router
from claude_mnemos.daemon.routes.ontology import router as ontology_router
from claude_mnemos.daemon.routes.pages import router as pages_router
from claude_mnemos.daemon.routes.snapshots import router as snapshots_router
from claude_mnemos.daemon.routes.trash import router as trash_router
from claude_mnemos.daemon.routes.vault import router as vault_router
from claude_mnemos.lint.exceptions import LintCorruptError, LintError
from claude_mnemos.state.activity import ActivityCorruptError
from claude_mnemos.state.jobs import JobsCorruptError
from claude_mnemos.state.manifest import ManifestCorruptError
from claude_mnemos.state.ontology import OntologyCorruptError


def create_app(vault_root: Path, daemon: Any | None = None) -> FastAPI:
    app = FastAPI(title="claude-mnemos daemon", version=__version__)
    app.state.vault_root = vault_root
    app.state.daemon = daemon

    app.include_router(health_router)
    app.include_router(vault_router)
    app.include_router(activity_router)
    app.include_router(snapshots_router)
    app.include_router(ontology_router)
    app.include_router(alerts_router)
    app.include_router(lint_router)
    app.include_router(jobs_router)
    app.include_router(dead_letter_router)
    app.include_router(pages_router)
    app.include_router(trash_router)

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

    @app.exception_handler(OntologyError)
    async def _ontology_error(_request: Request, exc: OntologyError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"error": "ontology_apply_failed", "detail": str(exc)},
        )

    @app.exception_handler(OntologyCorruptError)
    async def _ontology_corrupt(_request: Request, exc: OntologyCorruptError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"error": "ontology_corrupt", "detail": str(exc)},
        )

    @app.exception_handler(LintError)
    async def _lint_error(_request: Request, exc: LintError) -> JSONResponse:
        return JSONResponse(
            status_code=409, content={"error": "lint_failed", "detail": str(exc)}
        )

    @app.exception_handler(LintCorruptError)
    async def _lint_corrupt(_request: Request, exc: LintCorruptError) -> JSONResponse:
        return JSONResponse(
            status_code=503, content={"error": "lint_corrupt", "detail": str(exc)}
        )

    @app.exception_handler(JobsCorruptError)
    async def _jobs_corrupt(_request: Request, exc: JobsCorruptError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"error": "jobs_corrupt", "detail": str(exc)},
        )

    @app.exception_handler(PageRefError)
    async def _page_ref_error(_request: Request, exc: PageRefError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"error": "page_not_found", "detail": str(exc)},
        )

    @app.exception_handler(PageRestoreCollisionError)
    async def _restore_collision(
        _request: Request, exc: PageRestoreCollisionError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"error": "restore_collision", "detail": str(exc)},
        )

    @app.exception_handler(TrashEntryNotFoundError)
    async def _trash_not_found(
        _request: Request, exc: TrashEntryNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"error": "trash_entry_not_found", "detail": str(exc)},
        )

    @app.exception_handler(ValidationError)
    async def _pydantic_validation(
        _request: Request, exc: ValidationError
    ) -> JSONResponse:
        # Triggered when domain code (e.g. core/page_apply.apply_patch) calls
        # WikiPageFrontmatter.model_validate on a bad PATCH payload. Distinct
        # from FastAPI's RequestValidationError, which already returns 422 for
        # malformed request bodies.
        return JSONResponse(
            status_code=422,
            content={"error": "validation_error", "detail": exc.errors()},
        )

    return app
