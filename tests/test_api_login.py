"""Tests for ApiLoginAuth auth method with mocked HTTP."""
from unittest.mock import MagicMock, patch

import pytest
import requests

from custom_components.pgnig_gas_sensor.auth import AuthRegistry


def _make_mock_response(json_data=None, status_code=200, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.ok = 200 <= status_code < 300
    resp.text = text
    resp.json.return_value = json_data or {}
    resp.headers = {"Content-Type": "application/json"}
    return resp


@pytest.fixture
def auth():
    cls = AuthRegistry.get("api_login")
    return cls("testuser", "testpass")


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
    assert info.id == "api_login"
    assert info.name == "API Login (legacy)"


def test_login_returns_cached_token(auth):
    auth._cached_token = "cached-token-123"
    with patch.object(auth, "_init_session") as mock_init:
        token = auth.login()
        assert token == "cached-token-123"
        mock_init.assert_not_called()


def test_login_success(auth):
    with patch.object(auth, "_session") as mock_session:
        mock_session.get.return_value = _make_mock_response(status_code=200)
        mock_session.post.return_value = _make_mock_response(
            {"Token": "real-token-abc"}, status_code=200
        )
        token = auth.login()
        assert token == "real-token-abc"
        assert auth._cached_token == "real-token-abc"


def test_login_raises_on_http_error(auth):
    with patch.object(auth, "_session") as mock_session:
        mock_session.get.return_value = _make_mock_response(status_code=200)
        mock_session.post.return_value = _make_mock_response(status_code=401)
        with pytest.raises(RuntimeError, match="Login failed with status 401"):
            auth.login()


def test_login_raises_on_non_json(auth):
    with patch.object(auth, "_session") as mock_session:
        mock_session.get.return_value = _make_mock_response(status_code=200)
        resp = _make_mock_response(status_code=200)
        resp.json.side_effect = ValueError("Not JSON")
        resp.text = "not json"
        mock_session.post.return_value = resp
        with pytest.raises(RuntimeError, match="non-JSON response"):
            auth.login()


def test_login_raises_on_missing_token(auth):
    with patch.object(auth, "_session") as mock_session:
        mock_session.get.return_value = _make_mock_response(status_code=200)
        mock_session.post.return_value = _make_mock_response(
            {"NotToken": "abc"}, status_code=200
        )
        with pytest.raises(RuntimeError, match="missing 'Token' field"):
            auth.login()
