"""OrlenID OID login strategy for Orlen EBOK."""
from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urljoin

import requests
from requests.cookies import cookiejar_from_dict

from . import AuthMethod, AuthMethodInfo, AuthRegistry, device_id
from .exceptions import (
    AccountActionRequiredError,
    InvalidAuthError,
    MfaFailedError,
    MfaRequired,
    MfaSessionExpiredError,
    SessionExpiredError,
    UnexpectedLoginPageError,
)
from .keycloak import (
    LOGIN_FORM_FIELD_NAMES,
    MFA_FIELD_CANDIDATES,
    PageKind,
    build_mfa_payload,
    classify_page,
    describe_page,
    detect_mfa_field,
    extract_error_message,
    extract_form,
    find_mfa_form,
    find_skip_action,
    is_keycloak_url,
    is_login_page,
    iter_forms,
    normalize_otp_code,
    required_action_description,
)

_LOGGER = logging.getLogger(__name__)

# Backwards compatible aliases and re-exports; parsing now lives in keycloak.py.
__all__ = ["OrlenIDAuth", "LOGIN_FORM_FIELD_NAMES", "MFA_FIELD_CANDIDATES"]
_iter_forms = iter_forms
_extract_form = extract_form
_find_mfa_form = find_mfa_form
_detect_mfa_field = detect_mfa_field
_is_keycloak_url = is_keycloak_url
_is_login_page = is_login_page
_normalize_otp_code = normalize_otp_code
_build_mfa_payload = build_mfa_payload

BASE_URL = "https://ebok.myorlen.pl"

browser_headers = {
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Content-Type": "application/json",
    "Origin": BASE_URL,
    "Pragma": "no-cache",
    "Referer": f"{BASE_URL}/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
    ),
    "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}

FORM_URLENCODED_HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}



def _find_credentials_form(html: str, base_url: str) -> tuple[str, dict[str, str]]:
    """Locate the username/password form and its hidden fields on the SSO page.

    Falls back to the first form action so unfamiliar themes still work.
    """
    forms = iter_forms(html, base_url)
    for action, fields in forms:
        if "username" in fields and "password" in fields:
            hidden = {k: v for k, v in fields.items() if k not in {"username", "password"}}
            return action, hidden
    if forms:
        return forms[0][0], {}
    match = re.search(r'action="([^"]+)"', html)
    return (match.group(1).replace("&amp;", "&"), {}) if match else ("", {})


def _looks_like_mfa_challenge(response: requests.Response) -> bool:
    if f"{BASE_URL}/home" in response.url:
        return False
    return classify_page(response.url, response.text) is PageKind.MFA


def _cookies_for_storage(jar: requests.cookies.RequestsCookieJar) -> list[dict[str, str]]:
    """Serialize session cookies with domain/path for MFA step restore."""
    cookies: list[dict[str, str]] = []
    internal = getattr(jar, "_cookies", None)
    if internal:
        for domain, paths in internal.items():
            for path, names in paths.items():
                for cookie in names.values():
                    cookies.append(
                        {
                            "name": cookie.name,
                            "value": cookie.value,
                            "domain": cookie.domain or domain or "",
                            "path": cookie.path or path or "/",
                        }
                    )
        return cookies

    for name, value in jar.get_dict().items():
        cookies.append(
            {"name": name, "value": value, "domain": "", "path": "/"}
        )
    return cookies


def _restore_cookies(session: requests.Session, cookies: list[dict[str, str]]) -> None:
    session.cookies.clear()
    for cookie in cookies:
        set_kwargs: dict[str, str] = {"path": cookie.get("path") or "/"}
        domain = (cookie.get("domain") or "").strip()
        if domain:
            set_kwargs["domain"] = domain
        session.cookies.set(
            cookie["name"],
            cookie["value"],
            **set_kwargs,
        )



@AuthRegistry.register
class OrlenIDAuth(AuthMethod):
    def __init__(
        self,
        username: str,
        password: str,
        session_data: dict[str, Any] | None = None,
    ) -> None:
        self.username = username
        self.password = password
        self._device_id = device_id(username)
        self._session = requests.Session()
        self._session.headers.update(browser_headers)
        self._cached_token: str = ""
        if session_data:
            self._device_id = session_data.get("device_id", self._device_id)
            cookies = session_data.get("cookies", [])
            if isinstance(cookies, dict):
                cookiejar_from_dict(cookies, self._session.cookies)
            elif cookies:
                _restore_cookies(self._session, cookies)
            # Persisted token is not restored — it expires independently of OIDC cookies.
        self._session.cookies.set("pgnig-ebok-device-token", self._device_id)

    @property
    def session(self) -> requests.Session:
        return self._session

    @property
    def info(self) -> AuthMethodInfo:
        return AuthMethodInfo(
            id="orlen_id",
            name="OrlenID",
            description="OrlenID OID login",
        )

    def _init_session(self) -> None:
        _LOGGER.debug("Initializing session with GET %s", BASE_URL)
        resp = self._session.get(BASE_URL, timeout=30)
        _LOGGER.debug(
            "Session init status: %s, cookies: %s",
            resp.status_code,
            dict(self._session.cookies),
        )

    def _fetch_auth_token(self) -> str:
        auth_token_url = (
            f"{BASE_URL}/auth/get-auth-token?deviceId={self._device_id}&api-version=3.0"
        )
        res_auth = self._session.get(
            auth_token_url,
            headers={
                "Accept": "application/json, text/plain, */*",
                "Referer": f"{BASE_URL}/home",
            },
            timeout=30,
        )
        _LOGGER.debug("Auth token response: status=%s", res_auth.status_code)
        if res_auth.status_code != 200:
            raise RuntimeError(
                f"Auth token request failed with status {res_auth.status_code}: "
                f"{res_auth.text[:200]}"
            )
        token = res_auth.json().get("Token", "")
        if not token:
            raise RuntimeError("Auth token response missing Token field")
        self._cached_token = token
        return token

    def _handle_required_action(self, response: requests.Response) -> requests.Response:
        """Skip a Keycloak required-action screen, or report it to the user."""
        description = required_action_description(response.text, response.url)
        _LOGGER.warning(
            "OrlenID requires an account action (%s) at %s", description, response.url
        )
        skipped = self._try_skip_required_action(response)
        if skipped is not None:
            return skipped
        raise AccountActionRequiredError(
            f"OrlenID requires you to complete {description} before logging in. "
            f"Open {BASE_URL} in a browser, finish that step for your account, "
            "then retry the login here."
        )

    def _try_skip_required_action(
        self, response: requests.Response
    ) -> requests.Response | None:
        """Follow a 'skip / later' control if OrlenID offers one."""
        skip = find_skip_action(response.text, response.url)
        if skip is None:
            return None

        _LOGGER.info("Trying to skip OrlenID required action via %s %s", skip.method, skip.url)
        if skip.method == "post":
            skipped = self._session.post(
                skip.url,
                data=skip.data or {},
                headers={
                    **FORM_URLENCODED_HEADERS,
                    "Referer": response.url,
                    "Origin": urljoin(skip.url, "/"),
                },
                timeout=30,
                allow_redirects=True,
            )
        else:
            skipped = self._session.get(
                skip.url,
                headers={"Referer": response.url},
                timeout=30,
                allow_redirects=True,
            )

        if required_action_description(skipped.text, skipped.url):
            _LOGGER.info("OrlenID required action could not be skipped")
            return None
        return skipped

    def _complete_oidc_session(self, response: requests.Response) -> str:
        """Finish OIDC login after password or MFA and fetch EBOK API token."""
        if _looks_like_mfa_challenge(response):
            raise MfaFailedError("Invalid or expired MFA code")

        if required_action_description(response.text, response.url):
            response = self._handle_required_action(response)

        if _is_keycloak_url(response.url):
            if _is_login_page(response.text):
                raise MfaSessionExpiredError(
                    "MFA session expired — log in again with username and password, "
                    "then enter the latest SMS code."
                )
            raise MfaFailedError(
                "Authentication did not complete; still on OrlenID login page"
            )

        if f"{BASE_URL}/home" not in response.url:
            _LOGGER.info(
                "OrlenID post-auth URL is %s; navigating to /home before token fetch",
                response.url,
            )
            response = self._session.get(
                f"{BASE_URL}/home",
                headers={"Referer": response.url},
                timeout=30,
                allow_redirects=True,
            )

        if _looks_like_mfa_challenge(response):
            raise MfaFailedError("Invalid or expired MFA code")

        if _is_keycloak_url(response.url):
            raise MfaFailedError(
                "Authentication did not complete; OrlenID redirected back to login"
            )

        return self._fetch_auth_token()

    def _build_pending_mfa(self, response: requests.Response) -> dict[str, Any]:
        action, fields, mfa_field = _find_mfa_form(response.text, response.url)
        if not action or not mfa_field:
            raise InvalidAuthError(
                "OrlenID rejected credentials or returned an unexpected login page"
            )
        _LOGGER.info(
            "OrlenID MFA required; post_url=%s field=%s hidden_fields=%s",
            action,
            mfa_field,
            list(fields.keys()),
        )
        return {
            "username": self.username,
            "password": self.password,
            "device_id": self._device_id,
            "cookies": _cookies_for_storage(self._session.cookies),
            "mfa_post_url": action,
            "mfa_form_fields": fields,
            "mfa_field_name": mfa_field,
            "mfa_referer": response.url,
        }

    @classmethod
    def from_pending(cls, pending: dict[str, Any]) -> OrlenIDAuth:
        auth = cls.__new__(cls)
        auth.username = pending["username"]
        auth.password = pending.get("password", "")
        auth._device_id = pending["device_id"]
        auth._cached_token = ""
        auth._session = requests.Session()
        auth._session.headers.update(browser_headers)
        cookies = pending.get("cookies", [])
        if isinstance(cookies, dict):
            auth._session.cookies = cookiejar_from_dict(cookies)
        else:
            _restore_cookies(auth._session, cookies)
        auth._session.cookies.set("pgnig-ebok-device-token", auth._device_id)
        return auth

    def complete_mfa(self, pending: dict[str, Any], code: str) -> str:
        """Submit SMS / OTP code and finish OrlenID login."""
        auth = self.from_pending(pending)
        post_url = pending["mfa_post_url"]
        field_name = pending["mfa_field_name"]
        otp_code = _normalize_otp_code(code)
        if not otp_code:
            raise MfaFailedError("MFA code is empty")

        payload = _build_mfa_payload(
            pending.get("mfa_form_fields", {}),
            field_name,
            otp_code,
        )

        _LOGGER.info(
            "Submitting OrlenID MFA to %s using field %s payload_keys=%s",
            post_url,
            field_name,
            sorted(payload.keys()),
        )
        response = auth._session.post(
            post_url,
            data=payload,
            headers={
                **FORM_URLENCODED_HEADERS,
                "Referer": pending.get("mfa_referer", post_url),
                "Origin": urljoin(post_url, "/"),
            },
            timeout=30,
            allow_redirects=True,
        )
        _LOGGER.info(
            "OrlenID MFA response: final_url=%s status=%s",
            response.url,
            response.status_code,
        )

        if _looks_like_mfa_challenge(response):
            refreshed = auth._build_pending_mfa(response)
            pending.update(refreshed)
            raise MfaFailedError(
                "Invalid MFA code — enter the latest SMS code without spaces."
            )

        try:
            token = auth._complete_oidc_session(response)
        except MfaSessionExpiredError:
            _LOGGER.warning(
                "OrlenID MFA session expired; user must restart login with password"
            )
            raise
        except MfaFailedError:
            _LOGGER.warning(
                "OrlenID MFA failed; response snippet: %s",
                response.text[:300].replace("\n", " "),
            )
            raise

        self._session = auth._session
        self._cached_token = token
        self._device_id = auth._device_id
        return token

    def export_session(self) -> dict[str, Any]:
        return {
            "device_id": self._device_id,
            "cookies": _cookies_for_storage(self._session.cookies),
            "token": self._cached_token,
        }

    def _try_restore_session_token(self) -> str | None:
        if not list(self._session.cookies.keys()):
            return None
        try:
            return self._fetch_auth_token()
        except RuntimeError:
            _LOGGER.debug("Stored OrlenID session invalid, attempting silent SSO refresh...")
            try:
                init_url = f"{BASE_URL}/auth/oid/init-login?api-version=3.0"
                init_data = {
                    "DeviceId": self._device_id,
                    "DeviceType": "Web",
                    "DeviceName": "HomeAssistant wersja: 0.1",
                    "LightweightRedirectUrl": f"{BASE_URL}/?show=modal",
                    "FinalizeRegistrationRedirectUrl": f"{BASE_URL}/aktywuj-oid/",
                }
                resp_init = self._session.post(init_url, json=init_data, timeout=30)
                if resp_init.ok and "RedirectUrl" in resp_init.json():
                    redirect_url = resp_init.json()["RedirectUrl"]
                    resp_sso = self._session.get(redirect_url, timeout=30, allow_redirects=True)
                    if f"{BASE_URL}/home" in resp_sso.url:
                        _LOGGER.debug("Silent SSO refresh successful")
                        return self._fetch_auth_token()
            except Exception as e:
                _LOGGER.debug("Silent SSO refresh failed: %s", e)
                
            self._cached_token = ""
            return None

    def invalidate_token(self) -> None:
        """Drop in-memory API token so the next login() fetches a fresh one."""
        _LOGGER.debug("Invalidating cached auth token")
        self._cached_token = ""

    def login(self, *, allow_interactive: bool = False) -> str:
        if self._cached_token:
            _LOGGER.debug("Using cached auth token")
            return self._cached_token

        restored = self._try_restore_session_token()
        if restored:
            return restored

        if not allow_interactive:
            raise SessionExpiredError(
                "OrlenID session expired; re-authenticate in Home Assistant"
            )

        _LOGGER.debug("Starting OrlenID login flow for user %s", self.username)
        self._init_session()

        init_url = f"{BASE_URL}/auth/oid/init-login?api-version=3.0"
        init_data = {
            "DeviceId": self._device_id,
            "DeviceType": "Web",
            "DeviceName": "HomeAssistant wersja: 0.1",
            "LightweightRedirectUrl": f"{BASE_URL}/?show=modal",
            "FinalizeRegistrationRedirectUrl": f"{BASE_URL}/aktywuj-oid/",
        }

        response_init = self._session.post(init_url, json=init_data, timeout=30)
        _LOGGER.debug(
            "Init login response: status=%s, body=%s",
            response_init.status_code,
            response_init.text[:300],
        )
        if not response_init.ok:
            raise RuntimeError(
                f"OrlenID init-login failed with status {response_init.status_code}"
            )

        redirect_url = response_init.json().get("RedirectUrl")
        if not redirect_url:
            raise RuntimeError("OrlenID init-login response missing RedirectUrl")

        response_page = self._session.get(redirect_url, timeout=30)
        post_url, form_fields = _find_credentials_form(
            response_page.text, response_page.url
        )
        _LOGGER.debug(
            "Login page fetched: status=%s, form action found=%s",
            response_page.status_code,
            bool(post_url),
        )
        if not post_url:
            raise RuntimeError("OrlenID login form not found on SSO page")

        _LOGGER.debug("Posting credentials to %s", post_url)
        final_response = self._session.post(
            post_url,
            data={
                **form_fields,
                "username": self.username,
                "password": self.password,
            },
            headers={
                **FORM_URLENCODED_HEADERS,
                "Referer": redirect_url,
                "Origin": urljoin(post_url, "/"),
            },
            timeout=30,
            allow_redirects=True,
        )
        _LOGGER.debug(
            "Credentials posted: final_url=%s, status=%s",
            final_response.url,
            final_response.status_code,
        )

        # The 2FA enrollment screen (CANCEL_2FA / "Pomiń") is handled generically
        # as a Keycloak required action - see _handle_required_action below.
        if f"{BASE_URL}/home" in final_response.url:
            return self._fetch_auth_token()

        page_kind = classify_page(final_response.url, final_response.text)
        _LOGGER.debug("Post-credentials page classified as %s", page_kind.value)

        if page_kind is PageKind.MFA:
            raise MfaRequired(self._build_pending_mfa(final_response))

        if page_kind is PageKind.REQUIRED_ACTION:
            final_response = self._handle_required_action(final_response)
            if f"{BASE_URL}/home" in final_response.url:
                return self._fetch_auth_token()
            page_kind = classify_page(final_response.url, final_response.text)
            if page_kind is PageKind.MFA:
                raise MfaRequired(self._build_pending_mfa(final_response))

        if page_kind is PageKind.LOGIN_REJECTED:
            raise InvalidAuthError(
                "OrlenID rejected the credentials: "
                f"{extract_error_message(final_response.text)}"
            )

        if page_kind is PageKind.LOGIN_FORM:
            raise InvalidAuthError(
                "OrlenID returned the login form again without completing login — "
                "the username or password is most likely incorrect."
            )

        if not _is_keycloak_url(final_response.url):
            try:
                return self._complete_oidc_session(final_response)
            except MfaFailedError:
                pass

        raise UnexpectedLoginPageError(
            "OrlenID login did not complete and the page is not recognised: "
            f"{describe_page(final_response.url, final_response.text)}. "
            "Please report this with debug logs enabled."
        )
