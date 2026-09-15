"""Tests for OrlenIDAuth auth method with mocked HTTP."""
from unittest.mock import MagicMock, patch

import pytest
import requests

from custom_components.pgnig_gas_sensor.auth import AuthRegistry
from custom_components.pgnig_gas_sensor.auth.exceptions import InvalidAuthError, SessionExpiredError


def _mock_resp(json_data=None, status_code=200, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.ok = 200 <= status_code < 300
    resp.text = text
    if json_data is not None:
        resp.json.return_value = json_data
    resp.headers = {}
    return resp


@pytest.fixture
def auth():
    cls = AuthRegistry.get("orlen_id")
    return cls("oid_user@test.pl", "oid_pass")


def test_init_sets_session_and_cookies(auth):
    assert auth._session is not None
    assert isinstance(auth._session, requests.Session)
    assert auth._session.headers.get("User-Agent") is not None
    assert auth._session.cookies.get("pgnig-ebok-device-token")
    assert auth._cached_token == ""


def test_session_property(auth):
    assert auth.session is auth._session


def test_info(auth):
    info = auth.info
    assert info.id == "orlen_id"
    assert info.name == "OrlenID"


def test_login_returns_cached_token(auth):
    auth._cached_token = "cached-oid-token"
    with patch.object(auth, "_init_session") as mock_init:
        token = auth.login(allow_interactive=True)
        assert token == "cached-oid-token"
        mock_init.assert_not_called()


def test_login_full_flow_success(auth):
    with patch.object(auth, "_session") as mock_session, patch.object(
        auth, "_try_restore_session_token", return_value=None
    ):
        auth._device_id = "mocked-device-id"
        mock_token_resp = _mock_resp({"Token": "oid-token-xyz"}, status_code=200)
        cred_resp = _mock_resp(status_code=200)
        cred_resp.url = "https://ebok.myorlen.pl/home"
        mock_session.post.side_effect = [
            _mock_resp({"RedirectUrl": "https://oid.example.com/auth"}, status_code=200),
            cred_resp,
        ]
        mock_session.get.side_effect = [
            _mock_resp(status_code=200),
            _mock_resp(text='<form action="https://oid.example.com/auth">'),
            mock_token_resp,
        ]
        token = auth.login(allow_interactive=True)
        assert token == "oid-token-xyz"
        assert auth._cached_token == "oid-token-xyz"


def test_login_raises_when_login_form_missing(auth):
    with patch.object(auth, "_session") as mock_session, patch.object(
        auth, "_try_restore_session_token", return_value=None
    ):
        mock_session.post.return_value = _mock_resp(
            {"RedirectUrl": "https://oid.example.com/auth"}, status_code=200
        )
        mock_session.get.side_effect = [
            _mock_resp(status_code=200),
            _mock_resp(text="<html>No form here</html>"),
        ]
        with pytest.raises(RuntimeError, match="login form not found"):
            auth.login(allow_interactive=True)


def test_login_raises_invalid_auth_when_not_redirected_to_home(auth):
    with patch.object(auth, "_session") as mock_session, patch.object(
        auth, "_try_restore_session_token", return_value=None
    ):
        cred_resp = _mock_resp(status_code=200)
        cred_resp.url = "https://oid-ws.orlen.pl/login-actions/authenticate"
        mock_session.post.side_effect = [
            _mock_resp({"RedirectUrl": "https://oid.example.com/auth"}, status_code=200),
            cred_resp,
        ]
        mock_session.get.side_effect = [
            _mock_resp(status_code=200),
            _mock_resp(text='<form action="https://oid.example.com/auth">'),
        ]
        with pytest.raises(InvalidAuthError):
            auth.login(allow_interactive=True)


def test_login_raises_when_auth_token_request_fails(auth):
    with patch.object(auth, "_session") as mock_session, patch.object(
        auth, "_try_restore_session_token", return_value=None
    ):
        cred_resp = _mock_resp(status_code=200)
        cred_resp.url = "https://ebok.myorlen.pl/home"
        mock_session.post.side_effect = [
            _mock_resp({"RedirectUrl": "https://oid.example.com/auth"}, status_code=200),
            cred_resp,
        ]
        mock_session.get.side_effect = [
            _mock_resp(status_code=200),
            _mock_resp(text='<form action="https://oid.example.com/auth">'),
            _mock_resp(status_code=401, text="unauthorized"),
        ]
        with pytest.raises(RuntimeError, match="Auth token"):
            auth.login(allow_interactive=True)


def test_session_data_restores_cookies_not_token():
    cls = AuthRegistry.get("orlen_id")
    auth = cls(
        "oid_user@test.pl",
        "oid_pass",
        session_data={
            "device_id": "stored-device",
            "cookies": [
                {
                    "name": "session",
                    "value": "abc",
                    "domain": "ebok.myorlen.pl",
                    "path": "/",
                }
            ],
            "token": "expired-stale-token",
        },
    )
    assert auth._cached_token == ""
    assert auth._device_id == "stored-device"
    with patch.object(auth, "_fetch_auth_token", return_value="fresh-token") as mock_fetch:
        token = auth.login(allow_interactive=True)
        assert token == "fresh-token"
        mock_fetch.assert_called_once()


def test_login_without_interactive_raises_when_session_expired(auth):
    with patch.object(auth, "_try_restore_session_token", return_value=None):
        with pytest.raises(SessionExpiredError):
            auth.login()


def test_invalidate_token_clears_cache(auth):
    auth._cached_token = "cached"
    auth.invalidate_token()
    assert auth._cached_token == ""


def test_login_non_interactive_mfa_enabled_blocks(auth):
    auth._mfa_enabled = True
    with patch.object(auth, "_try_restore_session_token", return_value=None):
        with pytest.raises(SessionExpiredError, match="re-authenticate"):
            auth.login(allow_interactive=False)


def test_login_non_interactive_mfa_disabled_proceeds(auth):
    auth._mfa_enabled = False
    with patch.object(auth, "_try_restore_session_token", return_value=None):
        with patch.object(auth, "_init_session") as mock_init:
            # It should proceed to initialize session and try to login
            with pytest.raises(RuntimeError):  # It will fail later in the flow due to no mock setup
                auth.login(allow_interactive=False)
            mock_init.assert_called_once()


def test_try_restore_session_token_silent_sso_success(auth):
    auth._session.cookies.set("dummy", "val")
    with patch.object(auth, "_fetch_auth_token", side_effect=[RuntimeError("Expired"), "fresh-token-sso"]):
        with patch.object(auth, "_session") as mock_session:
            mock_session.cookies.keys.return_value = ["dummy"]
            
            init_resp = _mock_resp({"RedirectUrl": "https://sso.redirect"}, status_code=200)
            sso_resp = _mock_resp(status_code=200)
            sso_resp.url = "https://ebok.myorlen.pl/home"
            
            mock_session.post.return_value = init_resp
            mock_session.get.return_value = sso_resp
            
            token = auth._try_restore_session_token()
            assert token == "fresh-token-sso"
            assert mock_session.post.called
            assert mock_session.get.called


def test_try_restore_session_token_silent_sso_failure(auth):
    """Giving up is decided by the token still being refused, not by the URL."""
    auth._session.cookies.set("dummy", "val")
    with patch.object(auth, "_fetch_auth_token", side_effect=RuntimeError("Expired")):
        with patch.object(auth, "_session") as mock_session:
            mock_session.cookies.keys.return_value = ["dummy"]

            init_resp = _mock_resp({"RedirectUrl": "https://sso.redirect"}, status_code=200)
            sso_resp = _mock_resp(status_code=200)
            sso_resp.url = "https://ebok.myorlen.pl/"

            mock_session.post.return_value = init_resp
            mock_session.get.return_value = sso_resp

            token = auth._try_restore_session_token()
            assert token is None
            assert auth._cached_token == ""


# --- silent SSO recovery (issue #131 follow-up) ------------------------

OID_LOGIN_PAGE = """
<form id="kc-form-login" action="https://oid-ws.orlen.pl/realms/oid/login-actions/authenticate">
  <input id="username" name="username" type="text" />
  <input id="password" name="password" type="password" />
</form>
"""


def _silent_sso_session(auth, *, landing_url: str, landing_html: str = ""):
    """Mock session where init-login works and the callback lands somewhere."""
    mock_session = patch.object(auth, "_session").start()
    mock_session.cookies.keys.return_value = ["dummy"]
    mock_session.post.return_value = _mock_resp(
        {"RedirectUrl": "https://oid-ws.orlen.pl/realms/oid/protocol/openid-connect/auth"},
        status_code=200,
    )
    landing = _mock_resp(status_code=200, text=landing_html)
    landing.url = landing_url
    mock_session.get.return_value = landing
    return mock_session


def test_silent_sso_recovers_when_callback_lands_off_home(auth):
    """The regression: the callback does not reliably land on /home.

    Production logged 39 silent refresh attempts, 0 successes and 0 exceptions -
    it matched the landing URL against /home and silently gave up, so every
    lapsed session escalated to a full credential login and an SMS.
    """
    auth._session.cookies.set("dummy", "val")
    try:
        _silent_sso_session(auth, landing_url="https://ebok.myorlen.pl/?show=modal")
        with patch.object(
            auth, "_fetch_auth_token", side_effect=[RuntimeError("Expired"), "recovered"]
        ):
            assert auth._try_restore_session_token() == "recovered"
    finally:
        patch.stopall()


def test_silent_sso_gives_up_without_logging_in_when_sso_session_is_gone(auth):
    """A login page means the SSO session died too - do not try the token."""
    auth._session.cookies.set("dummy", "val")
    try:
        _silent_sso_session(
            auth,
            landing_url="https://oid-ws.orlen.pl/realms/oid/protocol/openid-connect/auth",
            landing_html=OID_LOGIN_PAGE,
        )
        with patch.object(
            auth, "_fetch_auth_token", side_effect=RuntimeError("Expired")
        ) as fetch:
            assert auth._try_restore_session_token() is None
            assert fetch.call_count == 1  # only the initial probe
    finally:
        patch.stopall()


@pytest.mark.parametrize(
    ("init_json", "status"),
    [({"RedirectUrl": "https://sso"}, 500), ({}, 200)],
    ids=["init-login-error", "no-redirect-url"],
)
def test_silent_sso_gives_up_when_init_login_is_unusable(auth, init_json, status):
    auth._session.cookies.set("dummy", "val")
    with patch.object(auth, "_fetch_auth_token", side_effect=RuntimeError("Expired")):
        with patch.object(auth, "_session") as mock_session:
            mock_session.cookies.keys.return_value = ["dummy"]
            mock_session.post.return_value = _mock_resp(init_json, status_code=status)

            assert auth._try_restore_session_token() is None
            mock_session.get.assert_not_called()


def test_silent_sso_survives_an_unexpected_error(auth):
    """Nothing here may stop the caller falling back to a credential login."""
    auth._session.cookies.set("dummy", "val")
    with patch.object(auth, "_fetch_auth_token", side_effect=RuntimeError("Expired")):
        with patch.object(auth, "_session") as mock_session:
            mock_session.cookies.keys.return_value = ["dummy"]
            mock_session.post.side_effect = ValueError("boom")

            assert auth._try_restore_session_token() is None



DEVICE_COOKIE = "pgnig-ebok-device-token"


def _device_cookie(auth) -> str:
    return auth.session.cookies.get(DEVICE_COOKIE)


def test_two_logins_for_one_account_present_the_same_device():
    """Without a stored session, every login used to look like a new device."""
    OrlenIDAuth = AuthRegistry.get("orlen_id")
    first = OrlenIDAuth("user@example.pl", "pw")
    second = OrlenIDAuth("user@example.pl", "pw")

    assert _device_cookie(first) == _device_cookie(second)


def test_different_accounts_get_different_devices():
    OrlenIDAuth = AuthRegistry.get("orlen_id")
    assert _device_cookie(OrlenIDAuth("a@example.pl", "pw")) != _device_cookie(
        OrlenIDAuth("b@example.pl", "pw")
    )


def test_stored_device_id_still_wins():
    """Existing installs keep the device Orlen has already seen and trusted."""
    OrlenIDAuth = AuthRegistry.get("orlen_id")
    auth = OrlenIDAuth(
        "user@example.pl",
        "pw",
        session_data={"device_id": "legacy-random-id", "cookies": []},
    )

    assert _device_cookie(auth) == "legacy-random-id"


def test_interactive_login_drops_stale_cookies_but_keeps_the_device():
    """Reusing a session must not drag expired auth cookies into a fresh login.

    A restored session that could not be refreshed still holds dead Keycloak
    cookies. Sending them makes Keycloak land somewhere unexpected, which the
    login flow reports as a bogus "credentials rejected". The device token has
    to survive, though, or Orlen stops recognising the device.
    """
    OrlenIDAuth = AuthRegistry.get("orlen_id")
    auth = OrlenIDAuth(
        "user@example.pl",
        "pw",
        session_data={
            "device_id": "dev-123",
            "cookies": [
                {
                    "name": "KEYCLOAK_SESSION",
                    "value": "stale",
                    "domain": "ebok.myorlen.pl",
                    "path": "/",
                }
            ],
        },
    )
    assert auth.session.cookies.get("KEYCLOAK_SESSION") == "stale"

    seen = {}

    def capture_jar():
        seen["cookies"] = dict(auth.session.cookies)
        raise RuntimeError("stop before any network call")

    with (
        patch.object(auth, "_try_restore_session_token", return_value=None),
        patch.object(auth, "_init_session", side_effect=capture_jar),
        pytest.raises(RuntimeError),
    ):
        auth.login(allow_interactive=True)

    assert "KEYCLOAK_SESSION" not in seen["cookies"]
    assert seen["cookies"].get("pgnig-ebok-device-token") == "dev-123"
