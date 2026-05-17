"""Tests for OrlenIDAuth auth method with mocked HTTP."""
from unittest.mock import MagicMock, patch

import pytest
import requests

from custom_components.pgnig_gas_sensor.auth import AuthRegistry


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
        token = auth.login()
        assert token == "cached-oid-token"
        mock_init.assert_not_called()


def test_login_full_flow_success(auth):
    with patch.object(auth, "_session") as mock_session:
        mock_session.get.return_value = _mock_resp(
            text='<form action="https://oid.example.com/auth?execution=123&tab_id=abc">'
        )
        mock_session.post.return_value = _mock_resp(status_code=200)
        mock_session.post.return_value.url = "https://ebok.myorlen.pl/home"
        auth._device_id = "mocked-device-id"
        mock_token_resp = _mock_resp({"Token": "oid-token-xyz"}, status_code=200)
        mock_session.get.side_effect = [
            _mock_resp(status_code=200),
            _mock_resp(text='<form action="https://oid.example.com/auth">'),
            mock_token_resp,
        ]
        mock_session.post.return_value = _mock_resp(status_code=200)
        mock_session.post.return_value.url = "https://ebok.myorlen.pl/home"
        mock_session.post.return_value.status_code = 302
        mock_session.post.return_value.ok = True
        token = auth.login()
        assert token == "oid-token-xyz"
        assert auth._cached_token == "oid-token-xyz"


def test_login_returns_empty_when_form_not_found(auth):
    with patch.object(auth, "_session") as mock_session:
        mock_session.get.return_value = _mock_resp(
            text="<html>No form here</html>"
        )
        mock_session.post.return_value = _mock_resp(status_code=200)
        mock_session.post.return_value.url = "https://ebok.myorlen.pl/login"
        assert auth.login() == ""


def test_login_returns_empty_when_not_redirected_to_home(auth):
    with patch.object(auth, "_session") as mock_session:
        mock_session.get.return_value = _mock_resp(
            text='<form action="https://oid.example.com/auth?execution=123">'
        )
        mock_session.post.return_value = _mock_resp(status_code=200)
        mock_session.post.return_value.url = "https://ebok.myorlen.pl/login?error=1"
        assert auth.login() == ""


def test_get_auth_token_fails_returns_empty(auth):
    with patch.object(auth, "_session") as mock_session:
        mock_session.get.return_value = _mock_resp(
            text='<form action="https://oid.example.com/auth">'
        )
        mock_session.post.return_value.url = "https://ebok.myorlen.pl/home"
        mock_session.post.return_value.status_code = 302
        mock_session.post.return_value.ok = True
        mock_session.get.side_effect = [
            _mock_resp(status_code=200),
            _mock_resp(text="some page"),
            _mock_resp(status_code=401),
        ]
        mock_session.post.return_value = _mock_resp(status_code=200)
        assert auth.login() == ""
