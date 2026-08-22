"""Init for PGNIG Gas Sensor."""
from __future__ import annotations

import logging
from datetime import timedelta

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry
from homeassistant.helpers.event import async_track_time_interval

from .auth.exceptions import InvalidAuthError, MfaRequired, SessionExpiredError
from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_CONSENT_METER_RESET,
    ATTR_DATE,
    ATTR_METER_ID,
    ATTR_VALUE,
    AUTH_METHOD_ORLEN_ID,
    CONF_AUTH_METHOD,
    CONF_ORLEN_SESSION,
    DEFAULT_AUTH_METHOD,
    DOMAIN,
    ORLEN_SESSION_REFRESH_MINUTES,
    SERVICE_ADD_READING,
    SERVICE_REFRESH,
)
from .exceptions import ReadingRejectedError
from .PgnigApi import PgnigApi

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
})

ADD_READING_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_METER_ID): cv.string,
        vol.Required(ATTR_VALUE): vol.All(vol.Coerce(float), vol.Range(min=0)),
        vol.Optional(ATTR_DATE): cv.date,
        vol.Optional(ATTR_CONSENT_METER_RESET, default=False): cv.boolean,
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
    }
)

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
    session_data = config_entry.data.get(CONF_ORLEN_SESSION)
    api = PgnigApi(user, password, auth_method, session_data=session_data)
    hass.data[DOMAIN][config_entry.entry_id] = api

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
        DOMAIN, SERVICE_REFRESH, handle_refresh,
        schema=vol.Schema({})
    )
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_REFRESH)

    _async_register_add_reading(hass)

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


def _resolve_api(hass: HomeAssistant, entry_id: str | None) -> PgnigApi:
    """Pick the account a service call applies to."""
    apis: dict[str, PgnigApi] = hass.data.get(DOMAIN, {})
    if entry_id is not None:
        api = apis.get(entry_id)
        if api is None:
            raise ServiceValidationError(
                f"No loaded Orlen gas sensor config entry with id {entry_id}"
            )
        return api

    if not apis:
        raise ServiceValidationError("No Orlen gas sensor account is set up")
    if len(apis) > 1:
        raise ServiceValidationError(
            "Several Orlen accounts are configured; pass config_entry_id to "
            "choose which one to submit the reading for"
        )
    return next(iter(apis.values()))


@callback
def _async_register_add_reading(hass: HomeAssistant) -> None:
    """Register the reading submission service once for the whole domain."""
    if hass.services.has_service(DOMAIN, SERVICE_ADD_READING):
        return

    async def handle_add_reading(call: ServiceCall) -> dict[str, object]:
        api = _resolve_api(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
        meter_id = call.data[ATTR_METER_ID]
        value = call.data[ATTR_VALUE]
        reading_date = call.data.get(ATTR_DATE)
        consent_meter_reset = call.data[ATTR_CONSENT_METER_RESET]

        _LOGGER.debug(
            "Submitting reading %s for meter %s (date=%s, consent_meter_reset=%s)",
            value,
            meter_id,
            reading_date,
            consent_meter_reset,
        )
        try:
            result = await hass.async_add_executor_job(
                api.addReading, meter_id, value, reading_date, consent_meter_reset
            )
        except ReadingRejectedError as err:
            raise ServiceValidationError(str(err)) from err
        except (InvalidAuthError, MfaRequired, SessionExpiredError) as err:
            raise HomeAssistantError(
                f"Orlen EBOK login is no longer valid: {err}"
            ) from err
        except Exception as err:
            raise HomeAssistantError(f"Failed to submit reading: {err}") from err

        return {
            "meter_id": result.meter_id or meter_id,
            "value": result.value,
            "added_at_utc": result.added_at_utc,
            "can_be_cancelled": result.can_be_cancelled,
        }

    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_READING,
        handle_add_reading,
        schema=ADD_READING_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_ADD_READING)


async def _async_refresh_orlen_session(hass: HomeAssistant, config_entry) -> None:
    """Refresh OrlenID cookies/token in the background without MFA."""
    api = hass.data[DOMAIN].get(config_entry.entry_id)
    if api is None:
        return

    def _refresh() -> tuple[str, dict | None]:
        token = api.refresh_auth_token()
        return token, api.export_orlen_session()

    try:
        token, session = await hass.async_add_executor_job(_refresh)
    except (MfaRequired, InvalidAuthError, SessionExpiredError) as err:
        _LOGGER.warning(
            "OrlenID session expired and requires re-authentication: %s", err
        )
        hass.async_create_task(hass.config_entries.async_start_reauth(config_entry))
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
    if hass.services.has_service(DOMAIN, SERVICE_REFRESH):
        hass.services.async_remove(DOMAIN, SERVICE_REFRESH)
    hass.data[DOMAIN].pop(config_entry.entry_id, None)
    if not hass.data[DOMAIN] and hass.services.has_service(DOMAIN, SERVICE_ADD_READING):
        hass.services.async_remove(DOMAIN, SERVICE_ADD_READING)
    unload_ok = True
    for platform in ("sensor", "button"):
        if not await hass.config_entries.async_forward_entry_unload(
            config_entry, platform
        ):
            unload_ok = False
    return unload_ok
