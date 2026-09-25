"""Errors raised by the Orlen EBOK API client."""
from __future__ import annotations


class PgnigApiError(Exception):
    """Base class for Orlen EBOK API errors."""


class ReadingRejectedError(PgnigApiError):
    """Orlen EBOK refused to accept a submitted meter reading."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
