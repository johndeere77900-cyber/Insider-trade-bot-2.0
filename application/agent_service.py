"""
High-level service boundary for the Insider Trade Bot agent.

This service coordinates the top-level agent runtime and request handling
without implementing domain-specific research or trading logic.
"""

from __future__ import annotations

from typing import Any, Optional

from application.agent import InsiderTradeAgent
from application.agent_context import AgentContext
from application.agent_errors import AgentExecutionError
from application.agent_result import AgentResult
from application.agent_runtime import AgentRuntime


class AgentService:
    """Public service boundary for interacting with the assembled agent."""

    def __init__(
        self,
        *,
        agent: InsiderTradeAgent,
        runtime: Optional[AgentRuntime] = None,
    ) -> None:
        self._agent = agent
        self._runtime = runtime or AgentRuntime(agent)

    @property
    def agent(self) -> InsiderTradeAgent:
        """Return the underlying assembled agent."""
        return self._agent

    @property
    def runtime(self) -> AgentRuntime:
        """Return the runtime controller."""
        return self._runtime

    def start(self) -> AgentResult:
        """Start the agent."""
        try:
            self._runtime.start()
        except Exception as exc:
            return AgentResult.failure(
                message="Agent startup failed.",
                error=str(exc),
            )

        return AgentResult.ok(
            message="Insider Trade Bot agent started.",
            data=self._runtime.status().to_dict(),
        )

    def stop(self) -> AgentResult:
        """Stop the agent."""
        try:
            self._runtime.stop()
        except Exception as exc:
            return AgentResult.failure(
                message="Agent shutdown failed.",
                error=str(exc),
            )

        return AgentResult.ok(
            message="Insider Trade Bot agent stopped.",
            data=self._runtime.status().to_dict(),
        )

    def status(self) -> AgentResult:
        """Return the current agent status."""
        try:
            status = self._runtime.status()
        except Exception as exc:
            return AgentResult.failure(
                message="Unable to obtain agent status.",
                error=str(exc),
            )

        return AgentResult.ok(
            message="Agent status retrieved.",
            data=status.to_dict(),
        )

    def health(self) -> AgentResult:
        """Return agent health information."""
        try:
            health = self._runtime.health()
        except Exception as exc:
            return AgentResult.failure(
                message="Unable to obtain agent health.",
                error=str(exc),
            )

        return AgentResult.ok(
            message="Agent health retrieved.",
            data=health,
        )

    def handle(
        self,
        request: Any,
        *,
        context: Optional[AgentContext] = None,
    ) -> AgentResult:
        """
        Handle an application-level request.

        The context is attached to request metadata when possible, but the
        underlying application controller remains responsible for command
        interpretation and execution.
        """
        try:
            self._runtime.require_running()

            enriched_request = self._attach_context(
                request=request,
                context=context,
            )

            result = self._agent.handle(enriched_request)

            if isinstance(result, AgentResult):
                return result

            return AgentResult.ok(
                message="Request handled.",
                data=result,
                request_id=(
                    context.request_id
                    if context is not None
                    else None
                ),
            )

        except Exception as exc:
            if isinstance(exc, AgentExecutionError):
                error = str(exc)
            else:
                error = str(exc)

            return AgentResult.failure(
                message="Agent request failed.",
                error=error,
                request_id=(
                    context.request_id
                    if context is not None
                    else None
                ),
            )

    @staticmethod
    def _attach_context(
        *,
        request: Any,
        context: Optional[AgentContext],
    ) -> Any:
        """
        Attach context metadata to dictionary-like requests.

        Non-dictionary request objects are passed through unchanged so that
        existing command/request types are not mutated or replaced.
        """
        if context is None:
            return request

        if isinstance(request, dict):
            enriched = dict(request)

            existing_metadata = enriched.get("metadata", {})
            if not isinstance(existing_metadata, dict):
                existing_metadata = {}

            enriched["metadata"] = {
                **existing_metadata,
                "agent_context": context.to_dict(),
            }

            return enriched

        return request
