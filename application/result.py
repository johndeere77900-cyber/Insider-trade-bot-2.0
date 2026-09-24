"""
Standard application result objects.

Provides a consistent response envelope for services and external interfaces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class ApplicationResult:
    """Standard result returned by an application operation."""

    success: bool
    status: str
    message: str = ""
    data: Any = None
    error: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @classmethod
    def ok(
        cls,
        *,
        data: Any = None,
        message: str = "",
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> "ApplicationResult":
        """Create a successful application result."""

        return cls(
            success=True,
            status="ok",
            message=message,
            data=data,
            metadata=dict(metadata or {}),
        )

    @classmethod
    def failure(
        cls,
        *,
        error: str,
        status: str = "error",
        message: str = "",
        data: Any = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> "ApplicationResult":
        """Create a failed application result."""

        if not error.strip():
            raise ValueError("error is required.")

        return cls(
            success=False,
            status=status,
            message=message,
            data=data,
            error=error,
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert the result to a serializable dictionary."""

        return {
            "success": self.success,
            "status": self.status,
            "message": self.message,
            "data": self.data,
            "error": self.error,
            "metadata": dict(self.metadata),
            "timestamp": self.timestamp.isoformat(),
  }
