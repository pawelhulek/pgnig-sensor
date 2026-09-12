"""Tests for the shared data coordinator.

Entities used to poll the API independently inside async_update. Home Assistant
catches whatever an entity update raises, so an expired session never reached
the user. The coordinator raises ConfigEntryAuthFailed instead, which HA turns
into a reauth prompt.
"""
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pgnig_gas_sensor.auth.exceptions import (
    InvalidAuthError,
    MfaRequired,
    SessionExpiredError,
)
from custom_components.pgnig_gas_sensor.const import DOMAIN
from custom_components.pgnig_gas_sensor.coordinator import (
    PgnigCoordinator,
    latest_reading,
)

from .builders import (
    build_meter_list,
    make_invoice,
    make_invoices_response,
    make_reading,
    make_readings_response,
)

AUTH_ERRORS = [
    SessionExpiredError("session expired"),
    InvalidAuthError("bad password"),
    MfaRequired({"mfa_form_fields": {}}),
]


@pytest.fixture(autouse=True)
def auto_enable(enable_custom_integrations):
    yield


def api_returning(readings=(), invoices=()) -> MagicMock:
    api = MagicMock()
    api.readingForMeter.return_value = make_readings_response(readings)
    api.invoices.return_value = make_invoices_response(invoices)
    return api


def build_coordinator(hass, api, *meter_numbers) -> PgnigCoordinator:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: "user@example.pl", CONF_PASSWORD: "secret"},
        entry_id="entry_1",
    )
    entry.add_to_hass(hass)
    return PgnigCoordinator(
        hass, entry, api, build_meter_list(*(meter_numbers or ("METER1",)))
    )


# --- latest_reading ----------------------------------------------------


def test_latest_reading_prefers_the_newest():
    older = make_reading(reading_date_utc=datetime(2022, 7, 4), value=3)
    newer = make_reading(reading_date_utc=datetime(2022, 7, 5), value=2)

    assert latest_reading([older, newer]).value == 2


@pytest.mark.parametrize("readings", [[], None])
def test_latest_reading_without_readings(readings):
    assert latest_reading(readings) is None


# --- polling -----------------------------------------------------------


async def test_readings_are_keyed_by_meter_number(hass: HomeAssistant):
    api = api_returning(readings=[make_reading(value=42)])
    coordinator = build_coordinator(hass, api, "METER1", "METER2")

    data = await coordinator._async_update_data()

    assert set(data.readings) == {"METER1", "METER2"}
    assert data.readings["METER1"].value == 42


async def test_invoices_are_fetched_once_for_all_meters(hass: HomeAssistant):
    """Each meter used to trigger two invoice fetches of its own."""
    api = api_returning(invoices=[make_invoice()])
    coordinator = build_coordinator(hass, api, "METER1", "METER2", "METER3")

    data = await coordinator._async_update_data()

    assert api.invoices.call_count == 1
    assert api.readingForMeter.call_count == 3
    assert len(data.invoices) == 1


# --- failures ----------------------------------------------------------


@pytest.mark.parametrize("error", AUTH_ERRORS, ids=lambda e: type(e).__name__)
async def test_auth_error_becomes_config_entry_auth_failed(hass: HomeAssistant, error):
    api = api_returning()
    api.readingForMeter.side_effect = error
    coordinator = build_coordinator(hass, api)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_transient_error_becomes_update_failed(hass: HomeAssistant):
    """A network blip must not be reported as an authentication problem."""
    api = api_returning()
    api.invoices.side_effect = RuntimeError("connection reset")
    coordinator = build_coordinator(hass, api)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_auth_failure_during_refresh_starts_reauth_flow(hass: HomeAssistant):
    """The gap this coordinator exists to close: sensors now prompt the user."""
    api = api_returning()
    api.readingForMeter.side_effect = SessionExpiredError("session expired")
    coordinator = build_coordinator(hass, api)

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.last_update_success is False
    assert [
        flow["context"]["source"] for flow in hass.config_entries.flow.async_progress()
    ] == ["reauth"]


async def test_transient_failure_during_refresh_does_not_prompt(hass: HomeAssistant):
    api = api_returning()
    api.invoices.side_effect = RuntimeError("connection reset")
    coordinator = build_coordinator(hass, api)

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.last_update_success is False
    assert hass.config_entries.flow.async_progress() == []
