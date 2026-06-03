from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from claude_mnemos.core.locks import pipeline_lock
from claude_mnemos.core.snapshots import (
    RestorePreview,
    SnapshotInfo,
    compute_restore_preview,
    create_manual_snapshot,
    delete_snapshot,
    list_snapshots,
    list_trash,
    parse_snapshot_name,
    purge_trash,
    restore_from_trash,
)
from claude_mnemos.daemon.routes._helpers import get_runtime
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


@router.get("/snapshots/{project}")
async def list_snapshots_endpoint(
    project: str, request: Request
) -> dict[str, list[SnapshotInfo]]:
    runtime = get_runtime(request, project)
    return {"snapshots": list_snapshots(runtime.vault_root)}


# Declared before the `/{name}/...` routes so the literal `trash` segment is
# matched here rather than captured as a {name} path param.
@router.get("/snapshots/{project}/trash")
async def list_trash_endpoint(
    project: str, request: Request
) -> dict[str, list[SnapshotInfo]]:
    runtime = get_runtime(request, project)
    return {"snapshots": list_trash(runtime.vault_root)}


@router.post("/snapshots/{project}", response_model=SnapshotInfo, status_code=201)
def create_snapshot_endpoint(
    project: str, body: CreateSnapshotRequest, request: Request
) -> SnapshotInfo:
    runtime = get_runtime(request, project)
    vault = runtime.vault_root
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


@router.delete("/snapshots/{project}/{name}")
def delete_snapshot_endpoint(
    project: str, name: str, request: Request
) -> dict[str, str]:
    runtime = get_runtime(request, project)
    vault = runtime.vault_root
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


@router.post("/snapshots/{project}/{name}/restore-from-trash")
def restore_from_trash_endpoint(
    project: str, name: str, request: Request
) -> dict[str, str]:
    runtime = get_runtime(request, project)
    vault = runtime.vault_root
    _validate_snapshot_name(name)
    with pipeline_lock(vault):
        try:
            restore_from_trash(vault, name)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "not_found",
                    "message": "Этот снимок уже удалён из корзины или восстановлен.",
                    "name": name,
                },
            ) from exc
        except FileExistsError as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "conflict",
                    "message": (
                        f"Снимок с именем «{name}» уже существует — "
                        "восстановление из корзины невозможно."
                    ),
                },
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail={"error": "invalid_name", "detail": str(exc)}
            ) from exc
    return {"restored": name}


@router.delete("/snapshots/{project}/{name}/purge")
def purge_trash_endpoint(
    project: str, name: str, request: Request
) -> dict[str, str]:
    runtime = get_runtime(request, project)
    vault = runtime.vault_root
    _validate_snapshot_name(name)
    with pipeline_lock(vault):
        try:
            purge_trash(vault, name)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "not_found",
                    "message": "Этот снимок уже удалён из корзины.",
                    "name": name,
                },
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail={"error": "invalid_name", "detail": str(exc)}
            ) from exc
    return {"purged": name}


@router.post(
    "/snapshots/{project}/{name}/restore", response_model=RestoreSnapshotResponse
)
async def restore_snapshot_endpoint(
    project: str, name: str, request: Request
) -> RestoreSnapshotResponse:
    runtime = get_runtime(request, project)
    vault = runtime.vault_root
    _validate_snapshot_name(name)
    snap_path = vault / ".backups" / name
    if not snap_path.is_dir():
        raise HTTPException(
            status_code=404, detail={"error": "not_found", "name": name}
        )

    with pipeline_lock(vault):
        try:
            # restore_with_quiesce closes the sqlite jobs.db handle around the
            # swap so the vault-dir rename succeeds on Windows (then reopens it).
            result = await runtime.restore_with_quiesce(snap_path)
        except Exception as exc:  # noqa: BLE001
            import traceback as _tb
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "restore_failed",
                    "message": (
                        f"Не удалось восстановить снимок: {type(exc).__name__}: {exc}"
                    ),
                    "traceback": _tb.format_exc(limit=5),
                },
            ) from exc
        if not result.success:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "restore_failed",
                    "message": (
                        "Восстановление не завершилось: "
                        f"{result.error or 'неизвестная ошибка'}"
                    ),
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


@router.get("/snapshots/{project}/{name}/preview", response_model=RestorePreview)
def snapshot_preview_endpoint(
    project: str, name: str, request: Request
) -> RestorePreview:
    runtime = get_runtime(request, project)
    _validate_snapshot_name(name)
    try:
        return compute_restore_preview(runtime.vault_root, name)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail={"error": "not_found", "name": name}
        ) from exc
