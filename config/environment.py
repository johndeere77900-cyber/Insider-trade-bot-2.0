from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


class EnvironmentConfigurationError(ValueError):
    """Raised when required environment configuration is invalid."""


def _get_bool(
    values: Mapping[str, str],
    name: str,
    default: bool,
) -> bool:
    raw = values.get(name)

    if raw is None:
        return default

    normalized = raw.strip().lower()

    if normalized in {"1", "true", "yes", "on"}:
        return True

    if normalized in {"0", "false", "no", "off"}:
        return False

    raise EnvironmentConfigurationError(
        f"{name} must be a boolean value"
    )


def _get_int(
    values: Mapping[str, str],
    name: str,
    default: int,
) -> int:
    raw = values.get(name)

    if raw is None or not raw.strip():
        return default

    try:
        value = int(raw)
    except ValueError as exc:
        raise EnvironmentConfigurationError(
            f"{name} must be an integer"
        ) from exc

    if value <= 0:
        raise EnvironmentConfigurationError(
            f"{name} must be greater than zero"
        )

    return value


@dataclass(frozen=True)
class EnvironmentSettings:
    """Resolved environment settings for the application."""

    environment: str
    strict_mode: bool
    live_trading: bool
    paper_trading: bool
    telegram_enabled: bool

    database_url: str

    sec_user_agent: str
    sec_timeout_seconds: int
    sec_store_raw_payload: bool
    sec_archive_backend: str
    sec_archive_path: str
    sec_archive_bucket: str
    sec_archive_endpoint_url: str
    sec_operational_retention_years: int

    telegram_bot_token: str
    telegram_allowed_user_ids: tuple[str, ...]

    market_data_api_key: str
    market_data_base_url: str

    corporate_actions_api_key: str
    corporate_actions_base_url: str

    fmp_api_key: str
    fmp_base_url: str

    log_level: str
    log_directory: str

    trading_mode: str
    live_trading_confirmation: bool

    secret_key: str


def validate_fmp_config(settings: EnvironmentSettings) -> None:
    """
    Validate that required configuration for FMP market-data acquisition is present.
    """
    if not settings.fmp_base_url or not settings.fmp_base_url.strip():
        raise EnvironmentConfigurationError(
            "FMP_BASE_URL is required when FMP market-data acquisition is requested."
        )
    if not settings.fmp_api_key or not settings.fmp_api_key.strip():
        raise EnvironmentConfigurationError(
            "FMP_API_KEY is required when FMP market-data acquisition is requested."
        )


def validate_market_data_config(
    settings: EnvironmentSettings,
    provider: str = "fmp",
) -> None:
    """
    Validate that required configuration for market-data acquisition is present.

    Must be called when the market-data acquisition path is requested, without
    failing application startup when market data acquisition is not being used.
    """
    prov = str(provider).strip().lower()
    if prov == "fmp":
        validate_fmp_config(settings)
    else:
        if not settings.market_data_base_url or not settings.market_data_base_url.strip():
            raise EnvironmentConfigurationError(
                "MARKET_DATA_BASE_URL is required when market-data acquisition is requested."
            )


def load_environment(
    values: Mapping[str, str] | None = None,
) -> EnvironmentSettings:
    """
    Load environment settings from a supplied mapping or os.environ.

    No external services are contacted and no trading operation is started.
    """

    source = values if values is not None else os.environ

    environment = source.get(
        "APP_ENVIRONMENT",
        "development",
    ).strip().lower()

    if environment not in {
        "development",
        "testing",
        "staging",
        "production",
    }:
        raise EnvironmentConfigurationError(
            "APP_ENVIRONMENT must be development, testing, "
            "staging, or production"
        )

    database_url = source.get(
        "DATABASE_URL",
        "sqlite:///data/insider_trade_bot.db",
    ).strip()

    if not database_url:
        raise EnvironmentConfigurationError(
            "DATABASE_URL cannot be empty"
        )

    sec_user_agent = source.get(
        "SEC_USER_AGENT",
        "",
    ).strip()

    if not sec_user_agent:
        raise EnvironmentConfigurationError(
            "SEC_USER_AGENT is required"
        )

    sec_archive_backend = source.get(
        "SEC_ARCHIVE_BACKEND",
        "filesystem",
    ).strip().lower()

    sec_archive_bucket = source.get("SEC_ARCHIVE_BUCKET", "").strip()
    sec_archive_endpoint_url = source.get("SEC_ARCHIVE_ENDPOINT_URL", "").strip()
    sec_operational_retention_years = _get_int(
        source,
        "SEC_OPERATIONAL_RETENTION_YEARS",
        3,
    )

    if sec_archive_backend in {"s3", "r2", "object_storage", "objectstorage", "s3_compat"}:
        if environment == "production" or source.get("SEC_ARCHIVE_BACKEND") is not None:
            if not sec_archive_bucket:
                raise EnvironmentConfigurationError(
                    "SEC_ARCHIVE_BUCKET is required when SEC_ARCHIVE_BACKEND is 's3'"
                )
            if not sec_archive_endpoint_url:
                raise EnvironmentConfigurationError(
                    "SEC_ARCHIVE_ENDPOINT_URL is required when SEC_ARCHIVE_BACKEND is 's3'"
                )
            aws_access_key = source.get("AWS_ACCESS_KEY_ID", "").strip()
            if not aws_access_key:
                raise EnvironmentConfigurationError(
                    "AWS_ACCESS_KEY_ID is required when SEC_ARCHIVE_BACKEND is 's3'"
                )
            aws_secret_key = source.get("AWS_SECRET_ACCESS_KEY", "").strip()
            if not aws_secret_key:
                raise EnvironmentConfigurationError(
                    "AWS_SECRET_ACCESS_KEY is required when SEC_ARCHIVE_BACKEND is 's3'"
                )

    telegram_enabled = _get_bool(
        source,
        "APP_TELEGRAM_ENABLED",
        False,
    )

    telegram_bot_token = source.get(
        "TELEGRAM_BOT_TOKEN",
        "",
    ).strip()

    if telegram_enabled and not telegram_bot_token:
        raise EnvironmentConfigurationError(
            "TELEGRAM_BOT_TOKEN is required when Telegram is enabled"
        )

    allowed_user_ids = tuple(
        item.strip()
        for item in source.get(
            "TELEGRAM_ALLOWED_USER_IDS",
            "",
        ).split(",")
        if item.strip()
    )

    # FMP configuration
    fmp_api_key = source.get("FMP_API_KEY", "").strip()
    fmp_base_url = (
        source.get("FMP_BASE_URL", "https://financialmodelingprep.com/stable").strip()
        or "https://financialmodelingprep.com/stable"
    )

    return EnvironmentSettings(
        environment=environment,
        strict_mode=_get_bool(
            source,
            "APP_STRICT_MODE",
            False,
        ),
        live_trading=_get_bool(
            source,
            "APP_LIVE_TRADING",
            False,
        ),
        paper_trading=_get_bool(
            source,
            "APP_PAPER_TRADING",
            True,
        ),
        telegram_enabled=telegram_enabled,
        database_url=database_url,
        sec_user_agent=sec_user_agent,
        sec_timeout_seconds=_get_int(
            source,
            "SEC_TIMEOUT_SECONDS",
            30,
        ),
        sec_store_raw_payload=_get_bool(
            source,
            "SEC_STORE_RAW_PAYLOAD",
            False,
        ),
        sec_archive_backend=sec_archive_backend,
        sec_archive_path=source.get(
            "SEC_ARCHIVE_PATH",
            "data/archive",
        ).strip(),
        sec_archive_bucket=sec_archive_bucket,
        sec_archive_endpoint_url=sec_archive_endpoint_url,
        sec_operational_retention_years=sec_operational_retention_years,
        telegram_bot_token=telegram_bot_token,
        telegram_allowed_user_ids=allowed_user_ids,
        market_data_api_key=source.get(
            "MARKET_DATA_API_KEY",
            "",
        ).strip(),
        market_data_base_url=source.get(
            "MARKET_DATA_BASE_URL",
            "",
        ).strip(),
        corporate_actions_api_key=source.get(
            "CORPORATE_ACTIONS_API_KEY",
            "",
        ).strip(),
        corporate_actions_base_url=source.get(
            "CORPORATE_ACTIONS_BASE_URL",
            "",
        ).strip(),
        fmp_api_key=fmp_api_key,
        fmp_base_url=fmp_base_url,
        log_level=source.get(
            "LOG_LEVEL",
            "INFO",
        ).strip().upper(),
        log_directory=source.get(
            "LOG_DIRECTORY",
            "logs",
        ).strip(),
        trading_mode=source.get(
            "TRADING_MODE",
            "paper",
        ).strip().lower(),
        live_trading_confirmation=_get_bool(
            source,
            "LIVE_TRADING_CONFIRMATION",
            False,
        ),
        secret_key=source.get(
            "SECRET_KEY",
            "",
        ).strip(),
    )
