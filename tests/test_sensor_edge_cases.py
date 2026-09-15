"""Additional sensor tests covering identity and empty-data edge cases."""
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.pgnig_gas_sensor.const import DOMAIN
from custom_components.pgnig_gas_sensor.coordinator import PgnigData
from custom_components.pgnig_gas_sensor.sensor import (
    PgnigCostTrackingSensor,
    PgnigInvoiceSensor,
    PgnigSensor,
    entities_for_meters,
)

from .builders import build_stub_coordinator, make_invoice, make_reading

SENSOR_CLASSES = [PgnigSensor, PgnigInvoiceSensor, PgnigCostTrackingSensor]


# --- identity ----------------------------------------------------------


@pytest.mark.parametrize(
    ("sensor_class", "expected"),
    [
        (PgnigSensor, "pgnig_sensorMETER-X_42"),
        (PgnigInvoiceSensor, "pgnig_invoice_sensorMETER-X_42"),
        (PgnigCostTrackingSensor, "pgnig_cost_tracking_sensorMETER-X_42"),
    ],
)
async def test_unique_id_format(hass: HomeAssistant, sensor_class, expected):
    """Unique ids are user-visible entity identity - they must not drift."""
    coordinator = build_stub_coordinator(hass)
    assert sensor_class(coordinator, "METER-X", 42).unique_id == expected


@pytest.mark.parametrize(
    ("sensor_class", "expected"),
    [
        (PgnigSensor, "Orlen Gas Sensor M1 1"),
        (PgnigInvoiceSensor, "Orlen Gas Invoice Sensor M1 1"),
        (PgnigCostTrackingSensor, "Orlen Gas Cost Tracking Sensor M1 1"),
    ],
)
async def test_name_format(hass: HomeAssistant, sensor_class, expected):
    coordinator = build_stub_coordinator(hass)
    assert sensor_class(coordinator, "M1", 1).name == expected


@pytest.mark.parametrize("sensor_class", SENSOR_CLASSES)
async def test_device_info(hass: HomeAssistant, sensor_class):
    coordinator = build_stub_coordinator(hass)
    info = sensor_class(coordinator, "M-123", 5).device_info
    assert info["identifiers"] == {(DOMAIN, "M-123")}
    assert "Orlen" in info["name"]


async def test_meter_sensor_units(hass: HomeAssistant):
    sensor = PgnigSensor(build_stub_coordinator(hass), "M1", 1)
    assert sensor.native_unit_of_measurement == "m³"
    assert sensor.device_class == "gas"
    assert sensor.state_class == "total_increasing"


async def test_invoice_sensor_units(hass: HomeAssistant):
    sensor = PgnigInvoiceSensor(build_stub_coordinator(hass), "M1", 1)
    assert sensor.native_unit_of_measurement == "PLN"
    assert sensor.device_class == "monetary"


# --- no data yet -------------------------------------------------------


@pytest.mark.parametrize("sensor_class", SENSOR_CLASSES)
async def test_state_is_none_before_the_first_poll(hass: HomeAssistant, sensor_class):
    coordinator = build_stub_coordinator(hass, has_data=False)
    assert sensor_class(coordinator, "M1", 1).state is None


async def test_meter_sensor_without_a_reading(hass: HomeAssistant):
    coordinator = build_stub_coordinator(hass, readings={"M1": None})
    sensor = PgnigSensor(coordinator, "M1", 1)
    assert sensor.state is None
    assert sensor.extra_state_attributes == {}


async def test_invoice_sensor_without_invoices(hass: HomeAssistant):
    sensor = PgnigInvoiceSensor(build_stub_coordinator(hass), "M1", 1)
    assert sensor.state == 0
    attrs = sensor.extra_state_attributes
    assert attrs["next_payment_date"] is None
    assert attrs["next_payment_amount_to_pay"] is None
    assert attrs["next_payment_wear"] is None
    assert attrs["next_payment_wear_KWH"] is None


async def test_cost_sensor_without_invoices(hass: HomeAssistant):
    sensor = PgnigCostTrackingSensor(build_stub_coordinator(hass), "M1", 1)
    assert sensor.state is None
    assert sensor.extra_state_attributes == {}


# --- filtering ---------------------------------------------------------


@pytest.mark.parametrize(
    "invoice_kwargs",
    [
        pytest.param({"id_pp": "999"}, id="other_meter"),
        pytest.param({"id_pp": "1", "is_credit_note": True}, id="credit_note"),
    ],
)
async def test_cost_sensor_ignores_invoices_that_do_not_count(
    hass: HomeAssistant, invoice_kwargs
):
    coordinator = build_stub_coordinator(
        hass,
        invoices=[make_invoice(gross_amount=50.0, wear_m3=10.0, **invoice_kwargs)],
    )
    assert PgnigCostTrackingSensor(coordinator, "M1", 1).state is None


# --- attributes --------------------------------------------------------


async def test_meter_sensor_attributes(hass: HomeAssistant):
    coordinator = build_stub_coordinator(hass, readings={"M1": make_reading(wear=75)})
    attrs = PgnigSensor(coordinator, "M1", 1).extra_state_attributes
    assert attrs["wear"] == 75
    assert attrs["wear_unit_of_measurment"] == "m³"


async def test_meter_sensor_exposes_reading_metadata(hass: HomeAssistant):
    """Reading date, type and status must reach the attributes."""
    reading = make_reading(
        status="Zaakceptowany",
        type="Odczyt",
        reading_date_local=datetime(2026, 9, 1, 12, 30),
        reading_date_utc=datetime(2026, 9, 1, 10, 30),
    )
    coordinator = build_stub_coordinator(hass, readings={"M1": reading})
    attrs = PgnigSensor(coordinator, "M1", 1).extra_state_attributes
    assert attrs["reading_type"] == "Odczyt"
    assert attrs["reading_status"] == "Zaakceptowany"
    assert attrs["reading_date"] == datetime(2026, 9, 1, 10, 30, tzinfo=UTC)
    assert attrs["reading_date_local"] == datetime(2026, 9, 1, 12, 30)


async def test_meter_sensor_exposes_tariff(hass: HomeAssistant):
    """The meter list carries the tariff symbol; surface it."""
    coordinator = build_stub_coordinator(hass)
    sensor = PgnigSensor(coordinator, "M1", 1, tariff="W-3.6")
    assert sensor.extra_state_attributes["tariff"] == "W-3.6"


async def test_meter_sensor_omits_tariff_when_unknown(hass: HomeAssistant):
    """No tariff means no key, not an empty one."""
    coordinator = build_stub_coordinator(hass)
    assert "tariff" not in PgnigSensor(coordinator, "M1", 1).extra_state_attributes


async def test_setup_passes_the_tariff_from_the_meter_list(hass: HomeAssistant):
    """The symbol must survive the trip from get-ppg-list to the entity."""
    coordinator = build_stub_coordinator(hass)
    meter_sensors = [
        entity for entity in entities_for_meters(coordinator)
        if isinstance(entity, PgnigSensor)
    ]
    assert [sensor.tariff for sensor in meter_sensors] == ["T1"]


async def test_invoice_sensor_attributes(hass: HomeAssistant):
    coordinator = build_stub_coordinator(
        hass,
        invoices=[
            make_invoice(
                id_pp="1", is_paid=False, amount_to_pay=75.0,
                paying_deadline_date=datetime(2022, 8, 15),
            )
        ],
    )
    attrs = PgnigInvoiceSensor(coordinator, "M1", 1).extra_state_attributes
    assert attrs["next_payment_amount_to_pay"] == 75.0
    assert attrs["next_payment_date"] == datetime(2022, 8, 15)


async def test_cost_sensor_attributes(hass: HomeAssistant):
    coordinator = build_stub_coordinator(
        hass,
        invoices=[
            make_invoice(
                id_pp="1", gross_amount=200.0, wear_m3=50.0,
                paying_deadline_date=datetime(2022, 9, 1), number="INV-123",
            )
        ],
    )
    attrs = PgnigCostTrackingSensor(coordinator, "M1", 1).extra_state_attributes
    assert attrs["last_invoice_date"] == datetime(2022, 9, 1)
    assert attrs["last_invoice_gross_amount"] == 200.0
    assert attrs["last_invoice_wear_m3"] == 50.0
    assert attrs["last_invoice_number"] == "INV-123"


# --- refresh -----------------------------------------------------------


async def test_state_follows_the_coordinator(hass: HomeAssistant):
    """A new poll must be picked up without the entity calling the API."""
    coordinator = build_stub_coordinator(hass, readings={"M1": make_reading(value=1)})
    sensor = PgnigSensor(coordinator, "M1", 1)
    assert sensor.state == 1

    coordinator.data = PgnigData(readings={"M1": make_reading(value=7)}, invoices=())
    with patch.object(PgnigSensor, "async_write_ha_state") as write_state:
        sensor._handle_coordinator_update()

    assert sensor.state == 7
    write_state.assert_called_once()


async def test_entities_do_not_poll(hass: HomeAssistant):
    """Polling is the coordinator's job; entities are push-updated."""
    sensor = PgnigSensor(build_stub_coordinator(hass), "M1", 1)
    assert sensor.should_poll is False
