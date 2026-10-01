# Factory Pattern

`UserContextIntelligenceFactory` (`core/services/user/intelligence/factory.py`) separates
**service wiring** from **context binding**:

- the domain services are singletons, built once at bootstrap;
- a `RichUserContext` is one user's snapshot, built or taken from the cache per request;
- `UserContextIntelligence` needs both at construction.

```
Bootstrap (once)              Request
      │                          │
      ▼                          ▼
   Factory                RichUserContext
      └────────────┬─────────────┘
                   ▼
        UserContextIntelligence
```

---

## The Factory

```python
class UserContextIntelligenceFactory:
    def __init__(
        self,
        # Activity (6) — the facades
        tasks: TasksService,
        goals: GoalsService,
        habits: HabitsService,
        events: EventsService,
        choices: ChoicesService,
        principles: PrinciplesService,
        # Curriculum (3)
        ps: PsService,
        lp: UnifiedRelationshipService,
        exercises: Any,  # boundary: ExerciseService facade, duck-typed
        # Processing (1)
        report: ReportRelationshipService,
        # Temporal (1)
        calendar: CalendarService,
        # Optional
        vector_search_service: Any = None,  # boundary: optional Neo4jVectorSearchService
        zpd_service: ZPDOperations | None = None,
        filtered_providers: dict[str, FilteredContextProvider] | None = None,
    ) -> None: ...

    def create(self, context: RichUserContext) -> UserContextIntelligence: ...
```

- The eleven required services are held in one dict, `_required_services`. It is both what the
  constructor validates and what `create()` forwards, so adding a service is one entry there
  plus the two matching parameters.
- A required service that is `None` raises `ValueError` at construction, naming every missing
  one.
- The factory's keyword is `vector_search_service`; the instance attribute it becomes is
  `vector_search`.
- `create()` is synchronous and does no I/O.

---

## Bootstrap Wiring

`_create_intelligence_hub()` (`services_bootstrap/_intelligence_hub.py`) builds the factory near
the end of `compose_services()`:

```python
context_intelligence_factory = UserContextIntelligenceFactory(
    tasks=activity_services["tasks"],
    goals=activity_services["goals"],
    habits=activity_services["habits"],
    events=activity_services["events"],
    choices=activity_services["choices"],
    principles=activity_services["principles"],
    ps=learning_services["ps"],
    lp=learning_services["learning_paths"].relationships,
    exercises=services.exercises,
    report=report_relationship_service,
    calendar=calendar_service,
    vector_search_service=vector_search_service,
    zpd_service=zpd_service,
    filtered_providers=filtered_providers,
)
services.context_intelligence = context_intelligence_factory
user_service.intelligence_factory = context_intelligence_factory
```

The same function:

- post-wires `services.ps_engagement` onto the context builder (it raises `RuntimeError` when
  that service is missing) — this is what fills `context.active_ps_engagements`;
- at FULL tier, builds `ZPDService`, sets it on the context builder and on the factory, and
  subscribes the ZPD snapshot handler to five events;
- at FULL tier, builds Askesis with the factory.

At CORE tier `zpd_service` and `vector_search_service` are `None`; the factory is built either
way. `compose_services` ends by checking that `services.context_intelligence` and
`user_service.intelligence_factory` are set, and raises if either is `None`.

On the container the field is `context_intelligence: UserContextIntelligenceFactory | None`
(`services_bootstrap/_container.py`) — narrow it before use in a route.

### One context builder

The builder `UserService.__init__` constructs is the single app-wide instance. The intelligence
hub post-wires `zpd_service` and `ps_engagement_service` onto that one. A second builder would
miss the post-wiring and produce contexts without a ZPD assessment or engagement buckets.
`tests/unit/services/test_user_context_builder_wiring.py` guards it.

---

## `filtered_providers`

```python
filtered_providers = _filtered_context_providers(
    activity_services, learning_services, services.exercises
)
# keys: tasks, goals, habits, events, choices, principles, ps, learning_paths, exercises
```

`_filtered_context_providers` (`services_bootstrap/_intelligence_hub.py`) checks each facade
with `isinstance(facade, FilteredContextProvider)` and raises `RuntimeError` naming the domain
when one has no `get_filtered_context` — the service dicts it reads are `Any`-valued, so the
annotation alone would not catch it. `KuService` is not a provider and is not registered.

The protocol (`core/ports/filtered_context_protocols.py`) is one method:

```python
async def get_filtered_context(
    self,
    user_uid: UserUID,
    status_filter: str = ...,
    sort_by: str = ...,
) -> Result[ListContext]: ...
```

What the code does with the dict:

- `DailyPlanningMixin` is the only reader, and it looks up the six Activity keys by name. Nothing
  reads `ps`, `learning_paths` or `exercises`.
- Every registered value is a provider, held by the check above and by
  `tests/unit/test_filtered_context_provider_wiring.py` (the registry is exactly the facades
  that define the method) and `tests/integration/test_filtered_provider_wiring.py` (the
  composed app).
- `UserContext` is the broad snapshot; `get_filtered_context()` is a per-domain read made at
  call time. The daily plan uses it for the `stats` aggregate only, with `status_filter="all"`.

---

## Runtime Usage

### The live path

```python
# adapters/inbound/context_aware_api.py
@rt("/api/context/next-action")
@boundary_handler()
async def get_next_action_route(request: Request) -> Result[NextActionResult]:
    user_uid = require_authenticated_user(request)
    return await context_service.get_next_action(user_uid)
```

`UserContextService.get_next_action` calls `UserService.get_daily_work_plan`, which is where the
factory is used:

```python
# core/services/user/_context_planning_mixin.py
async def get_daily_work_plan(
    self,
    user_uid: UserUID,
    prioritize_life_path: bool = True,
    respect_capacity: bool = True,
) -> Result[DailyWorkPlan]:
    if not self.intelligence_factory:
        return Result.fail(
            Errors.system(
                message="Intelligence factory not available",
                operation="get_daily_work_plan",
            )
        )

    context_result = await self.get_rich_unified_context(user_uid)
    if context_result.is_error:
        return Result.fail(context_result)

    intelligence = self.intelligence_factory.create(context_result.value)
    return await intelligence.get_ready_to_work_on_today(
        prioritize_life_path=prioritize_life_path,
        respect_capacity=respect_capacity,
    )
```

`get_next_action` then projects the `DailyWorkPlan` into the route-facing `NextActionResult`
TypedDict (`core/ports/query_types.py`).

### In a new service

Take the factory and the user service; build the context once and reuse the instance for every
method in the request.

```python
class AlignmentDigestService:
    def __init__(
        self,
        user_service: UserService,
        intelligence_factory: UserContextIntelligenceFactory,
    ) -> None:
        self.user_service = user_service
        self.intelligence_factory = intelligence_factory

    async def get_alignment(self, user_uid: UserUID) -> Result[LifePathAlignment]:
        context_result = await self.user_service.get_rich_unified_context(user_uid)
        if context_result.is_error:
            return Result.fail(context_result)

        intelligence = self.intelligence_factory.create(context_result.value)
        return await intelligence.calculate_life_path_alignment()
```

Propagate a failed read with `Result.fail(result)`. Do not flatten it to `None` or an empty list
in the return value — the caller cannot tell "no synergies" from "the read failed".

---

## Testing with the Factory

The factory accepts any object for a required service, so mocks satisfy it. `RichUserContext`
has a default for every field but `user_uid`.

```python
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.context_types import DailyWorkPlan
from core.services.user.intelligence import (
    UserContextIntelligence,
    UserContextIntelligenceFactory,
)
from core.services.user.unified_user_context import RichUserContext
from core.utils.result_simplified import Result

_PLANNING_METHODS = (
    "get_at_risk_habits_for_user",
    "get_upcoming_events_for_user",
    "get_pending_revisions_for_user",
    "get_actionable_exercises_for_user",
    "get_actionable_tasks_for_user",
    "get_ready_to_learn_for_user",
    "get_advancing_goals_for_user",
    "get_pending_decisions_for_user",
    "get_aligned_principles_for_user",
)


def make_service() -> AsyncMock:
    service = AsyncMock()
    for name in _PLANNING_METHODS:
        setattr(service, name, AsyncMock(return_value=Result.ok([])))
    return service


@pytest.fixture
def factory() -> UserContextIntelligenceFactory:
    service = make_service()
    return UserContextIntelligenceFactory(
        tasks=service,
        goals=service,
        habits=service,
        events=service,
        choices=service,
        principles=service,
        ps=service,
        lp=MagicMock(),
        exercises=service,
        report=MagicMock(),
        calendar=MagicMock(),
    )


@pytest.mark.asyncio
async def test_daily_plan_from_an_empty_context(
    factory: UserContextIntelligenceFactory,
) -> None:
    intelligence = factory.create(RichUserContext(user_uid="user_test"))

    assert isinstance(intelligence, UserContextIntelligence)

    result = await intelligence.get_ready_to_work_on_today()

    assert result.is_ok
    assert isinstance(result.value, DailyWorkPlan)
    assert result.value.tasks == ()


def test_factory_names_a_missing_service() -> None:
    service = make_service()
    with pytest.raises(ValueError, match="Missing: lp"):
        UserContextIntelligenceFactory(
            tasks=service,
            goals=service,
            habits=service,
            events=service,
            choices=service,
            principles=service,
            ps=service,
            lp=None,
            exercises=service,
            report=MagicMock(),
            calendar=MagicMock(),
        )
```

`plan.fits_capacity` is `estimated_time_minutes <= context.available_minutes_daily` (see
[SKILL.md](SKILL.md) § Plan metadata): set `available_minutes_daily` on the stub context to the
capacity the test is about, since at-risk habits and events are planned past it.

For a route test, replace the factory on the service under test and have `create` return a mock
whose method returns a real `Result`.

---

## Anti-Patterns

### Building a factory per request

```python
# WRONG - re-does the bootstrap wiring on every request
factory = UserContextIntelligenceFactory(tasks=services.tasks, ...)

# CORRECT - the singleton
intelligence = services.context_intelligence.create(context)
```

### Bypassing the factory

Constructing `UserContextIntelligence(...)` directly duplicates the wiring and drops the
optional services (`zpd_service`, `vector_search`, `filtered_providers`).

### Holding an instance

An instance is bound to the context it was created with. Keep the factory on the service, not
an instance: the context cache (`UserContextCache`, five-minute TTL, cleared by domain events)
is the reuse mechanism, and `create()` costs nothing.

### Passing `.relationships` for an Activity domain

The factory takes the Activity **facades**. `get_actionable_tasks_for_user` and its siblings are
facade methods; a `UnifiedRelationshipService` does not have them. `lp` is the one parameter that
takes a relationship service.
