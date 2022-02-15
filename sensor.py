"""Platform for sensor integration."""
from __future__ import annotations

import string

import homeassistant.helpers.config_validation as cv
import requests
import voluptuous as vol
from homeassistant.components.sensor import SensorEntity, PLATFORM_SCHEMA, SensorStateClass, SensorDeviceClass
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, ENERGY_KILO_WATT_HOUR
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
})

login_url = "https://ebok.pgnig.pl/auth/login?api-version=3.0"
url_devices_list = "https://ebok.pgnig.pl/crm/get-ppg-list?api-version=3.0"
data_url = "https://ebok.pgnig.pl/crm/get-all-ppg-readings-for-meter?pageSize=1&pageNumber=1&api-version=3.0&idPpg="

headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
}


def setup_platform(
        hass: HomeAssistant,
        config: ConfigType,
        add_entities: AddEntitiesCallback,
        discovery_info: DiscoveryInfoType | None = None
) -> None:
    """Set up the sensor platform."""
    authToken, response = login(CONF_USERNAME, CONF_PASSWORD)
    response_json = response.json()

    responseDevices = requests.get(url_devices_list, headers={
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'AuthToken': authToken
    })
    pgps = responseDevices.json().get("PpgList")

    for x in pgps:
        meterId = x.get('MeterNumber')
        add_entities(
            [PgnigSensor(hass, config, meterId)])


def login(username, password):
    payload = {"identificator": username,
               "accessPin": password,
               "rememberLogin": "false",
               "DeviceId": "123",  # TODO randomize it
               "DeviceName": "Home Assistant: 99.9.999.99<br>",
               "DeviceType": "Web"}
    response = requests.post(login_url, headers=headers, json=payload)
    return response.get('Token')


class PgnigSensor(SensorEntity):
    """Representation of a Sensor."""

    def __init__(self, hass, config: dict, meter_id: string) -> None:
        self._attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._state = None
        self.hass = hass
        self.username = config.get(CONF_USERNAME)
        self.password = config.get(CONF_PASSWORD)
        self.entity_name = "pgnig_gas_sensor_" + meter_id
        self.meter_id = meter_id

    @property
    def name(self) -> str:
        return self.entity_name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    def update(self) -> None:
        """Fetch new state data for the sensor.
        This is the only method that should fetch new data for Home Assistant.
        """
        self._state = self.getData()

    def getData(self) -> object:
        token = login(self.username, self.password)

        response = requests.get(data_url + self.meter_id, headers={
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'AuthToken': token
        })
        return response.json().get('MeterReadings')[0].get('Value')
