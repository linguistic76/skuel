"""Journal grounding projection — the named curated rendering of UserContext (ADR-081 D2).

The typed Journals companion grounds every turn on the real
``UnifiedUserContext.build()`` object, but what reaches the prompt is THIS
projection — a legible, tunable rendering, never an open-ended dump of the
~150-field context. ``JOURNAL_GROUNDING_FIELDS`` is the explicit list of
UserContext fields the projection may read; the recording test in
``tests/unit/services/test_journal_grounding_projection.py`` fails if the
renderer reaches beyond it. That explicit list is ADR-081's named mitigation
for the scope-creep risk.

Division of labour: UserContext supplies the *relevance lens* (which items are
active, overdue, due today, on a streak — the status rules the rest of the app
already trusts) plus identity and the learning journey; the domain services'
fetched models supply the titles the lens is joined against by UID.

Privacy wall (ADR-073/078): the projection reads structural UserContext only.
It never touches the discussion store — guarded by the understanding-wall
tests in ``tests/unit/conversation/test_conversation_understanding_wall.py``.

See: /docs/decisions/ADR-081-journals-companion-authored-instructions-and-grounding.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.models.protocols.domain_model_protocol import DomainModelProtocol

if TYPE_CHECKING:
    from core.models.goal.goal import Goal
    from core.models.habit.habit import Habit
    from core.models.task.task import Task
    from core.services.user.unified_user_context import UserContext

# The EXPLICIT UserContext field list this projection reads (ADR-081 D2).
# Adding a field here is a deliberate grounding decision — extend the render
# AND the tests together, never silently.
JOURNAL_GROUNDING_FIELDS: tuple[str, ...] = (
    # Identity
    "display_name",
    # Activity relevance lens
    "active_goal_uids",
    "active_task_uids",
    "overdue_task_uids",
    "today_task_uids",
    "active_habit_uids",
    "habit_streaks",
    # Learning journey framing
    "current_path_steps",
    "mastered_knowledge_uids",
    "in_progress_knowledge_uids",
)

# Same per-domain cap as the pre-ADR-081 title digest — grounding stays light.
_MAX_ITEMS_PER_DOMAIN = 6
_MAX_PATH_STEPS = 3


def render_journal_grounding(
    context: UserContext,
    *,
    goals: list[Goal],
    tasks: list[Task],
    habits: list[Habit],
) -> list[str]:
    """Render the curated grounding lines for a journal prompt.

    Pure function over an already-built ``UserContext`` and the owner's fetched
    activity models — no I/O, so the projection is testable byte-for-byte.
    Every UserContext read stays inside ``JOURNAL_GROUNDING_FIELDS``.

    Line prefixes ("Active goals:", "Current tasks:", "Active habits:") match
    the pre-ADR-081 digest so the prompt vocabulary the authored instructions
    were tuned against does not drift.
    """
    lines: list[str] = []

    if context.display_name:
        lines.append(f"You are speaking with {context.display_name}.")

    goal_entries = [_goal_entry(goal) for goal in _select(goals, context.active_goal_uids)]
    if goal_entries:
        lines.append("Active goals: " + ", ".join(goal_entries))

    task_entries = [
        _task_entry(task, context) for task in _select(tasks, _ordered_task_uids(context))
    ]
    if task_entries:
        lines.append("Current tasks: " + ", ".join(task_entries))

    habit_entries = [
        _habit_entry(habit, context) for habit in _select(habits, context.active_habit_uids)
    ]
    if habit_entries:
        lines.append("Active habits: " + ", ".join(habit_entries))

    studying = [
        step["title"] for step in context.current_path_steps[:_MAX_PATH_STEPS] if step["title"]
    ]
    if studying:
        lines.append("Currently studying: " + ", ".join(studying))

    mastered = len(context.mastered_knowledge_uids)
    in_progress = len(context.in_progress_knowledge_uids)
    if mastered or in_progress:
        lines.append(f"Knowledge journey: {mastered} concepts mastered, {in_progress} in progress.")

    return lines


def _select[E: DomainModelProtocol](entities: list[E], relevant_uids: list[str]) -> list[E]:
    """Pick the entities the context deems relevant, in the context's order.

    Falls back to fetch order when the UID join lands nothing (a sparse or
    just-built context) — the projection never grounds below the plain title
    digest it replaced.
    """
    by_uid = {entity.uid: entity for entity in entities}
    picked = [by_uid[uid] for uid in relevant_uids if uid in by_uid]
    if not picked:
        picked = list(entities)
    return picked[:_MAX_ITEMS_PER_DOMAIN]


def _ordered_task_uids(context: UserContext) -> list[str]:
    """Task relevance order: overdue first, then due today, then remaining active."""
    ordered = list(context.overdue_task_uids)
    ordered += [uid for uid in context.today_task_uids if uid not in ordered]
    ordered += [uid for uid in context.active_task_uids if uid not in ordered]
    return ordered


def _goal_entry(goal: Goal) -> str:
    if goal.progress_percentage > 0:
        return f"{goal.title} ({goal.progress_percentage:.0f}% along)"
    return goal.title


def _task_entry(task: Task, context: UserContext) -> str:
    if task.uid in context.overdue_task_uids:
        return f"{task.title} (overdue)"
    if task.uid in context.today_task_uids:
        return f"{task.title} (due today)"
    return task.title


def _habit_entry(habit: Habit, context: UserContext) -> str:
    streak = context.habit_streaks.get(habit.uid, habit.current_streak)
    if streak > 0:
        return f"{habit.title} ({streak}-day streak)"
    return habit.title
