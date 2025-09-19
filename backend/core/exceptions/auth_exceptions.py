from .base_exceptions import AuthenticationError, AuthorizationError


class InvalidTokenError(AuthenticationError):
    """Invalid or expired authentication token."""

    def __init__(self, message: str = "Invalid or expired token", **kwargs):
        super().__init__(message, **kwargs)


class TokenRevokedError(AuthenticationError):
    """Authentication token has been revoked."""

    def __init__(self, message: str = "Token has been revoked", **kwargs):
        super().__init__(message, **kwargs)
