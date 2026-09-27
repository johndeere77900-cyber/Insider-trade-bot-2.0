"""
Corporate-actions data client for Insider Trade Bot.

This module provides a provider-neutral HTTP JSON interface for retrieving
corporate-action data.

It does not normalize or permanently store retrieved data.
"""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from typing import Any


class CorporateActionsClientError(Exception):
    """Base exception for corporate-actions client failures."""


class CorporateActionsRequestError(
    CorporateActionsClientError
):
    """Raised when a corporate-actions request fails."""


class CorporateActionsResponseError(
    CorporateActionsClientError
):
    """Raised when a corporate-actions response is invalid."""


class CorporateActionsClient:
    """
    Generic HTTP JSON client for corporate-action providers.

    Authentication is supplied through configuration rather than
    hard-coded credentials.
    """

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        timeout: int = 30,
        api_key_parameter: str = "apikey",
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

    def _build_url(
        self,
        path: str,
        parameters: dict[str, Any] | None = None,
    ) -> str:
        """
        Build a request URL with optional query parameters.
        """

        if not str(path).strip():
            raise ValueError(
                "Corporate-actions request path cannot be empty."
            )

        if not self.base_url:
            raise CorporateActionsRequestError(
                "Corporate-actions base_url is not configured."
            )

        url = (
            f"{self.base_url}/"
            f"{str(path).lstrip('/')}"
        )

        query: dict[str, str] = {}

        if parameters:
            for key, value in parameters.items():
                if value is None:
                    continue

                query[str(key)] = str(value)

        if self.api_key:
            if not self.api_key_parameter:
                raise CorporateActionsRequestError(
                    "API-key parameter name cannot be empty."
                )

            query[
                self.api_key_parameter
            ] = self.api_key

        if query:
            encoded = "&".join(
                f"{quote(str(key))}="
                f"{quote(str(value))}"
                for key, value in query.items()
            )

            url = f"{url}?{encoded}"

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
                    raise CorporateActionsResponseError(
                        "Corporate-actions provider returned "
                        f"HTTP status {status}."
                    )

                body = response.read()

        except HTTPError as exc:
            raise CorporateActionsRequestError(
                "Corporate-actions request failed with "
                f"HTTP {exc.code}: {exc.reason}"
            ) from exc

        except URLError as exc:
            raise CorporateActionsRequestError(
                "Corporate-actions request could not be completed: "
                f"{exc.reason}"
            ) from exc

        except TimeoutError as exc:
            raise CorporateActionsRequestError(
                "Corporate-actions request timed out."
            ) from exc

        except OSError as exc:
            raise CorporateActionsRequestError(
                "Corporate-actions network operation failed: "
                f"{exc}"
            ) from exc

        try:
            return json.loads(
                body.decode("utf-8")
            )

        except UnicodeDecodeError as exc:
            raise CorporateActionsResponseError(
                "Corporate-actions response could not be decoded as UTF-8."
            ) from exc

        except json.JSONDecodeError as exc:
            raise CorporateActionsResponseError(
                "Corporate-actions response was not valid JSON."
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

    def get_actions(
        self,
        *,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        path: str = "corporate-actions",
    ) -> object:
        """
        Retrieve corporate-action data for one security.

        The provider response is returned unchanged and must pass through
        normalization and validation before permanent storage.
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
