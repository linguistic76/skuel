"""
Habit Converters
================

Conversion functions between the three tiers of habit models:
- External (Pydantic) ↔ Transfer (DTO) ↔ Core (Domain)

Preserves learning integration data (knowledge, goals, principles, curriculum spine) throughout all conversions.
Includes Atomic Habits identity-based habit support.
"""

from datetime import datetime
from typing import Any

from .habit import Habit, HabitStatus
from .habit_dto import HabitDTO
from .habit_request import HabitCreateRequest

# ============================================================================
# EXTERNAL → TRANSFER (Request → DTO)
# ============================================================================


def habit_create_request_to_dto(request: HabitCreateRequest, user_uid: str) -> HabitDTO:
    """
    Convert HabitCreateRequest to HabitDTO.

    Args:
        request: Validated external request
        user_uid: User UID (from authentication context)

    Returns:
        DTO ready for service operations with learning fields preserved
    """
    return HabitDTO.create(
        user_uid=user_uid,
        name=request.name,
        description=request.description,
        polarity=request.polarity,
        category=request.category,
        difficulty=request.difficulty,
        recurrence_pattern=request.recurrence_pattern,
        target_days_per_week=request.target_days_per_week,
        preferred_time=request.preferred_time,
        duration_minutes=request.duration_minutes,
        linked_knowledge_uids=request.linked_knowledge_uids or [],
        linked_goal_uids=request.linked_goal_uids or [],
        linked_principle_uids=request.linked_principle_uids or [],
        prerequisite_habit_uids=request.prerequisite_habit_uids or [],
        # Note: Curriculum fields (source_learning_step_uid, source_learning_path_uid,
        # reinforces_step_uids, curriculum_practice_type) removed (graph-native) migration.
        # These are now stored as graph relationships, not DTO fields.
        cue=request.cue,
        routine=request.routine,
        reward=request.reward,
        priority=request.priority,
        tags=request.tags or [],
    )


# NOTE: habit_update_request_to_dto_updates() removed - use generic helper directly:
#   - from core.utils.converter_helpers import update_request_to_dict
#   - updates = update_request_to_dict(request)
#
# This eliminates domain-specific wrappers in favor of the generic pattern.
# The helper works for ANY domain's update request (Pydantic BaseModel).


# ============================================================================
# TRANSFER ↔ CORE (DTO ↔ Domain)
# ============================================================================
# NOTE: Wrapper functions removed - use model methods directly:
#   - Habit.from_dto(dto) instead of habit_dto_to_domain(dto)
#   - habit.to_dto() instead of habit_domain_to_dto(habit)


# ============================================================================
# EXTERNAL → CORE (Direct conversion for read operations)
# ============================================================================


def habit_create_request_to_domain(request: HabitCreateRequest, user_uid: str) -> Habit:
    """
    Direct conversion from create request to domain model.
    Useful for operations that don't need intermediate DTO manipulation.

    Args:
        request: Validated external request
        user_uid: User UID (from authentication context)

    Returns:
        Immutable domain model with learning integration
    """
    dto = habit_create_request_to_dto(request, user_uid)
    return Habit.from_dto(dto)


# ============================================================================
# DATABASE OPERATIONS (Dict ↔ DTO)
# ============================================================================


def habit_dict_to_dto(data: dict[str, Any]) -> HabitDTO:
    """
    Convert dictionary (from database) to HabitDTO.
    Preserves all learning integration fields.

    Args:
        data: Raw dictionary from database/Neo4j with learning data,

    Returns:
        DTO with parsed and validated data including learning enhancements
    """
    # Validate and normalize data before conversion
    validated_data = validate_habit_learning_data(data)
    return HabitDTO.from_dict(validated_data)


# NOTE: habit_dto_to_dict() removed - use dto.to_dict() directly


# ============================================================================
# LEARNING INTEGRATION OPERATIONS
# ============================================================================


def extract_learning_summary_from_habit(
    habit: Habit,
    knowledge_uids: list[str] | None = None,
    goal_uids: list[str] | None = None,
    principle_uids: list[str] | None = None,
    step_uids: list[str] | None = None,
) -> dict[str, Any]:
    """
    Extract learning integration summary from a habit.

    Args:
        habit: Domain model with learning data
        knowledge_uids: UIDs of knowledge this habit practices (from relationship service)
        goal_uids: UIDs of goals this habit supports (from relationship service)
        principle_uids: UIDs of principles this habit aligns with (from relationship service)
        step_uids: UIDs of learning steps this habit reinforces (from relationship service)

    Returns:
        Summary dictionary with learning metrics

    Note:
        Service layer should fetch relationship UIDs using HabitsRelationshipService:
        - knowledge_uids = await habits_relationship_service.get_habit_knowledge(habit_uid)
        - goal_uids = await habits_relationship_service.get_habit_goals(habit_uid)
        - principle_uids = await habits_relationship_service.get_habit_principles(habit_uid)
        - step_uids = await habits_relationship_service.get_habit_learning_steps(habit_uid)
    """
    # Use provided relationship data or fall back to empty lists
    knowledge_uids = knowledge_uids or []
    goal_uids = goal_uids or []
    principle_uids = principle_uids or []
    step_uids = step_uids or []

    return {
        "uid": habit.uid,
        "name": habit.name,
        "category": habit.category.value,
        "polarity": habit.polarity.value,
        "difficulty": habit.difficulty.value,
        # GRAPH-NATIVE: Relationship data provided by service layer
        "linked_knowledge_count": len(knowledge_uids),
        "knowledge_uids": knowledge_uids,
        "linked_goal_count": len(goal_uids),
        "goal_uids": goal_uids,
        "linked_principle_count": len(principle_uids),
        "principle_uids": principle_uids,
        # Curriculum spine (scalar fields still exist on model)
        "is_curriculum_habit": habit.source_learning_step_uid is not None
        or habit.source_learning_path_uid is not None,
        "source_step_uid": habit.source_learning_step_uid,
        "source_path_uid": habit.source_learning_path_uid,
        "reinforces_step_count": len(step_uids),
        "step_uids": step_uids,
        "practice_type": habit.curriculum_practice_type,
        # Atomic Habits
        "is_identity_habit": habit.is_identity_habit,
        "reinforces_identity": habit.reinforces_identity,
        "identity_votes_cast": habit.identity_votes_cast,
        # Progress
        "current_streak": habit.current_streak,
        "best_streak": habit.best_streak,
        "total_completions": habit.total_completions,
        "success_rate": habit.success_rate,
        # Integration level
        "learning_integration_level": _calculate_learning_integration_level(habit),
    }


def _calculate_learning_integration_level(habit: Habit) -> str:
    """
    Calculate the level of learning integration for a habit.

    Args:
        habit: Domain model,

    Returns:
        Integration level: 'standalone', 'basic', 'moderate', 'high', 'comprehensive'
    """
    integration_count = 0

    # NOTE: Relationship fields removed from Habit domain model (graph-native).
    # Cannot calculate full integration level without graph queries.
    #
    # ARCHITECTURAL LIMITATION: This converter is in the models layer and should
    # not call services. For accurate integration level, the service layer should:
    #   1. Call HabitsRelationshipService to get relationship counts
    #   2. Calculate integration level using those counts
    #   3. Pass the result to this converter or include in the response
    #
    # For now, only count scalar fields that still exist on model:
    # Count learning connections (would need graph query)
    # integration_count += len(habit.linked_knowledge_uids)  # REMOVED
    # integration_count += len(habit.linked_goal_uids)  # REMOVED
    # integration_count += len(habit.linked_principle_uids)  # REMOVED

    # Curriculum spine adds significant weight (scalar fields exist)
    if habit.source_learning_step_uid or habit.source_learning_path_uid:
        integration_count += 3

    # integration_count += len(habit.reinforces_step_uids)  # REMOVED

    # Identity habits are special
    if habit.is_identity_habit:
        integration_count += 2

    if integration_count == 0:
        return "standalone"
    elif integration_count <= 2:
        return "basic"
    elif integration_count <= 5:
        return "moderate"
    elif integration_count <= 9:
        return "high"
    else:
        return "comprehensive"


def extract_identity_summary(habit: Habit) -> dict[str, Any]:
    """
    Extract Atomic Habits identity information.

    Args:
        habit: Domain model,

    Returns:
        Identity summary dictionary
    """
    return {
        "uid": habit.uid,
        "name": habit.name,
        "is_identity_habit": habit.is_identity_habit,
        "reinforces_identity": habit.reinforces_identity,
        "identity_votes_cast": habit.identity_votes_cast,
        "identity_strength": _calculate_identity_strength(habit),
        "identity_progress_percentage": _calculate_identity_progress(habit),
    }


def _calculate_identity_strength(habit: Habit) -> str:
    """
    Calculate identity strength based on votes cast.

    Args:
        habit: Domain model,

    Returns:
        Strength level: 'emerging', 'developing', 'established', 'strong', 'internalized'
    """
    if not habit.is_identity_habit or habit.identity_votes_cast == 0:
        return "emerging"
    elif habit.identity_votes_cast < 10:
        return "developing"
    elif habit.identity_votes_cast < 30:
        return "established"
    elif habit.identity_votes_cast < 66:  # James Clear's "66 days to form a habit"
        return "strong"
    else:
        return "internalized"


def _calculate_identity_progress(habit: Habit) -> float:
    """
    Calculate identity progress as percentage towards internalization (66 completions).

    Args:
        habit: Domain model,

    Returns:
        Progress percentage (0.0 - 100.0)
    """
    if not habit.is_identity_habit:
        return 0.0

    target = 66  # James Clear's research on habit formation
    return min(100.0, (habit.identity_votes_cast / target) * 100.0)


def extract_curriculum_metadata(
    habit: Habit,
    step_uids: list[str] | None = None,
) -> dict[str, Any]:
    """
    Extract curriculum spine metadata.

    Args:
        habit: Domain model
        step_uids: UIDs of learning steps this habit reinforces (from relationship service)

    Returns:
        Curriculum metadata dictionary

    Note:
        Service layer should fetch step UIDs using HabitsRelationshipService:
        - step_uids = await habits_relationship_service.get_habit_learning_steps(habit_uid)
    """
    # Use provided relationship data or fall back to empty list
    step_uids = step_uids or []

    return {
        "uid": habit.uid,
        "name": habit.name,
        "is_curriculum_habit": habit.source_learning_step_uid is not None
        or habit.source_learning_path_uid is not None,
        "source_step_uid": habit.source_learning_step_uid,
        "source_path_uid": habit.source_learning_path_uid,
        # GRAPH-NATIVE: Relationship data provided by service layer
        "reinforces_step_uids": step_uids,
        "reinforces_step_count": len(step_uids),
        "practice_type": habit.curriculum_practice_type,
        "supports_multiple_steps": len(step_uids) > 1,
    }


def enrich_habit_dto_with_completion_stats(dto: HabitDTO, stats_data: dict[str, Any]) -> HabitDTO:
    """
    Add completion statistics to a habit DTO.

    Args:
        dto: Habit DTO to enhance,
        stats_data: Completion statistics

    Returns:
        DTO with enriched statistics
    """
    # Update progress tracking
    if "current_streak" in stats_data:
        dto.current_streak = stats_data["current_streak"]
    if "best_streak" in stats_data:
        dto.best_streak = stats_data["best_streak"]
    if "total_completions" in stats_data:
        dto.total_completions = stats_data["total_completions"]
    if "total_attempts" in stats_data:
        dto.total_attempts = stats_data["total_attempts"]
    if "success_rate" in stats_data:
        dto.success_rate = stats_data["success_rate"]
    if "last_completed" in stats_data:
        dto.last_completed = stats_data["last_completed"]

    # Update identity votes if identity habit
    if dto.is_identity_habit and "total_completions" in stats_data:
        dto.identity_votes_cast = stats_data["total_completions"]

    dto.updated_at = datetime.now()

    return dto


# ============================================================================
# BULK OPERATIONS
# ============================================================================


def habit_create_requests_to_dtos(
    requests: list[HabitCreateRequest], user_uid: str
) -> list[HabitDTO]:
    """
    Convert multiple create requests to DTOs.

    Args:
        requests: List of validated external requests
        user_uid: User UID (from authentication context)

    Returns:
        List of DTOs ready for bulk operations
    """
    return [habit_create_request_to_dto(request, user_uid) for request in requests]


def habit_dtos_to_domains(dtos: list[HabitDTO]) -> list[Habit]:
    """
    Convert multiple DTOs to domain models.

    Args:
        dtos: List of transfer objects with learning data,

    Returns:
        List of immutable domain models
    """
    return [Habit.from_dto(dto) for dto in dtos]


def habit_domains_to_dtos(habits: list[Habit]) -> list[HabitDTO]:
    """
    Convert multiple domain models to DTOs.

    Args:
        habits: List of domain models,

    Returns:
        List of mutable DTOs
    """
    return [habit.to_dto() for habit in habits]


def habit_dicts_to_dtos(dicts: list[dict[str, Any]]) -> list[HabitDTO]:
    """
    Convert multiple dictionaries to DTOs.

    Args:
        dicts: List of raw dictionaries from database,

    Returns:
        List of DTOs with parsed data
    """
    return [habit_dict_to_dto(d) for d in dicts]


# ============================================================================
# PREREQUISITE CHAIN OPERATIONS
# ============================================================================


def extract_prerequisite_chain_metadata(
    habit: Habit,
    prerequisite_uids: list[str] | None = None,
) -> dict[str, Any]:
    """
    Extract prerequisite chain metadata for habit progression.

    Args:
        habit: Domain model
        prerequisite_uids: UIDs of prerequisite habits (from relationship service)

    Returns:
        Prerequisite metadata dictionary

    Note:
        Service layer should fetch prerequisite UIDs using HabitsRelationshipService:
        - prerequisite_uids = await habits_relationship_service.get_habit_prerequisites(habit_uid)
    """
    # Use provided relationship data or fall back to empty list
    prerequisite_uids = prerequisite_uids or []

    return {
        "uid": habit.uid,
        "name": habit.name,
        # GRAPH-NATIVE: Relationship data provided by service layer
        "has_prerequisites": len(prerequisite_uids) > 0,
        "prerequisite_uids": prerequisite_uids,
        "prerequisite_count": len(prerequisite_uids),
        "is_foundational": len(prerequisite_uids) == 0,  # Foundational if no prerequisites
        "difficulty": habit.difficulty.value,
        "is_active": habit.status == HabitStatus.ACTIVE,
    }


# ============================================================================
# VALIDATION HELPERS
# ============================================================================


def validate_habit_learning_data(data: dict[str, Any]) -> dict[str, Any]:
    """
    Validate and normalize habit learning data.

    Uses generic validation helpers from validation_helpers.py.
    Note: This validator is more permissive than others - uses defaults instead of raising errors.

    Args:
        data: Raw dictionary with potentially inconsistent learning data,

    Returns:
        Validated dictionary with normalized learning data
    """
    from core.utils.validation_helpers import ensure_list_fields

    validated = data.copy()

    # Ensure learning integration fields are lists using generic helper
    ensure_list_fields(
        validated,
        [
            "linked_knowledge_uids",
            "linked_goal_uids",
            "linked_principle_uids",
            "prerequisite_habit_uids",
            "reinforces_step_uids",
            "tags",
        ],
    )

    # Ensure numeric fields are correct type (with defaults)
    numeric_fields = {
        "current_streak": 0,
        "best_streak": 0,
        "total_completions": 0,
        "total_attempts": 0,
        "success_rate": 0.0,
        "identity_votes_cast": 0,
        "target_days_per_week": 7,
        "duration_minutes": 15,
    }

    for field, default in numeric_fields.items():
        if field in validated:
            try:
                if isinstance(default, float):
                    validated[field] = float(validated[field])
                else:
                    validated[field] = int(validated[field])
            except (ValueError, TypeError):
                validated[field] = default

    # Ensure boolean fields
    boolean_fields = ["is_identity_habit"]
    for field in boolean_fields:
        if field in validated:
            validated[field] = bool(validated[field])

    # Ensure datetime fields (permissive - defaults to None on error)
    datetime_fields = ["created_at", "updated_at", "started_at", "completed_at", "last_completed"]
    for field in datetime_fields:
        if field in validated and isinstance(validated[field], str):
            try:
                validated[field] = datetime.fromisoformat(validated[field])
            except ValueError:
                validated[field] = None

    return validated
