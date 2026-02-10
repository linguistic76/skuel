"""
Integration Test: Event Completion→Knowledge Practice Event-Driven Updates
===========================================================================

Tests Phase 4 event-driven architecture for Event→KU practice tracking.

This test suite verifies that:
1. CalendarEventCompleted events trigger KU practice updates
2. KuPracticeService.handle_event_completed() receives events
3. KU practice counts are incremented correctly (times_practiced_in_events)
4. Last practiced dates are updated correctly
5. KnowledgePracticed events are published when practice occurs
6. Multiple KUs can be updated from a single event completion
7. Unrelated event completion doesn't affect KU practice counts

Event Flow:
-----------
Event completed → CalendarEventCompleted event → KuPracticeService.handle_event_completed()
    → Query Neo4j for (Event)-[:PRACTICES]->(KU) → Update KU practice counts
    → Publish KnowledgePracticed event
"""

from datetime import date, datetime

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.events.calendar_event_events import CalendarEventCompleted
from core.events.ku_events import KnowledgePracticed
from core.models.enums import (
    ActivityStatus,
    Domain,
    SELCategory,
)
from core.models.event.event import Event
from core.models.ku.ku import Ku
from core.services.ku.ku_practice_service import KuPracticeService


@pytest.mark.asyncio
class TestEventKuPracticeFlow:
    """Integration tests for Event→KU event-driven practice tracking."""

    @pytest_asyncio.fixture
    async def event_bus(self):
        """Create event bus with history capture and performance monitoring disabled."""
        return InMemoryEventBus(capture_history=True)

    @pytest_asyncio.fixture
    async def ku_backend(self, neo4j_driver, clean_neo4j):
        """Create KU backend with clean database."""
        return UniversalNeo4jBackend[Ku](neo4j_driver, "Ku", Ku)

    @pytest_asyncio.fixture
    async def event_backend(self, neo4j_driver, clean_neo4j):
        """Create Event backend with clean database."""
        return UniversalNeo4jBackend[Event](neo4j_driver, "Event", Event)

    @pytest_asyncio.fixture
    async def ku_practice_service(self, event_bus, neo4j_driver):
        """Create KuPracticeService with event bus and driver."""
        return KuPracticeService(
            driver=neo4j_driver,  # Phase 4: For Event→KU Cypher queries
            event_bus=event_bus,
        )

    @pytest_asyncio.fixture
    async def test_user_uid(self):
        """Standard test user UID."""
        return "user.test_event_ku_flow"

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
        self, event_backend, neo4j_driver, ku_backend, test_user_uid, test_user
    ):
        """Create a meditation event that practices 2 KUs."""
        # Create 2 KUs related to meditation
        kus = []
        for i, title in enumerate(["Mindfulness Breathing", "Body Scan Technique"], start=1):
            ku = Ku(
                uid=f"ku.meditation_{i}",
                title=title,
                domain=Domain.HEALTH,
                sel_category=SELCategory.SELF_AWARENESS,
            )
            result = await ku_backend.create(ku)
            assert result.is_ok
            kus.append(result.value)

        # Create meditation event
        event = Event(
            uid="event.morning_meditation",
            user_uid=test_user_uid,
            title="Morning Meditation Session",
            event_type="LEARNING",
            event_date=date.today(),
            status=ActivityStatus.COMPLETED,
        )
        result = await event_backend.create(event)
        assert result.is_ok
        created_event = result.value

        # Create graph relationships: (Event)-[:PRACTICES]->(KU)
        async with neo4j_driver.session() as session:
            for ku in kus:
                await session.run(
                    """
                    MATCH (event:Event {uid: $event_uid})
                    MATCH (ku:Ku {uid: $ku_uid})
                    MERGE (event)-[:PRACTICES]->(ku)
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
                    MATCH (ku:Ku {uid: $ku_uid})
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
                    MATCH (ku:Ku {uid: $ku_uid})
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
        event, kus = meditation_event_with_kus

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
        # Create event with no PRACTICES relationships
        event = Event(
            uid="event.no_kus",
            user_uid=test_user_uid,
            title="Event Without KUs",
            event_type="WORK",
            event_date=date.today(),
            status=ActivityStatus.COMPLETED,
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
                MATCH (ku:Ku)
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

        # Verify both KU UIDs are represented
        practiced_ku_uids = {e.ku_uid for e in practice_events}
        expected_ku_uids = {ku.uid for ku in kus}
        assert practiced_ku_uids == expected_ku_uids

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
                    MATCH (ku:Ku {uid: $ku_uid})
                    RETURN ku.last_practiced_date as last_date
                    """,
                    ku_uid=ku.uid,
                )
                record = await result.single()
                assert record["last_date"] is not None, (
                    f"KU {ku.uid} should have last_practiced_date set"
                )
