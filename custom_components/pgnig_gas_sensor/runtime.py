"""Runtime objects shared between the integration's platforms.

The meter list is resolved once in async_setup_entry so that sensor and button
setup do not each re-fetch it, and so an expired session is reported through
ConfigEntryAuthFailed before any platform is forwarded.
"""
from __future__ import annotations

from dataclasses import dataclass

from .PgnigApi import PgnigApi
from .PgpList import PpgList


@dataclass(frozen=True)
class PgnigRuntimeData:
    """Everything a platform needs, resolved during setup."""

    api: PgnigApi
    meters: PpgList
