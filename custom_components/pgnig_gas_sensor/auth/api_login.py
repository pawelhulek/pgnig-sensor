"""Legacy API login strategy for Orlen EBOK."""
import logging

import requests

from . import AuthMethod, AuthMethodInfo, AuthRegistry, device_id

_LOGGER = logging.getLogger(__name__)

login_url = "https://ebok.myorlen.pl/auth/login?api-version=3.0"
headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
}


@AuthRegistry.register
class ApiLoginAuth(AuthMethod):
    def __init__(self, username, password) -> None:
        self.username = username
        self.password = password

    @property
    def info(self) -> AuthMethodInfo:
        return AuthMethodInfo(
            id="api_login",
            name="API Login (legacy)",
            description="Legacy username/password login via API"
        )

    def login(self) -> str:
        payload = {"identificator": self.username,
                   "accessPin": self.password,
                   "rememberLogin": "false",
                   "DeviceId": device_id(self.username),
                   "DeviceName": "Home Assistant: 99.9.999.99<br>",
                   "DeviceType": "Web"}
        response = requests.post(login_url, headers=headers, json=payload, timeout=30)
        _LOGGER.debug("Legacy login HTTP %s — body: %s", response.status_code, response.text[:500])
        try:
            data = response.json()
        except ValueError as err:
            raise RuntimeError(
                f"Login returned non-JSON (HTTP {response.status_code}): {response.text[:200]}"
            ) from err

        token = data.get("Token")
        if not token:
            raise RuntimeError(
                f"Login failed (HTTP {response.status_code}): no Token in response — {data}"
            )
        return token
