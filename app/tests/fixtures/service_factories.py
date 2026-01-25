"""
Test Service Factory Functions
================================

Mirrors production service composition with test-friendly behavior customization.

Design Philosophy:
- Services create sub-components internally (encapsulation)
- Tests should use same constructor as production (consistency)
- Factory functions provide mock backends/drivers (testing)
- Behavior can be customized without breaking encapsulation (flexibility)

Pattern:
    # Production
    service = MOCService(backend=backend, driver=driver)

    # Tests
    service = create_moc_service_for_testing(
        section_behavior={"add_section": Result.ok(section)}
    )

This ensures tests stay in sync with production composition while
maintaining the ability to mock specific behaviors for testing.

Migration Notes (November 8, 2025):
- Implements Option C from TEST_LEARNING_SUMMARY.md
- Replaces pattern of injecting mock sub-services
- Aligns with SKUEL fail-fast philosophy
- First implementation targets MOC service (26 failing tests)
"""

from typing import Any
from unittest.mock import AsyncMock, Mock

from core.utils.result_simplified import Result

# ============================================================================
# MOCK HELPERS - Reusable mock creation
# ============================================================================


def create_mock_backend(behavior: dict[str, Any] | None = None) -> Mock:
    """
    Create a mock backend with standard CRUD methods.

    Args:
        behavior: Optional dict mapping method names to return values
                  Example: {"get": Result.ok(entity), "create": Result.ok(entity)}

    Returns:
        Mock backend with AsyncMock methods for CRUD operations
    """
    backend = Mock()

    # Standard CRUD methods (all async)
    backend.create = AsyncMock(return_value=Result.ok(Mock()))
    backend.get = AsyncMock(return_value=Result.ok(Mock()))
    backend.update = AsyncMock(return_value=Result.ok(Mock()))
    backend.delete = AsyncMock(return_value=Result.ok(True))
    backend.list_by_user = AsyncMock(return_value=Result.ok([]))
    backend.list_by_domain = AsyncMock(return_value=Result.ok([]))
    backend.find_by = AsyncMock(return_value=Result.ok([]))
    backend.get_stats = AsyncMock(return_value=Result.ok(Mock()))

    # Apply custom behavior if provided
    if behavior:
        for method_name, return_value in behavior.items():
            if hasattr(backend, method_name):
                getattr(backend, method_name).return_value = return_value
            else:
                setattr(backend, method_name, AsyncMock(return_value=return_value))

    return backend


def create_mock_driver(behavior: dict[str, Any] | None = None) -> Mock:
    """
    Create a mock Neo4j driver.

    Args:
        behavior: Optional dict mapping method names to return values

    Returns:
        Mock driver with session context manager
    """
    driver = Mock()

    # Mock session context manager
    mock_session = Mock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.run = AsyncMock(return_value=[])

    driver.session = Mock(return_value=mock_session)

    # Apply custom behavior if provided
    if behavior:
        for method_name, return_value in behavior.items():
            setattr(driver, method_name, Mock(return_value=return_value))

    return driver


# ============================================================================
# SERVICE FACTORIES - One per service
# ============================================================================


def create_moc_service_for_testing(
    backend: Mock | None = None,
    driver: Mock | None = None,
    backend_behavior: dict[str, Any] | None = None,
    driver_behavior: dict[str, Any] | None = None,
) -> Any:  # Returns MOCService
    """
    Create MOCService instance for testing using production composition pattern.

    This factory mirrors how MOCService is created in production:
    - Accepts backend and driver (external dependencies)
    - Service creates sub-services internally (section, core, content, etc.)

    Args:
        backend: Optional mock backend (created if not provided)
        driver: Optional mock driver (created if not provided)
        backend_behavior: Optional behavior customization for backend
                         Example: {"get": Result.ok(moc), "create": Result.ok(moc)}
        driver_behavior: Optional behavior customization for driver

    Returns:
        MOCService instance with mocked dependencies

    Usage:
        # Simple: Use defaults
        service = create_moc_service_for_testing()

        # Custom backend behavior
        service = create_moc_service_for_testing(
            backend_behavior={"get": Result.ok(my_moc)}
        )

        # Full control
        my_backend = create_mock_backend({"create": Result.ok(moc)})
        service = create_moc_service_for_testing(backend=my_backend)

    Notes:
        - Sub-services (section, core, content, discovery, template) are
          created internally by MOCService.__init__
        - To customize sub-service behavior, access via service.section,
          service.core, etc. after creation
        - This pattern maintains encapsulation while enabling testing
    """
    from core.services.moc_service import MOCService

    # Create mocks if not provided
    if backend is None:
        backend = create_mock_backend(backend_behavior)
    if driver is None:
        driver = create_mock_driver(driver_behavior)

    # Create service using production pattern
    # MOCService.__init__ creates sub-services internally
    return MOCService(backend=backend, driver=driver)


def create_unified_user_context_for_testing(
    user_uid: str = "test_user",
    username: str = "testuser",
    email: str = "test@example.com",
    **kwargs: Any,
) -> Any:  # Returns UserContext
    """
    Create UserContext instance for testing with sensible defaults.

    Args:
        user_uid: User unique identifier
        username: Username
        email: User email
        **kwargs: Additional fields to override defaults

    Returns:
        UserContext instance

    Usage:
        # Simple: Use defaults
        context = create_unified_user_context_for_testing()

        # Custom fields
        context = create_unified_user_context_for_testing(
            user_uid="user_123",
            active_task_uids=["task_1", "task_2"]
        )

    Notes:
        - UserContext is a dataclass with many optional fields
        - This factory provides sensible defaults for testing
        - Override any field via kwargs
    """
    from core.services.user import UserContext

    # Create context with provided fields
    # UserContext has defaults for most fields
    return UserContext(user_uid=user_uid, username=username, email=email, **kwargs)


def create_finance_service_for_testing(
    backend: Mock | None = None,
    driver: Mock | None = None,
    graph_intelligence: Mock | None = None,
    event_bus: Mock | None = None,
    backend_behavior: dict[str, Any] | None = None,
) -> Any:  # Returns FinanceService
    """
    Create FinanceService instance for testing using production composition pattern.

    Args:
        backend: Optional mock backend (created if not provided)
        driver: Optional mock driver (for graph operations)
        graph_intelligence: Optional mock graph intelligence service
        event_bus: Optional mock event bus
        backend_behavior: Optional behavior customization for backend

    Returns:
        FinanceService instance with mocked dependencies

    Usage:
        # Simple: Use defaults
        service = create_finance_service_for_testing()

        # Custom backend behavior
        service = create_finance_service_for_testing(
            backend_behavior={"get": Result.ok(expense)}
        )

    Notes:
        - FinanceService may have sub-components created internally
        - Event bus is optional (can be None for testing)
        - Graph intelligence is optional (can be None for testing)
    """
    from core.services.finance_service import FinanceService

    # Create mocks if not provided
    if backend is None:
        backend = create_mock_backend(backend_behavior)

    # Create service using production pattern
    # Note: FinanceService may create sub-components internally
    return FinanceService(
        backend=backend,
        graph_intelligence_service=graph_intelligence,
        event_bus=event_bus,
    )


def create_tasks_service_for_testing(
    backend: Mock | None = None,
    ku_inference_service: Mock | None = None,
    analytics_engine: Mock | None = None,
    ku_generation_service: Mock | None = None,
    graph_intelligence_service: Mock | None = None,
    event_bus: Mock | None = None,
    backend_behavior: dict[str, Any] | None = None,
) -> Any:  # Returns TasksService
    """
    Create TasksService instance for testing using production composition pattern.

    Args:
        backend: Optional mock backend (created if not provided)
        ku_inference_service: Optional KU inference service
        analytics_engine: Optional analytics engine
        ku_generation_service: Optional KU generation service
        graph_intelligence_service: Optional graph intelligence service
        event_bus: Optional event bus
        backend_behavior: Optional behavior customization for backend

    Returns:
        TasksService instance with mocked dependencies

    Usage:
        # Simple: Use defaults (all optional services are None)
        service = create_tasks_service_for_testing()

        # Custom backend behavior
        service = create_tasks_service_for_testing(
            backend_behavior={"get": Result.ok(task)}
        )

    Notes:
        - TasksService has many optional intelligence services
        - For unit tests, leaving these as None is fine
        - For integration tests, provide real or more complete mocks
    """
    from core.services.tasks_service import TasksService

    # Create backend if not provided
    if backend is None:
        backend = create_mock_backend(backend_behavior)

    # Create service using production pattern
    return TasksService(
        backend=backend,
        ku_inference_service=ku_inference_service,
        analytics_engine=analytics_engine,
        ku_generation_service=ku_generation_service,
        graph_intelligence_service=graph_intelligence_service,
        event_bus=event_bus,
    )


# ============================================================================
# FUTURE: Add more service factories as tests are migrated
# ============================================================================

# def create_habits_service_for_testing(...):
#     """Create HabitsService for testing."""

# def create_events_service_for_testing(...):
#     """Create EventsService for testing."""

# def create_goals_service_for_testing(...):
#     """Create GoalsService for testing."""

# def create_journals_service_for_testing(...):
#     """Create JournalsService for testing."""

# def create_knowledge_service_for_testing(...):
#     """Create KnowledgeService (KuService) for testing."""

# def create_learning_service_for_testing(...):
#     """Create LearningService (LpIntelligenceService) for testing."""


# ============================================================================
# BASE SERVICE TESTING SUPPORT (January 2026)
# ============================================================================


def create_mock_backend_for_base_service(
    behavior: dict[str, Any] | None = None,
) -> Mock:
    """
    Create comprehensive mock backend for BaseService testing.

    Mocks all BackendOperations protocol methods including:
    - CRUD operations
    - Search operations
    - Relationship operations
    - Graph traversal

    Args:
        behavior: Optional dict mapping method names to return values

    Returns:
        Mock backend with all BackendOperations methods
    """
    from neo4j import EagerResult

    backend = Mock()

    # CRUD operations
    backend.create = AsyncMock(return_value=Result.ok({"uid": "test_001"}))
    backend.get = AsyncMock(return_value=Result.ok({"uid": "test_001", "title": "Test Entity"}))
    backend.update = AsyncMock(return_value=Result.ok({"uid": "test_001"}))
    backend.delete = AsyncMock(return_value=Result.ok(True))
    backend.list = AsyncMock(return_value=Result.ok(([], 0)))
    backend.get_many = AsyncMock(return_value=Result.ok([]))

    # Search operations
    backend.find_by = AsyncMock(return_value=Result.ok([]))
    backend.search = AsyncMock(return_value=Result.ok([]))
    backend.count = AsyncMock(return_value=Result.ok(0))

    # Relationship operations
    backend.add_relationship = AsyncMock(return_value=Result.ok(True))
    backend.delete_relationship = AsyncMock(return_value=Result.ok(True))
    backend.get_related = AsyncMock(return_value=Result.ok([]))
    backend.count_related = AsyncMock(return_value=Result.ok(0))
    backend.get_related_uids = AsyncMock(return_value=Result.ok([]))

    # Graph traversal
    backend.traverse = AsyncMock(return_value=Result.ok([]))
    backend.get_domain_context_raw = AsyncMock(return_value=Result.ok({}))

    # Low-level operations
    mock_driver = Mock()
    mock_driver.execute_query = AsyncMock(
        return_value=EagerResult(records=[], summary=None, keys=[])
    )
    backend.driver = mock_driver
    backend.execute_query = AsyncMock(return_value=EagerResult(records=[], summary=None, keys=[]))
    backend.health_check = AsyncMock(return_value=Result.ok(True))

    # Apply custom behavior if provided
    if behavior:
        for method_name, return_value in behavior.items():
            if hasattr(backend, method_name):
                getattr(backend, method_name).return_value = return_value
            else:
                setattr(backend, method_name, AsyncMock(return_value=return_value))

    return backend


def create_knowledge_state_for_testing(
    mastered: set[str] | None = None,
    in_progress: set[str] | None = None,
    gaps: list[str] | None = None,
    **kwargs: Any,
) -> Any:  # Returns KnowledgeState
    """
    Create KnowledgeState for adaptive_lp testing.

    Args:
        mastered: Set of mastered KU UIDs
        in_progress: Set of in-progress KU UIDs
        gaps: List of knowledge gap identifiers
        **kwargs: Additional fields to override

    Returns:
        KnowledgeState instance
    """
    from core.services.adaptive_lp_types import KnowledgeState

    return KnowledgeState(
        mastered_knowledge=mastered or {"ku.python-basics"},
        in_progress_knowledge=in_progress or set(),
        applied_knowledge=kwargs.get("applied", set()),
        knowledge_strengths=kwargs.get("strengths", {}),
        knowledge_gaps=gaps or [],
        mastery_levels=kwargs.get("mastery_levels", {"ku.python-basics": 0.8}),
        learning_velocity=kwargs.get("learning_velocity", 1.0),
    )


def create_adaptive_lp_facade_for_testing(
    ku_service: Mock | None = None,
    learning_service: Mock | None = None,
    goals_service: Mock | None = None,
    tasks_service: Mock | None = None,
) -> Any:  # Returns AdaptiveLpFacade
    """
    Create AdaptiveLpFacade for testing.

    Args:
        ku_service: Mock KU service
        learning_service: Mock learning service
        goals_service: Mock goals service
        tasks_service: Mock tasks service

    Returns:
        AdaptiveLpFacade instance with mocked dependencies
    """
    from core.services.adaptive_lp import AdaptiveLpFacade

    return AdaptiveLpFacade(
        ku_service=ku_service,
        learning_service=learning_service,
        goals_service=goals_service,
        tasks_service=tasks_service,
    )


def create_askesis_user_context_for_testing(
    user_uid: str = "test_user",
    **kwargs: Any,
) -> Any:  # Returns UserContext with Askesis-relevant fields
    """
    Create UserContext with Askesis-relevant fields populated.

    Args:
        user_uid: User identifier
        **kwargs: Override specific fields

    Returns:
        UserContext with rich data for Askesis testing
    """
    from core.services.user import UserContext

    defaults = {
        "user_uid": user_uid,
        "username": "testuser",
        "email": "test@example.com",
        # Activity data
        "active_task_count": kwargs.get("active_task_count", 5),
        "tasks_completed_30d": kwargs.get("tasks_completed_30d", 10),
        "tasks_overdue": kwargs.get("tasks_overdue", 1),
        # Habit data
        "active_habit_count": kwargs.get("active_habit_count", 3),
        "habits_at_risk": kwargs.get("habits_at_risk", 0),
        "average_habit_streak": kwargs.get("average_habit_streak", 7),
        # Goal data
        "active_goal_count": kwargs.get("active_goal_count", 2),
        # Knowledge data
        "mastered_knowledge_count": kwargs.get("mastered_knowledge_count", 5),
        "learning_velocity": kwargs.get("learning_velocity", 1.0),
        # Workload
        "current_workload": kwargs.get("current_workload", 0.6),
    }
    defaults.update(kwargs)

    return UserContext(**defaults)


# ============================================================================
# MIGRATION NOTES
# ============================================================================

"""
Service Factory Migration Checklist:

Phase 1: MOC (26 failures) ✅ IN PROGRESS
- [x] Create create_moc_service_for_testing()
- [ ] Update tests/test_moc_service.py to use factory
- [ ] Run tests: poetry run pytest tests/test_moc_service.py -v
- [ ] Validate: 26 failures → 0 failures

Phase 2: UserContext (6 failures)
- [x] Create create_unified_user_context_for_testing()
- [ ] Update tests/test_type_system.py
- [ ] Run tests: poetry run pytest tests/test_type_system.py -v
- [ ] Validate: 6 failures → 0 failures

Phase 3: Finance (multiple failures)
- [x] Create create_finance_service_for_testing()
- [ ] Update tests/test_finance_service.py
- [ ] Run tests: poetry run pytest tests/test_finance_service.py -v
- [ ] Validate failures resolved

Phase 4: Tasks (assertion failures)
- [x] Create create_tasks_service_for_testing()
- [ ] Update tests/test_tasks_service.py
- [ ] Run tests: poetry run pytest tests/test_tasks_service.py -v
- [ ] Validate failures resolved

Phase 5: Other services (as needed)
- [ ] Add factories for remaining services
- [ ] Migrate tests incrementally
- [ ] Track progress: 92% → 95% → 98% → 100%

Success Criteria:
- All service creation uses factory pattern
- Tests mirror production composition
- No direct service construction with mocks
- Clear, reusable test infrastructure
"""
