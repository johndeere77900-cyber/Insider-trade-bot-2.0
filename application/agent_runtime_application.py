from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from application.agent_runtime_runner import AgentRuntimeRunner


class AgentRuntimeApplicationError(RuntimeError):
    """Base error for runtime application operations."""


@dataclass(frozen=True)
class AgentRuntimeApplication:
    """
    Top-level application boundary around the agent runtime runner.

    This class provides the application-facing lifecycle and request
    interface. It does not implement business logic.
    """

    runner: AgentRuntimeRunner

    def __post_init__(self) -> None:
        if self.runner is None:
            raise ValueError("runner is required")

    def start(self) -> Any:
        return self.runner.start()

    def run(self) -> Any:
        return self.runner.run()

    def stop(self) -> Any:
        return self.runner.stop()

    def wait(self, timeout: float | None = None) -> bool:
        return self.runner.wait(timeout)

    def status(self) -> Any:
        return self.runner.status()

    def health(self) -> Any:
        return self.runner.health()

    def handle(self, request: Any) -> Any:
        return self.runner.handle(request)

    def metadata(self) -> Mapping[str, Any]:
        return self.runner.metadata()
