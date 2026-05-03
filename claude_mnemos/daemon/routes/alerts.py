from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from claude_mnemos.daemon.alerts import Alerts
from claude_mnemos.daemon.schemas import WatchdogAlertResponse

router = APIRouter()


def _alerts(request: Request) -> Alerts | None:
    daemon = request.app.state.daemon
    if daemon is None:
        return None
    alerts = getattr(daemon, "alerts", None)
    if not isinstance(alerts, Alerts):
        return None
    return alerts


@router.get("/watchdog-events", response_model=list[WatchdogAlertResponse])
async def list_alerts(request: Request) -> list[WatchdogAlertResponse]:
    alerts = _alerts(request)
    if alerts is None:
        return []
    return [
        WatchdogAlertResponse(
            id=a.id,
            kind=a.kind,
            path=a.path,
            message=a.message,
            detected_at=a.detected_at,
        )
        for a in alerts.list()
    ]


@router.delete("/watchdog-events/{alert_id}", status_code=204)
async def clear_alert(alert_id: str, request: Request) -> Response:
    alerts = _alerts(request)
    if alerts is None or not alerts.clear(alert_id):
        raise HTTPException(
            status_code=404, detail={"error": "not_found", "id": alert_id}
        )
    return Response(status_code=204)
