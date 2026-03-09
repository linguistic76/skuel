# Factory Pattern

## Overview

`UserContextIntelligenceFactory` separates **service wiring** (at bootstrap) from **context binding** (at runtime). This pattern is essential because:

1. The 13 domain services are **singletons** (created once at bootstrap)
2. `UserContext` is **user-specific** and built on-demand
3. `UserContextIntelligence` requires **both** at construction

```
Bootstrap (once)          Runtime (per request)
      │                         │
      ▼                         ▼
   Factory                   Context
      │                         │
      └─────────┬───────────────┘
                │
                ▼
    UserContextIntelligence
```

---

## Why Factory Pattern?

### Without Factory (Problematic)

```python
# WRONG - services must be passed every time
async def get_daily_plan(user_uid: str):
    context = await user_service.get_user_context(user_uid)

    # Where do these 13 services come from?
    intelligence = UserContextIntelligence(
        context=context,
        tasks=???,        # Need to access global services
        goals=???,        # Coupling to bootstrap
        habits=???,       # Hard to test
        # ... 10 more
    )

    return await intelligence.get_ready_to_work_on_today()
```

### With Factory (Clean)

```python
# CORRECT - factory holds services, runtime provides context
async def get_daily_plan(user_uid: str):
    context = await user_service.get_user_context(user_uid)

    # Factory already has the 13 services
    intelligence = factory.create(context)

    return await intelligence.get_ready_to_work_on_today()
```

---

## Factory Implementation

### Full Signature

```python
class UserContextIntelligenceFactory:
    def __init__(
        self,
        # Activity (6)
        tasks: UnifiedRelationshipService,
        goals: UnifiedRelationshipService,
        habits: UnifiedRelationshipService,
        events: UnifiedRelationshipService,
        choices: UnifiedRelationshipService,
        principles: UnifiedRelationshipService,
        # Curriculum (3)
        ku: KuGraphService,
        ls: UnifiedRelationshipService,
        lp: UnifiedRelationshipService,
        # Processing (3)
        submissions: SubmissionsRelationshipService,
        report: ReportRelationshipService,
        analytics: AnalyticsRelationshipService,
        # Temporal Domain (1)
        calendar: CalendarService,
        # Optional: Vector search for semantic enhancements
        vector_search_service: Any = None,
        # Optional: ZPD service for curriculum-graph-aware step ranking (FULL tier only)
        zpd_service: ZPDOperations | None = None,
    ) -> None:
        # Validate all 13 required services present
        required = {
            "tasks": tasks,
            "goals": goals,
            "habits": habits,
            "events": events,
            "choices": choices,
            "principles": principles,
            "ku": ku,
            "ls": ls,
            "lp": lp,
            "submissions": submissions,
            "report": report,
            "analytics": analytics,
            "calendar": calendar,
        }

        missing = [name for name, svc in required.items() if svc is None]
        if missing:
            raise ValueError(
                f"UserContextIntelligenceFactory requires all 13 services. "
                f"Missing: {', '.join(missing)}"
            )

        # Store services with _ prefix (internal)
        self._tasks = tasks
        self._goals = goals
        self._habits = habits
        self._events = events
        self._choices = choices
        self._principles = principles
        self._ku = ku
        self._ls = ls
        self._lp = lp
        # Processing domains (3)
        self._submissions = submissions
        self._report = report
        self._analytics = analytics
        # Temporal domain (1)
        self._calendar = calendar
        # Optional services
        self._vector_search = vector_search_service
        self._zpd_service = zpd_service

    def create(self, context: UserContext) -> UserContextIntelligence:
        """Create intelligence instance bound to user context."""
        return UserContextIntelligence(
            context=context,
            # Activity (6)
            tasks=self._tasks,
            goals=self._goals,
            habits=self._habits,
            events=self._events,
            choices=self._choices,
            principles=self._principles,
            # Curriculum (3)
            ku=self._ku,
            ls=self._ls,
            lp=self._lp,
            # Processing domains (3)
            submissions=self._submissions,
            report=self._report,
            analytics=self._analytics,
            # Temporal domain (1)
            calendar=self._calendar,
            # Optional services
            vector_search=self._vector_search,
            zpd_service=self._zpd_service,
        )
```

---

## Bootstrap Wiring

### In services_bootstrap.py

```python
from core.services.user.intelligence import UserContextIntelligenceFactory

async def compose_services(neo4j_driver, event_bus=None) -> Result[Services]:
    # ... create all domain services ...

    # Create factory with relationship services from facades
    context_intelligence_factory = UserContextIntelligenceFactory(
        # Activity (6) - from facade .relationships
        tasks=tasks_service.relationships,
        goals=goals_service.relationships,
        habits=habits_service.relationships,
        events=events_service.relationships,
        choices=choices_service.relationships,
        principles=principles_service.relationships,
        # Curriculum (3)
        ku=ku_service.graph,           # KuGraphService
        ls=ls_service.relationships,   # UnifiedRelationshipService
        lp=lp_service.relationships,   # UnifiedRelationshipService
        # Processing (3)
        submissions=submissions_relationship_service,
        report=report_relationship_service,
        analytics=analytics_relationship_service,
        # Temporal Domain (1)
        calendar=calendar_service,
        # Optional: ZPD service (FULL tier only — set to None in CORE tier)
        zpd_service=zpd_service,  # ZPDOperations | None
    )

    return Result.ok(Services(
        # ... other services ...
        context_intelligence=context_intelligence_factory,
    ))
```

### In Services Dataclass

```python
@dataclass
class Services:
    # ... other services ...
    context_intelligence: UserContextIntelligenceFactory
```

---

## Runtime Usage

### In Route Handlers

```python
@rt("/api/daily-plan")
@boundary_handler()
async def get_daily_plan(request):
    user_uid = require_authenticated_user(request)

    # Get fresh context for this user
    context = await services.user.get_user_context(user_uid)

    # Factory creates intelligence bound to context
    intelligence = services.context_intelligence.create(context)

    # Use the flagship method
    return await intelligence.get_ready_to_work_on_today()
```

### In Service Methods

```python
class DashboardService:
    def __init__(
        self,
        user_service: UserService,
        intelligence_factory: UserContextIntelligenceFactory,
    ):
        self.user_service = user_service
        self.intelligence_factory = intelligence_factory

    async def get_user_dashboard(self, user_uid: str) -> Result[dict]:
        # Get context
        context = await self.user_service.get_user_context(user_uid)

        # Create intelligence
        intelligence = self.intelligence_factory.create(context)

        # Gather all dashboard data
        plan = await intelligence.get_ready_to_work_on_today()
        alignment = await intelligence.calculate_life_path_alignment()
        synergies = await intelligence.get_cross_domain_synergies()

        return Result.ok({
            "plan": plan.value if plan.is_ok else None,
            "alignment": alignment.value if alignment.is_ok else None,
            "synergies": synergies.value if synergies.is_ok else [],
        })
```

---

## Testing with Factory

### Mocking the Factory

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

from core.services.user.intelligence import (
    UserContextIntelligenceFactory,
    UserContextIntelligence,
    DailyWorkPlan,
)


@pytest.fixture
def mock_factory():
    """Create factory with mock services."""
    return UserContextIntelligenceFactory(
        tasks=MagicMock(),
        goals=MagicMock(),
        habits=MagicMock(),
        events=MagicMock(),
        choices=MagicMock(),
        principles=MagicMock(),
        ku=MagicMock(),
        ls=MagicMock(),
        lp=MagicMock(),
        submissions=MagicMock(),
        report=MagicMock(),
        analytics=MagicMock(),
        calendar=MagicMock(),
    )


@pytest.fixture
def mock_context():
    """Create mock UserContext."""
    context = MagicMock()
    context.user_uid = "user.test"
    context.available_minutes_daily = 480
    context.daily_habits = ["habit-1", "habit-2"]
    context.active_habit_uids = ["habit-1", "habit-2", "habit-3"]
    context.upcoming_event_uids = ["event-1"]
    context.learning_goals = ["goal-1"]
    context.life_path_uid = "lp.life-path"
    return context


async def test_factory_creates_intelligence(mock_factory, mock_context):
    """Test factory creates valid intelligence instance."""
    intelligence = mock_factory.create(mock_context)

    assert isinstance(intelligence, UserContextIntelligence)
    assert intelligence.context == mock_context


async def test_intelligence_uses_services(mock_factory, mock_context):
    """Test intelligence uses injected services."""
    # Setup mock responses
    mock_factory._habits.get_at_risk_habits_for_user = AsyncMock(
        return_value=Result.ok([])
    )
    mock_factory._events.get_upcoming_events_for_user = AsyncMock(
        return_value=Result.ok([])
    )
    mock_factory._tasks.get_actionable_tasks_for_user = AsyncMock(
        return_value=Result.ok([])
    )
    mock_factory._goals.get_advancing_goals_for_user = AsyncMock(
        return_value=Result.ok([])
    )
    mock_factory._choices.get_pending_decisions_for_user = AsyncMock(
        return_value=Result.ok([])
    )
    mock_factory._principles.get_aligned_principles_for_user = AsyncMock(
        return_value=Result.ok([])
    )
    mock_factory._ku.get_ready_to_learn_for_user = AsyncMock(
        return_value=Result.ok([])
    )

    intelligence = mock_factory.create(mock_context)
    result = await intelligence.get_ready_to_work_on_today()

    assert result.is_ok
    assert isinstance(result.value, DailyWorkPlan)
```

### Integration Testing

```python
async def test_full_integration(real_neo4j_driver, real_event_bus):
    """Integration test with real services."""
    # Bootstrap real services
    services_result = await compose_services(real_neo4j_driver, real_event_bus)
    services = services_result.value

    # Create test user
    user = await create_test_user(services)

    # Get context
    context = await services.user.get_user_context(user.uid)

    # Create intelligence
    intelligence = services.context_intelligence.create(context)

    # Test flagship method
    result = await intelligence.get_ready_to_work_on_today()

    assert result.is_ok
    plan = result.value
    assert plan.fits_capacity
    assert plan.workload_utilization >= 0.0
    assert plan.workload_utilization <= 1.0
```

---

## Pattern Benefits

### 1. Separation of Concerns

- **Bootstrap**: Wires services (singleton pattern)
- **Runtime**: Binds context (per-request pattern)
- **Intelligence**: Uses both without knowing origin

### 2. Testability

```python
# Easy to mock just the factory
async def test_route(mock_factory):
    mock_factory.create.return_value = mock_intelligence
    # Test route behavior
```

### 3. Clean Dependency Injection

```python
# Service only needs factory, not 13 individual services
class MyService:
    def __init__(self, factory: UserContextIntelligenceFactory):
        self.factory = factory
```

### 4. Context Freshness

```python
# Each request gets fresh context
async def handler(request, user_uid: str):
    context = await get_fresh_context(user_uid)  # Always fresh
    intelligence = factory.create(context)       # Bound to fresh context
    return await intelligence.method()
```

---

## Anti-Patterns

### Don't Cache Intelligence Instances

```python
# WRONG - context becomes stale
class BadService:
    def __init__(self, factory):
        self.cached_intelligence = {}

    async def get_plan(self, user_uid: str):
        if user_uid not in self.cached_intelligence:
            context = await get_context(user_uid)
            self.cached_intelligence[user_uid] = factory.create(context)

        # STALE! Context was fetched once, never refreshed
        return await self.cached_intelligence[user_uid].get_ready_to_work_on_today()

# CORRECT - always fresh
class GoodService:
    def __init__(self, factory):
        self.factory = factory

    async def get_plan(self, user_uid: str):
        context = await get_context(user_uid)  # Fresh context
        intelligence = self.factory.create(context)  # Fresh intelligence
        return await intelligence.get_ready_to_work_on_today()
```

### Don't Create Factory Per Request

```python
# WRONG - creates factory each time (wasteful)
async def handler(request):
    factory = UserContextIntelligenceFactory(
        tasks=services.tasks.relationships,
        # ... 12 more
    )
    intelligence = factory.create(context)

# CORRECT - use singleton factory
async def handler(request):
    intelligence = services.context_intelligence.create(context)
```

### Don't Bypass Factory

```python
# WRONG - bypasses factory, couples to service location
async def handler(request):
    intelligence = UserContextIntelligence(
        context=context,
        tasks=services.tasks.relationships,
        # Duplicates bootstrap wiring!
    )

# CORRECT - use factory
async def handler(request):
    intelligence = services.context_intelligence.create(context)
```
