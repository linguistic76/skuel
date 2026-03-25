"""
Activity Entity Converter
=========================

Converts ParsedActivityLine (with type-safe EntityType/NonKuDomain contexts) into SKUEL domain entities.

This is the bridge from DSL parsing to entity creation:
- ParsedActivityLine → TaskCreateRequest → Task
- ParsedActivityLine → dict → Service.create()

The converter functions live in sub-modules:
- `activity_domain_converters` — Task, Habit, Goal, Event, Principle, Choice
- `specialized_domain_converters` — Finance, KU, LS, LP, Report, Analytics, Calendar, LifePath
- `dsl_mappings` — Shared mapping helpers and type aliases
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from core.models.enums.entity_enums import EntityType, NonKuDomain
from core.services.dsl.activity_domain_converters import (
    activity_to_choice_dict,
    activity_to_event_dict,
    activity_to_goal_dict,
    activity_to_habit_dict,
    activity_to_principle_dict,
    activity_to_task_request,
)
from core.services.dsl.activity_dsl_parser import ParsedActivityLine, ParsedJournal
from core.services.dsl.dsl_mappings import (
    ConversionResult,
    map_dsl_priority_to_enum,
    map_repeat_to_recurrence,
)
from core.services.dsl.specialized_domain_converters import (
    activity_to_analytics_dict,
    activity_to_calendar_dict,
    activity_to_finance_dict,
    activity_to_ku_dict,
    activity_to_lifepath_dict,
    activity_to_lp_dict,
    activity_to_ls_dict,
    activity_to_report_dict,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

# Re-export all converter functions and mappings for backward compatibility
__all__ = [
    "ActivityEntityConverter",
    "ConversionResult",
    "CreateRequestProtocol",
    "TypedConversionResult",
    "activity_to_analytics_dict",
    "activity_to_calendar_dict",
    "activity_to_choice_dict",
    "activity_to_event_dict",
    "activity_to_finance_dict",
    "activity_to_goal_dict",
    "activity_to_habit_dict",
    "activity_to_ku_dict",
    "activity_to_lifepath_dict",
    "activity_to_lp_dict",
    "activity_to_ls_dict",
    "activity_to_principle_dict",
    "activity_to_report_dict",
    "activity_to_task_request",
    "map_dsl_priority_to_enum",
    "map_repeat_to_recurrence",
]

# ============================================================================
# PROTOCOL DEFINITIONS
# ============================================================================


@runtime_checkable
class CreateRequestProtocol(Protocol):
    """
    Protocol for entity creation requests.

    All typed CreateRequest classes (TaskCreateRequest, HabitCreateRequest, etc.)
    implicitly satisfy this protocol. This enables type-safe handling of
    conversion results without knowing the concrete type.
    """

    pass  # Marker protocol for create requests


@dataclass
class TypedConversionResult:
    """
    Wrapper for conversion results with entity type information.

    Provides both the converted data and the entity type it represents,
    enabling type-safe dispatch in consuming code.

    Attributes:
        entity_type: The EntityType or NonKuDomain this conversion produced
        data: The converted data (CreateRequest or dict)
        source_activity: Reference to the original ParsedActivityLine
    """

    entity_type: EntityType | NonKuDomain
    data: ConversionResult
    source_activity: ParsedActivityLine


logger = get_logger("skuel.dsl.converter")


# ============================================================================
# JOURNAL DISPATCH TABLE
# ============================================================================

# (method_name on ParsedActivityLine, converter_fn, result_key, error_label)
_JOURNAL_DISPATCH: list[
    tuple[str, Callable[[ParsedActivityLine], Result[ConversionResult]], str, str]
] = [
    # Activity Domains (7)
    ("is_task", activity_to_task_request, "tasks", "Task"),
    ("is_habit", activity_to_habit_dict, "habits", "Habit"),
    ("is_goal", activity_to_goal_dict, "goals", "Goal"),
    ("is_event", activity_to_event_dict, "events", "Event"),
    ("is_principle", activity_to_principle_dict, "principles", "Principle"),
    ("is_choice", activity_to_choice_dict, "choices", "Choice"),
    ("is_finance", activity_to_finance_dict, "finances", "Finance"),
    # Curriculum Domains (3)
    ("is_lesson", activity_to_ku_dict, "knowledge_units", "KU"),
    ("is_ls", activity_to_ls_dict, "learning_steps", "LS"),
    ("is_lp", activity_to_lp_dict, "learning_paths", "LP"),
    # Meta Domains (2 — analytics has no is_analytics() guard)
    ("is_report", activity_to_report_dict, "reports", "Report"),
    ("is_calendar", activity_to_calendar_dict, "calendar_items", "Calendar"),
    # The Destination (+1)
    ("is_lifepath", activity_to_lifepath_dict, "lifepath_items", "LifePath"),
]


# ============================================================================
# BATCH CONVERTER
# ============================================================================


class ActivityEntityConverter:
    """
    Converts parsed activities to SKUEL entity requests.

    Handles batch conversion from ParsedJournal to create requests
    for all 13 domain types.
    """

    def __init__(self) -> None:
        """Initialize converter."""
        self.logger = get_logger("skuel.dsl.converter")

    def convert_journal(self, parsed: ParsedJournal) -> dict[str, list[Any]]:
        """
        Convert all activities in a parsed journal to entity requests.

        Returns dict with keys for ALL 13 SKUEL domains + errors:

        **Activity Domains (7) - What I DO:**
        - "tasks": list of TaskCreateRequest
        - "habits": list of habit dicts
        - "goals": list of goal dicts
        - "events": list of event dicts
        - "principles": list of principle dicts
        - "choices": list of choice dicts
        - "finances": list of finance dicts

        **Curriculum Domains (3) - What I LEARN:**
        - "knowledge_units": list of KU dicts
        - "learning_steps": list of LS dicts
        - "learning_paths": list of LP dicts

        **Meta Domains (3) - How I ORGANIZE:**
        - "reports": list of report dicts
        - "analytics": list of analytics dicts
        - "calendar_items": list of calendar dicts

        **The Destination (+1) - Where I'm GOING:**
        - "lifepath_items": list of lifepath dicts

        **Errors:**
        - "errors": list of conversion error messages
        """
        results: dict[str, list[Any]] = {
            # Activity Domains (7)
            "tasks": [],
            "habits": [],
            "goals": [],
            "events": [],
            "principles": [],
            "choices": [],
            "finances": [],
            # Curriculum Domains (3)
            "knowledge_units": [],
            "learning_steps": [],
            "learning_paths": [],
            # Meta Domains (3)
            "reports": [],
            "analytics": [],
            "calendar_items": [],
            # The Destination (+1)
            "lifepath_items": [],
            # Errors
            "errors": [],
        }

        for activity in parsed.activities:
            for method_name, converter_fn, result_key, error_label in _JOURNAL_DISPATCH:
                check_method: Callable[[], bool] = getattr(activity, method_name)
                if check_method():
                    result = converter_fn(activity)
                    if result.is_ok:
                        results[result_key].append(result.value)
                    else:
                        results["errors"].append(f"{error_label} conversion: {result.error}")

        # Log conversion summary
        self.logger.info(
            f"Converted journal: "
            # Activity domains
            f"{len(results['tasks'])} tasks, "
            f"{len(results['habits'])} habits, "
            f"{len(results['goals'])} goals, "
            f"{len(results['events'])} events, "
            f"{len(results['principles'])} principles, "
            f"{len(results['choices'])} choices, "
            f"{len(results['finances'])} finances, "
            # Curriculum domains
            f"{len(results['knowledge_units'])} KUs, "
            f"{len(results['learning_steps'])} LSs, "
            f"{len(results['learning_paths'])} LPs, "
            # Meta domains
            f"{len(results['reports'])} reports, "
            f"{len(results['analytics'])} analytics, "
            f"{len(results['calendar_items'])} calendar items, "
            # Destination
            f"{len(results['lifepath_items'])} lifepath items, "
            # Errors
            f"{len(results['errors'])} errors"
        )

        return results

    # ========================================================================
    # PROTOCOL-VERIFIED CONVERSION (Type-Safe EntityType/NonKuDomain Dispatch)
    # ========================================================================

    def convert(
        self,
        activity: ParsedActivityLine,
        entity_type: EntityType | NonKuDomain | None = None,
    ) -> Result[ConversionResult]:
        """
        Convert a ParsedActivityLine to a create request using EntityType/NonKuDomain dispatch.

        Args:
            activity: The parsed activity line to convert
            entity_type: Specific EntityType or NonKuDomain to convert to (defaults to primary_context)

        Returns:
            Result containing either:
            - TaskCreateRequest (for EntityType.TASK)
            - dict[str, Any] (for other entity types, pending typed request classes)
        """
        # Determine entity type to convert to
        target_type = entity_type or activity.primary_context

        if target_type is None:
            return Result.fail(
                Errors.validation(
                    message="Activity has no context to convert",
                    field="contexts",
                    value="[]",
                )
            )

        # EntityType/NonKuDomain-based dispatch
        match target_type:
            # ================================================================
            # ACTIVITY DOMAINS (6) - EntityType
            # ================================================================
            case EntityType.TASK:
                return activity_to_task_request(activity)

            case EntityType.HABIT:
                return activity_to_habit_dict(activity)

            case EntityType.GOAL:
                return activity_to_goal_dict(activity)

            case EntityType.EVENT:
                return activity_to_event_dict(activity)

            case EntityType.PRINCIPLE:
                return activity_to_principle_dict(activity)

            case EntityType.CHOICE:
                return activity_to_choice_dict(activity)

            # ================================================================
            # NON-KU DOMAINS - NonKuDomain
            # ================================================================
            case NonKuDomain.FINANCE:
                return activity_to_finance_dict(activity)

            case NonKuDomain.CALENDAR:
                return activity_to_calendar_dict(activity)

            case NonKuDomain.LEARNING:
                # LEARNING is a general learning context - a modifier, not a primary entity type
                return Result.ok(
                    {
                        "type": "learning_activity",
                        "description": activity.description,
                        "primary_ku": activity.primary_ku,
                        "linked_knowledge": activity.get_linked_knowledge(),
                        "duration_minutes": activity.duration_minutes,
                        "tags": activity.energy_states if activity.energy_states else [],
                    }
                )

            # ================================================================
            # CURRICULUM DOMAINS (3) - EntityType
            # ================================================================
            case EntityType.LESSON:
                return activity_to_ku_dict(activity)

            case EntityType.LEARNING_STEP:
                return activity_to_ls_dict(activity)

            case EntityType.LEARNING_PATH:
                return activity_to_lp_dict(activity)

            # ================================================================
            # CONTENT PROCESSING - EntityType
            # ================================================================
            case EntityType.EXERCISE_SUBMISSION:
                return activity_to_report_dict(activity)

            # ================================================================
            # THE DESTINATION (+1) - EntityType
            # ================================================================
            case EntityType.LIFE_PATH:
                return activity_to_lifepath_dict(activity)

            # ================================================================
            # FALLBACK
            # ================================================================
            case _:
                return Result.fail(
                    Errors.validation(
                        message=f"Unsupported entity type for conversion: {target_type}",
                        field="entity_type",
                        value=target_type.value,
                    )
                )

    def convert_typed(
        self,
        activity: ParsedActivityLine,
        entity_type: EntityType | NonKuDomain | None = None,
    ) -> Result[TypedConversionResult]:
        """
        Convert with full type information preserved.

        Returns a TypedConversionResult that includes the EntityType or NonKuDomain,
        enabling type-safe pattern matching on both the type and the data.

        Args:
            activity: The parsed activity line to convert
            entity_type: Specific EntityType or NonKuDomain to convert to (defaults to primary_context)

        Returns:
            Result containing TypedConversionResult
        """
        target_type = entity_type or activity.primary_context

        if target_type is None:
            return Result.fail(
                Errors.validation(
                    message="Activity has no context to convert",
                    field="contexts",
                    value="[]",
                )
            )

        # Convert using standard method
        conversion_result = self.convert(activity, target_type)

        if conversion_result.is_error:
            return Result.fail(conversion_result)

        # Wrap in TypedConversionResult
        typed_result = TypedConversionResult(
            entity_type=target_type,
            data=conversion_result.value,
            source_activity=activity,
        )

        return Result.ok(typed_result)

    def convert_all_contexts(
        self,
        activity: ParsedActivityLine,
    ) -> list[Result[TypedConversionResult]]:
        """
        Convert an activity for ALL its contexts (multi-context support).

        An activity can have multiple contexts (e.g., `@context(task,learning)`).
        This method converts to each context type and returns all results.

        Args:
            activity: The parsed activity line (may have multiple contexts)

        Returns:
            List of Results, one per context in the activity
        """
        results: list[Result[TypedConversionResult]] = []

        for context in activity.contexts:
            result = self.convert_typed(activity, context)
            results.append(result)

        return results
