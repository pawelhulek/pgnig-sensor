from typing import Optional, Dict, Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD

AUTH_SCHEMA = vol.Schema({
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
})


class PGNIGGasConfigFlow(ConfigFlow, domain="pgnig_gas_sensor"):
    """Example config flow."""

    async def async_step_import(self, import_config):
        return self.async_abort(reason="testestets")

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None):
        errors: Dict[str, str] = {}
        if user_input is not None:
            return self.async_create_entry(title="Pgnig sensor", data=user_input)
        return self.async_show_form(
            step_id="user", data_schema=AUTH_SCHEMA, errors=errors
        )
