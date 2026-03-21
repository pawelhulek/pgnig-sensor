"""Repairs support for PGNIG Gas Sensor."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_create_repair_issue(
        hass: HomeAssistant,
        issue_domain: str,
        issue_id: str,
        translation_key: str,
        translation_placeholders: dict[str, Any] | None = None,
) -> None:
    """Create a repair issue."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        breaks_in_ha_version=None,
        is_fixable=False,
        issue_domain=DOMAIN,
        learn_more_url=None,
        severity=ir.IssueSeverity.WARNING,
        translation_key=translation_key,
        translation_placeholders=translation_placeholders,
    )


async def async_delete_issue(
        hass: HomeAssistant,
        issue_id: str,
) -> None:
    """Delete a repair issue."""
    ir.async_delete_issue(hass, DOMAIN, issue_id)
