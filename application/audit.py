"""
Application audit service.

Provides a lightweight application-level audit boundary for recording
important service actions without embedding audit behavior into domain
components.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class AuditEvent:
    """Immutable representation of an application audit event."""

    event_id: str
    action: str
    source: str
    status: str
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    user_id: Optional[str] = None
    request_id: Optional[str] = None
    details: Mapping[str, Any] = field(default_factory=dict)


class ApplicationAudit:
    """
    Application audit collector.

    The collector is intentionally storage-neutral. A persistent audit
    repository can be injected later without coupling the application layer
    to a specific database implementation.
    """

    def __init__(self, repository: Any = None) -> None:
        self.repository = repository
        self._events: list[AuditEvent] = []

    def record(
        self,
        *,
        event_id: str,
        action: str,
        source: str,
        status: str,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None,
        details: Optional[Mapping[str, Any]] = None,
    ) -> AuditEvent:
        """Create and record an audit event."""

        if not event_id.strip():
            raise ValueError("event_id is required.")

        if not action.strip():
            raise ValueError("action is required.")

        if not source.strip():
            raise ValueError("source is required.")

        if not status.strip():
            raise ValueError("status is required.")

        event = AuditEvent(
            event_id=event_id,
            action=action,
            source=source,
            status=status,
            user_id=user_id,
            request_id=request_id,
            details=dict(details or {}),
        )

        self._events.append(event)

        if self.repository is not None:
            self._persist(event)

        return event

    def list_events(self) -> tuple[AuditEvent, ...]:
        """Return the audit events recorded by this collector."""

        return tuple(self._events)

    def _persist(self, event: AuditEvent) -> None:
        """Persist an event using a supported repository interface."""

        if hasattr(self.repository, "save"):
            self.repository.save(event)
            return

        if hasattr(self.repository, "create"):
            self.repository.create(event)
            return

        raise TypeError(
            "Audit repository must provide either 'save' or 'create'."
  )
