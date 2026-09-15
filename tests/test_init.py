"""Tests for integration setup and the background OrlenID session refresh.

An expired session has to reach the user as a reauth prompt on the integrations
page. Before these tests the trigger called a method that does not exist on
ConfigEntries, so the prompt never appeared and the failure was only ever a
stack trace in the log.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pgnig_gas_sensor import (
    _async_refresh_orlen_session,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.pgnig_gas_sensor.auth.exceptions import (
    InvalidAuthError,
    MfaRequired,
    SessionExpiredError,
)
from custom_components.pgnig_gas_sensor.const import (
    AUTH_METHOD_ORLEN_ID,
    CONF_AUTH_METHOD,
    CONF_ORLEN_SESSION,
    DEFAULT_AUTH_METHOD,
    DOMAIN,
)
from custom_components.pgnig_gas_sensor.runtime import PgnigRuntimeData

from .builders import build_stub_coordinator

AUTH_ERRORS = [
    SessionExpiredError("session expired"),
    InvalidAuthError("bad password"),
    MfaRequired({"mfa_form_fields": {}}),
]


@pytest.fixture(autouse=True)
def auto_enable(enable_custom_integrations):
    yield


def add_entry(
    hass: HomeAssistant,
    auth_method: str = AUTH_METHOD_ORLEN_ID,
    *,
    setting_up: bool = False,
) -> MockConfigEntry:
    """Register a config entry so reauth flows can be started against it."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_USERNAME: "user@example.pl",
            CONF_PASSWORD: "secret",
            CONF_AUTH_METHOD: auth_method,
        },
        entry_id="entry_1",
    )
    entry.add_to_hass(hass)
    if setting_up:
        # async_config_entry_first_refresh is only valid while HA is setting the
        # entry up, which is the state async_setup_entry really runs in.
        entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    return entry


def runtime_for(hass: HomeAssistant, api, meters) -> PgnigRuntimeData:
    """Runtime data with a coordinator that never touches the API."""
    return PgnigRuntimeData(
        api=api, meters=meters, coordinator=build_stub_coordinator(hass)
    )


def reauth_sources(hass: HomeAssistant) -> list[str]:
    return [flow["context"]["source"] for flow in hass.config_entries.flow.async_progress()]


# --- setup -------------------------------------------------------------


@pytest.mark.parametrize("error", AUTH_ERRORS, ids=lambda e: type(e).__name__)
async def test_setup_entry_raises_auth_failed(hass: HomeAssistant, error):
    """Auth errors must become ConfigEntryAuthFailed so HA prompts to reconfigure."""
    entry = add_entry(hass)
    with patch("custom_components.pgnig_gas_sensor.PgnigApi") as mock_api_class:
        mock_api_class.return_value.login.side_effect = error
        with pytest.raises(ConfigEntryAuthFailed):
            await async_setup_entry(hass, entry)


async def test_setup_entry_raises_not_ready_on_transient_error(hass: HomeAssistant):
    """A network blip must be retried, not turned into a reauth prompt."""
    entry = add_entry(hass)
    with patch("custom_components.pgnig_gas_sensor.PgnigApi") as mock_api_class:
        mock_api_class.return_value.login.side_effect = RuntimeError("connection reset")
        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(hass, entry)


async def test_setup_entry_stores_runtime_data(hass: HomeAssistant, mock_api):
    """Platforms read the meter list resolved once during setup."""
    entry = add_entry(hass, auth_method=DEFAULT_AUTH_METHOD, setting_up=True)
    with (
        patch("custom_components.pgnig_gas_sensor.PgnigApi", return_value=mock_api),
        patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()),
    ):
        assert await async_setup_entry(hass, entry) is True

    runtime = hass.data[DOMAIN][entry.entry_id]
    assert runtime.api is mock_api
    assert [meter.meter_number for meter in runtime.meters.ppg_list] == ["METER1"]
    mock_api.meterList.assert_called_once()


@pytest.mark.parametrize(
    ("auth_method", "scheduled"),
    [(AUTH_METHOD_ORLEN_ID, True), (DEFAULT_AUTH_METHOD, False)],
)
async def test_session_refresh_is_scheduled_only_for_orlen_id(
    hass: HomeAssistant, mock_api, auth_method, scheduled
):
    """Only OrlenID keeps a server-side session that needs periodic refreshing."""
    entry = add_entry(hass, auth_method=auth_method, setting_up=True)
    with (
        patch("custom_components.pgnig_gas_sensor.PgnigApi", return_value=mock_api),
        patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()),
        patch(
            "custom_components.pgnig_gas_sensor.async_track_time_interval"
        ) as track_interval,
    ):
        await async_setup_entry(hass, entry)

    assert track_interval.called is scheduled


# --- background session refresh ---------------------------------------


@pytest.mark.parametrize("error", AUTH_ERRORS, ids=lambda e: type(e).__name__)
async def test_background_refresh_starts_reauth_flow(
    hass: HomeAssistant, mock_api, mock_meters, error
):
    """The regression guard: a session with nothing left must raise a reauth flow."""
    entry = add_entry(hass)
    mock_api.refresh_auth_token.side_effect = error
    mock_api.has_token.return_value = False
    hass.data[DOMAIN] = {entry.entry_id: runtime_for(hass, mock_api, mock_meters)}

    await _async_refresh_orlen_session(hass, entry)
    await hass.async_block_till_done()

    assert reauth_sources(hass) == ["reauth"]


@pytest.mark.parametrize("error", AUTH_ERRORS, ids=lambda e: type(e).__name__)
async def test_background_refresh_keeps_quiet_while_a_token_survives(
    hass: HomeAssistant, mock_api, mock_meters, error
):
    """A failed renewal is not proof the token stopped working.

    Issue #131: every refresh tick escalated straight to reauth, and for an
    account with 2FA each escalation is an SMS. The next poll still surfaces a
    token that has genuinely expired, through ConfigEntryAuthFailed.
    """
    entry = add_entry(hass)
    mock_api.refresh_auth_token.side_effect = error
    mock_api.has_token.return_value = True
    hass.data[DOMAIN] = {entry.entry_id: runtime_for(hass, mock_api, mock_meters)}

    await _async_refresh_orlen_session(hass, entry)
    await hass.async_block_till_done()

    assert reauth_sources(hass) == []


async def test_background_refresh_stores_new_session(
    hass: HomeAssistant, mock_api, mock_meters
):
    entry = add_entry(hass)
    mock_api.refresh_auth_token.return_value = "TOKEN"
    mock_api.export_orlen_session.return_value = {"device_id": "abc", "cookies": []}
    hass.data[DOMAIN] = {entry.entry_id: runtime_for(hass, mock_api, mock_meters)}

    await _async_refresh_orlen_session(hass, entry)
    await hass.async_block_till_done()

    assert entry.data[CONF_ORLEN_SESSION] == {"device_id": "abc", "cookies": []}
    assert reauth_sources(hass) == []


async def test_background_refresh_does_not_prompt_on_transient_failure(
    hass: HomeAssistant, mock_api, mock_meters
):
    """A failed refresh that is not an auth problem must not nag the user."""
    entry = add_entry(hass)
    mock_api.refresh_auth_token.side_effect = RuntimeError("connection reset")
    hass.data[DOMAIN] = {entry.entry_id: runtime_for(hass, mock_api, mock_meters)}

    await _async_refresh_orlen_session(hass, entry)
    await hass.async_block_till_done()

    assert reauth_sources(hass) == []


async def test_background_refresh_is_a_noop_without_runtime_data(hass: HomeAssistant):
    entry = add_entry(hass)
    hass.data[DOMAIN] = {}

    await _async_refresh_orlen_session(hass, entry)
    await hass.async_block_till_done()

    assert reauth_sources(hass) == []


async def test_background_refresh_keeps_entry_when_session_is_empty(
    hass: HomeAssistant, mock_api, mock_meters
):
    """Nothing to persist means the stored session must be left untouched."""
    entry = add_entry(hass)
    mock_api.refresh_auth_token.return_value = "TOKEN"
    mock_api.export_orlen_session.return_value = None
    hass.data[DOMAIN] = {entry.entry_id: runtime_for(hass, mock_api, mock_meters)}

    await _async_refresh_orlen_session(hass, entry)
    await hass.async_block_till_done()

    assert CONF_ORLEN_SESSION not in entry.data
    assert reauth_sources(hass) == []


# --- unload -----------------------------------------------------------


@pytest.mark.parametrize(("platforms_unloaded", "expected"), [(True, True), (False, False)])
async def test_unload_entry_reports_platform_result(
    hass: HomeAssistant, mock_api, mock_meters, platforms_unloaded, expected
):
    entry = add_entry(hass, auth_method=DEFAULT_AUTH_METHOD)
    hass.data[DOMAIN] = {entry.entry_id: runtime_for(hass, mock_api, mock_meters)}

    with patch.object(
        hass.config_entries,
        "async_forward_entry_unload",
        AsyncMock(return_value=platforms_unloaded),
    ):
        assert await async_unload_entry(hass, entry) is expected

    assert entry.entry_id not in hass.data[DOMAIN]


# --- refresh service --------------------------------------------------


async def setup_loaded_entry(hass: HomeAssistant, mock_api) -> MockConfigEntry:
    """Run async_setup_entry with platform forwarding stubbed out."""
    entry = add_entry(hass, auth_method=DEFAULT_AUTH_METHOD, setting_up=True)
    with (
        patch("custom_components.pgnig_gas_sensor.PgnigApi", return_value=mock_api),
        patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()),
    ):
        await async_setup_entry(hass, entry)
    return entry


async def test_refresh_service_polls_the_api_again(hass: HomeAssistant, mock_api):
    """The button and the service must actually re-fetch, not just nudge entities."""
    entry = await setup_loaded_entry(hass, mock_api)
    mock_api.readingForMeter.reset_mock()
    mock_api.invoices.reset_mock()

    await hass.services.async_call(DOMAIN, "refresh", {}, blocking=True)
    await hass.async_block_till_done()

    assert mock_api.readingForMeter.called
    assert mock_api.invoices.called
    assert hass.data[DOMAIN][entry.entry_id].coordinator.last_update_success is True


async def test_refresh_service_is_removed_on_unload(hass: HomeAssistant, mock_api):
    entry = await setup_loaded_entry(hass, mock_api)
    assert hass.services.has_service(DOMAIN, "refresh")

    with patch.object(
        hass.config_entries, "async_forward_entry_unload", AsyncMock(return_value=True)
    ):
        await async_unload_entry(hass, entry)

    assert not hass.services.has_service(DOMAIN, "refresh")


# --- end to end -------------------------------------------------------


async def test_entities_are_created_when_home_assistant_loads_the_entry(
    hass: HomeAssistant, mock_api
):
    """Full wiring: setup -> first poll -> platforms -> entities with state."""
    entry = add_entry(hass, auth_method=DEFAULT_AUTH_METHOD)

    with patch("custom_components.pgnig_gas_sensor.PgnigApi", return_value=mock_api):
        assert await hass.config_entries.async_setup(entry.entry_id) is True
        await hass.async_block_till_done()

    sensors = hass.states.async_entity_ids("sensor")
    assert len(sensors) == 3, sensors
    assert len(hass.states.async_entity_ids("button")) == 1

    # the meter reading came from the coordinator's first poll, not an entity call
    meter_state = hass.states.get(
        next(s for s in sensors if "cost" not in s and "invoice" not in s)
    )
    assert meter_state.state == "100"

    assert await hass.config_entries.async_unload(entry.entry_id) is True
    await hass.async_block_till_done()
