"""Tests for PGNIG button entity."""
from unittest.mock import AsyncMock, MagicMock, patch, ANY

import pytest
from homeassistant.core import HomeAssistant

from custom_components.pgnig_gas_sensor.button import (
    PgnigRefreshButton,
    async_setup_entry,
)
from custom_components.pgnig_gas_sensor.const import DOMAIN
from custom_components.pgnig_gas_sensor.PgpList import PpgList, PpgListElement


@pytest.fixture
def mock_api():
    api = MagicMock()
    api.meterList.return_value = PpgList(
        ppg_list=[
            PpgListElement(
                id_ppg="1", meter_number="METER1", contract_number="C1",
                has_t12=True, reading_added=True, tariff="T1",
                has_history=True, type="G", id_local=1,
                client_number=100, installation_number="INST1",
                color="red", agreement_name="Main",
                can_create_home_assistant=True, add_reading_mode="auto",
                is_in_migration=False, is_in_migration_rk=False,
                is_in_migration_rw=False, is_company=False,
            ),
        ],
        code=0, message=None, display_to_end_user=False,
        end_user_message=None,
        token_expire_date="2026-06-01T00:00:00",
        token_expire_date_utc="2026-06-01T00:00:00",
    )
    return api


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


async def test_async_setup_entry_creates_buttons(hass: HomeAssistant, mock_api):
    config_entry = MagicMock()
    config_entry.data = {
        "username": "user",
        "password": "pass",
        "auth_method": "api_login",
    }
    config_entry.entry_id = "test_entry"

    async_add_entities = MagicMock()
    hass.data = {DOMAIN: {"test_entry": mock_api}}

    await async_setup_entry(hass, config_entry, async_add_entities)
    async_add_entities.assert_called_once()
    buttons = async_add_entities.call_args[0][0]
    assert len(buttons) == 1
    assert isinstance(buttons[0], PgnigRefreshButton)
    assert buttons[0].meter_id == "METER1"
