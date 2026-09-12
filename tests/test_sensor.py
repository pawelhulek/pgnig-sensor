"""Pgnig sensor test pack — state derived from one coordinator poll."""

from datetime import datetime

import pytest
from homeassistant.core import HomeAssistant

from custom_components.pgnig_gas_sensor.sensor import (
    PgnigCostTrackingSensor,
    PgnigInvoiceSensor,
    PgnigSensor,
)

from .builders import build_stub_coordinator, make_invoice, make_reading


@pytest.mark.asyncio
async def test_meter_sensor_exposes_the_reading_for_its_meter(hass: HomeAssistant):
    coordinator = build_stub_coordinator(
        hass,
        readings={
            "M1": make_reading(value=2),
            "M2": make_reading(value=99),
        },
    )

    assert PgnigSensor(coordinator, "M1", 1).state == 2


@pytest.mark.asyncio
async def test_next_payment_is_the_earliest_unpaid_invoice(hass: HomeAssistant):
    coordinator = build_stub_coordinator(
        hass,
        invoices=[
            make_invoice(id_pp="1", date=datetime(2022, 7, 1), amount_to_pay=1.0),
            make_invoice(id_pp="1", date=datetime(2022, 8, 1), amount_to_pay=9.0),
        ],
    )

    sensor = PgnigInvoiceSensor(coordinator, "12", 1)

    assert sensor.state == 10.0
    assert sensor.extra_state_attributes["next_payment_amount_to_pay"] == 1.0


@pytest.mark.asyncio
async def test_price_is_gross_amount_per_cubic_metre(hass: HomeAssistant):
    coordinator = build_stub_coordinator(
        hass, invoices=[make_invoice(id_pp="1", gross_amount=10.0, wear_m3=1.0)]
    )

    assert PgnigCostTrackingSensor(coordinator, "12", 1).state == 10.0


@pytest.mark.asyncio
async def test_price_comes_from_the_newest_invoice(hass: HomeAssistant):
    coordinator = build_stub_coordinator(
        hass,
        invoices=[
            make_invoice(id_pp="1", date=datetime(2022, 7, 15), gross_amount=1.0, wear_m3=1.0),
            make_invoice(id_pp="1", date=datetime(2022, 8, 15), gross_amount=2.0, wear_m3=1.0),
        ],
    )

    assert PgnigCostTrackingSensor(coordinator, "12", 1).state == 2.0


@pytest.mark.asyncio
async def test_price_skips_invoices_without_consumption(hass: HomeAssistant):
    """A newer invoice with no usable m³ must not hide the last real price."""
    coordinator = build_stub_coordinator(
        hass,
        invoices=[
            make_invoice(id_pp="1", date=datetime(2022, 9, 15), gross_amount=1.0, wear_m3=0.0, wear=0.0),
            make_invoice(id_pp="1", date=datetime(2022, 8, 15), gross_amount=2.0, wear_m3=1.0),
        ],
    )

    assert PgnigCostTrackingSensor(coordinator, "12", 1).state == 2.0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invoice_kwargs",
    [
        pytest.param({"gross_amount": None, "wear_m3": 1.0}, id="no_gross_amount"),
        pytest.param({"gross_amount": 1.0, "wear_m3": 0.0, "wear": 0.0}, id="no_consumption"),
    ],
)
async def test_price_is_none_without_usable_figures(hass: HomeAssistant, invoice_kwargs):
    coordinator = build_stub_coordinator(
        hass, invoices=[make_invoice(id_pp="1", **invoice_kwargs)]
    )

    assert PgnigCostTrackingSensor(coordinator, "12", 1).state is None
