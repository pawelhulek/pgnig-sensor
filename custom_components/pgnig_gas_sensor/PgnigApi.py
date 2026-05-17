import logging
import string
import threading

import requests

from .Invoices import invoices_from_dict, Invoices
from .PgpList import (PpgList, ppg_list_from_dict)
from .PpgReadingForMeter import PpgReadingForMeter, ppg_reading_for_meter_from_dict
from .auth import AuthRegistry
from .const import DEFAULT_AUTH_METHOD

_LOGGER = logging.getLogger(__name__)

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
        self._token: str | None = None
        self._token_lock = threading.Lock()

    def meterList(self) -> PpgList:
        response = requests.get(devices_list_url, headers={
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'AuthToken': self.login()
        }, timeout=30)
        _LOGGER.debug("meterList: HTTP %s body=%s", response.status_code, response.text[:500])
        data = response.json()
        if not isinstance(data, dict) or "PpgList" not in data:
            raise RuntimeError(
                f"meterList unexpected response (HTTP {response.status_code}): {response.text[:200]}"
            )
        return ppg_list_from_dict(data)

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
        with self._token_lock:
            if self._token:
                return self._token
            self._token = self._auth.login()
            return self._token

    def invalidate_token(self) -> None:
        with self._token_lock:
            self._token = None
