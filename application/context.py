"""
Application request context.

Carries request-level information across application services without
embedding interface-specific details inside the domain components.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class ApplicationContext:
    """Context associated with a single application request."""

    request_id: str
    source: str
    user_id: Optional[str] = None
    received_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def with_metadata(
        self,
        **additional_metadata: Any,
    ) -> "ApplicationContext":
        """Return a new context with additional metadata."""

        merged = dict(self.metadata)
        merged.update(additional_metadata)

        return ApplicationContext(
            request_id=self.request_id,
            source=self.source,
            user_id=self.user_id,
            received_at=self.received_at,
            metadata=merged,
  )
