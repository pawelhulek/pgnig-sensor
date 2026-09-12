"""Object builders for the API payloads the tests exercise."""
from datetime import datetime

from custom_components.pgnig_gas_sensor.Invoices import Invoices, InvoicesList
from custom_components.pgnig_gas_sensor.PgpList import PpgList, PpgListElement
from custom_components.pgnig_gas_sensor.PpgReadingForMeter import (
    MeterReading,
    PpgReadingForMeter,
)


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


def make_invoice(**kwargs) -> InvoicesList:
    """An invoice with sane defaults; override only what the test cares about."""
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


def make_reading(**kwargs) -> MeterReading:
    """A meter reading with sane defaults."""
    defaults = dict(
        status="OK", reading_date_local=datetime(2022, 6, 6),
        reading_date_utc=datetime(2022, 6, 6),
        pp_id=1, value=100, value2=None, value3=None,
        meter_number="M1", region_code="PL", wear=50,
        type="G", color="red",
    )
    defaults.update(kwargs)
    return MeterReading(**defaults)


def make_invoices_response(invoices) -> Invoices:
    """Wrap invoices the way the API returns them."""
    return Invoices(
        invoices_list=list(invoices),
        code=0, message=None, display_to_end_user=None,
        token_expire_date=None, allow_load_after30_days=None,
        allow_load_after30_days_filter=False, has_non_paid_forecast=None,
        token_expire_date_utc=None, end_user_message=None,
    )


def make_readings_response(readings) -> PpgReadingForMeter:
    """Wrap meter readings the way the API returns them."""
    return PpgReadingForMeter(
        meter_readings=list(readings),
        code=0, message=None, display_to_end_user=None,
        token_expire_date=None, token_expire_date_utc=None,
        end_user_message=None,
    )


def build_stub_coordinator(hass, *, readings=None, invoices=(), has_data=True):
    """A coordinator holding fixed data, so entity tests never touch the API."""
    from unittest.mock import MagicMock

    from custom_components.pgnig_gas_sensor.coordinator import (
        PgnigCoordinator,
        PgnigData,
    )

    coordinator = PgnigCoordinator(hass, None, MagicMock(), build_meter_list("M1"))
    coordinator.data = (
        PgnigData(readings=readings or {}, invoices=tuple(invoices))
        if has_data
        else None
    )
    return coordinator
