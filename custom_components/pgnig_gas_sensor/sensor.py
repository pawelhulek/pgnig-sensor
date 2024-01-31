"""Platform for sensor integration."""
from __future__ import annotations

import logging
import string
from datetime import timedelta
from typing import Callable, Optional

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.sensor import SensorEntity, PLATFORM_SCHEMA, SensorStateClass, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType, HomeAssistantType


from .Invoices import InvoicesList
from .PgnigApi import PgnigApi
from .PpgReadingForMeter import MeterReading

_LOGGER = logging.getLogger(__name__)
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
})
SCAN_INTERVAL = timedelta(hours=8)


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities,
):
    user = config_entry.data[CONF_USERNAME]
    password = config_entry.data[CONF_PASSWORD]
    api = PgnigApi(user, password)
    try:
        pgps = await hass.async_add_executor_job(api.meterList)
    except Exception:
        raise ValueError

    for x in pgps.ppg_list:
        meter_id = x.meter_number
        async_add_entities(
            [PgnigSensor(hass, api, meter_id, x.id_local),
             PgnigInvoiceSensor(hass, api, meter_id, x.id_local),
             PgnigCostTrackingSensor(hass, api, meter_id, x.id_local)],
            update_before_add=True)


async def async_setup_platform(
        hass: HomeAssistantType,
        config: ConfigType,
        async_add_entities: Callable,
        discovery_info: Optional[DiscoveryInfoType] = None,
) -> None:
    api = PgnigApi(config.get(CONF_USERNAME), config.get(CONF_PASSWORD))
    try:
        pgps = await hass.async_add_executor_job(api.meterList)
    except Exception:
        raise ValueError

    for x in pgps.ppg_list:
        async_add_entities(
            [PgnigSensor(hass, api, x.meter_number, x.id_local),
             PgnigInvoiceSensor(hass, api, x.meter_number, x.id_local),
             PgnigCostTrackingSensor(hass, api, x.meter_number, x.id_local)],
            update_before_add=True)


class PgnigSensor(SensorEntity):
    def __init__(self, hass, api: PgnigApi, meter_id: string, id_local: int) -> None:
        self._attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
        self._attr_device_class = SensorDeviceClass.GAS
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._state: MeterReading | None = None
        self.hass = hass
        self.api = api
        self.meter_id = meter_id
        self.id_local = id_local
        self.entity_name = "PGNIG Gas Sensor " + meter_id + " " + str(id_local)

    @property
    def unique_id(self) -> str | None:
        return "pgnig_sensor" + self.meter_id + "_" + str(self.id_local)

    @property
    def device_info(self):
        return {
            "identifiers": {("pgnig_gas_sensor", self.meter_id)},
            "name": f"PGNIG GAS METER ID {self.meter_id}",
            "manufacturer": "PGNIG",
            "model": self.meter_id,
            "via_device": None,
        }

    @property
    def name(self) -> str:
        return self.entity_name

    @property
    def state(self):
        if self._state is None:
            return None
        return self._state.value

    @property
    def extra_state_attributes(self):
        attrs = dict()
        if self._state is not None:
            attrs["wear"] = self._state.wear
            attrs["wear_unit_of_measurment"] = UnitOfVolume.CUBIC_METERS
        return attrs

    async def async_update(self):
        latest_meter_reading: MeterReading = await self.hass.async_add_executor_job(self.latestMeterReading)
        self._state = latest_meter_reading

    def latestMeterReading(self):
        return max(self.api.readingForMeter(self.meter_id).meter_readings,
                   key=lambda z: z.reading_date_utc)


class PgnigInvoiceSensor(SensorEntity):
    def __init__(self, hass, api: PgnigApi, meter_id: string, id_local: int) -> None:
        self._attr_native_unit_of_measurement = "PLN"
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._state: MeterReading | None = None
        self.hass = hass
        self.api = api
        self.meter_id = meter_id
        self.id_local = id_local
        self.entity_name = "PGNIG Gas Invoice Sensor " + meter_id + " " + str(id_local)

    @property
    def unique_id(self) -> str | None:
        return "pgnig_invoice_sensor" + self.meter_id + "_" + str(self.id_local)

    @property
    def device_info(self):
        return {
            "identifiers": {("pgnig_gas_sensor", self.meter_id)},
            "name": f"PGNIG GAS METER ID {self.meter_id}",
            "manufacturer": "PGNIG",
            "model": self.meter_id,
            "via_device": None,
        }

    @property
    def name(self) -> str:
        return self.entity_name

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

    async def async_update(self):
        self._state = await self.hass.async_add_executor_job(self.invoices_summary)

    def invoices_summary(self):
        id_local = self.id_local

        def upcoming_payment_for_meter(x: InvoicesList):
            return id_local == x.id_pp and not x.is_paid

        def to_amount_to_pay(x: InvoicesList):
            return x.amount_to_pay

        next_payment_item = min(filter(upcoming_payment_for_meter, self.api.invoices().invoices_list),
                                key=lambda z: z.date,
                                default=InvoicesList(None, None, None, None, None, None, None, None,
                                                     None, None, None, None, None, None, None, None,
                                                     None, None, None, None, None, None,
                                                     None, None, None,
                                                     None, None, None, None,
                                                     None))

        sum_of_unpaid_invoices = sum(
            map(to_amount_to_pay, filter(upcoming_payment_for_meter, self.api.invoices().invoices_list)))

        return {"sumOfUnpaidInvoices": sum_of_unpaid_invoices,
                "nextPaymentDate": next_payment_item.paying_deadline_date,
                "nextPaymentWear": next_payment_item.wear, "nextPaymentWearKWH": next_payment_item.wear_kwh,
                "nextPaymentAmountToPay": next_payment_item.amount_to_pay}


class PgnigCostTrackingSensor(SensorEntity):
    def __init__(self, hass, api: PgnigApi, meter_id: string, id_local: int) -> None:
        self._attr_native_unit_of_measurement = "PLN/m³"
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._state: InvoicesList | None = None
        self.hass = hass
        self.api = api
        self.meter_id = meter_id
        self.id_local = id_local
        self.entity_name = "PGNIG Gas Cost Tracking Sensor " + meter_id + " " + str(id_local)

    @property
    def unique_id(self) -> str | None:
        return "pgnig_cost_tracking_sensor" + self.meter_id + "_" + str(self.id_local)

    @property
    def device_info(self):
        return {
            "identifiers": {("pgnig_gas_sensor", self.meter_id)},
            "name": f"PGNIG GAS METER ID {self.meter_id}",
            "manufacturer": "PGNIG",
            "model": self.meter_id,
            "via_device": None,
        }

    @property
    def name(self) -> str:
        return self.entity_name

    @property
    def state(self):
        if self._state is None:
            return None
        if self._state.gross_amount is None or self._state.wear is None:
            return None
        return self._state.gross_amount / self._state.wear

    @property
    def extra_state_attributes(self):
        attrs = dict()
        if self._state is not None:
            attrs["last_invoice_date"] = self._state.paying_deadline_date
            attrs["last_invoice_gross_amount"] = self._state.gross_amount
            attrs["last_invoice_wear"] = self._state.wear
            attrs["last_invoice_wear_KWH"] = self._state.wear_kwh
        return attrs

    async def async_update(self):
        self._state = await self.hass.async_add_executor_job(self.latest_price)

    def latest_price(self):
        id_local = self.id_local

        def upcoming_payment_for_meter(x: InvoicesList):
            return id_local == x.id_pp \
                and x.wear is not None \
                and x.wear != 0 \
                and x.gross_amount is not None \
                and x.gross_amount != 0

        return max(filter(upcoming_payment_for_meter, self.api.invoices().invoices_list),
                   key=lambda z: z.date,
                   default=InvoicesList(None, None, None, None, None, None, None, None,
                                        None, None, None, None, None, None, None,
                                        None, None, None, None, None, None,
                                        None, None, None, None,
                                        None, None, None, None,
                                        None))
