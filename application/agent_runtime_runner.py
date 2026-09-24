from __future__ import annotations

from typing import Any, Mapping

from application.agent_runtime_process import AgentRuntimeProcess


class AgentRuntimeRunnerError(RuntimeError):
    """Base error for runtime-runner operations."""


class AgentRuntimeRunner:
    """
    Final runner boundary for the long-running agent process.

    The runner delegates lifecycle work to AgentRuntimeProcess and keeps
    process orchestration separate from agent business logic.
    """

    def __init__(
        self,
        process: AgentRuntimeProcess,
    ) -> None:
        if process is None:
            raise ValueError("process is required")

        self._process = process

    @property
    def process(self) -> AgentRuntimeProcess:
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
