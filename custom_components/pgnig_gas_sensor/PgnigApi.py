import string

import requests

from .Invoices import invoices_from_dict
from .PgpList import (PpgList, ppg_list_from_dict)
from .PpgReadingForMeter import PpgReadingForMeter, ppg_reading_for_meter_from_dict

login_url = "https://ebok.pgnig.pl/auth/login?api-version=3.0"
devices_list_url = "https://ebok.pgnig.pl/crm/get-ppg-list?api-version=3.0"
readings_url = "https://ebok.pgnig.pl/crm/get-all-ppg-readings-for-meter?pageSize=10&pageNumber=1&api-version=3.0&idPpg="
invoices_url = "https://ebok.pgnig.pl/crm/get-invoices-v2?pageNumber=1&pageSize=12&api-version=3.0"
headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
}

class PgnigApi:

    def __init__(self, username, password) -> None:
        self.username = username
        self.password = password

    def meterList(self) -> PpgList:
        dictionary = requests.get(devices_list_url, headers={
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'AuthToken': self.login()
        }).json()

        return ppg_list_from_dict(dictionary)

    def readingForMeter(self, meter_id) -> PpgReadingForMeter:
        return ppg_reading_for_meter_from_dict(requests.get(readings_url + meter_id, headers={
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'AuthToken': (self.login())
        }).json())

    def invoices(self):
        return invoices_from_dict(requests.get(invoices_url, headers={
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'AuthToken': (self.login())
        }).json())

    def login(self) -> string:
        payload = {"identificator": self.username,
                   "accessPin": self.password,
                   "rememberLogin": "false",
                   "DeviceId": "123",  # TODO randomize it
                   "DeviceName": "Home Assistant: 99.9.999.99<br>",
                   "DeviceType": "Web"}
        return requests.request('POST', login_url, headers=headers, json=payload).json().get('Token')
