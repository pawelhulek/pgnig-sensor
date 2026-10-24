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
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_interval

from .auth.exceptions import AuthError
from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_CONFIRM_LARGE_INCREASE,
    ATTR_CONSENT_METER_RESET,
    ATTR_DATE,
    ATTR_DEVICE_ID,
    ATTR_METER_ID,
    ATTR_VALUE,
    AUTH_METHOD_ORLEN_ID,
    CONF_AUTH_METHOD,
    CONF_ORLEN_SESSION,
    CONF_MFA_ENABLED,
    DEFAULT_AUTH_METHOD,
    DOMAIN,
    MAX_READING_INCREASE_M3,
    ORLEN_SESSION_REFRESH_MINUTES,
    SERVICE_ADD_READING,
    SERVICE_REFRESH,
)
from .coordinator import PgnigCoordinator
from .exceptions import ReadingRejectedError
from .PgnigApi import PgnigApi
from .PgpList import PpgList
from .runtime import PgnigRuntimeData

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
})

ADD_READING_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Optional(ATTR_DEVICE_ID): cv.string,
            vol.Optional(ATTR_METER_ID): cv.string,
            vol.Required(ATTR_VALUE): vol.All(vol.Coerce(float), vol.Range(min=0)),
            vol.Optional(ATTR_DATE): cv.date,
            vol.Optional(ATTR_CONSENT_METER_RESET, default=False): cv.boolean,
            vol.Optional(ATTR_CONFIRM_LARGE_INCREASE, default=False): cv.boolean,
            vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        }
    ),
    # Either pick the meter in the UI or name its number; meter_id stays
    # accepted on its own so existing automations keep working.
    cv.has_at_least_one_key(ATTR_DEVICE_ID, ATTR_METER_ID),
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
    mfa_enabled = config_entry.data.get(CONF_MFA_ENABLED, True)
    session_data = config_entry.data.get(CONF_ORLEN_SESSION)
    api = PgnigApi(user, password, auth_method, session_data=session_data, mfa_enabled=mfa_enabled)
    hass.data[DOMAIN][config_entry.entry_id] = await _async_build_runtime_data(
        hass, config_entry, api
    )

    await hass.config_entries.async_forward_entry_setups(config_entry, ["sensor", "button"])

    async def handle_refresh(call):
        """Poll now instead of waiting for the next scheduled update.

        The coordinator pushes the result to every entity, so there is no need
        to walk the entity registry and update each one in turn.
        """
        _LOGGER.debug("Refresh service called for config entry %s", config_entry.entry_id)
        runtime = hass.data[DOMAIN].get(config_entry.entry_id)
        if runtime is None:
            return
        await runtime.coordinator.async_refresh()
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


async def _async_build_runtime_data(
    hass: HomeAssistant, config_entry, api: PgnigApi
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
        meters = await hass.async_add_executor_job(_load)
    except AuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except Exception as err:
        raise ConfigEntryNotReady(f"Could not reach Orlen EBOK: {err}") from err

    coordinator = PgnigCoordinator(hass, config_entry, api, meters)
    await coordinator.async_config_entry_first_refresh()
    return PgnigRuntimeData(api=api, meters=meters, coordinator=coordinator)


def _resolve_meter(hass: HomeAssistant, call: ServiceCall) -> tuple[str, str | None]:
    """Resolve the picked device to a meter number and the account it belongs to.

    Picking the meter in the UI is the normal path - nobody should have to
    remember a 20-plus digit meter number. A device also names its own config
    entry, so a multi-account setup does not need config_entry_id as well.
    """
    entry_id = call.data.get(ATTR_CONFIG_ENTRY_ID)
    device_id = call.data.get(ATTR_DEVICE_ID)
    if not device_id:
        return call.data[ATTR_METER_ID], entry_id

    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        raise ServiceValidationError(f"No device with id {device_id}")

    meter_id = next(
        (identifier[1] for identifier in device.identifiers if identifier[0] == DOMAIN),
        None,
    )
    if meter_id is None:
        raise ServiceValidationError(
            f"{device.name or device_id} is not an Orlen gas meter"
        )

    if entry_id is None and device.config_entries:
        entry_id = next(iter(device.config_entries))
    return meter_id, entry_id


def _resolve_runtime(hass: HomeAssistant, entry_id: str | None) -> PgnigRuntimeData:
    """Pick the account a service call applies to."""
    runtimes: dict[str, PgnigRuntimeData] = hass.data.get(DOMAIN, {})
    if entry_id is not None:
        runtime = runtimes.get(entry_id)
        if runtime is None:
            raise ServiceValidationError(
                f"No loaded Orlen gas sensor config entry with id {entry_id}"
            )
        return runtime

    if not runtimes:
        raise ServiceValidationError("No Orlen gas sensor account is set up")
    if len(runtimes) > 1:
        raise ServiceValidationError(
            "Several Orlen accounts are configured; pass config_entry_id to "
            "choose which one to submit the reading for"
        )
    return next(iter(runtimes.values()))


def _last_known_reading(runtime: PgnigRuntimeData, meter_id: str) -> float | None:
    """The reading the sensor is currently showing, if there is one."""
    data = runtime.coordinator.data
    reading = data.readings.get(meter_id) if data is not None else None
    if reading is None or reading.value is None:
        return None
    try:
        return float(reading.value)
    except (TypeError, ValueError):
        return None


def _check_reading_is_plausible(
    runtime: PgnigRuntimeData,
    meter_id: str,
    value: float,
    *,
    consent_meter_reset: bool,
    confirm_large_increase: bool,
) -> None:
    """Refuse a reading that cannot be right before it becomes an invoice.

    Orlen bills from the value submitted and accepts it without much argument,
    so the checks that matter happen here. Both are measured against the last
    reading Home Assistant knows about - the number shown on the sensor - and
    both are skipped when there is nothing to compare against.
    """
    last = _last_known_reading(runtime, meter_id)
    if last is None:
        _LOGGER.debug(
            "No previous reading known for meter %s; submitting %s unchecked",
            meter_id,
            value,
        )
        return

    if value < last:
        if consent_meter_reset:
            return
        raise ServiceValidationError(
            f"{value:g} m3 is lower than the last reading for meter {meter_id} "
            f"({last:g} m3). A meter total only climbs, so this looks like a "
            "mistake and Orlen would bill from it. If the meter really was "
            "replaced or has rolled over, repeat the call with "
            "consent_meter_reset: true."
        )

    increase = value - last
    if increase > MAX_READING_INCREASE_M3 and not confirm_large_increase:
        raise ServiceValidationError(
            f"{value:g} m3 is {increase:g} m3 above the last reading "
            f"({last:g} m3), more than the {MAX_READING_INCREASE_M3} m3 this "
            "integration submits unchecked - a mistyped reading becomes a real "
            "invoice. If the value is correct, repeat the call with "
            "confirm_large_increase: true."
        )


@callback
def _async_register_add_reading(hass: HomeAssistant) -> None:
    """Register the reading submission service once for the whole domain."""
    if hass.services.has_service(DOMAIN, SERVICE_ADD_READING):
        return

    async def handle_add_reading(call: ServiceCall) -> dict[str, object]:
        meter_id, entry_id = _resolve_meter(hass, call)
        runtime = _resolve_runtime(hass, entry_id)
        api = runtime.api
        value = call.data[ATTR_VALUE]
        reading_date = call.data.get(ATTR_DATE)
        consent_meter_reset = call.data[ATTR_CONSENT_METER_RESET]

        _check_reading_is_plausible(
            runtime,
            meter_id,
            value,
            consent_meter_reset=consent_meter_reset,
            confirm_large_increase=call.data[ATTR_CONFIRM_LARGE_INCREASE],
        )

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
        except AuthError as err:
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
    """Refresh OrlenID cookies/token in the background without MFA.

    Runs often enough that Orlen never sees the session go idle. Escalating to
    a reauth flow is reserved for the case where no usable token is left,
    because for an account with 2FA that escalation costs the user an SMS.
    """
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
        if api.has_token():
            # The renewal failed but the token it was renewing survived, so
            # there is nothing to ask the user for yet. A token that really has
            # stopped working surfaces as a 401 on the next poll, and the
            # coordinator turns that into ConfigEntryAuthFailed.
            _LOGGER.warning(
                "OrlenID session refresh failed; keeping the token already held "
                "and retrying on the next interval: %s",
                err,
            )
            return
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
