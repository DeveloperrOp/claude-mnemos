"""Compute the daemon HTTP base URL from GlobalSettings.

CLI/MCP processes are short-lived; SettingsStore reads the JSON file once
per call (cheap — file is small and OS-cached). Daemon itself caches in memory.
"""

from __future__ import annotations

import os

from claude_mnemos.daemon.config import DEFAULT_HOST
from claude_mnemos.state.settings import SettingsStore


def daemon_base_url(host: str = DEFAULT_HOST) -> str:
    settings = SettingsStore().get_global()
    return f"http://{host}:{settings.daemon_port}"


def daemon_url() -> str:
    """Base URL with the MNEMOS_DAEMON_URL env override taking precedence.

    Single source of truth for CLI modules (previously copied verbatim in
    cli.py / cli_project.py / cli_settings.py). The env override lets tests
    and power users point the CLI at a non-default daemon.
    """
    env = os.environ.get("MNEMOS_DAEMON_URL")
    return env if env is not None else daemon_base_url()
