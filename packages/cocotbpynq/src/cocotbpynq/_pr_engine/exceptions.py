"""Custom exceptions for the PR simulation system."""


class PRError(Exception):
    """Base exception for all PR-related errors."""
    pass


class PRConfigError(PRError):
    """Configuration error."""
    pass


class PRReconfigurationError(PRError):
    """Reconfiguration error."""
    pass


class PRBuildError(PRError):
    """Build error."""
    pass
