from typing import Optional, Dict, Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD

from .auth import AuthRegistry
from .const import DOMAIN, CONF_AUTH_METHOD, DEFAULT_AUTH_METHOD
from .PgnigApi import PgnigApi


class PGNIGGasConfigFlow(ConfigFlow, domain=DOMAIN):
    async def async_step_import(self, import_config):
        return self.async_abort(reason="one_instance_at_a_time_please")

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None):
        errors: Dict[str, str] = {}
        description_placeholders: Dict[str, str] = {"error_info": ""}
        methods = AuthRegistry.list()

        if user_input is not None:
            auth_method = user_input.get(CONF_AUTH_METHOD, DEFAULT_AUTH_METHOD)
            username = user_input.get(CONF_USERNAME)
            password = user_input.get(CONF_PASSWORD)

            api = PgnigApi(username, password, auth_method)
            try:
                await self.hass.async_add_executor_job(api.login)
                data = {
                    CONF_USERNAME: username,
                    CONF_PASSWORD: password,
                    CONF_AUTH_METHOD: auth_method,
                }
                return self.async_create_entry(title="Pgnig sensor", data=data)
            except Exception:
                errors = {"base": "verify_connection_failed"}
                description_placeholders = {"error_info": "EBOK Login Failed"}

        schema_dict: Dict[str, Any] = {}
        if len(methods) > 1:
            options = [(m.id, m.name) for m in methods]
            schema_dict[vol.Required(CONF_AUTH_METHOD)] = vol.In(dict(options))
        schema_dict[vol.Required(CONF_USERNAME)] = cv.string
        schema_dict[vol.Required(CONF_PASSWORD)] = cv.string

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_reauth(self, user_input: Optional[Dict[str, Any]] = None):
        errors: Dict[str, str] = {}
        description_placeholders: Dict[str, str] = {"error_info": ""}
        methods = AuthRegistry.list()

        entry_id = self.context.get("entry_id")
        config_entry = self.hass.config_entries.async_get_entry(entry_id) if entry_id else None

        if user_input is not None and config_entry:
            auth_method = config_entry.data.get(CONF_AUTH_METHOD, DEFAULT_AUTH_METHOD)
            try:
                api = PgnigApi(
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                    auth_method,
                )
                await self.hass.async_add_executor_job(api.login)

                self.hass.config_entries.async_update_entry(
                    config_entry,
                    data={
                        **config_entry.data,
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )
                await self.hass.config_entries.async_reload(entry_id)
                return self.async_abort(reason="reauth_successful")
            except Exception:
                errors["base"] = "verify_connection_failed"
                description_placeholders["error_info"] = "Login Failed"

        schema_dict: Dict[str, Any] = {}
        if len(methods) > 1 and config_entry:
            current_method = config_entry.data.get(CONF_AUTH_METHOD, DEFAULT_AUTH_METHOD)
            options = [(m.id, m.name) for m in methods]
            schema_dict[vol.Required(CONF_AUTH_METHOD, default=current_method)] = vol.In(dict(options))
        schema_dict[vol.Required(CONF_USERNAME)] = cv.string
        schema_dict[vol.Required(CONF_PASSWORD)] = cv.string

        return self.async_show_form(
            step_id="reauth",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_reconfigure(self, user_input: Optional[Dict[str, Any]] = None):
        methods = AuthRegistry.list()
        entry_id = self.context.get("entry_id")
        config_entry = self.hass.config_entries.async_get_entry(entry_id) if entry_id else None

        if config_entry is None:
            return self.async_abort(reason="no_config_entry")

        if user_input is not None:
            auth_method = user_input.get(CONF_AUTH_METHOD, config_entry.data.get(CONF_AUTH_METHOD, DEFAULT_AUTH_METHOD))
            username = user_input.get(CONF_USERNAME)
            password = user_input.get(CONF_PASSWORD)

            try:
                api = PgnigApi(username, password, auth_method)
                await self.hass.async_add_executor_job(api.login)

                self.hass.config_entries.async_update_entry(
                    config_entry,
                    data={
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                        CONF_AUTH_METHOD: auth_method,
                    },
                )
                await self.hass.config_entries.async_reload(config_entry.entry_id)

                return self.async_abort(reason="reconfigure_successful")
            except Exception:
                errors = {"base": "verify_connection_failed"}
                description_placeholders = {"error_info": "Login Failed"}
        else:
            errors = {}
            description_placeholders = {"error_info": ""}

        current_method = config_entry.data.get(CONF_AUTH_METHOD, DEFAULT_AUTH_METHOD)
        schema_dict: Dict[str, Any] = {}
        if len(methods) > 1:
            options = [(m.id, m.name) for m in methods]
            schema_dict[vol.Required(CONF_AUTH_METHOD, default=current_method)] = vol.In(dict(options))
        schema_dict[vol.Required(CONF_USERNAME)] = cv.string
        schema_dict[vol.Required(CONF_PASSWORD)] = cv.string

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders=description_placeholders,
        )
