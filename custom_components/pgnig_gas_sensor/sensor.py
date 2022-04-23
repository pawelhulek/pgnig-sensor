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
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, VOLUME_CUBIC_METERS
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
            [PgnigSensor(hass, api, meter_id)], update_before_add=True)


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
        meter_id = x.meter_number
        async_add_entities(
            [PgnigSensor(hass, api, meter_id), PgnigInvoiceSensor(hass, api, meter_id)], update_before_add=True)


class PgnigSensor(SensorEntity):
    def __init__(self, hass, api: PgnigApi, meter_id: string) -> None:
        self._attr_native_unit_of_measurement = VOLUME_CUBIC_METERS
        self._attr_device_class = SensorDeviceClass.GAS
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._state: MeterReading | None = None
        self.hass = hass
        self.api = api
        self.meter_id = meter_id
        self.entity_name = "PGNIG Gas Sensor " + meter_id

    @property
    def unique_id(self) -> str | None:
        return "pgnig_sensor" + self.meter_id

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
            attrs["wear_unit_of_measurment"] = VOLUME_CUBIC_METERS
        return attrs

    async def async_update(self):
        latest_meter_reading: MeterReading = await self.hass.async_add_executor_job(self.latestMeterReading)
        self._state = latest_meter_reading

    def latestMeterReading(self):
        return max(self.api.readingForMeter(self.meter_id).meter_readings,
                   key=lambda z: z.value)


class PgnigInvoiceSensor(SensorEntity):
    def __init__(self, hass, api: PgnigApi, meter_id: string) -> None:
        self._attr_native_unit_of_measurement = "PLN"
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._state: MeterReading | None = None
        self.hass = hass
        self.api = api
        self.meter_id = meter_id
        self.entity_name = "PGNIG Gas Invoice Sensor " + meter_id

    @property
    def unique_id(self) -> str | None:
        return "pgnig_invoice_sensor" + self.meter_id

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
            attrs["next_payment_wear"] = self._state.get("nextPaymentWear")
            attrs["next_payment_wear_KWH"] = self._state.get("nextPaymentWearKWH")
        return attrs

    async def async_update(self):
        self._state = await self.hass.async_add_executor_job(self.invoicesSummary)

    def invoicesSummary(self):
        def closestPaymentDate(x: InvoicesList):
            return x.status == 'NotPaid'

        def toAmountToPay(x: InvoicesList):
            return x.amount_to_pay

        nextPaymentItem = min(filter(closestPaymentDate, self.api.invoices().invoices_list), key=lambda z: z)
        sumOfUnpaidInvoices = sum(map(toAmountToPay, self.api.invoices().invoices_list))

        return {"sumOfUnpaidInvoices": sumOfUnpaidInvoices, "nextPaymentDate": nextPaymentItem.paying_deadline_date,
                "nextPaymentWear": nextPaymentItem.wear, "nextPaymentWearKWH": nextPaymentItem.wear_kwh}

    def sumOfUnpaidInvoices(self):

        return sum(map(toAmountToPay, self.api.invoices().invoices_list))
