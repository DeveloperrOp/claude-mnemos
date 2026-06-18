"""Tests for Supervisor verbs added in Task 4 of E1 desktop launcher plan:
``open_launcher`` / ``pause_daemon`` / ``resume_daemon`` / ``shutdown``.

All subprocess and HTTP interactions are mocked — these tests must NEVER
actually spawn processes or hit a network endpoint.
"""

from __future__ import annotations

from pathlib import Path


def test_supervisor_open_launcher_spawns_subprocess(tmp_path: Path, monkeypatch) -> None:
    """When no launcher_proc alive, open_launcher spawns one as detached subprocess."""
    pid_file = tmp_path / "daemon.pid"
    from claude_mnemos.tray.supervisor import Supervisor

    sv = Supervisor(daemon_pid_file=pid_file, log_path=None)

    spawned: list = []

    class FakeProc:
        def __init__(self, cmd):
            self.cmd = cmd

        def poll(self):
            return None  # alive

    def fake_popen(cmd, *args, **kwargs):
        spawned.append(cmd)
        return FakeProc(cmd)

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    sv.open_launcher()

    assert len(spawned) == 1
    cmd_str = " ".join(str(c) for c in spawned[0])
    assert "launcher" in cmd_str


def test_supervisor_open_launcher_focuses_existing(tmp_path: Path, monkeypatch) -> None:
    """If launcher_proc is alive, send IPC 'show' instead of spawning a duplicate."""
    pid_file = tmp_path / "daemon.pid"
    from claude_mnemos.tray.supervisor import Supervisor

    sv = Supervisor(daemon_pid_file=pid_file, log_path=None)

    class AliveProc:
        def poll(self):
            return None  # alive

    sv.launcher_proc = AliveProc()

    sent: list = []
    monkeypatch.setattr(
        "claude_mnemos.tray.supervisor.ipc_send",
        lambda addr, msg, **kw: sent.append((addr, msg)) or True,
    )
    sv.open_launcher()
    assert sent and sent[0][1] == "show"


def test_supervisor_pause_resume_daemon_post_endpoints(tmp_path: Path) -> None:
    """pause_daemon/resume_daemon POST to /api/daemon/{pause,resume}."""
    pid_file = tmp_path / "daemon.pid"
    from claude_mnemos.tray.supervisor import Supervisor

    sv = Supervisor(daemon_pid_file=pid_file, log_path=None)

    posts: list = []

    class FakeHttp:
        def post(self, url, **kw):
            posts.append(url)

            class R:
                status_code = 200

            return R()

    sv._http = FakeHttp()
    sv.pause_daemon()
    sv.resume_daemon()

    paused = [u for u in posts if "pause" in u]
    resumed = [u for u in posts if "resume" in u]
    assert paused, f"expected pause URL in {posts}"
    assert resumed, f"expected resume URL in {posts}"


def test_post_to_daemon_works_before_first_tick(tmp_path: Path, monkeypatch) -> None:
    """A pause/resume issued before the first tick() (so ``self._http`` is still
    None) must still POST — via the lazy ``_http_client()`` — not be dropped."""
    pid_file = tmp_path / "daemon.pid"
    from claude_mnemos.tray.supervisor import Supervisor

    sv = Supervisor(daemon_pid_file=pid_file, log_path=None)
    assert sv._http is None  # never ticked → lazy client not built yet (bug repro)

    posted: dict = {}

    class FakeClient:
        def post(self, url, **kw):
            posted["url"] = url

    monkeypatch.setattr(sv, "_http_client", lambda: FakeClient())
    sv._post_to_daemon("/api/daemon/pause")
    assert posted.get("url", "").endswith("/api/daemon/pause")


def test_supervisor_shutdown_terminates_launcher_then_stops_daemon(
    tmp_path: Path, monkeypatch
) -> None:
    """shutdown(): kill launcher subprocess (if any), then call stop()."""
    pid_file = tmp_path / "daemon.pid"
    from claude_mnemos.tray.supervisor import Supervisor

    sv = Supervisor(daemon_pid_file=pid_file, log_path=None)

    terminated = {"launcher": 0}

    class FakeLauncher:
        def __init__(self):
            self._alive = True

        def poll(self):
            return None if self._alive else 0

        def terminate(self):
            terminated["launcher"] += 1
            self._alive = False

        def wait(self, timeout=None):
            return 0

    sv.launcher_proc = FakeLauncher()

    stop_called: list = []
    monkeypatch.setattr(sv, "stop", lambda **kw: stop_called.append(True))

    sv.shutdown()
    assert terminated["launcher"] == 1
    assert stop_called == [True]
