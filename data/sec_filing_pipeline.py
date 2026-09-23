"""
SEC filing processing pipeline for Insider Trade Bot.

This module connects:
    SEC filing retrieval
        -> document decoding
        -> structured parsing
        -> transaction normalization

It does not write directly to permanent storage. Storage remains controlled
by the standard ingestion pipeline.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from typing import Any, Mapping

from data.sec_form_parser import (
    SECFormParserError,
    parse_filing,
)
from ingestion.sec_client import (
    SECClient,
)
from data.sec_filing_client import (
    SECFilingClient,
)


class SECFilingPipelineError(
    Exception
):
    """Raised when SEC filing processing fails."""


def _decode_document(
    document: bytes,
) -> str:
    """
    Decode an SEC filing document into text.

    UTF-8 is attempted first, followed by Latin-1 as a permissive fallback.
    """

    if not isinstance(
        document,
        bytes,
    ):
        raise TypeError(
            "SEC filing document must be bytes."
        )

    if not document:
        raise SECFilingPipelineError(
            "SEC filing document is empty."
        )

    try:
        return document.decode(
            "utf-8"
        )
    except UnicodeDecodeError:
        try:
            return document.decode(
                "latin-1"
            )
        except UnicodeDecodeError as exc:
            raise SECFilingPipelineError(
                "SEC filing document could not be decoded."
            ) from exc


def _try_json(
    text: str,
) -> Mapping[str, Any] | None:
    """
    Attempt to interpret filing text as JSON.
    """

    try:
        payload = json.loads(
            text
        )
    except json.JSONDecodeError:
        return None

    if not isinstance(
        payload,
        Mapping,
    ):
        return None

    return payload


def _xml_to_dict(
    element: ET.Element,
) -> dict[str, Any]:
    """
    Convert a simple XML element tree into a dictionary.

    Repeated child tags become lists.
    """

    result: dict[str, Any] = {}

    for child in element:
        value: Any

        if len(child):
            value = _xml_to_dict(
                child
            )
        else:
            value = (
                child.text.strip()
                if child.text
                else ""
            )

        if child.tag in result:
            existing = result[
                child.tag
            ]

            if not isinstance(
                existing,
                list,
            ):
                result[
                    child.tag
                ] = [
                    existing
                ]

            result[
                child.tag
            ].append(
                value
            )

        else:
            result[
                child.tag
            ] = value

    return result


def _try_xml(
    text: str,
) -> Mapping[str, Any] | None:
    """
    Attempt to interpret filing text as XML.
    """

    try:
        root = ET.fromstring(
            text
        )
    except ET.ParseError:
        return None

    return {
        root.tag: _xml_to_dict(
            root
        )
    }


def _extract_embedded_json(
    text: str,
) -> Mapping[str, Any] | None:
    """
    Search for a JSON object embedded inside an SEC filing document.

    This is intentionally conservative and only attempts balanced outer
    object extraction.
    """

    stripped = text.strip()

    if not stripped:
        return None

    direct = _try_json(
        stripped
    )

    if direct is not None:
        return direct

    start = stripped.find(
        "{"
    )

    while start >= 0:
        depth = 0
        in_string = False
        escaped = False

        for index in range(
            start,
            len(stripped),
        ):
            character = stripped[
                index
            ]

            if escaped:
                escaped = False
                continue

            if character == "\\":
                escaped = True
                continue

            if character == '"':
                in_string = not in_string
                continue

            if in_string:
                continue

            if character == "{":
                depth += 1

            elif character == "}":
                depth -= 1

                if depth == 0:
                    candidate = stripped[
                        start:index + 1
                    ]

                    parsed = _try_json(
                        candidate
                    )

                    if parsed is not None:
                        return parsed

                    break

        start = stripped.find(
            "{",
            start + 1,
        )

    return None


def parse_filing_document(
    document: bytes,
) -> Mapping[str, Any]:
    """
    Decode and parse a retrieved SEC filing document.

    Supported representations:
        - JSON
        - XML
        - JSON embedded within a text/HTML document
    """

    text = _decode_document(
        document
    )

    payload = _try_json(
        text
    )

    if payload is not None:
        return payload

    payload = _try_xml(
        text
    )

    if payload is not None:
        return payload

    payload = _extract_embedded_json(
        text
    )

    if payload is not None:
        return payload

    raise SECFilingPipelineError(
        "SEC filing document could not be interpreted as JSON or XML."
    )


def extract_form_metadata(
    payload: Mapping[str, Any],
    *,
    default_form_type: str | None = None,
) -> dict[str, str | None]:
    """
    Extract common filing metadata from a parsed filing payload.
    """

    if not isinstance(
        payload,
        Mapping,
    ):
        raise TypeError(
            "payload must be a mapping."
        )

    form_type = None

    for key in (
        "form",
        "formType",
        "form_type",
    ):
        value = payload.get(
            key
        )

        if value is not None and str(
            value
        ).strip():
            form_type = str(
                value
            ).strip()
            break

    if form_type is None:
        form_type = default_form_type

    accession_number = None

    for key in (
        "accessionNumber",
        "accession_number",
        "accession",
    ):
        value = payload.get(
            key
        )

        if value is not None and str(
            value
        ).strip():
            accession_number = str(
                value
            ).strip()
            break

    filing_date = None

    for key in (
        "filingDate",
        "filing_date",
        "filedDate",
    ):
        value = payload.get(
            key
        )

        if value is not None and str(
            value
        ).strip():
            filing_date = str(
                value
            ).strip()
            break

    return {
        "form_type": form_type,
        "accession_number": accession_number,
        "filing_date": filing_date,
    }


def process_filing_document(
    document: bytes,
    *,
    issuer_cik: str,
    accession_number: str,
    form_type: str,
    issuer_name: str | None = None,
    insider_name: str | None = None,
    insider_cik: str | None = None,
    filing_date: str | None = None,
    source: str = "SEC",
) -> list[dict[str, Any]]:
    """
    Parse one SEC filing document into normalized transaction payloads.
    """

    payload = parse_filing_document(
        document
    )

    metadata = extract_form_metadata(
        payload,
        default_form_type=form_type,
    )

    normalized_accession = (
        metadata["accession_number"]
        or accession_number
    )

    normalized_form = (
        metadata["form_type"]
        or form_type
    )

    normalized_filing_date = (
        metadata["filing_date"]
        or filing_date
    )

    if not normalized_accession:
        raise SECFilingPipelineError(
            "SEC filing has no accession number."
        )

    if not normalized_form:
        raise SECFilingPipelineError(
            "SEC filing has no form type."
        )

    try:
        return parse_filing(
            payload,
            issuer_cik=issuer_cik,
            accession_number=normalized_accession,
            form_type=normalized_form,
            issuer_name=issuer_name,
            insider_name=insider_name,
            insider_cik=insider_cik,
            filing_date=normalized_filing_date,
            source=source,
        )

    except (
        SECFormParserError,
        TypeError,
        ValueError,
    ) as exc:
        raise SECFilingPipelineError(
            f"SEC transaction parsing failed: {exc}"
        ) from exc


def retrieve_and_process_filing(
    filing_client: SECFilingClient,
    *,
    cik: str,
    accession_number: str,
    document_name: str,
    form_type: str,
    issuer_name: str | None = None,
    insider_name: str | None = None,
    insider_cik: str | None = None,
    filing_date: str | None = None,
    source: str = "SEC",
) -> list[dict[str, Any]]:
    """
    Retrieve one SEC filing document and process its transactions.
    """

    if not isinstance(
        filing_client,
        SECFilingClient,
    ):
        raise TypeError(
            "filing_client must be an SECFilingClient."
        )

    try:
        document = filing_client.get_filing_document(
            cik=cik,
            accession_number=accession_number,
            document_name=document_name,
        )
    except Exception as exc:
        raise SECFilingPipelineError(
            f"SEC filing retrieval failed: {exc}"
        ) from exc

    return process_filing_document(
        document,
        issuer_cik=cik,
        accession_number=accession_number,
        form_type=form_type,
        issuer_name=issuer_name,
        insider_name=insider_name,
        insider_cik=insider_cik,
        filing_date=filing_date,
        source=source,
  )
