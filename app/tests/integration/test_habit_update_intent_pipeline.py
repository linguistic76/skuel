"""
Integration Test: Habit Update Intent pipeline (ADR-066 Phase 6)
================================================================

Verifies the typed ``HabitUpdateIntent`` update path end to end against live Neo4j:

1. ``update_habit(intent)`` materializes only the set fields at the single
   ``backend.update`` seam — a partial update does NOT clobber untouched columns.
2. A ``HabitUpdated`` event fires on the intent path (cache invalidation contract).
3. A status transition expressed as an intent persists and fires ``HabitUpdated``.
4. Habits' live ``_validate_update`` runs on the typed path: archiving a habit with a
   ``current_streak >= 7`` is BLOCKED without ``force_archive`` and SUCCEEDS with it — and
   ``force_archive`` is never persisted as a node column.
5. ``HabitUpdateRequest.to_intent()`` carries exactly the explicitly-set fields
   (``model_fields_set``), lowers enums, and drops the four cross-domain edge UIDs.

Mirrors ``test_goal_update_intent_pipeline.py`` (Phase 2) for the Habits domain — the
last Activity Domain to adopt the pattern.
"""

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.events import HabitUpdated
from core.models.enums import Priority, RecurrencePattern
from core.models.enums.entity_enums import EntityStatus
from core.models.enums.habit_enums import HabitCategory, HabitDifficulty
from core.models.habit.habit import Habit
from core.models.habit.habit_request import HabitUpdateRequest
from core.models.habit.habit_update_intent import HabitUpdateIntent
from core.models.sentinels import UNSET
from core.services.habits.habits_core_service import HabitsCoreService


@pytest.mark.asyncio
class TestHabitUpdateIntentPipeline:
    """Live-Neo4j checks for the ADR-066 typed update path (Habits)."""

    @pytest_asyncio.fixture
    async def event_bus(self):
        return InMemoryEventBus(capture_history=True)

    @pytest_asyncio.fixture
    async def habits_backend(self, neo4j_driver, clean_neo4j):
        return UniversalNeo4jBackend[Habit](
            neo4j_driver, "Entity", Habit, default_filters={"entity_type": "habit"}
        )

    @pytest_asyncio.fixture
    async def core_service(self, habits_backend, event_bus):
        return HabitsCoreService(backend=habits_backend, event_bus=event_bus)

    @staticmethod
    async def _persisted_node_keys(neo4j_driver, uid: str) -> set[str]:
        """Return the raw Neo4j property keys on the node — the honest persistence check.

        ``hasattr(habit, "force_archive")`` is vacuous (Habit is a fixed frozen dataclass
        with no such field, so it is always False regardless of what Neo4j stored, and it
        trips SKUEL011); reading the node's actual keys verifies the transient directive was
        never written as a column.
        """
        async with neo4j_driver.session() as session:
            result = await session.run("MATCH (n {uid: $uid}) RETURN keys(n) AS keys", uid=uid)
            record = await result.single()
        return set(record["keys"]) if record else set()

    @pytest_asyncio.fixture
    async def seeded_habit(self, core_service):
        # current_streak=10 so the streak-preservation rule (>= 7) is exercisable.
        habit = Habit(
            uid="habit.intent_pipeline",
            user_uid="user_intent_pipeline",
            title="Original title",
            description="Original description",
            recurrence_pattern=RecurrencePattern.DAILY,
            target_days_per_week=5,
            duration_minutes=15,
            priority=Priority.MEDIUM,
            current_streak=10,
            status=EntityStatus.ACTIVE,
        )
        result = await core_service.create(habit)
        assert result.is_ok
        return result.value

    async def test_partial_intent_writes_only_set_fields(
        self, core_service, seeded_habit, event_bus
    ) -> None:
        """A partial intent updates title only — description/priority/duration survive."""
        event_bus.clear_event_history()
        intent = HabitUpdateIntent(title="Updated title")

        result = await core_service.update_habit(seeded_habit.uid, intent)
        assert result.is_ok
        assert result.value.title == "Updated title"

        # Re-fetch from Neo4j: title changed, the rest is intact (no clobber).
        fetched = await core_service.get_habit(seeded_habit.uid)
        assert fetched.is_ok
        assert fetched.value.title == "Updated title"
        assert fetched.value.description == "Original description"
        assert fetched.value.priority == Priority.MEDIUM
        assert fetched.value.duration_minutes == 15
        assert fetched.value.current_streak == 10

        # HabitUpdated fired on the intent path, naming only the changed field.
        updated_events = [e for e in event_bus.get_event_history() if isinstance(e, HabitUpdated)]
        assert updated_events, "expected a HabitUpdated event on the intent path"
        assert updated_events[-1].updated_fields == ["title"]

    async def test_status_transition_intent_persists_and_emits_event(
        self, core_service, seeded_habit, event_bus
    ) -> None:
        """A status transition expressed as an intent persists and fires HabitUpdated."""
        event_bus.clear_event_history()
        intent = HabitUpdateIntent(status=EntityStatus.PAUSED.value)

        result = await core_service.update_habit(seeded_habit.uid, intent)
        assert result.is_ok
        assert result.value.status == EntityStatus.PAUSED

        fetched = await core_service.get_habit(seeded_habit.uid)
        assert fetched.is_ok
        assert fetched.value.status == EntityStatus.PAUSED

        updated_events = [e for e in event_bus.get_event_history() if isinstance(e, HabitUpdated)]
        assert updated_events, "status transition must fire HabitUpdated"
        assert "status" in updated_events[-1].updated_fields

    async def test_archive_with_streak_blocked_without_force(
        self, core_service, seeded_habit
    ) -> None:
        """Live _validate_update: archiving a 10-day streak is blocked without force_archive."""
        intent = HabitUpdateIntent(status=EntityStatus.ARCHIVED.value)

        result = await core_service.update_habit(seeded_habit.uid, intent)
        assert result.is_error, "archiving an active streak must be blocked"

        # The habit was NOT archived (validation ran before the write).
        fetched = await core_service.get_habit(seeded_habit.uid)
        assert fetched.is_ok
        assert fetched.value.status == EntityStatus.ACTIVE

    async def test_archive_with_streak_succeeds_with_force(
        self, core_service, seeded_habit, neo4j_driver
    ) -> None:
        """force_archive bypasses the streak rule and is never persisted as a column."""
        intent = HabitUpdateIntent(status=EntityStatus.ARCHIVED.value)

        result = await core_service.update_habit(seeded_habit.uid, intent, force_archive=True)
        assert result.is_ok
        assert result.value.status == EntityStatus.ARCHIVED

        fetched = await core_service.get_habit(seeded_habit.uid)
        assert fetched.is_ok
        assert fetched.value.status == EntityStatus.ARCHIVED
        # force_archive is a transient validation directive — never written to the node.
        keys = await self._persisted_node_keys(neo4j_driver, seeded_habit.uid)
        assert "force_archive" not in keys

    async def test_to_intent_carries_only_explicit_fields(self) -> None:
        """to_intent() reflects model_fields_set: provided → set, absent → UNSET."""
        request = HabitUpdateRequest(title="Just the title")
        intent = request.to_intent()

        assert intent.title == "Just the title"
        assert intent.status is UNSET
        assert intent.priority is UNSET
        assert intent.description is UNSET
        assert intent.to_changes() == {"title": "Just the title"}

        # Enum fields are lowered to their string value on the intent.
        request2 = HabitUpdateRequest(
            priority=Priority.HIGH,
            status=EntityStatus.ACTIVE,
            habit_difficulty=HabitDifficulty.EASY,
            habit_category=HabitCategory.HEALTH,
        )
        intent2 = request2.to_intent()
        assert intent2.priority == Priority.HIGH.value
        assert intent2.status == EntityStatus.ACTIVE.value
        assert intent2.habit_difficulty == HabitDifficulty.EASY.value
        assert intent2.habit_category == HabitCategory.HEALTH.value
        assert intent2.title is UNSET

    async def test_to_intent_drops_cross_domain_edge_uids(self) -> None:
        """The four edge-UID request fields are graph edges, never node properties."""
        request = HabitUpdateRequest(
            title="Edges plus a prop",
            linked_knowledge_uids=["ku_y"],
            linked_goal_uids=["goal_x"],
            linked_principle_uids=["principle_z"],
            prerequisite_habit_uids=["habit_w"],
        )
        intent = request.to_intent()

        # Only the node property survives; the four edge fields are not on the intent.
        assert intent.to_changes() == {"title": "Edges plus a prop"}
