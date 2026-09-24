"""
Runtime context for Insider Trade Bot 2.0.

This context provides immutable metadata about the currently running agent
instance without storing domain or trading state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class AgentRuntimeContext:
    """Immutable metadata describing one agent runtime instance."""

    runtime_id: str
    environment: str
    started_at: Optional[datetime] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.runtime_id.strip():
            raise ValueError("runtime_id must not be empty.")

        if not self.environment.strip():
            raise ValueError("environment must not be empty.")

        if self.started_at is not None and self.started_at.tzinfo is None:
            raise ValueError("started_at must be timezone-aware.")

    @classmethod
    def create(
        cls,
        *,
        runtime_id: str,
        environment: str,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> "AgentRuntimeContext":
        """Create a runtime context with the current UTC timestamp."""
        return cls(
            runtime_id=runtime_id,
            environment=environment,
            started_at=datetime.now(timezone.utc),
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a serialization-friendly representation."""
        return {
            "runtime_id": self.runtime_id,
            "environment": self.environment,
            "started_at": (
                self.started_at.isoformat()
                if self.started_at is not None
                else None
            ),
            "metadata": dict(self.metadata),
  }
