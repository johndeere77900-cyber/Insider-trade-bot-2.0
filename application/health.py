"""
Application health checks.

Provides a lightweight, non-destructive health/status layer for the agent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class HealthCheck:
    """Result of a single component health check."""

    name: str
    status: str
    message: str


class ApplicationHealth:
    """Runs non-destructive health checks against application services."""

    def __init__(
        self,
        *,
        application_service: Any,
        database_connection: Optional[Any] = None,
    ) -> None:
        self.application_service = application_service
        self.database_connection = database_connection

    def check(self) -> Mapping[str, Any]:
        """Return the current application health state."""

        checks = [
            self._check_application(),
            self._check_database(),
        ]

        failed = any(item.status == "unhealthy" for item in checks)

        return {
            "status": "unhealthy" if failed else "healthy",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "checks": [
                {
                    "name": item.name,
                    "status": item.status,
                    "message": item.message,
                }
                for item in checks
            ],
        }

    def _check_application(self) -> HealthCheck:
        """Check that the application service is reachable."""

        if self.application_service is None:
            return HealthCheck(
                name="application",
                status="unhealthy",
                message="Application service is not configured.",
            )

        try:
            self.application_service.status()

            return HealthCheck(
                name="application",
                status="healthy",
                message="Application service is available.",
            )
        except Exception as exc:
            return HealthCheck(
                name="application",
                status="unhealthy",
                message=f"Application service check failed: {exc}",
            )

    def _check_database(self) -> HealthCheck:
        """Check database connectivity when a connection is configured."""

        if self.database_connection is None:
            return HealthCheck(
                name="database",
                status="unknown",
                message="Database connection is not configured.",
            )

        try:
            connection = self.database_connection

            if hasattr(connection, "execute"):
                connection.execute("SELECT 1")
            elif hasattr(connection, "cursor"):
                cursor = connection.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
            else:
                return HealthCheck(
                    name="database",
                    status="unknown",
                    message="Database object has no supported health-check interface.",
                )

            return HealthCheck(
                name="database",
                status="healthy",
                message="Database connection is available.",
            )
        except Exception as exc:
            return HealthCheck(
                name="database",
                status="unhealthy",
                message=f"Database health check failed: {exc}",
      )
