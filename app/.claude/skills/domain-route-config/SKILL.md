---
name: domain-route-config
description: Expert guide for SKUEL's DomainRouteConfig pattern — configuration-driven route registration for *_routes.py files. Use when wiring domain routes, creating new route files, migrating routes to DomainRouteConfig, or when the user mentions DomainRouteConfig, route registration, routes file, domain routes, register_domain_routes, or *_routes.py.
allowed-tools: Read, Grep, Glob
---

# DomainRouteConfig: Configuration-Driven Route Registration

> "Configuration over code for route registration"

DomainRouteConfig eliminates boilerplate in `*_routes.py` files by replacing ~80 lines of manual service extraction, validation, and wiring with a ~15-line declarative config. The majority of `*_routes.py` files use it. All 6 Activity Domains use `create_activity_domain_route_config()`. Five proven pattern variants cover every route registration scenario in SKUEL. All DomainRouteConfig routes are registered without `if services.X:` guards in `_wire_all_routes()` — `register_domain_routes()` handles missing services via soft-fail.

**Three wiring patterns exist** — see `docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md` "Route Wiring Patterns" for when to use each:
- **A — DomainRouteConfig** (default): entity domains, soft-fail on missing service
- **B — Orchestrator-driven**: cross-domain coordination (`explore_routes.py`, `lateral_routes.py`, `library_routes.py`)
- **C — Manual `@rt()`**: structural/infrastructure routes (`home_routes.py`, `settings_routes.py`, `submissions_hub_routes.py`)

---

## Quick Reference

### The 6 Configuration Fields

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `domain_name` | `str` | Yes | Human-readable name for logging (e.g., `"tasks"`) |
| `primary_service_attr` | `str` | Yes | Attribute name on the services container (e.g., `"tasks"` → `services.tasks`) |
| `api_factory` | `Callable \| None` | No | Function that registers API routes. Defaults to `None` for UI-only domains |
| `ui_factory` | `Callable \| None` | No | Function that registers UI routes. Defaults to `None` for API-only domains |
| `api_related_services` | `dict[str, str]` | No | Service dependencies for the API factory (see Service Mapping Contract) |
| `ui_related_services` | `dict[str, str]` | No | Service dependencies for the UI factory — `{kwarg_name: container_attr}`, injected as named kwargs (same mechanism as `api_related_services`) |

\* Both default to `None`. At least one of `api_factory` or `ui_factory` must be provided.

### Import Surface

```python
# For all domains
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes

# For Activity Domains — use this instead
from adapters.inbound.route_factories import create_activity_domain_route_config, register_domain_routes
```

All three are exported from `adapters/inbound/route_factories/__init__.py`. The implementation lives in `adapters/inbound/route_factories/domain_route_factory.py`.

---

## Service Mapping Contract

This is the single most important concept in the pattern. The `api_related_services` dict maps **factory parameter names** to **services container attribute names**:

```python
api_related_services={
    "kwarg_name": "container_attr",
}
```

- **Key (`kwarg_name`):** The parameter name the factory function expects
- **Value (`container_attr`):** The attribute on the `services` container to look up

`register_domain_routes()` does `getattr(services, container_attr)` for each entry, then passes the results as keyword arguments to the factory:

```python
# Config declares the mapping:
api_related_services={
    "user_service": "user",    # kwarg name → Services.user (UserService)
    "goals_service": "goals",  # kwarg name → Services.goals
}

# register_domain_routes() resolves it at runtime:
api_factory(
    app, rt, primary_service,
    user_service=services.user,    # getattr(services, "user")
    goals_service=services.goals,  # getattr(services, "goals")
)
```

**Service attribute naming convention:**
- Activity domains use short names: `services.tasks`, `services.goals`, `services.habits`
- Shared services use bare names: `services.user`, `services.system`
- Special cases: `services.event_bus`, `services.driver`

**What these service attributes are:** `services.tasks`, `services.goals`, etc. are `TasksService`/`GoalsService` facade instances. Their `.relationships` attribute is a `UnifiedRelationshipService` (URS) — a shell + 6 focused mixins (`PlanningMixin`, `DomainPlanningMixin`, `LifePathMixin`, `IntelligenceMixin`, `OrderedRelationshipsMixin`, `BatchOperationsMixin`). DomainRouteConfig wires the facade; the URS methods are used by intelligence services internally. Public API unchanged across the decomposition.

**None is valid.** If the attribute exists on the container but its value is `None` (e.g. tier-dependent services like `submission_report` in CORE tier), the `None` is passed through silently. The factory must handle optional dependencies with default parameters:

```python
def create_tasks_api_routes(app, rt, tasks_service, goals_service=None, ...):
    ...  # goals_service may be None
```

**Missing attributes warn.** If `getattr(services, attr)` finds no such attribute (sentinel-based detection), a warning is logged and `None` is passed. This catches stale attr names after renames — e.g. `"assignments"` → `"exercises"`.

---

## Canonical Template

Copy-paste starting point for a new Standard (API + UI) route file:

```python
"""
{Domain} Routes - Configuration-Driven Registration
=================================================

Wires {Domain} API and UI routes using DomainRouteConfig pattern.
"""

from adapters.inbound.{domain}_api import create_{domain}_api_routes
from adapters.inbound.{domain}_ui import create_{domain}_ui_routes
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes

{DOMAIN}_CONFIG = DomainRouteConfig(
    domain_name="{domain}",
    primary_service_attr="{domain}",
    api_factory=create_{domain}_api_routes,
    ui_factory=create_{domain}_ui_routes,
    api_related_services={
        # Format: {kwarg_name: container_attr}
        # Each entry is passed to api_factory as: kwarg_name=getattr(services, container_attr)
    },
)


def create_{domain}_routes(app, rt, services, _sync_service=None):
    """Wire {domain} API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, {DOMAIN}_CONFIG)


__all__ = ["create_{domain}_routes"]
```

**Placeholders:** `{domain}` → lowercase, `{Domain}` → capitalized, `{DOMAIN}` → uppercase.

---

## The 5 Pattern Variants

### 0. Activity Domain — THE Standard for the 6 Activity Domains

**When to use:** Any of the 6 Activity Domains (Tasks, Goals, Habits, Events, Choices, Principles). This is the highest-level convenience — pre-populates CRUD, Query, and Intelligence factory configs automatically.

**Exemplar:** `adapters/inbound/tasks_routes.py`

```python
from typing import Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.route_factories import (
    create_activity_domain_route_config,
    register_domain_routes,
)
from adapters.inbound.tasks_api import create_tasks_api_routes
from adapters.inbound.tasks_ui import create_tasks_ui_routes
from core.models.task.task_request import TaskCreateRequest, TaskUpdateRequest

TASKS_CONFIG = create_activity_domain_route_config(
    domain_name="tasks",
    primary_service_attr="tasks",
    api_factory=create_tasks_api_routes,
    ui_factory=create_tasks_ui_routes,
    create_schema=TaskCreateRequest,
    update_schema=TaskUpdateRequest,
    uid_prefix="task",
    supports_goal_filter=True,
    supports_habit_filter=True,
    api_related_services={
        "goals_service": "goals",
        "habits_service": "habits",
    },
    prometheus_metrics_attr="prometheus_metrics",
)


def create_tasks_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: Any, _sync_service: Any = None
) -> None:
    """Wire tasks API and UI routes using configuration-driven registration."""
    register_domain_routes(app, rt, services, TASKS_CONFIG)


__all__ = ["create_tasks_routes"]
```

**What `create_activity_domain_route_config` registers automatically (before `api_factory`):**
- `CRUDRouteFactory` — create, get, list, update, delete
- `CommonQueryRouteFactory` — filter by status, domain, goal, habit
- `IntelligenceRouteFactory` — context, recommendations

**What stays in `api_factory`:** `OwnershipRouteFactory` (domain-specific ownership routes), `create_activity_field_api_routes` (inline status/priority updates), `AnalyticsRouteFactory`, and manual routes with custom logic.

**What `ui_factory` does (inside `create_{domain}_ui_routes`):**
- Creates an `ActivityUIConfig` dataclass (~50 lines) with domain-specific callbacks and components
- Delegates to `create_activity_ui_routes(app, rt, config)` from `activity_ui_factory.py`
- The shared factory generates 5 routes: `/{domain}`, `/{domain}/content`, `/{domain}/list-fragment`, `/{domain}/detail`, `/{domain}/detail/content`
- Uses `ActivityFilterBar` with per-domain `FilterBarConfig` for config-driven filter bars

---

### 1. Standard (API + UI) — For Non-Activity Domains Without CRUD

**When to use:** Any domain with both API endpoints and UI pages that is NOT an Activity Domain and does NOT use CRUDRouteFactory (e.g., KU, Askesis). For Activity Domains, use Pattern 0. For non-activity domains with CRUDRouteFactory, use Pattern 5.

**Exemplar:** `adapters/inbound/ku_routes.py`

```python
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes

KU_CONFIG = DomainRouteConfig(
    domain_name="ku",
    primary_service_attr="ku",
    api_factory=_ku_api_routes,
    ui_factory=create_ku_ui_routes,
    ui_related_services={"user_relationship_service": "user_relationships"},
)
```

---

### 2. API-Only — `ui_factory=None`

**When to use:** Domains that expose only JSON/data endpoints with no server-rendered pages. Examples: Transcription (audio processing), Visualization (chart data), Admin (user management API).

```python
TRANSCRIPTION_CONFIG = DomainRouteConfig(
    domain_name="transcription",
    primary_service_attr="transcription",
    api_factory=create_transcription_api_routes,
    ui_factory=None,  # API-only domain — no UI routes
    api_related_services={},
)
```

`register_domain_routes()` checks `if config.ui_factory:` before calling, so `None` is safe.

---

### 3. UI-Only — omit `api_factory`

**When to use:** Domains that only need server-rendered pages, with no CRUD API of their own. Example: Study (submission hub composing multiple services).

**Detail:** `api_factory` defaults to `None`. Simply omit it. `register_domain_routes()` skips API wiring and `api_related_services` extraction when `api_factory` is `None`.

**Exemplar:** `adapters/inbound/study_routes.py`

```python
STUDY_CONFIG = DomainRouteConfig(
    domain_name="study",
    primary_service_attr="user_entry",
    ui_factory=create_study_ui_routes,
    ui_related_services={
        "processing_service": "user_entry_processor",
        "user_service": "user",
        "exercises_service": "exercises",
        "activity_report_service": "activity_report",
        "teacher_review_service": "teacher_review",
    },
)
```

Note: `primary_service_attr` doesn't have to match the domain name — a UI-only domain can back onto another domain's service.

---

### 4. Multi-Factory — DomainRouteConfig + manual extension

**When to use:** Domains where DomainRouteConfig handles the standard API + UI routes, but additional routes (from a third factory) need to be registered outside the config. The pattern composes: config handles 80%, custom logic adds the rest.

**Exemplar:** `adapters/inbound/insights_routes.py`

```python
from adapters.inbound.insights_api import create_insights_api_routes
from adapters.inbound.insights_history_ui import create_insights_history_routes
from adapters.inbound.insights_ui import create_insights_ui_routes
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes

INSIGHTS_CONFIG = DomainRouteConfig(
    domain_name="insights",
    primary_service_attr="insight_store",
    api_factory=create_insights_api_routes,
    ui_factory=create_insights_ui_routes,
    api_related_services={},
)


def create_insights_routes(app, rt, services, _sync_service=None):
    # Standard routes via config
    routes = register_domain_routes(app, rt, services, INSIGHTS_CONFIG)

    # Additional history routes registered manually
    if services and services.insight_store:
        history_routes = create_insights_history_routes(app, rt, services.insight_store)
        routes.extend(history_routes)

    return routes
```

The manual block follows the same service-null-guard pattern that `register_domain_routes()` uses internally: check `services` and the specific service before calling the factory.

---

### 5. Config-Driven CRUDRouteConfig — Role-Gated Non-Activity Domains

**When to use:** Non-activity domains that need CRUDRouteFactory with role-based access control. The `crud` field on `DomainRouteConfig` auto-registers create/get/list/update/delete routes before `api_factory` runs. The `intelligence` field auto-registers context/analytics/insights routes. The API factory then only needs domain-specific routes.

**CRUDRouteConfig fields:**

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `create_schema` | `type` | required | Pydantic model for create validation |
| `update_schema` | `type` | required | Pydantic model for update validation. For Activity Domains this is the `*UpdateRequest`, which the generated update route turns into the typed `*UpdateIntent` via `to_intent()` (ADR-066); other domains fall back to a `RawChanges` patch. |
| `uid_prefix` | `str` | required | UID prefix (e.g., `"ft"`, `"group"`) |
| `scope` | `ContentScope` | `USER_OWNED` | Ownership model |
| `require_role` | `UserRole \| None` | `None` | Role gate for mutations (and reads if `role_gates_reads=True`) |
| `role_gates_reads` | `bool` | `True` | When False, get/list skip role check |
| `user_service_attr` | `str \| None` | `None` | Services container attr for role checks |

**IntelligenceRouteConfig fields:**

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `scope` | `ContentScope` | `USER_OWNED` | Ownership model for intelligence routes. Use `SHARED` for Curriculum domains. |

**Three proven CRUDRouteConfig configurations:**

```python
# Admin-only shared content (Ku, LearningPath, PathStep, FormTemplate)
crud=CRUDRouteConfig(
    scope=ContentScope.SHARED,
    require_role=UserRole.ADMIN,
    user_service_attr="user",  # Services.user
)

# Teacher-only user-owned (Exercises, RevisedExercise)
crud=CRUDRouteConfig(
    scope=ContentScope.USER_OWNED,
    require_role=UserRole.TEACHER,
    user_service_attr="user",  # Services.user
)

# Teacher mutations, any-auth reads (Groups)
crud=CRUDRouteConfig(
    scope=ContentScope.USER_OWNED,
    require_role=UserRole.TEACHER,
    role_gates_reads=False,    # Students can GET groups
    user_service_attr="user",  # Services.user
)
```

**Exemplars:** `groups_routes.py`, `ku_routes.py`, `exercises_routes.py`, `pathways_routes.py`, `path_steps_routes.py`, `form_templates_routes.py`, `revised_exercises_routes.py`

**Combining CRUD + Intelligence:** Curriculum domains typically pair both:

```python
crud=CRUDRouteConfig(
    scope=ContentScope.SHARED,
    require_role=UserRole.ADMIN,
    user_service_attr="user",  # Services.user
),
intelligence=IntelligenceRouteConfig(scope=ContentScope.SHARED),
```

**Service requirements:** The service must implement `create()`, `get()`, `update()`, `delete()`, `list()` (inherited from `BaseService`). For `scope=USER_OWNED`, also needs `get_for_user()`, `update_for_user()`, `delete_for_user()` (inherited from `CrudOperationsMixin`). Override these when the domain model uses a different ownership field (e.g., Group uses `owner_uid` instead of `user_uid`).

**ConversionServiceV2:** Add a `{entity}_create_to_pure()` classmethod and register it in `ConversionServiceV2.CONVERTER_REGISTRY` (keyed by schema type, e.g., `GroupCreateRequest: ConversionServiceV2.group_create_to_pure`). Alternatively, pass an explicit `entity_converter` callable via `CRUDRouteConfig.entity_converter`. Updates use the dict-based pattern in CRUDRouteFactory (`model_dump(exclude_unset=True)`) — no converter needed.

---

## Factory Signature Requirements

All API and UI factories wired via DomainRouteConfig MUST match these signatures exactly. `register_domain_routes()` calls them positionally for the first 3 args, then passes related services as kwargs.

### API Factory

```python
def create_{domain}_api_routes(
    app: Any,                        # FastHTML app instance
    rt: Any,                         # Route decorator
    {domain}_service: ServiceType,   # Primary service (positional)
    # Related services as keyword args with defaults:
    user_service: Any = None,
    goals_service: Any = None,
) -> list[Any]:                      # Sub-factory: must return list[Any] (DomainRouteConfig contract)
    ...
    return []
```

### UI Factory

```python
def create_{domain}_ui_routes(
    app: FastHTMLApp,                            # FastHTML app
    rt: RouteDecorator,                          # Route decorator
    {domain}_service: ServiceType,               # Primary service (positional)
    connection_fetch_backend: ConnectionFetchOperations,  # related service, injected by name via ui_related_services
    goals_service: GoalsService | None = None,   # optional related services default to None
) -> list[Any]:                                  # Sub-factory: must return list[Any] (DomainRouteConfig contract)
    ...
    return []
```

**Key requirements:**
1. Positional order: `app`, `rt`, `primary_service` — always in this order
2. Optional related services default to `None` (they may not be bootstrapped yet); always-present infrastructure (e.g. `connection_fetch_backend`) can be a required param with no default
3. **Two-layer return contract:** Sub-factories (wired into `DomainRouteConfig.api_factory`/`ui_factory`) return `list[Any]` — never `None` — because `register_domain_routes()` calls `.extend()` on the result. Top-level orchestrators (`create_{domain}_routes`) return `None` — bootstrap discards the value.
4. Related services are explicit **named** kwargs injected via `ui_related_services` — `register_domain_routes()` passes `primary_service` + those kwargs, never a whole `services` container. (A whole-`services` container is the separate Orchestrator/Manual hub convention — see Anti-Pattern #1.)

---

## Anti-Patterns

### 1. Putting the full services container in a factory

```python
# BAD — factory reaches into the container itself
def create_tasks_api_routes(app, rt, services):
    tasks_service = services.tasks        # ← breaks the contract
    goals_service = services.goals

# GOOD — services extracted by config, injected as kwargs
def create_tasks_api_routes(app, rt, tasks_service, goals_service=None):
    ...
```

DomainRouteConfig's purpose is to own service extraction. Factories that do their own `getattr(services, ...)` defeat the pattern entirely.

### 2. Mismatched container_attr in service mapping

```python
# BAD — "goals" is the container attr, not "goals_service"
api_related_services={
    "goals_service": "goals_service",  # ← services.goals_service doesn't exist → None silently
}

# GOOD — match the actual attribute name on services
api_related_services={
    "goals_service": "goals",          # ← services.goals (the real attr)
}
```

This fails silently: `getattr` returns `None`, which is passed as the kwarg. The factory won't crash if the param has a default, but it will behave as if the service doesn't exist.

### 3. Returning None from a sub-factory

```python
# BAD — sub-factory returns None implicitly
def create_tasks_api_routes(app, rt, tasks_service):
    @rt("/api/tasks")
    async def get_tasks(): ...
    # no return statement → None

# GOOD — sub-factories wired into DomainRouteConfig must return list[Any]
def create_tasks_api_routes(app, rt, tasks_service):
    @rt("/api/tasks")
    async def get_tasks(): ...
    return []
```

`register_domain_routes()` calls `.extend()` on the return value. `None.extend()` is a `TypeError`.

**Note:** This applies to sub-factories (`api_factory`/`ui_factory`), not top-level orchestrators. Top-level `create_{domain}_routes()` functions return `None` — bootstrap discards their return value.

### 4. Forgetting the null guard in UI-only domains

```python
# BAD — if someone removes the null guard from domain_route_factory.py:
# config.api_factory(app, rt, ...)  # TypeError when api_factory is None

# The guard at domain_route_factory.py line ~97 MUST stay:
if config.api_factory:
    config.api_factory(app, rt, primary_service, **api_related)
```

Don't refactor `register_domain_routes()` without preserving both null guards (api_factory and ui_factory).

---

## Key Source Files

| File | Role |
|------|------|
| `adapters/inbound/route_factories/domain_route_factory.py` | The dataclass + `register_domain_routes()` — source of truth (119 lines) |
| `adapters/inbound/route_factories/__init__.py` | Export surface: `DomainRouteConfig`, `register_domain_routes` |
| `adapters/inbound/tasks_routes.py` | Exemplar: Standard pattern with related services |
| `adapters/inbound/ku_routes.py` | Exemplar: Standard pattern with `ui_related_services` (UserRelationshipService for pins) |
| `adapters/inbound/nous_routes.py` | Exemplar: UI-only pattern |
| `adapters/inbound/insights_routes.py` | Exemplar: Multi-factory pattern |
| `docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md` | Canonical pattern documentation (1,043 lines) |
| `docs/migrations/DOMAIN_ROUTE_CONFIG_MIGRATION_2026-02-03.md` | Migration history and stats |

---

## Related Skills

- **[fasthtml](../fasthtml/SKILL.md)** — DomainRouteConfig is route infrastructure built on FastHTML's decorator-based registration. Read fasthtml first if you're new to SKUEL routes.
- **[python](../python/SKILL.md)** — Dataclass patterns, typing conventions used by the config.
- **[result-pattern](../result-pattern/SKILL.md)** — Factories called by DomainRouteConfig return `Result[T]` from services internally; `@boundary_handler` converts at route boundaries.

## Deep Dive Resources

**Patterns:**
- [DOMAIN_ROUTE_CONFIG_PATTERN.md](/docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md) — Canonical pattern doc: all 10 examples, migration guide, troubleshooting (1,043 lines)
- [ROUTE_FACTORIES.md](/docs/patterns/ROUTE_FACTORIES.md) — Endpoint-level factories (CRUDRouteFactory, create_activity_field_api_routes) that are called *inside* the factories wired by DomainRouteConfig
- [FASTHTML_ROUTE_REGISTRATION.md](/docs/patterns/FASTHTML_ROUTE_REGISTRATION.md) — Why routes register via decorator side effects (the reason factories return `[]`)

**Migration:**
- [DOMAIN_ROUTE_CONFIG_MIGRATION_2026-02-03.md](/docs/migrations/DOMAIN_ROUTE_CONFIG_MIGRATION_2026-02-03.md) — Phase 3 migration: 9 files, all 4 patterns proven, infrastructure bug fix
