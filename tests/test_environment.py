from __future__ import annotations

import pytest

from config.environment import (
    EnvironmentConfigurationError,
    load_environment,
)
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


def test_load_environment_with_valid_configuration() -> None:
    settings = load_environment(base_environment())

    assert settings.environment == "testing"
    assert settings.paper_trading is True
    assert settings.live_trading is False
    assert settings.trading_mode == "paper"


def test_environment_validator_accepts_valid_paper_configuration() -> None:
    settings = load_environment(base_environment())

    result = EnvironmentValidator().validate(settings)

    assert result.valid is True
    assert result.errors == ()


def test_invalid_environment_name_is_rejected() -> None:
    values = base_environment()
    values["APP_ENVIRONMENT"] = "invalid"

    with pytest.raises(EnvironmentConfigurationError):
        load_environment(values)


def test_missing_sec_user_agent_is_rejected() -> None:
    values = base_environment()
    values["SEC_USER_AGENT"] = ""

    with pytest.raises(EnvironmentConfigurationError):
        load_environment(values)


def test_telegram_requires_bot_token() -> None:
    values = base_environment()
    values["APP_TELEGRAM_ENABLED"] = "true"

    with pytest.raises(EnvironmentConfigurationError):
        load_environment(values)


def test_live_trading_requires_production() -> None:
    values = base_environment()
    values["APP_LIVE_TRADING"] = "true"
    values["APP_STRICT_MODE"] = "true"
    values["LIVE_TRADING_CONFIRMATION"] = "true"
    values["TRADING_MODE"] = "live"

    settings = load_environment(values)
    result = EnvironmentValidator().validate(settings)

    assert result.valid is False
    assert any(
        "production" in error.lower()
        for error in result.errors
    )


def test_filesystem_backend_works_without_r2_credentials() -> None:
    values = base_environment()
    values["SEC_ARCHIVE_BACKEND"] = "filesystem"
    settings = load_environment(values)
    assert settings.sec_archive_backend == "filesystem"


def test_s3_backend_with_all_credentials_succeeds() -> None:
    values = base_environment()
    values["SEC_ARCHIVE_BACKEND"] = "s3"
    values["SEC_ARCHIVE_BUCKET"] = "test-bucket"
    values["SEC_ARCHIVE_ENDPOINT_URL"] = "https://example.r2.cloudflarestorage.com"
    values["AWS_ACCESS_KEY_ID"] = "fake_key"
    values["AWS_SECRET_ACCESS_KEY"] = "fake_secret"

    settings = load_environment(values)
    assert settings.sec_archive_backend == "s3"
    assert settings.sec_archive_bucket == "test-bucket"


def test_s3_backend_missing_bucket_fails() -> None:
    values = base_environment()
    values["SEC_ARCHIVE_BACKEND"] = "s3"
    values["SEC_ARCHIVE_ENDPOINT_URL"] = "https://example.r2.cloudflarestorage.com"
    values["AWS_ACCESS_KEY_ID"] = "fake_key"
    values["AWS_SECRET_ACCESS_KEY"] = "fake_secret"

    with pytest.raises(EnvironmentConfigurationError, match="SEC_ARCHIVE_BUCKET is required"):
        load_environment(values)


def test_s3_backend_missing_endpoint_fails() -> None:
    values = base_environment()
    values["SEC_ARCHIVE_BACKEND"] = "s3"
    values["SEC_ARCHIVE_BUCKET"] = "test-bucket"
    values["AWS_ACCESS_KEY_ID"] = "fake_key"
    values["AWS_SECRET_ACCESS_KEY"] = "fake_secret"

    with pytest.raises(EnvironmentConfigurationError, match="SEC_ARCHIVE_ENDPOINT_URL is required"):
        load_environment(values)


def test_s3_backend_missing_access_key_fails() -> None:
    values = base_environment()
    values["SEC_ARCHIVE_BACKEND"] = "s3"
    values["SEC_ARCHIVE_BUCKET"] = "test-bucket"
    values["SEC_ARCHIVE_ENDPOINT_URL"] = "https://example.r2.cloudflarestorage.com"
    values["AWS_SECRET_ACCESS_KEY"] = "fake_secret"

    with pytest.raises(EnvironmentConfigurationError, match="AWS_ACCESS_KEY_ID is required"):
        load_environment(values)


def test_s3_backend_missing_secret_key_fails() -> None:
    values = base_environment()
    values["SEC_ARCHIVE_BACKEND"] = "s3"
    values["SEC_ARCHIVE_BUCKET"] = "test-bucket"
    values["SEC_ARCHIVE_ENDPOINT_URL"] = "https://example.r2.cloudflarestorage.com"
    values["AWS_ACCESS_KEY_ID"] = "fake_key"

    with pytest.raises(EnvironmentConfigurationError, match="AWS_SECRET_ACCESS_KEY is required"):
        load_environment(values)
