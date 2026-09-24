"""
Runtime environment helpers for Insider Trade Bot 2.0.

This module provides small, centralized helpers for identifying and
validating the execution environment.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AgentEnvironment(str, Enum):
    """Supported runtime environments."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


@dataclass(frozen=True)
class EnvironmentInfo:
    """Normalized runtime environment information."""

    environment: AgentEnvironment

    @property
    def is_development(self) -> bool:
        return self.environment is AgentEnvironment.DEVELOPMENT

    @property
    def is_testing(self) -> bool:
        return self.environment is AgentEnvironment.TESTING

    @property
    def is_staging(self) -> bool:
        return self.environment is AgentEnvironment.STAGING

    @property
    def is_production(self) -> bool:
        return self.environment is AgentEnvironment.PRODUCTION

    def to_dict(self) -> dict[str, str]:
        return {
            "environment": self.environment.value,
        }


def resolve_environment(value: str) -> EnvironmentInfo:
    """
    Convert a string environment name into normalized environment info.
    """
    if not value or not value.strip():
        raise ValueError("Environment value must not be empty.")

    normalized = value.strip().lower()

    aliases = {
        "dev": AgentEnvironment.DEVELOPMENT,
        "development": AgentEnvironment.DEVELOPMENT,
        "test": AgentEnvironment.TESTING,
        "testing": AgentEnvironment.TESTING,
        "stage": AgentEnvironment.STAGING,
        "staging": AgentEnvironment.STAGING,
        "prod": AgentEnvironment.PRODUCTION,
        "production": AgentEnvironment.PRODUCTION,
    }

    try:
        environment = aliases[normalized]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported agent environment: {value!r}"
        ) from exc

    return EnvironmentInfo(environment=environment)
