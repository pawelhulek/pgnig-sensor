import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
})

DOMAIN = "pgnig_gas_sensor"

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
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    await hass.config_entries.async_forward_entry_setup(config_entry, "sensor")
    return True


async def async_unload_entry(hass, config_entry):
    await hass.config_entries.async_forward_entry_unload(config_entry, "sensor")
    return True
