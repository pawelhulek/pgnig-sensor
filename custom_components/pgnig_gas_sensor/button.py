"""Button support for PGNIG Gas Sensor."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the PGNIG button."""
    api = hass.data[DOMAIN][config_entry.entry_id]
    meter_list = await hass.async_add_executor_job(api.meterList)

    buttons = [
        PgnigRefreshButton(hass, meter.meter_number, meter.id_local, config_entry.entry_id)
        for meter in meter_list.ppg_list
    ]
    async_add_entities(buttons)


class PgnigRefreshButton(ButtonEntity):
    """Refresh button for PGNIG sensor data."""

    _attr_has_entity_name = True
    _attr_translation_key = "refresh_data"

    def __init__(self, hass: HomeAssistant, meter_id: str, id_local: int, entry_id: str) -> None:
        self.hass = hass
        self.meter_id = meter_id
        self.id_local = id_local
        self._entry_id = entry_id
        self._attr_unique_id = f"pgnig_refresh_{meter_id}_{id_local}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, meter_id)},
            "name": f"Orlen Gas Meter {meter_id}",
            "manufacturer": "Orlen",
            "model": meter_id,
        }

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.debug("Refresh button pressed for meter %s (id_local=%d, entry=%s)",
                     self.meter_id, self.id_local, self._entry_id)
        await self.hass.services.async_call(
            DOMAIN, "refresh", {},
            blocking=True
        )
        _LOGGER.debug("Refresh complete for meter %s", self.meter_id)
