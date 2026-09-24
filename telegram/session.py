"""
Telegram session management for Insider Trade Bot 2.0.

Sessions are intentionally lightweight and in-memory. They hold only
short-lived Telegram interface state and do not replace the permanent
database or trading ledger.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any


@dataclass
class TelegramSession:
    """Short-lived session state for one Telegram user."""

    user_id: int
    chat_id: int
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    last_activity_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    metadata: dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        """Update the session activity timestamp."""
        self.last_activity_at = datetime.now(timezone.utc)


class TelegramSessionManager:
    """Manage short-lived Telegram sessions safely in memory."""

    def __init__(
        self,
        ttl_seconds: int = 3600,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError(
                "Telegram session TTL must be greater than zero."
            )

        self._ttl = timedelta(seconds=ttl_seconds)
        self._sessions: dict[int, TelegramSession] = {}
        self._lock = RLock()

    def get_or_create(
        self,
        user_id: int,
        chat_id: int,
    ) -> TelegramSession:
        """Return an active session or create a new one."""
        self._validate_ids(user_id, chat_id)

        with self._lock:
            self._remove_expired_locked()

            session = self._sessions.get(user_id)

            if session is None:
                session = TelegramSession(
                    user_id=user_id,
                    chat_id=chat_id,
                )
                self._sessions[user_id] = session
            else:
                session.chat_id = chat_id
                session.touch()

            return session

    def get(
        self,
        user_id: int,
    ) -> TelegramSession | None:
        """Return an active session, if one exists."""
        if not isinstance(user_id, int):
            return None

        with self._lock:
            self._remove_expired_locked()

            session = self._sessions.get(user_id)

            if session is not None:
                session.touch()

            return session

    def remove(self, user_id: int) -> None:
        """Remove a user's session."""
        with self._lock:
            self._sessions.pop(user_id, None)

    def clear(self) -> None:
        """Remove all sessions."""
        with self._lock:
            self._sessions.clear()

    def cleanup(self) -> int:
        """Remove expired sessions and return the number removed."""
        with self._lock:
            before = len(self._sessions)
            self._remove_expired_locked()
            return before - len(self._sessions)

    def count(self) -> int:
        """Return the number of active sessions."""
        with self._lock:
            self._remove_expired_locked()
            return len(self._sessions)

    def _remove_expired_locked(self) -> None:
        now = datetime.now(timezone.utc)

        expired_user_ids = [
            user_id
            for user_id, session in self._sessions.items()
            if now - session.last_activity_at > self._ttl
        ]

        for user_id in expired_user_ids:
            self._sessions.pop(user_id, None)

    @staticmethod
    def _validate_ids(
        user_id: int,
        chat_id: int,
    ) -> None:
        if not isinstance(user_id, int):
            raise TypeError("Telegram user_id must be an integer.")

        if not isinstance(chat_id, int):
            raise TypeError("Telegram chat_id must be an integer.")
