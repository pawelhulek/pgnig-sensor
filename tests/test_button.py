"""Tests for PGNIG button entity."""
from unittest.mock import AsyncMock, MagicMock

from homeassistant.core import HomeAssistant

from custom_components.pgnig_gas_sensor.button import (
    PgnigRefreshButton,
    async_setup_entry,
)
from custom_components.pgnig_gas_sensor.const import DOMAIN
from custom_components.pgnig_gas_sensor.runtime import PgnigRuntimeData

from .builders import build_stub_coordinator


def test_button_entity_attributes():
    button = PgnigRefreshButton(
        MagicMock(), "METER1", 1, "entry_123"
    )
    assert button.unique_id == "pgnig_refresh_METER1_1"
    assert button._attr_has_entity_name is True
    assert button._attr_translation_key == "refresh_data"
    assert button.device_info is not None
    assert button.device_info["identifiers"] == {(DOMAIN, "METER1")}


async def test_button_press_calls_refresh_service():
    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    button = PgnigRefreshButton(hass, "METER1", 1, "entry_123")
    await button.async_press()
    hass.services.async_call.assert_awaited_once_with(
        DOMAIN, "refresh", {},
        blocking=True
    )


async def test_async_setup_entry_creates_buttons(
    hass: HomeAssistant, mock_api, mock_meters
):
    config_entry = MagicMock()
    config_entry.data = {
        "username": "user",
        "password": "pass",
        "auth_method": "api_login",
    }
    config_entry.entry_id = "test_entry"

    async_add_entities = MagicMock()
    hass.data = {
        DOMAIN: {
            "test_entry": PgnigRuntimeData(
                api=mock_api,
                meters=mock_meters,
                coordinator=build_stub_coordinator(hass),
            ),
        }
    }

    await async_setup_entry(hass, config_entry, async_add_entities)
    async_add_entities.assert_called_once()
    buttons = async_add_entities.call_args[0][0]
    assert len(buttons) == 1
    assert isinstance(buttons[0], PgnigRefreshButton)
    assert buttons[0].meter_id == "METER1"


async def test_async_setup_entry_does_not_refetch_meters(
    hass: HomeAssistant, mock_api, mock_meters
):
    """The meter list is resolved once in async_setup_entry, not per platform."""
    config_entry = MagicMock()
    config_entry.entry_id = "test_entry"
    hass.data = {
        DOMAIN: {
            "test_entry": PgnigRuntimeData(
                api=mock_api,
                meters=mock_meters,
                coordinator=build_stub_coordinator(hass),
            ),
        }
    }

    await async_setup_entry(hass, config_entry, MagicMock())

    mock_api.meterList.assert_not_called()
