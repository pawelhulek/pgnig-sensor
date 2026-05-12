import string

import requests

from .Invoices import invoices_from_dict, Invoices
from .PgpList import (PpgList, ppg_list_from_dict)
from .PpgReadingForMeter import PpgReadingForMeter, ppg_reading_for_meter_from_dict
from .auth import AuthRegistry
from .const import DEFAULT_AUTH_METHOD

login_url = "https://ebok.myorlen.pl/auth/login?api-version=3.0"
devices_list_url = "https://ebok.myorlen.pl/crm/get-ppg-list?api-version=3.0"
readings_url = "https://ebok.myorlen.pl/crm/get-all-ppg-readings-for-meter?pageSize=10&pageNumber=1&api-version=3.0&idPpg="
invoices_url = "https://ebok.myorlen.pl/crm/get-invoices-v2?pageNumber=1&pageSize=12&api-version=3.0"
headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
}


class PgnigApi:

    def __init__(self, username, password, auth_method=DEFAULT_AUTH_METHOD) -> None:
        self.username = username
        self.password = password
        auth_class = AuthRegistry.get(auth_method)
        if auth_class is None:
            raise ValueError(f"Unknown auth method: {auth_method}")
        self._auth = auth_class(username, password)

    def meterList(self) -> PpgList:
        return ppg_list_from_dict(requests.get(devices_list_url, headers={
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'AuthToken': self.login()
        }).json())

    def readingForMeter(self, meter_id) -> PpgReadingForMeter:
        return ppg_reading_for_meter_from_dict(requests.get(readings_url + meter_id, headers={
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'AuthToken': (self.login())
        }).json())

    def invoices(self) -> Invoices:
        return invoices_from_dict(requests.get(invoices_url, headers={
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'AuthToken': (self.login())
        }).json())

    def login(self) -> string:
        return self._auth.login()
