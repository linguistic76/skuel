"""
GraphQL Mapper Functions
========================

Standalone conversion functions that transform domain objects into GraphQL types.
Extracted from classmethods on Strawberry types to separate schema definition
from conversion logic.

Each function uses structural protocols for type-safe parameters instead of ``Any``.
Deferred imports of Strawberry types avoid circular imports (same pattern as
``query_helpers.py``).

See: /docs/patterns/TYPE_SAFETY_OVERVIEW.md, /docs/patterns/ANY_USAGE_POLICY.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from routes.graphql.protocols import (
        KnowledgeNodeLike,
        LearningPathLike,
        LearningStepMappable,
        TaskLike,
    )
    from routes.graphql.types import KnowledgeNode, LearningPath, LearningStep, Task


def knowledge_node_from_dto(dto: KnowledgeNodeLike) -> KnowledgeNode:
    """Convert any curriculum-like object to KnowledgeNode.

    Accepts Article, CurriculumDTO, EntityDTO, or any object satisfying
    KnowledgeNodeLike protocol.
    """
    from routes.graphql.types import KnowledgeNode

    return KnowledgeNode(
        uid=dto.uid,
        title=dto.title,
        summary=dto.summary or "",
        domain=dto.domain.value,
        tags=dto.tags or [],
        quality_score=dto.quality_score,
    )


def knowledge_node_from_search_dict(item: dict[str, Any]) -> KnowledgeNode:
    """Convert a SearchRouter faceted_search result dict to KnowledgeNode."""
    from routes.graphql.types import KnowledgeNode

    return KnowledgeNode(
        uid=item.get("uid", ""),
        title=item.get("title", ""),
        summary=item.get("summary", ""),
        domain=item.get("_domain", "knowledge"),
        tags=item.get("tags", []),
        quality_score=item.get("quality_score", 0.5),
    )


def task_from_dto(dto: TaskLike) -> Task:
    """Convert a Task domain model to GraphQL Task type."""
    from routes.graphql.types import Task

    return Task(
        uid=dto.uid,
        title=dto.title,
        description=dto.description or "",
        status=dto.status.value,
        priority=dto.priority or "medium",
    )


def learning_path_from_dto(dto: LearningPathLike) -> LearningPath:
    """Convert a LP domain model to GraphQL LearningPath type."""
    from routes.graphql.types import LearningPath

    return LearningPath(
        uid=dto.uid,
        name=dto.title,
        goal=dto.description or "",
        total_steps=0,  # Steps loaded lazily via LearningPath.steps resolver
        estimated_hours=dto.estimated_hours or 0.0,
    )


def learning_step_from_domain(step: LearningStepMappable, step_number: int) -> LearningStep:
    """Convert Ls domain model to GraphQL LearningStep DTO.

    This explicit conversion layer:
    - Catches type mismatches at conversion time
    - Provides clear contract between service and API layers
    - Eliminates need for defensive hasattr() checks

    Args:
        step: Ls domain model from service layer (satisfies LearningStepMappable)
        step_number: Step position in learning path (1-indexed)

    Returns:
        LearningStep GraphQL DTO with only fields needed by API
    """
    from routes.graphql.types import LearningStep

    return LearningStep(
        step_number=step_number,
        uid=step.uid,
        title=step.title,
        knowledge_uid=step.primary_knowledge_uids[0] if step.primary_knowledge_uids else "",
        mastery_threshold=step.mastery_threshold,
        estimated_time=step.estimated_hours,
    )
