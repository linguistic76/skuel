"""
Event Converters
================

Conversion functions between the three tiers of event models:
- External (Pydantic) ↔ Transfer (DTO) ↔ Core (Domain)

Preserves learning integration data (habits, knowledge, goals, tasks) throughout all conversions.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from .event import Event
from .event_dto import EventDTO
from .event_request import EventCreateRequest

if TYPE_CHECKING:
    from .event_relationships import EventRelationships

# ============================================================================
# EXTERNAL → TRANSFER (Request → DTO)
# ============================================================================


def event_create_request_to_dto(request: EventCreateRequest, user_uid: str) -> EventDTO:
    """
    Convert EventCreateRequest to EventDTO.

    Args:
        request: Validated external request
        user_uid: User UID (from authentication context)

    Returns:
        DTO ready for service operations with learning fields preserved
    """
    return EventDTO.create(
        user_uid=user_uid,
        title=request.title,
        description=request.description,
        event_date=request.event_date,
        start_time=request.start_time,
        end_time=request.end_time,
        event_type=request.event_type,
        priority=request.priority,
        location=request.location,
        is_online=request.is_online,
        meeting_url=request.meeting_url,
        tags=request.tags or [],
        attendee_emails=request.attendee_emails or [],
        max_attendees=request.max_attendees,
        recurrence_pattern=request.recurrence_pattern,
        recurrence_end_date=request.recurrence_end_date,
        reminder_minutes=request.reminder_minutes,
        reinforces_habit_uid=request.reinforces_habit_uid,
        # PHASE 3B: practices_knowledge_uids and executes_tasks are graph relationships
        # Services create these via relationship services after entity creation
        milestone_celebration_for_goal=request.milestone_celebration_for_goal,
    )


# NOTE: event_update_request_to_dto_updates() removed - use generic helper directly:
#   - from core.utils.converter_helpers import update_request_to_dict
#   - updates = update_request_to_dict(request)
#
# This eliminates domain-specific wrappers in favor of the generic pattern.
# The helper works for ANY domain's update request (Pydantic BaseModel).


# ============================================================================
# TRANSFER ↔ CORE (DTO ↔ Domain)
# ============================================================================
# NOTE: Wrapper functions removed - use model methods directly:
#   - Event.from_dto(dto) instead of event_dto_to_domain(dto)
#   - event.to_dto() instead of event_domain_to_dto(event)


# ============================================================================
# EXTERNAL → CORE (Direct conversion for read operations)
# ============================================================================


def event_create_request_to_domain(request: EventCreateRequest, user_uid: str) -> Event:
    """
    Direct conversion from create request to domain model.
    Useful for operations that don't need intermediate DTO manipulation.

    Args:
        request: Validated external request
        user_uid: User UID (from authentication context)

    Returns:
        Immutable domain model with learning integration
    """
    dto = event_create_request_to_dto(request, user_uid)
    return Event.from_dto(dto)


# ============================================================================
# DATABASE OPERATIONS (Dict ↔ DTO)
# ============================================================================


def event_dict_to_dto(data: dict[str, Any]) -> EventDTO:
    """
    Convert dictionary (from database) to EventDTO.
    Preserves all learning integration fields.

    Args:
        data: Raw dictionary from database/Neo4j with learning data,

    Returns:
        DTO with parsed and validated data including learning enhancements
    """
    return EventDTO.from_dict(data)


# NOTE: event_dto_to_dict() removed - use dto.to_dict() directly


# ============================================================================
# LEARNING INTEGRATION OPERATIONS
# ============================================================================


def extract_learning_summary_from_event(
    event: Event, rels: "EventRelationships | None" = None
) -> dict[str, Any]:
    """
    Extract learning integration summary from an event.

    Args:
        event: Domain model with learning data
        rels: Event relationships from graph

    Returns:
        Summary dictionary with learning metrics
    """
    # GRAPH-NATIVE: Get relationship data from rels parameter
    practices_knowledge_count = len(rels.practices_knowledge_uids) if rels else 0
    knowledge_uids = list(rels.practices_knowledge_uids) if rels else []
    executes_tasks_count = len(rels.executes_task_uids) if rels else 0
    task_uids = list(rels.executes_task_uids) if rels else []
    has_conflicts = len(rels.conflicts_with_uids) if rels else 0 > 0
    conflict_count = len(rels.conflicts_with_uids) if rels else 0

    return {
        "uid": event.uid,
        "title": event.title,
        "event_date": event.event_date.isoformat() if event.event_date else None,
        "reinforces_habit": event.reinforces_habit_uid is not None,
        "habit_uid": event.reinforces_habit_uid,
        "practices_knowledge_count": practices_knowledge_count,
        "knowledge_uids": knowledge_uids,
        "is_milestone_celebration": event.milestone_celebration_for_goal is not None,
        "goal_uid": event.milestone_celebration_for_goal,
        "executes_tasks_count": executes_tasks_count,
        "task_uids": task_uids,
        "learning_integration_level": _calculate_learning_integration_level(event, rels),
        "has_conflicts": has_conflicts,
        "conflict_count": conflict_count,
    }


def _calculate_learning_integration_level(
    event: Event, rels: "EventRelationships | None" = None
) -> str:
    """
    Calculate the level of learning integration for an event.

    Args:
        event: Domain model
        rels: Event relationships from graph

    Returns:
        Integration level: 'none', 'basic', 'moderate', 'high', 'comprehensive'
    """
    integration_count = 0

    # Count each type of integration
    if event.reinforces_habit_uid:
        integration_count += 1

    # GRAPH-NATIVE: Get relationship counts from rels parameter
    practices_knowledge_count = len(rels.practices_knowledge_uids) if rels else 0
    executes_tasks_count = len(rels.executes_task_uids) if rels else 0

    if practices_knowledge_count > 0:
        integration_count += practices_knowledge_count
    if event.milestone_celebration_for_goal:
        integration_count += 2  # Milestones are significant
    if executes_tasks_count > 0:
        integration_count += executes_tasks_count

    if integration_count == 0:
        return "none"
    elif integration_count == 1:
        return "basic"
    elif integration_count <= 3:
        return "moderate"
    elif integration_count <= 6:
        return "high"
    else:
        return "comprehensive"


def enrich_event_dto_with_conflicts(dto: EventDTO, conflicting_event_uids: list[str]) -> EventDTO:
    """
    Add conflict information to an event DTO.

    GRAPH-NATIVE: conflicts_with is GRAPH-NATIVE, store in metadata instead.
    Graph relationship: (event)-[:CONFLICTS_WITH]->(other_event)

    Args:
        dto: Event DTO to enhance,
        conflicting_event_uids: UIDs of conflicting events

    Returns:
        DTO with conflict data in metadata
    """
    # GRAPH-NATIVE: Store in metadata since conflicts_with field removed from EventDTO
    dto.metadata["conflicts_with"] = conflicting_event_uids
    dto.updated_at = datetime.now()
    return dto


def extract_scheduling_metadata(event: Event) -> dict[str, Any]:
    """
    Extract scheduling metadata for calendar operations.

    Args:
        event: Domain model,

    Returns:
        Scheduling metadata dictionary
    """
    return {
        "uid": event.uid,
        "title": event.title,
        "event_date": event.event_date,
        "start_time": event.start_time,
        "end_time": event.end_time,
        "duration_minutes": event.duration_minutes,
        "is_recurring": event.recurrence_pattern is not None,
        "recurrence_pattern": event.recurrence_pattern.value if event.recurrence_pattern else None,
        "recurrence_end_date": event.recurrence_end_date,
        "has_reminder": event.reminder_minutes is not None,
        "reminder_minutes": event.reminder_minutes,
        "reminder_sent": event.reminder_sent,
        "is_online": event.is_online,
        "has_location": event.location is not None,
        "status": event.status.value,
        "priority": event.priority.value,
    }


# ============================================================================
# BULK OPERATIONS
# ============================================================================


def event_create_requests_to_dtos(
    requests: list[EventCreateRequest], user_uid: str
) -> list[EventDTO]:
    """
    Convert multiple create requests to DTOs.

    Args:
        requests: List of validated external requests
        user_uid: User UID (from authentication context)

    Returns:
        List of DTOs ready for bulk operations
    """
    return [event_create_request_to_dto(request, user_uid) for request in requests]


def event_dtos_to_domains(dtos: list[EventDTO]) -> list[Event]:
    """
    Convert multiple DTOs to domain models.

    Args:
        dtos: List of transfer objects with learning data,

    Returns:
        List of immutable domain models
    """
    return [Event.from_dto(dto) for dto in dtos]


def event_domains_to_dtos(events: list[Event]) -> list[EventDTO]:
    """
    Convert multiple domain models to DTOs.

    Args:
        events: List of domain models,

    Returns:
        List of mutable DTOs
    """
    return [event.to_dto() for event in events]


def event_dicts_to_dtos(dicts: list[dict[str, Any]]) -> list[EventDTO]:
    """
    Convert multiple dictionaries to DTOs.

    Args:
        dicts: List of raw dictionaries from database,

    Returns:
        List of DTOs with parsed data
    """
    return [event_dict_to_dto(d) for d in dicts]


# ============================================================================
# RECURRENCE OPERATIONS
# ============================================================================


def extract_recurrence_metadata(event: Event) -> dict[str, Any]:
    """
    Extract recurrence metadata for series management.

    Args:
        event: Domain model,

    Returns:
        Recurrence metadata dictionary
    """
    return {
        "uid": event.uid,
        "is_recurring": event.recurrence_pattern is not None,
        "recurrence_pattern": event.recurrence_pattern.value if event.recurrence_pattern else None,
        "recurrence_end_date": event.recurrence_end_date,
        "is_recurrence_child": event.recurrence_parent_uid is not None,
        "recurrence_parent_uid": event.recurrence_parent_uid,
        "can_edit_series": event.recurrence_parent_uid is None,  # Only parent can edit series
        # NOTE: Recurrence calculation not implemented - next_occurrence_date always None
        "next_occurrence_date": None,
    }


# ============================================================================
# VALIDATION HELPERS
# ============================================================================


def validate_event_time_data(data: dict[str, Any]) -> dict[str, Any]:
    """
    Validate and normalize event time data.

    Uses generic validation helpers from validation_helpers.py.

    Args:
        data: Raw dictionary with potentially inconsistent time data,

    Returns:
        Validated dictionary with normalized time data
    """
    from core.utils.validation_helpers import (
        ensure_list_fields,
        parse_date_fields,
        parse_time_fields,
    )

    validated = data.copy()

    # Parse date fields using generic helper
    parse_date_fields(validated, ["event_date", "recurrence_end_date"])

    # Parse time fields using generic helper
    parse_time_fields(validated, ["start_time", "end_time"])

    # Ensure list fields using generic helper
    ensure_list_fields(
        validated,
        [
            "practices_knowledge_uids",
            "executes_tasks",
            "attendee_emails",
            "conflicts_with",
            "tags",
        ],
    )

    return validated
