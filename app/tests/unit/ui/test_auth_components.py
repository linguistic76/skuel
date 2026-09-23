"""The auth forms post what their handlers read.

``login_submit`` / ``register_submit`` (``adapters/inbound/auth_ui.py``) read
fixed form keys; a renamed input in ``ui/auth/components.py`` would reach the
handler as a blank field and fail every submission with "X is required". These
tests pin the form half of that contract against the rendered HTML.
"""

from html.parser import HTMLParser

import pytest
from fasthtml.common import to_xml

from ui.auth.components import AuthComponents


class _FormScan(HTMLParser):
    """Collect each form's action and the names of the fields it submits."""

    def __init__(self) -> None:
        super().__init__()
        self.forms: list[tuple[str | None, set[str]]] = []
        self.alerts: list[str] = []
        self._in_alert = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag == "form":
            self.forms.append((attr.get("action"), set()))
        elif tag in {"input", "select", "textarea"} and self.forms and attr.get("name"):
            self.forms[-1][1].add(attr["name"])
        if attr.get("role") == "alert":
            self._in_alert += 1
            self.alerts.append("")
        elif self._in_alert and tag == "div":
            self._in_alert += 1

    def handle_endtag(self, tag: str) -> None:
        if self._in_alert and tag == "div":
            self._in_alert -= 1

    def handle_data(self, data: str) -> None:
        if self._in_alert:
            self.alerts[-1] += data


def _scan(component: object) -> _FormScan:
    scan = _FormScan()
    scan.feed(to_xml(component))
    scan.alerts = [" ".join(text.split()) for text in scan.alerts]
    return scan


_LOGIN_FIELDS = {"username", "password"}
_REGISTRATION_FIELDS = {"username", "email", "display_name", "password", "confirm_password"}


def test_login_form_posts_the_fields_login_submit_reads() -> None:
    [(action, fields)] = _scan(AuthComponents.render_login_page()).forms

    assert action == "/login/submit"
    assert fields >= _LOGIN_FIELDS
    assert "csrf_token" in fields


@pytest.mark.parametrize("gated", [False, True])
def test_registration_form_posts_the_fields_register_submit_reads(gated: bool) -> None:
    [(action, fields)] = _scan(
        AuthComponents.render_registration_page(require_invite_code=gated)
    ).forms

    assert action == "/register/submit"
    assert _REGISTRATION_FIELDS | {"accept_terms", "csrf_token"} <= fields
    assert ("invite_code" in fields) is gated


@pytest.mark.parametrize(
    "render",
    [
        AuthComponents.render_login_page,
        AuthComponents.render_registration_page,
        AuthComponents.render_forgot_password_form,
    ],
)
def test_error_message_is_announced_only_when_given(render) -> None:
    assert _scan(render()).alerts == []
    assert _scan(render(error_message="Invalid username or password")).alerts == [
        "Invalid username or password"
    ]
