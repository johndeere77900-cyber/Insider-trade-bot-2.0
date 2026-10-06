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


def test_main_historical_cli_args(monkeypatch) -> None:
    called_args = {}

    def mock_run_historical(start, end, batch_size=5000, force=False, **kwargs):
        called_args["start"] = start
        called_args["end"] = end
        called_args["batch_size"] = batch_size
        called_args["force"] = force
        return 0

    monkeypatch.setattr(main, "run_historical_acquisition", mock_run_historical)
    monkeypatch.setattr("sys.argv", ["main.py", "historical", "--start", "2006-Q1", "--end", "2006-Q2", "--batch-size", "1000", "--force"])

    result = main.main()

    assert result == 0
    assert called_args == {
        "start": "2006-Q1",
        "end": "2006-Q2",
        "batch_size": 1000,
        "force": True,
    }
