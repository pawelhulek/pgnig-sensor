"""Tests for submitting meter readings to Orlen EBOK (issue #50)."""
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pgnig_gas_sensor.AddReading import (
    ReadingResult,
    ReadingSubmission,
    error_message,
)
from custom_components.pgnig_gas_sensor.const import DOMAIN, SERVICE_ADD_READING
from custom_components.pgnig_gas_sensor.exceptions import ReadingRejectedError
from custom_components.pgnig_gas_sensor.PgnigApi import PgnigApi

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
    "code,expected",
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
    unauthorized = MagicMock(status_code=401, ok=False, text="")
    accepted = MagicMock(status_code=200, ok=True)
    accepted.json.return_value = ACCEPTED_RESPONSE
    mock_auth.session.post.side_effect = [unauthorized, accepted]

    assert api.addReading("METER1", 1234).value == 1234
    assert mock_auth.session.post.call_count == 2
    mock_auth.invalidate_token.assert_called_once()


def test_error_message_falls_back_to_code():
    assert "code 999" in error_message(999)


async def _setup_entry(hass, api):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "u", "password": "p", "auth_method": "api_login"},
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.pgnig_gas_sensor.PgnigApi", return_value=api
    ), patch(
        "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
        return_value=True,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_service_submits_reading(hass, enable_custom_integrations):
    api = MagicMock()
    api.addReading.return_value = ReadingResult.from_dict(ACCEPTED_RESPONSE)
    await _setup_entry(hass, api)

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


async def test_service_rejects_negative_value(hass, enable_custom_integrations):
    await _setup_entry(hass, MagicMock())
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_ADD_READING,
            {"meter_id": "METER1", "value": -5},
            blocking=True,
        )


async def test_service_surfaces_rejection_as_validation_error(
    hass, enable_custom_integrations
):
    api = MagicMock()
    api.addReading.side_effect = ReadingRejectedError(1032, "already submitted")
    await _setup_entry(hass, api)

    with pytest.raises(ServiceValidationError, match="already submitted"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_ADD_READING,
            {"meter_id": "METER1", "value": 1234},
            blocking=True,
        )


async def test_service_surfaces_transport_failure(hass, enable_custom_integrations):
    api = MagicMock()
    api.addReading.side_effect = RuntimeError("Add reading failed with status 500: ")
    await _setup_entry(hass, api)

    with pytest.raises(HomeAssistantError, match="status 500"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_ADD_READING,
            {"meter_id": "METER1", "value": 1234},
            blocking=True,
        )


async def test_service_requires_entry_id_with_multiple_accounts(
    hass, enable_custom_integrations
):
    api = MagicMock()
    await _setup_entry(hass, api)
    await _setup_entry(hass, MagicMock())

    with pytest.raises(ServiceValidationError, match="config_entry_id"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_ADD_READING,
            {"meter_id": "METER1", "value": 1234},
            blocking=True,
        )
