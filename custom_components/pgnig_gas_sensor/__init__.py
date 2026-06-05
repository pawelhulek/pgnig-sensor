"""Init for PGNIG Gas Sensor."""
from __future__ import annotations

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.helpers import entity_registry

from .const import DOMAIN, CONF_AUTH_METHOD, DEFAULT_AUTH_METHOD
from .PgnigApi import PgnigApi

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
})

async def async_setup(hass, config):
    hass.data[DOMAIN] = {}
    if not hass.config_entries.async_entries(DOMAIN) and DOMAIN in config:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data=config[DOMAIN]
            )
        )
    return True


async def async_setup_entry(hass, config_entry):
    hass.data.setdefault(DOMAIN, {})

    user = config_entry.data[CONF_USERNAME]
    password = config_entry.data[CONF_PASSWORD]
    auth_method = config_entry.data.get(CONF_AUTH_METHOD, DEFAULT_AUTH_METHOD)
    api = PgnigApi(user, password, auth_method)
    hass.data[DOMAIN][config_entry.entry_id] = api

    await hass.config_entries.async_forward_entry_setups(config_entry, ["sensor", "button"])

    async def handle_refresh(call):
        er = entity_registry.async_get(hass)
        for entry in list(er.entities.values()):
            if entry.config_entry_id == config_entry.entry_id:
                await hass.services.async_call(
                    "homeassistant", "update_entity",
                    {"entity_id": entry.entity_id},
                    blocking=True
                )

    hass.services.async_register(
        DOMAIN, "refresh", handle_refresh,
        schema=vol.Schema({})
    )

    return True


async def async_unload_entry(hass, config_entry):
    if hass.services.async_has_service(DOMAIN, "refresh"):
        hass.services.async_remove(DOMAIN, "refresh")
    hass.data[DOMAIN].pop(config_entry.entry_id, None)
    await hass.config_entries.async_forward_entry_unload(config_entry, "sensor")
    await hass.config_entries.async_forward_entry_unload(config_entry, "button")
    return True
