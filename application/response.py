"""
Application response serialization.

Converts internal application results into interface-neutral dictionaries.
"""

from __future__ import annotations

from typing import Any, Mapping

from application.result import ApplicationResult


class ApplicationResponseSerializer:
    """Serialize application results for external interfaces."""

    def serialize(
        self,
        result: ApplicationResult,
    ) -> Mapping[str, Any]:
        """Convert an ApplicationResult into a dictionary."""

        if not isinstance(result, ApplicationResult):
            raise TypeError(
                "result must be an ApplicationResult instance."
            )

        return result.to_dict()
