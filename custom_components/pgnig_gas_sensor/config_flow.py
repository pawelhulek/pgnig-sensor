from __future__ import annotations

import logging
from typing import Any, Optional

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from .auth import AuthRegistry
from .auth.exceptions import MfaFailedError, MfaRequired, MfaSessionExpiredError
from .const import (
    AUTH_METHOD_ORLEN_ID,
    CONF_AUTH_METHOD,
    CONF_MFA_CODE,
    CONF_ORLEN_SESSION,
    DEFAULT_AUTH_METHOD,
    DOMAIN,
)
from .PgnigApi import PgnigApi

_LOGGER = logging.getLogger(__name__)


class PGNIGGasConfigFlow(ConfigFlow, domain=DOMAIN):
    def __init__(self) -> None:
        self._pending_mfa: dict[str, Any] | None = None
        self._login_context: dict[str, Any] | None = None
        self._authenticated_api: PgnigApi | None = None

    async def async_step_import(self, import_config):
        return self.async_abort(reason="one_instance_at_a_time_please")

    def _credentials_schema(
        self,
        methods: list,
        auth_method_default: str | None = None,
    ) -> vol.Schema:
        schema_dict: dict[Any, Any] = {}
        if len(methods) > 1:
            options = [(m.id, m.name) for m in methods]
            if auth_method_default is not None:
                schema_dict[vol.Required(CONF_AUTH_METHOD, default=auth_method_default)] = vol.In(
                    dict(options)
                )
            else:
                schema_dict[vol.Required(CONF_AUTH_METHOD)] = vol.In(dict(options))
        schema_dict[vol.Required(CONF_USERNAME)] = cv.string
        schema_dict[vol.Required(CONF_PASSWORD)] = cv.string
        return vol.Schema(schema_dict)

    def _store_login_context(
        self,
        *,
        mode: str,
        username: str,
        password: str,
        auth_method: str,
        entry_id: str | None = None,
        pending_mfa: dict[str, Any],
    ) -> None:
        self._pending_mfa = pending_mfa
        self._login_context = {
            "mode": mode,
            "username": username,
            "password": password,
            "auth_method": auth_method,
            "entry_id": entry_id,
        }

    async def _perform_login(
        self,
        username: str,
        password: str,
        auth_method: str,
    ) -> None:
        api = PgnigApi(username, password, auth_method)
        await self.hass.async_add_executor_job(
            lambda: api.login(allow_interactive=True)
        )
        self._authenticated_api = api

    async def _perform_mfa(self, code: str) -> None:
        if not self._pending_mfa or not self._login_context:
            raise RuntimeError("MFA state missing from config flow")

        api = PgnigApi(
            self._login_context["username"],
            self._login_context["password"],
            self._login_context["auth_method"],
        )
        await self.hass.async_add_executor_job(
            api.complete_mfa, self._pending_mfa, code
        )
        self._authenticated_api = api

    def _entry_data(self) -> dict[str, Any]:
        if not self._login_context:
            raise RuntimeError("Login context missing from config flow")
        data: dict[str, Any] = {
            CONF_USERNAME: self._login_context["username"],
            CONF_PASSWORD: self._login_context["password"],
            CONF_AUTH_METHOD: self._login_context["auth_method"],
        }
        if self._authenticated_api:
            session = self._authenticated_api.export_orlen_session()
            if session:
                data[CONF_ORLEN_SESSION] = session
        return data

    async def _finalize_success(self):
        if not self._login_context:
            raise RuntimeError("Login context missing from config flow")

        mode = self._login_context["mode"]
        data = self._entry_data()
        self._pending_mfa = None
        self._login_context = None
        self._authenticated_api = None

        if mode == "user":
            return self.async_create_entry(title="Pgnig sensor", data=data)

        entry_id = self.context.get("entry_id")
        config_entry = (
            self.hass.config_entries.async_get_entry(entry_id) if entry_id else None
        )
        if config_entry is None:
            return self.async_abort(reason="no_config_entry")

        self.hass.config_entries.async_update_entry(config_entry, data=data)
        await self.hass.config_entries.async_reload(config_entry.entry_id)
        if mode == "reauth":
            return self.async_abort(reason="reauth_successful")
        return self.async_abort(reason="reconfigure_successful")

    async def _handle_login_exception(
        self,
        exc: Exception,
        *,
        mode: str,
        username: str,
        password: str,
        auth_method: str,
        entry_id: str | None = None,
    ):
        if isinstance(exc, MfaRequired):
            if auth_method != AUTH_METHOD_ORLEN_ID:
                return "verify_connection_failed", "MFA is only supported for OrlenID"
            self._store_login_context(
                mode=mode,
                username=username,
                password=password,
                auth_method=auth_method,
                entry_id=entry_id,
                pending_mfa=exc.pending,
            )
            return await self.async_step_mfa()

        _LOGGER.exception("Orlen EBOK login failed during %s", mode)
        message = str(exc).strip() or "EBOK Login Failed"
        return "verify_connection_failed", message

    async def _return_to_credentials_after_mfa_expiry(self):
        """Restart config flow from login/password after MFA session was reset."""
        if not self._login_context:
            return self.async_abort(reason="no_config_entry")

        mode = self._login_context["mode"]
        username = self._login_context["username"]
        auth_method = self._login_context["auth_method"]
        entry_id = self._login_context.get("entry_id")
        self._pending_mfa = None

        errors = {"base": "mfa_session_expired"}
        description_placeholders = {
            "error_info": (
                "The MFA session expired (for example after several wrong codes). "
                "Log in again with username and password, then enter the latest SMS code."
            )
        }
        methods = AuthRegistry.list()

        if mode == "user":
            return self.async_show_form(
                step_id="user",
                data_schema=self._credentials_schema(methods),
                errors=errors,
                description_placeholders=description_placeholders,
            )

        current_method = auth_method
        config_entry = None
        if entry_id:
            config_entry = self.hass.config_entries.async_get_entry(entry_id)
            if config_entry:
                current_method = config_entry.data.get(CONF_AUTH_METHOD, auth_method)

        step_id = "reauth" if mode == "reauth" else "reconfigure"
        return self.async_show_form(
            step_id=step_id,
            data_schema=self._credentials_schema(methods, current_method),
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_mfa(self, user_input: Optional[dict[str, Any]] = None):
        errors: dict[str, str] = {}
        description_placeholders = {"error_info": ""}

        if self._pending_mfa is None or self._login_context is None:
            return self.async_abort(reason="no_config_entry")

        if user_input is not None:
            try:
                await self._perform_mfa(user_input[CONF_MFA_CODE])
                return await self._finalize_success()
            except MfaSessionExpiredError as exc:
                return await self._return_to_credentials_after_mfa_expiry()
            except MfaFailedError as exc:
                errors = {"base": "mfa_failed"}
                description_placeholders = {"error_info": str(exc)}
            except Exception as exc:
                _LOGGER.exception("OrlenID MFA verification failed")
                errors = {"base": "mfa_failed"}
                description_placeholders = {"error_info": str(exc) or "MFA verification failed"}

        return self.async_show_form(
            step_id="mfa",
            data_schema=vol.Schema({vol.Required(CONF_MFA_CODE): cv.string}),
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_user(self, user_input: Optional[dict[str, Any]] = None):
        errors: dict[str, str] = {}
        description_placeholders = {"error_info": ""}
        methods = AuthRegistry.list()

        if user_input is not None:
            auth_method = user_input.get(CONF_AUTH_METHOD, DEFAULT_AUTH_METHOD)
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]
            try:
                await self._perform_login(username, password, auth_method)
                return self.async_create_entry(
                    title="Pgnig sensor",
                    data={
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                        CONF_AUTH_METHOD: auth_method,
                    },
                )
            except Exception as exc:
                result = await self._handle_login_exception(
                    exc,
                    mode="user",
                    username=username,
                    password=password,
                    auth_method=auth_method,
                )
                if not isinstance(result, tuple):
                    return result
                errors = {"base": result[0]}
                description_placeholders = {"error_info": result[1]}

        return self.async_show_form(
            step_id="user",
            data_schema=self._credentials_schema(methods),
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_reauth(self, user_input: Optional[dict[str, Any]] = None):
        errors: dict[str, str] = {}
        description_placeholders = {"error_info": ""}
        methods = AuthRegistry.list()
        entry_id = self.context.get("entry_id")
        config_entry = (
            self.hass.config_entries.async_get_entry(entry_id) if entry_id else None
        )

        if user_input is not None and config_entry:
            auth_method = user_input.get(
                CONF_AUTH_METHOD,
                config_entry.data.get(CONF_AUTH_METHOD, DEFAULT_AUTH_METHOD),
            )
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]
            try:
                await self._perform_login(username, password, auth_method)
                self.hass.config_entries.async_update_entry(
                    config_entry,
                    data={
                        **config_entry.data,
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                        CONF_AUTH_METHOD: auth_method,
                    },
                )
                await self.hass.config_entries.async_reload(entry_id)
                return self.async_abort(reason="reauth_successful")
            except Exception as exc:
                result = await self._handle_login_exception(
                    exc,
                    mode="reauth",
                    username=username,
                    password=password,
                    auth_method=auth_method,
                    entry_id=entry_id,
                )
                if not isinstance(result, tuple):
                    return result
                errors = {"base": result[0]}
                description_placeholders = {"error_info": result[1]}

        current_method = (
            config_entry.data.get(CONF_AUTH_METHOD, DEFAULT_AUTH_METHOD)
            if config_entry
            else DEFAULT_AUTH_METHOD
        )
        return self.async_show_form(
            step_id="reauth",
            data_schema=self._credentials_schema(methods, current_method),
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_reconfigure(self, user_input: Optional[dict[str, Any]] = None):
        methods = AuthRegistry.list()
        entry_id = self.context.get("entry_id")
        config_entry = (
            self.hass.config_entries.async_get_entry(entry_id) if entry_id else None
        )

        if config_entry is None:
            return self.async_abort(reason="no_config_entry")

        errors: dict[str, str] = {}
        description_placeholders = {"error_info": ""}
        current_method = config_entry.data.get(CONF_AUTH_METHOD, DEFAULT_AUTH_METHOD)

        if user_input is not None:
            auth_method = user_input.get(CONF_AUTH_METHOD, current_method)
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]
            try:
                await self._perform_login(username, password, auth_method)
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
            except Exception as exc:
                result = await self._handle_login_exception(
                    exc,
                    mode="reconfigure",
                    username=username,
                    password=password,
                    auth_method=auth_method,
                    entry_id=entry_id,
                )
                if not isinstance(result, tuple):
                    return result
                errors = {"base": result[0]}
                description_placeholders = {"error_info": result[1]}

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._credentials_schema(methods, current_method),
            errors=errors,
            description_placeholders=description_placeholders,
        )
