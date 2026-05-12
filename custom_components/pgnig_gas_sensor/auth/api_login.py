"""Legacy API login strategy for Orlen EBOK."""
import requests

from . import AuthMethod, AuthMethodInfo, AuthRegistry, device_id

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
        return requests.request('POST', login_url, headers=headers, json=payload).json().get('Token')
