"""
Financial Modeling Prep (FMP) Corporate Actions Provider for Insider Trade Bot.

Retrieves historical stock splits and dividends from FMP stable API (/splits, /dividends)
without modifying stored raw OHLCV market prices.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from data.corporate_actions_client import (
    CorporateActionsRequestError,
    CorporateActionsResponseError,
)


class FMPCorporateActionsProvider:
    """
    Corporate-actions adapter for Financial Modeling Prep (FMP).

    Endpoints:
        - Stock Splits: /splits
        - Dividends: /dividends
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
        """Provider identifier for corporate action provenance."""
        return "fmp"

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

    def _request_json(
        self,
        path: str,
        parameters: dict[str, Any] | None = None,
    ) -> Any:
        if not self.api_key:
            raise CorporateActionsRequestError("FMP_API_KEY is required but not configured.")

        url = self._build_url(path, parameters)
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
                    raise CorporateActionsResponseError(
                        f"FMP provider returned HTTP status {status}."
                    )
                body = response.read()

        except HTTPError as exc:
            msg = f"FMP corporate-actions request failed with HTTP {exc.code}: {exc.reason}"
            raise CorporateActionsRequestError(self._mask_key(msg)) from exc

        except URLError as exc:
            msg = f"FMP corporate-actions request could not be completed: {exc.reason}"
            raise CorporateActionsRequestError(self._mask_key(msg)) from exc

        except TimeoutError as exc:
            raise CorporateActionsRequestError("FMP corporate-actions request timed out.") from exc

        except OSError as exc:
            msg = f"FMP corporate-actions network operation failed: {exc}"
            raise CorporateActionsRequestError(self._mask_key(msg)) from exc

        try:
            decoded = body.decode("utf-8")
            return json.loads(decoded)
        except UnicodeDecodeError as exc:
            raise CorporateActionsResponseError(
                "FMP corporate-actions response could not be decoded as UTF-8."
            ) from exc
        except json.JSONDecodeError as exc:
            raise CorporateActionsResponseError(
                "FMP corporate-actions response was not valid JSON."
            ) from exc

    def get_splits(
        self,
        *,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieve historical stock splits for a symbol.

        Target Endpoint: /splits
        """
        norm_symbol = str(symbol).strip().upper()
        if not norm_symbol:
            raise ValueError("symbol cannot be empty.")

        params: dict[str, Any] = {"symbol": norm_symbol}
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

        raw_payload = self._request_json("splits", params)
        return self._process_splits_payload(raw_payload, norm_symbol)

    def get_dividends(
        self,
        *,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieve historical dividends for a symbol.

        Target Endpoint: /dividends
        """
        norm_symbol = str(symbol).strip().upper()
        if not norm_symbol:
            raise ValueError("symbol cannot be empty.")

        params: dict[str, Any] = {"symbol": norm_symbol}
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

        raw_payload = self._request_json("dividends", params)
        return self._process_dividends_payload(raw_payload, norm_symbol)

    def _process_splits_payload(
        self,
        payload: Any,
        requested_symbol: str,
    ) -> list[dict[str, Any]]:
        if isinstance(payload, dict):
            if "Error Message" in payload or "error" in payload or "message" in payload:
                err_msg = payload.get("Error Message") or payload.get("error") or payload.get("message")
                raise CorporateActionsResponseError(f"FMP provider error: {err_msg}")
            items = payload.get("historical") or payload.get("splits") or []
        elif isinstance(payload, list):
            items = payload
        else:
            raise CorporateActionsResponseError("FMP corporate-actions response must be a list or object.")

        if not isinstance(items, list):
            raise CorporateActionsResponseError("FMP splits field must be a list.")

        results: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue

            action_date = item.get("date") or item.get("executionDate") or item.get("action_date")
            numerator = item.get("numerator")
            denominator = item.get("denominator")
            ratio_val = item.get("ratio")

            if ratio_val is None and numerator is not None and denominator is not None:
                ratio_val = f"{numerator}:{denominator}"
            elif ratio_val is not None:
                ratio_val = str(ratio_val)

            rec = {
                "symbol": str(item.get("symbol") or requested_symbol).strip().upper(),
                "action_type": "split",
                "action_date": str(action_date).strip() if action_date else None,
                "ratio": ratio_val,
                "cash_amount": None,
                "source": self.source,
            }
            results.append(rec)

        return results

    def _process_dividends_payload(
        self,
        payload: Any,
        requested_symbol: str,
    ) -> list[dict[str, Any]]:
        if isinstance(payload, dict):
            if "Error Message" in payload or "error" in payload or "message" in payload:
                err_msg = payload.get("Error Message") or payload.get("error") or payload.get("message")
                raise CorporateActionsResponseError(f"FMP provider error: {err_msg}")
            items = payload.get("historical") or payload.get("dividends") or []
        elif isinstance(payload, list):
            items = payload
        else:
            raise CorporateActionsResponseError("FMP corporate-actions response must be a list or object.")

        if not isinstance(items, list):
            raise CorporateActionsResponseError("FMP dividends field must be a list.")

        results: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue

            action_date = item.get("date") or item.get("paymentDate") or item.get("declarationDate") or item.get("action_date")
            cash = item.get("dividend") if "dividend" in item else item.get("amount") if "amount" in item else item.get("cash_amount")

            rec = {
                "symbol": str(item.get("symbol") or requested_symbol).strip().upper(),
                "action_type": "dividend",
                "action_date": str(action_date).strip() if action_date else None,
                "ratio": None,
                "cash_amount": cash,
                "source": self.source,
            }
            results.append(rec)

        return results
