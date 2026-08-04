"""
Route-Facing Service Protocols
================================

Protocols for cross-cutting and infrastructure services that are
directly consumed by route files. ISP-compliant: each protocol
captures only the methods called from routes.

Protocols:
- CalendarServiceOperations — Calendar aggregation
- VisualizationOperations — Chart.js/Vis.js/Gantt aggregation + formatting
- SystemServiceOperations — Health checks and monitoring
- CrossDomainAnalyticsOperations — Event-driven analytics
- LifePathOperations — Vision-to-action bridge
- GraphAuthOperations — Graph-native authentication
- GoalTaskGeneratorOperations — Goal→Task generation
- HabitEventSchedulerOperations — Habit→Event scheduling
- LateralRelationshipOperations — Lateral relationship CRUD + graph queries
- LateralRelationshipBackendOperations — Backend-level Cypher for lateral relationships
- OwnershipVerifier — narrow protocol for ownership verification callbacks
"""

from collections.abc import Callable
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from core.models.relationship_names import RelationshipName
from core.models.type_hints import EntityUID, Neo4jProperties, UserUID
from core.ports.query_types import (
    AlertCheckResult,
    BlockingChainRow,
    ChartJsConfig,
    CousinRow,
    GanttConfig,
    HealthCheckValidation,
    HealthSummaryResult,
    LateralRelationshipRow,
    RelationshipGraphRow,
    SiblingRow,
    SystemHealthStatus,
    SystemInfoResult,
)
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.enums import UserRole
    from core.models.event.calendar_models import CalendarData, CalendarItem, CalendarView
    from core.models.event.event_dto import EventDTO
    from core.models.habit.completion import HabitCompletion
    from core.models.task.task_dto import TaskDTO
    from core.ports.query_types import (
        AlternativeComparisonItem,
        BlockingChainResult,
        LateralRelationshipItem,
        LifePathAlignmentResult,
        LifePathDesignation,
        LifePathRecommendation,
        LifePathStatus,
        RelationshipGraphData,
        SignInResult,
        SignUpResult,
    )
    from core.services.cross_domain_analytics_service import LearningVelocityMetrics
    from core.services.performance_types import AlertThresholds
    from core.services.user.unified_user_context import UserContext

# ============================================================================
# CALENDAR
# ============================================================================


@runtime_checkable
class CalendarServiceOperations(Protocol):
    """Calendar aggregation service operations.

    Route consumer: calendar_api.py, calendar_ui.py, visualization_api.py,
    journals_routes.py (weekly-note read panel)
    Implementation: CalendarService
    """

    async def get_calendar_view(
        self,
        user_uid: UserUID,
        start_date: date,
        end_date: date,
        view_type: "CalendarView" = ...,
        include_completed: bool = False,
    ) -> "Result[CalendarData]":
        """Get calendar view for a date range. Returns Result[CalendarData]."""
        ...

    async def get_planning_items(
        self,
        user_uid: UserUID,
        start_date: date,
        end_date: date,
    ) -> "Result[list[CalendarItem]]":
        """The range's plannable items — tasks + events + goal Milestones, no habits.

        Weekly-note read-panel producer (periodic-notes arc S3); mirrors the
        grid's due-OR-scheduled task semantics (act-from arc C2).
        """
        ...

    async def get_item(
        self, user_uid: UserUID, item_uid: str, on_date: date | None = None
    ) -> "Result[CalendarItem | None]":
        """Get a calendar item by UID, scoped to its owner. Returns Result[CalendarItem | None].

        ``on_date`` scopes a habit item to that occurrence day (day + completion
        state stamped in ``occurrence_data``); ignored for non-habit items.
        """
        ...

    async def reschedule_item(
        self,
        user_uid: UserUID,
        item_uid: str,
        new_start: datetime,
    ) -> "Result[CalendarItem]":
        """Reschedule a calendar item the user owns. Returns Result[CalendarItem]."""
        ...

    async def record_habit_occurrence(
        self,
        user_uid: UserUID,
        habit_uid: str,
        on_date: str,
        notes: str | None = None,
    ) -> "Result[HabitCompletion]":
        """Record a habit completion for the given day (verifies habit ownership)."""
        ...


# ============================================================================
# VISUALIZATION
# ============================================================================


@runtime_checkable
class VisualizationOperations(Protocol):
    """Chart.js and Gantt visualization operations.

    Route consumer: visualization_api.py
    Implementation: VisualizationAggregationService

    Async methods only — each fetches domain data and returns a formatted
    chart/gantt config. Pure formatting lives in VisualizationService
    and is not part of this protocol.

    See: core/services/analytics/visualization_aggregation_service.py
    """

    async def get_completion_chart_data(
        self,
        user_uid: UserUID,
        period: str,
    ) -> Result[ChartJsConfig]:
        """Get task completion data formatted for Chart.js."""
        ...

    async def get_priority_distribution_chart_data(
        self,
        user_uid: UserUID,
    ) -> Result[ChartJsConfig]:
        """Get task priority distribution formatted for Chart.js."""
        ...

    async def get_streak_chart_data(
        self,
        user_uid: UserUID,
    ) -> Result[ChartJsConfig]:
        """Get habit streak data formatted for Chart.js."""
        ...

    async def get_status_distribution_chart_data(
        self,
        user_uid: UserUID,
        days_back: int = 30,
    ) -> Result[ChartJsConfig]:
        """Get task status distribution formatted for Chart.js."""
        ...

    async def get_tasks_gantt_data(
        self,
        user_uid: UserUID,
        project: str | None = None,
    ) -> Result[GanttConfig]:
        """Get tasks Gantt data formatted for Frappe Gantt."""
        ...

    async def get_goal_gantt_data(
        self,
        user_uid: UserUID,
        goal_uid: str,
    ) -> Result[GanttConfig]:
        """Get goal with tasks as Gantt data formatted for Frappe Gantt."""
        ...


# ============================================================================
# SYSTEM
# ============================================================================


@runtime_checkable
class SystemServiceOperations(Protocol):
    """System health monitoring and management operations.

    Route consumer: system_api.py (primary)
    Implementation: SystemService

    Includes both async health-check methods and sync management methods.
    """

    # Async health check methods

    async def get_health_status(self) -> Result[SystemHealthStatus]:
        """Get system health status."""
        ...

    async def get_system_info(self) -> Result[SystemInfoResult]:
        """Get system version and info."""
        ...

    async def get_health_summary(self) -> Result[HealthSummaryResult]:
        """Get health summary with component counts."""
        ...

    async def validate_health_checkers(self) -> Result[HealthCheckValidation]:
        """Validate registered health checkers."""
        ...

    async def check_alerts(self) -> Result[AlertCheckResult]:
        """Check for triggered alerts."""
        ...

    # Sync management methods

    def register_component_checker(self, name: str, checker: Callable[..., Any]) -> None:
        """Register a health checker for a component."""
        ...

    def unregister_component_checker(self, name: str) -> bool:
        """Unregister a component health checker. Returns True if found."""
        ...

    def list_registered_components(self) -> list[str]:
        """List all registered component names."""
        ...

    def is_component_registered(self, name: str) -> bool:
        """Check if a component is registered."""
        ...

    def update_alert_thresholds(self, thresholds: dict[str, Any]) -> None:
        """Update alert thresholds."""
        ...

    def get_alert_thresholds(self) -> "AlertThresholds":
        """Get current alert thresholds."""
        ...


# ============================================================================
# CROSS-DOMAIN ANALYTICS
# ============================================================================


@runtime_checkable
class CrossDomainAnalyticsOperations(Protocol):
    """Event-driven cross-domain analytics operations.

    Route consumer: analytics_api.py (via services.cross_domain_analytics)
    Implementation: CrossDomainAnalyticsService
    """

    async def get_learning_velocity(
        self,
        user_uid: UserUID,
        days_back: int,
    ) -> "Result[LearningVelocityMetrics]":
        """Get learning velocity metrics. Returns Result[LearningVelocityMetrics]."""
        ...

    async def get_productivity_metrics(
        self,
        user_uid: UserUID,
    ) -> Result[dict[str, Any]]:
        """Get productivity analytics. Returns Result[dict]."""
        ...

    async def get_habit_consistency(
        self,
        user_uid: UserUID,
    ) -> Result[dict[str, Any]]:
        """Get habit consistency analytics. Returns Result[dict]."""
        ...


# ============================================================================
# LIFEPATH
# ============================================================================


@runtime_checkable
class LifePathAlignmentOperations(Protocol):
    """LifePath alignment sub-service operations.

    Accessed via lifepath_service.alignment in routes.
    Implementation: LifePathAlignmentService
    """

    async def calculate_alignment(
        self, context: "UserContext"
    ) -> "Result[LifePathAlignmentResult]":
        """Calculate life path alignment from a pre-built UserContext."""
        ...


@runtime_checkable
class LifePathOperations(Protocol):
    """LifePath domain service operations (facade).

    Route consumer: lifepath_api.py (primary), lifepath_ui.py
    Implementation: LifePathService

    Sub-service access: .alignment for alignment calculations.
    """

    alignment: LifePathAlignmentOperations

    async def get_full_status(self, user_uid: UserUID) -> "Result[LifePathStatus]":
        """Get full life path status. Returns Result[LifePathStatus]."""
        ...

    async def capture_and_recommend(
        self,
        user_uid: UserUID,
        vision_statement: str,
    ) -> "Result[LifePathRecommendation]":
        """Capture vision and get recommendations. Returns Result[LifePathRecommendation]."""
        ...

    async def designate_and_calculate(
        self,
        user_uid: UserUID,
        life_path_uid: str,
    ) -> "Result[LifePathDesignation]":
        """Designate LP as life path and calculate alignment. Returns Result[LifePathDesignation]."""
        ...

    async def get_alignment(self, user_uid: UserUID) -> "Result[LifePathAlignmentResult]":
        """Get alignment data. Builds context and delegates to alignment sub-service."""
        ...


# ============================================================================
# GRAPH AUTH
# ============================================================================


@runtime_checkable
class GraphAuthOperations(Protocol):
    """Graph-native authentication operations.

    Route consumer: auth_ui.py (primary), admin_api.py
    Implementation: GraphAuthService
    """

    async def sign_up(
        self,
        email: str,
        password: str,
        username: str,
        display_name: str | None = None,
        user_metadata: dict[str, Any] | None = None,
    ) -> "Result[SignUpResult]":
        """Register a new user. Returns Result[SignUpResult]."""
        ...

    async def sign_in(
        self,
        email: str,
        password: str,
        ip_address: str = "unknown",
        user_agent: str = "unknown",
    ) -> "Result[SignInResult]":
        """Authenticate a user. Returns Result[SignInResult]."""
        ...

    async def sign_out(
        self,
        session_token: str,
        ip_address: str = "unknown",
        user_agent: str = "unknown",
    ) -> Result[bool]:
        """End a user session. Returns Result[bool]."""
        ...

    async def reset_password_with_token(
        self,
        token_value: str,
        new_password: str,
        ip_address: str = "unknown",
        user_agent: str = "unknown",
    ) -> Result[bool]:
        """Reset password using a reset token. Returns Result[bool]."""
        ...

    async def admin_generate_reset_token(
        self,
        user_uid: UserUID,
        admin_uid: str,
        ip_address: str = "unknown",
        user_agent: str = "unknown",
    ) -> Result[str]:
        """Admin-initiated password reset token. Returns Result[str]."""
        ...

    async def reset_password_email(self, email: str) -> Result[bool]:
        """Send password reset email. Always returns ok(True) to prevent enumeration."""
        ...

    async def validate_session_uid(self, session_token: str) -> Result[str | None]:
        """Validate session token and return user UID (fast path, no user fetch)."""
        ...


@runtime_checkable
class SessionInvalidationOperations(Protocol):
    """Server-side session revocation — the kill switch for live cookies.

    Service consumer: UserService (role change, deactivation)
    Implementation: SessionBackend

    Both operations commit the privilege change AND the session sweep in one
    Cypher transaction — any two-step sequence leaves a window where a
    concurrent sign-in against the old user record dodges the sweep.
    Revocation only bites because AuthContextMiddleware validates the graph
    session once per request; see adapters/inbound/auth/context_middleware.py.
    """

    async def update_role_and_revoke_sessions(
        self, user_uid: UserUID, new_role: "UserRole"
    ) -> Result[int]:
        """Atomically persist a role change AND revoke every live session."""
        ...

    async def deactivate_user_and_revoke_sessions(self, user_uid: UserUID) -> Result[int]:
        """Atomically set the user inactive AND revoke every live session."""
        ...


# ============================================================================
# ORCHESTRATION — Goal→Task, Habit→Event
# ============================================================================


@runtime_checkable
class GoalTaskGeneratorOperations(Protocol):
    """Goal-to-Task generation operations.

    Route consumer: orchestration_routes.py (create_goal_task_routes, create_goal_task_bulk_routes)
    Implementation: GoalTaskGenerator
    """

    async def generate_tasks_for_goal(
        self,
        goal_uid: str,
        user_context: "UserContext",
        auto_create: bool = False,
    ) -> "Result[list[TaskDTO]]":
        """Generate tasks for a single goal."""
        ...

    async def generate_tasks_for_all_goals(
        self,
        user_context: "UserContext",
        auto_create: bool = False,
    ) -> "Result[dict[str, list[TaskDTO]]]":
        """Generate tasks for all active goals, skipping those already at capacity."""
        ...

    async def generate_next_critical_tasks(
        self,
        user_context: "UserContext",
        limit: int = 5,
    ) -> "Result[list[TaskDTO]]":
        """Generate the next critical tasks across all goals, prioritised by urgency."""
        ...


@runtime_checkable
class HabitEventSchedulerOperations(Protocol):
    """Habit-to-Event scheduling operations.

    Route consumer: orchestration_routes.py (create_habit_event_routes)
    Implementation: HabitEventScheduler
    """

    async def schedule_events_for_habit(
        self,
        habit_uid: str,
        user_context: "UserContext",
        auto_create: bool = False,
        days_ahead: int | None = None,
    ) -> "Result[list[EventDTO]]":
        """Schedule events for a habit."""
        ...


# ============================================================================
# LATERAL RELATIONSHIPS
# ============================================================================


@runtime_checkable
class OwnershipVerifier(Protocol):
    """Narrow protocol for ownership verification.

    The only contract lateral-relationship code needs from a domain service.
    All six Activity Domain facades satisfy this structurally via
    BaseServiceInterface[T].verify_ownership. The return type is
    Result[Any] because Result[T] is invariant — each facade returns a
    different concrete T (Task, Goal, Habit, …) and callers here only
    branch on `.is_error`. This is the single acceptable Result[Any] in a
    protocol: internal orchestrator contract, never a route return type.
    """

    async def verify_ownership(
        self, uid: str, user_uid: UserUID
    ) -> "Result[Any]": ...  # boundary: internal ownership callback — see class docstring


@runtime_checkable
class LateralRelationshipOperations(Protocol):
    """Protocol for lateral relationship service operations."""

    async def create_lateral_relationship(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: RelationshipName,
        metadata: Neo4jProperties | None = None,
        validate: bool = True,
        auto_inverse: bool = True,
        user_uid: UserUID | None = None,
        domain_service: OwnershipVerifier | None = None,
    ) -> Result[bool]: ...

    async def delete_lateral_relationship(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: RelationshipName,
        delete_inverse: bool = True,
        user_uid: UserUID | None = None,
        domain_service: OwnershipVerifier | None = None,
    ) -> Result[bool]: ...

    async def get_lateral_relationships(
        self,
        entity_uid: EntityUID,
        relationship_types: list[RelationshipName] | None = None,
        direction: str = "outgoing",
        include_metadata: bool = True,
        user_uid: UserUID | None = None,
        domain_service: OwnershipVerifier | None = None,
    ) -> "Result[list[LateralRelationshipItem]]": ...

    async def get_blocking_chain(
        self,
        entity_uid: EntityUID,
        max_depth: int = 10,
        user_uid: UserUID | None = None,
        domain_service: OwnershipVerifier | None = None,
    ) -> "Result[BlockingChainResult]": ...

    async def get_alternatives_with_comparison(
        self,
        entity_uid: EntityUID,
        user_uid: UserUID | None = None,
        domain_service: OwnershipVerifier | None = None,
    ) -> "Result[list[AlternativeComparisonItem]]": ...

    async def get_relationship_graph(
        self,
        entity_uid: EntityUID,
        depth: int = 2,
        relationship_types: list[RelationshipName] | None = None,
        user_uid: UserUID | None = None,
        domain_service: OwnershipVerifier | None = None,
    ) -> "Result[RelationshipGraphData]": ...

    async def get_siblings(
        self,
        entity_uid: EntityUID,
        include_explicit_only: bool = False,
        user_uid: UserUID | None = None,
        domain_service: OwnershipVerifier | None = None,
    ) -> Result[
        list[dict[str, Any]]
    ]: ...  # boundary: sibling rows come from multiple backend queries


@runtime_checkable
class LateralRelationshipBackendOperations(Protocol):
    """Backend-level protocol for lateral relationship Cypher queries.

    Implementation: LateralRelationshipBackend in backends/collab_backends.py.
    Consumer: LateralRelationshipService.

    Stable query returns are typed with TypedDicts from query_types.py.
    CRUD operations and validation checks remain as dict[str, Any] with
    inline boundary comments.
    """

    async def create_relationship(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: RelationshipName,
        metadata: dict[str, Any],
        created_at: str,
    ) -> Result[list[dict[str, Any]]]: ...  # boundary: returns relationship properties

    async def delete_relationship(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: RelationshipName,
    ) -> Result[list[dict[str, Any]]]: ...  # boundary: returns {deleted_count}

    async def create_inverse(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: RelationshipName,
        metadata: dict[str, Any],
        created_at: str,
    ) -> Result[list[dict[str, Any]]]: ...  # boundary: no RETURN clause

    async def delete_inverse(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: RelationshipName,
    ) -> Result[list[dict[str, Any]]]: ...  # boundary: no RETURN clause

    async def get_relationships(
        self,
        entity_uid: EntityUID,
        type_filter: str,
        pattern: str,
    ) -> Result[list[LateralRelationshipRow]]: ...

    async def get_siblings(self, entity_uid: EntityUID) -> Result[list[SiblingRow]]: ...

    async def get_cousins(self, entity_uid: EntityUID) -> Result[list[CousinRow]]: ...

    async def get_blocking_chain(self, entity_uid: EntityUID) -> Result[list[BlockingChainRow]]: ...

    async def get_alternatives_comparison(
        self, entity_uid: EntityUID
    ) -> Result[list[dict[str, Any]]]: ...  # boundary: raw ALTERNATIVE_TO comparison rows

    async def get_relationship_graph(
        self,
        entity_uid: EntityUID,
        type_filter: str,
        depth: int,
    ) -> Result[list[RelationshipGraphRow]]: ...

    async def check_entities_exist(
        self, source_uid: str, target_uid: str
    ) -> Result[list[dict[str, Any]]]: ...  # boundary: returns {source_count, target_count}

    async def check_same_parent(
        self, source_uid: str, target_uid: str
    ) -> Result[list[dict[str, Any]]]: ...  # boundary: returns {shared_parent_count}

    async def check_same_depth(
        self, source_uid: str, target_uid: str
    ) -> Result[list[dict[str, Any]]]: ...  # boundary: returns {source_depth, target_depth}

    async def check_no_cycles(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: RelationshipName,
    ) -> Result[list[dict[str, Any]]]: ...  # boundary: returns {cycle_count}
