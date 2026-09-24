"""
Exception hierarchy for the top-level Insider Trade Bot agent boundary.
"""

from __future__ import annotations


class AgentError(Exception):
    """Base exception for top-level agent failures."""


class AgentConfigurationError(AgentError):
    """Raised when the agent is incorrectly configured."""


class AgentNotRunningError(AgentError):
    """Raised when an operation requires a running agent."""


class AgentRequestError(AgentError):
    """Raised when an incoming agent request is invalid."""


class AgentExecutionError(AgentError):
    """Raised when an agent operation cannot be completed."""


class AgentSafetyError(AgentError):
    """Raised when an operation violates an agent safety boundary."""


class AgentDependencyError(AgentError):
    """Raised when a required application dependency is unavailable."""
