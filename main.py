from __future__ import annotations

import sys

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
        4. Hand control to the assembled application runtime.

    No trading operation is started directly from this function.
    Live trading remains controlled by the application's execution
    and safety layers.
    """

    try:
        settings = load_environment()

        EnvironmentValidator().require_valid(settings)

        configure_logging(
            level=settings.log_level,
            logs_directory=settings.log_directory,
        )

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

    # Application runtime startup will be connected here after the
    # assembled application layer has completed its integration audit.
    #
    # Keeping this boundary explicit prevents main.py from bypassing
    # application lifecycle, safety, execution-mode, and Telegram
    # controls.

    print(
        "Insider Trade Bot 2.0 configuration validated successfully."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
