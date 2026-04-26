"""Plugin manifests are valid JSON with the required keys."""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_plugin_manifest_exists_and_parseable():
    manifest = _load_json(REPO_ROOT / ".claude-plugin" / "plugin.json")
    assert manifest["name"] == "claude-mnemos"
    assert isinstance(manifest["description"], str)
    assert manifest["description"]
    assert isinstance(manifest.get("version"), str)


def test_mcp_manifest_registers_mnemos_server():
    manifest = _load_json(REPO_ROOT / ".mcp.json")
    server = manifest["mcpServers"]["mnemos"]
    assert server["command"] == "python"
    assert "claude_mnemos.mcp" in server["args"]
    assert "--vault" in server["args"]
    assert "${MNEMOS_VAULT_ROOT}" in server["args"]


def test_hooks_manifest_registers_session_end():
    manifest = _load_json(REPO_ROOT / "hooks" / "hooks.json")
    handlers = manifest["hooks"]["SessionEnd"]
    assert isinstance(handlers, list)
    assert len(handlers) >= 1
    handler = handlers[0]
    assert "session_end.py" in handler["command"]
    assert handler["blocking"] is False
    assert isinstance(handler["timeout_seconds"], int)


def test_session_end_hook_script_exists():
    assert (REPO_ROOT / "hooks" / "session_end.py").is_file()
