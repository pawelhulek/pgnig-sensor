import string

import requests
import re

from .Invoices import invoices_from_dict, Invoices
from .PgpList import (PpgList, ppg_list_from_dict)
from .PpgReadingForMeter import PpgReadingForMeter, ppg_reading_for_meter_from_dict

login_url = "https://ebok.myorlen.pl/auth/login?api-version=3.0"
devices_list_url = "https://ebok.myorlen.pl/crm/get-ppg-list?api-version=3.0"
readings_url = "https://ebok.myorlen.pl/crm/get-all-ppg-readings-for-meter?pageSize=10&pageNumber=1&api-version=3.0&idPpg="
invoices_url = "https://ebok.myorlen.pl/crm/get-invoices-v2?pageNumber=1&pageSize=12&api-version=3.0"
headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
}


class PgnigApi:

    def __init__(self, username, password) -> None:
        self.username = username
        self.password = password

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
        init_url = 'https://ebok.myorlen.pl/auth/oid/init-login?api-version=3.0'

        session = requests.Session()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8'
        }
        init_data = {
            "DeviceId": "a908313085dd4f16deaa4c15897e755e",
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
