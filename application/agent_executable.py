from __future__ import annotations

from typing import Any, Mapping

from application.agent_runner import AgentRunner


class AgentExecutableError(RuntimeError):
    """Base error for executable-level agent operations."""


class AgentExecutable:
    """
    Final executable boundary for the Insider Trade Bot.

    The executable delegates lifecycle work to AgentRunner and contains no
    trading, research, ingestion, or strategy logic.
    """

    def __init__(self, runner: AgentRunner) -> None:
        if runner is None:
            raise ValueError("runner is required")

        self._runner = runner

    @property
    def runner(self) -> AgentRunner:
        return self._runner

    def start(self) -> Any:
        return self._runner.start()

    def run(self) -> Any:
        return self._runner.run()

    def stop(self) -> Any:
        return self._runner.stop()

    def wait(self, timeout: float | None = None) -> bool:
        return self._runner.wait(timeout)

    def status(self) -> Any:
        return self._runner.status()

    def health(self) -> Any:
        return self._runner.health()

    def handle(self, request: Any) -> Any:
        return self._runner.handle(request)

    def metadata(self) -> Mapping[str, Any]:
        return self._runner.metadata()
