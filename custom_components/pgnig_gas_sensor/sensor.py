"""Platform for sensor integration."""
from __future__ import annotations

import logging
import string
from datetime import timedelta

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.sensor import SensorEntity, PLATFORM_SCHEMA, SensorStateClass, SensorDeviceClass
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, VOLUME_CUBIC_METERS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util import Throttle

from .PgnigApi import PgnigApi

_LOGGER = logging.getLogger(__name__)
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
})


def setup_platform(
        hass: HomeAssistant,
        config: ConfigType,
        add_entities: AddEntitiesCallback,
        discovery_info: DiscoveryInfoType | None = None
) -> None:
    """Set up the sensor platform."""
    api = PgnigApi(config.get(CONF_USERNAME), config.get(CONF_PASSWORD))
    pgps = api.meterList()

    for x in pgps.ppg_list:
        meter_id = x.meter_number
        add_entities(
            [PgnigSensor(hass, api, meter_id)])


class PgnigSensor(SensorEntity):
    """Representation of a Sensor."""

    def __init__(self, hass, api: PgnigApi, meter_id: string) -> None:
        self._attr_native_unit_of_measurement = VOLUME_CUBIC_METERS
        self._attr_device_class = SensorDeviceClass.GAS
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._state = None
        self.hass = hass
        self.api = api
        self.meter_id = meter_id
        self.entity_name = "PGNIG Gas Sensor " + meter_id
        self.update = Throttle(timedelta(hours=8))(self._update)

    @property
    def unique_id(self) -> str | None:
        return "pgnig_sensor" + self.meter_id

    @property
    def name(self) -> str:
        return self.entity_name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state.value

    @property
    def extra_state_attributes(self):
        attrs = dict()
        attrs["wear"] = self._state.wear
        attrs["wear_unit_of_measurment"] = VOLUME_CUBIC_METERS
        return attrs

    def _update(self) -> None:
        """Fetch new state data for the sensor.
        This is the only method that should fetch new data for Home Assistant.
        """
        self._state = max(self.api.readingForMeter(self.meter_id).meter_readings, key=lambda z: z.value)
