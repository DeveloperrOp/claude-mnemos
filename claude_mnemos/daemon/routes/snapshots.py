from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from claude_mnemos.core.locks import pipeline_lock
from claude_mnemos.core.snapshots import (
    SnapshotInfo,
    create_manual_snapshot,
    delete_snapshot,
    list_snapshots,
    parse_snapshot_name,
    restore_from_snapshot,
)
from claude_mnemos.state.activity import ActivityEntry, ActivityLog

router = APIRouter()


class CreateSnapshotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str | None = Field(default=None, max_length=128)


class RestoreSnapshotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    success: bool
    snapshot: str
    activity_id: str


def _validate_snapshot_name(name: str) -> None:
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_name", "name": name},
        )
    if Path(name).is_absolute():
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_name", "name": name},
        )
    if parse_snapshot_name(name) is None:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_name", "name": name},
        )


@router.get("/snapshots")
async def list_snapshots_endpoint(request: Request) -> dict[str, list[SnapshotInfo]]:
    vault: Path = request.app.state.vault_root
    return {"snapshots": list_snapshots(vault)}


@router.post("/snapshots", response_model=SnapshotInfo, status_code=201)
def create_snapshot_endpoint(
    body: CreateSnapshotRequest, request: Request
) -> SnapshotInfo:
    vault: Path = request.app.state.vault_root
    try:
        with pipeline_lock(vault):
            try:
                snap_path = create_manual_snapshot(vault, label=body.label)
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail={"error": "invalid_name", "detail": str(exc)},
                ) from exc
    except HTTPException:
        raise
    parsed = parse_snapshot_name(snap_path.name)
    assert parsed is not None  # we just created it
    return SnapshotInfo(
        name=snap_path.name,
        kind=parsed.kind,
        timestamp=parsed.timestamp,
        op_id=parsed.op_id,
        op_type=parsed.op_type,
        label=parsed.label,
        size_bytes=0,  # newly created — size not interesting
        path=f".backups/{snap_path.name}",
    )


@router.delete("/snapshots/{name}")
def delete_snapshot_endpoint(name: str, request: Request) -> dict[str, str]:
    vault: Path = request.app.state.vault_root
    _validate_snapshot_name(name)
    with pipeline_lock(vault):
        try:
            delete_snapshot(vault, name)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail={"error": "not_found", "name": name}
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail={"error": "invalid_name", "detail": str(exc)}
            ) from exc
    return {"deleted": name}


@router.post(
    "/snapshots/{name}/restore", response_model=RestoreSnapshotResponse
)
def restore_snapshot_endpoint(name: str, request: Request) -> RestoreSnapshotResponse:
    vault: Path = request.app.state.vault_root
    _validate_snapshot_name(name)
    snap_path = vault / ".backups" / name
    if not snap_path.is_dir():
        raise HTTPException(
            status_code=404, detail={"error": "not_found", "name": name}
        )

    with pipeline_lock(vault):
        result = restore_from_snapshot(vault, snap_path)
        if not result.success:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "restore_failed",
                    "detail": result.error or "unknown",
                    "recovery_hint": result.recovery_hint,
                },
            )

        # Append manual_restore activity entry
        log = ActivityLog.load(vault)
        new_id = uuid4().hex
        now = datetime.now(UTC)
        log.append(
            ActivityEntry(
                id=new_id,
                timestamp=now,
                operation_type="manual_restore",
                status="success",
                snapshot_path=None,
                can_undo=False,
                affected_pages=[],
                metadata={"restored_from": f".backups/{name}"},
            )
        )
        log.save(vault)

    return RestoreSnapshotResponse(success=True, snapshot=name, activity_id=new_id)
