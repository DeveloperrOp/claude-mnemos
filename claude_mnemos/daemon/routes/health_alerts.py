"""REST API for the persistent health-alerts store.

These endpoints expose the on-disk ``~/.claude-mnemos/alerts.json`` produced by
the periodic ``health_checks_global`` cron task. The in-memory
``daemon/alerts.py`` (watchdog file events) is served by ``routes/alerts.py``
and is intentionally kept separate.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from claude_mnemos.state.alerts_store import AlertsStore, StoredAlert

router = APIRouter()


class SilenceRequest(BaseModel):
    duration_hours: float = Field(gt=0, le=24 * 365)


class HealthAlertsResponse(BaseModel):
    alerts: list[StoredAlert]
    silenced: list[StoredAlert]


def _resolve_store(request: Request) -> AlertsStore:
    """Return the daemon's singleton store when running inside the daemon
    process, otherwise fall back to a fresh ``AlertsStore.load()``.

    The fallback path keeps test fixtures (``daemon=None``) and any future
    out-of-daemon caller working without changes.
    """
    daemon = getattr(request.app.state, "daemon", None)
    store = getattr(daemon, "alerts_store", None) if daemon is not None else None
    if store is None:
        return AlertsStore.load()
    return store


@router.get("/health-alerts", response_model=HealthAlertsResponse)
async def list_health_alerts(request: Request) -> HealthAlertsResponse:
    store = _resolve_store(request)
    return HealthAlertsResponse(
        alerts=store.active_alerts(),
        silenced=store.silenced_alerts(),
    )


@router.post("/health-alerts/{alert_id}/silence")
async def silence_health_alert(
    alert_id: str, body: SilenceRequest, request: Request,
) -> dict[str, str]:
    store = _resolve_store(request)
    updated = store.silence(alert_id, timedelta(hours=body.duration_hours))
    if updated is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "id": alert_id})
    store.save()
    return {"status": "ok", "id": alert_id}


@router.post("/health-alerts/{alert_id}/dismiss")
async def dismiss_health_alert(
    alert_id: str, request: Request,
) -> dict[str, str]:
    store = _resolve_store(request)
    updated = store.dismiss(alert_id)
    if updated is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "id": alert_id})
    store.save()
    return {"status": "ok", "id": alert_id}
