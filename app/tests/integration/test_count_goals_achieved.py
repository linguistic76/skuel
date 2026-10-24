"""GoalsBackend.count_goals_achieved — the aggregation tool's one query, on a real graph.

Tool-selection first slice (docs/roadmap/askesis-tool-selection-queries.md § 3).
What only a database can settle:

1. The :OWNS edge in the MATCH scopes the count structurally — another user's
   achieved goals are invisible even to a query that names their dates.
2. ``achieved_date`` is persisted as a date-shaped ISO STRING, and both bounds
   are bound as the same shape, so a same-day ``until`` is INCLUSIVE — the
   lexicographic trap that bites datetime-backed domains does not bite here,
   and this pins that it stays true.
3. Open bounds (None) mean unbounded, not "match nothing".
"""

from __future__ import annotations

from datetime import date

import pytest
import pytest_asyncio
from neo4j import AsyncDriver

from adapters.persistence.neo4j.backends.activity_backends import GoalsBackend
from core.models.enums import EntityStatus
from core.models.goal.goal import Goal
from tests.helpers.production_backends import build_production_backends
from tests.helpers.seed_uids import seed_user_uid

USER = seed_user_uid("agg_count")
OTHER = seed_user_uid("agg_other")


@pytest.mark.asyncio
class TestCountGoalsAchieved:
    @pytest_asyncio.fixture
    async def backend(self, neo4j_driver: AsyncDriver, clean_neo4j: None) -> GoalsBackend:
        # Mirror the production construction (services_bootstrap/_backends.py):
        # multi-label :Entity:Goal nodes — the count's MATCH is on (g:Goal), so
        # a test backend that wrote bare :Entity nodes would pass vacuously.
        return build_production_backends(neo4j_driver)["goals_backend"]

    async def _seed_achieved(
        self, backend: GoalsBackend, uid: str, achieved: str, user_uid: str = USER
    ) -> None:
        created = await backend.create(
            Goal(
                uid=uid,
                user_uid=user_uid,
                title=f"goal {uid}",
                status=EntityStatus.COMPLETED,
                achieved_date=date.fromisoformat(achieved),
            )
        )
        assert created.is_ok, created.error

    async def test_counts_are_owner_scoped_by_the_owns_edge(self, backend: GoalsBackend) -> None:
        await self._seed_achieved(backend, "goal.agg-mine-1", "2026-05-10")
        await self._seed_achieved(backend, "goal.agg-mine-2", "2026-06-30")
        await self._seed_achieved(backend, "goal.agg-theirs", "2026-05-10", user_uid=OTHER)

        result = await backend.count_goals_achieved(
            user_uid=USER, since=date(2026, 4, 1), until=date(2026, 6, 30)
        )

        assert result.is_ok
        assert result.value["total"] == 2, (
            "the other user's goal leaked into (or mine leaked out of) an :OWNS-scoped count"
        )
        # the applied bounds survive the call — the answer states its scope
        assert result.value["since"] == "2026-04-01"
        assert result.value["until"] == "2026-06-30"

    async def test_same_day_until_bound_is_inclusive(self, backend: GoalsBackend) -> None:
        """A goal achieved ON the until date is counted (date-shaped ISO strings
        compare lexicographically AND chronologically here — § 3's trap is for
        datetime-backed siblings, pinned absent on this one)."""
        await self._seed_achieved(backend, "goal.agg-on-bound", "2026-06-30")

        result = await backend.count_goals_achieved(
            user_uid=USER, since=date(2026, 6, 30), until=date(2026, 6, 30)
        )

        assert result.is_ok
        assert result.value["total"] == 1

    async def test_open_bounds_mean_unbounded(self, backend: GoalsBackend) -> None:
        await self._seed_achieved(backend, "goal.agg-old", "2020-01-01")
        await self._seed_achieved(backend, "goal.agg-new", "2026-08-01")

        unbounded = await backend.count_goals_achieved(user_uid=USER)
        since_only = await backend.count_goals_achieved(user_uid=USER, since=date(2026, 1, 1))
        until_only = await backend.count_goals_achieved(user_uid=USER, until=date(2020, 12, 31))

        assert unbounded.is_ok and unbounded.value["total"] == 2
        assert since_only.is_ok and since_only.value["total"] == 1
        assert until_only.is_ok and until_only.value["total"] == 1
        assert unbounded.value["since"] is None and unbounded.value["until"] is None

    async def test_unachieved_goals_do_not_count(self, backend: GoalsBackend) -> None:
        created = await backend.create(
            Goal(uid="goal.agg-open", user_uid=USER, title="open", status=EntityStatus.ACTIVE)
        )
        assert created.is_ok

        result = await backend.count_goals_achieved(user_uid=USER)

        assert result.is_ok
        assert result.value["total"] == 0
