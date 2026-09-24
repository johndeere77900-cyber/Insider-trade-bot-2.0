"""
Configuration package for Insider Trade Bot 2.0.

This package contains environment loading, validation, and application
configuration boundaries.
"""

from config.environment import (
    EnvironmentConfigurationError,
    EnvironmentSettings,
    load_environment,
)
from config.environment_validator import (
    EnvironmentValidationError,
    EnvironmentValidationResult,
    EnvironmentValidator,
    validate_environment,
)

__all__ = [
    "EnvironmentConfigurationError",
    "EnvironmentSettings",
    "EnvironmentValidationError",
    "EnvironmentValidationResult",
    "EnvironmentValidator",
    "load_environment",
    "validate_environment",
]
