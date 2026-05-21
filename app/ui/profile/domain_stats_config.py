"""
Profile Domain Stats Configuration
===================================

Configuration-driven approach for calculating domain statistics from UserContext.
Eliminates repetitive if-elif blocks in profile UI route logic.

**Pattern:** Named functions (SKUEL012 compliance) + dataclass configuration

**Usage:**
```python
from ui.profile.domain_stats_config import DOMAIN_STATS_CONFIG

config = DOMAIN_STATS_CONFIG.get("tasks")
if config:
    count = config.count_fn(context)
    active = config.active_fn(context)
    status_args = config.status_args_fn(context)
    status = config.status_fn(*status_args)
```

See: /docs/patterns/UI_COMPONENT_PATTERNS.md
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from core.services.user.domain_health import DomainStatus
from core.services.user.unified_user_context import UserContext


class StatusCalculator(Protocol):
    """Protocol for domain status calculator functions."""

    def __call__(self, *args: int) -> str: ...


@dataclass(frozen=True)
class DomainStatsConfig:
    """
    Configuration for calculating domain statistics from UserContext.

    Attributes:
        count_fn: Function to calculate total count from context
        active_fn: Function to calculate active count from context
        status_fn: DomainStatus calculator method
        status_args_fn: Function to extract args for status calculator
    """

    count_fn: Callable[[UserContext], int]
    active_fn: Callable[[UserContext], int]
    status_fn: StatusCalculator
    status_args_fn: Callable[[UserContext], tuple[int, ...]]


# ============================================================================
# ACTIVITY DOMAIN EXTRACTORS
# ============================================================================


# Tasks domain extractors
def tasks_count(ctx: UserContext) -> int:
    """Calculate total task count (active + completed)."""
    return len(ctx.active_task_uids) + len(ctx.completed_task_uids)


def tasks_active(ctx: UserContext) -> int:
    """Calculate active task count."""
    return len(ctx.active_task_uids)


def tasks_status_args(ctx: UserContext) -> tuple[int, int]:
    """Extract status args for tasks (overdue_count, blocked_count).

    blocked_task_uids is rich-context only; treated as 0 at standard depth.
    """
    blocked_count = len(ctx.blocked_task_uids_or_empty())
    return (len(ctx.overdue_task_uids), blocked_count)


# Events domain extractors
def events_count(ctx: UserContext) -> int:
    """Calculate total event count (upcoming + today)."""
    return len(ctx.upcoming_event_uids) + len(ctx.today_event_uids)


def events_active(ctx: UserContext) -> int:
    """Calculate active event count (today's events)."""
    return len(ctx.today_event_uids)


def events_status_args(ctx: UserContext) -> tuple[int, int]:
    """Extract status args for events (missed_today=0, missed_week)."""
    return (0, len(ctx.missed_event_uids))


# Goals domain extractors
def goals_count(ctx: UserContext) -> int:
    """Calculate total goal count (active + completed)."""
    return len(ctx.active_goal_uids) + len(ctx.completed_goal_uids)


def goals_active(ctx: UserContext) -> int:
    """Calculate active goal count."""
    return len(ctx.active_goal_uids)


def goals_status_args(ctx: UserContext) -> tuple[int, int]:
    """Extract status args for goals (at_risk_count, stalled_count)."""
    return (len(ctx.at_risk_goals), len(ctx.get_stalled_goals()))


# Habits domain extractors
def habits_count(ctx: UserContext) -> int:
    """Calculate total habit count (all active habits)."""
    return len(ctx.active_habit_uids)


def habits_active(ctx: UserContext) -> int:
    """Calculate active habit count (same as total for habits)."""
    return len(ctx.active_habit_uids)


def habits_status_args(ctx: UserContext) -> tuple[int]:
    """Extract status args for habits (at_risk_count).

    at_risk_habits is rich-context only; treated as 0 at standard depth.
    """
    at_risk_count = len(ctx.at_risk_habits_or_empty())
    return (at_risk_count,)


# Principles domain extractors
def principles_count(ctx: UserContext) -> int:
    """Calculate total principle count (all core principles)."""
    return len(ctx.core_principle_uids)


def principles_active(ctx: UserContext) -> int:
    """Calculate active principle count (same as total for principles)."""
    return len(ctx.core_principle_uids)


def principles_status_args(ctx: UserContext) -> tuple[int, int]:
    """Extract status args for principles (aligned_count, against_count)."""
    return (ctx.decisions_aligned_with_principles, ctx.decisions_against_principles)


# Choices domain extractors
def choices_count(ctx: UserContext) -> int:
    """Calculate total choice count (pending + resolved)."""
    return len(ctx.pending_choice_uids) + len(ctx.resolved_choice_uids)


def choices_active(ctx: UserContext) -> int:
    """Calculate active choice count (pending only)."""
    return len(ctx.pending_choice_uids)


def choices_status_args(ctx: UserContext) -> tuple[int]:
    """Extract status args for choices (pending_count)."""
    return (len(ctx.pending_choice_uids),)


# ============================================================================
# CURRICULUM DOMAIN EXTRACTORS
# ============================================================================


# Knowledge domain extractors (KU)
def knowledge_count(ctx: UserContext) -> int:
    """Calculate total knowledge count (mastered + in_progress + ready)."""
    mastered = len(ctx.mastered_knowledge_uids)
    in_progress = len(ctx.in_progress_knowledge_uids)
    ready = len(ctx.ready_to_learn_uids)
    return mastered + in_progress + ready


def knowledge_active(ctx: UserContext) -> int:
    """Calculate active knowledge count (in_progress)."""
    return len(ctx.in_progress_knowledge_uids)


def knowledge_status(ctx: UserContext) -> str:
    """Calculate knowledge domain status based on learning progress."""
    return DomainStatus.calculate_knowledge_status(
        blocked=len(ctx.prerequisites_needed),
        mastered=len(ctx.mastered_knowledge_uids),
        in_progress=len(ctx.in_progress_knowledge_uids),
    )


# Path Steps domain extractors (PS)
def path_steps_count(_ctx: UserContext) -> int:
    """Calculate total path steps count. Placeholder - no PS nodes yet."""
    return 0


def path_steps_active(_ctx: UserContext) -> int:
    """Calculate active path steps count. Placeholder - no PS nodes yet."""
    return 0


def path_steps_status(_ctx: UserContext) -> str:
    """Calculate path steps status. Placeholder - no PS nodes yet."""
    return "healthy"


# Learning Paths domain extractors (LP)
def learning_paths_count(ctx: UserContext) -> int:
    """Calculate total learning paths count (enrolled)."""
    return len(ctx.enrolled_path_uids)


def learning_paths_active(ctx: UserContext) -> int:
    """Calculate active learning paths count (enrolled with progress < 1.0)."""
    return len(ctx.enrolled_path_uids)


def learning_paths_status(ctx: UserContext) -> str:
    """Calculate learning paths status based on blocked prerequisites."""
    return DomainStatus.calculate_learning_paths_status(
        blocked=len(ctx.prerequisites_needed),
        enrolled=len(ctx.enrolled_path_uids),
    )


# ============================================================================
# CONFIGURATION DICTIONARIES
# ============================================================================

DOMAIN_STATS_CONFIG: dict[str, DomainStatsConfig] = {
    "tasks": DomainStatsConfig(
        count_fn=tasks_count,
        active_fn=tasks_active,
        status_fn=DomainStatus.calculate_tasks_status,
        status_args_fn=tasks_status_args,
    ),
    "events": DomainStatsConfig(
        count_fn=events_count,
        active_fn=events_active,
        status_fn=DomainStatus.calculate_events_status,
        status_args_fn=events_status_args,
    ),
    "goals": DomainStatsConfig(
        count_fn=goals_count,
        active_fn=goals_active,
        status_fn=DomainStatus.calculate_goals_status,
        status_args_fn=goals_status_args,
    ),
    "habits": DomainStatsConfig(
        count_fn=habits_count,
        active_fn=habits_active,
        status_fn=DomainStatus.calculate_habits_status,
        status_args_fn=habits_status_args,
    ),
    "principles": DomainStatsConfig(
        count_fn=principles_count,
        active_fn=principles_active,
        status_fn=DomainStatus.calculate_principles_status,
        status_args_fn=principles_status_args,
    ),
    "choices": DomainStatsConfig(
        count_fn=choices_count,
        active_fn=choices_active,
        status_fn=DomainStatus.calculate_choices_status,
        status_args_fn=choices_status_args,
    ),
}


__all__ = [
    "DomainStatsConfig",
    "DOMAIN_STATS_CONFIG",
    "StatusCalculator",
    "knowledge_active",
    "knowledge_count",
    "knowledge_status",
    "learning_paths_active",
    "learning_paths_count",
    "learning_paths_status",
    "path_steps_active",
    "path_steps_count",
    "path_steps_status",
]
