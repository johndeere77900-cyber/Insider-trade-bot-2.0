"""
Market Data Provider Factory for Insider Trade Bot.

Centralizes construction and selection of market-data providers.
"""

from __future__ import annotations

import os
from typing import Any

from config.environment import EnvironmentConfigurationError, EnvironmentSettings, load_environment
from data.market_data_client import MarketDataProvider
from data.providers.fmp_market_data import FMPMarketDataProvider


def get_market_data_provider(
    provider_name: str = "fmp",
    settings: EnvironmentSettings | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    timeout: int = 30,
) -> MarketDataProvider:
    """
    Construct and return the configured MarketDataProvider for the requested provider name.

    Supported providers:
        - "fmp": Financial Modeling Prep provider adapter.

    Raises:
        ValueError / EnvironmentConfigurationError: If provider_name is unknown or configuration is invalid.
    """
    normalized_name = str(provider_name).strip().lower()

    if not normalized_name:
        raise ValueError("provider_name cannot be empty.")

    if normalized_name == "fmp":
        resolved_settings = settings or load_environment()

        key = api_key if api_key is not None else resolved_settings.fmp_api_key
        url = base_url if base_url is not None else resolved_settings.fmp_base_url

        if not key:
            key = os.getenv("FMP_API_KEY", "").strip()

        final_key = str(key).strip()
        final_url = str(url).strip()

        if not final_key:
            raise EnvironmentConfigurationError("FMP_API_KEY is required when FMP market-data acquisition is requested.")
        if not final_url:
            raise EnvironmentConfigurationError("FMP_BASE_URL is required when FMP market-data acquisition is requested.")

        return FMPMarketDataProvider(
            api_key=final_key,
            base_url=final_url,
            timeout=timeout,
        )

    raise ValueError(f"Unknown or unsupported market data provider: '{provider_name}'.")
