from __future__ import annotations

from pathlib import Path

from data.sec_filing_pipeline import parse_filing_document
from data.sec_form_parser import parse_filing


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "form4_realistic.xml"
)


def test_realistic_sec_form4_xml_parses_into_transactions() -> None:
    payload = parse_filing_document(
        FIXTURE.read_bytes()
    )

    records = parse_filing(
        payload,
        issuer_cik="1234567",
        accession_number="0001234567-26-000001",
        form_type="4",
    )

    assert len(records) == 2

    first, second = records

    assert first["form_type"] == "4"
    assert first["issuer_cik"] == "0001234567"
    assert first["issuer_name"] == "Example Holdings Inc."
    assert first["insider_name"] == "Jane Doe"
    assert first["insider_cik"] == "0007654321"
    assert first["security_title"] == "Common Stock"
    assert first["transaction_date"] == "2026-09-23"
    assert first["transaction_code"] == "P"
    assert first["shares"] == 1000.0
    assert first["price"] == 25.50
    assert first["ownership_type"] == "D"

    assert second["transaction_code"] == "S"
    assert second["shares"] == 250.0
    assert second["price"] == 26.75
    assert second["ownership_type"] == "I"
