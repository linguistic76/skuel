"""
Real-Neo4j guard for the Goals period-analytics window.
=======================================================

``GoalsIntelligenceService.get_performance_analytics`` fetched its window with
``find_by(user_uid=..., updated_at__gte=cutoff.isoformat())`` — a bare ``>=`` against a
**string** bound.

This is not #859's failure mode. There the key was dropped by ``build_search_query`` and the
query over-returned. Here ``updated_at`` is a real ``Goal`` field, so the predicate was
emitted exactly as written; the defect is that ``updated_at`` holds two different Neo4j
types and ``<temporal> >= <string>`` evaluates to **null**, not false. Those rows were
silently dropped, and the endpoint answered with a plausible number that was simply too low.

Which is why the obvious test does not work. "Seed goals, assert non-empty" **passes against
this bug** — it under-returns rather than zeroing, so the assertion is satisfied by the rows
that survived. The guard has to be a row that must be *included* and was not.

So the two in-window goals here are seeded through the two real writers, not through
hand-written Cypher that merely resembles them:

  * ``goal.win_crud_string`` — last written by ``UniversalNeo4jBackend.update``, whose
    ``_crud_mixin`` stamp is ``datetime.now().isoformat()``: an ISO **string**.
  * ``goal.win_bulk_temporal`` — last written by ``BulkUpsertBackend.upsert_nodes``, whose
    template sets ``n.updated_at = datetime()`` on ``ON MATCH``: a native **temporal**.
    ``Goal`` carries an ``EntityIngestionConfig``, so this is the shape of any goal whose
    last write came from a vault re-ingest, and the config used below is the production one.

``TestSeededStorageShapesReallyDiffer`` runs first for a reason. If the bulk path ever stops
producing a temporal, every assertion in this module would still pass — while testing
nothing. That class reads the raw property back off the driver and pins the two types, so
the premise fails loudly instead of the suite passing vacuously.

The third goal is 200 days stale and must be **excluded** — without it, a fix that dropped
the window entirely would pass. Counts below are 2, not 3; pre-fix they were 1.

See: tests/unit/services/goals/test_goals_analytics_window.py (the cheap half + the
     tree-wide guard for the still-unimplemented siblings)
     tests/integration/test_created_at_window_coercion.py (the same mixed column,
     on ``created_at``)
     docs/reference/PLACEHOLDER_INDEX.md § Group A
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from neo4j.time import DateTime as Neo4jDateTime

from adapters.persistence.neo4j.bulk_upsert_backend import BulkUpsertBackend
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.goal.goal import Goal
from core.services.activity_domain_config import ACTIVITY_DOMAIN_CONFIGS
from core.services.goals.goals_intelligence_service import GoalsIntelligenceService
from core.services.ingestion.config import ENTITY_CONFIGS
from core.services.relationships import UnifiedRelationshipService

USER = "user_goal_window"

CRUD_STRING = "goal.win_crud_string"  # updated_at: ISO string, via the CRUD update path
BULK_TEMPORAL = "goal.win_bulk_temporal"  # updated_at: native temporal, via ON MATCH
OUT_OF_WINDOW = "goal.win_out_of_window"  # updated_at: ISO string, 200 days ago

STALE_DAYS = 200
GOAL_CONFIG = ENTITY_CONFIGS[EntityType.GOAL]


def _goal(uid: str, title: str, updated_at: datetime) -> Goal:
    """A minimal in-window-eligible goal. ``__post_init__`` leaves ``updated_at`` alone.

    ``status`` is set explicitly: ``EntityType.GOAL.default_status()`` is ``DRAFT``, so
    relying on the default would make ``active_goals`` 0 for every seeded row and quietly
    cost this module one of its two independent reads of the window.
    """
    return Goal(
        uid=uid,
        user_uid=USER,
        title=title,
        description="Goals analytics window fixture",
        progress_percentage=50.0,
        status=EntityStatus.ACTIVE,
        updated_at=updated_at,
    )


async def _seed(neo4j_driver) -> None:
    """Seed three goals, each through the writer whose storage shape it represents."""
    now = datetime.now()
    backend = UniversalNeo4jBackend[Goal](
        neo4j_driver, NeoLabel.GOAL, Goal, base_label=NeoLabel.ENTITY
    )

    async with neo4j_driver.session() as session:
        await session.run("MERGE (u:User {uid: $u})", u=USER)

    for uid, title, updated_at in (
        (CRUD_STRING, "In window (CRUD string)", now),
        (BULK_TEMPORAL, "In window (bulk temporal)", now),
        (OUT_OF_WINDOW, "Out of window", now - timedelta(days=STALE_DAYS)),
    ):
        created = await backend.create(_goal(uid, title, updated_at))
        assert created.is_ok, f"seed create failed for {uid}: {created}"

    # Shape 1: the CRUD write path stamps updated_at as datetime.now().isoformat().
    touched = await backend.update(CRUD_STRING, {"description": "touched via CRUD"})
    assert touched.is_ok, f"seed update failed: {touched}"

    # Shape 2: the vault re-ingest path. The node already exists, so ON MATCH fires and
    # overwrites updated_at with a native temporal. Production config, production labels.
    bulk = BulkUpsertBackend(neo4j_driver)
    reingested = await bulk.upsert_nodes(
        entity_label=GOAL_CONFIG.entity_label,
        base_label=GOAL_CONFIG.base_label,
        entities=[
            {
                "uid": BULK_TEMPORAL,
                "user_uid": USER,
                "entity_type": EntityType.GOAL.value,
                "title": "In window (bulk temporal)",
                "description": "re-ingested from the vault",
            }
        ],
        relationship_config=GOAL_CONFIG.relationship_config or {},
    )
    assert reingested.is_ok, f"seed bulk upsert failed: {reingested}"


async def _read_raw_updated_at(neo4j_driver, uid: str) -> Any:
    """The ``updated_at`` property as the driver hands it back, un-coerced."""
    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (n:Goal {uid: $uid}) RETURN n.updated_at AS updated_at", uid=uid
        )
        record = await result.single()
    assert record is not None, f"{uid} was not seeded"
    return record["updated_at"]


def _intelligence(neo4j_driver) -> GoalsIntelligenceService:
    """Built the way services_bootstrap builds it — production label pair and config."""
    backend = UniversalNeo4jBackend[Goal](
        neo4j_driver, NeoLabel.GOAL, Goal, base_label=NeoLabel.ENTITY
    )
    relationships: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
        backend=backend,
        config=ACTIVITY_DOMAIN_CONFIGS["goals"].relationship_config,
        graph_intel=None,
    )
    # _require_relationships = True, so the constructor refuses without this. The method
    # under test reads no edges, but construction must be the production shape.
    return GoalsIntelligenceService(backend=backend, relationship_service=relationships)


@pytest.mark.asyncio
class TestSeededStorageShapesReallyDiffer:
    """The premise. Without this, the whole module could pass while testing one shape."""

    @pytest_asyncio.fixture
    async def seeded(self, neo4j_driver, clean_neo4j):
        await _seed(neo4j_driver)
        return neo4j_driver

    async def test_crud_path_stores_updated_at_as_an_iso_string(self, seeded) -> None:
        """``_crud_mixin.update`` writes ``datetime.now().isoformat()``."""
        value = await _read_raw_updated_at(seeded, CRUD_STRING)

        assert isinstance(value, str), (
            f"expected the CRUD path to store an ISO string, got {type(value).__name__}"
        )

    async def test_bulk_reingest_stores_updated_at_as_a_native_temporal(self, seeded) -> None:
        """``ON MATCH SET n.updated_at = datetime()`` writes a real temporal.

        This is the shape the bare ``>=`` could not compare against. If this assertion
        ever fails, the defect this module guards has changed shape — do not relax it.
        """
        value = await _read_raw_updated_at(seeded, BULK_TEMPORAL)

        assert isinstance(value, Neo4jDateTime), (
            f"expected the bulk re-ingest path to store a temporal, "
            f"got {type(value).__name__} — the mixed-representation premise no longer holds"
        )

    async def test_the_two_shapes_are_not_the_same_type(self, seeded) -> None:
        """Stated directly, so the failure message names the actual problem."""
        crud = await _read_raw_updated_at(seeded, CRUD_STRING)
        bulk = await _read_raw_updated_at(seeded, BULK_TEMPORAL)

        assert type(crud) is not type(bulk), (
            "both writers produced the same type — this module is no longer exercising "
            "a mixed-representation column"
        )


@pytest.mark.asyncio
class TestGoalsPerformanceAnalyticsWindow:
    """The window must admit both storage shapes and exclude the stale goal."""

    @pytest_asyncio.fixture
    async def intelligence(self, neo4j_driver, clean_neo4j):
        await _seed(neo4j_driver)
        return _intelligence(neo4j_driver)

    async def test_window_includes_both_storage_shapes(self, intelligence) -> None:
        """The headline guard. Pre-fix: 1 — the temporally-stored goal was dropped.

        Note what "assert non-empty" would have done here: passed, on a count of 1.
        """
        result = await intelligence.get_performance_analytics(USER, period_days=30)
        assert result.is_ok, f"get_performance_analytics failed: {result}"

        assert result.value["total_goals"] == 2, (
            "1 = the bulk-re-ingested goal was dropped (string bound vs temporal value); "
            "3 = the window was not applied at all"
        )

    async def test_stale_goal_is_excluded(self, intelligence) -> None:
        """The negative control that makes the count above meaningful."""
        result = await intelligence.get_performance_analytics(USER, period_days=30)
        assert result.is_ok, f"get_performance_analytics failed: {result}"

        # Both in-window goals carry progress_percentage=50.0; the stale one does too, so
        # avg_progress cannot distinguish them — the count is what does.
        assert result.value["analytics"]["total"] == 2
        assert result.value["active_goals"] == 2

    async def test_widening_the_window_admits_the_stale_goal(self, intelligence) -> None:
        """``period_days`` is live in both directions.

        The pair is the point: a single count could be produced by a hardcoded limit, and
        pre-fix *both* calls returned 1 regardless of the window.
        """
        narrow = await intelligence.get_performance_analytics(USER, period_days=30)
        wide = await intelligence.get_performance_analytics(USER, period_days=365)

        assert narrow.is_ok and wide.is_ok
        assert narrow.value["total_goals"] == 2
        assert wide.value["total_goals"] == 3

    async def test_window_is_scoped_to_the_owner(self, intelligence, neo4j_driver) -> None:
        """``additional_filters`` must still carry ``user_uid``.

        ``find_by_date_range`` matches on the label first, so losing the owner filter
        would leak every user's goals into one user's analytics. The old ``find_by``
        carried this scoping; the replacement has to keep it.
        """
        other_backend = UniversalNeo4jBackend[Goal](
            neo4j_driver, NeoLabel.GOAL, Goal, base_label=NeoLabel.ENTITY
        )
        async with neo4j_driver.session() as session:
            await session.run("MERGE (u:User {uid: 'user_goal_window_other'})")
        intruder = Goal(
            uid="goal.win_other_user",
            user_uid="user_goal_window_other",
            title="Another user's in-window goal",
            progress_percentage=50.0,
            updated_at=datetime.now(),
        )
        created = await other_backend.create(intruder)
        assert created.is_ok, f"intruder seed failed: {created}"

        result = await intelligence.get_performance_analytics(USER, period_days=30)
        assert result.is_ok, f"get_performance_analytics failed: {result}"

        assert result.value["total_goals"] == 2, (
            "3 = the intruder leaked in (owner filter lost); 1 = the coercion regressed, "
            "which this test cannot distinguish — read the headline test's verdict first"
        )
