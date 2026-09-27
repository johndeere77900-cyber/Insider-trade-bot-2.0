from __future__ import annotations

import sys

from application.agent_bootstrap import AgentBootstrap
from application.configuration import ApplicationConfiguration
from config.environment import (
    EnvironmentConfigurationError,
    load_environment,
)
from config.environment_validator import (
    EnvironmentValidationError,
    EnvironmentValidator,
)
from core.logging_config import configure_logging


def main() -> int:
    """
    Main executable entry point for Insider Trade Bot 2.0.

    Startup order:
        1. Load environment configuration.
        2. Validate configuration.
        3. Configure application logging.
        4. Assemble and start the application runtime.

    Live trading remains controlled by the application's execution
    and safety layers and is disabled by default.
    """

    try:
        settings = load_environment()

        EnvironmentValidator().require_valid(settings)

        configure_logging(
            level=settings.log_level,
            logs_directory=settings.log_directory,
        )

        configuration = ApplicationConfiguration(
            environment=settings.environment,
            paper_trading_enabled=settings.paper_trading,
            live_trading_enabled=settings.live_trading,
            telegram_enabled=settings.telegram_enabled,
            historical_data_available=False,
            strict_mode=settings.strict_mode,
        )

        agent = AgentBootstrap(
            configuration=configuration,
        ).build()

        result = agent.entrypoint.start()

    except (
        EnvironmentConfigurationError,
        EnvironmentValidationError,
        ValueError,
    ) as exc:
        print(
            f"Startup configuration error: {exc}",
            file=sys.stderr,
        )
        return 1

    except Exception as exc:
        print(
            f"Agent startup error: {exc}",
            file=sys.stderr,
        )
        return 1

    if not result.success:
        print(
            f"Agent startup failed: {result.message}",
            file=sys.stderr,
        )
        return 1

    print("Insider Trade Bot 2.0 started successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
