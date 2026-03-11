"""
GraphQL Type Definitions
========================

Strawberry type definitions for SKUEL GraphQL API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import strawberry
from strawberry.types import (
    Info,  # noqa: TC002 - Strawberry evaluates resolver annotations at runtime
)

from routes.graphql.context import GraphQLContext
from routes.graphql.query_helpers import GraphQLQueryHelpers, unwrap_list

if TYPE_CHECKING:
    from core.models.pathways.learning_step import LearningStep as LsModel
    from core.utils.result_simplified import Result

# Protocol for objects with curriculum-like attributes (Article, CurriculumDTO, etc.)
# Used by from_dto() classmethods to accept any object with the right fields.
_KNOWLEDGE_NODE_DEFAULTS = {"summary": "", "tags": [], "quality_score": 0.0}


@strawberry.type
class KnowledgeNode:
    """A knowledge unit with optional nested relationships."""

    uid: str
    title: str
    summary: str
    domain: str
    tags: list[str]
    quality_score: float

    @classmethod
    def from_dto(cls, dto: Any) -> KnowledgeNode:
        """Convert any curriculum-like object to KnowledgeNode.

        Accepts Article, CurriculumDTO, or any object with uid/title/summary/domain/tags/quality_score.
        """
        return cls(
            uid=dto.uid,
            title=dto.title,
            summary=dto.summary or "",
            domain=dto.domain.value,
            tags=dto.tags or [],
            quality_score=getattr(dto, "quality_score", _KNOWLEDGE_NODE_DEFAULTS["quality_score"]),
        )

    @classmethod
    def from_search_dict(cls, item: dict[str, Any]) -> KnowledgeNode:
        """Convert a SearchRouter faceted_search result dict to KnowledgeNode."""
        return cls(
            uid=item.get("uid", ""),
            title=item.get("title", ""),
            summary=item.get("summary", ""),
            domain=item.get("_domain", "knowledge"),
            tags=item.get("tags", []),
            quality_score=item.get("quality_score", 0.5),
        )

    @strawberry.field
    async def prerequisites(self, info: Info[GraphQLContext, Any]) -> list[KnowledgeNode]:
        """
        Get prerequisite knowledge units.

        Uses GraphQLQueryHelpers with QueryPatterns + DataLoader batching.
        """
        return await GraphQLQueryHelpers.get_prerequisites(info.context, self.uid)

    @strawberry.field
    async def enables(self, info: Info[GraphQLContext, Any]) -> list[KnowledgeNode]:
        """
        Get knowledge units enabled by this one.

        Uses GraphQLQueryHelpers with QueryPatterns + DataLoader batching.
        """
        return await GraphQLQueryHelpers.get_enables(info.context, self.uid)


@strawberry.type
class Task:
    """
    A task with optional nested knowledge units.

    Note: knowledge_uid field removed.
    Use the knowledge() resolver to get associated knowledge units.
    """

    uid: str
    title: str
    description: str
    status: str
    priority: str

    @classmethod
    def from_dto(cls, dto: Any) -> Task:
        """Convert a Task domain model to GraphQL Task type."""
        return cls(
            uid=dto.uid,
            title=dto.title,
            description=dto.description or "",
            status=dto.status.value,
            priority=dto.priority or "medium",
        )

    @strawberry.field
    async def knowledge(self, info: Info[GraphQLContext, Any]) -> KnowledgeNode | None:
        """
        Get the knowledge unit associated with this task.

        GRAPH-NATIVE: Queries relationships instead of stored field.
        Uses GraphQLQueryHelpers with QueryPatterns + DataLoader batching.
        """
        return await GraphQLQueryHelpers.get_task_knowledge(info.context, self.uid)


@strawberry.type
class LearningPath:
    """A learning path with nested steps."""

    uid: str
    name: str
    goal: str
    total_steps: int
    estimated_hours: float

    @classmethod
    def from_dto(cls, dto: Any) -> LearningPath:
        """Convert a LP domain model to GraphQL LearningPath type."""
        return cls(
            uid=dto.uid,
            name=dto.title,
            goal=dto.description or "",
            total_steps=0,  # Steps loaded lazily via LearningPath.steps resolver
            estimated_hours=dto.estimated_hours or 0.0,
        )

    @strawberry.field
    async def steps(self, info: Info[GraphQLContext, Any]) -> list[LearningStep]:
        """
        Get learning path steps.

        Each step can nest its knowledge unit, solving N+1 problems.
        Uses LearningStep.from_domain() for explicit DTO conversion.
        """
        context: GraphQLContext = info.context

        if not context.services.lp:
            return []

        # Get steps with type safety
        result: Result[list[LsModel]] = await context.services.lp.get_path_steps(self.uid)
        steps: list[LsModel] = unwrap_list(result)

        # Convert domain models to GraphQL DTOs using explicit from_domain()
        return [LearningStep.from_domain(step, i + 1) for i, step in enumerate(steps)]


@strawberry.type
class LearningStep:
    """
    GraphQL-specific view of LearningStep (DTO pattern).

    This is a flatter structure optimized for GraphQL queries,
    containing only the fields needed by the API layer.
    Converted from Ls domain model via from_domain() method.
    """

    step_number: int
    uid: str
    title: str
    knowledge_uid: str
    mastery_threshold: float
    estimated_time: float

    @classmethod
    def from_domain(cls, step: Any, step_number: int) -> LearningStep:
        """
        Convert Ku domain model to GraphQL DTO.

        This explicit conversion layer:
        - Catches type mismatches at conversion time
        - Provides clear contract between service and API layers
        - Eliminates need for defensive hasattr() checks

        Args:
            step: Ls domain model from service layer
            step_number: Step position in learning path (1-indexed)

        Returns:
            LearningStep GraphQL DTO with only fields needed by API
        """
        return cls(
            step_number=step_number,
            uid=step.uid,
            title=step.title,
            knowledge_uid=step.primary_knowledge_uids[0] if step.primary_knowledge_uids else "",
            mastery_threshold=step.mastery_threshold,
            estimated_time=step.estimated_hours,
        )

    @strawberry.field
    async def knowledge(self, info: Info[GraphQLContext, Any]) -> KnowledgeNode | None:
        """
        Get the knowledge unit for this step.

        Uses DataLoader for batching when loading multiple steps.
        """
        context: GraphQLContext = info.context

        # Use DataLoader
        ku = await context.knowledge_loader.load(self.knowledge_uid)

        if not ku:
            return None

        return KnowledgeNode.from_dto(ku)


@strawberry.type
class SearchResult:
    """Semantic search result with ranking."""

    knowledge: KnowledgeNode
    relevance: float
    explanation: str


@strawberry.type
class CrossDomainOpportunity:
    """Cross-domain learning opportunity."""

    source: KnowledgeNode
    target: KnowledgeNode
    bridge_type: str
    transferability: float
    effort_required: str
    reasoning: str

    # Additional fields from AdaptiveLpCrossDomainService
    practical_projects: list[str] | None = None
    success_patterns: list[str] | None = None
    supporting_examples: list[str] | None = None


# Input Types


@strawberry.input
class SearchInput:
    """Input for semantic search."""

    query: str
    limit: int | None = 20
    domains: list[str] | None = None
    min_quality: float = 0.0


@strawberry.type
class DashboardData:
    """User dashboard summary data."""

    tasks_count: int
    paths_count: int
    habits_count: int


@strawberry.input
class TaskInput:
    """Input for task creation."""

    title: str
    description: str | None = None
    priority: str = "medium"
    knowledge_uid: str | None = None


# ============================================================================
# Complex Graph Query Types
# ============================================================================


@strawberry.type
class LearningPathContext:
    """
    Extended context for a learning path including progress, blockers, and recommendations.

    This type demonstrates GraphQL's strength: combining related data from multiple
    sources into a single rich response.
    """

    path: LearningPath
    current_step_number: int
    completed_steps: int
    completion_percentage: float
    blockers: list[Blocker]
    next_recommended_steps: list[LearningStep]
    prerequisites_met: bool


@strawberry.type
class PrerequisiteNode:
    """A node in the prerequisite dependency graph."""

    knowledge: KnowledgeNode
    depth: int
    is_mastered: bool
    children: list[PrerequisiteNode]


@strawberry.type
class PrerequisiteGraph:
    """
    Prerequisite chain showing full dependency tree.

    This solves the "what do I need to learn first?" question by traversing
    the entire prerequisite chain in a single query.
    """

    target: KnowledgeNode
    prerequisite_tree: list[PrerequisiteNode]
    total_prerequisites: int
    prerequisites_mastered: int
    estimated_total_hours: float


@strawberry.type
class DependencyEdge:
    """An edge in the dependency graph."""

    from_knowledge: KnowledgeNode
    to_knowledge: KnowledgeNode
    relationship_type: str
    strength: float


@strawberry.type
class DependencyGraph:
    """
    Knowledge dependency graph showing relationships.

    This visualizes how knowledge units connect, useful for understanding
    the broader knowledge structure.
    """

    center: KnowledgeNode
    nodes: list[KnowledgeNode]
    edges: list[DependencyEdge]
    depth: int


@strawberry.type
class Blocker:
    """
    A blocker preventing progress in a learning path.

    Types of blockers:
    - Missing prerequisite
    - Low mastery score
    - Circular dependency
    """

    blocker_type: str
    knowledge_uid: str
    knowledge_title: str
    severity: str  # "critical", "warning", "info"
    description: str
    recommended_action: str
