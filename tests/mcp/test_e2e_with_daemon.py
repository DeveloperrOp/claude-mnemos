"""End-to-end: real mnemos daemon subprocess + in-process MCP tools.

Marked `slow`: spawns Python interpreter and binds to a TCP port.
"""

from __future__ import annotations

import contextlib
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psutil
import pytest
from mcp import types

from claude_mnemos.mcp.config import MCPConfig
from claude_mnemos.mcp.server import build_server

pytestmark = pytest.mark.skip(
    reason=(
        "Plan #13b-β1 Task 12 stubbed MnemosDaemon.run() as NotImplementedError "
        "until Task 16 wires _bootstrap_runtimes + uvicorn. Re-enable this "
        "subprocess e2e once Task 16 lands."
    )
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_health(url: str, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=0.5)
            if r.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    return False


async def _call_tool(server, name: str, arguments: dict | None = None):
    handler = server.request_handlers[types.CallToolRequest]
    request = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(name=name, arguments=arguments or {}),
    )
    result = await handler(request)
    return result.root


@pytest.mark.slow
async def test_mcp_create_and_delete_snapshot_via_real_daemon(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    pid_file = tmp_path / "daemon.pid"
    port = _free_port()

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "claude_mnemos.daemon",
            "run",
            "--vault",
            str(vault),
            "--port",
            str(port),
            "--pid-file",
            str(pid_file),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        assert _wait_for_health(f"http://127.0.0.1:{port}/health"), (
            f"daemon failed to start on :{port}"
        )

        config = MCPConfig(
            vault_root=vault, daemon_url=f"http://127.0.0.1:{port}"
        )
        server = build_server(config)

        # Create manual snapshot via MCP
        result = await _call_tool(
            server, "create_snapshot", {"label": "mcp-e2e"}
        )
        body = json.loads(result.content[0].text)
        assert body["kind"] == "manual"
        assert body["label"] == "mcp-e2e"
        snap_name = body["name"]
        assert (vault / ".backups" / snap_name).is_dir()

        # List via MCP read tool
        list_result = await _call_tool(server, "get_status", {})
        status = json.loads(list_result.content[0].text)
        assert status["snapshots"] >= 1

        # Delete via MCP
        del_result = await _call_tool(
            server, "delete_snapshot", {"name": snap_name}
        )
        del_body = json.loads(del_result.content[0].text)
        assert del_body["deleted"] == snap_name
        assert not (vault / ".backups" / snap_name).exists()

    finally:
        with contextlib.suppress(psutil.NoSuchProcess):
            psutil.Process(proc.pid).terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        if pid_file.exists():
            pid_file.unlink()


@pytest.mark.slow
async def test_mcp_undo_unreachable_daemon_returns_helpful_error(tmp_path: Path):
    """No daemon running → write tool returns text with 'mnemos daemon start' hint."""
    vault = tmp_path / "vault"
    vault.mkdir()
    config = MCPConfig(
        vault_root=vault,
        daemon_url=f"http://127.0.0.1:{_free_port()}",
        daemon_timeout_s=2.0,
    )
    server = build_server(config)
    result = await _call_tool(server, "undo_operation", {"op_id": "abc"})
    text = result.content[0].text
    # Either ConnectError ("not reachable") or timeout — both mean daemon offline
    assert "daemon" in text
    assert ("not reachable" in text) or ("timeout" in text)
