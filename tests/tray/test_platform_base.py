from __future__ import annotations

from claude_mnemos.tray.platform.base import AutostartManager, AutostartStatus


def test_autostart_status_dataclass_fields() -> None:
    status = AutostartStatus(installed=True, path="/tmp/x.lnk")
    assert status.installed is True
    assert status.path == "/tmp/x.lnk"


def test_autostart_status_default_path_none() -> None:
    status = AutostartStatus(installed=False)
    assert status.path is None


def test_autostart_manager_is_runtime_checkable_protocol() -> None:
    """A class with the right methods should pass isinstance check."""

    class Stub:
        def install(self) -> None: ...
        def uninstall(self) -> None: ...
        def status(self) -> AutostartStatus:
            return AutostartStatus(installed=False)
        def is_installed(self) -> bool:
            return False

    assert isinstance(Stub(), AutostartManager)


def test_autostart_manager_rejects_class_missing_methods() -> None:
    class Incomplete:
        def install(self) -> None: ...

    assert not isinstance(Incomplete(), AutostartManager)
