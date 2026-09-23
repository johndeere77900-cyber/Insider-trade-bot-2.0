"""
Historical market-data client for Insider Trade Bot.

This module defines the controlled interface for retrieving market-price
data from an external provider.

It deliberately does not write directly to the permanent database.
Retrieved data must pass through normalization, validation, ingestion,
and provenance tracking before permanent storage.
"""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from typing import Any


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


class MarketDataClient:
    """
    Generic HTTP JSON market-data client.

    The provider URL is supplied by configuration so that the rest of the
    system remains independent of a specific market-data vendor.

    Provider-specific authentication and endpoint details are intentionally
    handled through configuration rather than hard-coded credentials.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        timeout: int = 30,
        api_key_parameter: str = "apikey",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.timeout = timeout
        self.api_key_parameter = (
            api_key_parameter.strip()
        )

    def _build_url(
        self,
        path: str,
        parameters: dict[str, Any] | None = None,
    ) -> str:
        """
        Build an HTTP URL with optional query parameters.
        """

        if not path.strip():
            raise ValueError(
                "Market-data request path cannot be empty."
            )

        url = (
            f"{self.base_url}/"
            f"{path.lstrip('/')}"
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
                        f"Market-data provider returned "
                        f"HTTP status {status}."
                    )

                body = response.read()

        except HTTPError as exc:
            raise MarketDataRequestError(
                f"Market-data request failed with "
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
                f"Market-data network operation failed: {exc}"
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

        This method is intentionally generic because the exact market-data
        provider will be selected and configured separately.
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
