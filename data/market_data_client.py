"""
Historical market-data client and provider contract for Insider Trade Bot.

This module defines the provider-neutral interface/contract for retrieving
market-price data from external market-data providers.

It deliberately does not write directly to the permanent database.
Retrieved data must pass through normalization, validation, ingestion,
and provenance tracking before permanent storage.
"""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from typing import Any, Protocol, Sequence, runtime_checkable


class MarketDataClientError(Exception):
    """Base exception for market-data client failures."""


class MarketDataRequestError(
    MarketDataClientError
):
    """Raised when a market-data request cannot be completed."""


class MarketDataResponseError(
    MarketDataClientError
):
    """Raised when a market-data response cannot be interpreted."""


@runtime_checkable
class MarketDataProvider(Protocol):
    """
    Provider-neutral interface contract for historical OHLCV market-data retrieval.

    Implementations must provide source identification, batch support capability,
    and single/batch historical price retrieval without performing direct database writes.
    """

    @property
    def source(self) -> str:
        ...

    @property
    def supports_batch(self) -> bool:
        ...

    def get_historical_prices(
        self,
        *,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Any:
        ...

    def get_historical_prices_batch(
        self,
        *,
        symbols: Sequence[str],
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Any:
        ...


class MarketDataClient:
    """
    Generic HTTP JSON market-data client implementing the provider contract.

    The provider URL is supplied by configuration so that the rest of the
    system remains independent of a specific market-data vendor.
    """

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        timeout: int = 30,
        api_key_parameter: str = "apikey",
        source: str = "market_data_provider",
        supports_batch: bool = False,
    ) -> None:
        self.base_url = str(
            base_url
        ).strip().rstrip("/")

        self.api_key = str(
            api_key
        ).strip()

        self.timeout = timeout

        self.api_key_parameter = str(
            api_key_parameter
        ).strip()

        self._source = str(
            source
        ).strip() or "market_data_provider"

        self._supports_batch = bool(
            supports_batch
        )

    @property
    def source(self) -> str:
        """Provider identifier for provenance tracking."""
        return self._source

    @property
    def supports_batch(self) -> bool:
        """Indicates whether the provider supports multi-symbol batch requests."""
        return self._supports_batch

    def _build_url(
        self,
        path: str,
        parameters: dict[str, Any] | None = None,
    ) -> str:
        """
        Build an HTTP URL with optional query parameters.
        """

        if not str(path).strip():
            raise ValueError(
                "Market-data request path cannot be empty."
            )

        if not self.base_url:
            raise MarketDataRequestError(
                "Market-data base_url is not configured."
            )

        url = (
            f"{self.base_url}/"
            f"{str(path).lstrip('/')}"
        )

        query_parameters: dict[str, str] = {}

        if parameters:
            for key, value in parameters.items():
                if value is None:
                    continue

                query_parameters[
                    str(key)
                ] = str(value)

        if self.api_key:
            if not self.api_key_parameter:
                raise MarketDataRequestError(
                    "API-key parameter name cannot be empty."
                )

            query_parameters[
                self.api_key_parameter
            ] = self.api_key

        if query_parameters:
            encoded = "&".join(
                f"{quote(str(key))}="
                f"{quote(str(value))}"
                for key, value in query_parameters.items()
            )

            url = (
                f"{url}?{encoded}"
            )

        return url

    def _request_json(
        self,
        path: str,
        parameters: dict[str, Any] | None = None,
    ) -> object:
        """
        Execute a GET request and decode the response as JSON.
        """

        url = self._build_url(
            path,
            parameters,
        )

        request = Request(
            url=url,
            method="GET",
            headers={
                "Accept": "application/json",
                "User-Agent": (
                    "Insider-Trade-Bot/2.0"
                ),
            },
        )

        try:
            with urlopen(
                request,
                timeout=self.timeout,
            ) as response:

                status = getattr(
                    response,
                    "status",
                    None,
                )

                if status is not None and not (
                    200 <= status < 300
                ):
                    raise MarketDataResponseError(
                        "Market-data provider returned "
                        f"HTTP status {status}."
                    )

                body = response.read()

        except HTTPError as exc:
            raise MarketDataRequestError(
                "Market-data request failed with "
                f"HTTP {exc.code}: {exc.reason}"
            ) from exc

        except URLError as exc:
            raise MarketDataRequestError(
                "Market-data request could not be completed: "
                f"{exc.reason}"
            ) from exc

        except TimeoutError as exc:
            raise MarketDataRequestError(
                "Market-data request timed out."
            ) from exc

        except OSError as exc:
            raise MarketDataRequestError(
                "Market-data network operation failed: "
                f"{exc}"
            ) from exc

        try:
            return json.loads(
                body.decode("utf-8")
            )

        except UnicodeDecodeError as exc:
            raise MarketDataResponseError(
                "Market-data response could not be decoded as UTF-8."
            ) from exc

        except json.JSONDecodeError as exc:
            raise MarketDataResponseError(
                "Market-data response was not valid JSON."
            ) from exc

    def get(
        self,
        path: str,
        parameters: dict[str, Any] | None = None,
    ) -> object:
        """
        Retrieve arbitrary JSON data from the configured provider.
        """

        return self._request_json(
            path,
            parameters,
        )

    def get_historical_prices(
        self,
        *,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        path: str = "historical",
    ) -> object:
        """
        Retrieve historical price data for one symbol.

        The provider-specific response is returned unchanged. It must be
        normalized before entering permanent storage.
        """

        normalized_symbol = str(
            symbol
        ).strip().upper()

        if not normalized_symbol:
            raise ValueError(
                "symbol cannot be empty."
            )

        parameters: dict[str, Any] = {
            "symbol": normalized_symbol,
        }

        if start_date is not None:
            normalized_start = str(
                start_date
            ).strip()

            if not normalized_start:
                raise ValueError(
                    "start_date cannot be empty."
                )

            parameters[
                "start_date"
            ] = normalized_start

        if end_date is not None:
            normalized_end = str(
                end_date
            ).strip()

            if not normalized_end:
                raise ValueError(
                    "end_date cannot be empty."
                )

            parameters[
                "end_date"
            ] = normalized_end

        return self._request_json(
            path,
            parameters,
        )

    def get_historical_prices_batch(
        self,
        *,
        symbols: Sequence[str],
        start_date: str | None = None,
        end_date: str | None = None,
        path: str = "historical/batch",
    ) -> object:
        """
        Retrieve historical price data for multiple symbols if supported by provider.
        """
        if not self.supports_batch:
            raise NotImplementedError(
                f"Provider '{self.source}' does not support batch symbol requests."
            )

        normalized_symbols = [
            str(s).strip().upper() for s in symbols if str(s).strip()
        ]

        if not normalized_symbols:
            raise ValueError(
                "symbols sequence cannot be empty."
            )

        parameters: dict[str, Any] = {
            "symbols": ",".join(normalized_symbols),
        }

        if start_date is not None:
            normalized_start = str(
                start_date
            ).strip()

            if not normalized_start:
                raise ValueError(
                    "start_date cannot be empty."
                )

            parameters[
                "start_date"
            ] = normalized_start

        if end_date is not None:
            normalized_end = str(
                end_date
            ).strip()

            if not normalized_end:
                raise ValueError(
                    "end_date cannot be empty."
                )

            parameters[
                "end_date"
            ] = normalized_end

        return self._request_json(
            path,
            parameters,
        )
