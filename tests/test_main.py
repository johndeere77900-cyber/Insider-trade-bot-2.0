from __future__ import annotations

import main


def test_main_module_imports() -> None:
    assert callable(main.main)


def test_main_returns_success_with_valid_environment(
    monkeypatch,
) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "testing")
    monkeypatch.setenv("APP_STRICT_MODE", "false")
    monkeypatch.setenv("APP_LIVE_TRADING", "false")
    monkeypatch.setenv("APP_PAPER_TRADING", "true")
    monkeypatch.setenv("APP_TELEGRAM_ENABLED", "false")
    monkeypatch.setenv(
        "DATABASE_URL",
        "sqlite:///data/test.db",
    )
    monkeypatch.setenv(
        "SEC_USER_AGENT",
        "InsiderTradeBotTest/test@example.com",
    )
    monkeypatch.setenv("SEC_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("TRADING_MODE", "paper")
    monkeypatch.setenv(
        "LIVE_TRADING_CONFIRMATION",
        "false",
    )
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("LOG_DIRECTORY", "logs")

    result = main.main()

    assert result == 0


def test_main_rejects_invalid_environment(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "APP_ENVIRONMENT",
        "invalid",
    )

    result = main.main()

    assert result == 1
