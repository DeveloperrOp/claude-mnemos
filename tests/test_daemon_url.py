from __future__ import annotations

from pathlib import Path


def _set_home(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))


def test_daemon_base_url_default(tmp_path, monkeypatch):
    _set_home(tmp_path, monkeypatch)
    from claude_mnemos.daemon_url import daemon_base_url
    assert daemon_base_url() == "http://127.0.0.1:5757"


def test_daemon_base_url_reads_from_settings(tmp_path, monkeypatch):
    _set_home(tmp_path, monkeypatch)
    from claude_mnemos.state.settings import GlobalSettings, SettingsStore
    SettingsStore().set_global(GlobalSettings(daemon_port=5800))
    from claude_mnemos.daemon_url import daemon_base_url
    assert daemon_base_url() == "http://127.0.0.1:5800"


def test_daemon_base_url_custom_host(tmp_path, monkeypatch):
    _set_home(tmp_path, monkeypatch)
    from claude_mnemos.daemon_url import daemon_base_url
    assert daemon_base_url(host="0.0.0.0") == "http://0.0.0.0:5757"


def test_cli_project_uses_daemon_base_url(tmp_path, monkeypatch):
    """When user pins daemon_port via global settings, CLI hits the new port."""
    _set_home(tmp_path, monkeypatch)
    # Ensure MNEMOS_DAEMON_URL env var is absent so the fallback code runs
    monkeypatch.delenv("MNEMOS_DAEMON_URL", raising=False)

    from claude_mnemos.state.settings import GlobalSettings, SettingsStore
    SettingsStore().set_global(GlobalSettings(daemon_port=5800))

    captured: dict[str, str] = {}

    def fake_post(url: str, **kw: object) -> object:
        captured["url"] = url
        import httpx
        return httpx.Response(201, json={})

    import httpx
    monkeypatch.setattr(httpx, "post", fake_post)

    # Reload module so _daemon_url() picks up fresh state (no cached import)
    import importlib

    import claude_mnemos.cli_project as mod
    importlib.reload(mod)

    import argparse
    ns = argparse.Namespace(
        name="myproject",
        vault=tmp_path / "vault",
        cwd_pattern=["~/code/*"],
    )
    rc = mod._handle_add(ns)
    assert rc == 0, f"_handle_add returned {rc}"
    assert "url" in captured, "httpx.post was never called — _handle_add did not reach the daemon"
    assert captured["url"].startswith("http://127.0.0.1:5800"), (
        f"expected port 5800 but got: {captured['url']!r}"
    )


def test_cli_jobs_uses_daemon_base_url(tmp_path, monkeypatch):
    """_post_or_delete_to_daemon in cli.py should respect configured daemon_port."""
    _set_home(tmp_path, monkeypatch)
    monkeypatch.delenv("MNEMOS_DAEMON_URL", raising=False)

    from claude_mnemos.state.settings import GlobalSettings, SettingsStore
    SettingsStore().set_global(GlobalSettings(daemon_port=5800))

    captured: dict[str, str] = {}

    def fake_request(_method: str, url: str, **kw: object) -> object:
        captured["url"] = url
        import httpx
        return httpx.Response(204)

    import httpx
    monkeypatch.setattr(httpx, "request", fake_request)

    import importlib

    import claude_mnemos.cli as cli_mod
    importlib.reload(cli_mod)

    import argparse
    ns = argparse.Namespace(job_id="abc123")
    rc = cli_mod._post_or_delete_to_daemon(ns, method="DELETE", path="/jobs/abc123")
    assert rc == 0, f"_post_or_delete_to_daemon returned {rc}"
    assert "url" in captured, "httpx.request was never called"
    assert captured["url"].startswith("http://127.0.0.1:5800"), (
        f"expected port 5800 but got: {captured['url']!r}"
    )
