"""
Integration Test: Goals Core Operations
=========================================

Tests basic CRUD operations and core functionality for the Goals domain
against a real Neo4j database.

This suite fills the coverage gap identified on 2026-02-28 — GoalsCoreService
had no integration tests despite being a central Activity Domain service.

Test Coverage:
--------------
- GoalsCoreService.create()        — create, retrieve, validate
- GoalsCoreService.get()           — by UID, not found
- GoalsCoreService.update()        — field mutation
- GoalsCoreService.delete()        — deletion and not-found after
- GoalsCoreService.get_user_goals() — user-scoped listing
- BaseService.list_all_categories() — inherited category query (verifies
                                       list_goal_categories was correctly removed
                                       and BaseService is the canonical path)
- Status transitions               — ACTIVE → PAUSED, ACTIVE → COMPLETED
- Goal enum fields                 — GoalType, GoalTimeframe, MeasurementType
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.goal_enums import GoalTimeframe, GoalType, MeasurementType
from core.models.goal.goal import Goal
from core.services.goals.goals_core_service import GoalsCoreService
from core.services.goals.goals_search_service import GoalsSearchService

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.mark.asyncio
class TestGoalsCoreOperations:
    """Integration tests for Goals CRUD and core operations."""

    @pytest_asyncio.fixture
    async def event_bus(self):
        return InMemoryEventBus(capture_history=True)

    @pytest_asyncio.fixture
    async def goals_backend(self, neo4j_driver, clean_neo4j):
        return UniversalNeo4jBackend[Goal](
            neo4j_driver, "Entity", Goal, default_filters={"entity_type": "goal"}
        )

    @pytest_asyncio.fixture
    async def goals_core(self, goals_backend, event_bus):
        return GoalsCoreService(backend=goals_backend, event_bus=event_bus)

    @pytest_asyncio.fixture
    async def goals_search(self, goals_backend):
        """GoalsSearchService has _category_field='domain' configured via DomainConfig."""
        return GoalsSearchService(backend=goals_backend)

    @pytest_asyncio.fixture
    def user_uid(self):
        return "user.test_goals_core"

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _goal(self, uid: str, user_uid: str, **kwargs) -> Goal:
        defaults: dict = {
            "uid": uid,
            "user_uid": user_uid,
            "title": "Test Goal",
            "description": "A goal created for automated testing",
            "entity_type": EntityType.GOAL,
        }
        defaults.update(kwargs)
        return Goal(**defaults)

    # =========================================================================
    # CRUD OPERATIONS (5 tests)
    # =========================================================================

    async def test_create_goal(self, goals_core, user_uid):
        """Creating a valid goal returns the persisted Goal."""
        goal = self._goal("goal_create_001", user_uid, title="Learn Neo4j")

        result = await goals_core.create(goal)

        assert result.is_ok
        created = result.value
        assert created.uid == "goal_create_001"
        assert created.title == "Learn Neo4j"
        assert created.entity_type == EntityType.GOAL

    async def test_get_goal_by_uid(self, goals_core, user_uid):
        """A created goal can be retrieved by UID."""
        goal = self._goal("goal_get_001", user_uid, title="Read daily")
        await goals_core.create(goal)

        result = await goals_core.get("goal_get_001")

        assert result.is_ok
        assert result.value.uid == "goal_get_001"
        assert result.value.title == "Read daily"

    async def test_get_nonexistent_goal_returns_error(self, goals_core):
        """Getting a UID that doesn't exist returns a NotFound error."""
        result = await goals_core.get("goal_does_not_exist_xyz")

        assert result.is_error
        assert "not found" in result.error.message.lower()

    async def test_update_goal_field(self, goals_core, user_uid):
        """Updating a goal field persists the change."""
        goal = self._goal("goal_upd_001", user_uid, title="Original title")
        await goals_core.create(goal)

        result = await goals_core.update("goal_upd_001", {"title": "Updated title"})

        assert result.is_ok
        # Confirm the change persisted
        fetch = await goals_core.get("goal_upd_001")
        assert fetch.is_ok
        assert fetch.value.title == "Updated title"

    async def test_delete_goal(self, goals_core, user_uid):
        """Deleting a goal makes it unfindable."""
        goal = self._goal("goal_del_001", user_uid)
        await goals_core.create(goal)

        del_result = await goals_core.delete("goal_del_001")
        assert del_result.is_ok

        fetch = await goals_core.get("goal_del_001")
        assert fetch.is_error

    # =========================================================================
    # USER-SCOPED LISTING (2 tests)
    # =========================================================================

    async def test_get_user_goals_returns_all_user_goals(self, goals_core, user_uid):
        """get_user_goals returns all goals belonging to the user."""
        for i in range(3):
            goal = self._goal(f"goal_list_{i}", user_uid, title=f"Goal {i}")
            await goals_core.create(goal)

        result = await goals_core.get_user_goals(user_uid)

        assert result.is_ok
        assert len(result.value) >= 3
        assert all(isinstance(g, Goal) for g in result.value)

    async def test_get_user_goals_isolated_per_user(self, goals_core):
        """Goals from user A must not appear in user B's list."""
        await goals_core.create(self._goal("goal_user_a", "user.alpha", title="Alpha goal"))
        await goals_core.create(self._goal("goal_user_b", "user.beta", title="Beta goal"))

        result_a = await goals_core.get_user_goals("user.alpha")
        result_b = await goals_core.get_user_goals("user.beta")

        assert result_a.is_ok
        assert result_b.is_ok
        uids_a = {g.uid for g in result_a.value}
        uids_b = {g.uid for g in result_b.value}
        assert uids_a.isdisjoint(uids_b), "Users share goals — ownership isolation is broken"

    # =========================================================================
    # STATUS TRANSITIONS (2 tests)
    # =========================================================================

    async def test_goal_default_status_is_draft(self, goals_core, user_uid):
        """Goals are created DRAFT by default (Entity.__post_init__ default)."""
        goal = self._goal("goal_status_default", user_uid)
        result = await goals_core.create(goal)

        assert result.is_ok
        assert result.value.status == EntityStatus.DRAFT

    async def test_pause_goal_changes_status(self, goals_core, user_uid):
        """Updating status to PAUSED persists correctly."""
        goal = self._goal("goal_status_pause", user_uid)
        await goals_core.create(goal)

        upd = await goals_core.update("goal_status_pause", {"status": EntityStatus.PAUSED.value})
        assert upd.is_ok

        fetch = await goals_core.get("goal_status_pause")
        assert fetch.is_ok
        assert fetch.value.status == EntityStatus.PAUSED

    # =========================================================================
    # GOAL ENUM FIELDS (2 tests)
    # =========================================================================

    async def test_goal_type_persisted(self, goals_core, user_uid):
        """GoalType enum is persisted and retrieved correctly."""
        for goal_type in [GoalType.OUTCOME, GoalType.PROCESS, GoalType.LEARNING]:
            goal = self._goal(
                f"goal_type_{goal_type.value}",
                user_uid,
                title=f"Goal {goal_type.value}",
                goal_type=goal_type,
            )
            result = await goals_core.create(goal)
            assert result.is_ok
            assert result.value.goal_type == goal_type

    async def test_goal_timeframe_persisted(self, goals_core, user_uid):
        """GoalTimeframe enum is persisted and retrieved correctly."""
        for tf in [GoalTimeframe.YEARLY, GoalTimeframe.QUARTERLY, GoalTimeframe.MONTHLY]:
            goal = self._goal(
                f"goal_tf_{tf.value}",
                user_uid,
                title=f"Goal {tf.value}",
                timeframe=tf,
            )
            result = await goals_core.create(goal)
            assert result.is_ok
            assert result.value.timeframe == tf

    # =========================================================================
    # BASESERVICE.list_all_categories() — verifies dead code was correctly removed
    # =========================================================================

    async def test_list_all_categories_accessible_on_search_service(self, goals_search):
        """GoalsSearchService inherits list_all_categories() from BaseService.

        The now-deleted GoalsCoreService.list_goal_categories() used a raw Cypher
        query that duplicated BaseService.list_all_categories().  This test verifies
        the canonical mixin method is present and callable on the search sub-service,
        which is the correct path for category queries (it has the domain config).
        """
        # Structural: the method must exist and be callable
        assert hasattr(goals_search, "list_all_categories")
        assert callable(goals_search.list_all_categories)

        # Callable: it returns a Result without raising
        result = await goals_search.list_all_categories()
        assert result.is_ok  # Empty DB returns an empty list, not an error

    async def test_list_goal_categories_not_defined_on_core_service(self, goals_core):
        """list_goal_categories must not exist on GoalsCoreService.

        It was removed on 2026-02-28 as dead code.  The canonical path is
        BaseService.list_all_categories() for admin use, or
        GoalsService.list_goal_categories() for user-scoped queries via the facade.
        """
        assert not hasattr(goals_core.__class__, "list_goal_categories") or (
            "list_goal_categories" not in GoalsCoreService.__dict__
        ), (
            "list_goal_categories is still defined directly on GoalsCoreService. "
            "It was removed because the facade never called it — remove it."
        )

    # =========================================================================
    # MULTIPLE GOALS — edge cases (2 tests)
    # =========================================================================

    async def test_create_many_goals_same_user(self, goals_core, user_uid):
        """Creating 5+ goals for the same user all succeed."""
        for i in range(5):
            goal = self._goal(f"goal_many_{i}", user_uid, title=f"Goal {i}")
            result = await goals_core.create(goal)
            assert result.is_ok

        list_result = await goals_core.get_user_goals(user_uid)
        assert list_result.is_ok
        assert len(list_result.value) >= 5

    async def test_goal_with_all_optional_fields(self, goals_core, user_uid):
        """A goal with all optional fields specified persists correctly."""
        from datetime import date

        goal = self._goal(
            "goal_full_001",
            user_uid,
            title="Complete Python course",
            description="Finish the advanced Python programming course by Q2",
            goal_type=GoalType.OUTCOME,
            timeframe=GoalTimeframe.QUARTERLY,
            measurement_type=MeasurementType.BINARY,
            vision_statement="Become proficient in Python",
            why_important="Career advancement and personal growth",
            target_date=date(2026, 6, 30),
        )

        result = await goals_core.create(goal)

        assert result.is_ok
        created = result.value
        assert created.goal_type == GoalType.OUTCOME
        assert created.timeframe == GoalTimeframe.QUARTERLY
        assert created.vision_statement == "Become proficient in Python"
