"""
Telegram authorization for Insider Trade Bot 2.0.

This module provides a strict allowlist-based authorization boundary.
Telegram users are not trusted merely because they can contact the bot.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class AuthorizationResult:
    """Result of a Telegram authorization check."""

    authorized: bool
    user_id: int | None
    reason: str


class TelegramAuthorizer:
    """
    Authorize Telegram users against an explicit numeric user-ID allowlist.

    An empty allowlist denies access to everyone. This fail-closed behavior
    prevents accidental exposure of the agent if authorization has not been
    configured.
    """

    def __init__(self, allowed_user_ids: Iterable[int]) -> None:
        self._allowed_user_ids = frozenset(
            int(user_id) for user_id in allowed_user_ids
        )

    @property
    def allowed_user_ids(self) -> frozenset[int]:
        """Return the configured immutable authorization set."""
        return self._allowed_user_ids

    def is_authorized(self, user_id: int | None) -> bool:
        """Return whether a Telegram user ID is explicitly authorized."""
        if user_id is None:
            return False

        try:
            normalized_user_id = int(user_id)
        except (TypeError, ValueError):
            return False

        return normalized_user_id in self._allowed_user_ids

    def check(self, user_id: int | None) -> AuthorizationResult:
        """Return a structured authorization result."""
        if user_id is None:
            return AuthorizationResult(
                authorized=False,
                user_id=None,
                reason="Telegram user ID is missing.",
            )

        try:
            normalized_user_id = int(user_id)
        except (TypeError, ValueError):
            return AuthorizationResult(
                authorized=False,
                user_id=None,
                reason="Telegram user ID is invalid.",
            )

        if normalized_user_id not in self._allowed_user_ids:
            return AuthorizationResult(
                authorized=False,
                user_id=normalized_user_id,
                reason="Telegram user is not authorized.",
            )

        return AuthorizationResult(
            authorized=True,
            user_id=normalized_user_id,
            reason="Telegram user is authorized.",
        )

    def check_update(self, update: Any) -> AuthorizationResult:
        """
        Extract a Telegram user ID from a Telegram-style update object.

        The method intentionally supports both attribute-based Telegram
        objects and simple test doubles/dictionaries.
        """
        user_id = self._extract_user_id(update)
        return self.check(user_id)

    @staticmethod
    def _extract_user_id(update: Any) -> int | None:
        """Extract the effective Telegram user ID from an update."""
        if update is None:
            return None

        effective_user = getattr(update, "effective_user", None)

        if effective_user is not None:
            user_id = getattr(effective_user, "id", None)

            if user_id is not None:
                return user_id

        if isinstance(update, dict):
            effective_user = update.get("effective_user")

            if isinstance(effective_user, dict):
                return effective_user.get("id")

            if effective_user is not None:
                return getattr(effective_user, "id", None)

            return update.get("user_id")

        return None
