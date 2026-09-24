"""
Execution context for the top-level Insider Trade Bot agent.

The context carries request-scoped metadata without containing business
logic or mutable trading state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class AgentContext:
    """
    Immutable context associated with one agent operation.

    Attributes:
        request_id: Unique identifier for tracing the operation.
        user_id: Optional identifier of the requesting user.
        source: Interface that originated the request, such as Telegram.
        received_at: UTC timestamp when the context was created.
        metadata: Additional non-sensitive request metadata.
    """

    request_id: str
    user_id: Optional[str] = None
    source: str = "internal"
    received_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.request_id or not self.request_id.strip():
            raise ValueError("request_id must not be empty.")

        if not self.source or not self.source.strip():
            raise ValueError("source must not be empty.")

        if self.received_at.tzinfo is None:
            raise ValueError("received_at must be timezone-aware.")

    def with_metadata(self, **values: Any) -> "AgentContext":
        """
        Return a new context with additional metadata.

        Existing metadata is preserved unless a key is explicitly replaced.
        """
        merged = dict(self.metadata)
        merged.update(values)

        return AgentContext(
            request_id=self.request_id,
            user_id=self.user_id,
            source=self.source,
            received_at=self.received_at,
            metadata=merged,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a serializable representation of the context."""
        return {
            "request_id": self.request_id,
            "user_id": self.user_id,
            "source": self.source,
            "received_at": self.received_at.isoformat(),
            "metadata": dict(self.metadata),
  }
