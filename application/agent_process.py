from __future__ import annotations

import signal
from threading import Event, Lock
from typing import Any, Mapping

from application.agent_application_entrypoint import (
    AgentApplicationEntrypoint,
)


class AgentProcessError(RuntimeError):
    """Base error for process-level agent operations."""


class AgentProcess:
    """
    Process-level coordinator for the complete Insider Trade Bot.

    This component owns graceful process lifecycle handling. It does not
    contain trading, research, ingestion, or strategy logic.
    """

    def __init__(
        self,
        entrypoint: AgentApplicationEntrypoint,
    ) -> None:
        if entrypoint is None:
            raise ValueError("entrypoint is required")

        self._entrypoint = entrypoint
        self._stop_event = Event()
        self._lock = Lock()
        self._started = False
        self._signal_handlers_installed = False

    @property
    def entrypoint(self) -> AgentApplicationEntrypoint:
        return self._entrypoint

    @property
    def started(self) -> bool:
        with self._lock:
            return self._started

    def install_signal_handlers(self) -> None:
        if self._signal_handlers_installed:
            return

        try:
            signal.signal(signal.SIGINT, self._handle_signal)
            signal.signal(signal.SIGTERM, self._handle_signal)
        except ValueError as exc:
            raise AgentProcessError(
                "Signal handlers can only be installed from the main thread"
            ) from exc

        self._signal_handlers_installed = True

    def start(self) -> Any:
        with self._lock:
            if self._started:
                return self._entrypoint.status()

            self.install_signal_handlers()

            result = self._entrypoint.start()

            self._started = True
            self._stop_event.clear()

            return result

    def stop(self) -> Any:
        with self._lock:
            if not self._started:
                self._stop_event.set()
                return None

            try:
                return self._entrypoint.stop()
            finally:
                self._started = False
                self._stop_event.set()

    def wait(self, timeout: float | None = None) -> bool:
        return self._stop_event.wait(timeout)

    def run(self) -> Any:
        self.start()

        try:
            self.wait()
            return self._entrypoint.status()
        finally:
            self.stop()

    def status(self) -> Any:
        return self._entrypoint.status()

    def health(self) -> Any:
        return self._entrypoint.health()

    def handle(self, request: Any) -> Any:
        if not self.started:
            raise AgentProcessError(
                "Agent process is not started"
            )

        return self._entrypoint.handle(request)

    def metadata(self) -> Mapping[str, Any]:
        return self._entrypoint.metadata()

    def _handle_signal(self, signum: int, frame: Any) -> None:
        self._stop_event.set()
