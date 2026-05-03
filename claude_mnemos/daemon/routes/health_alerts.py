"""REST API for the persistent health-alerts store.

These endpoints expose the on-disk ``~/.claude-mnemos/alerts.json`` produced by
the periodic ``health_checks_global`` cron task. The in-memory
``daemon/alerts.py`` (watchdog file events) is served by ``routes/alerts.py``
and is intentionally kept separate.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from claude_mnemos.state.alerts_store import AlertsStore, StoredAlert

router = APIRouter()


class SilenceRequest(BaseModel):
    duration_hours: float = Field(gt=0, le=24 * 365)


class HealthAlertsResponse(BaseModel):
    alerts: list[StoredAlert]
    silenced: list[StoredAlert]


@router.get("/health-alerts", response_model=HealthAlertsResponse)
async def list_health_alerts() -> HealthAlertsResponse:
    store = AlertsStore.load()
    return HealthAlertsResponse(
        alerts=store.active_alerts(),
        silenced=store.silenced_alerts(),
    )


@router.post("/health-alerts/{alert_id}/silence")
async def silence_health_alert(alert_id: str, body: SilenceRequest) -> dict[str, str]:
    store = AlertsStore.load()
    updated = store.silence(alert_id, timedelta(hours=body.duration_hours))
    if updated is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "id": alert_id})
    store.save()
    return {"status": "ok", "id": alert_id}


@router.post("/health-alerts/{alert_id}/dismiss")
async def dismiss_health_alert(alert_id: str) -> dict[str, str]:
    store = AlertsStore.load()
    updated = store.dismiss(alert_id)
    if updated is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "id": alert_id})
    store.save()
    return {"status": "ok", "id": alert_id}
