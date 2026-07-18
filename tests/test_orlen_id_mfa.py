"""Tests for OrlenID MFA helpers and config flow step."""
from unittest.mock import MagicMock, patch

import pytest
import requests
from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from custom_components.pgnig_gas_sensor.auth.exceptions import MfaRequired, MfaSessionExpiredError
from custom_components.pgnig_gas_sensor.auth.orlen_id import (
    OrlenIDAuth,
    _build_mfa_payload,
    _cookies_for_storage,
    _find_mfa_form,
    _restore_cookies,
)
from custom_components.pgnig_gas_sensor.const import (
    AUTH_METHOD_ORLEN_ID,
    CONF_AUTH_METHOD,
    CONF_MFA_CODE,
    CONF_ORLEN_SESSION,
    DOMAIN,
)

SMS_FORM_HTML = """
<p>Wpisz kod SMS weryfikacyjny</p>
<form action="https://oid-ws.orlen.pl/realms/oid/login-actions/authenticate?session_code=abc"
      method="post">
  <input type="text" id="code" name="code" />
  <input type="submit" value="Submit" />
</form>
"""

OTP_FORM_HTML = """
<form action="https://oid-ws.orlen.pl/realms/oid/login-actions/authenticate?session_code=xyz"
      method="post">
  <input type="text" name="otp" />
  <input name="login" type="submit" value="Log In" />
</form>
"""


@pytest.fixture(autouse=True)
def auto_enable(enable_custom_integrations):
    yield


def test_find_mfa_form_detects_sms_code_field():
    action, fields, field_name = _find_mfa_form(
        SMS_FORM_HTML, "https://oid-ws.orlen.pl/"
    )
    assert "authenticate" in action
    assert field_name == "code"
    assert fields == {}


def test_find_mfa_form_detects_otp_field():
    action, fields, field_name = _find_mfa_form(
        OTP_FORM_HTML, "https://oid-ws.orlen.pl/"
    )
    assert field_name == "otp"
    assert fields["login"] == "Log In"


def test_build_mfa_payload_for_sms_does_not_add_login():
    payload = _build_mfa_payload({}, "code", "123456")
    assert payload == {"code": "123456"}
    assert "login" not in payload


def test_build_mfa_payload_for_otp_adds_login_submit():
    payload = _build_mfa_payload({}, "otp", "123456")
    assert payload == {"otp": "123456", "login": "Log In"}


def test_cookie_storage_roundtrip_preserves_values():
    session = requests.Session()
    session.cookies.set("KEYCLOAK_SESSION", "abc", domain="oid-ws.orlen.pl", path="/")
    session.cookies.set("pgnig-ebok-device-token", "device123")

    stored = _cookies_for_storage(session.cookies)
    restored = requests.Session()
    _restore_cookies(restored, stored)

    assert restored.cookies.get("KEYCLOAK_SESSION") == "abc"
    assert restored.cookies.get("pgnig-ebok-device-token") == "device123"


def test_restore_cookies_handles_empty_domain():
    session = requests.Session()
    _restore_cookies(
        session,
        [{"name": "KEYCLOAK_SESSION", "value": "abc", "domain": "", "path": "/"}],
    )
    assert session.cookies.get("KEYCLOAK_SESSION") == "abc"


def test_export_session_contains_token_and_cookies():
    auth = OrlenIDAuth("user@test.pl", "secret")
    auth._cached_token = "token-xyz"
    auth._session.cookies.set("session", "value", domain="oid-ws.orlen.pl", path="/")

    exported = auth.export_session()
    assert exported["token"] == "token-xyz"
    assert exported["device_id"]
    assert any(cookie["name"] == "session" for cookie in exported["cookies"])


@pytest.mark.asyncio
async def test_config_flow_mfa_step_after_mfa_required(hass):
    pending = {
        "username": "user@test.pl",
        "password": "secret",
        "device_id": "device123",
        "cookies": [],
        "mfa_post_url": "https://oid-ws.orlen.pl/auth",
        "mfa_form_fields": {},
        "mfa_field_name": "code",
        "mfa_referer": "https://oid-ws.orlen.pl/",
    }

    with patch("custom_components.pgnig_gas_sensor.config_flow.PgnigApi") as mock_api_cls:
        mock_api = MagicMock()
        mock_api.login.side_effect = MfaRequired(pending)
        mock_api.export_orlen_session.return_value = {
            "device_id": "device123",
            "cookies": [],
            "token": "token-xyz",
        }
        mock_api_cls.return_value = mock_api

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_AUTH_METHOD: AUTH_METHOD_ORLEN_ID,
                CONF_USERNAME: "user@test.pl",
                CONF_PASSWORD: "secret",
            },
        )
        assert result["type"] == data_entry_flow.FlowResultType.FORM
        assert result["step_id"] == "mfa"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_MFA_CODE: "123456"},
        )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_ORLEN_SESSION]["token"] == "token-xyz"
    mock_api.complete_mfa.assert_called_once_with(pending, "123456")


@pytest.mark.asyncio
async def test_config_flow_returns_to_user_on_mfa_session_expired(hass):
    pending = {
        "username": "user@test.pl",
        "password": "secret",
        "device_id": "device123",
        "cookies": [],
        "mfa_post_url": "https://oid-ws.orlen.pl/auth",
        "mfa_form_fields": {},
        "mfa_field_name": "code",
        "mfa_referer": "https://oid-ws.orlen.pl/",
    }

    with patch("custom_components.pgnig_gas_sensor.config_flow.PgnigApi") as mock_api_cls:
        mock_api = MagicMock()
        mock_api.login.side_effect = MfaRequired(pending)
        mock_api.complete_mfa.side_effect = MfaSessionExpiredError("session expired")
        mock_api_cls.return_value = mock_api

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_AUTH_METHOD: AUTH_METHOD_ORLEN_ID,
                CONF_USERNAME: "user@test.pl",
                CONF_PASSWORD: "secret",
            },
        )
        assert result["step_id"] == "mfa"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_MFA_CODE: "999999"},
        )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"]["base"] == "mfa_session_expired"


def test_build_pending_mfa_from_sms_response():
    auth = OrlenIDAuth("user@test.pl", "secret")
    response = MagicMock()
    response.text = SMS_FORM_HTML
    response.url = "https://oid-ws.orlen.pl/realms/oid/login-actions/authenticate"

    pending = auth._build_pending_mfa(response)
    assert pending["mfa_field_name"] == "code"
    assert pending["username"] == "user@test.pl"
    assert isinstance(pending["cookies"], list)
