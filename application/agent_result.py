"""
Standard result envelope for top-level Insider Trade Bot operations.

This module keeps interface-facing responses consistent without embedding
domain-specific business logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class AgentResult:
    """Immutable result returned by the top-level agent boundary."""

    success: bool
    message: str
    data: Any = None
    error: Optional[str] = None
    request_id: Optional[str] = None
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(
        cls,
        *,
        message: str = "Operation completed successfully.",
        data: Any = None,
        request_id: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> "AgentResult":
        """Create a successful result."""
        return cls(
            success=True,
            message=message,
            data=data,
            error=None,
            request_id=request_id,
            metadata=dict(metadata or {}),
        )

    @classmethod
    def failure(
        cls,
        *,
        message: str,
        error: Optional[str] = None,
        data: Any = None,
        request_id: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> "AgentResult":
        """Create a failed result."""
        return cls(
            success=False,
            message=message,
            data=data,
            error=error,
            request_id=request_id,
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a serialization-friendly representation."""
        return {
            "success": self.success,
            "message": self.message,
            "data": self.data,
            "error": self.error,
            "request_id": self.request_id,
            "timestamp": self.timestamp.isoformat(),
            "metadata": dict(self.metadata),
      }
