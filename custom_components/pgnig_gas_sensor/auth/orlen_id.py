"""OrlenID OID login strategy for Orlen EBOK."""
import re

import requests

from . import AuthMethod, AuthMethodInfo, AuthRegistry, device_id


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

        response_init = session.post(init_url, json=init_data, headers={'Content-Type': 'application/json'})
        redirect_url = response_init.json().get('RedirectUrl')
        response_page = session.get(redirect_url, headers=headers)
        match = re.search(r'action="([^"]+)"', response_page.text)

        if match:
            post_url = match.group(1).replace('&amp;', '&')
            payload = {
                'username': self.username,
                'password': self.password,
                'credentialId': ''
            }
            final_response = session.post(post_url, data=payload, headers=headers)

            if "https://ebok.myorlen.pl/home" in final_response.url:
                auth_token_url = f'https://ebok.myorlen.pl/auth/get-auth-token?deviceId={init_data["DeviceId"]}&api-version=3.0'
                headers.update({'Referer': 'https://ebok.myorlen.pl/'})
                res_auth = session.get(auth_token_url, headers=headers)
                if res_auth.status_code == 200:
                    return res_auth.json().get('Token')
        return ""
