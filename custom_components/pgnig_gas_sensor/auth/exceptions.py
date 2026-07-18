"""Authentication exceptions for Orlen EBOK login flows."""


class AuthError(Exception):
    """Base class for authentication errors."""


class InvalidAuthError(AuthError):
    """Username or password was rejected."""


class MfaRequired(AuthError):
    """OrlenID login requires an MFA code; session state is preserved for the next step."""

    def __init__(self, pending: dict) -> None:
        super().__init__("MFA code required")
        self.pending = pending


class MfaFailedError(AuthError):
    """Submitted MFA code was rejected."""


class MfaSessionExpiredError(MfaFailedError):
    """MFA session expired; user must log in again with password."""


class SessionExpiredError(AuthError):
    """OIDC session cookies expired; user must re-authenticate in config flow."""
