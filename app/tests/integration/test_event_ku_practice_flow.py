"""
Integration Test: Event Completion→Knowledge Practice Event-Driven Updates
===========================================================================

Tests event-driven architecture for Event→knowledge practice tracking, plus the
substance-increment writers' grain contract (ruling 2026-08-21: grain-agnostic —
a knowledge uid may name a Ku or a PathStep, and the write lands on whatever it
names).

This test suite verifies that:
1. CalendarEventCompleted events trigger practice updates
2. PsPracticeService.handle_event_completed() receives events
3. Practice counts are incremented correctly (times_practiced_in_events)
4. Last practiced dates are updated correctly
5. KnowledgePracticed events are published when practice occurs
6. Multiple knowledge entities can be updated from a single event completion
7. Unrelated event completion doesn't affect practice counts
8. KuBackend.increment_substance / batch_increment_substance report every
   landed write (orphan-Ku and PathStep-targeted included) and credit each
   composing PathStep once, however many edge types connect the pair

Event Flow:
-----------
Event completed → CalendarEventCompleted event → PsPracticeService.handle_event_completed()
    → Query Neo4j for (Event)-[:APPLIES_KNOWLEDGE]->(knowledge) → Update practice counts
    → Publish KnowledgePracticed event

APPLIES_KNOWLEDGE is THE Event→knowledge edge (EVENTS_CONFIG registry, Edge-YAML
`connections.applies_knowledge`). The seeds below MERGE the same edge the real
writers write — a seed-and-match guard: if the read in
find_kus_practiced_by_event drifts to an unwritten edge again (the former
[:PRACTICES], 2026-07-10 audit), these tests fail.
"""

from datetime import date, datetime

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.backends.curriculum_backends import KuBackend, PsBackend
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.events.calendar_event_events import CalendarEventCompleted
from core.events.knowledge_substance_events import KnowledgePracticed
from core.models.enums import (
    Domain,
    EntityStatus,
    SELCategory,
)
from core.models.enums.neo_labels import NeoLabel
from core.models.event.event import Event
from core.models.ku.ku import Ku
from core.models.pathways.path_step import PathStep
from core.models.relationship_names import RelationshipName
from core.services.ps.ps_practice_service import PsPracticeService


@pytest.mark.asyncio
class TestEventKuPracticeFlow:
    """Integration tests for Event→KU event-driven practice tracking."""

    @pytest_asyncio.fixture
    async def event_bus(self):
        """Create event bus with history capture and performance monitoring disabled."""
        return InMemoryEventBus(capture_history=True)

    @pytest_asyncio.fixture
    async def ps_backend(self, neo4j_driver, clean_neo4j):
        """Create PathStep backend with clean database.

        Named for what it constructs — the former name ``ku_backend`` was the
        test-side instance of the ku-named-but-grain-agnostic pattern the
        substance-write-grain arc renamed (item C rider, 2026-08-21).
        """
        return PsBackend(neo4j_driver, NeoLabel.PATH_STEP, PathStep, base_label=NeoLabel.ENTITY)

    @pytest_asyncio.fixture
    async def event_backend(self, neo4j_driver, clean_neo4j):
        """Create Event backend with clean database."""
        return UniversalNeo4jBackend[Event](
            neo4j_driver, "Entity", Event, default_filters={"entity_type": "event"}
        )

    @pytest_asyncio.fixture
    async def ku_practice_service(self, event_bus, ps_backend):
        """Create PsPracticeService with event bus and backend."""
        return PsPracticeService(
            backend=ps_backend,  # For Event→knowledge Cypher queries
            event_bus=event_bus,
        )

    @pytest_asyncio.fixture
    async def test_user_uid(self):
        """Standard test user UID."""
        return "user_test_event_ku_flow"

    @pytest_asyncio.fixture
    async def test_user(self, neo4j_driver, test_user_uid):
        """Create test user node in Neo4j."""
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MERGE (u:User {uid: $user_uid})
                ON CREATE SET u.created_at = datetime()
                RETURN u
                """,
                user_uid=test_user_uid,
            )
        return test_user_uid

    @pytest_asyncio.fixture
    async def meditation_event_with_kus(
        self, event_backend, neo4j_driver, ps_backend, test_user_uid, test_user
    ):
        """Create a meditation event that practices 2 PathSteps.

        The practiced entities are PathSteps — the readable substance grain —
        seeded honestly as such (they were formerly PathSteps wearing
        ``ku.``-spelled uids). The event→knowledge edge is grain-agnostic, so
        the Ku-targeted case is covered by TestIncrementSubstanceGrain below.
        """
        kus = []
        for slug, title in [
            ("ps.meditation.mindfulness-breathing", "Mindfulness Breathing"),
            ("ps.meditation.body-scan", "Body Scan Technique"),
        ]:
            ku = PathStep(
                uid=slug,
                title=title,
                domain=Domain.HEALTH,
                sel_category=SELCategory.SELF_AWARENESS,
            )
            result = await ps_backend.create(ku)
            assert result.is_ok
            kus.append(result.value)

        # Create meditation event
        event = Event(
            uid="event.morning_meditation",
            user_uid=test_user_uid,
            title="Morning Meditation Session",
            event_type="learning",
            event_date=date.today(),
            status=EntityStatus.COMPLETED,
        )
        result = await event_backend.create(event)
        assert result.is_ok
        created_event = result.value

        # Add :Event secondary label so production Cypher MATCH (event:Event ...) works
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MATCH (e:Entity {uid: $event_uid, entity_type: 'event'})
                SET e:Event
                """,
                event_uid=event.uid,
            )

        # Create graph relationships: (Event)-[:APPLIES_KNOWLEDGE]->(KU) —
        # the canonical writer-backed Event→Ku edge (matches EVENTS_CONFIG,
        # Edge-YAML ingestion, and the link_event_to_knowledge facade).
        async with neo4j_driver.session() as session:
            for ku in kus:
                await session.run(
                    f"""
                    MATCH (event:Event {{uid: $event_uid}})
                    MATCH (ku:Entity {{uid: $ku_uid}})
                    MERGE (event)-[:{RelationshipName.APPLIES_KNOWLEDGE.value}]->(ku)
                    RETURN event.uid, ku.uid
                    """,
                    event_uid=event.uid,
                    ku_uid=ku.uid,
                )

        return created_event, kus

    # ========================================================================
    # BASIC EVENT FLOW TESTS
    # ========================================================================

    async def test_event_completed_triggers_ku_practice_update(
        self,
        event_bus,
        ku_practice_service,
        neo4j_driver,
        meditation_event_with_kus,
        test_user_uid,
    ):
        """Test that completing an event triggers KU practice update via events."""
        event, kus = meditation_event_with_kus

        # Subscribe to CalendarEventCompleted event
        event_bus.subscribe(CalendarEventCompleted, ku_practice_service.handle_event_completed)

        # Publish CalendarEventCompleted event
        completion_event = CalendarEventCompleted(
            event_uid=event.uid,
            user_uid=test_user_uid,
            completion_date=date.today(),
            quality_score=8,
            occurred_at=datetime.now(),
        )
        await event_bus.publish_async(completion_event)

        # Give event processing time to complete
        import asyncio

        await asyncio.sleep(0.1)

        # Verify KU practice counts were updated
        async with neo4j_driver.session() as session:
            for ku in kus:
                result = await session.run(
                    """
                    MATCH (ku:Entity {uid: $ku_uid})
                    RETURN ku.times_practiced_in_events as count
                    """,
                    ku_uid=ku.uid,
                )
                record = await result.single()
                assert record["count"] == 1, f"KU {ku.uid} practice count should be 1"

    async def test_ku_practice_count_incremented_correctly(
        self,
        event_bus,
        ku_practice_service,
        neo4j_driver,
        meditation_event_with_kus,
        test_user_uid,
    ):
        """Test that KU practice count increments correctly from multiple events."""
        event, kus = meditation_event_with_kus

        event_bus.subscribe(CalendarEventCompleted, ku_practice_service.handle_event_completed)

        # Complete event 3 times (simulate 3 meditation sessions)
        for _ in range(3):
            completion_event = CalendarEventCompleted(
                event_uid=event.uid,
                user_uid=test_user_uid,
                completion_date=date.today(),
                quality_score=8,
                occurred_at=datetime.now(),
            )
            await event_bus.publish_async(completion_event)

        import asyncio

        await asyncio.sleep(0.1)

        # Verify practice count is 3 for both KUs
        async with neo4j_driver.session() as session:
            for ku in kus:
                result = await session.run(
                    """
                    MATCH (ku:Entity {uid: $ku_uid})
                    RETURN ku.times_practiced_in_events as count
                    """,
                    ku_uid=ku.uid,
                )
                record = await result.single()
                assert record["count"] == 3, f"KU {ku.uid} should have 3 practices"

    async def test_knowledge_practiced_event_published(
        self,
        event_bus,
        ku_practice_service,
        meditation_event_with_kus,
        test_user_uid,
    ):
        """Test that KnowledgePracticed event is published when practice occurs."""
        event, _kus = meditation_event_with_kus

        event_bus.subscribe(CalendarEventCompleted, ku_practice_service.handle_event_completed)

        # Publish CalendarEventCompleted event
        completion_event = CalendarEventCompleted(
            event_uid=event.uid,
            user_uid=test_user_uid,
            completion_date=date.today(),
            quality_score=8,
            occurred_at=datetime.now(),
        )
        await event_bus.publish_async(completion_event)

        import asyncio

        await asyncio.sleep(0.1)

        # Verify KnowledgePracticed events were published (one per KU)
        history = event_bus.get_event_history()
        practice_events = [e for e in history if isinstance(e, KnowledgePracticed)]
        assert len(practice_events) == 2, "Should publish 2 KnowledgePracticed events"

        # Verify event details
        for practice_event in practice_events:
            assert practice_event.user_uid == test_user_uid
            assert practice_event.event_uid == event.uid
            assert practice_event.practice_context == "event_completion"
            assert practice_event.times_practiced == 1

    async def test_no_update_when_event_practices_no_kus(
        self,
        event_bus,
        ku_practice_service,
        event_backend,
        test_user_uid,
    ):
        """Test that completing an event with no KUs doesn't affect practice counts."""
        # Create event with no APPLIES_KNOWLEDGE relationships
        event = Event(
            uid="event.no_kus",
            user_uid=test_user_uid,
            title="Event Without KUs",
            event_type="work",
            event_date=date.today(),
            status=EntityStatus.COMPLETED,
        )
        result = await event_backend.create(event)
        assert result.is_ok, "Setup failed: Could not create event"

        event_bus.subscribe(CalendarEventCompleted, ku_practice_service.handle_event_completed)

        # Publish CalendarEventCompleted event
        completion_event = CalendarEventCompleted(
            event_uid=event.uid,
            user_uid=test_user_uid,
            completion_date=date.today(),
            quality_score=None,
            occurred_at=datetime.now(),
        )
        await event_bus.publish_async(completion_event)

        import asyncio

        await asyncio.sleep(0.1)

        # Verify no KnowledgePracticed events
        history = event_bus.get_event_history()
        practice_events = [e for e in history if isinstance(e, KnowledgePracticed)]
        assert len(practice_events) == 0, "Should not publish practice events"

    async def test_multiple_kus_updated_from_single_event(
        self,
        event_bus,
        ku_practice_service,
        neo4j_driver,
        meditation_event_with_kus,
        test_user_uid,
    ):
        """Test that a single event can update multiple KUs."""
        event, kus = meditation_event_with_kus

        event_bus.subscribe(CalendarEventCompleted, ku_practice_service.handle_event_completed)

        # Publish CalendarEventCompleted event
        completion_event = CalendarEventCompleted(
            event_uid=event.uid,
            user_uid=test_user_uid,
            completion_date=date.today(),
            quality_score=9,
            occurred_at=datetime.now(),
        )
        await event_bus.publish_async(completion_event)

        import asyncio

        await asyncio.sleep(0.1)

        # Verify both KUs were updated
        async with neo4j_driver.session() as session:
            result = await session.run(
                """
                MATCH (ku:Entity)
                WHERE ku.times_practiced_in_events > 0
                RETURN count(ku) as updated_count
                """
            )
            record = await result.single()
            assert record["updated_count"] == 2, "Both KUs should have practice counts"

        # Verify 2 KnowledgePracticed events published
        history = event_bus.get_event_history()
        practice_events = [e for e in history if isinstance(e, KnowledgePracticed)]
        assert len(practice_events) == 2

        # Verify both knowledge UIDs are represented
        practiced_knowledge_uids = {e.knowledge_uid for e in practice_events}
        expected_knowledge_uids = {ku.uid for ku in kus}
        assert practiced_knowledge_uids == expected_knowledge_uids

    async def test_last_practiced_date_updated(
        self,
        event_bus,
        ku_practice_service,
        neo4j_driver,
        meditation_event_with_kus,
        test_user_uid,
    ):
        """Test that last_practiced_date is updated when event is completed."""
        event, kus = meditation_event_with_kus

        event_bus.subscribe(CalendarEventCompleted, ku_practice_service.handle_event_completed)

        occurred_at = datetime.now()

        # Publish CalendarEventCompleted event
        completion_event = CalendarEventCompleted(
            event_uid=event.uid,
            user_uid=test_user_uid,
            completion_date=date.today(),
            quality_score=8,
            occurred_at=occurred_at,
        )
        await event_bus.publish_async(completion_event)

        import asyncio

        await asyncio.sleep(0.1)

        # Verify last_practiced_date was set
        async with neo4j_driver.session() as session:
            for ku in kus:
                result = await session.run(
                    """
                    MATCH (ku:Entity {uid: $ku_uid})
                    RETURN ku.last_practiced_date as last_date
                    """,
                    ku_uid=ku.uid,
                )
                record = await result.single()
                assert record["last_date"] is not None, (
                    f"KU {ku.uid} should have last_practiced_date set"
                )


@pytest.mark.asyncio
class TestIncrementSubstanceGrain:
    """Grain contract of KuBackend.increment_substance / batch_increment_substance.

    Pins the three-row table from the substance-write-grain arc (2026-08-21):
    the uid may name an orphan Ku, a composed Ku, or a PathStep, and in every
    case the write lands AND is reported. Before the fix, ``WHERE ps IS NOT
    NULL`` gated the RETURN, so the orphan-Ku and PathStep-targeted rows
    reported ``ok(0)`` for an increment that had already been written — and a
    PathStep composing the same Ku via two edge types was credited twice.
    """

    METRIC = "times_practiced_in_events"
    TS_FIELD = "last_practiced_date"

    @pytest_asyncio.fixture
    async def ku_backend(self, neo4j_driver, clean_neo4j):
        """Create a real Ku backend (label :Ku) with clean database."""
        return KuBackend(neo4j_driver, NeoLabel.KU, Ku, base_label=NeoLabel.ENTITY)

    @pytest_asyncio.fixture
    async def ps_backend(self, neo4j_driver, clean_neo4j):
        """Create PathStep backend with clean database."""
        return PsBackend(neo4j_driver, NeoLabel.PATH_STEP, PathStep, base_label=NeoLabel.ENTITY)

    async def _counter(self, neo4j_driver, uid: str) -> int | None:
        async with neo4j_driver.session() as session:
            result = await session.run(
                f"MATCH (e:Entity {{uid: $uid}}) RETURN e.{self.METRIC} AS n",
                uid=uid,
            )
            record = await result.single()
            return record["n"]

    async def _link(self, neo4j_driver, ps_uid: str, ku_uid: str, edge: str) -> None:
        """Seed-and-match: MERGE the same composition edge the ingestion writers write."""
        async with neo4j_driver.session() as session:
            await session.run(
                f"""
                MATCH (ps:Entity {{uid: $ps_uid}})
                MATCH (ku:Entity {{uid: $ku_uid}})
                MERGE (ps)-[:{edge}]->(ku)
                """,
                ps_uid=ps_uid,
                ku_uid=ku_uid,
            )

    async def test_orphan_ku_write_lands_and_is_reported(self, ku_backend, neo4j_driver):
        """An orphan Ku (no composing PathStep) is the majority live case — the
        write must land on the Ku and the returned count must say so."""
        ku = Ku(uid="ku.test.orphan-atom", title="Orphan Atom")
        create = await ku_backend.create(ku)
        assert create.is_ok

        result = await ku_backend.increment_substance(
            knowledge_uid=ku.uid,
            metric=self.METRIC,
            timestamp_field=self.TS_FIELD,
            timestamp_str=datetime.now().isoformat(),
        )
        assert result.is_ok
        assert result.value == 1, "landed write must be reported, not ok(0)"
        assert await self._counter(neo4j_driver, ku.uid) == 1

    async def test_pathstep_targeted_write_lands_and_is_reported(
        self, ps_backend, ku_backend, neo4j_driver
    ):
        """'I practised this lesson' is a real fact — a PathStep-targeted
        write lands on the PathStep and is reported (no roll-up: nothing
        composes a PathStep)."""
        step = PathStep(uid="ps.test.lesson-direct", title="Direct Lesson")
        create = await ps_backend.create(step)
        assert create.is_ok

        result = await ku_backend.increment_substance(
            knowledge_uid=step.uid,
            metric=self.METRIC,
            timestamp_field=self.TS_FIELD,
            timestamp_str=datetime.now().isoformat(),
        )
        assert result.is_ok
        assert result.value == 1, "landed write must be reported, not ok(0)"
        assert await self._counter(neo4j_driver, step.uid) == 1

    async def test_composed_ku_credits_each_pathstep_once(
        self, ku_backend, ps_backend, neo4j_driver
    ):
        """Composing PathSteps are credited once each — including one that
        composes the same Ku via TWO edge types (formerly double-credited)."""
        ku = Ku(uid="ku.test.composed-atom", title="Composed Atom")
        assert (await ku_backend.create(ku)).is_ok
        single = PathStep(uid="ps.test.single-edge", title="Single-Edge Composer")
        dual = PathStep(uid="ps.test.dual-edge", title="Dual-Edge Composer")
        assert (await ps_backend.create(single)).is_ok
        assert (await ps_backend.create(dual)).is_ok
        await self._link(neo4j_driver, single.uid, ku.uid, RelationshipName.USES_KU.value)
        await self._link(neo4j_driver, dual.uid, ku.uid, RelationshipName.USES_KU.value)
        await self._link(neo4j_driver, dual.uid, ku.uid, RelationshipName.CONTAINS_KNOWLEDGE.value)

        result = await ku_backend.increment_substance(
            knowledge_uid=ku.uid,
            metric=self.METRIC,
            timestamp_field=self.TS_FIELD,
            timestamp_str=datetime.now().isoformat(),
        )
        assert result.is_ok
        assert result.value == 1
        assert await self._counter(neo4j_driver, ku.uid) == 1
        assert await self._counter(neo4j_driver, single.uid) == 1
        assert await self._counter(neo4j_driver, dual.uid) == 1, (
            "a PathStep composing via two edge types must be credited once"
        )

    async def test_unknown_uid_is_a_true_noop(self, ku_backend):
        """ok(0) now means exactly one thing: the uid matched no node."""
        result = await ku_backend.increment_substance(
            knowledge_uid="ku.test.does-not-exist",
            metric=self.METRIC,
            timestamp_field=self.TS_FIELD,
            timestamp_str=datetime.now().isoformat(),
        )
        assert result.is_ok
        assert result.value == 0

    async def test_batch_lands_on_orphan_and_composed_alike(
        self, ku_backend, ps_backend, neo4j_driver
    ):
        """Batch: the orphan's primary write lands even though only the
        composed Ku produces a PathStep credit."""
        orphan = Ku(uid="ku.test.batch-orphan", title="Batch Orphan")
        composed = Ku(uid="ku.test.batch-composed", title="Batch Composed")
        step = PathStep(uid="ps.test.batch-composer", title="Batch Composer")
        assert (await ku_backend.create(orphan)).is_ok
        assert (await ku_backend.create(composed)).is_ok
        assert (await ps_backend.create(step)).is_ok
        await self._link(neo4j_driver, step.uid, composed.uid, RelationshipName.USES_KU.value)

        result = await ku_backend.batch_increment_substance(
            knowledge_uids=[orphan.uid, composed.uid],
            metric=self.METRIC,
            timestamp_field=self.TS_FIELD,
            timestamp_str=datetime.now().isoformat(),
        )
        assert result.is_ok
        assert result.value == 1, "one PathStep credit (the composed Ku's composer)"
        assert await self._counter(neo4j_driver, orphan.uid) == 1
        assert await self._counter(neo4j_driver, composed.uid) == 1
        assert await self._counter(neo4j_driver, step.uid) == 1
