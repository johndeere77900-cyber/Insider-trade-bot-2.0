from __future__ import annotations

from trading.paper import PaperTradingEngine


def test_paper_trading_engine_can_be_created() -> None:
    engine = PaperTradingEngine()

    assert engine is not None


def test_paper_trading_engine_starts_with_no_positions() -> None:
    engine = PaperTradingEngine()

    positions = engine.get_positions()

    assert positions == {}


def test_paper_trading_engine_starts_with_no_orders() -> None:
    engine = PaperTradingEngine()

    orders = engine.get_orders()

    assert orders == []
