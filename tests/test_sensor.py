"""Pgnig sensor test pack."""

from datetime import datetime
from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant

from custom_components.pgnig_gas_sensor.PpgReadingForMeter import (
    MeterReading,
    PpgReadingForMeter,
)
from custom_components.pgnig_gas_sensor.sensor import PgnigSensor, PgnigInvoiceSensor, PgnigCostTrackingSensor
from custom_components.pgnig_gas_sensor.Invoices import Invoices, InvoicesList


async def test_newer_takes_precedence(hass: HomeAssistant):
    """Pgnig sensor test - test_newer_takes_precedence."""
    # given
    pgnig_api = MagicMock()
    reading_newer = any_meter_reading()
    reading_newer.reading_date_utc = datetime(2022, 7, 5)
    reading_newer.value = 2

    reading_older = any_meter_reading()
    reading_older.reading_date_utc = datetime(2022, 7, 4)
    reading_older.value = 3
    pgnig_api.readingForMeter = MagicMock(return_value=(
        PpgReadingForMeter(meter_readings=[reading_older, reading_newer], code=0, message=None,
                           display_to_end_user=None,
                           token_expire_date=None,
                           token_expire_date_utc=None, end_user_message=None)))
    sensor = PgnigSensor(hass, pgnig_api, "1", 2)
    # when
    await sensor.async_update()
    # then
    assert sensor._state.value == 2


async def test_multiple_invocies(hass: HomeAssistant):
    """Pgnig sensor test - test_multiple_invocies."""
    pgnig_api = MagicMock()
    pgnig_api.invoices = MagicMock(return_value=(Invoices(invoices_list=[any_invoice(), any_invoice()],
                                                          code=0, message=None,
                                                          display_to_end_user=None,
                                                          token_expire_date=None, allow_load_after30_days=None,
                                                          has_non_paid_forecast=None,
                                                          token_expire_date_utc=None, end_user_message=None)))
    sensor = PgnigInvoiceSensor(hass, pgnig_api, '12', 1)
    await sensor.async_update()
    # then
    assert sensor._state.get('nextPaymentAmountToPay') == 1


async def test_a_price(hass: HomeAssistant):
    """Pgnig sensor test - test_multiple_invocies."""
    pgnig_api = MagicMock()
    invoice = any_invoice()
    invoice.gross_amount = 10
    invoice.wear_kwh = 1
    pgnig_api.invoices = MagicMock(return_value=(Invoices(invoices_list=[invoice],
                                                          code=0, message=None,
                                                          display_to_end_user=None,
                                                          token_expire_date=None, allow_load_after30_days=None,
                                                          has_non_paid_forecast=None,
                                                          token_expire_date_utc=None, end_user_message=None)))
    sensor = PgnigCostTrackingSensor(hass, pgnig_api, '12', 1)
    await sensor.async_update()
    # then
    assert sensor.state == 10.0

async def test_latest_price(hass: HomeAssistant):
    """Pgnig sensor test - test_multiple_invocies."""
    pgnig_api = MagicMock()
    old_invoice = any_invoice()
    old_invoice.date = datetime(2022, 7, 15)
    old_invoice.gross_amount = 1
    old_invoice.wear_kwh = 1

    new_invoice = any_invoice()
    new_invoice.date = datetime(2022, 8, 15)
    new_invoice.gross_amount = 2
    new_invoice.wear_kwh = 1

    pgnig_api.invoices = MagicMock(return_value=(Invoices(invoices_list=[old_invoice,new_invoice],
                                                          code=0, message=None,
                                                          display_to_end_user=None,
                                                          token_expire_date=None, allow_load_after30_days=None,
                                                          has_non_paid_forecast=None,
                                                          token_expire_date_utc=None, end_user_message=None)))
    sensor = PgnigCostTrackingSensor(hass, pgnig_api, '12', 1)
    await sensor.async_update()
    # then
    assert sensor.state == 2.0


def any_invoice() -> InvoicesList:
    return InvoicesList(number="a",
                        date=datetime(2022, 6, 6),
                        sell_date=datetime(2022, 6, 6),
                        gross_amount=22,
                        amount_to_pay=1,
                        wear=1,
                        wear_kwh=1,
                        paying_deadline_date=datetime(2022, 6, 6),
                        start_date=datetime(2022, 6, 6),
                        end_date=datetime(2022, 6, 6),
                        is_paid=False,
                        id_pp=1,
                        type='a',
                        temp_type='a',
                        days_remaining_to_deadline=1,
                        has_iban=True,
                        status='a',
                        pdf_exists=True,
                        is_interest_note=True,
                        color='a',
                        agreement_name='a',
                        agreement_number='a',
                        is_additional_agreement=True,
                        agreement_end_date=None,
                        agreement_expired=True,
                        pdf_print_allowed=True,
                        payment_process_allowed=True,
                        agreement_has_card=True,
                        automatic_payment_date=datetime(2022, 6, 6),
                        is_insurance_policy=True,
                        is_lawyer_agreement=True)


def any_meter_reading():
    """Any helper method for meter reading template."""
    return MeterReading(status="",
                        reading_date_local=datetime(2022, 6, 6),
                        reading_date_utc=datetime(2022, 6, 6),
                        pp_id=None,
                        value=2,
                        value2=None,
                        value3=None,
                        meter_number=None,
                        region_code=None,
                        wear=None,
                        type=None,
                        color=None)
