"""
Application layer for Insider Trade Bot 2.0.

The application layer coordinates the agent's domain services and provides
a stable interface for external entry points such as Telegram, CLI, and
future automation.
"""

from .service import ApplicationService, ApplicationStatus

__all__ = [
    "ApplicationService",
    "ApplicationStatus",
]
