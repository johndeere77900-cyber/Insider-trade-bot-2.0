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
import hashlib
import io
import json
import time
import urllib.request
import zipfile
from dataclasses import dataclass, field
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
    record_hash: Optional[str] = None
    form_type: Optional[str] = "4"


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

    return cleaned


def build_dataset_url(year: int, quarter: int) -> str:
    """Build the official SEC URL for a given year and quarter."""
    return f"{SEC_DATASET_BASE_URL}/{year}q{quarter}_form345.zip"


TRANSIENT_HTTP_STATUSES = {429, 500, 502, 503, 504}


def download_dataset_zip_to_file(
    year: int,
    quarter: int,
    user_agent: str,
    target_path: str,
    timeout: int = 60,
    max_retries: int = 3,
    backoff_factor: float = 1.0,
) -> str:
    """
    Download the zip archive for a given year and quarter directly to disk at target_path.
    Avoids holding large ZIP files in memory.
    Includes bounded retries with exponential backoff for transient HTTP or network failures only.
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

    last_exc: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        if attempt > 0:
            sleep_time = backoff_factor * (2 ** (attempt - 1))
            time.sleep(sleep_time)

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                status = getattr(response, "status", 200)
                if status != 200:
                    raise SECDatasetDownloadError(
                        f"HTTP status {status} downloading dataset {year}q{quarter} from {url}"
                    )
                with open(target_path, "wb") as out_file:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        out_file.write(chunk)
            return target_path
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code not in TRANSIENT_HTTP_STATUSES:
                raise SECDatasetDownloadError(
                    f"HTTP {exc.code} downloading dataset {year}q{quarter}: {exc.reason}"
                ) from exc
        except urllib.error.URLError as exc:
            last_exc = exc
        except TimeoutError as exc:
            last_exc = exc

    if isinstance(last_exc, urllib.error.HTTPError):
        raise SECDatasetDownloadError(
            f"HTTP {last_exc.code} downloading dataset {year}q{quarter}: {last_exc.reason}"
        ) from last_exc
    elif isinstance(last_exc, urllib.error.URLError):
        raise SECDatasetDownloadError(
            f"URL error downloading dataset {year}q{quarter}: {last_exc.reason}"
        ) from last_exc
    else:
        raise SECDatasetDownloadError(
            f"Failed to download dataset {year}q{quarter}: {last_exc}"
        ) from last_exc


def download_dataset_zip(
    year: int,
    quarter: int,
    user_agent: str,
    timeout: int = 60,
    max_retries: int = 3,
    backoff_factor: float = 1.0,
) -> bytes:
    """
    Legacy helper: download zip archive into memory bytes.
    Includes bounded retries with exponential backoff for transient HTTP or network failures only.
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

    last_exc: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        if attempt > 0:
            sleep_time = backoff_factor * (2 ** (attempt - 1))
            time.sleep(sleep_time)

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                status = getattr(response, "status", 200)
                if status != 200:
                    raise SECDatasetDownloadError(
                        f"HTTP status {status} downloading dataset {year}q{quarter} from {url}"
                    )
                return response.read()
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code not in TRANSIENT_HTTP_STATUSES:
                raise SECDatasetDownloadError(
                    f"HTTP {exc.code} downloading dataset {year}q{quarter}: {exc.reason}"
                ) from exc
        except urllib.error.URLError as exc:
            last_exc = exc
        except TimeoutError as exc:
            last_exc = exc

    if isinstance(last_exc, urllib.error.HTTPError):
        raise SECDatasetDownloadError(
            f"HTTP {last_exc.code} downloading dataset {year}q{quarter}: {last_exc.reason}"
        ) from last_exc
    elif isinstance(last_exc, urllib.error.URLError):
        raise SECDatasetDownloadError(
            f"URL error downloading dataset {year}q{quarter}: {last_exc.reason}"
        ) from last_exc
    else:
        raise SECDatasetDownloadError(
            f"Failed to download dataset {year}q{quarter}: {last_exc}"
        ) from last_exc


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


def compute_transaction_identity(
    accession_number: str,
    transaction_type: str,
    transaction_sk: str,
    is_amendment: bool = False,
    form_type: str = "",
) -> str:
    """
    Create a deterministic, semantic SEC transaction identity hash based explicitly on:
    - ACCESSION_NUMBER
    - transaction table/type (NONDERIV_TRANS / DERIV_TRANS)
    - corresponding NONDERIV_TRANS_SK / DERIV_TRANS_SK
    - form type and amendment status
    """
    raw_key = (
        f"{accession_number}|"
        f"{transaction_type.upper()}|"
        f"{transaction_sk}|"
        f"{form_type}|"
        f"{'1' if is_amendment else '0'}"
    )
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def parse_dataset_zip(
    zip_bytes_or_path: Any,
    source_url: str = "",
) -> Generator[Dict[str, Any], None, None]:
    """
    Parse a SEC Form 3/4/5 bulk dataset zip archive (from file path or in-memory bytes)
    and yield raw merged record dicts.
    Guarantees that opened ZipFile handles are explicitly closed in a try...finally block.
    """
    close_zf = False
    try:
        if isinstance(zip_bytes_or_path, zipfile.ZipFile):
            zf = zip_bytes_or_path
            close_zf = False
        elif isinstance(zip_bytes_or_path, str):
            zf = zipfile.ZipFile(zip_bytes_or_path, "r")
            close_zf = True
        elif isinstance(zip_bytes_or_path, (bytes, bytearray)):
            zf = zipfile.ZipFile(io.BytesIO(zip_bytes_or_path))
            close_zf = True
        else:
            zf = zipfile.ZipFile(zip_bytes_or_path)
            close_zf = True
    except Exception as exc:
        raise SECDatasetError(f"Invalid zip file: {exc}") from exc

    try:
        # 1. SUBMISSION.tsv
        submissions: Dict[str, Dict[str, str]] = {}
        for row in read_tsv_from_zip(zf, "SUBMISSION.tsv"):
            acc = row.get("ACCESSION_NUMBER", "")
            if acc:
                submissions[acc] = row

        # 2. REPORTINGOWNER.tsv (multimap: accession -> list of owner dicts)
        reporting_owners: Dict[str, List[Dict[str, str]]] = {}
        for row in read_tsv_from_zip(zf, "REPORTINGOWNER.tsv"):
            acc = row.get("ACCESSION_NUMBER", "")
            if acc:
                if acc not in reporting_owners:
                    reporting_owners[acc] = []
                reporting_owners[acc].append(row)

        # 3. FOOTNOTES.tsv (accession -> list of footnote dicts)
        footnotes: Dict[str, List[Dict[str, str]]] = {}
        for row in read_tsv_from_zip(zf, "FOOTNOTES.tsv"):
            acc = row.get("ACCESSION_NUMBER", "")
            if acc:
                if acc not in footnotes:
                    footnotes[acc] = []
                footnotes[acc].append(row)

        # 4. OWNER_SIGNATURE.tsv (accession -> list of signature dicts)
        signatures: Dict[str, List[Dict[str, str]]] = {}
        for row in read_tsv_from_zip(zf, "OWNER_SIGNATURE.tsv"):
            acc = row.get("ACCESSION_NUMBER", "")
            if acc:
                if acc not in signatures:
                    signatures[acc] = []
                signatures[acc].append(row)

        # 5. NONDERIV_HOLDING.tsv (accession -> list of holding dicts)
        nonderiv_holdings: Dict[str, List[Dict[str, str]]] = {}
        for row in read_tsv_from_zip(zf, "NONDERIV_HOLDING.tsv"):
            acc = row.get("ACCESSION_NUMBER", "")
            if acc:
                if acc not in nonderiv_holdings:
                    nonderiv_holdings[acc] = []
                nonderiv_holdings[acc].append(row)

        # 6. DERIV_HOLDING.tsv (accession -> list of holding dicts)
        deriv_holdings: Dict[str, List[Dict[str, str]]] = {}
        for row in read_tsv_from_zip(zf, "DERIV_HOLDING.tsv"):
            acc = row.get("ACCESSION_NUMBER", "")
            if acc:
                if acc not in deriv_holdings:
                    deriv_holdings[acc] = []
                deriv_holdings[acc].append(row)

        def build_record_for_transaction(
            acc: str,
            trans_row: Dict[str, str],
            transaction_type: str,  # 'non_derivative' or 'derivative'
        ) -> Dict[str, Any]:
            sub_info = submissions.get(acc, {})
            owners_list = reporting_owners.get(acc, [{}])
            primary_owner = owners_list[0] if owners_list else {}

            fn_list = footnotes.get(acc, [])
            sig_list = signatures.get(acc, [])
            hld_list = (
                nonderiv_holdings.get(acc, [])
                if transaction_type == "non_derivative"
                else deriv_holdings.get(acc, [])
            )

            filing_date_raw = sub_info.get("FILING_DATE", "")
            trans_date_raw = trans_row.get("TRANS_DATE", "")

            filing_date = parse_sec_date(filing_date_raw)
            trans_date = parse_sec_date(trans_date_raw)

            issuer_cik = sub_info.get("ISSUERCIK", "")
            if issuer_cik and issuer_cik.isdigit():
                clean_issuer_cik_dir = str(int(issuer_cik))
                issuer_cik = issuer_cik.zfill(10)
            else:
                clean_issuer_cik_dir = issuer_cik or "0"

            date_orig_sub = sub_info.get("DATE_OF_ORIG_SUB", "")
            doc_type = sub_info.get("DOCUMENT_TYPE", "")
            is_amendment = bool(date_orig_sub) or doc_type.endswith("/A")

            trans_sk = (
                trans_row.get("NONDERIV_TRANS_SK")
                if transaction_type == "non_derivative"
                else trans_row.get("DERIV_TRANS_SK")
            ) or ""

            form_type = trans_row.get("TRANS_FORM_TYPE") or doc_type or "4"

            # Owner attribution: Only attribute if filing lists exactly 1 owner;
            # if multiple owners exist, do not arbitrarily attribute to owner[0].
            # All reporting owners are preserved in raw["all_owners"].
            if len(owners_list) == 1:
                owner_cik = primary_owner.get("RPTOWNERCIK", "")
                if owner_cik and owner_cik.isdigit():
                    owner_cik = owner_cik.zfill(10)
                owner_name = primary_owner.get("RPTOWNERNAME", "")
                owner_title = primary_owner.get("RPTOWNER_TITLE", "")
                owner_rel = primary_owner.get("RPTOWNER_RELATIONSHIP", "")
            else:
                owner_cik = None
                owner_name = None
                owner_title = None
                owner_rel = None

            # Deterministic semantic SEC transaction identity
            rec_hash = compute_transaction_identity(
                accession_number=acc,
                transaction_type=transaction_type,
                transaction_sk=str(trans_sk),
                is_amendment=is_amendment,
                form_type=form_type,
            )

            rec_source_url = source_url or f"https://www.sec.gov/Archives/edgar/data/{clean_issuer_cik_dir}/{acc.replace('-', '')}/{acc}.txt"

            record = {
                "accession_number": acc,
                "source": "SEC",
                "source_url": rec_source_url,
                "form_type": form_type,
                "filing_date": filing_date,
                "transaction_date": trans_date,
                "issuer_cik": issuer_cik,
                "issuer_name": sub_info.get("ISSUERNAME", ""),
                "ticker": sub_info.get("ISSUERTRADINGSYMBOL", ""),
                "reporting_owner_cik": owner_cik,
                "reporting_owner_name": owner_name,
                "reporting_owner_title": owner_title,
                "reporting_owner_relationship": owner_rel,
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
                "record_hash": rec_hash,
                "raw": {
                    "submission": sub_info,
                    "owner": primary_owner,
                    "all_owners": owners_list,
                    "transaction": trans_row,
                    "footnotes": fn_list,
                    "signatures": sig_list,
                    "holdings": hld_list,
                },
            }
            return record

        # Parse non-derivative transactions (1 record per transaction row)
        for row in read_tsv_from_zip(zf, "NONDERIV_TRANS.tsv"):
            acc = row.get("ACCESSION_NUMBER", "")
            if acc:
                yield build_record_for_transaction(acc, row, "non_derivative")

        # Parse derivative transactions (1 record per transaction row)
        for row in read_tsv_from_zip(zf, "DERIV_TRANS.tsv"):
            acc = row.get("ACCESSION_NUMBER", "")
            if acc:
                yield build_record_for_transaction(acc, row, "derivative")

    finally:
        if close_zf and 'zf' in locals():
            try:
                zf.close()
            except Exception:
                pass


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
        record_hash=_str(raw_record.get("record_hash")),
        form_type=_str(raw_record.get("form_type")) or "4",
    )


def validate_bulk_record(record: NormalizedBulkTransaction) -> BulkValidationResult:
    """
    Validate normalized transaction according to Section 5/9 rules.
    Does not silently discard invalid records; reports specific validation errors.
    """
    errors: List[str] = []

    # Filing identity
    if not record.accession_number:
        errors.append("Missing filing identity (accession_number)")

    if not record.form_type:
        errors.append("Missing form type")

    # Issuer identity
    if not record.issuer_cik:
        errors.append("Missing issuer identity (issuer_cik)")

    # Reporting owner identity
    has_raw_owners = bool(
        record.raw_payload.get("all_owners") or record.raw_payload.get("owner")
    )
    if not record.reporting_owner_cik and not record.reporting_owner_name and not has_raw_owners:
        errors.append("Missing reporting owner identity (reporting_owner_cik, reporting_owner_name, and raw owners all empty)")

    # Dates and temporal consistency
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

    if record.date_of_orig_submission:
        try:
            datetime.strptime(record.date_of_orig_submission, "%Y-%m-%d")
        except ValueError:
            errors.append(f"Invalid date_of_orig_submission format: {record.date_of_orig_submission}")

    if record.transaction_date and record.filing_date:
        try:
            t_dt = datetime.strptime(record.transaction_date, "%Y-%m-%d")
            f_dt = datetime.strptime(record.filing_date, "%Y-%m-%d")
            if t_dt > f_dt and (t_dt - f_dt).days > 365:
                errors.append(f"Transaction date ({record.transaction_date}) is >1 year ahead of filing date ({record.filing_date})")
        except ValueError:
            pass

    # Transaction codes and indicators
    valid_codes = {
        "P", "S", "A", "D", "F", "I", "M", "C", "E", "H", "O", "X", "G", "L", "W", "Z", "J", "K", "U"
    }
    if record.transaction_code and record.transaction_code.upper() not in valid_codes:
        errors.append(f"Invalid transaction code: {record.transaction_code}")

    if record.acquired_disposed and record.acquired_disposed.upper() not in {"A", "D"}:
        errors.append(f"Invalid acquired_disposed indicator: {record.acquired_disposed}")

    if record.ownership_type and record.ownership_type.upper() not in {"D", "I"}:
        errors.append(f"Invalid ownership_type indicator: {record.ownership_type}")

    # Numeric checks
    if record.shares is not None and record.shares < 0:
        errors.append(f"Negative shares value: {record.shares}")

    if record.price_per_share is not None and record.price_per_share < 0:
        errors.append(f"Negative price_per_share value: {record.price_per_share}")

    # Source and raw payload
    if not record.source_url:
        errors.append("Missing source URL/reference")

    if not record.raw_payload:
        errors.append("Missing raw source payload")

    return BulkValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
    )
