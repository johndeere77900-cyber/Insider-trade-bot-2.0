"""
Financial Modeling Prep (FMP) Market Data Provider for Insider Trade Bot.

Implements the provider-neutral MarketDataProvider contract for FMP stable API.
Uses FMP's /historical-price-eod/non-split-adjusted endpoint to retrieve
canonical as-traded historical OHLCV data without split or dividend adjustments.
"""

from __future__ import annotations

import json
import re
from typing import Any, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from data.market_data_client import (
    MarketDataRequestError,
    MarketDataResponseError,
)


class FMPMarketDataProvider:
    """
    Adapter implementing the MarketDataProvider contract for Financial Modeling Prep (FMP).

    Target Endpoint: /historical-price-eod/non-split-adjusted
    Retrieves canonical as-traded historical OHLCV prices.
    """

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://financialmodelingprep.com/stable",
        timeout: int = 30,
    ) -> None:
        self.api_key = str(api_key).strip()
        self.base_url = str(base_url).strip().rstrip("/") or "https://financialmodelingprep.com/stable"
        self.timeout = timeout

    @property
    def source(self) -> str:
        """Provider identifier for market data provenance."""
        return "fmp"

    @property
    def supports_batch(self) -> bool:
        """FMP historical EOD adapter does not support batch symbol requests initially."""
        return False

    def _mask_key(self, text: str) -> str:
        """
        Redact the API key from strings, exception messages, and URLs.
        """
        if not text:
            return ""
        result = str(text)
        if self.api_key:
            result = result.replace(self.api_key, "***REDACTED***")
        result = re.sub(r"([?&]apikey=)[^&]+", r"\1***REDACTED***", result, flags=re.IGNORECASE)
        return result

    def _build_url(
        self,
        path: str,
        parameters: dict[str, Any] | None = None,
    ) -> str:
        """
        Build request URL for FMP stable API.
        """
        if not path or not str(path).strip():
            raise ValueError("Request path cannot be empty.")

        url = f"{self.base_url}/{str(path).lstrip('/')}"
        query_params: dict[str, str] = {}

        if parameters:
            for k, v in parameters.items():
                if v is not None:
                    query_params[str(k)] = str(v)

        if self.api_key:
            query_params["apikey"] = self.api_key

        if query_params:
            encoded = "&".join(
                f"{quote(str(k))}={quote(str(v))}"
                for k, v in query_params.items()
            )
            url = f"{url}?{encoded}"

        return url

    def get_historical_prices(
        self,
        *,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieve historical as-traded (non-split-adjusted) EOD market data for a single symbol from FMP.

        Target Endpoint: /historical-price-eod/non-split-adjusted
        Query Parameters: symbol, from (start_date), to (end_date), apikey
        """
        normalized_symbol = str(symbol).strip().upper()
        if not normalized_symbol:
            raise ValueError("symbol cannot be empty.")

        if not self.api_key:
            raise MarketDataRequestError("FMP_API_KEY is required but not configured.")

        params: dict[str, Any] = {
            "symbol": normalized_symbol,
        }

        if start_date is not None:
            norm_start = str(start_date).strip()
            if not norm_start:
                raise ValueError("start_date cannot be empty.")
            params["from"] = norm_start

        if end_date is not None:
            norm_end = str(end_date).strip()
            if not norm_end:
                raise ValueError("end_date cannot be empty.")
            params["to"] = norm_end

        url = self._build_url("historical-price-eod/non-split-adjusted", params)

        request = Request(
            url=url,
            method="GET",
            headers={
                "Accept": "application/json",
                "User-Agent": "Insider-Trade-Bot/2.0",
            },
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                status = getattr(response, "status", None)
                if status is not None and not (200 <= status < 300):
                    raise MarketDataResponseError(
                        f"FMP provider returned HTTP status {status}."
                    )
                body = response.read()

        except HTTPError as exc:
            msg = f"FMP market-data request failed with HTTP {exc.code}: {exc.reason}"
            raise MarketDataRequestError(self._mask_key(msg)) from exc

        except URLError as exc:
            msg = f"FMP market-data request could not be completed: {exc.reason}"
            raise MarketDataRequestError(self._mask_key(msg)) from exc

        except TimeoutError as exc:
            raise MarketDataRequestError("FMP market-data request timed out.") from exc

        except OSError as exc:
            msg = f"FMP market-data network operation failed: {exc}"
            raise MarketDataRequestError(self._mask_key(msg)) from exc

        try:
            decoded_body = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise MarketDataResponseError(
                "FMP market-data response could not be decoded as UTF-8."
            ) from exc

        try:
            payload = json.loads(decoded_body)
        except json.JSONDecodeError as exc:
            raise MarketDataResponseError(
                "FMP market-data response was not valid JSON."
            ) from exc

        return self._process_response(payload, normalized_symbol)

    def _process_response(
        self,
        payload: Any,
        requested_symbol: str,
    ) -> list[dict[str, Any]]:
        """
        Validate response envelope and transform into internal record representations.
        """
        if isinstance(payload, dict):
            # Check for explicit provider error messages
            if "Error Message" in payload:
                raise MarketDataResponseError(
                    f"FMP provider error: {payload['Error Message']}"
                )
            if "error" in payload:
                raise MarketDataResponseError(
                    f"FMP provider error: {payload['error']}"
                )
            if "message" in payload and not payload.get("historical"):
                raise MarketDataResponseError(
                    f"FMP provider error: {payload['message']}"
                )

            # Check for status error payloads
            if "status" in payload and str(payload["status"]).lower() in {"error", "400", "401", "403", "404", "500"}:
                err_msg = payload.get("message") or payload.get("error") or f"Status {payload['status']}"
                raise MarketDataResponseError(f"FMP provider error: {err_msg}")

            if "historical" in payload:
                raw_records = payload["historical"]
            else:
                raw_records = []

        elif isinstance(payload, list):
            raw_records = payload
        else:
            raise MarketDataResponseError(
                "FMP market-data response envelope must be a list or dict."
            )

        if not isinstance(raw_records, list):
            raise MarketDataResponseError(
                "FMP market-data response 'historical' field must be a list."
            )

        normalized_records: list[dict[str, Any]] = []

        for item in raw_records:
            if not isinstance(item, dict):
                # Pass through non-dict items so loader isolates them as REJECTED
                normalized_records.append(item)
                continue

            item_symbol = str(item.get("symbol") or requested_symbol).strip().upper()
            price_date = item.get("date") or item.get("price_date") or item.get("priceDate")

            # Priority-based unadjusted OHLC retrieval: prefer canonical "open"/"high"/"low"/"close", falling back to "adjOpen"/"adjHigh"/"adjLow"/"adjClose"
            open_price = item["open"] if "open" in item and item["open"] is not None else item.get("adjOpen")
            high_price = item["high"] if "high" in item and item["high"] is not None else item.get("adjHigh")
            low_price = item["low"] if "low" in item and item["low"] is not None else item.get("adjLow")
            close_price = item["close"] if "close" in item and item["close"] is not None else item.get("adjClose")

            volume = item.get("volume")

            # adjusted_close rule: Do NOT copy adjClose into adjusted_close for non-split-adjusted endpoint.
            # adjusted_close remains None unless FMP explicitly supplies a separate genuinely adjusted field.
            adj_close = item.get("adjusted_close") if "adjusted_close" in item else item.get("adjustedClose")

            rec: dict[str, Any] = {
                "symbol": item_symbol,
                "price_date": price_date,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "adjusted_close": adj_close,
                "volume": volume,
            }
            normalized_records.append(rec)

        return normalized_records

    def get_historical_prices_batch(
        self,
        *,
        symbols: Sequence[str],
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Any:
        """
        Batch request implementation.
        """
        raise NotImplementedError(
            f"Provider '{self.source}' does not support batch symbol requests."
        )
