"""
Read-only data-access layer for research modules.

Provides query functions for normalized insider transactions and market prices
from operational storage without duplicating data or embedding SQL in research logic.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Union

from data.sec_dataset_pipeline import NormalizedBulkTransaction
from database.connection import connect, is_postgresql_url


def query_insider_transactions(
    database_url: str,
    *,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    tickers: Optional[Union[str, List[str]]] = None,
    issuer_ciks: Optional[Union[str, List[str]]] = None,
    transaction_codes: Optional[Union[str, List[str]]] = None,
    acquired_disposed: Optional[str] = None,
    ownership_types: Optional[Union[str, List[str]]] = None,
    source: Optional[str] = None,
    accession_numbers: Optional[Union[str, List[str]]] = None,
    limit: Optional[int] = None,
) -> List[NormalizedBulkTransaction]:
    """
    Retrieve normalized insider transaction records from the operational database.

    Filters records dynamically using parameterized SQL queries.
    Returns domain objects (`NormalizedBulkTransaction`).
    """
    is_pg = is_postgresql_url(database_url)
    param_placeholder = "%s" if is_pg else "?"

    query = """
        SELECT
            accession_number,
            issuer_cik,
            issuer_name,
            ticker,
            insider_name,
            insider_cik,
            transaction_date,
            filing_date,
            form_type,
            transaction_code,
            security_title,
            shares,
            price,
            transaction_type,
            acquired_disposed,
            ownership_type,
            ownership_nature,
            source,
            source_url,
            is_amendment,
            date_of_orig_submission,
            raw_payload,
            record_hash
        FROM insider_transactions
        WHERE 1 = 1
    """

    params: List[Any] = []

    if start_date:
        query += f" AND transaction_date >= {param_placeholder}"
        params.append(start_date)

    if end_date:
        query += f" AND transaction_date <= {param_placeholder}"
        params.append(end_date)

    if tickers:
        t_list = [tickers] if isinstance(tickers, str) else list(tickers)
        if t_list:
            placeholders = ", ".join([param_placeholder] * len(t_list))
            query += f" AND UPPER(ticker) IN ({placeholders})"
            params.extend([t.upper() for t in t_list])

    if issuer_ciks:
        c_list = [issuer_ciks] if isinstance(issuer_ciks, str) else list(issuer_ciks)
        if c_list:
            placeholders = ", ".join([param_placeholder] * len(c_list))
            query += f" AND issuer_cik IN ({placeholders})"
            params.extend([c.zfill(10) if c.isdigit() else c for c in c_list])

    if transaction_codes:
        tc_list = [transaction_codes] if isinstance(transaction_codes, str) else list(transaction_codes)
        if tc_list:
            placeholders = ", ".join([param_placeholder] * len(tc_list))
            query += f" AND UPPER(transaction_code) IN ({placeholders})"
            params.extend([code.upper() for code in tc_list])

    if acquired_disposed:
        query += f" AND UPPER(acquired_disposed) = {param_placeholder}"
        params.append(acquired_disposed.strip().upper())

    if ownership_types:
        ot_list = [ownership_types] if isinstance(ownership_types, str) else list(ownership_types)
        if ot_list:
            placeholders = ", ".join([param_placeholder] * len(ot_list))
            query += f" AND UPPER(ownership_type) IN ({placeholders})"
            params.extend([ot.upper() for ot in ot_list])

    if source:
        query += f" AND source = {param_placeholder}"
        params.append(source)

    if accession_numbers:
        acc_list = [accession_numbers] if isinstance(accession_numbers, str) else list(accession_numbers)
        if acc_list:
            placeholders = ", ".join([param_placeholder] * len(acc_list))
            query += f" AND accession_number IN ({placeholders})"
            params.extend(acc_list)

    query += " ORDER BY transaction_date ASC, filing_date ASC"

    if limit is not None and limit > 0:
        query += f" LIMIT {param_placeholder}"
        params.append(limit)

    records: List[NormalizedBulkTransaction] = []

    with connect(database_url) as conn:
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()

        for row in rows:
            raw_payload_data = {}
            if row["raw_payload"]:
                try:
                    raw_payload_data = json.loads(row["raw_payload"])
                except Exception:
                    raw_payload_data = {}

            acq_disp = row["acquired_disposed"] or raw_payload_data.get("transaction", {}).get("TRANS_ACQUIRED_DISP_CD")
            form_t = row["form_type"] or "4"
            is_amend_val = bool(row["is_amendment"]) if row["is_amendment"] is not None else ("/A" in form_t)
            orig_sub_date = row["date_of_orig_submission"]

            records.append(
                NormalizedBulkTransaction(
                    accession_number=row["accession_number"] or "",
                    issuer_cik=row["issuer_cik"] or "",
                    issuer_name=row["issuer_name"],
                    ticker=row["ticker"],
                    reporting_owner_name=row["insider_name"],
                    reporting_owner_cik=row["insider_cik"],
                    transaction_date=row["transaction_date"],
                    filing_date=row["filing_date"],
                    transaction_code=row["transaction_code"],
                    security_title=row["security_title"],
                    shares=float(row["shares"]) if row["shares"] is not None else None,
                    price_per_share=float(row["price"]) if row["price"] is not None else None,
                    transaction_type=row["transaction_type"],
                    acquired_disposed=acq_disp,
                    ownership_type=row["ownership_type"],
                    ownership_nature=row["ownership_nature"],
                    source_url=row["source_url"] or "",
                    is_amendment=is_amend_val,
                    date_of_orig_submission=orig_sub_date,
                    raw_payload=raw_payload_data,
                    source=row["source"] or "SEC",
                    record_hash=row["record_hash"],
                    form_type=form_t,
                )
            )

    return records


def get_market_prices_for_ticker(
    database_url: str,
    ticker: str,
    *,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, float]:
    """
    Retrieve price records for a ticker symbol from market_prices table as a date -> close_price mapping.
    """
    if not ticker or not ticker.strip():
        return {}

    is_pg = is_postgresql_url(database_url)
    param_placeholder = "%s" if is_pg else "?"

    query = f"""
        SELECT price_date, close, adjusted_close
        FROM market_prices
        WHERE UPPER(symbol) = {param_placeholder}
    """
    params: List[Any] = [ticker.strip().upper()]

    if start_date:
        query += f" AND price_date >= {param_placeholder}"
        params.append(start_date)

    if end_date:
        query += f" AND price_date <= {param_placeholder}"
        params.append(end_date)

    query += " ORDER BY price_date ASC"

    prices: Dict[str, float] = {}

    with connect(database_url) as conn:
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
        for row in rows:
            price_val = row["close"] if row["close"] is not None else row["adjusted_close"]
            if price_val is not None:
                prices[row["price_date"]] = float(price_val)

    return prices
