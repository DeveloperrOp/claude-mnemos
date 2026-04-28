"""Compute the daemon HTTP base URL from GlobalSettings.

CLI/MCP processes are short-lived; SettingsStore reads the JSON file once
per call (cheap — file is small and OS-cached). Daemon itself caches in memory.
"""

from __future__ import annotations

from claude_mnemos.daemon.config import DEFAULT_HOST
from claude_mnemos.state.settings import SettingsStore


def daemon_base_url(host: str = DEFAULT_HOST) -> str:
    settings = SettingsStore().get_global()
    return f"http://{host}:{settings.daemon_port}"
