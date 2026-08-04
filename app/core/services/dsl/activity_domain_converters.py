"""
Activity Domain Converters
==========================

Converter functions for the 6 Activity Domains:
Task, Habit, Goal, Event, Principle, Choice.

Each function converts a ParsedActivityLine to the domain's typed
``*CreateRequest`` — the exact object the domain facade's create method
accepts (``TasksService.create_task(request, user_uid)`` et al.). The
intermediate "creation dict" layer was removed with the EXTRACT_ACTIVITIES
pipeline wiring (ADR-069): one conversion, one shape, validated by Pydantic
at the boundary.
"""

from datetime import date, datetime, timedelta
from typing import Any

from core.models.choice.choice_request import ChoiceCreateRequest
from core.models.enums import EntityStatus, RecurrencePattern, TimeOfDay
from core.models.enums.choice_enums import ChoiceType
from core.models.enums.entity_enums import Domain, EntityType
from core.models.enums.principle_enums import (
    PrincipleCategory,
    PrincipleSource,
    PrincipleStrength,
)
from core.models.event.event_request import EventCreateRequest
from core.models.goal.goal_request import GoalCreateRequest
from core.models.habit.habit_request import HabitCreateRequest
from core.models.principle.principle_request import PrincipleCreateRequest
from core.models.task.task_request import TaskCreateRequest
from core.services.dsl.activity_dsl_parser import ParsedActivityLine
from core.services.dsl.dsl_mappings import (
    ConversionResult,
    map_dsl_priority_to_enum,
    map_repeat_to_recurrence,
)
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.dsl.converter")

# These converters run ONLY on the EXTRACT_ACTIVITIES ingestion path (vault
# notes → activities). Historical notes legitimately carry past dates, so the
# future-date guard is relaxed here via Pydantic validation context — the
# interactive API/UI creation paths construct their requests without this
# context and keep the guard (see validate_future_date, G10/Arc E).
INGESTED_NOTE_CONTEXT = {"allow_past_dates": True}


def derive_principle_title(description: str) -> str:
    """Principle title = first segment before any dash/colon, capped at 100 chars.

    Shared by the converter (what gets persisted) and the extractor's semantic
    dedup key (R3) so both compute the identical title for a given line.
    """
    title = description.split(" - ")[0].split(":")[0].strip()
    if len(title) > 100:
        title = title[:97] + "..."
    return title


def derive_choice_title(description: str) -> str:
    """Choice title = the description, capped at 200 chars (shared with R3 dedup)."""
    title = description
    if len(title) > 200:
        title = title[:197] + "..."
    return title


def _not_a(activity: ParsedActivityLine, entity_type: EntityType) -> Result[ConversionResult]:
    """Shared validation failure for a context mismatch."""
    return Result.fail(
        Errors.validation(
            message=(
                f"Activity is not a {entity_type.value} (missing '{entity_type.value}' in @context)"
            ),
            field="context",
            value=",".join(activity.context_values),
        )
    )


# ============================================================================
# TASK CONVERTER
# ============================================================================


@with_error_handling(error_type="system", operation="activity_to_task_request")
def activity_to_task_request(activity: ParsedActivityLine) -> Result[ConversionResult]:
    """
    Convert ParsedActivityLine to TaskCreateRequest.

    The resulting request can be passed to TasksService.create_task().

    Args:
        activity: Parsed activity line with context containing "task"

    Returns:
        Result containing TaskCreateRequest (as ConversionResult for type compatibility)
    """
    if not activity.is_task():
        return _not_a(activity, EntityType.TASK)

    # Extract due date from @when
    due_date: date | None = None
    if activity.when:
        due_date = activity.when.date()

    # Map priority
    priority = map_dsl_priority_to_enum(activity.priority)

    # Map recurrence
    recurrence = map_repeat_to_recurrence(activity.repeat_pattern)

    # Build request — model_validate so the ingestion validation context
    # applies (past due/scheduled dates are admissible for historical notes).
    request = TaskCreateRequest.model_validate(
        {
            "title": activity.description,
            "due_date": due_date,
            "scheduled_date": activity.scheduled_date,
            "duration_minutes": activity.duration_minutes or 30,
            "priority": priority,
            "status": EntityStatus.DRAFT if not activity.is_checked else EntityStatus.COMPLETED,
            "recurrence_pattern": recurrence,
            # Knowledge connections
            "applies_knowledge_uids": activity.get_linked_knowledge(),
            # Goal connections
            "fulfills_goal_uid": (
                activity.get_linked_goals()[0] if activity.get_linked_goals() else None
            ),
            # Tags from energy states (@energy) + obsidian-tasks #tags / period marker
            "tags": list(dict.fromkeys(activity.energy_states + activity.extra_tags)),
        },
        context=INGESTED_NOTE_CONTEXT,
    )

    logger.debug(f"Converted activity to TaskCreateRequest: {request.title}")
    return Result.ok(request)


# ============================================================================
# HABIT CONVERTER
# ============================================================================


@with_error_handling(error_type="system", operation="activity_to_habit_request")
def activity_to_habit_request(activity: ParsedActivityLine) -> Result[ConversionResult]:
    """
    Convert ParsedActivityLine to HabitCreateRequest.

    The resulting request can be passed to HabitsService.create_habit().

    Args:
        activity: Parsed activity line with context containing "habit"

    Returns:
        Result containing HabitCreateRequest
    """
    if not activity.is_habit():
        return _not_a(activity, EntityType.HABIT)

    request = HabitCreateRequest(
        title=activity.description,
        recurrence_pattern=map_repeat_to_recurrence(activity.repeat_pattern)
        or RecurrencePattern.DAILY,
        duration_minutes=activity.duration_minutes or 15,
        # A habit's slot comes from @when()'s hour, classified into the one
        # time-of-day vocabulary (habit-rhythm arc M1/M3). This previously took
        # @energy()'s first state, writing energy words like "medium" into a time
        # field; energy still reaches the habit as a tag below.
        #
        # Only when the author wrote a clock time: a date-only @when() parses to
        # midnight, and inferring LATE_NIGHT from it would schedule the habit at
        # 02:00 on the strength of a time nobody stated.
        preferred_time=(
            TimeOfDay.from_hour(activity.when.hour)
            if activity.when is not None and activity.when_has_clock_time
            else None
        ),
        linked_knowledge_uids=activity.get_linked_knowledge(),
        linked_goal_uids=activity.get_linked_goals(),
        linked_principle_uids=activity.get_linked_principles(),
        priority=map_dsl_priority_to_enum(activity.priority),
        tags=activity.energy_states if activity.energy_states else [],
    )

    logger.debug(f"Converted activity to HabitCreateRequest: {request.title}")
    return Result.ok(request)


# ============================================================================
# GOAL CONVERTER
# ============================================================================


@with_error_handling(error_type="system", operation="activity_to_goal_request")
def activity_to_goal_request(activity: ParsedActivityLine) -> Result[ConversionResult]:
    """
    Convert ParsedActivityLine to GoalCreateRequest.

    The resulting request can be passed to GoalsService.create_goal().

    Args:
        activity: Parsed activity line with context containing "goal"

    Returns:
        Result containing GoalCreateRequest
    """
    if not activity.is_goal():
        return _not_a(activity, EntityType.GOAL)

    # Extract target date if provided
    target_date: date | None = None
    if activity.when:
        target_date = activity.when.date()

    # model_validate so the ingestion validation context applies (a past
    # target_date on a historical note must not reject the goal). A past
    # target also needs a coherent start_date — the model defaults it to
    # today, which would violate the (kept) target-after-start invariant.
    data: dict[str, Any] = {
        "title": activity.description,
        "target_date": target_date,
        "priority": map_dsl_priority_to_enum(activity.priority),
        "required_knowledge_uids": activity.get_linked_knowledge(),
        "guiding_principle_uids": activity.get_linked_principles(),
        "tags": activity.energy_states if activity.energy_states else [],
    }
    if target_date is not None and target_date < date.today():
        data["start_date"] = target_date
    request = GoalCreateRequest.model_validate(data, context=INGESTED_NOTE_CONTEXT)

    logger.debug(f"Converted activity to GoalCreateRequest: {request.title}")
    return Result.ok(request)


# ============================================================================
# EVENT CONVERTER
# ============================================================================


@with_error_handling(error_type="system", operation="activity_to_event_request")
def activity_to_event_request(activity: ParsedActivityLine) -> Result[ConversionResult]:
    """
    Convert ParsedActivityLine to EventCreateRequest.

    The resulting request can be passed to EventsService.create_event().

    Args:
        activity: Parsed activity line with context containing "event"

    Returns:
        Result containing EventCreateRequest
    """
    if not activity.is_event():
        return _not_a(activity, EntityType.EVENT)

    # Events require a datetime
    event_datetime = activity.when or datetime.now()

    # Calculate end time based on duration
    duration = activity.duration_minutes or 60
    end_datetime = event_datetime + timedelta(minutes=duration)

    request = EventCreateRequest(
        title=activity.description,
        event_date=event_datetime.date(),
        start_time=event_datetime.time(),
        end_time=end_datetime.time(),
        priority=map_dsl_priority_to_enum(activity.priority),
        practices_knowledge_uids=activity.get_linked_knowledge(),
        recurrence_pattern=map_repeat_to_recurrence(activity.repeat_pattern),
        tags=activity.energy_states if activity.energy_states else [],
    )

    logger.debug(f"Converted activity to EventCreateRequest: {request.title}")
    return Result.ok(request)


# ============================================================================
# PRINCIPLE CONVERTER
# ============================================================================


@with_error_handling(error_type="system", operation="activity_to_principle_request")
def activity_to_principle_request(activity: ParsedActivityLine) -> Result[ConversionResult]:
    """
    Convert ParsedActivityLine to PrincipleCreateRequest.

    Principles represent values, beliefs, and guiding philosophies that
    inform goals, choices, and habits.

    Args:
        activity: Parsed activity line with context containing "principle"

    Returns:
        Result containing PrincipleCreateRequest
    """
    if not activity.is_principle():
        return _not_a(activity, EntityType.PRINCIPLE)

    # Extract principle title (first part before any dash or colon)
    description = activity.description
    title = derive_principle_title(description)

    # Full statement is the complete description
    statement = description
    if len(statement) > 500:
        statement = statement[:497] + "..."

    # Map energy states to principle category
    # spiritual → SPIRITUAL, focus/creative → INTELLECTUAL, etc.
    principle_category = PrincipleCategory.PERSONAL
    if activity.energy_states:
        energy_to_category = {
            "spiritual": PrincipleCategory.SPIRITUAL,
            "emotion": PrincipleCategory.RELATIONAL,
            "focus": PrincipleCategory.INTELLECTUAL,
            "creative": PrincipleCategory.CREATIVE,
            "physical": PrincipleCategory.HEALTH,
            "social": PrincipleCategory.RELATIONAL,
        }
        for energy in activity.energy_states:
            if energy.lower() in energy_to_category:
                principle_category = energy_to_category[energy.lower()]
                break

    # Map DSL priority (1-5) to principle strength
    strength = PrincipleStrength.MODERATE
    if activity.priority:
        priority_to_strength = {
            1: PrincipleStrength.CORE,
            2: PrincipleStrength.STRONG,
            3: PrincipleStrength.MODERATE,
            4: PrincipleStrength.DEVELOPING,
            5: PrincipleStrength.EXPLORING,
        }
        strength = priority_to_strength.get(activity.priority, PrincipleStrength.MODERATE)

    request = PrincipleCreateRequest(
        title=title,
        statement=statement,
        description=description if description != statement else None,
        principle_category=principle_category,
        principle_source=PrincipleSource.PERSONAL,  # DSL entries are personal by default
        strength=strength,
        priority=map_dsl_priority_to_enum(activity.priority),
        tags=activity.energy_states if activity.energy_states else [],
    )

    logger.debug(f"Converted activity to PrincipleCreateRequest: {request.title}")
    return Result.ok(request)


# ============================================================================
# CHOICE CONVERTER
# ============================================================================


@with_error_handling(error_type="system", operation="activity_to_choice_request")
def activity_to_choice_request(activity: ParsedActivityLine) -> Result[ConversionResult]:
    """
    Convert ParsedActivityLine to ChoiceCreateRequest.

    Choices represent decisions to be made, with options to evaluate
    and criteria to consider.

    Args:
        activity: Parsed activity line with context containing "choice"

    Returns:
        Result containing ChoiceCreateRequest
    """
    if not activity.is_choice():
        return _not_a(activity, EntityType.CHOICE)

    # Title from description
    title = derive_choice_title(activity.description)

    # Infer domain from energy states
    domain = Domain.PERSONAL
    if activity.energy_states:
        energy_to_domain = {
            "focus": Domain.TECH,
            "creative": Domain.CREATIVE,
            "social": Domain.SOCIAL,
            "physical": Domain.HEALTH,
            "spiritual": Domain.PERSONAL,
        }
        for energy in activity.energy_states:
            if energy.lower() in energy_to_domain:
                domain = energy_to_domain[energy.lower()]
                break

    # Determine choice type from context
    # If binary keywords detected, mark as binary
    binary_keywords = ["whether", "or not", "should i", "yes or no"]
    choice_type = ChoiceType.MULTIPLE
    if any(kw in activity.description.lower() for kw in binary_keywords):
        choice_type = ChoiceType.BINARY

    request = ChoiceCreateRequest(
        title=title,
        description=activity.description,
        choice_type=choice_type,
        priority=map_dsl_priority_to_enum(activity.priority),
        domain=domain,
        decision_deadline=activity.when,
        informed_by_knowledge_uids=activity.get_linked_knowledge(),
        tags=activity.energy_states if activity.energy_states else [],
    )

    logger.debug(f"Converted activity to ChoiceCreateRequest: {request.title}")
    return Result.ok(request)
