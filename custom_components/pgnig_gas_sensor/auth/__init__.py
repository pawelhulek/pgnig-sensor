"""Authentication method abstraction for Orlen EBOK."""
from __future__ import annotations

import secrets
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
    return secrets.token_hex(16)


from .api_login import ApiLoginAuth  # noqa: E402
from .orlen_id import OrlenIDAuth  # noqa: E402
