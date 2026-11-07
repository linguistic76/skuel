"""The DTO path reads the driver's temporal types as the mapper does.

A node read raw from the graph carries the driver's own temporals: the mapper writes
a ``time`` as a native LOCAL TIME (an Event's ``start_time``), and Cypher
``datetime()`` stamps a native (bulk upsert's ``updated_at`` on re-ingest, the
exercise backend's stamps). The search, traversal and range reads turn those
records into models through ``to_domain_model`` (``{Domain}DTO.from_dict`` →
``from_dto``), the by-uid reads through ``from_neo4j_node``. These tests hand both
paths the same raw Event record and pin that they agree, field by field, and that
the result serializes at the JSON boundary, which refuses a driver temporal.

The route-level proof is ``tests/integration/routes/test_dto_path_driver_temporals.py``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
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
