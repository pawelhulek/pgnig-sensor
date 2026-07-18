import logging
import threading

import requests

from .Invoices import invoices_from_dict, Invoices
from .PgpList import PpgList, ppg_list_from_dict
from .PpgReadingForMeter import PpgReadingForMeter, ppg_reading_for_meter_from_dict
from .auth import AuthRegistry
from .auth.exceptions import SessionExpiredError
from .auth.orlen_id import OrlenIDAuth
from .const import AUTH_METHOD_ORLEN_ID, DEFAULT_AUTH_METHOD

_LOGGER = logging.getLogger(__name__)

devices_list_url = "https://ebok.myorlen.pl/crm/get-ppg-list?api-version=3.0"
readings_url = (
    "https://ebok.myorlen.pl/crm/get-all-ppg-readings-for-meter"
    "?pageSize=10&pageNumber=1&api-version=3.0&idPpg="
)
invoices_url = (
    "https://ebok.myorlen.pl/crm/get-invoices-v2"
    "?pageNumber=1&pageSize=12&api-version=3.0"
)


class PgnigApi:
    def __init__(
        self,
        username,
        password,
        auth_method=DEFAULT_AUTH_METHOD,
        session_data=None,
    ) -> None:
        self.username = username
        self.password = password
        auth_class = AuthRegistry.get(auth_method)
        if auth_class is None:
            raise ValueError(f"Unknown auth method: {auth_method}")
        self._auth_method = auth_method
        if auth_method == AUTH_METHOD_ORLEN_ID:
            self._auth = auth_class(username, password, session_data=session_data)
        else:
            self._auth = auth_class(username, password)
        self._login_lock = threading.Lock()

    def _api_headers(self, token):
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "AuthToken": token,
        }

    def invalidate_token(self) -> None:
        self._auth.invalidate_token()

    def refresh_auth_token(self) -> str:
        """Refresh EBOK API token using the current HTTP session (no MFA)."""
        with self._login_lock:
            if self._auth_method == AUTH_METHOD_ORLEN_ID and isinstance(
                self._auth, OrlenIDAuth
            ):
                self.invalidate_token()
                token = self._auth._try_restore_session_token()
                if not token:
                    raise SessionExpiredError(
                        "OrlenID session expired; re-authenticate in Home Assistant"
                    )
                return token
            self.invalidate_token()
            return self._auth.login()

    def _get_authenticated(self, url: str, operation: str) -> requests.Response:
        last_response = None
        for attempt in range(2):
            if attempt > 0:
                _LOGGER.debug(
                    "%s returned 401, invalidating token and retrying", operation
                )
                self.invalidate_token()

            token = self.login(allow_interactive=False)
            if not token:
                raise RuntimeError("Login failed - no token received")

            resp = self._auth.session.get(
                url, headers=self._api_headers(token), timeout=30
            )
            if resp.status_code == 401 and attempt == 0:
                last_response = resp
                continue
            if not resp.ok:
                raise RuntimeError(
                    f"{operation} failed with status {resp.status_code}: {resp.text[:200]}"
                )
            return resp

        status = last_response.status_code if last_response else 401
        body = last_response.text[:200] if last_response else ""
        raise RuntimeError(f"{operation} failed with status {status}: {body}")

    def meterList(self) -> PpgList:
        resp = self._get_authenticated(devices_list_url, "Meter list")
        return ppg_list_from_dict(resp.json())

    def readingForMeter(self, meter_id) -> PpgReadingForMeter:
        resp = self._get_authenticated(readings_url + meter_id, "Reading")
        return ppg_reading_for_meter_from_dict(resp.json())

    def invoices(self) -> Invoices:
        resp = self._get_authenticated(invoices_url, "Invoices")
        return invoices_from_dict(resp.json())

    def login(self, *, allow_interactive: bool = False) -> str:
        with self._login_lock:
            _LOGGER.debug(
                "PgnigApi.login() delegating to %s", type(self._auth).__name__
            )
            if self._auth_method == AUTH_METHOD_ORLEN_ID and isinstance(
                self._auth, OrlenIDAuth
            ):
                return self._auth.login(allow_interactive=allow_interactive)
            return self._auth.login()

    def export_orlen_session(self) -> dict | None:
        if self._auth_method != AUTH_METHOD_ORLEN_ID or not isinstance(
            self._auth, OrlenIDAuth
        ):
            return None
        return self._auth.export_session()

    def complete_mfa(self, pending: dict, code: str) -> str:
        if self._auth_method != AUTH_METHOD_ORLEN_ID:
            raise ValueError("MFA is only supported for OrlenID authentication")
        if not isinstance(self._auth, OrlenIDAuth):
            raise ValueError("OrlenID auth handler is not active")
        return self._auth.complete_mfa(pending, code)
