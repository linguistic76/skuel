"""Persistence-side readers of stored instants, in ``adapters/persistence/``.

A stored instant arrives in several shapes: an offset-less string (UTC digits),
an offset string, a Neo4j native, a ``datetime`` naive or aware. A reader here
sorts them as instants and takes a moment's day in the current zone, never its
digits' day.

See: /docs/roadmap/utc-instants-arc.md § PR 6
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest
from neo4j.time import DateTime as Neo4jDateTime

from adapters.persistence.neo4j._search_mixin import _range_day
from adapters.persistence.neo4j.user_context_queries import _sort_by_last_viewed_at
from core.utils.zone_context import current_zone_var


@pytest.fixture
def vancouver_user() -> Iterator[None]:
    """The current zone is a Vancouver user's."""
    token = current_zone_var.set(ZoneInfo("America/Vancouver"))
    try:
        yield
    finally:
        current_zone_var.reset(token)


@pytest.mark.usefixtures("vancouver_user")
class TestRecentlyViewedOrder:
    def test_views_sort_newest_first_across_shapes(self) -> None:
        views = [
            {"uid": "ku_naive", "last_viewed_at": datetime(2026, 9, 15, 12, 0)},
            {
                "uid": "ku_native",
                "last_viewed_at": Neo4jDateTime.from_native(
                    datetime(2026, 9, 15, 14, 0, tzinfo=UTC)
                ),
            },
            {"uid": "ku_aware", "last_viewed_at": datetime(2026, 9, 15, 13, 0, tzinfo=UTC)},
            {"uid": "ku_string", "last_viewed_at": "2026-09-15T11:00:00+00:00"},
        ]

        ordered = sorted(views, key=_sort_by_last_viewed_at, reverse=True)

        assert [v["uid"] for v in ordered] == ["ku_native", "ku_aware", "ku_naive", "ku_string"]


@pytest.mark.usefixtures("vancouver_user")
class TestRangeDay:
    def test_a_day_is_itself(self) -> None:
        assert _range_day(date(2026, 9, 15)) == date(2026, 9, 15)
        assert _range_day("2026-09-15") == date(2026, 9, 15)

    def test_a_moment_names_its_day_in_the_zone_not_its_digits(self) -> None:
        """03:00Z on the 15th is the evening of the 14th in Vancouver."""
        assert _range_day(datetime(2026, 9, 15, 3, 0, tzinfo=UTC)) == date(2026, 9, 14)
        assert _range_day("2026-09-15T03:00:00Z") == date(2026, 9, 14)

    def test_an_unreadable_value_raises(self) -> None:
        with pytest.raises(ValueError):
            _range_day("mid-September")
