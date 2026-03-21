"""Button support for PGNIG Gas Sensor."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .PgnigApi import PgnigApi

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the PGNIG button."""
    username = config_entry.data.get(CONF_USERNAME)
    password = config_entry.data.get(CONF_PASSWORD)

    api = PgnigApi(username, password)
    meter_list = await hass.async_add_executor_job(api.meterList)

    buttons = []
    for meter in meter_list.ppg_list:
        buttons.append(PgnigRefreshButton(hass, api, meter.meter_number, meter.id_local))

    async_add_entities(buttons)


class PgnigRefreshButton(ButtonEntity):
    """Refresh button for PGNIG sensor data."""

    _attr_has_entity_name = True
    _attr_translation_key = "refresh_data"

    def __init__(self, hass: HomeAssistant, api: PgnigApi, meter_id: str, id_local: int) -> None:
        self.hass = hass
        self.api = api
        self.meter_id = meter_id
        self.id_local = id_local
        self._attr_unique_id = f"pgnig_refresh_{meter_id}_{id_local}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, meter_id)},
            "name": f"Orlen Gas Meter {meter_id}",
            "manufacturer": "Orlen",
            "model": meter_id,
        }

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.hass.async_add_executor_job(self.api.meterList)
