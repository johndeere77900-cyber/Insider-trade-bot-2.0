"""
SEC data client for Insider Trade Bot.

This module handles communication with SEC endpoints.

Important:
- Retrieval is not the same as validation.
- A successful HTTP response does not prove data completeness.
- Historical ingestion will use this client together with validation,
  provenance, deduplication, and reconciliation.
"""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class SECClientError(Exception):
    """Base exception for SEC client failures."""


class SECRequestError(SECClientError):
    """Raised when an SEC request cannot be completed."""


class SECResponseError(SECClientError):
    """Raised when the SEC response cannot be interpreted correctly."""


class SECClient:
    """
    Client for retrieving SEC data.

    A descriptive User-Agent is required by the SEC and must be supplied
    through application configuration rather than hard-coded credentials.
    """

    def __init__(
        self,
        base_url: str,
        user_agent: str,
        timeout: int = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent.strip()
        self.timeout = timeout

    def _build_url(self, path: str) -> str:
        """
        Build an absolute SEC URL from a relative path.
        """

        if not path:
            raise ValueError(
                "SEC request path cannot be empty."
            )

        return (
            f"{self.base_url}/"
            f"{path.lstrip('/')}"
        )

    def _build_request(
        self,
        url: str,
    ) -> Request:
        """
        Build an SEC HTTP request with required headers.
        """

        if not self.user_agent:
            raise SECRequestError(
                "SEC_USER_AGENT is not configured. "
                "Configure a valid descriptive User-Agent before "
                "making SEC requests."
            )

        return Request(
            url=url,
            method="GET",
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate",
            },
        )

    def get_json(
        self,
        path: str,
    ) -> object:
        """
        Retrieve and decode a JSON response from the SEC.
        """

        url = self._build_url(path)
        request = self._build_request(url)

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
                    raise SECResponseError(
                        f"SEC returned HTTP status {status}."
                    )

                raw_body = response.read()

        except HTTPError as exc:
            raise SECRequestError(
                f"SEC request failed with HTTP "
                f"{exc.code}: {exc.reason}"
            ) from exc

        except URLError as exc:
            raise SECRequestError(
                f"SEC request could not be completed: "
                f"{exc.reason}"
            ) from exc

        except TimeoutError as exc:
            raise SECRequestError(
                "SEC request timed out."
            ) from exc

        except OSError as exc:
            raise SECRequestError(
                f"SEC network operation failed: {exc}"
            ) from exc

        try:
            return json.loads(
                raw_body.decode("utf-8")
            )

        except UnicodeDecodeError as exc:
            raise SECResponseError(
                "SEC response could not be decoded as UTF-8."
            ) from exc

        except json.JSONDecodeError as exc:
            raise SECResponseError(
                "SEC response was not valid JSON."
            ) from exc

    def get_company_tickers(self) -> object:
        """
        Retrieve the SEC company-tickers JSON dataset.
        """

        return self.get_json(
            "/files/company_tickers.json"
        )

    def get_submissions(
        self,
        cik: str,
    ) -> object:
        """
        Retrieve SEC submissions data for a company CIK.

        The CIK is normalized to ten digits before the request.
        """

        normalized_cik = str(
            cik
        ).strip()

        if not normalized_cik.isdigit():
            raise ValueError(
                "CIK must contain digits only."
            )

        normalized_cik = normalized_cik.zfill(10)

        return self.get_json(
            f"/files/submissions/"
            f"CIK{normalized_cik}.json"
        )

    def get_submission_file(
        self,
        filename: str,
    ) -> object:
        """
        Retrieve one historical SEC submissions file.

        The filename must be a plain SEC submissions filename rather
        than an arbitrary path. This prevents callers from turning this
        method into a general path traversal mechanism.
        """

        normalized_filename = str(
            filename
        ).strip()

        if not normalized_filename:
            raise ValueError(
                "SEC submissions filename cannot be empty."
            )

        if (
            "/" in normalized_filename
            or "\\" in normalized_filename
            or normalized_filename in {".", ".."}
            or ".." in normalized_filename
        ):
            raise ValueError(
                "SEC submissions filename must be a plain filename."
            )

        return self.get_json(
            f"/files/submissions/"
            f"{normalized_filename}"
  )
