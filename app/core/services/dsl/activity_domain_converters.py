"""
Activity Domain Converters
==========================

Converter functions for the 6 Activity Domains:
Task, Habit, Goal, Event, Principle, Choice.

Each function converts a ParsedActivityLine to a domain-specific
create request (TaskCreateRequest) or dict.
"""

from datetime import date, datetime, timedelta

from core.models.enums import EntityStatus
from core.models.enums.entity_enums import EntityType
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


# ============================================================================
# TASK CONVERTER
# ============================================================================


@with_error_handling(error_type="system", operation="activity_to_task_request")
def activity_to_task_request(activity: ParsedActivityLine) -> Result[ConversionResult]:
    """
    Convert ParsedActivityLine to TaskCreateRequest.

    The resulting request can be passed to TasksCoreService.create_task().

    Args:
        activity: Parsed activity line with context containing "task"

    Returns:
        Result containing TaskCreateRequest (as ConversionResult for type compatibility)
    """
    if not activity.is_task():
        return Result.fail(
            Errors.validation(
                message=f"Activity is not a task (missing '{EntityType.TASK.value}' in @context)",
                field="context",
                value=",".join(activity.context_values),
            )
        )

    # Extract due date from @when
    due_date: date | None = None
    if activity.when:
        due_date = activity.when.date()

    # Map priority
    priority = map_dsl_priority_to_enum(activity.priority)

    # Map recurrence
    recurrence = map_repeat_to_recurrence(activity.repeat_pattern)

    # Build request
    request = TaskCreateRequest(
        title=activity.description,
        due_date=due_date,
        duration_minutes=activity.duration_minutes or 30,
        priority=priority,
        status=EntityStatus.DRAFT if not activity.is_checked else EntityStatus.COMPLETED,
        recurrence_pattern=recurrence,
        # Knowledge connections
        applies_knowledge_uids=activity.get_linked_knowledge(),
        # Goal connections
        fulfills_goal_uid=activity.get_linked_goals()[0] if activity.get_linked_goals() else None,
        # Tags from energy states
        tags=activity.energy_states if activity.energy_states else [],
    )

    logger.debug(f"Converted activity to TaskCreateRequest: {request.title}")
    return Result.ok(request)


# ============================================================================
# HABIT CONVERTER
# ============================================================================


@with_error_handling(error_type="system", operation="activity_to_habit_dict")
def activity_to_habit_dict(activity: ParsedActivityLine) -> Result[ConversionResult]:
    """
    Convert ParsedActivityLine to habit creation dict.

    Since HabitCreateRequest may vary, this returns a dict that can be
    adapted to your specific habit service.

    Args:
        activity: Parsed activity line with context containing "habit"

    Returns:
        Result containing dict for habit creation
    """
    if not activity.is_habit():
        return Result.fail(
            Errors.validation(
                message=f"Activity is not a habit (missing '{EntityType.HABIT.value}' in @context)",
                field="context",
                value=",".join(activity.context_values),
            )
        )

    # Map recurrence to frequency string
    frequency = "daily"  # default
    if activity.repeat_pattern:
        pattern_type = activity.repeat_pattern.get("type", "daily")
        if pattern_type == "weekly":
            days = activity.repeat_pattern.get("days", [])
            frequency = f"weekly:{','.join(days)}" if days else "weekly"
        elif pattern_type == "interval":
            interval = activity.repeat_pattern.get("interval", 1)
            unit = activity.repeat_pattern.get("unit", "days")
            frequency = f"every_{interval}_{unit}"
        else:
            frequency = pattern_type

    habit_dict = {
        "title": activity.description,
        "frequency": frequency,
        "duration_minutes": activity.duration_minutes,
        "energy_required": activity.energy_states[0] if activity.energy_states else None,
        "linked_knowledge_uids": activity.get_linked_knowledge(),
        "linked_goal_uids": activity.get_linked_goals(),
        "linked_principle_uids": activity.get_linked_principles(),
        "tags": activity.energy_states,
    }

    logger.debug(f"Converted activity to habit dict: {habit_dict['title']}")
    return Result.ok(habit_dict)


# ============================================================================
# GOAL CONVERTER
# ============================================================================


@with_error_handling(error_type="system", operation="activity_to_goal_dict")
def activity_to_goal_dict(activity: ParsedActivityLine) -> Result[ConversionResult]:
    """
    Convert ParsedActivityLine to goal creation dict.

    Args:
        activity: Parsed activity line with context containing "goal"

    Returns:
        Result containing dict for goal creation
    """
    if not activity.is_goal():
        return Result.fail(
            Errors.validation(
                message=f"Activity is not a goal (missing '{EntityType.GOAL.value}' in @context)",
                field="context",
                value=",".join(activity.context_values),
            )
        )

    # Extract target date if provided
    target_date: date | None = None
    if activity.when:
        target_date = activity.when.date()

    goal_dict = {
        "title": activity.description,
        "target_date": target_date,
        "priority": activity.priority,
        "linked_knowledge_uids": activity.get_linked_knowledge(),
        "linked_principle_uids": activity.get_linked_principles(),
        "tags": activity.energy_states,
    }

    logger.debug(f"Converted activity to goal dict: {goal_dict['title']}")
    return Result.ok(goal_dict)


# ============================================================================
# EVENT CONVERTER
# ============================================================================


@with_error_handling(error_type="system", operation="activity_to_event_dict")
def activity_to_event_dict(activity: ParsedActivityLine) -> Result[ConversionResult]:
    """
    Convert ParsedActivityLine to event creation dict.

    Args:
        activity: Parsed activity line with context containing "event"

    Returns:
        Result containing dict for event creation
    """
    if not activity.is_event():
        return Result.fail(
            Errors.validation(
                message=f"Activity is not an event (missing '{EntityType.EVENT.value}' in @context)",
                field="context",
                value=",".join(activity.context_values),
            )
        )

    # Events require a datetime
    event_datetime = activity.when or datetime.now()

    # Calculate end time based on duration
    duration = activity.duration_minutes or 60
    end_datetime = event_datetime + timedelta(minutes=duration)

    event_dict = {
        "title": activity.description,
        "start_datetime": event_datetime,
        "end_datetime": end_datetime,
        "duration_minutes": duration,
        "priority": activity.priority,
        "linked_knowledge_uids": activity.get_linked_knowledge(),
        "linked_goal_uids": activity.get_linked_goals(),
        "recurrence_pattern": map_repeat_to_recurrence(activity.repeat_pattern),
        "tags": activity.energy_states,
    }

    logger.debug(f"Converted activity to event dict: {event_dict['title']}")
    return Result.ok(event_dict)


# ============================================================================
# PRINCIPLE CONVERTER
# ============================================================================


@with_error_handling(error_type="system", operation="activity_to_principle_dict")
def activity_to_principle_dict(activity: ParsedActivityLine) -> Result[ConversionResult]:
    """
    Convert ParsedActivityLine to principle creation dict.

    Principles represent values, beliefs, and guiding philosophies that
    inform goals, choices, and habits.

    Args:
        activity: Parsed activity line with context containing "principle"

    Returns:
        Result containing dict for principle creation
    """
    if not activity.is_principle():
        return Result.fail(
            Errors.validation(
                message=f"Activity is not a principle (missing '{EntityType.PRINCIPLE.value}' in @context)",
                field="context",
                value=",".join(activity.context_values),
            )
        )

    # Extract principle title (first part before any dash or colon)
    description = activity.description
    title = description.split(" - ")[0].split(":")[0].strip()
    if len(title) > 100:
        title = title[:97] + "..."

    # Full statement is the complete description
    statement = description
    if len(statement) > 500:
        statement = statement[:497] + "..."

    # Map energy states to principle category
    # spiritual → SPIRITUAL, focus/creative → INTELLECTUAL, etc.
    principle_category = "personal"  # default
    if activity.energy_states:
        energy_to_category = {
            "spiritual": "spiritual",
            "emotion": "relational",
            "focus": "intellectual",
            "creative": "creative",
            "physical": "health",
            "social": "relational",
        }
        for energy in activity.energy_states:
            if energy.lower() in energy_to_category:
                principle_category = energy_to_category[energy.lower()]
                break

    # Map priority to principle strength
    strength = "moderate"  # default
    if activity.priority:
        priority_to_strength = {
            1: "core",  # Priority 1 = Core principle
            2: "strong",  # Priority 2 = Strong
            3: "moderate",  # Priority 3 = Moderate
            4: "developing",
            5: "exploring",
        }
        strength = priority_to_strength.get(activity.priority, "moderate")

    principle_dict = {
        "title": title,
        "statement": statement,
        "description": description if description != statement else None,
        "principle_category": principle_category,
        "principle_source": "personal",  # DSL entries are personal by default
        "strength": strength,
        "priority": activity.priority or 3,
        "linked_knowledge_uids": activity.get_linked_knowledge(),
        "linked_goal_uids": activity.get_linked_goals(),
        "tags": activity.energy_states if activity.energy_states else [],
        "key_behaviors": [],  # Can be extracted from description if needed
    }

    logger.debug(f"Converted activity to principle dict: {principle_dict['title']}")
    return Result.ok(principle_dict)


# ============================================================================
# CHOICE CONVERTER
# ============================================================================


@with_error_handling(error_type="system", operation="activity_to_choice_dict")
def activity_to_choice_dict(activity: ParsedActivityLine) -> Result[ConversionResult]:
    """
    Convert ParsedActivityLine to choice creation dict.

    Choices represent decisions to be made, with options to evaluate
    and criteria to consider.

    Args:
        activity: Parsed activity line with context containing "choice"

    Returns:
        Result containing dict for choice creation
    """
    if not activity.is_choice():
        return Result.fail(
            Errors.validation(
                message=f"Activity is not a choice (missing '{EntityType.CHOICE.value}' in @context)",
                field="context",
                value=",".join(activity.context_values),
            )
        )

    # Title from description
    title = activity.description
    if len(title) > 200:
        title = title[:197] + "..."

    # Decision deadline from @when
    deadline = activity.when

    # Map priority (1-5) to Priority enum
    priority = map_dsl_priority_to_enum(activity.priority)

    # Infer domain from linked entities or energy states
    domain = "personal"  # default
    if activity.energy_states:
        energy_to_domain = {
            "focus": "tech",
            "creative": "creative",
            "social": "social",
            "physical": "health",
            "spiritual": "personal",
        }
        for energy in activity.energy_states:
            if energy.lower() in energy_to_domain:
                domain = energy_to_domain[energy.lower()]
                break

    # Determine choice type from context
    # If binary keywords detected, mark as binary
    binary_keywords = ["whether", "or not", "should i", "yes or no"]
    choice_type = "multiple"  # default
    if any(kw in activity.description.lower() for kw in binary_keywords):
        choice_type = "binary"

    choice_dict = {
        "title": title,
        "description": activity.description,
        "choice_type": choice_type,
        "priority": priority.value if priority else "medium",
        "domain": domain,
        "decision_deadline": deadline,
        "decision_criteria": [],  # Can be extracted from description
        "constraints": [],
        "stakeholders": [],
        "informed_by_knowledge_uids": activity.get_linked_knowledge(),
        "linked_goal_uids": activity.get_linked_goals(),
        "linked_principle_uids": activity.get_linked_principles(),
        "tags": activity.energy_states if activity.energy_states else [],
    }

    logger.debug(f"Converted activity to choice dict: {choice_dict['title']}")
    return Result.ok(choice_dict)
