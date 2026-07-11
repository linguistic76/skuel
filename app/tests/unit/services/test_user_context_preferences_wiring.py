"""User preferences must reach UserContext — the Settings→context wiring.

Regression tests for the dead preference wiring (July 2026): the Settings form
persists ``UserPreferences`` as a JSON-string blob on the :User node
(``preferences`` property, via ``to_neo4j_node``), but the populator used to
read FLAT node properties (``available_minutes``, ``energy_level``, ...) that
no writer ever set — so ``UserContext.available_minutes_daily`` (workload
capacity, /search capacity_warnings) ran on defaults for everyone.

The fix: both build paths populate preference fields from the parsed
``User.preferences`` model via ``populate_user_preferences``.
"""

from __future__ import annotations

import dataclasses
import json
from unittest.mock import AsyncMock, MagicMock

from core.models.enums import LearningLevel, TimeOfDay
from core.models.user.user import User, UserPreferences
from core.services.user.unified_user_context import UserContext
from core.services.user.user_context_populator import UserContextPopulator
from core.services.user_service import UserService
from core.utils.neo4j_mapper import from_neo4j_node
from core.utils.result_simplified import Errors, Result

_UID = "user_test_prefs"


def _context() -> UserContext:
    return UserContext(user_uid=_UID)


def _preferences(**overrides: object) -> UserPreferences:
    return dataclasses.replace(UserPreferences(), **overrides)  # type: ignore[arg-type]


class TestPopulateUserPreferences:
    """Populator maps the parsed UserPreferences model onto the context."""

    def test_realistic_preferences_reach_context(self) -> None:
        context = _context()
        prefs = _preferences(
            learning_level=LearningLevel.ADVANCED,
            preferred_time_of_day=TimeOfDay.MORNING,
            available_minutes_daily=300,
        )

        UserContextPopulator().populate_user_preferences(context, prefs)

        assert context.available_minutes_daily == 300
        assert context.preferred_time == TimeOfDay.MORNING
        assert context.learning_level == LearningLevel.ADVANCED

    def test_defaults_pass_through(self) -> None:
        """Absent user edits = model defaults; the context mirrors them."""
        context = _context()

        UserContextPopulator().populate_user_preferences(context, UserPreferences())

        assert context.available_minutes_daily == 60
        assert context.preferred_time == TimeOfDay.ANYTIME
        assert context.learning_level == LearningLevel.INTERMEDIATE

    def test_unparsed_blob_keeps_context_defaults(self) -> None:
        """Mapper fail-soft hands the RAW string through — populator must not blow up."""
        context = _context()

        UserContextPopulator().populate_user_preferences(
            context,
            "{not valid json",  # type: ignore[arg-type]  # simulating mapper fallback
        )

        assert context.available_minutes_daily == 60
        assert context.preferred_time == TimeOfDay.ANYTIME

    def test_bad_field_values_keep_field_defaults(self) -> None:
        """A single unconvertible field (mapper raw-value fallback) fails soft;
        the valid fields still land."""
        context = _context()
        prefs = _preferences(
            learning_level="bogus-level",
            preferred_time_of_day="morning",  # raw string form — still coercible
            available_minutes_daily="not-a-number",
        )

        UserContextPopulator().populate_user_preferences(context, prefs)

        assert context.learning_level == LearningLevel.INTERMEDIATE  # default kept
        assert context.preferred_time == TimeOfDay.MORNING  # string coerced
        assert context.available_minutes_daily == 60  # default kept

    def test_untouched_interaction_preferences_keep_defaults(self) -> None:
        """personality/tone/guidance/energy have no writer anywhere — defaults stand."""
        context = _context()
        before = (
            context.preferred_personality,
            context.preferred_tone,
            context.preferred_guidance,
            context.current_energy_level,
        )

        UserContextPopulator().populate_user_preferences(context, _preferences())

        assert (
            context.preferred_personality,
            context.preferred_tone,
            context.preferred_guidance,
            context.current_energy_level,
        ) == before


class TestBlobRoundTrip:
    """The real storage shape: JSON-string blob on the node → User → context."""

    def _node(self, prefs_blob: str) -> dict[str, object]:
        return {"uid": _UID, "title": _UID, "email": "prefs@test.local", "preferences": prefs_blob}

    def test_live_blob_shape_parses_and_populates(self) -> None:
        """Blob as persisted by to_neo4j_node — note energy_pattern is itself
        a JSON string inside the blob (double-encoded)."""
        blob = json.dumps(
            {
                "learning_level": "intermediate",
                "preferred_time_of_day": "evening",
                "available_minutes_daily": 300,
                "energy_pattern": json.dumps(
                    {"morning": "medium", "afternoon": "high", "evening": "low"}
                ),
                "theme": "light",
            }
        )
        user = from_neo4j_node(self._node(blob), User)
        context = _context()

        UserContextPopulator().populate_user_preferences(context, user.preferences)

        assert context.available_minutes_daily == 300
        assert context.preferred_time == TimeOfDay.EVENING

    def test_malformed_blob_defaults(self) -> None:
        user = from_neo4j_node(self._node("{definitely not json"), User)
        context = _context()

        UserContextPopulator().populate_user_preferences(context, user.preferences)

        assert context.available_minutes_daily == 60
        assert context.preferred_time == TimeOfDay.ANYTIME


class TestBuilderWiresPreferences:
    """BOTH build paths must carry User.preferences into the context."""

    def _user_service(self, prefs: UserPreferences) -> UserService:
        # Stateful repo double: update_user persists, get_user_by_uid returns
        # the latest — the post-save context REBUILD must see the new prefs.
        state = {"user": User(uid=_UID, title=_UID, email="prefs@test.local", preferences=prefs)}

        async def _get(_uid: str) -> Result[User]:
            return Result.ok(state["user"])

        async def _update(user: User) -> Result[User]:
            state["user"] = user
            return Result.ok(user)

        repo = MagicMock()
        repo.get_user_by_uid = AsyncMock(side_effect=_get)
        repo.update_user = AsyncMock(side_effect=_update)
        executor = MagicMock()
        executor.execute_mega_query = AsyncMock(
            return_value=Result.ok({"uids": {}, "entities": {}, "rich": {}})
        )
        executor.execute_consolidated_query = AsyncMock(return_value=Result.ok({}))
        executor.fetch_current_path_steps = AsyncMock(
            return_value=Result.fail(Errors.system(message="not in this test"))
        )
        executor.fetch_user_groups = AsyncMock(
            return_value=Result.fail(Errors.system(message="not in this test"))
        )
        return UserService(user_repo=repo, query_executor=executor)

    async def test_standard_build_carries_available_minutes(self) -> None:
        service = self._user_service(_preferences(available_minutes_daily=300))

        result = await service.get_user_context(_UID)

        assert result.is_ok, f"context build failed: {result.error}"
        assert result.value.available_minutes_daily == 300

    async def test_rich_build_carries_available_minutes(self) -> None:
        service = self._user_service(_preferences(available_minutes_daily=300))

        result = await service.get_rich_unified_context(_UID)

        assert result.is_ok, f"rich context build failed: {result.error}"
        assert result.value.available_minutes_daily == 300

    async def test_update_preferences_rebuilds_context_cache(self) -> None:
        """A Settings save must be visible to cache-hit-only consumers
        (SearchRouter._peek_capacity_warnings never builds): the cached rich
        context is invalidated AND rebuilt with the new preferences — neither
        stale (old value until TTL) nor cold (peek returns nothing)."""
        service = self._user_service(_preferences(available_minutes_daily=60))

        warmed = await service.get_rich_unified_context(_UID)
        assert warmed.is_ok
        cached = service.peek_cached_context(_UID)
        assert cached is not None
        assert cached.available_minutes_daily == 60

        update = await service.update_preferences(_UID, {"available_minutes_daily": 300})

        assert update.is_ok, f"update failed: {update.error}"
        rebuilt = service.peek_cached_context(_UID)
        assert rebuilt is not None, (
            "preferences save left a COLD context cache — cache-hit-only "
            "capacity warnings would vanish on a save-then-search flow"
        )
        assert rebuilt.available_minutes_daily == 300, (
            "preferences save left a STALE cached context — capacity warnings "
            "would ignore the new available_minutes_daily until TTL expiry"
        )
