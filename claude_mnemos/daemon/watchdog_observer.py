"""Thin wrapper around watchdog.observers.Observer scoped to a single vault."""

from __future__ import annotations

import logging
from pathlib import Path

from watchdog.observers import Observer

from claude_mnemos.daemon.watchdog_handler import VaultChangeHandler

logger = logging.getLogger(__name__)


class VaultObserver:
    """Wraps a watchdog Observer scheduled on the vault root, recursive.

    Lifecycle: construct -> start() -> ... -> stop(). Observer runs in a
    background thread; the public API is thread-safe.
    """

    def __init__(self, vault: Path, handler: VaultChangeHandler) -> None:
        self.vault = vault
        self.handler = handler
        self._observer: Observer | None = None  # type: ignore[valid-type]

    def start(self) -> None:
        if self._observer is not None:
            raise RuntimeError("VaultObserver already started")
        observer = Observer()
        observer.schedule(self.handler, str(self.vault), recursive=True)
        observer.start()
        self._observer = observer

    def stop(self, *, timeout: float = 5.0) -> None:
        if self._observer is None:
            return
        try:
            self._observer.stop()
            self._observer.join(timeout=timeout)
        except Exception:
            logger.exception("VaultObserver stop failed")
        finally:
            self._observer = None

    @property
    def is_running(self) -> bool:
        return self._observer is not None and self._observer.is_alive()
