"""System-level toggles: autostart on/off, window-close action."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Body, HTTPException

from claude_mnemos.state.install_state import load_install_state

if TYPE_CHECKING:
    from claude_mnemos.tray.platform import AutostartManager

router = APIRouter()


def _resolve_target() -> tuple[str, list[str]]:
    from claude_mnemos.tray.__main__ import _resolve_target as r
    return r()


def _autostart_manager() -> AutostartManager:
    from claude_mnemos.tray.platform import get_autostart_manager
    target_exe, target_args = _resolve_target()
    return get_autostart_manager(target_exe=target_exe, target_args=target_args)


def _is_autostart_installed() -> bool:
    try:
        return _autostart_manager().is_installed()
    except Exception:
        return False


def _install_autostart() -> bool:
    _autostart_manager().install()
    return True


def _uninstall_autostart() -> bool:
    _autostart_manager().uninstall()
    return True


@router.get("/system/autostart")
def get_autostart() -> dict[str, Any]:
    return {"enabled": _is_autostart_installed()}


@router.post("/system/autostart")
def set_autostart(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    enabled = bool(payload.get("enabled"))
    try:
        if enabled:
            _install_autostart()
        else:
            _uninstall_autostart()
    except Exception as exc:
        raise HTTPException(500, f"autostart toggle failed: {exc}") from exc
    return {"ok": True, "enabled": enabled}


@router.get("/system/window-close-action")
def get_window_close_action() -> dict[str, Any]:
    state = load_install_state()
    return {"action": state.window_close_action or "hide"}


@router.post("/system/window-close-action")
def set_window_close_action(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    action = payload.get("action")
    if action not in ("hide", "quit"):
        raise HTTPException(400, "action must be 'hide' or 'quit'")
    state = load_install_state()
    state.window_close_action = action
    state.save()
    return {"ok": True, "action": action}
