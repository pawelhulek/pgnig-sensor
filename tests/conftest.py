"""Global fixtures for pgnig_sensor integration."""
import logging
from unittest.mock import MagicMock

import pytest

from custom_components.pgnig_gas_sensor.PgpList import PpgList

from .builders import (
    build_meter_list,
    make_invoice,
    make_invoices_response,
    make_reading,
    make_readings_response,
)

# The `enable_custom_integrations` fixture is provided by
# pytest-homeassistant-custom-component plugin.
# Individual test files should request it when needed.

logging.getLogger("custom_components.pgnig_gas_sensor").setLevel(logging.DEBUG)


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
    api.readingForMeter.return_value = make_readings_response([make_reading()])
    api.invoices.return_value = make_invoices_response([make_invoice()])
    return api
