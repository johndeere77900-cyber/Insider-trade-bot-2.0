from __future__ import annotations


def test_core_modules_import() -> None:
    import core.hashing
    import core.models
    import core.logging_config


def test_data_modules_import() -> None:
    import data.normalization
    import data.ingestion_pipeline
    import data.historical_loader
    import data.market_data_client


def test_research_and_signal_modules_import() -> None:
    import research.event_study
    import research.performance
    import signals.signal_engine
    import backtesting.engine
    import outcomes.engine


def test_trading_and_execution_modules_import() -> None:
    import trading.paper
    import trading.live
    import trading.portfolio
    import execution.interface
    import execution.safety
    import execution.mode


def test_telegram_modules_import() -> None:
    import telegram.parser
    import telegram.router
    import telegram.service
    import telegram.application


def test_application_modules_import() -> None:
    import application.service
    import application.factory
    import application.bootstrap
    import application.runtime
    import application.agent
