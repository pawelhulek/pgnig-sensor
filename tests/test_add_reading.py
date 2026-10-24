"""Tests for submitting meter readings to Orlen EBOK (issue #50)."""
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pgnig_gas_sensor import _async_register_add_reading
from custom_components.pgnig_gas_sensor.AddReading import (
    ReadingResult,
    ReadingSubmission,
    error_message,
)
from custom_components.pgnig_gas_sensor.auth.exceptions import SessionExpiredError
from custom_components.pgnig_gas_sensor.const import DOMAIN, SERVICE_ADD_READING
from custom_components.pgnig_gas_sensor.exceptions import ReadingRejectedError
from custom_components.pgnig_gas_sensor.PgnigApi import PgnigApi
from custom_components.pgnig_gas_sensor.runtime import PgnigRuntimeData

from .builders import build_stub_coordinator

ACCEPTED_RESPONSE = {
    "Code": 0,
    "Reading": {
        "MeterNumber": "METER1",
        "Value": 1234,
        "ReadingDateAddedUtc": "2026-08-08T10:00:00",
        "CanBeCancelled": True,
    },
}


@pytest.fixture
def mock_auth():
    auth = MagicMock()
    auth.login.return_value = "test-token"
    auth.session = MagicMock()
    auth.session.post.return_value.ok = True
    auth.session.post.return_value.status_code = 200
    auth.session.post.return_value.json.return_value = ACCEPTED_RESPONSE
    return auth


@pytest.fixture
def api(mock_auth):
    with patch(
        "custom_components.pgnig_gas_sensor.PgnigApi.AuthRegistry.get",
        return_value=MagicMock(return_value=mock_auth),
    ):
        return PgnigApi("user", "pass", "api_login")


# --- payload and result ------------------------------------------------


def test_submission_payload_matches_ebok_contract():
    payload = ReadingSubmission(
        meter_id="METER1", value=1234.0, reading_date=date(2026, 8, 8)
    ).to_payload()
    assert payload == {
        "DateReading": "2026-08-08",
        "OsdNumber": "METER1",
        "Value": 1234.0,
        "ConsentMeterReset": False,
        "UseDate": True,
        "SourceFromWWW": True,
    }


def test_reading_result_from_response():
    result = ReadingResult.from_dict(ACCEPTED_RESPONSE)
    assert result.meter_id == "METER1"
    assert result.value == 1234
    assert result.can_be_cancelled is True


def test_error_message_falls_back_to_code():
    assert "code 999" in error_message(999)


# --- API ---------------------------------------------------------------


def test_add_reading_posts_and_returns_result(api, mock_auth):
    result = api.addReading("METER1", 1234, date(2026, 8, 8))

    mock_auth.session.post.assert_called_once()
    args, kwargs = mock_auth.session.post.call_args
    assert args[0].endswith("/crm/add-ppg-reading-v2?api-version=3.0")
    assert kwargs["json"]["OsdNumber"] == "METER1"
    assert kwargs["json"]["Value"] == 1234
    assert kwargs["headers"]["AuthToken"] == "test-token"
    assert result.value == 1234


def test_add_reading_defaults_to_today(api, mock_auth):
    api.addReading("METER1", 1234)
    assert mock_auth.session.post.call_args[1]["json"]["DateReading"] == (
        date.today().isoformat()
    )


def test_add_reading_passes_meter_reset_consent(api, mock_auth):
    api.addReading("METER1", 5, date(2026, 8, 8), consent_meter_reset=True)
    assert mock_auth.session.post.call_args[1]["json"]["ConsentMeterReset"] is True


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (1032, "already been submitted"),
        (1031, "invalid"),
        (1040, "consent_meter_reset"),
        (4711, "code 4711"),
    ],
)
def test_add_reading_raises_with_explained_code(api, mock_auth, code, expected):
    mock_auth.session.post.return_value.json.return_value = {"Code": code}
    with pytest.raises(ReadingRejectedError) as err:
        api.addReading("METER1", 1234)
    assert err.value.code == code
    assert expected in str(err.value)


def test_add_reading_retries_once_after_401(api, mock_auth):
    """POST shares the GET path's token refresh, so a stale token is retried."""
    unauthorized = MagicMock(status_code=401, ok=False, text="")
    accepted = MagicMock(status_code=200, ok=True)
    accepted.json.return_value = ACCEPTED_RESPONSE
    mock_auth.session.post.side_effect = [unauthorized, accepted]

    assert api.addReading("METER1", 1234).value == 1234
    assert mock_auth.session.post.call_count == 2
    mock_auth.invalidate_token.assert_called_once()


# --- service -----------------------------------------------------------


def _register(hass: HomeAssistant, *apis) -> None:
    """Put runtime data in place for each account and register the service."""
    hass.data[DOMAIN] = {
        f"entry_{index}": PgnigRuntimeData(
            api=api,
            meters=MagicMock(),
            coordinator=build_stub_coordinator(hass),
        )
        for index, api in enumerate(apis, start=1)
    }
    _async_register_add_reading(hass)


async def test_service_submits_reading(hass: HomeAssistant):
    api = MagicMock()
    api.addReading.return_value = ReadingResult.from_dict(ACCEPTED_RESPONSE)
    _register(hass, api)

    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_ADD_READING,
        {"meter_id": "METER1", "value": 1234, "date": "2026-08-08"},
        blocking=True,
        return_response=True,
    )

    api.addReading.assert_called_once_with("METER1", 1234.0, date(2026, 8, 8), False)
    assert response["value"] == 1234
    assert response["can_be_cancelled"] is True


async def test_service_rejects_negative_value(hass: HomeAssistant):
    _register(hass, MagicMock())
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_ADD_READING,
            {"meter_id": "METER1", "value": -5},
            blocking=True,
        )


async def test_service_surfaces_rejection_as_validation_error(hass: HomeAssistant):
    api = MagicMock()
    api.addReading.side_effect = ReadingRejectedError(1032, "already submitted")
    _register(hass, api)

    with pytest.raises(ServiceValidationError, match="already submitted"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_ADD_READING,
            {"meter_id": "METER1", "value": 1234},
            blocking=True,
        )


async def test_service_surfaces_expired_login(hass: HomeAssistant):
    api = MagicMock()
    api.addReading.side_effect = SessionExpiredError("session expired")
    _register(hass, api)

    with pytest.raises(HomeAssistantError, match="no longer valid"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_ADD_READING,
            {"meter_id": "METER1", "value": 1234},
            blocking=True,
        )


async def test_service_surfaces_transport_failure(hass: HomeAssistant):
    api = MagicMock()
    api.addReading.side_effect = RuntimeError("Add reading failed with status 500: ")
    _register(hass, api)

    with pytest.raises(HomeAssistantError, match="status 500"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_ADD_READING,
            {"meter_id": "METER1", "value": 1234},
            blocking=True,
        )


async def test_service_requires_entry_id_with_multiple_accounts(hass: HomeAssistant):
    _register(hass, MagicMock(), MagicMock())

    with pytest.raises(ServiceValidationError, match="config_entry_id"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_ADD_READING,
            {"meter_id": "METER1", "value": 1234},
            blocking=True,
        )


async def test_service_uses_the_named_account(hass: HomeAssistant):
    first, second = MagicMock(), MagicMock()
    second.addReading.return_value = ReadingResult.from_dict(ACCEPTED_RESPONSE)
    _register(hass, first, second)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_ADD_READING,
        {"meter_id": "METER1", "value": 1234, "config_entry_id": "entry_2"},
        blocking=True,
    )

    second.addReading.assert_called_once()
    first.addReading.assert_not_called()


async def test_service_rejects_an_unknown_account(hass: HomeAssistant):
    _register(hass, MagicMock())

    with pytest.raises(ServiceValidationError, match="No loaded"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_ADD_READING,
            {"meter_id": "METER1", "value": 1234, "config_entry_id": "nope"},
            blocking=True,
        )


# --- picking the meter instead of typing its number --------------------


def _register_entry(hass: HomeAssistant, entry, api) -> None:
    """Expose one account keyed by a real config entry id."""
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = PgnigRuntimeData(
        api=api, meters=MagicMock(), coordinator=build_stub_coordinator(hass)
    )
    _async_register_add_reading(hass)


def _add_meter_device(hass: HomeAssistant, entry, meter_id: str):
    return dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, meter_id)},
        name=f"Orlen GAS METER ID {meter_id}",
    )


async def test_service_accepts_a_picked_device(hass: HomeAssistant):
    """Nobody should have to retype a 20-plus digit meter number."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    api = MagicMock()
    api.addReading.return_value = ReadingResult.from_dict(ACCEPTED_RESPONSE)
    _register_entry(hass, entry, api)
    device = _add_meter_device(hass, entry, "8018590365500081588393")

    await hass.services.async_call(
        DOMAIN,
        SERVICE_ADD_READING,
        {"device_id": device.id, "value": 1234},
        blocking=True,
    )

    assert api.addReading.call_args[0][0] == "8018590365500081588393"


async def test_picked_device_also_names_its_account(hass: HomeAssistant):
    """A device belongs to one entry, so config_entry_id is not needed too."""
    first_entry = MockConfigEntry(domain=DOMAIN, data={}, entry_id="acc_1")
    first_entry.add_to_hass(hass)
    second_entry = MockConfigEntry(domain=DOMAIN, data={}, entry_id="acc_2")
    second_entry.add_to_hass(hass)

    first_api, second_api = MagicMock(), MagicMock()
    second_api.addReading.return_value = ReadingResult.from_dict(ACCEPTED_RESPONSE)
    _register_entry(hass, first_entry, first_api)
    _register_entry(hass, second_entry, second_api)
    device = _add_meter_device(hass, second_entry, "METER2")

    await hass.services.async_call(
        DOMAIN,
        SERVICE_ADD_READING,
        {"device_id": device.id, "value": 7},
        blocking=True,
    )

    second_api.addReading.assert_called_once()
    first_api.addReading.assert_not_called()


async def test_service_rejects_an_unknown_device(hass: HomeAssistant):
    _register(hass, MagicMock())
    with pytest.raises(ServiceValidationError, match="No device with id"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_ADD_READING,
            {"device_id": "does-not-exist", "value": 1234},
            blocking=True,
        )


async def test_service_rejects_a_device_from_another_integration(hass: HomeAssistant):
    entry = MockConfigEntry(domain="other_integration", data={})
    entry.add_to_hass(hass)
    foreign = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("other_integration", "thing")},
        name="Something else",
    )
    _register(hass, MagicMock())

    with pytest.raises(ServiceValidationError, match="not an Orlen gas meter"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_ADD_READING,
            {"device_id": foreign.id, "value": 1234},
            blocking=True,
        )


async def test_service_needs_a_device_or_a_meter_number(hass: HomeAssistant):
    _register(hass, MagicMock())
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN, SERVICE_ADD_READING, {"value": 1234}, blocking=True
        )


async def test_meter_number_still_works_without_a_device(hass: HomeAssistant):
    """Back-compat: automations written against #107 keep working."""
    api = MagicMock()
    api.addReading.return_value = ReadingResult.from_dict(ACCEPTED_RESPONSE)
    _register(hass, api)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_ADD_READING,
        {"meter_id": "METER1", "value": 1234},
        blocking=True,
    )

    assert api.addReading.call_args[0][0] == "METER1"
