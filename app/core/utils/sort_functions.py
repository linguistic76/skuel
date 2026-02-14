"""
Sort Functions for Collections
==============================

Named sort functions to replace lambda expressions in sorting operations.
Following clean code principle: no lambdas, only named functions.
"""

from typing import Any

from core.services.protocols.base_protocols import (
    HasPriority,
    HasRelevanceScore,
    HasScore,
    HasToNumeric,
)


def sort_by_start_time(event: Any) -> Any:
    """Sort events by their start_time attribute."""
    return event.start_time


def sort_by_confidence_and_strength(relationship: Any) -> float:
    """Sort relationships by combined confidence and strength scores."""
    return relationship.metadata.confidence * relationship.metadata.strength


def sort_by_relevance_score(item: tuple[Any, float]) -> float:
    """Sort search results by relevance score (second element of tuple)."""
    return item[1]


def sort_by_index_count(item: tuple[str, list[Any]]) -> int:
    """Sort labeled indexes by count of items."""
    return len(item[1])


def get_intent_score(item: tuple[str, float]) -> float:
    """
    Get intent score from (intent_name, score) tuple.

    Used for finding the maximum scoring intent in query analysis.
    Example: max(intent_scores.items(), key=get_intent_score)
    """
    return item[1]


def get_result_score(scored_result: tuple[Any, float]) -> float:
    """
    Get score from (result, score) tuple.

    Used for sorting ranked search results by relevance score.
    Example: scored_results.sort(key=get_result_score, reverse=True)
    """
    return scored_result[1]


def get_avg_time_ms(metrics: Any) -> float:
    """
    Get average time in milliseconds from OperationMetrics object.

    Used for sorting operations by performance.
    Example: sorted(operations, key=get_avg_time_ms, reverse=True)
    """
    return metrics.avg_time_ms


def get_linked_knowledge_count(goal: Any) -> int:
    """
    Get count of linked knowledge units from a goal.

    Used for sorting goals by their knowledge linkage density.
    Example: learning_supporting_goals.sort(key=get_linked_knowledge_count, reverse=True)
    """
    linked_uids = getattr(goal, "linked_knowledge_uids", []) or []
    return len(linked_uids)


def get_domain_choice_count(item: tuple[str, dict[str, Any]]) -> int:
    """
    Get choice count from domain pattern dictionary.

    Used for finding the domain with the highest choice count.
    Example: max(domain_patterns.items(), key=get_domain_choice_count)

    Args:
        item: Tuple of (domain_name, pattern_dict) where pattern_dict has 'choice_count' key,

    Returns:
        The choice count from the pattern dictionary
    """
    return item[1]["choice_count"]


def get_completed_at(completion: Any) -> Any:
    """
    Get completed_at timestamp from HabitCompletion object.

    Used for sorting habit completions by completion date.
    Example: completions.sort(key=get_completed_at, reverse=True)
    """
    return completion.completed_at


def get_timestamp(activity: dict[str, Any]) -> Any:
    """
    Get timestamp from activity dictionary.

    Used for sorting activity records by timestamp.
    Example: activities.sort(key=get_timestamp, reverse=True)
    """
    return activity["timestamp"]


def get_recommendation_score(recommendation: Any) -> float:
    """
    Get combined recommendation score.

    Calculates weighted score from relevance, readiness, and difficulty match.
    Used for sorting recommendations by overall quality.
    Example: recommendations.sort(key=get_recommendation_score, reverse=True)
    """
    # If recommendation has a simple 'score' attribute (but not relevance_score), use that
    if isinstance(recommendation, HasScore) and not isinstance(recommendation, HasRelevanceScore):
        return recommendation.score

    # Otherwise calculate from components (ContentRecommendation pattern)
    relevance = getattr(recommendation, "relevance_score", 0.5)
    readiness = getattr(recommendation, "readiness_score", 0.5)
    difficulty = getattr(recommendation, "difficulty_match", 0.5)
    return relevance * 0.4 + readiness * 0.4 + difficulty * 0.2


def get_relevance_score(recommendation: Any) -> float:
    """
    Get relevance_score from recommendation object.

    Used for sorting recommendations by relevance.
    Example: recommendations.sort(key=get_relevance_score, reverse=True)
    """
    return recommendation.relevance_score


def get_intervention_priority(intervention: Any) -> float:
    """
    Get priority from intervention object.

    Used for sorting interventions by priority.
    Example: interventions.sort(key=get_intervention_priority, reverse=True)
    """
    return intervention.priority


def get_second_item(tuple_item: tuple[Any, Any]) -> Any:
    """
    Get second element from a tuple.

    Used for sorting tuples by their second element (e.g., similarity scores).
    Example: similarities.sort(key=get_second_item, reverse=True)

    Note: For simple tuple access, prefer operator.itemgetter(1)
    This function is for consistency with existing code patterns.
    """
    return tuple_item[1]


def get_readiness_score(content_tuple: tuple[Any, float]) -> float:
    """
    Get readiness score from (content, readiness) tuple.

    Used for sorting learning content by user readiness.
    Example: content_with_readiness.sort(key=get_readiness_score, reverse=True)
    """
    return content_tuple[1]


def get_confidence_score(item: Any) -> float:
    """
    Get confidence score from object with confidence attribute.

    Used for sorting items by confidence level.
    Example: results.sort(key=get_confidence_score, reverse=True)
    """
    return item.confidence


def get_combined_score(item: Any) -> float:
    """
    Get combined score from object with combined_score property.

    Used for sorting SearchResultItem by combined relevance + priority score.
    Example: results.sort(key=get_combined_score, reverse=True)
    """
    return item.combined_score


def get_synergy_score(synergy: Any) -> float:
    """
    Get synergy_score from CrossDomainSynergy object.

    Used for sorting synergies by their score (0.0-1.0).
    Example: synergies.sort(key=get_synergy_score, reverse=True)
    """
    return synergy.synergy_score


def get_priority_value(item: Any) -> int:
    """
    Get numeric priority value from item.

    Used for sorting by priority (higher number = higher priority).
    Example: tasks.sort(key=get_priority_value, reverse=True)
    """
    if isinstance(item, HasPriority):
        # Handle enum priorities with to_numeric method
        if isinstance(item.priority, HasToNumeric):
            return item.priority.to_numeric()
        # Ensure we return an int (priority could be int, str, or enum value)
        if isinstance(item.priority, int):
            return item.priority
        return 0
    return 0


def get_due_date(task: Any) -> Any:
    """
    Get due_date from task object.

    Used for sorting tasks by due date.
    Example: tasks.sort(key=get_due_date)

    Note: For simple attribute access, prefer operator.attrgetter('due_date')
    This function handles None values gracefully.
    """
    from datetime import date, datetime

    due = getattr(task, "due_date", None)
    # Put None values at the end
    if due is None:
        return datetime.max.date() if isinstance(datetime.max.date(), date) else datetime.max
    return due


def get_task_urgency(task: Any) -> tuple[Any, Any]:
    """
    Get task urgency key (priority, due_date) for sorting critical tasks.

    Returns tuple of (priority.value, due_date) where None due_dates are placed last.
    Used for sorting tasks by urgency (priority first, then due date).
    Example: critical_tasks.sort(key=get_task_urgency)
    """
    from datetime import date as date_type

    priority_value = getattr(task.priority, "value", 0) if isinstance(task, HasPriority) else 0
    due_date = getattr(task, "due_date", None) or date_type.max
    return (priority_value, due_date)


def get_gap_severity_order(gap: Any) -> int:
    """
    Get severity order value for KnowledgeGap sorting.

    Maps severity levels to numeric ordering: high=0, medium=1, low=2, unknown=3.
    Lower numbers = higher priority (sorts high-severity gaps first).
    Used for sorting knowledge gaps by severity.
    Example: gaps.sort(key=get_gap_severity_order)
    """
    severity_order = {"high": 0, "medium": 1, "low": 2}
    severity = getattr(gap, "severity", "unknown")
    return severity_order.get(severity, 3)


def get_final_score(result: Any) -> float:
    """
    Get final_score from EnhancedResult object.

    Used for sorting knowledge retrieval results by final combined score.
    Example: results.sort(key=get_final_score, reverse=True)
    """
    return result.final_score


def get_query_plan_priority(plan: Any, strategy_priority: dict[Any, int]) -> tuple[int, float]:
    """
    Get query plan priority for selecting the best execution plan.

    Returns tuple of (strategy_priority, estimated_cost) for sorting query plans.
    Lower values indicate better plans (faster execution).
    Used for selecting optimal query plan from multiple alternatives.

    Example:
        from functools import partial
        sort_key = partial(get_query_plan_priority, strategy_priority=strategy_map)
        best_plan = min(plans, key=sort_key)

    Args:
        plan: QueryPlan object with strategy and estimated_cost attributes,
        strategy_priority: Dictionary mapping IndexStrategy to priority integers

    Returns:
        Tuple of (strategy_priority_value, estimated_cost)
    """
    strategy_value = strategy_priority.get(plan.strategy, 10)
    cost = plan.estimated_cost
    return (strategy_value, cost)


def get_journal_date(journal: Any) -> Any:
    """
    Get occurred_at date from journal object, with fallback to datetime.min.

    Used for sorting journal entries by date.
    Example: journals.sort(key=get_journal_date, reverse=True)

    Args:
        journal: Journal object with occurred_at attribute,

    Returns:
        The occurred_at date, or datetime.min if None
    """
    from datetime import datetime

    return journal.occurred_at or datetime.min


def get_window_start_time(window_tuple: tuple[str, Any]) -> Any:
    """
    Get start time from (uid, TimeWindow) tuple.

    Used for sorting calendar window tuples by their start time.
    Example: all_windows.sort(key=get_window_start_time)

    Args:
        window_tuple: Tuple of (uid, TimeWindow) where TimeWindow has .start attribute,

    Returns:
        The start datetime from the TimeWindow
    """
    return window_tuple[1].start


def get_principle_priority(principle: Any) -> int:
    """
    Get numeric priority value from principle for sorting.

    Converts Priority enum to numeric value (1-4) using the to_numeric() method.
    Higher numbers indicate higher priority (LOW=1, MEDIUM=2, HIGH=3, CRITICAL=4).
    Used for sorting principles by priority (descending order shows highest priority first).
    Example: principles.sort(key=get_principle_priority, reverse=True)

    Args:
        principle: Principle object with priority attribute,

    Returns:
        Numeric priority value (1-4), defaults to 2 (MEDIUM) if unavailable
    """
    if isinstance(principle, HasPriority) and isinstance(principle.priority, HasToNumeric):
        return principle.priority.to_numeric()
    return 2  # Default to MEDIUM priority


def get_discovery_score(discovery: Any) -> float:
    """
    Get combined discovery score for personalized knowledge ranking.

    Calculates weighted score from personal relevance, cognitive readiness, and final score.
    Used for sorting personalized knowledge discoveries by overall quality.
    Example: discoveries.sort(key=get_discovery_score, reverse=True)

    Args:
        discovery: PersonalizedDiscoveryResult object with score attributes,

    Returns:
        Combined score (0.0-1.0) weighted by relevance (40%), readiness (30%), and quality (30%)
    """
    personal_relevance = getattr(discovery, "personal_relevance_score", 0.5)
    cognitive_readiness = getattr(discovery, "cognitive_readiness_match", 0.5)
    final_score = getattr(discovery, "final_score", 0.5)
    return personal_relevance * 0.4 + cognitive_readiness * 0.3 + final_score * 0.3


def get_created_at(item: dict[str, Any]) -> Any:
    """
    Get created_at timestamp from dictionary.

    Used for sorting search results or entities by creation date.
    Example: results.sort(key=get_created_at, reverse=True)

    Args:
        item: Dictionary with 'created_at' key,

    Returns:
        The created_at timestamp, or empty string if not present
    """
    return item.get("created_at", "")


def get_sequence(item: dict[str, Any]) -> int:
    """
    Get sequence number from dictionary, defaulting to 0 if None.

    Used for sorting learning path steps, ordered items, and sequential data.
    Example: sorted(steps_data, key=get_sequence)

    Args:
        item: Dictionary with 'sequence' key,

    Returns:
        The sequence number, or 0 if not present or None
    """
    sequence = item.get("sequence")
    return sequence if sequence is not None else 0


def get_activity_score(item: dict[str, Any]) -> float:
    """
    Get activity_score from dictionary.

    Used for sorting activity rankings by score.
    Example: rankings.sort(key=get_activity_score, reverse=True)

    Args:
        item: Dictionary with 'activity_score' key

    Returns:
        The activity score value
    """
    return item["activity_score"]


def get_days_until_review(item: dict[str, Any]) -> int:
    """
    Get days_until_review from dictionary.

    Used for sorting decay warnings by review urgency.
    Example: sorted(decay_warnings, key=get_days_until_review)

    Args:
        item: Dictionary with 'days_until_review' key

    Returns:
        Number of days until review needed
    """
    return item["days_until_review"]


def get_contribution_estimate(item: tuple[str, dict[str, Any]]) -> float:
    """
    Get contribution_estimate from tuple of (key, dict).

    Used for sorting domain contributions by estimate value.
    Example: sorted(items, key=get_contribution_estimate, reverse=True)

    Args:
        item: Tuple of (key, dict) where dict has 'contribution_estimate' key

    Returns:
        The contribution estimate value
    """
    return item[1]["contribution_estimate"]


def get_theme_count(item: tuple[str, int]) -> int:
    """
    Get count from (theme, count) tuple.

    Used for sorting theme frequency counts.
    Example: sorted(theme_counts.items(), key=get_theme_count, reverse=True)

    Args:
        item: Tuple of (theme_name, count)

    Returns:
        The count value
    """
    return item[1]


def get_frequency(item: dict[str, Any]) -> int:
    """
    Get frequency value from dictionary.

    Used for sorting patterns or items by frequency count.
    Example: sorted(patterns.values(), key=get_frequency, reverse=True)

    Args:
        item: Dictionary with 'frequency' key

    Returns:
        The frequency count
    """
    return item["frequency"]


def make_attribute_sort_key(attribute_name: str):
    """
    Create a sort key function for dynamic attribute access.

    Returns a function that safely gets an attribute value from an object,
    with None values or missing attributes converted to empty string for sorting.

    Used for sorting by dynamic attribute names (e.g., from query parameters).
    Example:
        sort_key = make_attribute_sort_key('title')
        items.sort(key=sort_key)

    Args:
        attribute_name: Name of the attribute to sort by

    Returns:
        A function that can be used as a sort key
    """

    def sort_key(item: Any) -> Any:
        """Get attribute value for sorting, defaulting to empty string."""
        return getattr(item, attribute_name, None) or ""

    return sort_key


def get_confidence_score_attr(item: Any) -> float:
    """
    Get confidence_score attribute from object.

    Used for sorting items by confidence_score attribute.
    Example: recommendations.sort(key=get_confidence_score_attr, reverse=True)

    Note: Different from get_confidence_score which accesses .confidence
    """
    return item.confidence_score


def get_schedule_recommendation_score(recommendation: Any) -> float:
    """
    Get overall_score from ScheduleAwareRecommendation object.

    Used for sorting schedule-aware recommendations by their overall score.
    Example: recommendations.sort(key=get_schedule_recommendation_score, reverse=True)

    Args:
        recommendation: ScheduleAwareRecommendation object with overall_score attribute

    Returns:
        The overall score (0.0-1.0) for schedule-based ranking
    """
    return recommendation.overall_score


def get_report_date(report: Any) -> Any:
    """
    Get created_at date from Report object, with fallback to datetime.min.

    Used for sorting reports by creation date.
    Example: reports.sort(key=get_report_date, reverse=True)

    Args:
        report: Report object with created_at attribute

    Returns:
        The created_at datetime, or datetime.min if None
    """
    from datetime import datetime

    return report.created_at or datetime.min


def get_principle_strength_order(principle: Any) -> int:
    """
    Get strength order value for Principle sorting.

    Maps PrincipleStrength enum to numeric ordering for sorting.
    Lower numbers = higher strength (sorts strongest principles first).

    Order: CORE=0, STRONG=1, MODERATE=2, DEVELOPING=3, EXPLORING=4, unknown=5

    Used for sorting principles by strength level.
    Example: principles.sort(key=get_principle_strength_order)

    Args:
        principle: Principle object with strength attribute

    Returns:
        Numeric order value (0-5), lower = stronger
    """
    from core.models.enums.ku_enums import PrincipleStrength

    strength_order = {
        PrincipleStrength.CORE: 0,
        PrincipleStrength.STRONG: 1,
        PrincipleStrength.MODERATE: 2,
        PrincipleStrength.DEVELOPING: 3,
        PrincipleStrength.EXPLORING: 4,
    }
    return strength_order.get(principle.strength, 5)


def get_priority_score(item: Any) -> float:
    """
    Get priority_score attribute from item.

    Used for sorting items by priority score (higher = more important).
    Example: items.sort(key=get_priority_score, reverse=True)

    Args:
        item: Object with priority_score attribute

    Returns:
        The priority_score value
    """
    return item.priority_score


def get_ready_score_with_unlocks(item: dict[str, Any]) -> tuple[float, int]:
    """
    Get ready_score and unlocks_count for sorting ready-to-learn knowledge.

    Returns tuple of (ready_score, unlocks_count) for sorting knowledge units
    by readiness and impact (higher = better).

    Used for sorting knowledge units by learning readiness and unblocking potential.
    Example: ready_units.sort(key=get_ready_score_with_unlocks, reverse=True)

    Args:
        item: Dictionary with 'ready_score' and 'unlocks_count' keys

    Returns:
        Tuple of (ready_score, unlocks_count) for multi-key sorting
    """
    return (item.get("ready_score", 0.0), item.get("unlocks_count", 0))


def get_progression_score_with_enablers(item: dict[str, Any]) -> tuple[float, int]:
    """
    Get progression_score and enabled_by count for sorting learning progression.

    Returns tuple of (progression_score, len(enabled_by)) for sorting learning steps
    by progression value and enabling relationships.

    Used for sorting next logical learning steps by progression and connectivity.
    Example: next_steps.sort(key=get_progression_score_with_enablers, reverse=True)

    Args:
        item: Dictionary with 'progression_score' and 'enabled_by' keys

    Returns:
        Tuple of (progression_score, enabler_count) for multi-key sorting
    """
    enabled_by = item.get("enabled_by", [])
    return (item.get("progression_score", 0.0), len(enabled_by))


def get_alignment_score_with_goal_count(item: dict[str, Any]) -> tuple[float, int]:
    """
    Get alignment_score and goal_count for sorting goal-aligned knowledge.

    Returns tuple of (alignment_score, goal_count) for sorting knowledge units
    by goal alignment and the number of goals they support.

    Used for sorting knowledge by alignment to active goals and breadth of impact.
    Example: results.sort(key=get_alignment_score_with_goal_count, reverse=True)

    Args:
        item: Dictionary with 'alignment_score' and 'goal_count' keys

    Returns:
        Tuple of (alignment_score, goal_count) for multi-key sorting
    """
    return (item.get("alignment_score", 0.0), item.get("goal_count", 0))


def get_priority_score_with_blocking_count(item: dict[str, Any]) -> tuple[float, int]:
    """
    Get priority_score and blocking_goals_count for sorting knowledge gaps.

    Returns tuple of (priority_score, blocking_goals_count) for sorting gaps
    by priority and the number of goals they block.

    Used for sorting knowledge gaps by urgency and impact.
    Example: gaps.sort(key=get_priority_score_with_blocking_count, reverse=True)

    Args:
        item: Dictionary with 'priority_score' and 'blocking_goals_count' keys

    Returns:
        Tuple of (priority_score, blocking_count) for multi-key sorting
    """
    return (item.get("priority_score", 0.0), item.get("blocking_goals_count", 0))


def get_updated_timestamp(item: dict[str, Any]) -> str:
    """
    Get updated timestamp from dictionary for sorting MOC views.

    Returns the 'updated' timestamp or empty string for sorting recently viewed MOCs.

    Used for sorting MOC view history by recency.
    Example: sorted(moc_data, key=get_updated_timestamp, reverse=True)

    Args:
        item: Dictionary with optional 'updated' key

    Returns:
        The updated timestamp string, or empty string if not present
    """
    return item.get("updated") or ""


def make_dict_score_getter(scores_dict: dict[str, float], default: float = 0.0):
    """
    Create a sort key function that looks up scores from a dictionary.

    Used for sorting items by their scores stored in a separate dictionary.
    Returns a function that safely gets a score for a given key.

    Example:
        relevance_scores = {"ku1": 0.9, "ku2": 0.7}
        sort_key = make_dict_score_getter(relevance_scores)
        sorted_uids = sorted(knowledge_uids, key=sort_key, reverse=True)

    Args:
        scores_dict: Dictionary mapping keys to scores
        default: Default score for missing keys (default 0.0)

    Returns:
        A function that can be used as a sort key
    """

    def get_score(key: str) -> float:
        """Get score for key from dictionary."""
        return scores_dict.get(key, default)

    return get_score


def get_negative_second_item(item: tuple[Any, Any]) -> Any:
    """
    Get negative of second element from a tuple (for descending sort).

    Used for sorting tuples by their second element in descending order
    without using reverse=True.
    Example: sorted(category_totals.items(), key=get_negative_second_item)

    Args:
        item: Tuple where second element is numeric

    Returns:
        Negative of the second element
    """
    return -item[1]


def get_task_due_date_sort_key(task: Any) -> tuple[bool, Any]:
    """
    Get sort key for task due date with None values at end.

    Returns tuple of (is_none, date) which sorts None values last
    because True > False in Python sorting.
    Example: tasks.sort(key=get_task_due_date_sort_key)

    Args:
        task: Task object with due_date attribute

    Returns:
        Tuple of (due_date is None, due_date or max date)
    """
    from datetime import date as date_type

    due = getattr(task, "due_date", None)
    return (due is None, due or date_type.max)


def get_created_at_attr(item: Any) -> Any:
    """
    Get created_at attribute from object.

    Used for sorting objects by creation timestamp.
    Example: items.sort(key=get_created_at_attr, reverse=True)

    Args:
        item: Object with created_at attribute

    Returns:
        The created_at timestamp
    """
    return item.created_at


def get_project_and_title(task: Any) -> tuple[str, str]:
    """
    Get (project, title) tuple for task sorting.

    Projects with None value are sorted last using "zzz" as placeholder.
    Example: tasks.sort(key=get_project_and_title)

    Args:
        task: Task object with project and title attributes

    Returns:
        Tuple of (project or "zzz", title)
    """
    return (task.project or "zzz", task.title)


def get_dict_score(item: dict[str, Any]) -> float:
    """
    Get _score from dictionary, defaulting to 0.

    Used for sorting search results by score.
    Example: results.sort(key=get_dict_score, reverse=True)

    Args:
        item: Dictionary with optional '_score' key

    Returns:
        The _score value or 0 if not present
    """
    return item.get("_score", 0)


def make_priority_order_getter(priority_order: dict[Any, int], default: int = 5):
    """
    Create a sort key function for priority ordering.

    Returns a function that looks up priority values from a mapping dict.
    Lower values = higher priority (sorted first).

    Example:
        priority_order = {Priority.CRITICAL: 0, Priority.HIGH: 1, Priority.MEDIUM: 2, Priority.LOW: 3}
        sort_key = make_priority_order_getter(priority_order)
        tasks.sort(key=sort_key)

    Args:
        priority_order: Dictionary mapping priority enum values to sort order
        default: Default order for unknown priorities (default 5)

    Returns:
        A function that can be used as a sort key
    """

    def get_order(task: Any) -> int:
        """Get priority order for task."""
        return priority_order.get(task.priority, default)

    return get_order


# =============================================================================
# UI SORTING FUNCTIONS (Added January 2026)
# =============================================================================


def get_decision_deadline(choice: Any) -> Any:
    """
    Get decision_deadline from choice, with fallback to datetime.max.

    Used for sorting choices by deadline (soonest first).
    Example: choices.sort(key=get_decision_deadline)

    Args:
        choice: Choice object with decision_deadline attribute

    Returns:
        The decision_deadline or datetime.max if None
    """
    from datetime import datetime

    return getattr(choice, "decision_deadline", None) or datetime.max


def get_title_lower(item: Any) -> str:
    """
    Get title attribute lowercased for case-insensitive sorting.

    Used for alphabetical sorting by title.
    Example: items.sort(key=get_title_lower)

    Args:
        item: Object with title attribute

    Returns:
        Lowercased title string, or empty string if not present
    """
    return getattr(item, "title", "").lower()


def get_name_lower(item: Any) -> str:
    """
    Get name attribute lowercased for case-insensitive sorting.

    Used for alphabetical sorting by name.
    Example: habits.sort(key=get_name_lower)

    Args:
        item: Object with name attribute

    Returns:
        Lowercased name string, or empty string if not present
    """
    return getattr(item, "name", "").lower()


def get_title_or_name_lower(item: Any) -> str:
    """
    Get title or name attribute lowercased (title preferred).

    Used for sorting items that may have either title or name attribute.
    Example: principles.sort(key=get_title_or_name_lower)

    Args:
        item: Object with title and/or name attribute

    Returns:
        Lowercased title or name string
    """
    return getattr(item, "title", getattr(item, "name", "")).lower()


def get_current_value(item: Any) -> float:
    """
    Get current_value from item for progress sorting.

    Used for sorting goals by progress/current value.
    Example: goals.sort(key=get_current_value, reverse=True)

    Args:
        item: Object with current_value attribute

    Returns:
        The current_value or 0 if not present
    """
    return getattr(item, "current_value", 0)


def get_current_streak(item: Any) -> int:
    """
    Get current_streak from habit for streak sorting.

    Used for sorting habits by streak length.
    Example: habits.sort(key=get_current_streak, reverse=True)

    Args:
        item: Object with current_streak attribute

    Returns:
        The current_streak or 0 if not present
    """
    return getattr(item, "current_streak", 0)


def get_recurrence_pattern(item: Any) -> str:
    """
    Get recurrence_pattern from item for frequency sorting.

    Used for sorting habits by frequency pattern.
    Example: habits.sort(key=get_recurrence_pattern)

    Args:
        item: Object with recurrence_pattern attribute

    Returns:
        The recurrence_pattern string or empty string
    """
    return getattr(item, "recurrence_pattern", "") or ""


def make_priority_string_getter(
    priority_order: dict[str, int],
    priority_extractor: Any,
    default: int = 2,
):
    """
    Create a sort key function for string-based priority ordering.

    Returns a function that extracts a priority string and looks it up in the mapping.
    Used when priority values are strings (e.g., "critical", "high", "medium", "low").

    Example:
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        sort_key = make_priority_string_getter(priority_order, get_priority_str)
        goals.sort(key=sort_key)

    Args:
        priority_order: Dictionary mapping priority strings to sort order
        priority_extractor: Function to extract priority string from item
        default: Default order for unknown priorities (default 2 = medium)

    Returns:
        A function that can be used as a sort key
    """

    def get_order(item: Any) -> int:
        """Get priority order for item."""
        priority_str = priority_extractor(item)
        return priority_order.get(priority_str, default)

    return get_order


# =============================================================================
# CONTEXTUAL OBJECT SORTING (Planning Mixin - January 2026)
# =============================================================================


def get_streak_and_priority(item: Any) -> tuple[int, float]:
    """
    Get (current_streak, priority_score) tuple for habit sorting.

    Used for sorting contextual habits by streak (longer = higher priority to maintain)
    and then by priority score.
    Example: contextual_habits.sort(key=get_streak_and_priority, reverse=True)

    Args:
        item: ContextualHabit object with current_streak and priority_score

    Returns:
        Tuple of (current_streak, priority_score)
    """
    return (item.current_streak, item.priority_score)


def get_days_until_and_priority(item: Any) -> tuple[int, float]:
    """
    Get (days_until, -priority_score) tuple for event sorting.

    Used for sorting contextual events by days until (today's first)
    and then by priority score (higher priority first via negation).
    Example: contextual_events.sort(key=get_days_until_and_priority)

    Args:
        item: ContextualEvent object with days_until and priority_score

    Returns:
        Tuple of (days_until, -priority_score)
    """
    return (item.days_until, -item.priority_score)


def get_overdue_and_priority(item: Any) -> tuple[bool, float]:
    """
    Get (is_overdue, priority_score) tuple for task sorting.

    Used for sorting contextual tasks by overdue status and priority.
    Example: contextual_tasks.sort(key=get_overdue_and_priority, reverse=True)

    Args:
        item: ContextualTask object with is_overdue and priority_score

    Returns:
        Tuple of (is_overdue, priority_score)
    """
    return (item.is_overdue, item.priority_score)


def get_risk_progress_priority(item: Any) -> tuple[bool, float, float]:
    """
    Get (not is_at_risk, current_progress, priority_score) tuple for goal sorting.

    Used for sorting contextual goals by risk status (non-at-risk first),
    progress, and priority.
    Example: contextual_goals.sort(key=get_risk_progress_priority, reverse=True)

    Args:
        item: ContextualGoal object with is_at_risk, current_progress, priority_score

    Returns:
        Tuple of (not is_at_risk, current_progress, priority_score)
    """
    return (not item.is_at_risk, item.current_progress, item.priority_score)


def get_core_and_alignment(item: Any) -> tuple[bool, float]:
    """
    Get (is_core, alignment_score) tuple for principle sorting.

    Used for sorting contextual principles by core status and alignment.
    Example: contextual_principles.sort(key=get_core_and_alignment, reverse=True)

    Args:
        item: ContextualPrinciple object with is_core and alignment_score

    Returns:
        Tuple of (is_core, alignment_score)
    """
    return (item.is_core, item.alignment_score)


def get_alignment_average(item: Any) -> float:
    """
    Get alignment_average from cross-domain insight for sorting.

    Used for sorting CrossDomainInsight by alignment average.
    Example: insights.sort(key=get_alignment_average, reverse=True)

    Args:
        item: CrossDomainInsight object with alignment_average

    Returns:
        The alignment_average value
    """
    return item.alignment_average


def get_conflict_count(item: dict[str, Any]) -> int:
    """
    Get conflict_count from dictionary for conflict sorting.

    Used for sorting conflicting principles by conflict count.
    Example: sorted(conflicts.values(), key=get_conflict_count, reverse=True)

    Args:
        item: Dictionary with 'conflict_count' key

    Returns:
        The conflict_count value
    """
    return item["conflict_count"]


def make_dict_count_getter(counts_dict: dict[str, int]):
    """
    Create a sort key function for dictionary count lookups.

    Used for finding max value from a dictionary of counts.
    Example:
        alignment_counts = {"high": 5, "medium": 3, "low": 2}
        most_common = max(alignment_counts.keys(), key=make_dict_count_getter(alignment_counts))

    Args:
        counts_dict: Dictionary mapping keys to counts

    Returns:
        A function that can be used as a sort/max key
    """

    def get_count(key: str) -> int:
        """Get count for key from dictionary."""
        return counts_dict[key]

    return get_count


def get_tuple_first(item: tuple[Any, ...]) -> Any:
    """
    Get first element from a tuple.

    Used for sorting tuples by their first element.
    Example: blocked_times.sort(key=get_tuple_first)

    Args:
        item: Tuple of any length

    Returns:
        The first element of the tuple
    """
    return item[0]


def get_aligned_count(item: tuple[str, dict[str, Any]]) -> int:
    """
    Get aligned_count from principle breakdown tuple.

    Used for sorting principle alignment data by aligned choice count.
    Example: sorted(principle_breakdown.items(), key=get_aligned_count, reverse=True)

    Args:
        item: Tuple of (principle_uid, breakdown_dict) where breakdown_dict has 'aligned_count'

    Returns:
        The aligned_count value
    """
    return item[1]["aligned_count"]


def make_dict_value_getter(values_dict: dict[str, float], default: float = 0.0):
    """
    Create a sort key function for dictionary value lookups.

    Used for finding max/min values from a dictionary when sorting by keys.
    Example:
        load_by_timeframe = {"weekly": 3.5, "monthly": 2.0}
        peak = max(load_by_timeframe, key=make_dict_value_getter(load_by_timeframe))

    Args:
        values_dict: Dictionary mapping keys to float values
        default: Default value for missing keys (default 0.0)

    Returns:
        A function that can be used as a sort/max/min key
    """

    def get_value(key: str) -> float:
        """Get value for key from dictionary."""
        return values_dict.get(key, default)

    return get_value
