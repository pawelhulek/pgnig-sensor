"""OrlenID OID login strategy for Orlen EBOK."""
import logging
import re

import requests

from . import AuthMethod, AuthMethodInfo, AuthRegistry, device_id

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://ebok.myorlen.pl"

browser_headers = {
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
class OrlenIDAuth(AuthMethod):
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
            id="orlen_id",
            name="OrlenID",
            description="OrlenID OID login"
        )

    def _init_session(self):
        _LOGGER.debug("Initializing session with GET %s", BASE_URL)
        resp = self._session.get(BASE_URL, timeout=30)
        _LOGGER.debug("Session init status: %s, cookies: %s", resp.status_code, dict(self._session.cookies))

    def login(self) -> str:
        if self._cached_token:
            _LOGGER.debug("Using cached auth token")
            return self._cached_token

        _LOGGER.debug("Starting OrlenID login flow for user %s", self.username)
        self._init_session()

        init_url = f'{BASE_URL}/auth/oid/init-login?api-version=3.0'
        init_data = {
            "DeviceId": self._device_id,
            "DeviceType": "Web",
            "DeviceName": "HomeAssistant wersja: 0.1",
            "LightweightRedirectUrl": f"{BASE_URL}/?show=modal",
            "FinalizeRegistrationRedirectUrl": f"{BASE_URL}/aktywuj-oid/"
        }

        response_init = self._session.post(init_url, json=init_data, timeout=30)
        _LOGGER.debug("Init login response: status=%s, body=%s", response_init.status_code, response_init.text[:300])
        redirect_url = response_init.json().get('RedirectUrl')
        _LOGGER.debug("Redirect URL received: %s", redirect_url)

        response_page = self._session.get(redirect_url, timeout=30)
        match = re.search(r'action="([^"]+)"', response_page.text)
        _LOGGER.debug("Login page fetched: status=%s, form action found=%s", response_page.status_code, match is not None)

        if match:
            post_url = match.group(1).replace('&amp;', '&')
            _LOGGER.debug("Posting credentials to %s", post_url)
            payload = {
                'username': self.username,
                'password': self.password,
                'credentialId': ''
            }
            final_response = self._session.post(post_url, data=payload, headers={
                'Referer': redirect_url,
                'Content-Type': 'application/x-www-form-urlencoded',
            }, timeout=30)
            _LOGGER.debug("Credentials posted: final_url=%s, status=%s", final_response.url, final_response.status_code)

            if f"{BASE_URL}/home" in final_response.url:
                _LOGGER.debug("Login successful, fetching auth token")
                auth_token_url = f'{BASE_URL}/auth/get-auth-token?deviceId={self._device_id}&api-version=3.0'
                res_auth = self._session.get(auth_token_url, headers={
                    'Accept': 'application/json, text/plain, */*',
                    'Referer': f'{BASE_URL}/home',
                }, timeout=30)
                _LOGGER.debug("Auth token response: status=%s", res_auth.status_code)
                if res_auth.status_code == 200:
                    self._cached_token = res_auth.json().get('Token', "")
                    token_preview = self._cached_token[:20] + "..." if self._cached_token else "empty"
                    _LOGGER.debug("Token obtained: %s", token_preview)
                    return self._cached_token
                else:
                    _LOGGER.debug("Auth token request failed: status=%s, body=%s", res_auth.status_code, res_auth.text[:200])
            else:
                _LOGGER.debug("Login failed: redirect ended at %s instead of %s/home", final_response.url, BASE_URL)
        else:
            _LOGGER.debug("Login form not found in page at %s", redirect_url)
        return ""
