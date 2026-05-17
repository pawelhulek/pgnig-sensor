"""OrlenID OID login strategy for Orlen EBOK."""
import logging
import re

import requests

from . import AuthMethod, AuthMethodInfo, AuthRegistry, device_id

_LOGGER = logging.getLogger(__name__)


class InvalidAuthError(Exception):
    """Raised when OrlenID rejects the supplied credentials."""


@AuthRegistry.register
class OrlenIDAuth(AuthMethod):
    def __init__(self, username, password) -> None:
        self.username = username
        self.password = password

    @property
    def info(self) -> AuthMethodInfo:
        return AuthMethodInfo(
            id="orlen_id",
            name="OrlenID",
            description="OrlenID OID login"
        )

    def login(self) -> str:
        init_url = 'https://ebok.myorlen.pl/auth/oid/init-login?api-version=3.0'

        init_device_id = device_id(self.username)
        session = requests.Session()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8'
        }
        init_data = {
            "DeviceId": init_device_id,
            "DeviceType": "Web",
            "DeviceName": "HomeAssistant wersja: 0.1",
            "LightweightRedirectUrl": "https://ebok.myorlen.pl/?show=modal",
            "FinalizeRegistrationRedirectUrl": "https://ebok.myorlen.pl/aktywuj-oid/"
        }

        response_init = session.post(
            init_url, json=init_data, headers={'Content-Type': 'application/json'}, timeout=30
        )
        if response_init.status_code != 200:
            raise RuntimeError(
                f"OrlenID init-login failed (HTTP {response_init.status_code}): {response_init.text[:200]}"
            )
        redirect_url = response_init.json().get('RedirectUrl')
        if not redirect_url:
            raise RuntimeError(f"OrlenID init-login missing RedirectUrl: {response_init.text[:200]}")

        response_page = session.get(redirect_url, headers=headers, timeout=30)
        match = re.search(r'action="([^"]+)"', response_page.text)
        if not match:
            raise RuntimeError("OrlenID login page missing form action — login flow may have changed")

        post_url = match.group(1).replace('&amp;', '&')
        payload = {
            'username': self.username,
            'password': self.password,
            'credentialId': ''
        }
        final_response = session.post(post_url, data=payload, headers=headers, timeout=30)
        _LOGGER.debug("OrlenID final URL=%s status=%s", final_response.url, final_response.status_code)

        if "https://ebok.myorlen.pl/home" not in final_response.url:
            raise InvalidAuthError(
                "OrlenID rejected credentials — username or password is incorrect"
            )

        auth_token_url = f'https://ebok.myorlen.pl/auth/get-auth-token?deviceId={init_data["DeviceId"]}&api-version=3.0'
        headers.update({'Referer': 'https://ebok.myorlen.pl/'})
        res_auth = session.get(auth_token_url, headers=headers, timeout=30)
        if res_auth.status_code != 200:
            raise RuntimeError(
                f"OrlenID get-auth-token failed (HTTP {res_auth.status_code}): {res_auth.text[:200]}"
            )

        token = res_auth.json().get('Token')
        if not token:
            raise RuntimeError(f"OrlenID get-auth-token missing Token: {res_auth.text[:200]}")
        return token
