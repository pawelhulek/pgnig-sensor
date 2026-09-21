"""Platform for sensor integration."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Callable, Optional, Sequence

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, UnitOfVolume
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_AUTH_METHOD, DOMAIN
from .coordinator import PgnigCoordinator, PgnigData
from .Invoices import InvoicesList
from .PgnigApi import PgnigApi

_LOGGER = logging.getLogger(__name__)
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
})


def _as_utc(value: datetime | None) -> datetime | None:
    """Return an aware UTC datetime; EBOK sends ReadingDateUtc without a suffix."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def invoice_summary(
    invoices: Sequence[InvoicesList], id_local: int
) -> dict[str, Any]:
    """Unpaid total and the next payment due for one meter."""

    def upcoming_payment_for_meter(x: InvoicesList) -> bool:
        return str(id_local) == str(x.id_pp) and not x.is_paid and not x.is_credit_note

    unpaid_invoices = list(filter(upcoming_payment_for_meter, invoices))
    sum_of_unpaid_invoices = sum(x.amount_to_pay for x in unpaid_invoices)
    next_payment_item = (
        min(unpaid_invoices, key=lambda z: z.date) if unpaid_invoices else None
    )

    return {
        "sumOfUnpaidInvoices": sum_of_unpaid_invoices,
        "nextPaymentDate": next_payment_item.paying_deadline_date if next_payment_item else None,
        "nextPaymentWear": next_payment_item.wear_m3 or next_payment_item.wear if next_payment_item else None,
        "nextPaymentWearKWH": next_payment_item.wear_kwh if next_payment_item else None,
        "nextPaymentAmountToPay": next_payment_item.amount_to_pay if next_payment_item else None,
    }


def latest_priced_invoice(
    invoices: Sequence[InvoicesList], id_local: int
) -> InvoicesList | None:
    """The newest invoice for one meter that carries a usable price per m³."""

    def has_valid_consumption(x: InvoicesList) -> bool:
        gas_m3 = x.wear_m3 or x.wear
        return (
            str(id_local) == str(x.id_pp)
            and gas_m3 is not None
            and gas_m3 != 0
            and x.gross_amount is not None
            and x.gross_amount != 0
            and not x.is_credit_note
        )

    valid_invoices = list(filter(has_valid_consumption, invoices))
    return max(valid_invoices, key=lambda z: z.date) if valid_invoices else None


def entities_for_meters(coordinator: PgnigCoordinator) -> list[SensorEntity]:
    """Every sensor the given coordinator feeds."""
    return [
        entity
        for meter in coordinator.meters.ppg_list
        for entity in (
            PgnigSensor(
                coordinator, meter.meter_number, meter.id_local, tariff=meter.tariff
            ),
            PgnigInvoiceSensor(coordinator, meter.meter_number, meter.id_local),
            PgnigCostTrackingSensor(coordinator, meter.meter_number, meter.id_local),
        )
    ]


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities,
):
    runtime = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities(entities_for_meters(runtime.coordinator))


async def async_setup_platform(
        hass: HomeAssistant,
        config: ConfigType,
        async_add_entities: Callable,
        discovery_info: Optional[DiscoveryInfoType] = None,
) -> None:
    api = PgnigApi(config.get(CONF_USERNAME), config.get(CONF_PASSWORD), DEFAULT_AUTH_METHOD)
    meters = await hass.async_add_executor_job(api.meterList)
    coordinator = PgnigCoordinator(hass, None, api, meters)
    await coordinator.async_refresh()
    async_add_entities(entities_for_meters(coordinator))


class PgnigBaseSensor(CoordinatorEntity[PgnigCoordinator], SensorEntity):
    """Shared identity and state refresh for one meter's sensors.

    State is recomputed when the coordinator delivers a poll, so the entities
    never touch the API themselves.
    """

    _name_prefix: str
    _unique_id_prefix: str

    def __init__(
        self, coordinator: PgnigCoordinator, meter_id: str, id_local: int
    ) -> None:
        super().__init__(coordinator)
        self.meter_id = meter_id
        self.id_local = id_local
        self.entity_name = f"{self._name_prefix} {meter_id} {id_local}"
        self._state: Any = None
        self._refresh_state()

    @property
    def unique_id(self) -> str | None:
        return f"{self._unique_id_prefix}{self.meter_id}_{self.id_local}"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.meter_id)},
            "name": f"Orlen GAS METER ID {self.meter_id}",
            "manufacturer": "Orlen",
            "model": self.meter_id,
        }

    @property
    def name(self) -> str:
        return self.entity_name

    def _state_from(self, data: PgnigData) -> Any:
        """Derive this entity's state from one poll."""
        raise NotImplementedError

    def _refresh_state(self) -> None:
        data = self.coordinator.data
        self._state = None if data is None else self._state_from(data)

    @callback
    def _handle_coordinator_update(self) -> None:
        self._refresh_state()
        _LOGGER.debug("%s updated: %s", self.entity_name, self.state)
        super()._handle_coordinator_update()


class PgnigSensor(PgnigBaseSensor):
    """Latest meter reading."""

    _name_prefix = "Orlen Gas Sensor"
    _unique_id_prefix = "pgnig_sensor"

    _attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
    _attr_device_class = SensorDeviceClass.GAS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self,
        coordinator: PgnigCoordinator,
        meter_id: str,
        id_local: int,
        tariff: str | None = None,
    ) -> None:
        self.tariff = tariff
        super().__init__(coordinator, meter_id, id_local)

    def _state_from(self, data: PgnigData):
        return data.readings.get(self.meter_id)

    @property
    def state(self):
        if self._state is None:
            return None
        return self._state.value

    @property
    def extra_state_attributes(self):
        attrs = dict()
        if self.tariff:
            attrs["tariff"] = self.tariff
        if self._state is not None:
            attrs["wear"] = self._state.wear
            attrs["wear_unit_of_measurment"] = UnitOfVolume.CUBIC_METERS
            attrs["reading_date"] = _as_utc(self._state.reading_date_utc)
            attrs["reading_date_local"] = self._state.reading_date_local
            attrs["reading_type"] = self._state.type
            attrs["reading_status"] = self._state.status
        return attrs


class PgnigInvoiceSensor(PgnigBaseSensor):
    """Total still owed, plus the next payment due."""

    _name_prefix = "Orlen Gas Invoice Sensor"
    _unique_id_prefix = "pgnig_invoice_sensor"

    _attr_native_unit_of_measurement = "PLN"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.MEASUREMENT

    def _state_from(self, data: PgnigData):
        return invoice_summary(data.invoices, self.id_local)

    @property
    def state(self):
        if self._state is None:
            return None
        return self._state.get("sumOfUnpaidInvoices")

    @property
    def extra_state_attributes(self):
        attrs = dict()
        if self._state is not None:
            attrs["next_payment_date"] = self._state.get("nextPaymentDate")
            attrs["next_payment_amount_to_pay"] = self._state.get("nextPaymentAmountToPay")
            attrs["next_payment_wear"] = self._state.get("nextPaymentWear")
            attrs["next_payment_wear_KWH"] = self._state.get("nextPaymentWearKWH")
        return attrs


class PgnigCostTrackingSensor(PgnigBaseSensor):
    """Price per m³ from the most recent priced invoice."""

    _name_prefix = "Orlen Gas Cost Tracking Sensor"
    _unique_id_prefix = "pgnig_cost_tracking_sensor"

    _attr_native_unit_of_measurement = "PLN/m³"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.MEASUREMENT

    def _state_from(self, data: PgnigData):
        return latest_priced_invoice(data.invoices, self.id_local)

    @property
    def state(self):
        if self._state is None:
            return None
        gas_m3 = self._state.wear_m3 or self._state.wear
        if self._state.gross_amount is None or gas_m3 is None or gas_m3 == 0:
            return None
        return self._state.gross_amount / gas_m3

    @property
    def extra_state_attributes(self):
        attrs = dict()
        if self._state is not None:
            attrs["last_invoice_date"] = self._state.paying_deadline_date
            attrs["last_invoice_gross_amount"] = self._state.gross_amount
            attrs["last_invoice_wear_m3"] = self._state.wear_m3
            attrs["last_invoice_wear_KWH"] = self._state.wear_kwh
            attrs["last_invoice_number"] = self._state.number
        return attrs
