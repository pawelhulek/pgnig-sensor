import logging

from .Invoices import invoices_from_dict, Invoices
from .PgpList import (PpgList, ppg_list_from_dict)
from .PpgReadingForMeter import PpgReadingForMeter, ppg_reading_for_meter_from_dict
from .auth import AuthRegistry
from .const import DEFAULT_AUTH_METHOD

_LOGGER = logging.getLogger(__name__)

devices_list_url = "https://ebok.myorlen.pl/crm/get-ppg-list?api-version=3.0"
readings_url = "https://ebok.myorlen.pl/crm/get-all-ppg-readings-for-meter?pageSize=10&pageNumber=1&api-version=3.0&idPpg="
invoices_url = "https://ebok.myorlen.pl/crm/get-invoices-v2?pageNumber=1&pageSize=12&api-version=3.0"


class PgnigApi:

    def __init__(self, username, password, auth_method=DEFAULT_AUTH_METHOD) -> None:
        self.username = username
        self.password = password
        auth_class = AuthRegistry.get(auth_method)
        if auth_class is None:
            raise ValueError(f"Unknown auth method: {auth_method}")
        self._auth = auth_class(username, password)

    def _api_headers(self, token):
        return {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'AuthToken': token,
        }

    def meterList(self) -> PpgList:
        token = self.login()
        if not token:
            raise RuntimeError("Login failed - no token received")
        resp = self._auth.session.get(devices_list_url, headers=self._api_headers(token))
        if not resp.ok:
            raise RuntimeError(f"Meter list failed with status {resp.status_code}: {resp.text[:200]}")
        return ppg_list_from_dict(resp.json())

    def readingForMeter(self, meter_id) -> PpgReadingForMeter:
        token = self.login()
        if not token:
            raise RuntimeError("Login failed - no token received")
        resp = self._auth.session.get(readings_url + meter_id, headers=self._api_headers(token))
        if not resp.ok:
            raise RuntimeError(f"Reading failed with status {resp.status_code}: {resp.text[:200]}")
        return ppg_reading_for_meter_from_dict(resp.json())

    def invoices(self) -> Invoices:
        token = self.login()
        if not token:
            raise RuntimeError("Login failed - no token received")
        resp = self._auth.session.get(invoices_url, headers=self._api_headers(token))
        if not resp.ok:
            raise RuntimeError(f"Invoices failed with status {resp.status_code}: {resp.text[:200]}")
        return invoices_from_dict(resp.json())

    def login(self) -> str:
        return self._auth.login()
