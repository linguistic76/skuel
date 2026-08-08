"""
Sort Functions for Collections
==============================

Named sort functions to replace lambda expressions in sorting operations.
Following clean code principle: no lambdas, only named functions.
"""

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from _typeshed import SupportsRichComparison

from core.ports.base_protocols import HasPriority, HasToNumeric


def get_result_score(scored_result: tuple[Any, float]) -> float:
    """
    Get score from (result, score) tuple.

    Used for sorting ranked search results by relevance score.
    Example: scored_results.sort(key=get_result_score, reverse=True)
    """
    return scored_result[1]


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
        # Handle string priorities (stored as str via Neo4j deserialization)
        if isinstance(item.priority, str):
            from core.models.enums import Priority

            try:
                return Priority(item.priority).to_numeric()
            except ValueError:
                return 0
        # Ensure we return an int (priority could be int)
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


def get_principle_strength_order(principle: Any) -> int:
    """Sort key for principles by strength (CORE first = 0, EXPLORING last = 4)."""
    from core.models.enums.principle_enums import PrincipleStrength

    return PrincipleStrength.from_value(
        getattr(principle, "strength", PrincipleStrength.MODERATE)
    ).sort_order()


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


# =============================================================================
# CONTEXTUAL OBJECT SORTING (Planning Mixin - January 2026)
# =============================================================================


def make_dict_value_getter[K, V: "SupportsRichComparison"](
    mapping: Mapping[K, V],
) -> Callable[[K], V]:
    """
    Create a sort key function for dictionary value lookups.

    Used for finding max/min by value over a dictionary's keys. Replaces
    `dict.get` as a key= callable — `dict.get`'s `_VT | None` return type
    is rejected by max/min as it doesn't satisfy SupportsRichComparison.

    Two type-level choices make this typecheck under `--enable-error-code
    arg-type` at `max`/`min` call sites:

    - The parameter is `Mapping[K, V]`, not `dict[K, V]`: `max`/`min`'s `key=`
      context widens `V` to `SupportsRichComparison` via bidirectional inference,
      and `dict` is *invariant* in its value type — so a concrete `dict[str,
      float]` argument is rejected against `dict[str, SupportsRichComparison]`.
      `Mapping` is *covariant* in its value type, so the concrete dict is
      accepted.
    - `V` is bound to `SupportsRichComparison`, documenting that values must be
      orderable (every call site passes `int`/`float` values).

    Example:
        alignment_counts = {"high": 5, "medium": 3, "low": 2}
        most_common = max(alignment_counts, key=make_dict_value_getter(alignment_counts))

    Args:
        mapping: Dictionary to look up values in

    Returns:
        A function that takes a key and returns its value
    """

    def get_value(key: K) -> V:
        return mapping[key]

    return get_value


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


def get_principle_frequency_rank(item: tuple[str, int]) -> tuple[int, str]:
    """
    Rank a (principle_uid, count) pair: most frequent first, UID ascending on ties.

    Used to pick the most-linked principle deterministically. The UID tie-break matters
    because the counts are built from Neo4j ``collect()`` output, whose order can differ
    between runs — without it, two principles on equal counts would make the winner
    non-reproducible for the same graph.
    Example: min(principle_frequency.items(), key=get_principle_frequency_rank)

    Args:
        item: Tuple of (principle_uid, occurrence_count)

    Returns:
        Sort key placing the highest count first, then the lowest UID
    """
    uid, count = item
    return (-count, uid)
