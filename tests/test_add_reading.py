"""Tests for submitting meter readings to Orlen EBOK (issue #50)."""
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

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
