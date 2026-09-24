from __future__ import annotations

from data.sec_company_data import SECCompanyData
from data.sec_form_parser import SECFormParser
from data.sec_historical_loader import SECHistoricalLoader
from data.sec_historical_orchestrator import SECHistoricalOrchestrator


def test_sec_company_data_can_be_created() -> None:
    client = SECCompanyData(
        user_agent="InsiderTradeBotTest/test@example.com"
    )

    assert client is not None


def test_sec_form_parser_can_be_created() -> None:
    parser = SECFormParser()

    assert parser is not None


def test_sec_historical_loader_can_be_created() -> None:
    loader = SECHistoricalLoader()

    assert loader is not None


def test_sec_historical_orchestrator_can_be_created() -> None:
    orchestrator = SECHistoricalOrchestrator()

    assert orchestrator is not None
