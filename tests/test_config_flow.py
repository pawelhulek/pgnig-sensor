"""Tests for PGNIG config flow with mocked API."""
from unittest.mock import patch, MagicMock
import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pgnig_gas_sensor.const import (
    DOMAIN,
    CONF_AUTH_METHOD,
    DEFAULT_AUTH_METHOD,
)
from custom_components.pgnig_gas_sensor.config_flow import PGNIGGasConfigFlow


@pytest.fixture(autouse=True)
def auto_enable(enable_custom_integrations):
    yield


async def test_form_start(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"
    assert CONF_USERNAME in result["data_schema"].schema
    assert CONF_PASSWORD in result["data_schema"].schema


async def test_form_creates_entry_on_success(hass: HomeAssistant):
    with patch(
        "custom_components.pgnig_gas_sensor.config_flow.PgnigApi"
    ) as MockApi:
        mock_api = MagicMock()
        MockApi.return_value = mock_api

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_AUTH_METHOD: DEFAULT_AUTH_METHOD,
                CONF_USERNAME: "test@user.pl",
                CONF_PASSWORD: "testpass",
            },
        )
        assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
        assert result["title"] == "Pgnig sensor"
        assert result["data"][CONF_USERNAME] == "test@user.pl"
        assert result["data"][CONF_PASSWORD] == "testpass"
        assert result["data"][CONF_AUTH_METHOD] == DEFAULT_AUTH_METHOD
        mock_api.login.assert_called_once()


async def test_form_shows_error_on_failure(hass: HomeAssistant):
    with patch(
        "custom_components.pgnig_gas_sensor.config_flow.PgnigApi"
    ) as MockApi:
        mock_api = MagicMock()
        mock_api.login.side_effect = RuntimeError("Login failed")
        MockApi.return_value = mock_api

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_AUTH_METHOD: DEFAULT_AUTH_METHOD,
                CONF_USERNAME: "test@user.pl",
                CONF_PASSWORD: "badpass",
            },
        )
        assert result["type"] == data_entry_flow.FlowResultType.FORM
        assert result["errors"]["base"] == "verify_connection_failed"


async def test_reauth_updates_entry(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_USERNAME: "old@user.pl",
            CONF_PASSWORD: "oldpass",
            CONF_AUTH_METHOD: DEFAULT_AUTH_METHOD,
        },
        entry_id="test_entry_id",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.pgnig_gas_sensor.config_flow.PgnigApi"
    ) as MockApi:
        mock_api = MagicMock()
        MockApi.return_value = mock_api

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "entry_id": entry.entry_id,
            },
        )
        assert result["type"] == data_entry_flow.FlowResultType.FORM
        assert result["step_id"] == "reauth"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_USERNAME: "new@user.pl",
                CONF_PASSWORD: "newpass",
            },
        )
        assert result["type"] == data_entry_flow.FlowResultType.ABORT
        assert result["reason"] == "reauth_successful"
        assert entry.data[CONF_USERNAME] == "new@user.pl"
        assert entry.data[CONF_PASSWORD] == "newpass"


async def test_reauth_shows_error_on_failure(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_USERNAME: "old@user.pl",
            CONF_PASSWORD: "oldpass",
            CONF_AUTH_METHOD: DEFAULT_AUTH_METHOD,
        },
        entry_id="reauth_fail_id",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.pgnig_gas_sensor.config_flow.PgnigApi"
    ) as MockApi:
        mock_api = MagicMock()
        mock_api.login.side_effect = RuntimeError("Still wrong")
        MockApi.return_value = mock_api

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "entry_id": entry.entry_id,
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_USERNAME: "new@user.pl",
                CONF_PASSWORD: "wrongpass",
            },
        )
        assert result["type"] == data_entry_flow.FlowResultType.FORM
        assert result["errors"]["base"] == "verify_connection_failed"


async def test_reconfigure_updates_entry(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_USERNAME: "old@user.pl",
            CONF_PASSWORD: "oldpass",
            CONF_AUTH_METHOD: DEFAULT_AUTH_METHOD,
        },
        entry_id="reconfigure_test_id",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.pgnig_gas_sensor.config_flow.PgnigApi"
    ) as MockApi:
        mock_api = MagicMock()
        MockApi.return_value = mock_api

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_RECONFIGURE,
                "entry_id": entry.entry_id,
            },
        )
        assert result["type"] == data_entry_flow.FlowResultType.FORM
        assert result["step_id"] == "reconfigure"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_AUTH_METHOD: DEFAULT_AUTH_METHOD,
                CONF_USERNAME: "updated@user.pl",
                CONF_PASSWORD: "updatedpass",
            },
        )
        assert result["type"] == data_entry_flow.FlowResultType.ABORT
        assert result["reason"] == "reconfigure_successful"
        assert entry.data[CONF_USERNAME] == "updated@user.pl"
        assert entry.data[CONF_PASSWORD] == "updatedpass"


async def test_reconfigure_shows_error_on_failure(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_USERNAME: "old@user.pl",
            CONF_PASSWORD: "oldpass",
            CONF_AUTH_METHOD: DEFAULT_AUTH_METHOD,
        },
        entry_id="reconfigure_fail_id",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.pgnig_gas_sensor.config_flow.PgnigApi"
    ) as MockApi:
        mock_api = MagicMock()
        mock_api.login.side_effect = RuntimeError("Failed")
        MockApi.return_value = mock_api

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_RECONFIGURE,
                "entry_id": entry.entry_id,
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_AUTH_METHOD: DEFAULT_AUTH_METHOD,
                CONF_USERNAME: "bad@user.pl",
                CONF_PASSWORD: "badpass",
            },
        )
        assert result["type"] == data_entry_flow.FlowResultType.FORM
        assert result["errors"]["base"] == "verify_connection_failed"


async def test_reconfigure_aborts_when_no_entry(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": "nonexistent",
        },
    )
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "no_config_entry"


async def test_import_aborts(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_IMPORT},
        data={CONF_USERNAME: "u", CONF_PASSWORD: "p"},
    )
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "one_instance_at_a_time_please"
