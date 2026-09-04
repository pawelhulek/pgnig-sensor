"""Additional sensor tests covering edge cases."""
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.pgnig_gas_sensor.PpgReadingForMeter import (
    MeterReading,
    PpgReadingForMeter,
)
from custom_components.pgnig_gas_sensor.sensor import (
    PgnigSensor,
    PgnigInvoiceSensor,
    PgnigCostTrackingSensor,
    _fit_marginal_price,
    _billing_days,
    MARGINAL_PRICE_INVOICE_WINDOW,
)
from custom_components.pgnig_gas_sensor.Invoices import Invoices, InvoicesList


def _make_invoices(invoice_list):
    return Invoices(
        invoices_list=invoice_list,
        code=0, message=None,
        display_to_end_user=None,
        token_expire_date=None,
        allow_load_after30_days=None,
        allow_load_after30_days_filter=False,
        has_non_paid_forecast=None,
        token_expire_date_utc=None,
        end_user_message=None,
    )


def _make_readings(reading_list):
    return PpgReadingForMeter(
        meter_readings=reading_list,
        code=0, message=None,
        display_to_end_user=None,
        token_expire_date=None,
        token_expire_date_utc=None,
        end_user_message=None,
    )


def _invoice(**kwargs):
    defaults = dict(
        number="INV", date=datetime(2022, 6, 6),
        sell_date=datetime(2022, 6, 6),
        gross_amount=100.0, amount_to_pay=50.0,
        wear=10.0, wear_kwh=100.0, wear_m3=50.0,
        paying_deadline_date=datetime(2022, 7, 6),
        start_date=datetime(2022, 5, 1),
        end_date=datetime(2022, 5, 31),
        is_paid=False, id_pp="1", type="G", temp_type="G",
        days_remaining_to_deadline=10, has_iban=True, iban="PL00",
        status="OPEN", pdf_exists=True,
        is_interest_note=False, is_credit_note=False,
        color="red", agreement_name="Main",
        agreement_number="A1", is_additional_agreement=False,
        agreement_end_date=None, agreement_expired=False,
        pdf_print_allowed=True, payment_process_allowed=True,
        agreement_has_card=False, automatic_payment_date=None,
        is_insurance_policy=False, is_lawyer_agreement=False,
    )
    defaults.update(kwargs)
    return InvoicesList(**defaults)


def _reading(**kwargs):
    defaults = dict(
        status="OK", reading_date_local=datetime(2022, 6, 6),
        reading_date_utc=datetime(2022, 6, 6),
        pp_id=1, value=100, value2=None, value3=None,
        meter_number="M1", region_code="PL", wear=50,
        type="G", color="red",
    )
    defaults.update(kwargs)
    return MeterReading(**defaults)


@pytest.mark.asyncio
async def test_sensor_no_readings_returns_none(hass: HomeAssistant):
    api = MagicMock()
    api.readingForMeter.return_value = _make_readings([])
    sensor = PgnigSensor(hass, api, "M1", 1)
    await sensor.async_update()
    assert sensor.state is None


@pytest.mark.asyncio
async def test_sensor_native_unit_and_device_class(hass: HomeAssistant):
    api = MagicMock()
    sensor = PgnigSensor(hass, api, "M1", 1)
    assert sensor.native_unit_of_measurement == "m³"
    assert sensor.device_class == "gas"
    assert sensor.state_class == "total_increasing"


@pytest.mark.asyncio
async def test_sensor_unique_id_format(hass: HomeAssistant):
    api = MagicMock()
    sensor = PgnigSensor(hass, api, "METER-X", 42)
    assert sensor.unique_id == "pgnig_sensorMETER-X_42"


@pytest.mark.asyncio
async def test_sensor_name(hass: HomeAssistant):
    api = MagicMock()
    sensor = PgnigSensor(hass, api, "M1", 1)
    assert "Orlen Gas Sensor" in sensor.name
    assert "M1" in sensor.name


@pytest.mark.asyncio
async def test_sensor_extra_state_attributes(hass: HomeAssistant):
    api = MagicMock()
    api.readingForMeter.return_value = _make_readings([
        _reading(wear=75),
    ])
    sensor = PgnigSensor(hass, api, "M1", 1)
    await sensor.async_update()
    attrs = sensor.extra_state_attributes
    assert attrs["wear"] == 75


@pytest.mark.asyncio
async def test_sensor_state_none_when_not_updated():
    api = MagicMock()
    sensor = PgnigSensor(MagicMock(), api, "M1", 1)
    assert sensor.state is None


def _invoice_with(volume, amount, day=1, days=None):
    """Invoice for meter id_pp="1" covering `volume` m3 billed at `amount` gross.

    `days` sets the billing period length; None strips the dates so the
    per-invoice fallback is exercised.
    """
    start = datetime(2026, 1, 1)
    return _invoice(
        wear_m3=volume,
        wear=volume,
        gross_amount=amount,
        date=datetime(2026, 1, day),
        start_date=start if days else None,
        end_date=(start + timedelta(days=days)) if days else None,
    )


def test_marginal_price_separates_fixed_from_variable():
    """amount = fixed + marginal * volume, recovered exactly from clean points."""
    # 40 PLN standing charge, 3 PLN per m3.
    invoices = [_invoice_with(33, 40 + 3 * 33), _invoice_with(300, 40 + 3 * 300)]
    marginal, fixed, used, model, _ = _fit_marginal_price(invoices)
    assert model == "per_invoice"
    assert marginal == pytest.approx(3.0)
    assert fixed == pytest.approx(40.0)
    assert used == 2


def test_marginal_price_needs_two_distinct_volumes():
    """One invoice, or several at the same volume, leaves the split undetermined."""
    assert _fit_marginal_price([]) is None
    assert _fit_marginal_price([_invoice_with(33, 139)]) is None
    assert _fit_marginal_price([_invoice_with(33, 139), _invoice_with(33, 139)]) is None


def test_marginal_price_rejects_non_positive_rate():
    """A falling amount against a rising volume is not a tariff."""
    assert _fit_marginal_price([_invoice_with(33, 300), _invoice_with(300, 100)]) is None


def test_billing_days_reads_the_period():
    assert _billing_days(_invoice_with(33, 100, days=61)) == 61
    assert _billing_days(_invoice_with(33, 100)) is None


def test_fit_uses_days_when_dates_are_present():
    """Standing charges accrue per day, so a longer period carries more of them.

    2 PLN/day plus 3 PLN/m3: a 30-day and a 60-day invoice at the same volume
    differ only by the standing charge, which the per-invoice model cannot
    separate at all.
    """
    invoices = [
        _invoice_with(33, 2 * 30 + 3 * 33, days=30),
        _invoice_with(300, 2 * 60 + 3 * 300, days=60),
    ]
    marginal, per_day, used, model, _ = _fit_marginal_price(invoices)
    assert model == "per_day"
    assert marginal == pytest.approx(3.0)
    assert per_day == pytest.approx(2.0)
    assert used == 2


def test_fit_falls_back_when_dates_are_missing():
    """Without usable dates the old per-invoice split still applies."""
    invoices = [_invoice_with(33, 40 + 3 * 33), _invoice_with(300, 40 + 3 * 300)]
    marginal, fixed, used, model, _ = _fit_marginal_price(invoices)
    assert model == "per_invoice"
    assert marginal == pytest.approx(3.0)
    assert fixed == pytest.approx(40.0)


def test_equal_periods_still_recover_the_rate():
    """Equal periods are not degenerate; the per-day charge is just fixed/days.

    Volume still varies, so the slope is determined. The standing charge comes
    out as a rate rather than a lump sum, which is the same information.
    """
    invoices = [
        _invoice_with(33, 40 + 3 * 33, days=30),
        _invoice_with(300, 40 + 3 * 300, days=30),
    ]
    marginal, per_day, _, model, _ = _fit_marginal_price(invoices)
    assert model == "per_day"
    assert marginal == pytest.approx(3.0)
    assert per_day * 30 == pytest.approx(40.0)


@pytest.mark.asyncio
async def test_cost_sensor_reports_per_day_charge(hass: HomeAssistant):
    """Per-day model also reports the newest invoice's own standing charge."""
    api = MagicMock()
    api.invoices.return_value = _make_invoices([
        _invoice_with(33, 2 * 30 + 3 * 33, day=1, days=30),
        _invoice_with(300, 2 * 60 + 3 * 300, day=2, days=60),
    ])
    sensor = PgnigCostTrackingSensor(hass, api, "M1", 1)
    await sensor.async_update()

    attrs = sensor.extra_state_attributes
    assert attrs["marginal_price_model"] == "per_day"
    assert attrs["fixed_charge_per_day"] == pytest.approx(2.0)
    assert attrs["last_invoice_days"] == 60
    assert attrs["fixed_charge_per_invoice"] == pytest.approx(120.0)


@pytest.mark.asyncio
async def test_cost_sensor_reports_marginal_price(hass: HomeAssistant):
    """The regression reaches the attributes alongside the average."""
    api = MagicMock()
    api.invoices.return_value = _make_invoices(
        [_invoice_with(33, 40 + 3 * 33, day=1), _invoice_with(300, 40 + 3 * 300, day=2)]
    )
    sensor = PgnigCostTrackingSensor(hass, api, "M1", 1)
    await sensor.async_update()

    attrs = sensor.extra_state_attributes
    assert attrs["marginal_price"] == pytest.approx(3.0)
    assert attrs["fixed_charge_per_invoice"] == pytest.approx(40.0)
    assert attrs["marginal_price_invoices_used"] == 2
    # The state stays the average including standing charges, unchanged.
    assert sensor.state == pytest.approx((40 + 3 * 300) / 300)


@pytest.mark.asyncio
async def test_cost_sensor_omits_marginal_price_when_undetermined(hass: HomeAssistant):
    """A single invoice must not produce a made-up rate."""
    api = MagicMock()
    api.invoices.return_value = _make_invoices([_invoice_with(33, 139)])
    sensor = PgnigCostTrackingSensor(hass, api, "M1", 1)
    await sensor.async_update()
    assert "marginal_price" not in sensor.extra_state_attributes


@pytest.mark.asyncio
async def test_invoice_sensor_no_invoices(hass: HomeAssistant):
    api = MagicMock()
    api.invoices.return_value = _make_invoices([])
    sensor = PgnigInvoiceSensor(hass, api, "M1", 1)
    await sensor.async_update()
    assert sensor.state == 0


@pytest.mark.asyncio
async def test_invoice_sensor_attributes(hass: HomeAssistant):
    api = MagicMock()
    api.invoices.return_value = _make_invoices([
        _invoice(id_pp="1", is_paid=False, amount_to_pay=75.0,
                 paying_deadline_date=datetime(2022, 8, 15)),
    ])
    sensor = PgnigInvoiceSensor(hass, api, "M1", 1)
    await sensor.async_update()
    attrs = sensor.extra_state_attributes
    assert attrs["next_payment_amount_to_pay"] == 75.0
    assert attrs["next_payment_date"] == datetime(2022, 8, 15)


@pytest.mark.asyncio
async def test_invoice_sensor_unique_id(hass: HomeAssistant):
    api = MagicMock()
    sensor = PgnigInvoiceSensor(hass, api, "M2", 3)
    assert sensor.unique_id == "pgnig_invoice_sensorM2_3"


@pytest.mark.asyncio
async def test_invoice_sensor_native_unit(hass: HomeAssistant):
    api = MagicMock()
    sensor = PgnigInvoiceSensor(hass, api, "M1", 1)
    assert sensor.native_unit_of_measurement == "PLN"
    assert sensor.device_class == "monetary"


@pytest.mark.asyncio
async def test_cost_sensor_only_matching_meters(hass: HomeAssistant):
    api = MagicMock()
    api.invoices.return_value = _make_invoices([
        _invoice(id_pp="999", gross_amount=50.0, wear_m3=10.0),
    ])
    sensor = PgnigCostTrackingSensor(hass, api, "M1", 1)
    await sensor.async_update()
    assert sensor.state is None


@pytest.mark.asyncio
async def test_cost_sensor_credit_note_skipped(hass: HomeAssistant):
    api = MagicMock()
    api.invoices.return_value = _make_invoices([
        _invoice(id_pp="1", is_credit_note=True, gross_amount=50.0, wear_m3=10.0),
    ])
    sensor = PgnigCostTrackingSensor(hass, api, "M1", 1)
    await sensor.async_update()
    assert sensor.state is None


@pytest.mark.asyncio
async def test_cost_sensor_state_none_when_not_updated():
    api = MagicMock()
    sensor = PgnigCostTrackingSensor(MagicMock(), api, "M1", 1)
    assert sensor.state is None


@pytest.mark.asyncio
async def test_invoice_sensor_state_none_when_not_updated():
    api = MagicMock()
    sensor = PgnigInvoiceSensor(MagicMock(), api, "M1", 1)
    assert sensor.state is None


@pytest.mark.asyncio
async def test_sensor_device_info(hass: HomeAssistant):
    api = MagicMock()
    sensor = PgnigSensor(hass, api, "M-123", 5)
    info = sensor.device_info
    assert info["identifiers"] == {("pgnig_gas_sensor", "M-123")}
    assert "Orlen" in info["name"]


@pytest.mark.asyncio
async def test_invoice_sensor_device_info(hass: HomeAssistant):
    api = MagicMock()
    sensor = PgnigInvoiceSensor(hass, api, "M-123", 5)
    info = sensor.device_info
    assert info["identifiers"] == {("pgnig_gas_sensor", "M-123")}


@pytest.mark.asyncio
async def test_cost_sensor_device_info(hass: HomeAssistant):
    api = MagicMock()
    sensor = PgnigCostTrackingSensor(hass, api, "M-123", 5)
    info = sensor.device_info
    assert info["identifiers"] == {("pgnig_gas_sensor", "M-123")}


@pytest.mark.asyncio
async def test_invoice_sensor_attributes_none_when_no_invoice(hass: HomeAssistant):
    api = MagicMock()
    api.invoices.return_value = _make_invoices([])
    sensor = PgnigInvoiceSensor(hass, api, "M1", 1)
    await sensor.async_update()
    attrs = sensor.extra_state_attributes
    assert attrs["next_payment_date"] is None
    assert attrs["next_payment_amount_to_pay"] is None
    assert attrs["next_payment_wear"] is None
    assert attrs["next_payment_wear_KWH"] is None


@pytest.mark.asyncio
async def test_cost_sensor_extra_state_attributes(hass: HomeAssistant):
    api = MagicMock()
    invoice = _invoice(
        id_pp="1", gross_amount=200.0, wear_m3=50.0,
        paying_deadline_date=datetime(2022, 9, 1),
        number="INV-123",
    )
    api.invoices.return_value = _make_invoices([invoice])
    sensor = PgnigCostTrackingSensor(hass, api, "M1", 1)
    await sensor.async_update()
    attrs = sensor.extra_state_attributes
    assert attrs["last_invoice_date"] == datetime(2022, 9, 1)
    assert attrs["last_invoice_gross_amount"] == 200.0
    assert attrs["last_invoice_wear_m3"] == 50.0
    assert attrs["last_invoice_number"] == "INV-123"


@pytest.mark.asyncio
async def test_cost_sensor_attributes_none_when_no_data(hass: HomeAssistant):
    api = MagicMock()
    api.invoices.return_value = _make_invoices([])
    sensor = PgnigCostTrackingSensor(hass, api, "M1", 1)
    await sensor.async_update()
    assert sensor.extra_state_attributes == {}


def test_fit_uses_only_the_most_recent_invoices():
    """A tariff change must not be averaged into the current rate.

    Old invoices at 6 PLN/m3, recent ones at 3. Fitting everything would land
    between the two and describe neither.
    """
    old = [
        _invoice_with(100 + i, 2 * 30 + 6 * (100 + i), day=1 + i, days=30)
        for i in range(6)
    ]
    recent = [
        _invoice_with(30 + 40 * i, 2 * 30 + 3 * (30 + 40 * i), day=20 + i, days=30)
        for i in range(MARGINAL_PRICE_INVOICE_WINDOW)
    ]
    marginal, _, used, _, _ = _fit_marginal_price(old + recent)
    assert used == MARGINAL_PRICE_INVOICE_WINDOW
    assert marginal == pytest.approx(3.0)


def test_residual_is_reported_and_small_for_a_clean_fit():
    invoices = [
        _invoice_with(33, 2 * 30 + 3 * 33, day=1, days=30),
        _invoice_with(300, 2 * 60 + 3 * 300, day=2, days=60),
    ]
    *_, residual = _fit_marginal_price(invoices)
    assert residual == pytest.approx(0.0, abs=1e-6)


def test_residual_grows_when_the_model_does_not_describe_the_bills():
    """A tariff change inside the window shows up as a large residual."""
    invoices = [
        _invoice_with(100, 2 * 30 + 6 * 100, day=1, days=30),
        _invoice_with(110, 2 * 30 + 3 * 110, day=2, days=30),
        _invoice_with(120, 2 * 30 + 6 * 120, day=3, days=30),
    ]
    *_, residual = _fit_marginal_price(invoices)
    assert residual > 5


@pytest.mark.asyncio
async def test_reading_date_sensor_reports_aware_timestamp(hass: HomeAssistant):
    """An attribute cannot be graphed or alerted on; a timestamp entity can."""
    from custom_components.pgnig_gas_sensor.sensor import PgnigReadingDateSensor

    api = MagicMock()
    api.readingForMeter.return_value = _make_readings([
        _reading(reading_date_utc=datetime(2026, 8, 31), value=417, type="Real"),
    ])
    sensor = PgnigReadingDateSensor(hass, api, "M1", 1)
    await sensor.async_update()

    assert sensor.state == datetime(2026, 8, 31, tzinfo=UTC)
    assert sensor.extra_state_attributes["reading_type"] == "Real"
    assert sensor.extra_state_attributes["value"] == 417


@pytest.mark.asyncio
async def test_reading_date_sensor_without_readings(hass: HomeAssistant):
    from custom_components.pgnig_gas_sensor.sensor import PgnigReadingDateSensor

    api = MagicMock()
    api.readingForMeter.return_value = _make_readings([])
    sensor = PgnigReadingDateSensor(hass, api, "M1", 1)
    await sensor.async_update()

    assert sensor.state is None
    assert sensor.extra_state_attributes == {}


@pytest.mark.asyncio
async def test_marginal_price_sensor_reports_the_fitted_rate(hass: HomeAssistant):
    """The Energy dashboard needs a rate, not an average carrying fixed fees."""
    from custom_components.pgnig_gas_sensor.sensor import PgnigMarginalPriceSensor

    api = MagicMock()
    api.invoices.return_value = _make_invoices([
        _invoice_with(33, 2 * 30 + 3 * 33, day=1, days=30),
        _invoice_with(300, 2 * 60 + 3 * 300, day=2, days=60),
    ])
    sensor = PgnigMarginalPriceSensor(hass, api, "M1", 1)
    await sensor.async_update()

    assert sensor.state == pytest.approx(3.0)
    attrs = sensor.extra_state_attributes
    assert attrs["model"] == "per_day"
    assert attrs["fixed_charge_per_day"] == pytest.approx(2.0)
    assert attrs["fixed_charge_per_invoice"] == pytest.approx(120.0)
    assert attrs["residual_pct"] == pytest.approx(0.0, abs=1e-6)


@pytest.mark.asyncio
async def test_marginal_price_sensor_is_none_when_undetermined(hass: HomeAssistant):
    """One invoice cannot separate the rate from the standing charge."""
    from custom_components.pgnig_gas_sensor.sensor import PgnigMarginalPriceSensor

    api = MagicMock()
    api.invoices.return_value = _make_invoices([_invoice_with(33, 139)])
    sensor = PgnigMarginalPriceSensor(hass, api, "M1", 1)
    await sensor.async_update()

    assert sensor.state is None
    assert sensor.extra_state_attributes == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sensor_name",
    ["PgnigReadingDateSensor", "PgnigMarginalPriceSensor"],
)
async def test_new_sensors_join_the_existing_device(hass: HomeAssistant, sensor_name):
    """Both must land on the meter device, not create their own."""
    import custom_components.pgnig_gas_sensor.sensor as module

    sensor = getattr(module, sensor_name)(hass, MagicMock(), "M-123", 5)
    info = sensor.device_info
    assert info["identifiers"] == {("pgnig_gas_sensor", "M-123")}
    assert "via_device" not in info
