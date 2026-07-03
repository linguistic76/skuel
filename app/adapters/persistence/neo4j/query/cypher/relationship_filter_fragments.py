"""
Relationship Filter Fragments - Graph-Aware Faceted Search WHERE Clauses
=========================================================================

Authors the Cypher WHERE-clause fragments that realize each graph-aware
relationship filter (ready to learn, builds on mastered, supports goals, ...).

These fragments used to be built in ``core/models/search_request.py`` and
handed to ``faceted_search_raw`` as a pre-built ``dict[str, str]`` — the
"inverted boundary" anti-pattern (a core model authoring Cypher for a
passthrough adapter to execute blindly). They now live below the hexagonal
boundary (ADR-044): ``SearchRequest`` passes only the active-flag *intent*
(``RelationshipFilters``) down, and the flag→Cypher mapping is authored here.

The anchor node is ``(entity)`` — the variable ``faceted_search_raw`` binds the
candidate node to. ``$user_uid`` is a Cypher query parameter filled at
execution time, not here. Relationship types are a fixed, hand-authored
vocabulary (the same literals the prior fragments used), so nothing is
interpolated from caller input.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.relationship_filters import RelationshipFilters

__all__ = ["build_relationship_filter_fragments"]


# Pattern 1: Ready to learn (all prerequisites mastered)
_READY_TO_LEARN = """NOT EXISTS {
    MATCH (entity)-[:REQUIRES_KNOWLEDGE]->(prereq:Entity)
    WHERE NOT EXISTS {
        MATCH (user:User {uid: $user_uid})-[:MASTERED]->(prereq)
    }
}"""

# Pattern 2: Builds on mastered knowledge (related to what user knows)
_BUILDS_ON_MASTERED = """EXISTS {
    MATCH (user:User {uid: $user_uid})-[:MASTERED]->(mastered:Entity)
    WHERE (mastered)-[:ENABLES_LEARNING|RELATED_TO]-(entity)
}"""

# Pattern 3: In active learning path
_IN_ACTIVE_PATH = """EXISTS {
    MATCH (user:User {uid: $user_uid})-[:ENROLLED_IN]->(lp:LearningPath)
          -[:CONTAINS_STEP]->(ps:PathStep)
          -[:REQUIRES_KNOWLEDGE]->(entity)
    WHERE lp.status = 'active'
}"""

# Pattern 4: Supports active goals
_SUPPORTS_GOALS = """EXISTS {
    MATCH (user:User {uid: $user_uid})-[:PURSUING_GOAL]->(goal:Goal)
          -[:REQUIRES_KNOWLEDGE]->(entity)
    WHERE goal.status IN ['active', 'in_progress']
}"""

# Pattern 5: Builds on active habits
_BUILDS_ON_HABITS = """EXISTS {
    MATCH (user:User {uid: $user_uid})-[:PRACTICES]->(habit:Habit)
          -[:APPLIES_KNOWLEDGE]->(entity)
    WHERE habit.status IN ['active', 'in_progress']
      AND habit.is_active = true
}"""

# Pattern 6: Applied in recent tasks
_APPLIED_IN_TASKS = """EXISTS {
    MATCH (user:User {uid: $user_uid})-[:OWNS]->(task:Task)
          -[:APPLIES_KNOWLEDGE]->(entity)
    WHERE task.status IN ['completed', 'in_progress']
      AND task.updated_at >= datetime() - duration({days: 30})
}"""

# Pattern 7: Aligned with principles
_ALIGNED_WITH_PRINCIPLES = """EXISTS {
    MATCH (user:User {uid: $user_uid})-[:ADHERES_TO]->(principle:Principle)
          -[:EMBODIES_KNOWLEDGE]->(entity)
    WHERE principle.status = 'adopted'
      OR principle.priority >= 0.7
}"""

# Pattern 8: Next logical step (enabled by mastered, not yet mastered, prereqs met)
_NEXT_LOGICAL_STEP = """EXISTS {
    MATCH (user:User {uid: $user_uid})-[:MASTERED]->(mastered:Entity)
          -[:ENABLES_LEARNING]->(entity)
    WHERE NOT EXISTS {
        MATCH (user)-[:MASTERED]->(entity)
    }
    AND NOT EXISTS {
        MATCH (entity)-[:REQUIRES_KNOWLEDGE]->(prereq:Entity)
        WHERE NOT EXISTS {
            MATCH (user)-[:MASTERED]->(prereq)
        }
    }
}"""

# Pattern 9: Not yet viewed - show unseen content
_NOT_YET_VIEWED = """NOT EXISTS {
    MATCH (user:User {uid: $user_uid})-[:VIEWED|IN_PROGRESS|MASTERED]->(entity)
}"""

# Pattern 10: Viewed but not mastered - in-progress content
_VIEWED_NOT_MASTERED = """EXISTS {
    MATCH (user:User {uid: $user_uid})-[:VIEWED|IN_PROGRESS]->(entity)
}
AND NOT EXISTS {
    MATCH (user:User {uid: $user_uid})-[:MASTERED]->(entity)
}"""

# Pattern 11: Ready for review (mastered but not reviewed recently)
_READY_TO_REVIEW = """EXISTS {
    MATCH (user:User {uid: $user_uid})-[m:MASTERED]->(entity)
    WHERE m.mastered_at <= datetime() - duration({days: 30})
}"""


def build_relationship_filter_fragments(filters: RelationshipFilters) -> list[str]:
    """Map active relationship-filter flags to Cypher WHERE-clause fragments.

    Each active flag contributes one self-contained boolean fragment (anchored
    on ``(entity)``, referencing ``$user_uid``) which the caller AND-joins into
    the faceted-search WHERE clause. Emission order is fixed (matches the
    ``RelationshipFilters`` field order) for deterministic queries.

    Args:
        filters: The active relationship-filter intent.

    Returns:
        Ordered list of Cypher fragments; empty when no filters are active.
    """
    ordered: list[tuple[bool, str]] = [
        (filters.ready_to_learn, _READY_TO_LEARN),
        (filters.builds_on_mastered, _BUILDS_ON_MASTERED),
        (filters.in_active_path, _IN_ACTIVE_PATH),
        (filters.supports_goals, _SUPPORTS_GOALS),
        (filters.builds_on_habits, _BUILDS_ON_HABITS),
        (filters.applied_in_tasks, _APPLIED_IN_TASKS),
        (filters.aligned_with_principles, _ALIGNED_WITH_PRINCIPLES),
        (filters.next_logical_step, _NEXT_LOGICAL_STEP),
        (filters.not_yet_viewed, _NOT_YET_VIEWED),
        (filters.viewed_not_mastered, _VIEWED_NOT_MASTERED),
        (filters.ready_to_review, _READY_TO_REVIEW),
    ]
    return [fragment for active, fragment in ordered if active]
