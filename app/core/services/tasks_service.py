"""
Enhanced Tasks Service - Facade Pattern
========================================

Tasks service facade that delegates to specialized sub-services.

Sub-Services:
- TasksCoreService: CRUD operations
- TasksSearchService: Search and discovery (DomainSearchOperations[Task] protocol)
- TasksProgressService: Progress tracking and completion
- TasksSchedulingService: Scheduling and context-aware creation
- TasksLearningService: Learning path integration and learning-aligned suggestions
- UnifiedRelationshipService (TASKS_CONFIG): Dependencies and relationships
"""

from __future__ import annotations

import dataclasses
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, TypedDict

from core.models.type_hints import EntityUID, UserUID
from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone

if TYPE_CHECKING:
    from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
    from core.ports.base_protocols import Direction
    from core.ports.domain_protocols import TasksOperations
    from core.ports.infrastructure_protocols import EventBusOperations
    from core.ports.intelligence_protocols import KnowledgeIntelligenceOperations
    from core.ports.query_types import TaskDependencyNeighbor, TaskDependencyNeighbors
    from core.ports.search_protocols import TasksSearchOperations
    from core.services.cross_domain import CrossDomainQueryService
    from core.services.entity_inference_service import EntityInferenceService
    from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
    from core.services.insight.insight_generation_service import InsightGenerationService
    from core.services.insight.insight_store import InsightStore
    from core.services.tasks.tasks_ai_service import TasksAIService

# Domain models
from core.events import GoalContributionsChanged, TaskUpdated, publish_event
from core.models.enums import EntityStatus, Priority
from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName
from core.models.sentinels import UNSET, Unset
from core.models.task.task import Task
from core.models.task.task_dto import TaskDTO
from core.models.task.task_update_intent import TaskUpdateIntent
from core.models.type_hints import Neo4jProperties
from core.services.activity_domain_config import CommonSubServices, create_common_sub_services

# Base service
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.filtered_context import build_filtered_context
from core.services.mixins import KnowledgeIntelligenceDelegationMixin
from core.services.mixins.link_edge_guard import (
    GOAL_FAR_END,
    KNOWLEDGE_FAR_END,
    KNOWLEDGE_LABELS,
    LinkEdge,
    keep_permitted_link_edges,
)

# Unified relationship service
from core.services.relationships import UnifiedRelationshipService

# Sub-services
from core.services.tasks import (
    TaskEventHandlerService,
    TasksCoreService,
    TasksIntelligenceService,
    TasksLearningService,
    TasksPlanningService,
    TasksProgressService,
    TasksSchedulingService,
)
from core.services.tasks._orchestration_mixin import _OrchestrationMixin
from core.utils.activity_stats import compute_task_stats
from core.utils.list_helpers import FilterConfig, SortConfig, apply_entity_filter, apply_entity_sort
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from core.utils.sort_functions import (
    get_created_at_attr,
    get_project_and_title,
    get_task_due_date_sort_key,
)

if TYPE_CHECKING:
    from core.models.context_types import ContextualDependencies, ContextualTask
    from core.models.pathways.lp_position import LpPosition
    from core.models.task.task_request import TaskCreateRequest
    from core.ports.query_types import ListContext
    from core.services.user import UserContext
    from core.services.user.unified_user_context import RichUserContext


@dataclasses.dataclass(frozen=True)
class TaskEdgeIntent:
    """The edge-typed fields of a task update, split off its ``TaskUpdateIntent``.

    Each keeps the ADR-066 contract: ``UNSET`` = not in this update, ``None`` / ``[]`` =
    clear, a value = replace.
    """

    habit_uid: str | Unset | None = UNSET
    applies_knowledge_uids: list[str] | Unset | None = UNSET
    contributes_to_goal_uids: list[str] | Unset | None = UNSET

    def any_set(self) -> bool:
        """Whether this update touches any edge."""
        return any(
            value is not UNSET
            for value in (
                self.habit_uid,
                self.applies_knowledge_uids,
                self.contributes_to_goal_uids,
            )
        )


# TypedDicts for analytics dashboard structure (fixes MyPy index errors)
class TaskStatistics(TypedDict):
    """Task statistics for analytics dashboard."""

    total_tasks: int
    recent_tasks: int
    completed_tasks: int
    completion_rate: float
    average_complexity: float
    learning_opportunities_total: int


class LearningPatternsData(TypedDict):
    """Learning patterns data for analytics dashboard."""

    patterns_detected: int
    patterns: list[dict[str, Any]]


class KnowledgeMasteryData(TypedDict):
    """Knowledge mastery data for analytics dashboard."""

    areas_tracked: int
    average_mastery_level: float
    top_mastery_areas: list[dict[str, Any]]


class InsightsData(TypedDict):
    """Insights data for analytics dashboard."""

    insights_generated: int
    key_insights: list[dict[str, Any]]


class AnalyticsStatus(TypedDict):
    """Analytics processing status."""

    patterns_analysis: str
    insights_generation: str
    mastery_tracking: str
    recommendations: str


class TaskAnalyticsDashboard(TypedDict):
    """Complete analytics dashboard data structure."""

    timeframe_days: int
    user_uid: UserUID
    generated_at: str
    task_statistics: TaskStatistics
    learning_patterns: LearningPatternsData
    knowledge_mastery: KnowledgeMasteryData
    insights: InsightsData
    recommendations: list[Any]
    analytics_status: AnalyticsStatus


def _compute_task_stats(all_tasks: list[Any]) -> dict[str, int | float]:
    """Dict projection of TaskStats for the cross-domain ListContext contract."""
    s = compute_task_stats(all_tasks)
    return {
        "total": s.total,
        "active": s.active,
        "completed": s.completed,
        "overdue": s.overdue,
    }


def _compute_task_metadata(all_tasks: list[Any]) -> dict[str, Any]:
    """Compute task-specific metadata for UI dropdowns."""
    projects = sorted({t.project for t in all_tasks if t.project})
    assignees_set = {getattr(t, "assignee", None) for t in all_tasks}
    assignees_set.discard(None)
    return {"projects": list(projects), "assignees": sorted(assignees_set)}


def _is_task_not_completed(e: Any) -> bool:
    """Filter predicate: task is not completed."""
    return e.status != EntityStatus.COMPLETED


def _is_task_completed(e: Any) -> bool:
    """Filter predicate: task is completed."""
    return e.status == EntityStatus.COMPLETED


_TASK_FILTER_CONFIG: FilterConfig = {
    "active": _is_task_not_completed,
    "completed": _is_task_completed,
}


def _apply_task_secondary_filters(
    tasks: list[Any],
    project: str | None = None,
    assignee: str | None = None,
    due_filter: str | None = None,
) -> list[Any]:
    """Apply secondary filter criteria (project, assignee, due date) to task list.

    The status filter is applied beside it, through ``_TASK_FILTER_CONFIG``.
    """
    today = today_in(current_zone())

    if project:
        tasks = [t for t in tasks if t.project == project]

    if assignee:
        tasks = [t for t in tasks if getattr(t, "assignee", None) == assignee]

    if due_filter == "today":
        tasks = [t for t in tasks if t.due_date == today]
    elif due_filter == "tomorrow":
        tomorrow = today + timedelta(days=1)
        tasks = [t for t in tasks if t.due_date == tomorrow]
    elif due_filter == "week":
        week_end = today + timedelta(days=7)
        tasks = [t for t in tasks if t.due_date and t.due_date <= week_end]
    elif due_filter == "overdue":
        tasks = [
            t
            for t in tasks
            if t.due_date and t.due_date < today and t.status != EntityStatus.COMPLETED
        ]

    return tasks


def _get_task_priority_order(task: Any) -> int:
    """Sort key for priority (CRITICAL first = 0, LOW last = 3)."""
    return Priority.from_value(task.priority).sort_order()


_TASK_SORT_CONFIG: SortConfig = {
    "due_date": (get_task_due_date_sort_key, False),
    "priority": (_get_task_priority_order, False),
    "created_at": (get_created_at_attr, True),
    "project": (get_project_and_title, False),
}


def _apply_task_sort(tasks: list[Any], sort_by: str = "due_date") -> list[Any]:
    """Sort tasks using declarative config."""
    return apply_entity_sort(tasks, sort_by, _TASK_SORT_CONFIG, "due_date")


class TasksService(
    _OrchestrationMixin,
    KnowledgeIntelligenceDelegationMixin,
    BaseService["TasksOperations", Task, TaskUpdateIntent],
):
    """
    Tasks service facade with specialized sub-services.

    This facade:
    1. Delegates to 7 specialized sub-services for core operations
    2. Uses explicit delegation methods for all sub-service calls
    3. Retains explicit methods for complex orchestration and transformations
    4. Provides clean separation of concerns

    Delegation Methods:
    - Core CRUD: get_task, get_user_tasks, list_tasks, update_task, delete_task
    - Search: get_tasks_for_goal, get_tasks_for_habit, get_prioritized, etc.
    - Progress: check_prerequisites, unblock_task_if_ready, assign_task_to_user
    - Scheduling: create_task_with_context, create_task_from_path_step, etc.
    - Learning: get_learning_relevant_tasks, get_next_learning_task, suggest_learning_aligned_tasks
    - Analytics: analyze_learning_patterns, generate_task_insights, etc.

    Explicit Methods (custom logic):
    - create_task: Has special user_uid parameter handling
    - link_task_to_knowledge/goal: Passes specific parameters
    - analyze_task_knowledge_impact: Full orchestration
    """

    # ========================================================================
    # DOMAIN CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================
    # Facade services use same config as core/search sub-services
    _config = create_activity_domain_config(
        dto_class=TaskDTO,
        model_class=Task,
        domain_name="tasks",
        date_field="due_date",
        completed_statuses=(EntityStatus.COMPLETED.value,),
    )

    # ========================================================================
    # CLASS-LEVEL TYPE ANNOTATIONS
    # ========================================================================
    core: TasksCoreService
    search: TasksSearchOperations  # type: ignore[assignment]  # search service implements callable protocol
    progress: TasksProgressService
    scheduling: TasksSchedulingService
    planning: TasksPlanningService
    relationships: UnifiedRelationshipService
    intelligence: TasksIntelligenceService
    ai: TasksAIService | None
    event_handler: TaskEventHandlerService

    def __init__(
        self,
        backend: TasksOperations,
        cross_domain_query: CrossDomainQueryService,
        graph_intel: GraphIntelligenceService,
        ku_inference_service: EntityInferenceService | None = None,
        ku_generation_service: InsightGenerationService | None = None,
        event_bus: EventBusOperations | None = None,
        insight_store: InsightStore | None = None,
        activity_knowledge_intelligence: KnowledgeIntelligenceOperations | None = None,
        ai_service: TasksAIService | None = None,
    ) -> None:
        """
        Initialize enhanced tasks service with specialized sub-services.

        Args:
            backend: Protocol-based backend for task operations
            cross_domain_query: Cross-domain query service (REQUIRED)
            graph_intel: GraphIntelligenceService for pure Cypher analytics (REQUIRED)
            ku_inference_service: Service for automatic knowledge inference (optional)
            ku_generation_service: InsightGenerationService for knowledge generation (optional)
            event_bus: Event bus for publishing domain events (optional)
            insight_store: For persisting event-driven insights (optional)
            activity_knowledge_intelligence: Shared knowledge intelligence singleton (optional)
            ai_service: Optional AI service — None when INTELLIGENCE_TIER=core (optional)

        Migration Note (2026-04-22):
            Made graph_intel REQUIRED — TasksIntelligenceService construction needs it.
            Fail-fast at construction, not at method call. Matches Goals v3.2.0.
        """
        super().__init__(backend, "tasks")

        # Optional AI service (ADR-030: AI features are optional)
        self.ai: TasksAIService | None = ai_service

        self.logger = get_logger("skuel.services.tasks")  # structlog BoundLogger

        # Use factory for search, relationships, event_handler, learning, and
        # knowledge_intelligence. core and intelligence need domain-specific
        # parameters — created manually below.
        common: CommonSubServices[
            TasksCoreService, TasksSearchOperations, TasksIntelligenceService
        ] = create_common_sub_services(
            domain="tasks",
            backend=backend,
            graph_intel=graph_intel,
            event_bus=event_bus,
            insight_store=insight_store,
            skip={"core"},
            activity_knowledge_intelligence=activity_knowledge_intelligence,
        )
        assert common.search is not None  # 'search' not in skip
        assert common.relationships is not None  # 'relationships' not in skip

        # NOTE: Named 'search' for consistency with other domain facades
        # This shadows BaseService.search(), intentionally - we delegate via self.search.search()
        self.search: TasksSearchOperations = common.search
        self.relationships: UnifiedRelationshipService = common.relationships
        self.core = TasksCoreService(
            backend=backend, ku_inference_service=ku_inference_service, event_bus=event_bus
        )
        # Held for edge-only updates: those bypass core.update_task (which publishes
        # TaskUpdated), so the facade publishes the invalidation event itself.
        self.event_bus = event_bus

        # Intelligence service now uses BaseAnalyticsService (no AI dependencies)
        # See ADR-030 for the intelligence layer separation
        self.intelligence: TasksIntelligenceService = TasksIntelligenceService(
            backend=backend,
            graph_intel=graph_intel,
            relationship_service=self.relationships,
            event_bus=event_bus,
            insight_store=insight_store,
        )

        # Domain-specific sub-services
        self.learning: TasksLearningService = common.learning
        self.progress = TasksProgressService(backend=backend, event_bus=event_bus)
        # Holds core so its two create doors run through THE create primitive
        # (events, embedding request, guarded link edges) instead of backend.create.
        self.scheduling = TasksSchedulingService(backend=backend, core=self.core)
        self.planning = TasksPlanningService(
            backend=backend,
            cross_domain_query=cross_domain_query,
            relationship_service=self.relationships,
        )

        # Event-driven reactive handlers (fire-and-forget).
        # Constructed manually (not via factory) to wire ku_generation_service — knowledge
        # generation is a named TaskCompleted consequence, not a hidden orchestration side effect.
        self.event_handler: TaskEventHandlerService = TaskEventHandlerService(
            backend=backend,
            relationship_service=self.relationships,
            insight_store=insight_store,
            event_bus=event_bus,
            ku_generation_service=ku_generation_service,
        )

        # Knowledge intelligence (shared singleton — domain-agnostic)
        self.knowledge_intelligence = common.knowledge_intelligence  # always passed by bootstrap

        self.logger.info(
            "TasksService facade initialized with 9 sub-services: "
            "core, search, progress, scheduling, planning, learning, relationships, "
            "intelligence, event_handler"
        )

    # ========================================================================
    # DELEGATION METHODS
    # ========================================================================

    # Core CRUD delegations
    async def get_task(self, task_uid: str) -> Result[Task]:
        return await self.core.get_task(task_uid)

    async def get_user_tasks(self, user_uid: UserUID) -> Result[list[Task]]:
        return await self.core.get_user_tasks(user_uid)

    async def list_tasks(self, filters: dict | None = None, limit: int = 100) -> Result[list[Task]]:
        return await self.core.list_tasks(filters, limit)

    async def get_user_items_in_range(
        self,
        user_uid: UserUID,
        start_date: date,
        end_date: date,
        include_completed: bool = False,
        date_field: str | list[str] | None = None,
    ) -> Result[list[Task]]:
        return await self.core.get_user_items_in_range(
            user_uid=user_uid,
            start_date=start_date,
            end_date=end_date,
            include_completed=include_completed,
            date_field=date_field,
        )

    # Relationship-typed fields are graph edges, not node properties. They must be
    # split off the update and synced as edges regardless of which entry point a caller
    # uses — update_task (UI route), or the inherited update / update_for_user (generated
    # CRUD JSON route). The backend update does an unfiltered `SET n += $changes`, so a
    # relationship-typed field left in the property patch would write a junk denormalized
    # property onto the node AND skip the edge (the very split the ADR-035/ADR-065
    # graph-native migration removed).
    @staticmethod
    def _split_relationship_intent(
        intent: TaskUpdateIntent,
    ) -> tuple[TaskEdgeIntent, TaskUpdateIntent]:
        """Split the edge-typed fields off a ``TaskUpdateIntent``.

        Returns ``(edges, prop_intent)`` where ``prop_intent`` is the same intent with
        every edge-only field reset to ``UNSET`` (so its ``to_changes()`` carries only node
        properties). The edge values pass through with the canonical ADR-066 contract
        intact — ``UNSET`` = not in this update (untouched), ``None`` / ``[]`` = explicit
        clear, value = set — which ``_sync_relationship_edges`` consumes.
        """
        prop_intent = dataclasses.replace(
            intent,
            reinforces_habit_uid=UNSET,
            applies_knowledge_uids=UNSET,
            contributes_to_goal_uids=UNSET,
        )
        edges = TaskEdgeIntent(
            habit_uid=intent.reinforces_habit_uid,
            applies_knowledge_uids=intent.applies_knowledge_uids,
            contributes_to_goal_uids=intent.contributes_to_goal_uids,
        )
        return edges, prop_intent

    async def _delete_edges_of_kind(
        self, relationship_key: str, task_uid: str
    ) -> Result[list[str]]:
        """Remove every edge the registry key resolves to for this task; return their far ends.

        Stale-edge removal must succeed before new edges are created: treating a failed
        fetch as "no old edges", or ignoring a failed delete, would leave stale edges
        attached while still creating new ones and returning success — so cleared or
        replaced knowledge would keep affecting detectors and graph queries.
        """
        existing = await self.relationships.get_related_uids(relationship_key, EntityUID(task_uid))
        if existing.is_error:
            return Result.fail(existing)
        for old_uid in existing.value or []:
            deleted = await self.relationships.delete_relationship(
                relationship_key, task_uid, old_uid
            )
            if deleted.is_error:
                return Result.fail(deleted)
        return Result.ok(list(existing.value or []))

    async def _sync_relationship_edges(
        self, task_uid: str, *, owner_uid: str, edges: TaskEdgeIntent
    ) -> Result[list[str]]:
        """Replace the task's habit, knowledge and goal edges from the intent values.

        ``UNSET`` means "not in this update" (edges of that kind untouched); a value means
        "replace" — clearing every edge of that kind when the value is empty (``None`` for
        the habit, ``[]`` for the knowledge and goal sets).

        New edges are admitted through ``keep_permitted_link_edges`` — the far end must
        EXIST, be OWNED by ``owner_uid`` or by nobody, and be the KIND the field names —
        exactly as the create path admits them (``TasksCoreService._write_link_edges``).
        A refused edge is logged and dropped, never written. ``update_for_user`` verifies
        the TASK's owner and nothing about the far end, so this guard is what stands
        between a crafted update and another user's habit, knowledge or goal.

        New edges go through ``backend.create_relationships_batch`` with explicit
        ``RelationshipName`` values — NOT ``UnifiedRelationshipService.create_relationship``,
        whose dynamic ``link_task_to_<key>`` backend method does not exist for tasks.

        Returns the goals the task contributed to before a goal-set replace — the caller
        announces them, since a goal that lost a contribution cannot be found from the
        task afterwards. A replace that fails after its deletes began announces them
        itself before reporting the failure.
        """
        candidates: list[LinkEdge] = []

        if edges.habit_uid is not UNSET:
            # (Task)-[:REINFORCES_HABIT]->(Habit): a set value replaces whatever was linked.
            removed = await self._delete_edges_of_kind("habits", task_uid)
            if removed.is_error:
                return Result.fail(removed)
            if edges.habit_uid:  # non-empty → link the new target (None = cleared)
                candidates.append(
                    LinkEdge(
                        (task_uid, edges.habit_uid, RelationshipName.REINFORCES_HABIT.value, None),
                        other_uid=edges.habit_uid,
                        allowed_labels=frozenset({NeoLabel.HABIT.value}),
                    )
                )

        # The two edge SETS — (Task)-[:APPLIES_KNOWLEDGE]->(Ku) and
        # (Task)-[:CONTRIBUTES_TO_GOAL]->(Goal): a list replaces the full set; an empty
        # list clears it.
        removed_goals: list[str] = []
        edge_sets: tuple[
            tuple[str, list[str] | Unset | None, RelationshipName, frozenset[str]], ...
        ] = (
            (
                "knowledge",
                edges.applies_knowledge_uids,
                RelationshipName.APPLIES_KNOWLEDGE,
                KNOWLEDGE_LABELS,
            ),
            (
                "contributes_to_goal",
                edges.contributes_to_goal_uids,
                RelationshipName.CONTRIBUTES_TO_GOAL,
                frozenset({NeoLabel.GOAL.value}),
            ),
        )
        for relationship_key, uids, relationship, allowed_labels in edge_sets:
            if uids is UNSET:
                continue
            if relationship is RelationshipName.CONTRIBUTES_TO_GOAL:
                # Read the goal set before any delete: a delete that fails part-way has
                # still unlinked some goals, and every goal the task held is announced
                # (a recount of one it still holds changes nothing).
                prior = await self.relationships.get_related_uids(
                    relationship_key, EntityUID(task_uid)
                )
                if prior.is_error:
                    return Result.fail(prior)
                removed_goals = list(prior.value or [])
            removed = await self._delete_edges_of_kind(relationship_key, task_uid)
            if removed.is_error:
                if relationship is RelationshipName.CONTRIBUTES_TO_GOAL:
                    await self._announce_goal_set_change(task_uid, owner_uid, removed_goals)
                return Result.fail(removed)
            candidates.extend(
                LinkEdge(
                    (task_uid, far_uid, relationship.value, None),
                    other_uid=far_uid,
                    allowed_labels=allowed_labels,
                )
                for far_uid in dict.fromkeys(uids or [])
            )

        if candidates:
            permitted = await keep_permitted_link_edges(
                self.backend,
                candidates=candidates,
                subject_uid=task_uid,
                owner_uid=owner_uid,
                logger=self.logger,
            )
            if permitted:
                batch = await self.backend.create_relationships_batch(permitted)
                if batch.is_error:
                    # The old goal edges are already gone: announce the goals that lost
                    # the task before reporting the failure, or their tallies keep
                    # counting it.
                    if edges.contributes_to_goal_uids is not UNSET:
                        await self._announce_goal_set_change(task_uid, owner_uid, removed_goals)
                    return Result.fail(batch)
        return Result.ok(removed_goals)

    async def _announce_goal_set_change(
        self, task_uid: str, owner_uid: str, removed_goals: list[str]
    ) -> None:
        """Announce a replaced goal set: the goals the task left, and the task itself
        (the handler reads the goals it contributes to now)."""
        await publish_event(
            self.event_bus,
            GoalContributionsChanged(
                user_uid=UserUID(owner_uid),
                goal_uids=tuple(removed_goals),
                contributor_uids=(task_uid,),
            ),
            self.logger,
        )

    async def _publish_edge_only_update(
        self,
        task: Task,
        edges: TaskEdgeIntent,
    ) -> None:
        """Publish TaskUpdated after an edge-only update so user-context caches invalidate.

        Property updates publish TaskUpdated via TasksCoreService.update_task, but the
        relationship-only path bypasses it (fetch-only) — without this, rich context
        (entities_rich, ZPD, applied-knowledge/habit links) stays stale until the cache
        TTL expires. TaskUpdated is wired to context invalidation in _event_wiring.py.
        """
        changed_fields = [
            name
            for name, value in (
                ("reinforces_habit_uid", edges.habit_uid),
                ("applies_knowledge_uids", edges.applies_knowledge_uids),
                ("contributes_to_goal_uids", edges.contributes_to_goal_uids),
            )
            if value is not UNSET
        ]
        event = TaskUpdated(
            task_uid=task.uid, user_uid=task.user_uid, updated_fields=changed_fields
        )
        await publish_event(self.event_bus, event, self.logger)

    async def update_task(self, task_uid: str, intent: TaskUpdateIntent) -> Result[Task]:
        """THE Tasks update path (ADR-066). Splits the edge-only fields off the intent,
        writes node properties via core (events fire), and syncs the habit, knowledge and
        goal edges. See `_sync_relationship_edges`.

        A change to the task's goal set announces ``GoalContributionsChanged`` for the
        goals it left and the ones it now contributes to."""
        edges, prop_intent = self._split_relationship_intent(intent)

        # A relationship-only update (e.g. only applies_knowledge_uids, which
        # TaskUpdateRequest permits) leaves no node properties to write. The backend
        # rejects an empty update dict, so fetch the task to confirm it exists and to
        # have a Task to return. A genuinely empty call keeps the validation error.
        wrote_properties = bool(prop_intent.to_changes()) or not edges.any_set()
        if wrote_properties:
            result = await self.core.update_task(task_uid, prop_intent)
        else:
            result = await self.core.get_task(task_uid)
        if result.is_error:
            return result

        task = result.value
        sync = await self._sync_relationship_edges(task_uid, owner_uid=task.user_uid, edges=edges)
        if sync.is_error:
            return Result.fail(sync)
        if edges.contributes_to_goal_uids is not UNSET:
            await self._announce_goal_set_change(task_uid, task.user_uid, sync.value)
        if not wrote_properties:  # edge-only: core.update_task didn't fire TaskUpdated
            await self._publish_edge_only_update(task, edges)
        return Result.ok(task)

    async def update(self, uid: str, updates: TaskUpdateIntent) -> Result[Task]:
        """Override the inherited CRUD update (generated JSON route, no ownership check).

        Routes the typed intent through the one update path (`update_task`), which fires
        events and syncs edges — the inherited base `update` would write edge fields as
        junk node properties and skip the edge sync."""
        return await self.update_task(uid, updates)

    async def update_for_user(
        self,
        uid: str,
        updates: TaskUpdateIntent,
        user_uid: UserUID,
    ) -> Result[Task]:
        """Override the inherited ownership-verified CRUD update (generated JSON route).

        Verifies ownership BEFORE any mutation, then routes through the one update path
        (`update_task`)."""
        ownership = await self.verify_ownership(uid, user_uid)
        if ownership.is_error:
            return ownership
        return await self.update_task(uid, updates)

    async def get_reinforced_habit(self, task_uid: str) -> Result[str | None]:
        """Return the habit uid this task reinforces via (Task)-[:REINFORCES_HABIT]->(Habit).

        A task reinforces at most one habit, so this returns the first linked habit
        uid or ``None``. Graph-native — the linkage is the edge, not a property.
        """
        related = await self.relationships.get_related_uids("habits", EntityUID(task_uid))
        if related.is_error:
            return Result.fail(related)
        uids = related.value or []
        return Result.ok(uids[0] if uids else None)

    async def delete_task(self, task_uid: str) -> Result[bool]:
        return await self.core.delete_task(task_uid)

    async def delete_for_user(
        self, uid: str, user_uid: UserUID, cascade: bool = False
    ) -> Result[bool]:
        """Override the inherited ownership-verified CRUD delete (generated route).

        Verifies ownership BEFORE the delete, then deletes through the one task delete
        door (``TasksCoreService.delete_task``), which publishes ``TaskDeleted`` and
        announces the goals the task contributed to. A task's edges always go with it,
        so ``cascade`` is not read.
        """
        ownership = await self.verify_ownership(uid, user_uid)
        if ownership.is_error:
            return Result.fail(ownership)
        return await self.core.delete_task(uid)

    # Search delegations
    async def get_tasks_for_goal(self, goal_uid: str, user_uid: UserUID) -> Result[list[Task]]:
        return await self.search.get_tasks_for_goal(goal_uid, user_uid)

    async def get_tasks_for_habit(self, habit_uid: str, user_uid: UserUID) -> Result[list[Task]]:
        return await self.search.get_tasks_for_habit(habit_uid, user_uid)

    async def get_blocked_by_prerequisites(self, user_uid: UserUID) -> Result[list[Task]]:
        return await self.search.get_blocked_by_prerequisites(user_uid)

    async def get_prioritized(
        self, user_context: UserContext, limit: int = 10
    ) -> Result[list[Task]]:
        return await self.search.get_prioritized(user_context, limit)

    async def get_learning_relevant_tasks(
        self, user_uid: UserUID, learning_position: LpPosition, limit: int = 10
    ) -> Result[list[Task]]:
        return await self.learning.get_learning_relevant_tasks(user_uid, learning_position, limit)

    async def get_tasks_for_path_step(self, step_uid: str, user_uid: UserUID) -> Result[list[Task]]:
        return await self.search.get_tasks_for_path_step(step_uid, user_uid)

    async def get_upcoming(
        self, days_ahead: int = 7, user_uid: UserUID | None = None, limit: int = 100
    ) -> Result[list[Task]]:
        return await self.search.get_upcoming(days_ahead, user_uid, limit)

    async def get_overdue(
        self, user_uid: UserUID | None = None, limit: int = 100
    ) -> Result[list[Task]]:
        return await self.search.get_overdue(user_uid, limit)

    async def get_active(self, user_uid: UserUID, limit: int = 100) -> Result[list[Task]]:
        return await self.search.get_active(user_uid, limit)

    # Progress delegations
    async def check_prerequisites(
        self, task_uid: str, user_context: UserContext
    ) -> Result[dict[str, Any]]:
        return await self.progress.check_prerequisites(task_uid, user_context)

    async def unblock_task_if_ready(
        self, task_uid: str, user_context: UserContext
    ) -> Result[Task | None]:
        return await self.progress.unblock_task_if_ready(task_uid, user_context)

    async def assign_task_to_user(
        self,
        task_uid: str,
        user_uid: UserUID,
        assigned_by: str | None = None,
        priority_override: str | None = None,
    ) -> Result[bool]:
        return await self.progress.assign_task_to_user(
            task_uid, user_uid, assigned_by, priority_override
        )

    # Scheduling delegations
    async def create_task_with_context(
        self, task_data: TaskCreateRequest, user_context: UserContext
    ) -> Result[Task]:
        return await self.scheduling.create_task_with_context(task_data, user_context)

    async def create_tasks_from_learning_path(
        self, learning_path_uid: str, _user_context: UserContext
    ) -> Result[list[Task]]:
        return await self.learning.create_tasks_from_learning_path(learning_path_uid, _user_context)

    async def get_next_learning_task(self, user_context: UserContext) -> Result[Task | None]:
        return await self.learning.get_next_learning_task(user_context)

    async def suggest_learning_aligned_tasks(
        self, learning_position: LpPosition, _task_domain: str | None = None, limit: int = 10
    ) -> Result[list[dict[str, Any]]]:
        return await self.learning.suggest_learning_aligned_tasks(
            learning_position, _task_domain, limit
        )

    async def create_task_from_path_step(
        self, step_uid: str, task_title: str, knowledge_uids: list[str], user_uid: UserUID
    ) -> Result[Task]:
        return await self.scheduling.create_task_from_path_step(
            step_uid, task_title, knowledge_uids, user_uid
        )

    # Planning delegations
    async def get_task_dependencies_for_user(
        self,
        task_uid: str,
        context: UserContext,
        include_transitive: bool = False,
        max_depth: int = 2,
    ) -> Result[ContextualDependencies]:
        return await self.planning.get_task_dependencies_for_user(
            task_uid, context, include_transitive, max_depth
        )

    async def get_actionable_tasks_for_user(
        self, context: RichUserContext, limit: int = 10
    ) -> Result[list[ContextualTask]]:
        return await self.planning.get_actionable_tasks_for_user(context, limit)

    async def get_learning_tasks_for_user(
        self,
        context: UserContext,
        knowledge_focus: list[str] | None = None,
        limit: int = 10,
    ) -> Result[list[ContextualTask]]:
        return await self.planning.get_learning_tasks_for_user(context, knowledge_focus, limit)

    # Intelligence delegations
    async def analyze_task_learning_metrics(
        self, _filters: dict[str, Any] | None = None
    ) -> Result[list[dict[str, Any]]]:
        return await self.intelligence.analyze_task_learning_metrics(_filters)

    async def generate_task_knowledge_insights(
        self, _domain_filter: str | None = None
    ) -> Result[dict[str, Any]]:
        return await self.intelligence.generate_task_knowledge_insights(_domain_filter)

    # ========================================================================
    # EXPLICIT CORE METHODS (custom logic)
    # ========================================================================

    async def create(self, entity: Task) -> Result[Task]:
        """Override the inherited CRUD create — the ENTITY door.

        Routes the entity through the one event-firing create path
        (``TasksCoreService.create``). The inherited base ``create`` went straight to
        ``backend.create``: the core sub-service is the delegated attribute ``self.core``,
        which this facade does NOT inherit, so its ``create`` override was never in this
        class's MRO. The generated route therefore published neither TaskCreated nor the
        ADR-074 embedding request — a task created through ``POST /api/tasks/create``
        invalidated no user context and was never embedded.

        Same reconciliation ``ChoicesService.create`` makes (#960), and Goals, Habits and
        Events after it (#963). Tasks were held back there because they have no
        ``_validate_create`` rule to reach; the event half of the defect survived.

        The generated JSON route entered here until it was bound to
        ``create_task`` (the request door — ``CRUDRouteConfig.request_create_method``),
        so its request-only link fields could ride; this door remains for in-process
        callers that hand the CRUD surface an entity they built themselves.
        """
        return await self.core.create(entity)

    async def create_task(self, task_request: TaskCreateRequest, user_uid: UserUID) -> Result[Task]:
        """
        Create a task with automatic knowledge inference.

        Args:
            task_request: Task creation request
            user_uid: User UID (REQUIRED - fail-fast)

        Returns:
            Result containing created Task
        """
        return await self.core.create_task(task_request, user_uid)

    # ========================================================================
    # RELATIONSHIPS AND DEPENDENCIES
    # ========================================================================

    async def link_task_to_knowledge(
        self,
        task_uid: str,
        knowledge_uid: str,
        knowledge_score_required: float = 0.8,
        is_learning_opportunity: bool = False,
    ) -> Result[bool]:
        """Link task to the Ku it applies (``APPLIES_KNOWLEDGE``)."""
        return await self.relationships.create_relationship(
            "knowledge",
            task_uid,
            knowledge_uid,
            {
                "knowledge_score_required": knowledge_score_required,
                "is_learning_opportunity": is_learning_opportunity,
            },
            far_end=KNOWLEDGE_FAR_END,
        )

    async def link_task_to_goal(self, task_uid: str, goal_uid: str) -> Result[bool]:
        """Link a task to a goal it contributes to (``CONTRIBUTES_TO_GOAL``, no properties).

        Announces ``GoalContributionsChanged`` so the goal's tally counts the task.
        """
        result = await self.relationships.create_relationship(
            "contributes_to_goal", task_uid, goal_uid, far_end=GOAL_FAR_END
        )
        if result.is_ok:
            await self._announce_goal_contributions(task_uid, (goal_uid,))
        return result

    async def unlink_task_from_goal(self, task_uid: str, goal_uid: str) -> Result[bool]:
        """Remove a task's contribution to a goal.

        The keyed delete names the far end's kind (``Goal``), so it removes only this
        task's ``CONTRIBUTES_TO_GOAL`` edge. Announces ``GoalContributionsChanged`` for
        the goal, which can no longer be found from the task.
        """
        result = await self.relationships.delete_relationship(
            "contributes_to_goal", task_uid, goal_uid
        )
        if result.is_ok:
            await self._announce_goal_contributions(task_uid, (goal_uid,))
        return result

    async def _announce_goal_contributions(
        self, task_uid: str, goal_uids: tuple[str, ...] = ()
    ) -> None:
        """Publish ``GoalContributionsChanged`` for a task, under its owner.

        Best-effort: a task that no longer resolves is logged — its link is already
        written or removed.
        """
        task = await self.core.get_task(task_uid)
        if task.is_error:
            self.logger.warning(
                "Goal contributions of task %s not announced: %s", task_uid, task.error
            )
            return
        await publish_event(
            self.event_bus,
            GoalContributionsChanged(
                user_uid=task.value.user_uid, goal_uids=goal_uids, contributor_uids=(task_uid,)
            ),
            self.logger,
        )

    async def create_task_dependency(
        self,
        dependent_task_uid: str,
        blocks_task_uid: str,
        is_hard_dependency: bool = True,
        dependency_type: str = "blocks",
    ) -> Result[bool]:
        """Create a ``(dependent)-[:DEPENDS_ON]->(blocks)`` dependency edge between tasks.

        Backend: UniversalNeo4jBackend.create_relationships_batch — the same proven
        path the create/update flows use. NOT UnifiedRelationshipService.create_relationship,
        whose dynamic ``link_task_to_<key>`` backend method does not exist for tasks
        (it getattrs a missing method and fails at runtime — the bug this method had).
        """
        properties: Neo4jProperties = {
            "is_hard_dependency": is_hard_dependency,
            "dependency_type": dependency_type,
        }
        edges: list[tuple[str, str, str, Neo4jProperties | None]] = [
            (dependent_task_uid, blocks_task_uid, RelationshipName.DEPENDS_ON.value, properties)
        ]
        result = await self.backend.create_relationships_batch(edges)
        if result.is_error:
            return Result.fail(result)
        await self._publish_dependency_update(dependent_task_uid, blocks_task_uid)
        return Result.ok(True)

    async def _publish_dependency_update(
        self, dependent_task_uid: str, blocks_task_uid: str
    ) -> None:
        """Publish TaskUpdated for the affected owners after a DEPENDS_ON edge change.

        The dependency graph feeds ``UserContext.task_dependencies`` and the
        inverse blockers view, so a successful edge-only mutation must invalidate the
        owners' rich-context caches — otherwise dependency context stays stale until
        the TTL expires (same reason ``_publish_edge_only_update`` exists for the
        habit/knowledge edges). Best-effort: with no event bus wired, or a task that
        no longer resolves, this is a no-op — the edge is already written.
        """
        if self.event_bus is None:
            return
        seen: set[str] = set()
        for uid in (dependent_task_uid, blocks_task_uid):
            fetched = await self.backend.get(uid)
            if fetched.is_error or fetched.value is None:
                continue
            user_uid = fetched.value.user_uid
            if not user_uid or user_uid in seen:
                continue
            seen.add(user_uid)
            event = TaskUpdated(task_uid=uid, user_uid=user_uid, updated_fields=["dependencies"])
            await publish_event(self.event_bus, event, self.logger)

    async def delete_task_dependency(
        self, dependent_task_uid: str, blocks_task_uid: str
    ) -> Result[bool]:
        """Remove a ``(dependent)-[:DEPENDS_ON]->(blocks)`` dependency edge.

        The delete twin of :meth:`create_task_dependency`. Reuses the config-driven
        ``"prerequisite_tasks"`` relationship key (the outgoing ``DEPENDS_ON`` spec for
        Task) so the edge is oriented the same way it was written, then publishes the
        same ``TaskUpdated`` invalidation so both owners' rich-context caches refresh.

        Backend: UnifiedRelationshipService.delete_relationship → TasksBackend.delete_relationship.
        """
        result = await self.relationships.delete_relationship(
            "prerequisite_tasks", dependent_task_uid, blocks_task_uid
        )
        if result.is_error:
            return Result.fail(result)
        await self._publish_dependency_update(dependent_task_uid, blocks_task_uid)
        return Result.ok(True)

    async def get_task_dependency_neighbors(
        self, task_uid: str, user_uid: UserUID
    ) -> Result[TaskDependencyNeighbors]:
        """Return a task's *direct* ``DEPENDS_ON`` neighbours in both directions.

        Distinct from :meth:`get_task_dependencies_for_user` (contextual, planner-facing,
        variable-length transitive): this is the immediate one-hop neighbourhood the
        task-detail Dependencies fragment renders — ``depends_on`` (outgoing) and
        ``required_by`` (incoming). Reads via the backend enum traversal (the proven
        direct-neighbour path, no config method-key for the incoming direction) and
        hydrates titles/status in one batched fetch per direction.

        Owner-scoped: a ``DEPENDS_ON`` edge to a task owned by another user (from
        ingestion or a non-UI caller) is OMITTED, not disclosed — the list equivalent
        of the "not found for entities the user doesn't own" contract.

        Backend: TasksBackend.get_related_uids (both directions) + get_many.
        """
        depends_on = await self._hydrate_dependency_neighbors(task_uid, "outgoing", user_uid)
        if depends_on.is_error:
            return Result.fail(depends_on)
        required_by = await self._hydrate_dependency_neighbors(task_uid, "incoming", user_uid)
        if required_by.is_error:
            return Result.fail(required_by)
        neighbors: TaskDependencyNeighbors = {
            "depends_on": depends_on.value,
            "required_by": required_by.value,
        }
        return Result.ok(neighbors)

    async def _hydrate_dependency_neighbors(
        self, task_uid: str, direction: Direction, user_uid: UserUID
    ) -> Result[list[TaskDependencyNeighbor]]:
        """Fetch direct DEPENDS_ON neighbour UIDs in one direction and hydrate them.

        Neighbours owned by another user are filtered out (privacy — never disclose a
        foreign task's title/status through a dependency edge).
        """
        uids_result = await self.backend.get_related_uids(
            EntityUID(task_uid), RelationshipName.DEPENDS_ON, direction=direction
        )
        if uids_result.is_error:
            return Result.fail(uids_result)
        uids = uids_result.value
        if not uids:
            return Result.ok([])
        tasks_result = await self.backend.get_many(uids)
        if tasks_result.is_error:
            return Result.fail(tasks_result)
        neighbors: list[TaskDependencyNeighbor] = [
            {"uid": task.uid, "title": task.title, "status": task.status.value}
            for task in tasks_result.value
            if task is not None and task.user_uid == user_uid
        ]
        return Result.ok(neighbors)

    async def would_create_dependency_cycle(
        self, dependent_task_uid: str, blocks_task_uid: str
    ) -> Result[bool]:
        """Report whether adding ``dependent -[:DEPENDS_ON]-> blocks`` would form a cycle.

        A self-link is always a cycle. Otherwise the new edge closes a loop iff ``blocks``
        already (transitively) depends on ``dependent`` — i.e. a ``blocks -[:DEPENDS_ON*]->
        dependent`` path exists. Uses an UNBOUNDED reachability check (not the depth-10
        ``get_transitive_dependencies``, which would miss a cycle closing beyond the cap),
        guarding the variable-length transitive traversal in ``get_task_dependencies_for_user``
        from runaway on a cyclic graph.

        Backend: TasksBackend.dependency_path_exists.
        """
        if dependent_task_uid == blocks_task_uid:
            return Result.ok(True)
        return await self.backend.dependency_path_exists(
            blocks_task_uid, dependent_task_uid, RelationshipName.DEPENDS_ON
        )

    async def create_semantic_knowledge_relationship(
        self,
        task_uid: str,
        knowledge_uid: str,
        semantic_type: SemanticRelationshipType,
        confidence: float = 0.9,
        notes: str | None = None,
    ) -> Result[dict[str, Any]]:
        """Create a semantic relationship between task and knowledge."""
        return await self.relationships.create_semantic_relationship(
            task_uid, knowledge_uid, semantic_type, confidence, notes
        )

    # KNOWLEDGE ANALYSIS / ORCHESTRATION — provided by _OrchestrationMixin

    # ========================================================================
    # ANALYTICS — thin delegations to TasksIntelligenceService
    # ========================================================================

    async def analyze_learning_patterns(
        self, user_uid: UserUID, timeframe_days: int = 30
    ) -> Result[list[Any]]:
        """Analyze learning patterns across user's task activities."""
        return await self.intelligence.analyze_learning_patterns(user_uid, timeframe_days)

    async def calculate_knowledge_aware_priorities(
        self, user_uid: UserUID, task_uids: list[str] | None = None
    ) -> Result[list[Any]]:
        """Calculate knowledge-aware priority scores for tasks."""
        return await self.intelligence.calculate_knowledge_aware_priorities(user_uid, task_uids)

    async def generate_task_insights(
        self, user_uid: UserUID, timeframe_days: int = 30
    ) -> Result[list[Any]]:
        """Generate insights from user's completed tasks."""
        return await self.intelligence.generate_task_insights(user_uid, timeframe_days)

    async def track_knowledge_mastery_progression(
        self, user_uid: UserUID, knowledge_uids: list[str] | None = None
    ) -> Result[dict[str, Any]]:
        """Track knowledge mastery progression for user."""
        return await self.intelligence.track_knowledge_mastery_progression(user_uid, knowledge_uids)

    # ========================================================================
    # QUERY LAYER
    # ========================================================================

    # ========================================================================
    # HIERARCHY DELEGATIONS
    # ========================================================================

    async def get_subtasks(self, parent_uid: str, depth: int = 1) -> Result[list[Task]]:
        return await self.core.get_subentities(parent_uid, depth)

    async def get_parent_task(self, subtask_uid: str) -> Result[Task | None]:
        return await self.core.get_parent_entity(subtask_uid)

    async def get_task_hierarchy(self, task_uid: str) -> Result[dict[str, Any]]:
        return await self.core.get_entity_hierarchy(task_uid)

    async def create_subtask_relationship(
        self, parent_uid: str, child_uid: str, progress_weight: float = 1.0
    ) -> Result[bool]:
        return await self.core.create_subtask_relationship(parent_uid, child_uid, progress_weight)

    async def remove_subtask_relationship(self, parent_uid: str, child_uid: str) -> Result[bool]:
        return await self.core.remove_subtask_relationship(parent_uid, child_uid)

    async def get_filtered_context(
        self,
        user_uid: UserUID,
        project: str | None = None,
        assignee: str | None = None,
        due_filter: str | None = None,
        status_filter: str = "active",
        sort_by: str = "due_date",
    ) -> Result[ListContext]:
        """Get filtered and sorted tasks with pre-filter stats in a single query."""

        async def fetch_all() -> Result[list[Any]]:
            return await self.core.get_all_for_user(user_uid)

        def apply_filters(all_tasks: list[Any]) -> list[Any]:
            filtered = apply_entity_filter(all_tasks, status_filter, _TASK_FILTER_CONFIG)
            return _apply_task_secondary_filters(filtered, project, assignee, due_filter)

        return await build_filtered_context(
            fetch_all=fetch_all,
            compute_stats=_compute_task_stats,
            apply_filters=apply_filters,
            apply_sort=_apply_task_sort,
            sort_by=sort_by,
            compute_metadata=_compute_task_metadata,
        )


# Legacy alias removed - class renamed directly to TasksService
