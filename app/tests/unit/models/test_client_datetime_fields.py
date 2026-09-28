"""Every datetime a client supplies is read on the user's clock (UTC arc, ADR-089).

A request model's ``datetime`` field is a client door: an offset-less value
(a ``datetime-local`` field, a JSON string without an offset) names a moment on
the user's clock, and ``ClientDateTime`` reads it in the current zone and holds
the stored form of the instant. This test finds every Pydantic model in
``core/models`` with a ``datetime`` field and requires each field to be either a
``ClientDateTime`` or a named response field — so a new request field cannot
read a client's wall clock as the server's without failing here.
"""

from __future__ import annotations

import importlib
import pkgutil
from datetime import datetime
from typing import get_args
from zoneinfo import ZoneInfo

import pytest
from pydantic import BaseModel

import core.models
from core.models.choice.choice_request import ChoiceCreateRequest
from core.models.request_base import ClientDateTime
from core.utils.timestamp_helpers import as_stored_clock
from core.utils.zone_context import current_zone_var
from tests.helpers.laptop_clock import laptop_wall

#: Fields a server fills and a client reads — never parsed from client input.
RESPONSE_FIELDS = {
    ("SearchResponse", "timestamp"),
    ("UserView", "created_at"),
    ("UserView", "last_active_at"),
    ("UserView", "last_login_at"),
    ("UserSummaryView", "created_at"),
    ("UserSummaryView", "last_active_at"),
    ("UserServiceContextSchema", "session_start"),
    ("UserStatisticsSchema", "computed_at"),
    ("TaskResponse", "created_at"),
    ("TaskResponse", "updated_at"),
}


def _models() -> list[type[BaseModel]]:
    """Every Pydantic model defined under ``core/models``."""
    for info in pkgutil.walk_packages(core.models.__path__, "core.models."):
        importlib.import_module(info.name)
    seen: list[type[BaseModel]] = []
    stack = [BaseModel]
    while stack:
        for sub in stack.pop().__subclasses__():
            stack.append(sub)
            if sub.__module__.startswith("core.models.") and sub not in seen:
                seen.append(sub)
    return seen


def _holds_datetime(annotation: object) -> bool:
    return (
        annotation is datetime
        or datetime in get_args(annotation)
        or any(_holds_datetime(arg) for arg in get_args(annotation))
    )


def _is_client_datetime(annotation: object) -> bool:
    return annotation == ClientDateTime or ClientDateTime in get_args(annotation)


def _datetime_fields() -> list[tuple[str, str, object]]:
    return [
        (model.__name__, name, field.annotation)
        for model in _models()
        for name, field in model.model_fields.items()
        if name in model.__annotations__ and _holds_datetime(field.annotation)
    ]


def test_every_datetime_field_is_a_client_door_or_a_named_response():
    fields = _datetime_fields()
    assert fields, "no datetime fields found — the scan itself is broken"
    unclassified = [
        f"{model}.{name}"
        for model, name, annotation in fields
        if not _is_client_datetime(annotation) and (model, name) not in RESPONSE_FIELDS
    ]
    assert not unclassified, (
        "A request model's datetime field must be ClientDateTime (a client's "
        "offset-less value is a wall clock in the current zone); a field only a "
        f"server fills belongs in RESPONSE_FIELDS: {unclassified}"
    )


def test_every_named_response_field_still_exists():
    present = {(model, name) for model, name, _ in _datetime_fields()}
    assert present >= RESPONSE_FIELDS, sorted(RESPONSE_FIELDS - present)


@pytest.mark.usefixtures("laptop_zone")
def test_a_bangkok_users_deadline_is_read_on_the_bangkok_clock():
    """17:00 typed by a Bangkok user is 10:00Z, held on the stored (UTC) clock; the
    same 17:00 typed by a user on the default zone is 17:00 in Vancouver."""
    token = current_zone_var.set(ZoneInfo("Asia/Bangkok"))
    try:
        request = ChoiceCreateRequest(
            title="t", description="d", decision_deadline=datetime(2026, 9, 27, 17, 0)
        )
    finally:
        current_zone_var.reset(token)
    assert request.decision_deadline == datetime(2026, 9, 27, 10, 0)
    assert request.decision_deadline == as_stored_clock(
        datetime(2026, 9, 27, 17, 0, tzinfo=ZoneInfo("Asia/Bangkok"))
    )

    default = ChoiceCreateRequest(
        title="t", description="d", decision_deadline=datetime(2026, 9, 27, 17, 0)
    )
    assert default.decision_deadline == laptop_wall(2026, 9, 27, 17, 0)


def test_an_offset_bearing_value_keeps_its_instant():
    request = ChoiceCreateRequest(
        title="t", description="d", decision_deadline="2026-09-27T17:00:00+07:00"
    )
    assert request.decision_deadline == datetime(
        2026, 9, 27, 17, 0, tzinfo=ZoneInfo("Asia/Bangkok")
    )
