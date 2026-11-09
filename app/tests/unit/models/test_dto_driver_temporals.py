"""The DTO path reads the driver's temporal types as the mapper does.

A node read raw from the graph carries the driver's own temporals: the mapper writes
a ``time`` as a native LOCAL TIME (an Event's ``start_time``), and Cypher
``datetime()`` stamps a native (bulk upsert's ``updated_at`` on re-ingest, the
exercise backend's stamps). The search, traversal and range reads turn those
records into models through ``to_domain_model`` (``{Domain}DTO.from_dict`` →
``from_dto``), the by-uid reads through ``from_neo4j_node``. These tests hand both
paths the same raw Event record and pin that they agree, field by field, and that
the result serializes at the JSON boundary, which refuses a driver temporal. A census
then builds every DTO under ``core/models`` from a driver value in each ``date`` /
``datetime`` / ``time`` field it declares, so a field left off its DTO's parse list
fails here. A second census hands every ``dict`` field a DTO declares the JSON text the
mapper stores for it (Neo4j holds no maps), so a dict field read raw reaches the model
as a dict, never as its text.

The route-level proof is ``tests/integration/routes/test_dto_path_driver_temporals.py``.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import types
import typing
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

import neo4j.time
import pytest

from adapters.inbound.boundary import jsonable_content
from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node
from core.models.dto_helpers import parse_date_field, parse_datetime_field, parse_time_field
from core.models.event.event import Event
from core.models.event.event_dto import EventDTO
from core.utils.dto_converters import to_domain_model

_STAMP = datetime(2026, 11, 8, 17, 4, 5, 123000, tzinfo=UTC)


def _raw_event() -> dict[str, Any]:  # boundary: a stored node's property dict
    """An Event as the driver hands back a node the create door wrote."""
    return {
        "uid": "event_0123456789abcdef",
        "title": "Morning run",
        "entity_type": "event",
        "user_uid": "user_0123456789abcdef",
        "status": "scheduled",
        "event_date": neo4j.time.Date(2026, 11, 20),
        "start_time": neo4j.time.Time(9, 30, 0),
        "end_time": neo4j.time.Time(10, 15, 0),
        "created_at": "2026-11-01T08:00:00",
        "updated_at": neo4j.time.DateTime.from_native(_STAMP),
    }


_TEMPORAL_FIELDS = ("event_date", "start_time", "end_time", "created_at", "updated_at")


def test_both_converters_read_a_raw_event_alike() -> None:
    via_dto = to_domain_model(_raw_event(), EventDTO, Event)
    via_mapper = from_neo4j_node(_raw_event(), Event)
    for name in _TEMPORAL_FIELDS:
        dto_value, mapper_value = getattr(via_dto, name), getattr(via_mapper, name)
        assert type(dto_value) is type(mapper_value), name
        assert dto_value == mapper_value, name
    assert via_dto.event_date == date(2026, 11, 20)
    assert via_dto.start_time == time(9, 30)
    assert via_dto.end_time == time(10, 15)
    assert via_dto.updated_at == _STAMP


def test_a_raw_event_read_through_the_dto_serializes() -> None:
    content = jsonable_content(to_domain_model(_raw_event(), EventDTO, Event))
    assert content["start_time"] == "09:30:00"
    assert content["end_time"] == "10:15:00"
    assert content["event_date"] == "2026-11-20"
    assert content["updated_at"] == "2026-11-08T17:04:05.123000Z"


@pytest.mark.parametrize(
    ("parse", "stored", "expected"),
    [
        (parse_time_field, neo4j.time.Time(9, 30, 15), time(9, 30, 15)),
        (parse_time_field, "09:30:15", time(9, 30, 15)),
        (parse_date_field, neo4j.time.Date(2026, 11, 20), date(2026, 11, 20)),
        (parse_date_field, "2026-11-20", date(2026, 11, 20)),
        (parse_datetime_field, neo4j.time.DateTime.from_native(_STAMP), _STAMP),
        (parse_datetime_field, "2026-11-08T17:04:05.123000+00:00", _STAMP),
    ],
)
def test_each_parser_reads_a_driver_value_and_an_iso_string(
    parse: Any,  # boundary: one of the three parsers
    stored: object,
    expected: object,
) -> None:
    data = {"field": stored}
    parse(data, "field")
    assert type(data["field"]) is type(expected)
    assert data["field"] == expected


@pytest.mark.parametrize("parse", [parse_time_field, parse_date_field, parse_datetime_field])
def test_an_absent_or_null_field_is_left_as_it_is(
    parse: Any,  # boundary: one of the three parsers
) -> None:
    absent: dict[str, object] = {}
    parse(absent, "field")
    assert absent == {}
    null: dict[str, object] = {"field": None}
    parse(null, "field")
    assert null == {"field": None}


# ---------------------------------------------------------------------------
# The census: every DTO converts every temporal field it declares
# ---------------------------------------------------------------------------

_MODELS = Path(__file__).resolve().parents[3] / "core" / "models"
_DRIVER_VALUE: dict[type, object] = {
    date: neo4j.time.Date(2026, 11, 20),
    datetime: neo4j.time.DateTime.from_native(_STAMP),
    time: neo4j.time.Time(9, 30, 0),
}
# The fields a DTO requires beyond the common ones, so from_dict can build it.
_REQUIRED: dict[str, dict[str, object]] = {
    "HabitCompletionDTO": {"habit_uid": "habit_0123456789abcdef", "completed_at": _STAMP},
    "UserDTO": {"username": "census", "email": "census@example.test"},
    "PrincipleReflectionDTO": {
        "principle_uid": "principle_0123456789abcdef",
        "alignment_level": "aligned",
        "evidence": "evidence",
        "reflection_date": date(2026, 11, 20),
    },
}


def _temporal_type(hint: object) -> type | None:
    members = (
        typing.get_args(hint)
        if typing.get_origin(hint) in (typing.Union, types.UnionType)
        else (hint,)
    )
    for member in members:
        for kind in (datetime, date, time):  # datetime first: it subclasses date
            if member is kind:
                return kind
    return None


def _is_dto(candidate: object, module_name: str) -> bool:
    return (
        isinstance(candidate, type)
        and dataclasses.is_dataclass(candidate)
        and candidate.__module__ == module_name
        and any("from_dict" in vars(klass) for klass in candidate.__mro__[:-1])
    )


def _dto_classes() -> list[type]:
    found: list[type] = []
    for path in sorted(_MODELS.rglob("*dto*.py")):
        module_name = ".".join(path.relative_to(_MODELS.parents[1]).with_suffix("").parts)
        module = importlib.import_module(module_name)
        found.extend(
            candidate for candidate in vars(module).values() if _is_dto(candidate, module_name)
        )
    return found


_DTOS = _dto_classes()


def test_the_census_finds_the_dtos() -> None:
    names = {dto.__name__ for dto in _DTOS}
    assert {"EventDTO", "TaskDTO", "UserEntryDTO", "PrincipleReflectionDTO"} <= names
    assert len(_DTOS) >= 31


def _dto_name(dto_class: type) -> str:
    return dto_class.__name__


@pytest.mark.parametrize("dto_class", _DTOS, ids=_dto_name)
def test_every_temporal_field_a_dto_declares_reads_a_driver_value(dto_class: type) -> None:
    """A field left off its DTO's parse list would hand the model a driver temporal."""
    hints = typing.get_type_hints(
        dto_class, localns={"date": date, "datetime": datetime, "time": time}
    )
    declared = {field.name for field in dataclasses.fields(dto_class)}
    temporal = {
        name: kind for name in declared if (kind := _temporal_type(hints[name])) is not None
    }
    if not temporal:
        pytest.skip(f"{dto_class.__name__} declares no temporal field")
    common = {
        "uid": "x_0123456789abcdef",
        "title": "census",
        "user_uid": "user_0123456789abcdef",
        "entity_type": "task",
    }
    data = {
        key: value
        for key, value in {**common, **_REQUIRED.get(dto_class.__name__, {})}.items()
        if key in declared
    }
    data.update({name: _DRIVER_VALUE[kind] for name, kind in temporal.items()})

    dto = dto_class.from_dict(data)  # type: ignore[attr-defined]

    left = sorted(name for name in temporal if type(getattr(dto, name)).__module__ == "neo4j.time")
    assert left == [], f"{dto_class.__name__} leaves driver temporals in {left}"


def _is_dict(hint: object) -> bool:
    members = (
        typing.get_args(hint)
        if typing.get_origin(hint) in (typing.Union, types.UnionType)
        else (hint,)
    )
    return any(member is dict or typing.get_origin(member) is dict for member in members)


_STORED_OBJECT = {"time_period": "7d", "snapshot": {"tasks": {"count": 2}}}


@pytest.mark.parametrize("dto_class", _DTOS, ids=_dto_name)
def test_every_dict_field_a_dto_declares_reads_the_stored_json(dto_class: type) -> None:
    """The mapper writes a dict property as JSON text; the DTO must hand the model the dict."""
    hints = typing.get_type_hints(
        dto_class, localns={"date": date, "datetime": datetime, "time": time}
    )
    declared = {field.name for field in dataclasses.fields(dto_class)}
    dict_fields = sorted(name for name in declared if _is_dict(hints[name]))
    if not dict_fields:
        pytest.skip(f"{dto_class.__name__} declares no dict field")
    common = {
        "uid": "x_0123456789abcdef",
        "title": "census",
        "user_uid": "user_0123456789abcdef",
        "entity_type": "task",
    }
    data = {
        key: value
        for key, value in {**common, **_REQUIRED.get(dto_class.__name__, {})}.items()
        if key in declared
    }
    data.update({name: json.dumps(_STORED_OBJECT) for name in dict_fields})

    dto = dto_class.from_dict(data)  # type: ignore[attr-defined]

    left = [name for name in dict_fields if getattr(dto, name) != _STORED_OBJECT]
    assert left == [], f"{dto_class.__name__} leaves stored JSON text in {left}"


def test_a_stored_dict_field_that_is_not_a_json_object_is_refused() -> None:
    from core.models.dto_helpers import ensure_dict_field

    for corrupt in ("{not json", "[1, 2]"):
        with pytest.raises(ValueError, match="metadata"):
            ensure_dict_field({"metadata": corrupt}, "metadata")
    for empty in (None, ""):
        data: dict[str, object] = {"metadata": empty}
        ensure_dict_field(data, "metadata")
        assert data == {"metadata": {}}
