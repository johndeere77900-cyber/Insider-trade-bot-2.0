from __future__ import annotations

from typing import Any, Mapping

from application.agent_process import AgentProcess


class AgentRunnerError(RuntimeError):
    """Base error for agent-runner operations."""


class AgentRunner:
    """
    Final runner boundary for the complete Insider Trade Bot process.

    This class delegates process lifecycle operations to AgentProcess and
    keeps the executable layer independent from internal agent components.
    """

    def __init__(self, process: AgentProcess) -> None:
        if process is None:
            raise ValueError("process is required")

        self._process = process

    @property
    def process(self) -> AgentProcess:
        return self._process

    def start(self) -> Any:
        return self._process.start()

    def run(self) -> Any:
        return self._process.run()

    def stop(self) -> Any:
        return self._process.stop()

    def wait(self, timeout: float | None = None) -> bool:
        return self._process.wait(timeout)

    def status(self) -> Any:
        return self._process.status()

    def health(self) -> Any:
        return self._process.health()

    def handle(self, request: Any) -> Any:
        return self._process.handle(request)

    def metadata(self) -> Mapping[str, Any]:
        return self._process.metadata()
