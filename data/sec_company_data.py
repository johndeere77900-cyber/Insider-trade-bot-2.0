"""
SEC company-data utilities for Insider Trade Bot.

This module converts SEC company-ticker information into normalized lookup
records that can be used by the historical SEC ingestion layer.

It does not download data itself and does not write directly to the
database.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class SECCompany:
    """
    Normalized SEC company identity.
    """

    cik: str
    ticker: str
    title: str


class SECCompanyDataError(Exception):
    """Raised when SEC company data cannot be normalized safely."""


class SECCompanyData:
    """
    Compatibility interface for SEC company-data access.

    The current module performs normalization locally. The user-agent is
    retained as configuration for future SEC HTTP operations and is not
    used to perform network access during construction.
    """

    def __init__(self, user_agent: str) -> None:
        if not isinstance(user_agent, str):
            raise TypeError("user_agent must be a string.")

        if not user_agent.strip():
            raise ValueError("user_agent cannot be empty.")

        self.user_agent = user_agent.strip()

    def normalize(
        self,
        payload: Mapping[str, Any],
    ) -> SECCompany:
        """Normalize one SEC company record."""

        return normalize_company(payload)

    def normalize_companies(
        self,
        payload: Mapping[str, Any],
    ) -> list[SECCompany]:
        """Normalize an SEC company-tickers dataset."""

        return normalize_company_tickers(payload)

    def find_by_ticker(
        self,
        companies: list[SECCompany],
        ticker: str,
    ) -> SECCompany | None:
        """Find a company by ticker."""

        return find_company_by_ticker(
            companies,
            ticker,
        )

    def find_by_cik(
        self,
        companies: list[SECCompany],
        cik: str,
    ) -> SECCompany | None:
        """Find a company by CIK."""

        return find_company_by_cik(
            companies,
            cik,
        )


def _text(
    value: Any,
) -> str | None:
    """
    Convert a value to stripped text.

    Empty values become None.
    """

    if value is None:
        return None

    result = str(value).strip()

    if not result:
        return None

    return result


def normalize_cik(
    value: Any,
) -> str:
    """
    Normalize a CIK to the SEC's ten-digit representation.
    """

    text = _text(value)

    if text is None:
        raise SECCompanyDataError(
            "CIK is required."
        )

    if not text.isdigit():
        raise SECCompanyDataError(
            "CIK must contain digits only."
        )

    return text.zfill(10)


def normalize_company(
    payload: Mapping[str, Any],
) -> SECCompany:
    """
    Normalize one SEC company-ticker record.
    """

    if not isinstance(
        payload,
        Mapping,
    ):
        raise TypeError(
            "Company payload must be a mapping."
        )

    cik = normalize_cik(
        payload.get("cik_str")
        if "cik_str" in payload
        else payload.get("cik")
    )

    ticker = _text(
        payload.get("ticker")
    )

    title = _text(
        payload.get("title")
    )

    if ticker is None:
        raise SECCompanyDataError(
            "Company ticker is required."
        )

    if title is None:
        raise SECCompanyDataError(
            "Company title is required."
        )

    return SECCompany(
        cik=cik,
        ticker=ticker.upper(),
        title=title,
    )


def normalize_company_tickers(
    payload: Mapping[str, Any],
) -> list[SECCompany]:
    """
    Normalize the SEC company-tickers dataset.
    """

    if not isinstance(
        payload,
        Mapping,
    ):
        raise TypeError(
            "SEC company-tickers payload must be a mapping."
        )

    companies: list[SECCompany] = []

    for key, value in payload.items():
        if not isinstance(
            value,
            Mapping,
        ):
            continue

        try:
            company = normalize_company(
                value
            )

        except (
            SECCompanyDataError,
            TypeError,
        ) as exc:
            raise SECCompanyDataError(
                f"Invalid SEC company record '{key}': {exc}"
            ) from exc

        companies.append(
            company
        )

    return companies


def find_company_by_ticker(
    companies: list[SECCompany],
    ticker: str,
) -> SECCompany | None:
    """
    Find a normalized company by ticker.
    """

    normalized_ticker = _text(
        ticker
    )

    if normalized_ticker is None:
        raise SECCompanyDataError(
            "ticker cannot be empty."
        )

    normalized_ticker = normalized_ticker.upper()

    for company in companies:
        if company.ticker == normalized_ticker:
            return company

    return None


def find_company_by_cik(
    companies: list[SECCompany],
    cik: str,
) -> SECCompany | None:
    """
    Find a normalized company by CIK.
    """

    normalized_cik = normalize_cik(
        cik
    )

    for company in companies:
        if company.cik == normalized_cik:
            return company

    return None
