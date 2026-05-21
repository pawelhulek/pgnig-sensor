"""Legacy API login strategy for Orlen EBOK."""
import logging

import requests

from . import AuthMethod, AuthMethodInfo, AuthRegistry, device_id

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://ebok.myorlen.pl"
login_url = f"{BASE_URL}/auth/login?api-version=3.0"

browser_headers = {
    'Accept': 'application/json',
    'Accept-Language': 'pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7',
    'Cache-Control': 'no-cache',
    'Content-Type': 'application/json',
    'Origin': BASE_URL,
    'Pragma': 'no-cache',
    'Referer': f'{BASE_URL}/',
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36',
    'sec-ch-ua': '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"macOS"',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
}


@AuthRegistry.register
class ApiLoginAuth(AuthMethod):
    def __init__(self, username, password) -> None:
        self.username = username
        self.password = password
        self._device_id = device_id(username)
        self._session = requests.Session()
        self._session.headers.update(browser_headers)
        self._session.cookies.set("pgnig-ebok-device-token", self._device_id)
        self._cached_token: str = ""

    @property
    def session(self) -> requests.Session:
        return self._session

    @property
    def info(self) -> AuthMethodInfo:
        return AuthMethodInfo(
            id="api_login",
            name="API Login (legacy)",
            description="Legacy username/password login via API"
        )

    def _init_session(self):
        _LOGGER.debug("Initializing session with GET %s", BASE_URL)
        resp = self._session.get(BASE_URL, timeout=30)
        _LOGGER.debug("Session init status: %s, cookies: %s", resp.status_code, dict(self._session.cookies))

    def login(self) -> str:
        if self._cached_token:
            _LOGGER.debug("Using cached auth token")
            return self._cached_token

        self._init_session()

        payload = {"identificator": self.username,
                   "accessPin": self.password,
                   "rememberLogin": False,
                   "DeviceId": self._device_id,
                   "DeviceName": "Home Assistant",
                   "DeviceType": "Web"}
        response = self._session.post(login_url, json=payload, timeout=30)
        _LOGGER.debug("Login response status: %s, body: %s", response.status_code, response.text[:500])
        if not response.ok:
            raise RuntimeError(f"Login failed with status {response.status_code}: {response.text[:200]}")
        try:
            data = response.json()
        except ValueError as e:
            raise RuntimeError(
                f"Login returned non-JSON response (status {response.status_code}). "
                f"Headers: {dict(response.headers)}. "
                f"Body preview: {response.text[:500]}"
            ) from e
        token = data.get('Token')
        if not token:
            raise RuntimeError(f"Login response missing 'Token' field: {data}")
        self._cached_token = token
        return token
