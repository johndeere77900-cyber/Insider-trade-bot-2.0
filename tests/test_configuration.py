from __future__ import annotations

from config.environment import load_environment
from config.environment_validator import validate_environment


def test_configuration_loads_from_mapping() -> None:
    values = {
        "APP_ENVIRONMENT": "testing",
        "APP_STRICT_MODE": "false",
        "APP_LIVE_TRADING": "false",
        "APP_PAPER_TRADING": "true",
        "APP_TELEGRAM_ENABLED": "false",
        "DATABASE_URL": "sqlite:///data/test.db",
        "SEC_USER_AGENT": "InsiderTradeBotTest/test@example.com",
        "SEC_TIMEOUT_SECONDS": "30",
        "TRADING_MODE": "paper",
        "LIVE_TRADING_CONFIRMATION": "false",
    }

    settings = load_environment(values)

    assert settings.environment == "testing"
    assert settings.database_url == "sqlite:///data/test.db"
    assert settings.sec_timeout_seconds == 30


def test_configuration_validation_returns_valid_result() -> None:
    values = {
        "APP_ENVIRONMENT": "testing",
        "APP_STRICT_MODE": "false",
        "APP_LIVE_TRADING": "false",
        "APP_PAPER_TRADING": "true",
        "APP_TELEGRAM_ENABLED": "false",
        "DATABASE_URL": "sqlite:///data/test.db",
        "SEC_USER_AGENT": "InsiderTradeBotTest/test@example.com",
        "SEC_TIMEOUT_SECONDS": "30",
        "TRADING_MODE": "paper",
        "LIVE_TRADING_CONFIRMATION": "false",
    }

    settings = load_environment(values)
    result = validate_environment(settings)

    assert result.valid is True
    assert result.errors == ()


def test_telegram_user_ids_are_parsed() -> None:
    values = {
        "APP_ENVIRONMENT": "testing",
        "APP_STRICT_MODE": "false",
        "APP_LIVE_TRADING": "false",
        "APP_PAPER_TRADING": "true",
        "APP_TELEGRAM_ENABLED": "true",
        "TELEGRAM_BOT_TOKEN": "test-token",
        "TELEGRAM_ALLOWED_USER_IDS": "123, 456,789",
        "DATABASE_URL": "sqlite:///data/test.db",
        "SEC_USER_AGENT": "InsiderTradeBotTest/test@example.com",
        "SEC_TIMEOUT_SECONDS": "30",
        "TRADING_MODE": "paper",
        "LIVE_TRADING_CONFIRMATION": "false",
    }

    settings = load_environment(values)

    assert settings.telegram_allowed_user_ids == (
        "123",
        "456",
        "789",
      )
