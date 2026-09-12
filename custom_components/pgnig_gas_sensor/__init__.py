"""Init for PGNIG Gas Sensor."""
from __future__ import annotations

import logging
from datetime import timedelta

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import entity_registry
from homeassistant.helpers.event import async_track_time_interval

from .auth.exceptions import AuthError
from .const import (
    AUTH_METHOD_ORLEN_ID,
    CONF_AUTH_METHOD,
    CONF_ORLEN_SESSION,
    CONF_MFA_ENABLED,
    DEFAULT_AUTH_METHOD,
    DOMAIN,
    ORLEN_SESSION_REFRESH_MINUTES,
)
from .PgnigApi import PgnigApi
from .PgpList import PpgList
from .runtime import PgnigRuntimeData

_LOGGER = logging.getLogger(__name__)

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
    mfa_enabled = config_entry.data.get(CONF_MFA_ENABLED, True)
    session_data = config_entry.data.get(CONF_ORLEN_SESSION)
    api = PgnigApi(user, password, auth_method, session_data=session_data, mfa_enabled=mfa_enabled)
    hass.data[DOMAIN][config_entry.entry_id] = await _async_build_runtime_data(hass, api)

    await hass.config_entries.async_forward_entry_setups(config_entry, ["sensor", "button"])

    async def handle_refresh(call):
        _LOGGER.debug("Refresh service called for config entry %s", config_entry.entry_id)
        er = entity_registry.async_get(hass)
        entities = [
            entry.entity_id
            for entry in list(er.entities.values())
            if entry.config_entry_id == config_entry.entry_id
        ]
        _LOGGER.debug("Found %d entities to refresh: %s", len(entities), entities)
        for entity_id in entities:
            _LOGGER.debug("Triggering update for %s", entity_id)
            await hass.services.async_call(
                "homeassistant", "update_entity",
                {"entity_id": entity_id},
                blocking=True
            )
        _LOGGER.debug("Refresh complete for config entry %s", config_entry.entry_id)

    hass.services.async_register(
        DOMAIN, "refresh", handle_refresh,
        schema=vol.Schema({})
    )
    _LOGGER.debug("Registered service %s.refresh", DOMAIN)

    if auth_method == AUTH_METHOD_ORLEN_ID:

        @callback
        def _schedule_orlen_session_refresh(_now) -> None:
            hass.async_create_task(
                _async_refresh_orlen_session(hass, config_entry)
            )

        config_entry.async_on_unload(
            async_track_time_interval(
                hass,
                _schedule_orlen_session_refresh,
                timedelta(minutes=ORLEN_SESSION_REFRESH_MINUTES),
            )
        )

    return True


async def _async_build_runtime_data(
    hass: HomeAssistant, api: PgnigApi
) -> PgnigRuntimeData:
    """Authenticate and resolve the meter list before any platform is forwarded.

    ConfigEntryAuthFailed puts the entry into an error state on the integrations
    page and starts the reauth flow, which is the only way the user is asked to
    log in again. Everything else is treated as transient so HA retries setup
    instead of demanding credentials over a dropped connection.
    """

    def _load() -> PpgList:
        api.login()
        return api.meterList()

    try:
        return PgnigRuntimeData(
            api=api, meters=await hass.async_add_executor_job(_load)
        )
    except AuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except Exception as err:
        raise ConfigEntryNotReady(f"Could not reach Orlen EBOK: {err}") from err


async def _async_refresh_orlen_session(hass: HomeAssistant, config_entry) -> None:
    """Refresh OrlenID cookies/token in the background without MFA."""
    runtime = hass.data[DOMAIN].get(config_entry.entry_id)
    if runtime is None:
        return
    api = runtime.api

    def _refresh() -> tuple[str, dict | None]:
        token = api.refresh_auth_token()
        return token, api.export_orlen_session()

    try:
        token, session = await hass.async_add_executor_job(_refresh)
    except AuthError as err:
        _LOGGER.warning(
            "OrlenID session expired and requires re-authentication: %s", err
        )
        config_entry.async_start_reauth(hass)
        return
    except Exception as err:
        _LOGGER.warning("Background OrlenID session refresh failed: %s", err)
        return

    if not token or not session:
        return

    hass.config_entries.async_update_entry(
        config_entry,
        data={**config_entry.data, CONF_ORLEN_SESSION: session},
    )
    _LOGGER.debug("OrlenID session refreshed in background")


async def async_unload_entry(hass, config_entry):
    if hass.services.has_service(DOMAIN, "refresh"):
        hass.services.async_remove(DOMAIN, "refresh")
    hass.data[DOMAIN].pop(config_entry.entry_id, None)
    unload_ok = True
    for platform in ("sensor", "button"):
        if not await hass.config_entries.async_forward_entry_unload(
            config_entry, platform
        ):
            unload_ok = False
    return unload_ok
