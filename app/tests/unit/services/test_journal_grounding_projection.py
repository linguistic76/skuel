"""Tests for the journal grounding projection (ADR-081 D2).

Three contracts:
1. The projection renders exactly its curated shape — identity, active
   goals/tasks/habits with light relevance, learning-journey framing.
2. The EXPLICIT field list is enforced: a recording UserContext proves the
   renderer reads nothing beyond ``JOURNAL_GROUNDING_FIELDS`` (the scope-creep
   mitigation ADR-081 names), and the list contains no discussion-transcript
   fields (ADR-073/078 privacy wall).
3. ``JournalService`` degrades soft: an unwired ``context_builder`` or a
   failed build falls back to the pre-ADR-081 title digest — never a crash,
   never grounding below the old floor.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.goal.goal import Goal
from core.models.habit.habit import Habit
from core.models.task.task import Task
from core.services.journal.grounding_projection import (
    JOURNAL_GROUNDING_FIELDS,
    render_journal_grounding,
)
from core.services.journal.journal_service import JournalService
from core.services.user.unified_user_context import UserContext
from core.utils.result_simplified import Errors, Result

_USER = "user_mike"


def _goal(uid: str, title: str, progress: float = 0.0) -> Goal:
    return Goal(uid=uid, title=title, user_uid=_USER, progress_percentage=progress)


def _task(uid: str, title: str) -> Task:
    return Task(uid=uid, title=title, user_uid=_USER)


def _habit(uid: str, title: str, streak: int = 0) -> Habit:
    return Habit(uid=uid, title=title, user_uid=_USER, current_streak=streak)


def _context(**overrides) -> UserContext:
    return UserContext(user_uid=_USER, display_name="Mike", **overrides)


class TestRenderJournalGrounding:
    def test_identity_line_leads(self):
        lines = render_journal_grounding(_context(), goals=[], tasks=[], habits=[])
        assert lines == ["You are speaking with Mike."]

    def test_blank_display_name_renders_no_identity_line(self):
        context = UserContext(user_uid=_USER)
        lines = render_journal_grounding(context, goals=[], tasks=[], habits=[])
        assert lines == []

    def test_goals_annotated_with_progress(self):
        context = _context(active_goal_uids=["g1", "g2"])
        goals = [_goal("g1", "Learn Spanish", progress=40.0), _goal("g2", "Ship SKUEL")]
        lines = render_journal_grounding(context, goals=goals, tasks=[], habits=[])
        assert "Active goals: Learn Spanish (40% along), Ship SKUEL" in lines

    def test_tasks_ordered_overdue_then_today_and_annotated(self):
        context = _context(
            active_task_uids=["t1", "t2", "t3"],
            overdue_task_uids=["t3"],
            today_task_uids=["t2"],
        )
        tasks = [_task("t1", "Read ADR"), _task("t2", "Write PR"), _task("t3", "Fix bug")]
        lines = render_journal_grounding(context, goals=[], tasks=tasks, habits=[])
        assert "Current tasks: Fix bug (overdue), Write PR (due today), Read ADR" in lines

    def test_habits_annotated_with_streak(self):
        context = _context(active_habit_uids=["h1", "h2"], habit_streaks={"h1": 12})
        habits = [_habit("h1", "Meditation"), _habit("h2", "Running")]
        lines = render_journal_grounding(context, goals=[], tasks=[], habits=habits)
        assert "Active habits: Meditation (12-day streak), Running" in lines

    def test_habit_streak_falls_back_to_model_when_context_lacks_it(self):
        context = _context(active_habit_uids=["h1"])
        habits = [_habit("h1", "Running", streak=3)]
        lines = render_journal_grounding(context, goals=[], tasks=[], habits=habits)
        assert "Active habits: Running (3-day streak)" in lines

    def test_learning_journey_lines(self):
        context = _context(
            current_path_steps=[{"uid": "ps.a", "title": "Graph Modeling"}],
            mastered_knowledge_uids={"ku1", "ku2"},
            in_progress_knowledge_uids={"ku3"},
        )
        lines = render_journal_grounding(context, goals=[], tasks=[], habits=[])
        assert "Currently studying: Graph Modeling" in lines
        assert "Knowledge journey: 2 concepts mastered, 1 in progress." in lines

    def test_selection_is_capped_at_six_per_domain(self):
        uids = [f"g{i}" for i in range(10)]
        context = _context(active_goal_uids=uids)
        goals = [_goal(uid, f"Goal {uid}") for uid in uids]
        lines = render_journal_grounding(context, goals=goals, tasks=[], habits=[])
        goal_line = next(line for line in lines if line.startswith("Active goals:"))
        assert goal_line.count(",") == 5  # 6 items

    def test_context_selects_and_orders_the_active_subset(self):
        # The context's active list, not fetch order, decides what renders.
        context = _context(active_goal_uids=["g2"])
        goals = [_goal("g1", "Done long ago"), _goal("g2", "The live one")]
        lines = render_journal_grounding(context, goals=goals, tasks=[], habits=[])
        assert "Active goals: The live one" in lines

    def test_empty_uid_join_falls_back_to_fetch_order(self):
        # A sparse context must never ground below the plain title digest.
        context = _context(active_goal_uids=["g_gone"])
        goals = [_goal("g1", "Still visible")]
        lines = render_journal_grounding(context, goals=goals, tasks=[], habits=[])
        assert "Active goals: Still visible" in lines


class _RecordingContext(UserContext):
    """UserContext that records every dataclass-field read — the field-list tripwire."""

    def __init__(self, **kwargs):
        object.__setattr__(self, "_reads", set())
        super().__init__(**kwargs)

    def __getattribute__(self, name):
        if name != "_reads" and name in UserContext.__dataclass_fields__:
            object.__getattribute__(self, "_reads").add(name)
        return object.__getattribute__(self, name)


class TestExplicitFieldList:
    def test_render_reads_only_the_declared_fields(self):
        context = _RecordingContext(
            user_uid=_USER,
            display_name="Mike",
            active_goal_uids=["g1"],
            active_task_uids=["t1"],
            overdue_task_uids=["t1"],
            today_task_uids=[],
            active_habit_uids=["h1"],
            habit_streaks={"h1": 4},
            current_path_steps=[{"uid": "ps.a", "title": "Graph Modeling"}],
            mastered_knowledge_uids={"ku1"},
            in_progress_knowledge_uids={"ku2"},
        )
        render_journal_grounding(
            context,
            goals=[_goal("g1", "Learn Spanish", progress=10.0)],
            tasks=[_task("t1", "Fix bug")],
            habits=[_habit("h1", "Meditation")],
        )
        reads = object.__getattribute__(context, "_reads")
        undeclared = reads - set(JOURNAL_GROUNDING_FIELDS)
        assert not undeclared, (
            f"render_journal_grounding read UserContext fields outside the explicit "
            f"projection list: {sorted(undeclared)}. Extend JOURNAL_GROUNDING_FIELDS "
            f"deliberately (ADR-081 D2) or drop the read."
        )

    def test_declared_fields_exist_on_user_context(self):
        # A renamed UserContext field must fail here, not silently un-ground.
        missing = set(JOURNAL_GROUNDING_FIELDS) - set(UserContext.__dataclass_fields__)
        assert not missing

    def test_no_transcript_shaped_fields_in_the_list(self):
        # ADR-073/078: grounding reads structural context, never discussion data.
        for field_name in JOURNAL_GROUNDING_FIELDS:
            assert "conversation" not in field_name
            assert "transcript" not in field_name
            assert "session" not in field_name


def _domain_service(method_name: str, entities: list) -> MagicMock:
    service = MagicMock()
    setattr(service, method_name, AsyncMock(return_value=Result.ok(entities)))
    return service


def _make_service(context_builder=None, user_entry=None) -> JournalService:
    if user_entry is None:
        user_entry = MagicMock()
        user_entry.get_vault_notes_for_context = AsyncMock(return_value=Result.ok([]))
    return JournalService(
        llm_caller=MagicMock(),
        user_entry_service=user_entry,
        goals_service=_domain_service("get_user_goals", [_goal("g1", "Learn Spanish")]),
        tasks_service=_domain_service("get_user_tasks", [_task("t1", "Fix bug")]),
        habits_service=_domain_service("get_user_habits", [_habit("h1", "Meditation")]),
        dsl_bridge=None,
        canon_retrieval_service=None,
        context_builder=context_builder,
    )


class TestGroundingDegradation:
    @pytest.mark.asyncio
    async def test_no_builder_falls_back_to_title_digest(self):
        service = _make_service(context_builder=None)
        summary = await service._build_context_summary(_USER)
        assert summary == (
            "Active goals: Learn Spanish\nCurrent tasks: Fix bug\nActive habits: Meditation"
        )

    @pytest.mark.asyncio
    async def test_failed_build_falls_back_to_title_digest(self):
        builder = MagicMock()
        builder.build = AsyncMock(return_value=Result.fail(Errors.not_found("User", _USER)))
        service = _make_service(context_builder=builder)
        summary = await service._build_context_summary(_USER)
        assert "You are speaking with" not in summary
        assert "Active goals: Learn Spanish" in summary

    @pytest.mark.asyncio
    async def test_built_context_renders_the_projection(self):
        builder = MagicMock()
        builder.build = AsyncMock(
            return_value=Result.ok(_context(active_goal_uids=["g1"], overdue_task_uids=["t1"]))
        )
        service = _make_service(context_builder=builder)
        summary = await service._build_context_summary(_USER)
        assert "You are speaking with Mike." in summary
        assert "Current tasks: Fix bug (overdue)" in summary
        builder.build.assert_awaited_once_with(_USER)

    @pytest.mark.asyncio
    async def test_vault_notes_ride_both_paths(self):
        user_entry = MagicMock()
        user_entry.get_vault_notes_for_context = AsyncMock(
            return_value=Result.ok([{"title": "Note", "snippet": "A thought."}])
        )
        service = _make_service(context_builder=None, user_entry=user_entry)
        summary = await service._build_context_summary(_USER)
        assert "Personal project notes:\n  [Note] A thought." in summary

    @pytest.mark.asyncio
    async def test_include_vault_notes_false_skips_the_note_read(self):
        # Canon P3 de-dup: the vault dial's grounded block replaces the snippets.
        user_entry = MagicMock()
        notes_read = AsyncMock(return_value=Result.ok([]))
        user_entry.get_vault_notes_for_context = notes_read
        service = _make_service(context_builder=None, user_entry=user_entry)
        await service._build_context_summary(_USER, include_vault_notes=False)
        notes_read.assert_not_called()
