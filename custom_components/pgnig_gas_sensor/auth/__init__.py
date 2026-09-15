"""Authentication method abstraction for Orlen EBOK."""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import requests


@dataclass
class AuthMethodInfo:
    id: str
    name: str
    description: str


class AuthMethod(ABC):
    #: Last token handed out by login(); subclasses set this when they fetch one.
    _cached_token: str = ""

    @property
    def cached_token(self) -> str:
        """The token currently held, or "" when there is none."""
        return self._cached_token

    def restore_token(self, token: str) -> None:
        """Put back a token that was dropped for a refresh that then failed."""
        self._cached_token = token

    @property
    @abstractmethod
    def info(self) -> AuthMethodInfo:
        pass

    @property
    @abstractmethod
    def session(self) -> requests.Session:
        pass

    @abstractmethod
    def login(self) -> str:
        pass

    @abstractmethod
    def invalidate_token(self) -> None:
        pass


class AuthRegistry:
    _methods: dict[str, type[AuthMethod]] = {}

    @classmethod
    def register(cls, method_class: type[AuthMethod]) -> type[AuthMethod]:
        instance = method_class("", "")
        cls._methods[instance.info.id] = method_class
        return method_class

    @classmethod
    def get(cls, method_id: str) -> Optional[type[AuthMethod]]:
        return cls._methods.get(method_id)

    @classmethod
    def list(cls) -> list[AuthMethodInfo]:
        return [m("", "").info for m in cls._methods.values()]

    @classmethod
    def get_ids(cls) -> list[str]:
        return list(cls._methods.keys())


def device_id(username: str) -> str:
    """Stable per-account device token.

    Orlen remembers a device by the `pgnig-ebok-device-token` cookie and only
    challenges an unrecognised one with an SMS code. This used to return
    `secrets.token_hex(16)`, ignoring `username`, so every login that started
    without a stored session looked like a brand new device: Orlen demanded MFA
    every time, `mfa_enabled` was always recorded as True, and the integration
    could never restore a session on its own once the SSO session expired.

    Derived from the username so it survives re-authentication, and hashed so
    the account name is not sent as the token. Same 32-hex-character shape as
    the value it replaces.
    """
    return hashlib.sha256(f"pgnig-ebok:{username}".encode()).hexdigest()[:32]


from .api_login import ApiLoginAuth  # noqa: E402
from .exceptions import (  # noqa: E402
    AuthError,
    InvalidAuthError,
    MfaFailedError,
    MfaRequired,
    SessionExpiredError,
)
from .orlen_id import OrlenIDAuth  # noqa: E402
