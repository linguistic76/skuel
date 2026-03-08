"""
Route-Facing Service Protocols
================================

Protocols for cross-cutting and infrastructure services that are
directly consumed by route files. ISP-compliant: each protocol
captures only the methods called from routes.

Protocols:
- CalendarServiceOperations — Calendar aggregation
- VisualizationOperations — Chart.js/Vis.js/Gantt formatting
- SystemServiceOperations — Health checks and monitoring
- CrossDomainAnalyticsOperations — Event-driven analytics
- LifePathOperations — Vision-to-action bridge
- GraphAuthOperations — Graph-native authentication
- GoalTaskGeneratorOperations — Goal→Task generation
- HabitEventSchedulerOperations — Habit→Event scheduling
- LateralRelationshipOperations — Lateral relationship CRUD + graph queries
"""

from collections.abc import Callable
from datetime import date, datetime
from typing import Any, Literal, Protocol, runtime_checkable

from core.models.relationship_names import RelationshipName
from core.ports.context_awareness_protocols import FullAwareness
from core.utils.result_simplified import Result

# ============================================================================
# CALENDAR
# ============================================================================


@runtime_checkable
class CalendarServiceOperations(Protocol):
    """Calendar aggregation service operations.

    Route consumer: calendar_api.py, calendar_ui.py, visualization_api.py
    Implementation: CalendarService
    """

    async def get_calendar_view(
        self,
        user_uid: str,
        start_date: date,
        end_date: date,
        view_type: Any = ...,
        include_completed: bool = False,
    ) -> Result[Any]:
        """Get calendar view for a date range. Returns Result[CalendarData]."""
        ...

    async def get_item(self, item_uid: str) -> Result[Any | None]:
        """Get a calendar item by UID. Returns Result[CalendarItem | None]."""
        ...

    async def quick_create(
        self,
        item_type: str,
        title: str,
        start_time: datetime,
        **kwargs: Any,
    ) -> Result[Any]:
        """Quick-create a calendar item. Returns Result[CalendarItem]."""
        ...

    async def reschedule_item(
        self,
        item_uid: str,
        new_start: datetime,
    ) -> Result[Any]:
        """Reschedule a calendar item. Returns Result[CalendarItem]."""
        ...


# ============================================================================
# VISUALIZATION
# ============================================================================


@runtime_checkable
class VisualizationOperations(Protocol):
    """Chart.js, Vis.js, and Gantt visualization operations.

    Route consumer: visualization_api.py
    Implementation: VisualizationService

    Includes both async data-fetching methods and sync formatting methods,
    since routes call both.
    """

    # Async data-fetching methods

    async def get_completion_data(
        self,
        user_uid: str,
        period: str,
        tasks_service: Any,
    ) -> Result[dict[str, Any]]:
        """Get task completion rate data. Returns Result[dict]."""
        ...

    async def get_priority_distribution_data(
        self,
        user_uid: str,
        tasks_service: Any,
    ) -> Result[dict[str, int]]:
        """Get task priority distribution. Returns Result[dict]."""
        ...

    async def get_streak_data(
        self,
        user_uid: str,
        habits_service: Any,
    ) -> Result[list[dict[str, Any]]]:
        """Get habit streak data. Returns Result[list[dict]]."""
        ...

    async def get_status_distribution_data(
        self,
        user_uid: str,
        tasks_service: Any,
        days_back: int = 30,
    ) -> Result[dict[str, int]]:
        """Get task status distribution. Returns Result[dict]."""
        ...

    # Sync formatting methods (Chart.js)

    def format_completion_chart(
        self,
        completed: list[int],
        total: list[int],
        labels: list[str],
        chart_type: Literal["line", "bar"] = "line",
    ) -> Result[dict[str, Any]]:
        """Format completion data for Chart.js. Returns Result[dict]."""
        ...

    def format_distribution_chart(
        self,
        data: dict[str, int],
        title: str = "Distribution",
        chart_type: Literal["pie", "doughnut", "bar"] = "doughnut",
    ) -> Result[dict[str, Any]]:
        """Format distribution data for Chart.js. Returns Result[dict]."""
        ...

    def format_streak_chart(
        self,
        streaks: list[dict[str, Any]],
    ) -> Result[dict[str, Any]]:
        """Format streak data for Chart.js. Returns Result[dict]."""
        ...

    # Sync formatting methods (Vis.js + Gantt)

    def format_for_visjs(
        self,
        calendar_data: Any,
        group_by: Literal["type", "project", "none"] = "type",
    ) -> Result[dict[str, Any]]:
        """Format calendar data for Vis.js timeline. Returns Result[dict]."""
        ...

    def format_tasks_for_visjs(
        self,
        tasks: list[Any],
        show_deadlines: bool = True,
    ) -> Result[dict[str, Any]]:
        """Format tasks for Vis.js timeline. Returns Result[dict]."""
        ...

    def format_for_gantt(
        self,
        tasks: list[Any],
        dependencies: dict[str, list[str]] | None = None,
    ) -> Result[dict[str, Any]]:
        """Format tasks for Frappe Gantt. Returns Result[dict]."""
        ...

    def format_goal_gantt(
        self,
        goal: Any,
        tasks: list[Any],
        milestones: list[dict[str, Any]] | None = None,
    ) -> Result[dict[str, Any]]:
        """Format goal with tasks for Gantt. Returns Result[dict]."""
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

    async def get_health_status(self) -> Result[Any]:
        """Get system health status. Returns Result[SystemHealthStatus]."""
        ...

    async def get_system_info(self) -> Result[dict[str, Any]]:
        """Get system version and info. Returns Result[dict]."""
        ...

    async def get_health_summary(self) -> Result[dict[str, Any]]:
        """Get health summary with component counts. Returns Result[dict]."""
        ...

    async def validate_health_checkers(self) -> Result[Any]:
        """Validate registered health checkers. Returns Result[HealthCheckValidation]."""
        ...

    async def check_alerts(self) -> Result[dict[str, Any]]:
        """Check for triggered alerts. Returns Result[dict]."""
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

    def get_alert_thresholds(self) -> Any:
        """Get current alert thresholds. Returns AlertThresholds."""
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
        user_uid: str,
        days_back: int,
    ) -> Result[Any]:
        """Get learning velocity metrics. Returns Result[LearningVelocityMetrics]."""
        ...

    async def get_spending_patterns(
        self,
        user_uid: str,
        days_back: int,
    ) -> Result[Any]:
        """Get spending pattern analysis. Returns Result[SpendingPatternAnalysis]."""
        ...

    async def get_mood_analysis(
        self,
        user_uid: str,
        days_back: int,
    ) -> Result[Any]:
        """Get journal mood analysis. Returns Result[JournalMoodAnalysis]."""
        ...

    async def get_productivity_metrics(
        self,
        user_uid: str,
    ) -> Result[dict[str, Any]]:
        """Get productivity analytics. Returns Result[dict]."""
        ...

    async def get_habit_consistency(
        self,
        user_uid: str,
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

    async def calculate_alignment(self, context: Any) -> Result[Any]:
        """Calculate life path alignment. Accepts pre-built UserContext."""
        ...


@runtime_checkable
class LifePathOperations(Protocol):
    """LifePath domain service operations (facade).

    Route consumer: lifepath_api.py (primary), lifepath_ui.py
    Implementation: LifePathService

    Sub-service access: .alignment for alignment calculations.
    """

    alignment: LifePathAlignmentOperations

    async def get_full_status(self, user_uid: str) -> Result[dict[str, Any]]:
        """Get full life path status. Returns Result[dict]."""
        ...

    async def capture_and_recommend(
        self,
        user_uid: str,
        vision_statement: str,
    ) -> Result[dict[str, Any]]:
        """Capture vision and get recommendations. Returns Result[dict]."""
        ...

    async def designate_and_calculate(
        self,
        user_uid: str,
        life_path_uid: str,
    ) -> Result[dict[str, Any]]:
        """Designate LP as life path and calculate alignment. Returns Result[dict]."""
        ...

    async def get_alignment(self, user_uid: str) -> Result[dict[str, Any]]:
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
    ) -> Result[dict[str, Any]]:
        """Register a new user. Returns Result[dict]."""
        ...

    async def sign_in(
        self,
        email: str,
        password: str,
        ip_address: str = "unknown",
        user_agent: str = "unknown",
    ) -> Result[dict[str, Any]]:
        """Authenticate a user. Returns Result[dict]."""
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
        user_uid: str,
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


# ============================================================================
# ORCHESTRATION — Goal→Task, Habit→Event
# ============================================================================


@runtime_checkable
class GoalTaskGeneratorOperations(Protocol):
    """Goal-to-Task generation operations.

    Route consumer: orchestration_routes.py (create_goal_task_routes)
    Implementation: GoalTaskGenerator
    """

    async def generate_tasks_for_goal(
        self,
        goal_uid: str,
        user_context: FullAwareness,
        auto_create: bool = False,
    ) -> Result[Any]:
        """Generate tasks for a goal. Returns Result[list[TaskDTO]]."""
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
        user_context: FullAwareness,
        auto_create: bool = False,
        days_ahead: int | None = None,
    ) -> Result[Any]:
        """Schedule events for a habit. Returns Result[list[EventDTO]]."""
        ...


# ============================================================================
# LATERAL RELATIONSHIPS
# ============================================================================


@runtime_checkable
class LateralRelationshipOperations(Protocol):
    """Protocol for lateral relationship service operations."""

    async def create_lateral_relationship(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: RelationshipName,
        metadata: dict[str, Any] | None = None,
        validate: bool = True,
        auto_inverse: bool = True,
        user_uid: str | None = None,
        domain_service: Any | None = None,
    ) -> Result[bool]: ...

    async def delete_lateral_relationship(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: RelationshipName,
        delete_inverse: bool = True,
        user_uid: str | None = None,
        domain_service: Any | None = None,
    ) -> Result[bool]: ...

    async def get_lateral_relationships(
        self,
        entity_uid: str,
        relationship_types: list[RelationshipName] | None = None,
        direction: str = "outgoing",
        include_metadata: bool = True,
        user_uid: str | None = None,
        domain_service: Any | None = None,
    ) -> Result[list[dict[str, Any]]]: ...

    async def get_blocking_chain(
        self, entity_uid: str, max_depth: int = 10
    ) -> Result[dict[str, Any]]: ...

    async def get_alternatives_with_comparison(
        self, entity_uid: str, comparison_fields: list[str] | None = None
    ) -> Result[list[dict[str, Any]]]: ...

    async def get_relationship_graph(
        self,
        entity_uid: str,
        depth: int = 2,
        relationship_types: list[RelationshipName] | None = None,
    ) -> Result[dict[str, Any]]: ...
