"""
Application-layer exception hierarchy.
"""


class ApplicationError(Exception):
    """Base exception for application-layer failures."""


class ApplicationConfigurationError(ApplicationError):
    """Raised when required application configuration is invalid."""


class ApplicationDependencyError(ApplicationError):
    """Raised when a required application dependency is unavailable."""


class ApplicationRequestError(ApplicationError):
    """Raised when an application request is invalid."""


class ApplicationAuthorizationError(ApplicationError):
    """Raised when a request is not authorized."""


class ApplicationExecutionError(ApplicationError):
    """Raised when an application operation fails during execution."""
