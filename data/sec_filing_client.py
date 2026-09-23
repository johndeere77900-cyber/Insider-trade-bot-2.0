"""
SEC filing-document client for Insider Trade Bot.

This module retrieves individual SEC filing documents after a filing has
been identified.

Retrieval is kept separate from parsing, validation, and permanent storage.
"""

from __future__ import annotations

import gzip
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class SEC filingClientError(
    Exception
):
    """Base exception for SEC filing retrieval failures."""


class SECFilingRequestError(
    SEC filingClientError
):
    """Raised when an SEC filing request fails."""


class SECFilingClient:
    """
    Client for retrieving SEC filing documents.

    The client returns the original document bytes. Parsing is performed by
    a separate component.
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

    def _build_url(
        self,
        path: str,
    ) -> str:
        """
        Build an absolute SEC URL.
        """

        normalized_path = str(
            path
        ).strip()

        if not normalized_path:
            raise ValueError(
                "SEC filing path cannot be empty."
            )

        if normalized_path.startswith(
            "http://"
        ) or normalized_path.startswith(
            "https://"
        ):
            return normalized_path

        return (
            f"{self.base_url}/"
            f"{normalized_path.lstrip('/')}"
        )

    def _request(
        self,
        url: str,
    ) -> bytes:
        """
        Retrieve one SEC document.
        """

        if not self.user_agent:
            raise SECFilingRequestError(
                "SEC User-Agent is not configured."
            )

        request = Request(
            url=url,
            method="GET",
            headers={
                "User-Agent": self.user_agent,
                "Accept": (
                    "application/xml, "
                    "application/xhtml+xml, "
                    "text/html, "
                    "text/xml, "
                    "*/*"
                ),
                "Accept-Encoding": "gzip",
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
                    raise SECFilingRequestError(
                        f"SEC returned HTTP status {status}."
                    )

                body = response.read()

                content_encoding = str(
                    response.headers.get(
                        "Content-Encoding",
                        ""
                    )
                ).lower()

        except HTTPError as exc:
            raise SECFilingRequestError(
                f"SEC filing request failed with HTTP "
                f"{exc.code}: {exc.reason}"
            ) from exc

        except URLError as exc:
            raise SECFilingRequestError(
                "SEC filing request could not be completed: "
                f"{exc.reason}"
            ) from exc

        except TimeoutError as exc:
            raise SECFilingRequestError(
                "SEC filing request timed out."
            ) from exc

        except OSError as exc:
            raise SECFilingRequestError(
                f"SEC filing network operation failed: {exc}"
            ) from exc

        if "gzip" in content_encoding:
            try:
                body = gzip.decompress(
                    body
                )
            except OSError as exc:
                raise SECFilingRequestError(
                    "SEC filing response could not be decompressed."
                ) from exc

        return body

    def get_document(
        self,
        path: str,
    ) -> bytes:
        """
        Retrieve an SEC filing document by relative or absolute URL.
        """

        url = self._build_url(
            path
        )

        return self._request(
            url
        )

    def get_filing_document(
        self,
        *,
        cik: str,
        accession_number: str,
        document_name: str,
    ) -> bytes:
        """
        Retrieve a filing document from the SEC archive.

        The accession number may be supplied with or without hyphens.
        """

        normalized_cik = str(
            cik
        ).strip()

        if not normalized_cik.isdigit():
            raise ValueError(
                "CIK must contain digits only."
            )

        normalized_cik = normalized_cik.zfill(
            10
        )

        normalized_accession = str(
            accession_number
        ).strip()

        if not normalized_accession:
            raise ValueError(
                "accession_number cannot be empty."
            )

        archive_accession = (
            normalized_accession.replace(
                "-",
                "",
            )
        )

        if not archive_accession.isdigit():
            raise ValueError(
                "accession_number must contain only digits "
                "and optional hyphens."
            )

        normalized_document = str(
            document_name
        ).strip()

        if not normalized_document:
            raise ValueError(
                "document_name cannot be empty."
            )

        path = (
            f"/Archives/edgar/data/"
            f"{int(normalized_cik)}/"
            f"{archive_accession}/"
            f"{normalized_document}"
        )

        return self.get_document(
            path
)
