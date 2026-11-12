"""What a display name may be, at every door that takes one.

One rule (``display_name_problem``) and one length (``DISPLAY_NAME_MAX_LENGTH``),
read by the Account card's save, by registration, and by the service that writes
the name.
"""

from __future__ import annotations

import pytest
from fasthtml.common import to_xml
from pydantic import SecretStr, ValidationError

from core.models.auth.auth_request import RegistrationRequest
from core.models.user.user import DISPLAY_NAME_MAX_LENGTH, display_name_problem
from core.models.user.user_request import DisplayNameUpdateRequest
from ui.auth.components import AuthComponents
from ui.settings.account import render_account_card

REFUSED = {
    "blank": "",
    "newline": "two\nlines",
    "carriage-return": "two\rlines",
    "tab": "a\ttab",
    "nul": "a\x00b",
    "escape": "a\x1bb",
    "direction-override": "a‮b",
    "byte-order-mark": "a﻿b",
    "line-separator": "a" + chr(0x2028) + "b",
    "paragraph-separator": "a" + chr(0x2029) + "b",
    "too-long": "x" * (DISPLAY_NAME_MAX_LENGTH + 1),
}

TAKEN = {
    "plain": "Mike",
    "inner-spaces": "Ana María de la Cruz",
    "punctuation": "O'Brien-Smith, Jr.",
    "cjk": "山田太郎",
    "arabic": "محمد",
    "persian-joiner": "می‌خواهم",
    "emoji": "Sam 🌱",
    "joined-emoji": "👩‍👧",
    "longest": "x" * DISPLAY_NAME_MAX_LENGTH,
}


@pytest.mark.parametrize("name", REFUSED.values(), ids=REFUSED.keys())
def test_the_rule_refuses(name: str) -> None:
    assert display_name_problem(name) is not None


@pytest.mark.parametrize("name", TAKEN.values(), ids=TAKEN.keys())
def test_the_rule_takes(name: str) -> None:
    assert display_name_problem(name) is None


def test_the_limit_is_one_hundred() -> None:
    assert DISPLAY_NAME_MAX_LENGTH == 100


class TestTheAccountDoorsModel:
    def test_surrounding_whitespace_is_trimmed(self) -> None:
        assert DisplayNameUpdateRequest(display_name="  \n Bo \t").display_name == "Bo"

    def test_only_spaces_is_refused_not_defaulted(self) -> None:
        with pytest.raises(ValidationError, match="cannot be blank"):
            DisplayNameUpdateRequest(display_name="   ")

    def test_the_length_is_counted_after_the_trim(self) -> None:
        padded = " " + "x" * DISPLAY_NAME_MAX_LENGTH + " "
        assert len(DisplayNameUpdateRequest(display_name=padded).display_name) == 100

    @pytest.mark.parametrize("name", REFUSED.values(), ids=REFUSED.keys())
    def test_it_refuses_what_the_rule_refuses(self, name: str) -> None:
        with pytest.raises(ValidationError):
            DisplayNameUpdateRequest(display_name=name)

    def test_display_name_is_its_one_field(self) -> None:
        assert list(DisplayNameUpdateRequest.model_fields) == ["display_name"]


def _registration(display_name: str) -> RegistrationRequest:
    return RegistrationRequest(
        username="newcomer",
        email="new@example.com",
        display_name=display_name,
        password=SecretStr("secret-pass"),
        confirm_password=SecretStr("secret-pass"),
        accept_terms=True,
    )


class TestRegistration:
    def test_it_takes_the_same_longest_name(self) -> None:
        assert len(_registration("x" * DISPLAY_NAME_MAX_LENGTH).display_name) == 100

    @pytest.mark.parametrize("name", REFUSED.values(), ids=REFUSED.keys())
    def test_it_refuses_what_the_rule_refuses(self, name: str) -> None:
        with pytest.raises(ValidationError):
            _registration(name)

    def test_it_trims(self) -> None:
        assert _registration("  Bo ").display_name == "Bo"


def test_both_forms_cap_the_field_at_the_limit() -> None:
    registration = to_xml(AuthComponents.render_registration_page())
    for html in (registration, to_xml(render_account_card("Bo"))):
        field = html.split('name="display_name"', 1)
        assert len(field) == 2
        tag = field[0].rsplit("<input", 1)[1] + field[1].split(">", 1)[0]
        assert f'maxlength="{DISPLAY_NAME_MAX_LENGTH}"' in tag
