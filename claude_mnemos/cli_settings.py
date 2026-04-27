"""CLI subgroup ``mnemos settings`` — get/set/reset per-project + global.

Reads always direct file access. Writes try the daemon REST first
(/settings/{name}, /settings/global — no /api/ prefix) and fall back to
direct SettingsStore when offline.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import httpx
from pydantic import BaseModel

from claude_mnemos.state.settings import (
    GlobalSettings,
    ProjectSettings,
    SettingsStore,
    get_by_dot_path,
    patch_dict_for_dot_path,
)

EXIT_SETTINGS_ERROR = 95


def _daemon_url() -> str:
    return os.environ.get("MNEMOS_DAEMON_URL", "http://127.0.0.1:5757")


def handle(args: argparse.Namespace) -> int:
    cmd = args.settings_command
    if cmd == "get":
        return _handle_get(args)
    if cmd == "set":
        return _handle_set(args)
    if cmd == "reset":
        return _handle_reset(args)
    print(f"unknown settings command: {cmd}", file=sys.stderr)
    return 2


def _handle_get(args: argparse.Namespace) -> int:
    store = SettingsStore()
    s: GlobalSettings | ProjectSettings = (
        store.get_global()
        if getattr(args, "is_global", False)
        else store.get_project(args.project)
    )
    if args.key is None:
        print(json.dumps(s.model_dump(mode="json"), indent=2))
        return 0
    try:
        value = get_by_dot_path(s, args.key)
    except AttributeError as exc:
        print(f"unknown setting key: {args.key} ({exc})", file=sys.stderr)
        return EXIT_SETTINGS_ERROR
    if isinstance(value, BaseModel):
        print(json.dumps(value.model_dump(mode="json"), indent=2))
    elif isinstance(value, list | dict) or getattr(args, "json", False):
        print(json.dumps(value))
    else:
        print(value)
    return 0


def _handle_set(args: argparse.Namespace) -> int:
    try:
        parsed: Any = json.loads(args.value)
    except json.JSONDecodeError as exc:
        print(f"value is not valid JSON: {exc}", file=sys.stderr)
        return EXIT_SETTINGS_ERROR
    patch = patch_dict_for_dot_path(args.key, parsed)
    target_global = getattr(args, "is_global", False)
    url = (
        f"{_daemon_url()}/settings/global"
        if target_global
        else f"{_daemon_url()}/settings/{args.project}"
    )
    try:
        r = httpx.patch(url, json=patch, timeout=2.0)
        if r.status_code == 200:
            return 0
        if r.status_code == 422:
            print(f"validation error: {r.text}", file=sys.stderr)
            return EXIT_SETTINGS_ERROR
        print(f"daemon error {r.status_code}: {r.text}", file=sys.stderr)
        return EXIT_SETTINGS_ERROR
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
        store = SettingsStore()
        try:
            if target_global:
                store.patch_global(patch)
            else:
                store.patch_project(args.project, patch)
            return 0
        except Exception as exc:  # noqa: BLE001
            print(f"settings error: {exc}", file=sys.stderr)
            return EXIT_SETTINGS_ERROR


def _handle_reset(args: argparse.Namespace) -> int:
    store = SettingsStore()
    target_global = getattr(args, "is_global", False)
    if args.key is None:
        if target_global:
            store.reset_global()
        else:
            store.reset_project(args.project)
        return 0
    defaults: GlobalSettings | ProjectSettings = (
        GlobalSettings() if target_global else ProjectSettings()
    )
    try:
        default_value = get_by_dot_path(defaults, args.key)
    except AttributeError as exc:
        print(f"unknown setting key: {args.key} ({exc})", file=sys.stderr)
        return EXIT_SETTINGS_ERROR
    if isinstance(default_value, BaseModel):
        default_value = default_value.model_dump(mode="json")
    patch = patch_dict_for_dot_path(args.key, default_value)
    try:
        if target_global:
            store.patch_global(patch)
        else:
            store.patch_project(args.project, patch)
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"settings error: {exc}", file=sys.stderr)
        return EXIT_SETTINGS_ERROR
