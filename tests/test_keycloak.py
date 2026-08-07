"""Tests for OrlenID (Keycloak) page parsing and classification."""
import pytest

from custom_components.pgnig_gas_sensor.auth.keycloak import (
    PageKind,
    classify_page,
    describe_page,
    extract_error_message,
    extract_page_title,
    find_mfa_form,
    find_skip_action,
    iter_forms,
    required_action_description,
)

AUTH_URL = "https://oid-ws.orlen.pl/realms/oid/login-actions/authenticate?session_code=x"

LOGIN_FORM_HTML = """
<title>Zaloguj się do ORLEN ID</title>
<form id="kc-form-login" action="/realms/oid/login-actions/authenticate?session_code=x" method="post">
  <input tabindex="2" id="username" name="username" value="" type="text" />
  <input tabindex="3" id="password" name="password" type="password" />
  <input type="hidden" id="id-hidden-input" name="credentialId" />
</form>
"""

REJECTED_LOGIN_HTML = LOGIN_FORM_HTML.replace(
    "<input type=\"hidden\"",
    '<span id="input-error" class="pf-m-error kc-feedback-text">'
    "Nieprawidłowa nazwa użytkownika lub hasło.</span>\n  <input type=\"hidden\"",
)

SMS_CHALLENGE_HTML = """
<p>Wpisz kod SMS weryfikacyjny wysłany na Twój telefon</p>
<form action="https://oid-ws.orlen.pl/realms/oid/login-actions/authenticate?session_code=y" method="post">
  <input type="text" id="code" name="code" />
  <input type="hidden" name="execution" value="abc" />
</form>
"""

TOTP_SETUP_HTML = """
<h1>Skonfiguruj aplikację uwierzytelniającą</h1>
<form id="kc-totp-settings-form" action="https://oid-ws.orlen.pl/required-action" method="post">
  <input type="hidden" name="totpSecret" value="ABC123" />
  <input type="text" id="totp" name="totp" />
</form>
"""

TOTP_SETUP_SKIPPABLE_HTML = TOTP_SETUP_HTML.replace(
    "</form>", '<input type="submit" name="cancel-aia" value="true" /></form>'
)

ORLEN_2FA_ENROLLMENT_HTML = """
<h1>Włącz weryfikację dwuetapową</h1>
<form id="kc-totp-settings-form" action="https://oid-ws.orlen.pl/realms/oid/login-actions/required-action?execution=CONFIGURE_TOTP" method="post">
  <input type="hidden" name="execution" value="abc" />
  <input type="text" id="totp" name="totp" />
  <button type="submit" name="CANCEL_2FA" value="Pomiń">Pomiń</button>
</form>
"""

SKIP_LINK_HTML = """
<h1>Włącz weryfikację dwuetapową</h1>
<div id="kc-form">
  <a href="/realms/oid/login-actions/required-action?execution=CONFIGURE_TOTP&amp;skip=true">Pomiń</a>
</div>
<form id="kc-totp-settings-form" action="https://oid-ws.orlen.pl/required-action" method="post">
  <input type="text" id="totp" name="totp" />
</form>
"""


def test_iter_forms_resolves_relative_action_and_reads_fields():
    action, fields = iter_forms(LOGIN_FORM_HTML, AUTH_URL)[0]
    assert action.startswith("https://oid-ws.orlen.pl/realms/oid/login-actions/authenticate")
    assert fields == {"username": "", "password": "", "credentialId": ""}


def test_classify_login_form_without_error():
    assert classify_page(AUTH_URL, LOGIN_FORM_HTML) is PageKind.LOGIN_FORM


def test_classify_rejected_credentials():
    assert classify_page(AUTH_URL, REJECTED_LOGIN_HTML) is PageKind.LOGIN_REJECTED
    assert (
        extract_error_message(REJECTED_LOGIN_HTML)
        == "Nieprawidłowa nazwa użytkownika lub hasło."
    )


def test_classify_sms_challenge_as_mfa():
    assert classify_page(AUTH_URL, SMS_CHALLENGE_HTML) is PageKind.MFA


def test_classify_totp_setup_as_required_action_not_mfa():
    """The TOTP *setup* screen also has a 'totp' input — it is not a code challenge."""
    assert classify_page(AUTH_URL, TOTP_SETUP_HTML) is PageKind.REQUIRED_ACTION
    assert find_mfa_form(TOTP_SETUP_HTML, AUTH_URL) == ("", {}, "")


def test_classify_unknown_page():
    assert classify_page(AUTH_URL, "<html><body>Przerwa techniczna</body></html>") is (
        PageKind.UNKNOWN
    )


@pytest.mark.parametrize(
    "html,expected",
    [
        (TOTP_SETUP_HTML, "two-factor authentication setup"),
        ('<form id="kc-passwd-update-form"></form>', "password update"),
        ('<form id="kc-terms-form"></form>', "terms and conditions acceptance"),
        (LOGIN_FORM_HTML, ""),
    ],
)
def test_required_action_description(html, expected):
    assert required_action_description(html, AUTH_URL) == expected


def test_required_action_detected_from_url_alone():
    url = "https://oid-ws.orlen.pl/realms/oid/login-actions/required-action?execution=X"
    assert required_action_description("<html></html>", url) == "an account action"


def test_find_skip_action_prefers_cancel_button():
    skip = find_skip_action(TOTP_SETUP_SKIPPABLE_HTML, AUTH_URL)
    assert skip is not None
    assert skip.method == "post"
    assert skip.data["cancel-aia"] == "true"


def test_orlen_2fa_enrollment_screen_is_a_skippable_required_action():
    """The real screen from issue #101: a <button name="CANCEL_2FA">Pomiń</button>."""
    assert classify_page(AUTH_URL, ORLEN_2FA_ENROLLMENT_HTML) is PageKind.REQUIRED_ACTION
    assert (
        required_action_description(ORLEN_2FA_ENROLLMENT_HTML, AUTH_URL)
        == "two-factor authentication setup"
    )

    skip = find_skip_action(ORLEN_2FA_ENROLLMENT_HTML, AUTH_URL)
    assert skip is not None
    assert skip.method == "post"
    assert skip.data["CANCEL_2FA"] == "Pomiń"
    # hidden state is carried over, the empty OTP box is not submitted
    assert skip.data["execution"] == "abc"
    assert "totp" not in skip.data


def test_find_skip_action_falls_back_to_skip_link():
    skip = find_skip_action(SKIP_LINK_HTML, AUTH_URL)
    assert skip is not None
    assert skip.method == "get"
    assert skip.url.endswith("execution=CONFIGURE_TOTP&skip=true")


def test_find_skip_action_returns_none_without_skip_control():
    assert find_skip_action(TOTP_SETUP_HTML, AUTH_URL) is None


def test_describe_page_includes_title_and_error():
    summary = describe_page(AUTH_URL, REJECTED_LOGIN_HTML)
    assert "Zaloguj się do ORLEN ID" in summary
    assert "Nieprawidłowa nazwa użytkownika lub hasło." in summary
    assert AUTH_URL in summary


def test_extract_page_title_falls_back_to_heading():
    assert extract_page_title(TOTP_SETUP_HTML) == "Skonfiguruj aplikację uwierzytelniającą"
