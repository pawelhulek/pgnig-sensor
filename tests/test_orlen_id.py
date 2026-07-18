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
