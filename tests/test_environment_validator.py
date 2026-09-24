from __future__ import annotations

from config.environment import load_environment
from config.environment_validator import EnvironmentValidator


def base_environment() -> dict[str, str]:
    return {
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
        "SECRET_KEY": "",
    }


def test_valid_paper_environment() -> None:
    settings = load_environment(base_environment())

    result = EnvironmentValidator().validate(settings)

    assert result.valid is True
    assert result.errors == ()


def test_production_requires_strict_mode() -> None:
    values = base_environment()
    values["APP_ENVIRONMENT"] = "production"
    values["APP_STRICT_MODE"] = "false"
    values["SECRET_KEY"] = "test-secret"

    settings = load_environment(values)
    result = EnvironmentValidator().validate(settings)

    assert result.valid is False
    assert any(
        "strict" in error.lower()
        for error in result.errors
    )


def test_production_requires_secret_key() -> None:
    values = base_environment()
    values["APP_ENVIRONMENT"] = "production"
    values["APP_STRICT_MODE"] = "true"

    settings = load_environment(values)
    result = EnvironmentValidator().validate(settings)

    assert result.valid is False
    assert any(
        "secret_key" in error.lower()
        for error in result.errors
    )


def test_live_trading_requires_confirmation() -> None:
    values = base_environment()
    values["APP_ENVIRONMENT"] = "production"
    values["APP_STRICT_MODE"] = "true"
    values["APP_LIVE_TRADING"] = "true"
    values["APP_PAPER_TRADING"] = "false"
    values["TRADING_MODE"] = "live"
    values["SECRET_KEY"] = "test-secret"
    values["LIVE_TRADING_CONFIRMATION"] = "false"

    settings = load_environment(values)
    result = EnvironmentValidator().validate(settings)

    assert result.valid is False
    assert any(
        "confirmation" in error.lower()
        for error in result.errors
    )


def test_live_trading_configuration_can_be_valid() -> None:
    values = base_environment()
    values["APP_ENVIRONMENT"] = "production"
    values["APP_STRICT_MODE"] = "true"
    values["APP_LIVE_TRADING"] = "true"
    values["APP_PAPER_TRADING"] = "false"
    values["TRADING_MODE"] = "live"
    values["SECRET_KEY"] = "test-secret"
    values["LIVE_TRADING_CONFIRMATION"] = "true"

    settings = load_environment(values)
    result = EnvironmentValidator().validate(settings)

    assert result.valid is True
    assert result.errors == ()
