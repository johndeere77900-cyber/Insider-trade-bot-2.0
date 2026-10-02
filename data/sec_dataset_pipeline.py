"""
Official SEC Insider Transactions Bulk Dataset Pipeline.

This module handles downloading, zip extraction, TSV parsing, normalization,
validation, deduplication, and ingestion for official SEC Form 3/4/5 bulk
datasets (2006 to present).

URL structure:
https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{year}q{quarter}_form345.zip
"""

from __future__ import annotations

import csv
import io
import json
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Generator, List, Mapping, Optional, Tuple


SEC_DATASET_BASE_URL = (
    "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets"
)


class SECDatasetError(Exception):
    """Base exception for SEC bulk dataset pipeline failures."""


class SECDatasetDownloadError(SECDatasetError):
    """Raised when downloading a bulk dataset fails."""


@dataclass
class NormalizedBulkTransaction:
    """
    Normalized representation of one transaction from SEC bulk datasets.
    Preserves all required temporal, amendment, and raw data fields.
    """
    accession_number: str
    issuer_cik: str
    issuer_name: Optional[str]
    ticker: Optional[str]
    reporting_owner_name: Optional[str]
    reporting_owner_cik: Optional[str]
    transaction_date: Optional[str]
    filing_date: Optional[str]
    transaction_code: Optional[str]
    security_title: Optional[str]
    shares: Optional[float]
    price_per_share: Optional[float]
    transaction_type: Optional[str]  # e.g. non_derivative, derivative
    acquired_disposed: Optional[str]  # A or D
    ownership_type: Optional[str]    # D (Direct) or I (Indirect)
    ownership_nature: Optional[str]
    source_url: str
    is_amendment: bool
    date_of_orig_submission: Optional[str]
    raw_payload: Dict[str, Any]
    source: str = "SEC"


@dataclass
class BulkValidationResult:
    """Validation result for a normalized transaction record."""
    is_valid: bool
    errors: List[str]


def parse_sec_date(date_str: Optional[str]) -> Optional[str]:
    """
    Parse SEC date strings (e.g. '31-MAR-2023', '2023-03-31', '20230331') into ISO 'YYYY-MM-DD'.
    Returns None if date_str is empty or unparseable.
    """
    if not date_str:
        return None

    cleaned = str(date_str).strip()
    if not cleaned:
        return None

    formats = [
        "%d-%b-%Y",  # 31-MAR-2023
        "%Y-%m-%d",  # 2023-03-31
        "%Y%m%d",    # 20230331
        "%d-%b-%y",  # 31-MAR-23
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # Return raw cleaned string if no pattern matches, avoiding data loss
    return cleaned


def build_dataset_url(year: int, quarter: int) -> str:
    """Build the official SEC URL for a given year and quarter."""
    return f"{SEC_DATASET_BASE_URL}/{year}q{quarter}_form345.zip"


def download_dataset_zip(
    year: int,
    quarter: int,
    user_agent: str,
    timeout: int = 60,
) -> bytes:
    """
    Download the zip archive for a given year and quarter from SEC.
    """
    url = build_dataset_url(year, quarter)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/zip, application/octet-stream, */*",
            "Accept-Encoding": "gzip, deflate",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise SECDatasetDownloadError(
                    f"HTTP status {status} downloading dataset {year}q{quarter} from {url}"
                )
            return response.read()
    except urllib.error.HTTPError as exc:
        raise SECDatasetDownloadError(
            f"HTTP {exc.code} downloading dataset {year}q{quarter}: {exc.reason}"
        ) from exc
    except urllib.error.URLError as exc:
        raise SECDatasetDownloadError(
            f"URL error downloading dataset {year}q{quarter}: {exc.reason}"
        ) from exc
    except Exception as exc:
        raise SECDatasetDownloadError(
            f"Failed to download dataset {year}q{quarter}: {exc}"
        ) from exc


def read_tsv_from_zip(
    zf: zipfile.ZipFile, filename: str
) -> Generator[Dict[str, str], None, None]:
    """
    Yield dict rows from a TSV file inside a zip file.
    """
    matching = [name for name in zf.namelist() if name.lower() == filename.lower()]
    if not matching:
        return

    target_file = matching[0]
    with zf.open(target_file) as f:
        wrapper = io.TextIOWrapper(f, encoding="utf-8", errors="replace")
        reader = csv.DictReader(wrapper, delimiter="\t")
        for row in reader:
            yield {
                k.strip(): (v.strip() if v else "")
                for k, v in row.items()
                if k is not None
            }


def parse_dataset_zip(
    zip_bytes: bytes,
    source_url: str = "",
) -> Generator[Dict[str, Any], None, None]:
    """
    Parse a SEC Form 3/4/5 bulk dataset zip archive and yield raw merged record dicts.

    Combines:
    - SUBMISSION.tsv (submission metadata, issuer info, filing date)
    - REPORTINGOWNER.tsv (insider / reporting owner CIK and name)
    - NONDERIV_TRANS.tsv (non-derivative transactions)
    - DERIV_TRANS.tsv (derivative transactions)
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except Exception as exc:
        raise SECDatasetError(f"Invalid zip file: {exc}") from exc

    # 1. Parse SUBMISSION.tsv
    submissions: Dict[str, Dict[str, str]] = {}
    for row in read_tsv_from_zip(zf, "SUBMISSION.tsv"):
        acc = row.get("ACCESSION_NUMBER", "")
        if acc:
            submissions[acc] = row

    # 2. Parse REPORTINGOWNER.tsv
    reporting_owners: Dict[str, Dict[str, str]] = {}
    for row in read_tsv_from_zip(zf, "REPORTINGOWNER.tsv"):
        acc = row.get("ACCESSION_NUMBER", "")
        if acc and acc not in reporting_owners:
            reporting_owners[acc] = row

    def build_record(
        acc: str,
        trans_row: Dict[str, str],
        transaction_type: str,  # 'non_derivative' or 'derivative'
    ) -> Dict[str, Any]:
        sub_info = submissions.get(acc, {})
        owner_info = reporting_owners.get(acc, {})

        filing_date_raw = sub_info.get("FILING_DATE", "")
        trans_date_raw = trans_row.get("TRANS_DATE", "")

        filing_date = parse_sec_date(filing_date_raw)
        trans_date = parse_sec_date(trans_date_raw)

        issuer_cik = sub_info.get("ISSUERCIK", "")
        if issuer_cik and issuer_cik.isdigit():
            issuer_cik = issuer_cik.zfill(10)

        owner_cik = owner_info.get("RPTOWNERCIK", "")
        if owner_cik and owner_cik.isdigit():
            owner_cik = owner_cik.zfill(10)

        date_orig_sub = sub_info.get("DATE_OF_ORIG_SUB", "")
        doc_type = sub_info.get("DOCUMENT_TYPE", "")
        is_amendment = bool(date_orig_sub) or doc_type.endswith("/A")

        record = {
            "accession_number": acc,
            "source": "SEC",
            "source_url": source_url or f"https://www.sec.gov/Archives/edgar/data/{issuer_cik}/{acc.replace('-', '')}/{acc}.txt",
            "form_type": trans_row.get("TRANS_FORM_TYPE") or doc_type or "4",
            "filing_date": filing_date,
            "transaction_date": trans_date,
            "issuer_cik": issuer_cik,
            "issuer_name": sub_info.get("ISSUERNAME", ""),
            "ticker": sub_info.get("ISSUERTRADINGSYMBOL", ""),
            "reporting_owner_cik": owner_cik,
            "reporting_owner_name": owner_info.get("RPTOWNERNAME", ""),
            "reporting_owner_title": owner_info.get("RPTOWNER_TITLE", ""),
            "reporting_owner_relationship": owner_info.get("RPTOWNER_RELATIONSHIP", ""),
            "security_title": trans_row.get("SECURITY_TITLE", ""),
            "transaction_code": trans_row.get("TRANS_CODE", ""),
            "shares": trans_row.get("TRANS_SHARES", ""),
            "price_per_share": trans_row.get("TRANS_PRICEPERSHARE", ""),
            "acquired_disposed": trans_row.get("TRANS_ACQUIRED_DISP_CD", ""),
            "direct_indirect": trans_row.get("DIRECT_INDIRECT_OWNERSHIP", ""),
            "ownership_nature": trans_row.get("NATURE_OF_OWNERSHIP", ""),
            "transaction_type": transaction_type,
            "is_amendment": is_amendment,
            "date_of_orig_submission": parse_sec_date(date_orig_sub) if date_orig_sub else None,
            "raw": {
                "submission": sub_info,
                "owner": owner_info,
                "transaction": trans_row,
            },
        }
        return record

    for row in read_tsv_from_zip(zf, "NONDERIV_TRANS.tsv"):
        acc = row.get("ACCESSION_NUMBER", "")
        if acc:
            yield build_record(acc, row, "non_derivative")

    for row in read_tsv_from_zip(zf, "DERIV_TRANS.tsv"):
        acc = row.get("ACCESSION_NUMBER", "")
        if acc:
            yield build_record(acc, row, "derivative")


def normalize_bulk_record(raw_record: Dict[str, Any]) -> NormalizedBulkTransaction:
    """
    Normalize a raw bulk record into NormalizedBulkTransaction.
    Enforces clean type conversion without loss of original data.
    """
    def _float(val: Any) -> Optional[float]:
        if val is None or val == "":
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    def _str(val: Any) -> Optional[str]:
        if val is None:
            return None
        s = str(val).strip()
        return s if s else None

    return NormalizedBulkTransaction(
        accession_number=_str(raw_record.get("accession_number")) or "",
        issuer_cik=_str(raw_record.get("issuer_cik")) or "",
        issuer_name=_str(raw_record.get("issuer_name")),
        ticker=_str(raw_record.get("ticker")),
        reporting_owner_name=_str(raw_record.get("reporting_owner_name")),
        reporting_owner_cik=_str(raw_record.get("reporting_owner_cik")),
        transaction_date=_str(raw_record.get("transaction_date")),
        filing_date=_str(raw_record.get("filing_date")),
        transaction_code=_str(raw_record.get("transaction_code")),
        security_title=_str(raw_record.get("security_title")),
        shares=_float(raw_record.get("shares")),
        price_per_share=_float(raw_record.get("price_per_share")),
        transaction_type=_str(raw_record.get("transaction_type")),
        acquired_disposed=_str(raw_record.get("acquired_disposed")),
        ownership_type=_str(raw_record.get("direct_indirect")),
        ownership_nature=_str(raw_record.get("ownership_nature")),
        source_url=_str(raw_record.get("source_url")) or "",
        is_amendment=bool(raw_record.get("is_amendment")),
        date_of_orig_submission=_str(raw_record.get("date_of_orig_submission")),
        raw_payload=raw_record.get("raw") or {},
        source="SEC",
    )


def validate_bulk_record(record: NormalizedBulkTransaction) -> BulkValidationResult:
    """
    Validate normalized transaction according to Section 9 rules.
    Does not silently discard invalid records; reports specific validation errors.
    """
    errors: List[str] = []

    if not record.accession_number:
        errors.append("Missing filing identity (accession_number)")

    if not record.issuer_cik:
        errors.append("Missing issuer identity (issuer_cik)")

    if not record.reporting_owner_cik and not record.reporting_owner_name:
        errors.append("Missing reporting owner identity (reporting_owner_cik and reporting_owner_name both empty)")

    if record.transaction_date:
        try:
            datetime.strptime(record.transaction_date, "%Y-%m-%d")
        except ValueError:
            errors.append(f"Invalid transaction_date format: {record.transaction_date}")

    if record.filing_date:
        try:
            datetime.strptime(record.filing_date, "%Y-%m-%d")
        except ValueError:
            errors.append(f"Invalid filing_date format: {record.filing_date}")

    return BulkValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
    )
