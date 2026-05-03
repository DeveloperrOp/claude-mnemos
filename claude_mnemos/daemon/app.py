from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from claude_mnemos import __version__
from claude_mnemos.core.locks import LockTimeoutError
from claude_mnemos.core.ontology_apply import OntologyError
from claude_mnemos.core.page_apply import PageRestoreCollisionError
from claude_mnemos.core.pages import PageRefError
from claude_mnemos.core.trash import TrashEntryNotFoundError
from claude_mnemos.core.undo import UndoError
from claude_mnemos.daemon.routes.activity import router as activity_router
from claude_mnemos.daemon.routes.alerts import router as alerts_router
from claude_mnemos.daemon.routes.dashboard import router as dashboard_router
from claude_mnemos.daemon.routes.dead_letter import router as dead_letter_router
from claude_mnemos.daemon.routes.fs import router as fs_router
from claude_mnemos.daemon.routes.health import router as health_router
from claude_mnemos.daemon.routes.hooks import router as hooks_router
from claude_mnemos.daemon.routes.jobs import router as jobs_router
from claude_mnemos.daemon.routes.lint import router as lint_router
from claude_mnemos.daemon.routes.lost_sessions import router as lost_sessions_router
from claude_mnemos.daemon.routes.metrics import router as metrics_router
from claude_mnemos.daemon.routes.ontology import router as ontology_router
from claude_mnemos.daemon.routes.pages import router as pages_router
from claude_mnemos.daemon.routes.projects import router as projects_router
from claude_mnemos.daemon.routes.sessions import router as sessions_router
from claude_mnemos.daemon.routes.settings import router as settings_router
from claude_mnemos.daemon.routes.snapshots import router as snapshots_router
from claude_mnemos.daemon.routes.trash import router as trash_router
from claude_mnemos.daemon.routes.tray import router as tray_router
from claude_mnemos.daemon.routes.vault import router as vault_router
from claude_mnemos.lint.exceptions import LintCorruptError, LintError
from claude_mnemos.state.activity import ActivityCorruptError
from claude_mnemos.state.jobs import JobsCorruptError
from claude_mnemos.state.manifest import ManifestCorruptError
from claude_mnemos.state.ontology import OntologyCorruptError
from claude_mnemos.state.projects import ProjectMapCorruptError, ProjectMapError
from claude_mnemos.state.settings import SettingsCorruptError


def create_app(daemon: Any | None = None, static_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="claude-mnemos daemon", version=__version__)
    app.state.daemon = daemon

    # All API routers live under /api/* so the SPA mount at / can serve
    # client-side routes like /lost-sessions, /dead-letter etc. via fallback
    # to index.html without route conflicts.
    app.include_router(health_router, prefix="/api")
    app.include_router(vault_router, prefix="/api")
    app.include_router(activity_router, prefix="/api")
    app.include_router(snapshots_router, prefix="/api")
    app.include_router(ontology_router, prefix="/api")
    app.include_router(alerts_router, prefix="/api")
    app.include_router(lint_router, prefix="/api")
    app.include_router(jobs_router, prefix="/api")
    app.include_router(dashboard_router, prefix="/api")
    app.include_router(dead_letter_router, prefix="/api")
    app.include_router(pages_router, prefix="/api")
    app.include_router(trash_router, prefix="/api")
    app.include_router(sessions_router, prefix="/api")
    app.include_router(lost_sessions_router, prefix="/api")
    app.include_router(metrics_router, prefix="/api")
    app.include_router(projects_router, prefix="/api")
    app.include_router(settings_router, prefix="/api")
    app.include_router(tray_router, prefix="/api")
    app.include_router(fs_router, prefix="/api")
    app.include_router(hooks_router, prefix="/api")

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

    @app.exception_handler(ProjectMapCorruptError)
    async def _project_map_corrupt(_request: Request, exc: ProjectMapCorruptError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"error": "project_map_corrupt", "detail": str(exc)},
        )

    @app.exception_handler(ProjectMapError)
    async def _project_map_error(_request: Request, exc: ProjectMapError) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"error": "project_map_error", "detail": str(exc)},
        )

    @app.exception_handler(SettingsCorruptError)
    async def _settings_corrupt(_request: Request, exc: SettingsCorruptError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"error": "settings_corrupt", "detail": str(exc)},
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

    # Mount frontend static files (built by `frontend/`).
    # `StaticFiles(html=True)` only auto-serves index.html for the root path —
    # it returns 404 for non-existent paths like /onboarding, /project/x/settings.
    # SpaStaticFiles below adds proper SPA fallback: any 404 on a directory-style
    # path falls back to index.html so React Router can take over.
    # Mounted last so REST routers take precedence on overlapping paths.
    if static_dir is None:
        static_dir = Path(__file__).parent / "static"
    if (static_dir / "index.html").is_file():
        app.mount(
            "/",
            SpaStaticFiles(directory=static_dir, html=True),
            name="frontend",
        )

    return app


class SpaStaticFiles(StaticFiles):
    """StaticFiles subclass with SPA fallback to index.html on 404."""

    async def get_response(self, path: str, scope: Any) -> Any:  # type: ignore[override]
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                # Browsers implicitly request /favicon.ico — we ship favicon.svg.
                # Serve the SVG as fallback (Content-Type set to image/svg+xml).
                if path == "favicon.ico":
                    return await super().get_response("favicon.svg", scope)
                # Fall back to index.html so client-side router (React Router)
                # can resolve the path. Asset paths like /assets/foo.js still
                # 404 normally because they DO exist as files when the bundle
                # is built; missing-asset 404s are real errors.
                if "." in path.rsplit("/", 1)[-1]:
                    raise
                return await super().get_response("index.html", scope)
            raise
