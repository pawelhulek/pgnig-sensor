"""Parsing and classification of OrlenID (Keycloak) HTML pages.

OrlenID is a Keycloak deployment, so every step of the login flow answers with a
themed HTML page instead of a machine readable status. These helpers turn those
pages into something the login flow can branch on: which form to post next, and
- when login does not complete - *why* it did not.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from html import unescape
from urllib.parse import urljoin

# netzbegruenung SMS authenticator uses name="code"; login-otp.ftl uses "otp"/"totp".
MFA_FIELD_CANDIDATES = ("code", "otp", "totp", "smsCode", "mfa_code", "verificationCode")

LOGIN_FORM_FIELD_NAMES = {"username", "password", "credentialId"}

MFA_PAGE_TOKENS = (
    "otp",
    "totp",
    "sms",
    "kod",
    "weryfik",
    "uwierzyteln",
    "mfa",
    "jednoraz",
)

# Keycloak required-action screens. Each entry maps a marker found in the page
# (form id, field name or URL fragment) to a human readable description.
REQUIRED_ACTION_MARKERS: tuple[tuple[str, str], ...] = (
    # CANCEL_2FA is Orlen's own control on the "enable 2FA?" enrollment screen.
    ("CANCEL_2FA", "two-factor authentication setup"),
    ("kc-totp-settings-form", "two-factor authentication setup"),
    ("totpSecret", "two-factor authentication setup"),
    ("kc-passwd-update-form", "password update"),
    ("password-new", "password update"),
    ("kc-terms-form", "terms and conditions acceptance"),
    ("kc-update-profile-form", "profile data update"),
    ("execution=update_profile", "profile data update"),
    ("execution=verify_email", "e-mail verification"),
    ("login-actions/required-action", "an account action"),
    ("login-actions/action-token", "an account action"),
)

# Controls rendered to dismiss an optional action. CANCEL_2FA is Orlen's;
# cancel-aia is stock Keycloak for application-initiated actions.
SKIP_FIELD_NAMES = ("CANCEL_2FA", "cancel-aia", "cancel", "skip")

SKIP_LINK_PATTERN = re.compile(
    r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL
)
SKIP_LINK_TEXT = re.compile(
    r"pomi[nń]|p[oó][zź]niej|nie teraz|skip|later|not now", re.IGNORECASE
)

ERROR_TEXT_PATTERNS = (
    re.compile(r'class="[^"]*kc-feedback-text[^"]*"[^>]*>(.*?)</', re.IGNORECASE | re.DOTALL),
    re.compile(r'id="input-error[^"]*"[^>]*>(.*?)</', re.IGNORECASE | re.DOTALL),
    re.compile(r'class="[^"]*kc-error-message[^"]*"[^>]*>(.*?)</', re.IGNORECASE | re.DOTALL),
    re.compile(r'id="kc-error-message"[^>]*>.*?<p[^>]*>(.*?)</p>', re.IGNORECASE | re.DOTALL),
)

KEYCLOAK_URL_TOKENS = (
    "login-actions",
    "openid-connect",
    "orlenid",
    "keycloak",
    "/auth/realms/",
    "/realms/",
)


class PageKind(str, Enum):
    """What an OrlenID page returned after posting credentials represents."""

    LOGIN_REJECTED = "login_rejected"
    LOGIN_FORM = "login_form"
    MFA = "mfa"
    REQUIRED_ACTION = "required_action"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SkipAction:
    """A control that dismisses an optional Keycloak required-action screen."""

    method: str
    url: str
    data: dict[str, str] | None = None


@dataclass(frozen=True)
class FormSpec:
    """A parsed HTML form: where it posts, and which controls it carries."""

    action: str
    fields: dict[str, str]
    hidden: dict[str, str]
    buttons: dict[str, str]


def _strip_tags(html: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def iter_form_specs(html: str, base_url: str) -> list[FormSpec]:
    """Parse every form, keeping hidden inputs and submit controls apart.

    Submit controls are parsed from both <input type="submit"> and <button>,
    because Orlen's 2FA enrollment screen renders its skip control as a button.
    """
    specs: list[FormSpec] = []
    for form_match in re.finditer(
        r"<form\b[^>]*action=\"([^\"]+)\"[^>]*>(.*?)</form>",
        html,
        re.IGNORECASE | re.DOTALL,
    ):
        action = unescape(form_match.group(1).replace("&amp;", "&"))
        if action.startswith("/"):
            action = urljoin(base_url, action)
        body = form_match.group(2)

        fields: dict[str, str] = {}
        hidden: dict[str, str] = {}
        buttons: dict[str, str] = {}

        for input_match in re.finditer(
            r"<input[^>]+name=\"([^\"]+)\"[^>]*>", body, re.IGNORECASE
        ):
            tag = input_match.group(0)
            name = input_match.group(1)
            value_match = re.search(r'value="([^"]*)"', tag, re.IGNORECASE)
            value = unescape(value_match.group(1)) if value_match else ""
            input_type = re.search(r'type="([^"]+)"', tag, re.IGNORECASE)
            kind = input_type.group(1).lower() if input_type else "text"
            if kind in {"submit", "button", "image"}:
                if name:
                    buttons[name] = value
                    fields[name] = value
                continue
            if kind == "hidden":
                hidden[name] = value
            fields[name] = value

        for button_match in re.finditer(
            r"<button[^>]+name=\"([^\"]+)\"[^>]*>", body, re.IGNORECASE
        ):
            tag = button_match.group(0)
            name = button_match.group(1)
            value_match = re.search(r'value="([^"]*)"', tag, re.IGNORECASE)
            buttons[name] = unescape(value_match.group(1)) if value_match else ""

        specs.append(FormSpec(action=action, fields=fields, hidden=hidden, buttons=buttons))
    return specs


def iter_forms(html: str, base_url: str) -> list[tuple[str, dict[str, str]]]:
    """Return (action, fields) for every form in the page."""
    return [(spec.action, spec.fields) for spec in iter_form_specs(html, base_url)]


def extract_form(html: str, base_url: str) -> tuple[str, dict[str, str]]:
    forms = iter_forms(html, base_url)
    return forms[0] if forms else ("", {})


def detect_mfa_field(html: str, fields: dict[str, str]) -> str | None:
    lowered = html.lower()
    if not any(token in lowered for token in MFA_PAGE_TOKENS):
        return None

    for candidate in MFA_FIELD_CANDIDATES:
        if candidate in fields:
            return candidate
        if re.search(rf'name=["\']{candidate}["\']', html, re.IGNORECASE):
            return candidate
    return None


def find_mfa_form(html: str, base_url: str) -> tuple[str, dict[str, str], str]:
    """Return MFA form action, hidden fields, and OTP field name."""
    if required_action_description(html, base_url):
        # TOTP *setup* screens also carry an "totp" input; they are not a challenge.
        return "", {}, ""
    for action, fields in iter_forms(html, base_url):
        field_name = detect_mfa_field(html, fields)
        if not field_name:
            continue
        mfa_fields = {
            k: v
            for k, v in fields.items()
            if k not in LOGIN_FORM_FIELD_NAMES and k != field_name
        }
        return action, mfa_fields, field_name
    return "", {}, ""


def is_keycloak_url(url: str) -> bool:
    lowered = url.lower()
    return any(token in lowered for token in KEYCLOAK_URL_TOKENS)


def is_login_page(html: str) -> bool:
    for _, fields in iter_forms(html, ""):
        if "username" in fields and "password" in fields:
            return detect_mfa_field(html, fields) is None
    return False


def extract_error_message(html: str) -> str:
    """Return the error Keycloak rendered on the page, if any."""
    for pattern in ERROR_TEXT_PATTERNS:
        for match in pattern.finditer(html):
            message = _strip_tags(match.group(1))
            if message:
                return message
    return ""


def extract_page_title(html: str) -> str:
    for pattern in (r"<title[^>]*>(.*?)</title>", r"<h1[^>]*>(.*?)</h1>"):
        match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
        if match:
            title = _strip_tags(match.group(1))
            if title:
                return title
    return ""


def required_action_description(html: str, url: str) -> str:
    """Describe the Keycloak required action the page asks for, if any."""
    haystack = f"{url}\n{html}".lower()
    for marker, description in REQUIRED_ACTION_MARKERS:
        if marker.lower() in haystack:
            return description
    return ""


def find_skip_action(html: str, base_url: str) -> SkipAction | None:
    """Find a control that dismisses an optional required-action screen.

    Only the skip control and the form's hidden fields are submitted; the
    visible inputs (an empty OTP box, say) are left out so the server treats
    the post as a cancellation rather than an empty answer.
    """
    for spec in iter_form_specs(html, base_url):
        for name in SKIP_FIELD_NAMES:
            if name not in spec.buttons and name not in spec.hidden:
                continue
            value = spec.buttons.get(name) or spec.hidden.get(name) or "true"
            return SkipAction(
                method="post",
                url=spec.action,
                data={**spec.hidden, name: value},
            )

    for match in SKIP_LINK_PATTERN.finditer(html):
        href = unescape(match.group(1).replace("&amp;", "&"))
        text = _strip_tags(match.group(2))
        if not href or href.startswith("#") or not SKIP_LINK_TEXT.search(text):
            continue
        if href.startswith("/"):
            href = urljoin(base_url, href)
        return SkipAction(method="get", url=href)
    return None


def classify_page(url: str, html: str) -> PageKind:
    """Classify the page OrlenID returned after a credential or MFA post."""
    if required_action_description(html, url):
        return PageKind.REQUIRED_ACTION

    _, _, mfa_field = find_mfa_form(html, url)
    if mfa_field:
        return PageKind.MFA

    if is_login_page(html):
        return PageKind.LOGIN_REJECTED if extract_error_message(html) else PageKind.LOGIN_FORM

    return PageKind.UNKNOWN


def describe_page(url: str, html: str) -> str:
    """Short human readable summary of an unexpected page, for error messages."""
    parts = [part for part in (extract_page_title(html), extract_error_message(html)) if part]
    summary = " - ".join(dict.fromkeys(parts)) or "no error message on page"
    return f"{summary} (at {url})"


def normalize_otp_code(code: str) -> str:
    return re.sub(r"\D", "", (code or "").strip())


def build_mfa_payload(
    form_fields: dict[str, str],
    field_name: str,
    otp_code: str,
) -> dict[str, str]:
    """Build POST body for MFA form without polluting SMS forms with login fields."""
    payload = dict(form_fields)
    payload[field_name] = otp_code
    # Standard Keycloak OTP/TOTP forms use a submit input named "login".
    if field_name in {"otp", "totp"} and "login" not in payload:
        payload["login"] = "Log In"
    return payload
