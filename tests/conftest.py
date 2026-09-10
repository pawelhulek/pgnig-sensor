"""Global fixtures for pgnig_sensor integration."""
import logging
from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
)

from custom_components.pgnig_gas_sensor.PgpList import PpgList, PpgListElement


# The `enable_custom_integrations` fixture is provided by
# pytest-homeassistant-custom-component plugin.
# Individual test files should request it when needed.


logging.getLogger("custom_components.pgnig_gas_sensor").setLevel(logging.DEBUG)


def build_meter_list(*meter_numbers: str) -> PpgList:
    """Build a PpgList covering the given meters, for platform setup tests."""
    return PpgList(
        ppg_list=[
            PpgListElement(
                id_ppg=str(index), meter_number=number, contract_number="C1",
                has_t12=True, reading_added=True, tariff="T1",
                has_history=True, type="G", id_local=index,
                client_number=100, installation_number="INST1",
                color="red", agreement_name="Main",
                can_create_home_assistant=True, add_reading_mode="auto",
                is_in_migration=False, is_in_migration_rk=False,
                is_in_migration_rw=False, is_company=False,
            )
            for index, number in enumerate(meter_numbers, start=1)
        ],
        code=0, message=None, display_to_end_user=False,
        end_user_message=None,
        token_expire_date="2026-06-01T00:00:00",
        token_expire_date_utc="2026-06-01T00:00:00",
    )


@pytest.fixture
def mock_meters() -> PpgList:
    """A single-meter PpgList."""
    return build_meter_list("METER1")


@pytest.fixture
def mock_api(mock_meters: PpgList) -> MagicMock:
    """A PgnigApi stub that authenticates and returns one meter."""
    api = MagicMock()
    api.meterList.return_value = mock_meters
    api.login.return_value = "TOKEN"
    return api
