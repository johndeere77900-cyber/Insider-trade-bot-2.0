from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from config.environment import EnvironmentSettings


class EnvironmentValidationError(ValueError):
    """Raised when the resolved environment is unsafe or incomplete."""


@dataclass(frozen=True)
class EnvironmentValidationResult:
    valid: bool
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "errors": list(self.errors),
        }


class EnvironmentValidator:
    """
    Validates resolved environment configuration before application startup.

    This validator performs configuration checks only. It never contacts
    external services and never enables live trading by itself.
    """

    def validate(
        self,
        settings: EnvironmentSettings,
    ) -> EnvironmentValidationResult:
        if settings is None:
            raise ValueError("settings is required")

        errors: list[str] = []

        if not settings.database_url.strip():
            errors.append("DATABASE_URL is required")

        if not settings.sec_user_agent.strip():
            errors.append("SEC_USER_AGENT is required")

        if settings.sec_timeout_seconds <= 0:
            errors.append("SEC_TIMEOUT_SECONDS must be greater than zero")

        if settings.telegram_enabled:
            if not settings.telegram_bot_token.strip():
                errors.append(
                    "TELEGRAM_BOT_TOKEN is required when Telegram is enabled"
                )

            if not settings.telegram_allowed_user_ids:
                errors.append(
                    "TELEGRAM_ALLOWED_USER_IDS must contain at least "
                    "one authorized user when Telegram is enabled"
                )

        if settings.environment == "production":
            if not settings.strict_mode:
                errors.append(
                    "APP_STRICT_MODE must be enabled in production"
                )

            if not settings.secret_key.strip():
                errors.append(
                    "SECRET_KEY is required in production"
                )

        if settings.live_trading:
            if settings.environment != "production":
                errors.append(
                    "Live trading is permitted only in production"
                )

            if not settings.strict_mode:
                errors.append(
                    "APP_STRICT_MODE must be enabled for live trading"
                )

            if not settings.live_trading_confirmation:
                errors.append(
                    "LIVE_TRADING_CONFIRMATION must be enabled for "
                    "live trading"
                )

            if settings.trading_mode != "live":
                errors.append(
                    "TRADING_MODE must be 'live' when live trading is enabled"
                )

        if settings.paper_trading and settings.trading_mode == "live":
            errors.append(
                "Paper trading cannot be enabled while TRADING_MODE is live"
            )

        if not settings.paper_trading and not settings.live_trading:
            errors.append(
                "At least one trading mode must be enabled"
            )

        if settings.trading_mode not in {"paper", "live"}:
            errors.append(
                "TRADING_MODE must be 'paper' or 'live'"
            )

        return EnvironmentValidationResult(
            valid=not errors,
            errors=tuple(errors),
        )

    def require_valid(
        self,
        settings: EnvironmentSettings,
    ) -> EnvironmentValidationResult:
        result = self.validate(settings)

        if not result.valid:
            raise EnvironmentValidationError(
                "Invalid environment configuration: "
                + "; ".join(result.errors)
            )

        return result


def validate_environment(
    settings: EnvironmentSettings,
) -> EnvironmentValidationResult:
    """Convenience function for validating environment settings."""

    return EnvironmentValidator().validate(settings)
