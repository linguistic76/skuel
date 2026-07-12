---
title: Domain Route Configuration Pattern
updated: '2026-03-19'
category: patterns
related_skills:
- fasthtml
- domain-route-config
related_docs: []
---
# Domain Route Configuration Pattern

**Status:** Active | **Last Updated:** 2026-03-19
## Related Skills

For implementation guidance, see:
- [@fasthtml](../../.claude/skills/fasthtml/SKILL.md)

## Overview

**What:** Configuration-driven route registration pattern that eliminates boilerplate in domain route files.

**Why:** Enforce consistency, reduce duplication, and make route wiring declarative rather than imperative.

**Impact:** Reduces route file complexity from ~80 lines to ~15 lines per domain (83% reduction).

**Adoption:** 42 of 46 route files (91%). All 6 Activity Domains use `create_activity_domain_route_config()`. Non-adopters: graphql_routes.py, metrics_routes.py, pwa_routes.py, library_routes.py (hub orchestrator). ai_routes.py uses its own config-driven pattern (AIRouteSpec).

## The Pattern

### Core Components

1. **DomainRouteConfig** - Declarative configuration object
2. **register_domain_routes()** - Single registration function
3. **Service extraction** - Automatic attribute lookup from services container
4. **Route collection** - Gathers and returns route lists from both factories

### Configuration Structure

```python
@dataclass
class DomainRouteConfig:
    domain_name: str                           # Human-readable name (e.g., "tasks")
    primary_service_attr: str                  # Attribute on services container (e.g., "tasks")
    api_factory: Callable[..., list[Any]] | None = None  # Optional API routes factory
    ui_factory: Callable[..., list[Any]] | None = None  # Optional UI routes factory
    api_related_services: dict[str, str] = {}  # API factory dependencies
    ui_related_services: dict[str, str] = {}   # UI factory dependencies
    crud: CRUDRouteConfig | None = None        # Config-driven CRUD factory (optional)
    query: QueryRouteConfig | None = None      # Config-driven Query factory (optional)
    intelligence: IntelligenceRouteConfig | None = None  # Config-driven Intelligence factory (optional)
```

### Config-Driven Factory Registration (2026-02-05)

**What:** Move formulaic factory instantiation (CRUD, Query, Intelligence) from `api_factory` functions into `DomainRouteConfig` declarations.

**Why:** These three factories have purely static parameters across all Activity Domains. Moving them to config eliminates ~80-120 lines of boilerplate per domain.

**What Stays in api_factory:** Factories with runtime closures (StatusRouteFactory, AnalyticsRouteFactory) and all manual domain-specific routes remain in api_factory.

#### Sub-Config Dataclasses

Three frozen dataclasses define static factory parameters:

```python
@dataclass(frozen=True)
class CRUDRouteConfig:
    """Parameters for CRUDRouteFactory."""
    create_schema: type              # e.g., TaskCreateRequest
    update_schema: type              # e.g., TaskUpdateRequest
    uid_prefix: str                  # e.g., "task"
    prometheus_metrics_attr: str | None = None  # Container attr name
    # Non-activity domain support (defaults match Activity Domain behavior)
    scope: ContentScope = ContentScope.USER_OWNED
    require_role: UserRole | None = None
    role_gates_reads: bool = True    # When False, get/list skip role check
    user_service_attr: str | None = None  # Services container attr for user_service_getter

@dataclass(frozen=True)
class QueryRouteConfig:
    """Parameters for CommonQueryRouteFactory."""
    supports_goal_filter: bool = False
    supports_habit_filter: bool = False

@dataclass(frozen=True)
class IntelligenceRouteConfig:
    """Sentinel — presence means 'register intelligence routes'."""
    # All Activity Domains use identical parameters, nothing to configure
```

#### Activity Domain Convenience Function

For Activity Domains (Tasks, Goals, Habits, Events, Choices, Principles), use the convenience function:

```python
def create_activity_domain_route_config(
    domain_name: str,
    primary_service_attr: str,
    api_factory: Callable[..., list[Any]],
    create_schema: type,
    update_schema: type,
    uid_prefix: str,
    ui_factory: Callable[..., list[Any]] | None = None,
    supports_goal_filter: bool = False,
    supports_habit_filter: bool = False,
    api_related_services: dict[str, str] | None = None,
    ui_related_services: dict[str, str] | None = None,
    prometheus_metrics_attr: str | None = None,
) -> DomainRouteConfig:
    """
    Pre-populate Activity Domain conventions into DomainRouteConfig.

    Automatically creates CRUD, Query, and Intelligence sub-configs.
    Ensures user_service is in api_related_services (required by Query).
    """
```

#### Execution Order

When sub-configs are present, `register_domain_routes()` executes in this order:

1. CRUD factory instantiation + registration
2. Query factory instantiation + registration
3. Intelligence factory instantiation + registration
4. api_factory call (Status, Analytics, manual routes)
5. ui_factory call (if present)

**Benefits:**
- api_factory files reduced by ~80-120 lines (Tasks: 264 → 145 lines)
- Zero factory code duplication across domains
- Schema imports moved to *_routes.py (single source of truth)
- Factories with static params declared once in config
- Manual routes and dynamic factories remain flexible

**Adoption:** All 6 Activity Domains + FormTemplate (`scope=ContentScope.SHARED`, `require_role=UserRole.ADMIN`) + RevisedExercise (`scope=ContentScope.USER_OWNED`, `require_role=UserRole.TEACHER`) + Groups (`require_role=UserRole.TEACHER`, `role_gates_reads=False`) migrated. Curriculum domains (KU, PS, LP) use `IntelligenceRouteConfig` only — no `CRUDRouteConfig` since they are created via ingestion.

### Recent Updates

**2026-03-23: CRUDRouteConfig enum types + Groups migration**
- `scope` and `require_role` now use `ContentScope`/`UserRole` enums (not strings)
- Added `role_gates_reads: bool = True` — when False, role only gates mutations
- Removed "role overrides scope" — role and ownership verification are now orthogonal
- FormTemplate, RevisedExercise, and Groups all use CRUDRouteFactory
- Groups uses `role_gates_reads=False`: TEACHER gates mutations, reads open to any authenticated user
- Services override inherited CRUD methods for domain-specific logic (events, authority checks, ownership)


**2026-02-03: UI Factory Signature Standardization (superseded)**
- A 2026-02-03 pass tried to standardize all UI factories on a single `services: Any = None` container. The codebase did **not** retain this — current UI factories take their related services as explicit **named kwargs** injected via `ui_related_services` (see § Service Mapping Contract and Example 2). The surviving `services`/`user_service: Any = None` params are vestigial, commented `# kept for DomainRouteConfig signature compat`.
- Historical record (point-in-time, not current guidance): `/docs/migrations/UI_FACTORY_SIGNATURE_STANDARDIZATION_2026-02-03.md`

### Service Mapping Contract

Both `api_related_services` and `ui_related_services` use the same `{kwarg_name: container_attr}` mapping pattern — `register_domain_routes()` resolves each entry and passes it to the factory as a named kwarg:

```python
{
    "kwarg_name": "container_attr"
}
```

- **Key (kwarg_name):** The parameter name expected by the factory function
- **Value (container_attr):** The attribute name on the services container

**Example:**
```python
api_related_services={
    "user_service": "user",    # user_service=getattr(services, "user")  ← Services.user
    "goals_service": "goals",  # goals_service=getattr(services, "goals")
    "habits_service": "habits",  # habits_service=getattr(services, "habits")
}
```

This is passed to the factory as:
```python
api_factory(app, rt, primary_service,
    user_service=services.user,
    goals_service=services.goals,
    habits_service=services.habits
)
```

### Execution Flow

```
1. register_domain_routes() receives config
2. Extract primary service: getattr(services, config.primary_service_attr)
3. Validate primary service exists (return [] if missing)
4. Extract API-related services: sentinel-based getattr for each api_related_services entry (warns if attr missing, silent if None)
5. Call api_factory(app, rt, primary_service, **api_related), collect returned routes
6. (Optional) Extract UI-related services, call ui_factory, collect returned routes
7. Return combined route list (API + UI)
```

**Service resolution warnings:** `register_domain_routes()` uses sentinel-based detection to distinguish two cases:
- **Attribute exists but is `None`** (e.g. tier-dependent services like `submission_report` in CORE tier) — silently passes `None` through. Factory must handle with default parameters.
- **Attribute not found on container** (e.g. stale attr name after a rename) — logs a warning and passes `None`. This catches misconfiguration early.

**Logging:** `_wire_all_routes()` in `bootstrap.py` logs a single summary line at the end with total route count. Individual route registrations do not log — `register_domain_routes()` logs a warning only when a primary service is missing.

## Canonical Template

Copy-paste template for new domain route files:

```python
"""
{Domain} Routes - Configuration-Driven Registration
=================================================

Wires {Domain} API and UI routes using DomainRouteConfig pattern.

Benefits:
- Consistent with other domain route files
- Soft-fail service validation
- Minimal boilerplate
- Clean separation of concerns

Version: 2.0 (Migrated to DomainRouteConfig pattern)
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

### Activity Domain Template (With Config-Driven Factories)

For Activity Domains (Tasks, Goals, Habits, Events, Choices, Principles), use this template:

```python
"""
{Domain} Routes - Configuration-Driven Registration (Activity Domain)
=====================================================================

Wires {Domain} API and UI routes using DomainRouteConfig with config-driven
CRUD, Query, and Intelligence factory registration.

Benefits:
- Zero factory boilerplate in api_factory
- Schema definitions centralized in routes file
- Consistent with other Activity Domains
- Minimal maintenance overhead

Version: 3.0 (Config-Driven Factory Registration)
"""

from adapters.inbound.{domain}_api import create_{domain}_api_routes
from adapters.inbound.{domain}_ui import create_{domain}_ui_routes
from adapters.inbound.route_factories import create_activity_domain_route_config, register_domain_routes
from core.models.{domain}.{domain}_request import {Domain}CreateRequest, {Domain}UpdateRequest

{DOMAIN}_CONFIG = create_activity_domain_route_config(
    domain_name="{domain}",
    primary_service_attr="{domain}",
    api_factory=create_{domain}_api_routes,
    ui_factory=create_{domain}_ui_routes,
    create_schema={Domain}CreateRequest,
    update_schema={Domain}UpdateRequest,
    uid_prefix="{domain_prefix}",  # e.g., "task", "goal", "habit"
    supports_goal_filter=False,  # True if domain relates to goals
    supports_habit_filter=False,  # True if domain relates to habits
    api_related_services={
        # Format: {kwarg_name: container_attr}
        "user_service": "user_service",  # Always include for Query factory
        # Add other domain-specific services as needed
    },
    prometheus_metrics_attr="prometheus_metrics",  # Optional
)


def create_{domain}_routes(app, rt, services, _sync_service=None):
    """Wire {domain} API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, {DOMAIN}_CONFIG)


__all__ = ["create_{domain}_routes"]
```

**What this eliminates from api_factory:**
- CRUDRouteFactory instantiation (~25 lines)
- CommonQueryRouteFactory instantiation (~20 lines)
- IntelligenceRouteFactory instantiation (~15 lines)
- Schema imports (moved to routes file)
- ContentScope import (unless needed by Status/Analytics factories)

**What remains in api_factory:**
- StatusRouteFactory (if domain has status transitions)
- AnalyticsRouteFactory (if domain has custom analytics)
- All manual domain-specific routes
- Module-level request builders (for StatusRouteFactory)

**Placeholders to replace:**
- `{domain}` → Domain name in lowercase (e.g., "tasks", "goals")
- `{Domain}` → Domain name capitalized (e.g., "Tasks", "Goals")
- `{DOMAIN}` → Domain name in uppercase (e.g., "TASKS", "GOALS")

## Canonical Factory Signatures

**CRITICAL:** All API and UI factories MUST follow these signature patterns:

### API Factory Signature

```python
def create_{domain}_api_routes(
    app: Any,
    rt: Any,
    primary_service: ServiceType,
    **related_services: Any  # Optional kwargs - MUST have defaults
) -> list[Any]:
    """
    Create {domain} API routes.

    Args:
        app: FastHTML application instance
        rt: Route decorator
        primary_service: {Domain}Service instance
        **related_services: Optional related services (e.g., user_service, goals_service)

    Returns:
        Empty list (sub-factory contract — DomainRouteConfig calls .extend() on result)
    """
    # Register routes via @rt() decorators
    return []
```

### UI Factory Signature

```python
def create_{domain}_ui_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    {domain}_service: ServiceType,
    # Related services are injected BY NAME via ui_related_services — each an explicit kwarg:
    connection_fetch_backend: ConnectionFetchOperations,
    goals_service: GoalsService | None = None,   # optional ones default to None
) -> list[Any]:
    """
    Create {domain} UI routes.

    Args:
        app: FastHTML application instance
        rt: Route decorator
        {domain}_service: {Domain}Service instance (primary service, positional)
        connection_fetch_backend / goals_service / ...: related services injected by
            name via ui_related_services (kwarg_name must match the param name)

    Returns:
        Empty list (sub-factory contract — DomainRouteConfig calls .extend() on result)
    """
    # Register routes via @rt() decorators
    return []
```

**Key requirements:**
1. **First param:** `app` (FastHTML app instance, prefixed with `_` only if unused)
2. **Second param:** `rt` (route decorator)
3. **Third param:** `primary_service` (the domain's main service, positional)
4. **Related services (both API and UI):** declared as explicit **named** kwargs, injected by `register_domain_routes()` from `api_related_services` / `ui_related_services`. Required ones (e.g. `connection_fetch_backend` since PR #75) have no default; optional ones default to `None`. The registration path passes only `primary_service` + these named kwargs — it does **not** inject a whole `services` container.
5. **Two-layer return contract:**
   - **Sub-factories** (`api_factory`/`ui_factory`): return `list[Any]` — never `None`. `register_domain_routes()` calls `.extend()` on the result.
   - **Top-level orchestrators** (`create_{domain}_routes`): return `None` — bootstrap discards the value.

**Note:** A whole-`services` container is the convention for the separate **Orchestrator / Manual hub** wiring (home, explore, today, settings, lifepath, system — wired by hand in bootstrap), not for the DomainRouteConfig path, which injects named services via `ui_related_services`.

## Route Wiring Patterns

SKUEL has three distinct route wiring patterns. Choose deliberately — mixing them without reason creates cognitive load.

### Pattern A: DomainRouteConfig (default — 79% of route files)

Declarative config object + `register_domain_routes()`. Soft-fails when primary service is absent (logs a warning, skips registration).

**Use when:** Standard entity domain with a primary service + optional related services, and distinct `*_api.py` / `*_ui.py` factories.

**Examples:** Every Activity Domain, Ku, PathStep, LearningPath, Exercises, Forms, Finance, Ingestion, Journals, Upload.

### Pattern B: Orchestrator-Driven (3 files)

Route factory creates or receives an orchestrator object that encapsulates cross-domain coordination, then delegates registration to it. Raises `RuntimeError` on missing orchestrator — these routes are required.

**Use when:** Registration requires coordinating multiple services that don't fit a single primary-service model (explore graph + learning state, lateral relationships across all domains, library aggregation).

**Current adopters:** `explore_routes.py`, `lateral_routes.py`, `library_routes.py`.

**Do not add new files here** unless DomainRouteConfig genuinely cannot express the coordination needed.

### Pattern C: Manual `@rt()` (4 files)

Routes registered directly with `@rt()` decorators inside the factory function. No config object. Service-missing behavior is ad-hoc per file.

**Use when:** The routes are structural (auth flow, PWA shell, GraphQL schema mounting, settings page) and don't map to an entity domain. These are stable and unlikely to grow.

**Current adopters:** `home_routes.py`, `settings_routes.py`, `submissions_hub_routes.py`, `graphql_routes.py`.

**Do not use for new entity domains** — reach for DomainRouteConfig instead.

---

### Decision Guide

```
New route file for an entity domain?
  └─ YES → Pattern A (DomainRouteConfig)
      └─ Need cross-domain orchestration a single primary service can't handle?
          └─ YES → Pattern B (Orchestrator-Driven) — justify in docstring
New route file for structural/infrastructure concerns?
  └─ YES → Pattern C (Manual @rt()) — only for auth, shell, schema mounting
```

---

## When to Use DomainRouteConfig

### ✓ Use When:

1. **Standard service extraction** - You need primary service + optional related services
2. **Activity domains** - Tasks, Goals, Habits, Events, Choices, Principles
3. **Other standard domains** - Knowledge, Reports, Finance, Context, Learning
4. **Consistent logging** - You want uniform registration logging
5. **Minimal custom logic** - Route wiring doesn't require complex conditional logic
6. **Separation of API/UI** - You have distinct `*_api.py` and `*_ui.py` files

### ✗ Don't Use When:

1. **Complex conditional logic** - Route registration depends on runtime conditions
2. **Non-standard dependencies** - Services don't follow canonical factory signature
3. **Custom initialization** - Routes require special setup beyond service injection
4. **Full services container needed** - Factory requires entire services object (refactor first)

### Gray Area (Evaluate Case-by-Case):

- **Multiple primary services** - Domain has 2+ core services (consider consolidation first)
- **Mixed initialization** - Some routes need custom logic, others don't (split into separate files)
- **Prototype/experimental** - New domain under active development (defer pattern adoption)

## Migration Guide

### Step 0: Verify Factory Signatures (PREREQUISITE)

**Before migrating,** ensure factories follow canonical signature:

```python
# ✅ CORRECT - canonical signature
def create_reports_api_routes(app, rt, reports_service):
    return []

# ✅ CORRECT - with optional related services
def create_finance_api_routes(app, rt, finance_service, user_service: Any = None):
    return []

# ❌ WRONG - takes full services container
def create_system_api_routes(app, rt, services, sync_service):
    system_service = services.system
    # Must refactor to extract services.system first

# ❌ WRONG - sub-factory doesn't return list (DomainRouteConfig calls .extend())
def create_old_api_routes(app, rt, service):
    # registers routes but returns None
    pass  # Must add: return []
```

**Fix non-canonical signatures BEFORE migration.**

### Step 1: Identify Service Dependencies

**Before (manual pattern):**
```python
def create_tasks_routes(app, rt, services, _sync_service=None):
    tasks_service = getattr(services, "tasks", None)
    user_service = getattr(services, "user_service", None)
    goals_service = getattr(services, "goals", None)
    habits_service = getattr(services, "habits", None)

    if not tasks_service:
        logger.warning("Tasks routes registered without tasks service")
        return []

    api_routes = create_tasks_api_routes(
        app, rt, tasks_service,
        user_service=user_service,
        goals_service=goals_service,
        habits_service=habits_service,
    )
    ui_routes = create_tasks_ui_routes(app, rt, tasks_service)

    logger.info(f"Registered tasks routes: {len(api_routes)} API, {len(ui_routes)} UI")
    return api_routes + ui_routes
```

**Analysis:**
- Primary service: `tasks` → `services.tasks`
- API factory needs: `user_service`, `goals_service`, `habits_service`
- UI factory needs: None (only primary service)

### Step 2: Create DomainRouteConfig

```python
TASKS_CONFIG = DomainRouteConfig(
    domain_name="tasks",              # For logging
    primary_service_attr="tasks",     # services.tasks
    api_factory=create_tasks_api_routes,
    ui_factory=create_tasks_ui_routes,
    api_related_services={
        # Map factory kwargs to container attributes
        "user_service": "user",    # services.user
        "goals_service": "goals",  # services.goals
        "habits_service": "habits",  # services.habits
    },
    # ui_related_services is empty (UI factory only needs primary service)
)
```

### Step 3: Replace Manual Logic

**After (DomainRouteConfig pattern):**
```python
def create_tasks_routes(app, rt, services, _sync_service=None) -> None:
    """Wire tasks API and UI routes using configuration-driven registration."""
    register_domain_routes(app, rt, services, TASKS_CONFIG)
```

### Step 4: Verify Registration

`_wire_all_routes()` in `bootstrap.py` calls DomainRouteConfig routes without per-route logging — a single summary log at the end reports total route count. `register_domain_routes()` logs a warning only when a primary service is missing. No `if services.X:` guard is needed in bootstrap — the soft-fail in `register_domain_routes()` handles `None` services.

### Two-Layer Return Type Contract

FastHTML uses `@rt()` decorators which register routes as a side effect. There are no
route objects to collect. This creates a two-layer return type contract:

**Sub-factories** (`api_factory`/`ui_factory` wired into `DomainRouteConfig`):
- Return `list[Any]` — `register_domain_routes()` calls `.extend()` on the result
- `return []` at the end satisfies the `Callable[..., list[Any]]` type contract
- Returning `None` causes `TypeError: 'NoneType' has no attribute 'extend'`

**Top-level orchestrators** (`create_{domain}_routes` called from `bootstrap.py`):
- Return `None` — bootstrap discards the value
- No `return` statement needed

### Step 5: Test Registration

```bash
# Start application and verify routes are registered
uv run python main.py

# Check logs for registration message
grep "Registered tasks routes" logs/skuel.log
```

## Examples

### Example 1: Single Service (KU)

**File:** `/adapters/inbound/ku_routes.py`

```python
KU_CONFIG = DomainRouteConfig(
    domain_name="ku",
    primary_service_attr="ku",  # services.ku
    api_factory=create_ku_api_routes,
    ui_factory=create_ku_ui_routes,
    api_related_services={"user_service": "user"},  # Services.user
)
```

**Key features:**
- KU routes serve `/ku/*` endpoints only
- PathStep has its own routes in `pathways_routes.py` with `PS_CONFIG` (PsService serves `/path-steps`)
- Demonstrates minimal DomainRouteConfig setup with one related service

### Example 2: API Dependencies Only (Habits)

**File:** `/adapters/inbound/habits_routes.py`

```python
HABITS_CONFIG = create_activity_domain_route_config(
    domain_name="habits",
    primary_service_attr="habits",
    api_factory=create_habits_api_routes,
    ui_factory=create_habits_ui_routes,
    create_schema=HabitCreateRequest,
    update_schema=HabitUpdateRequest,
    uid_prefix="habit",
    api_related_services={
        # Format: {kwarg_name: container_attr}
        # Each entry is passed to api_factory as: kwarg_name=getattr(services, container_attr)
        "principles_service": "principles",  # for link_habit_to_principle ownership check
    },
    ui_related_services={
        "connection_fetch_backend": "connection_fetch_backend",
        "choices_ownership": "choices",  # owner-scopes INFORMS_CHOICE / IMPACTS_HABIT fragments
    },
)
```

**Key features:**
- API factory receives `principles_service` (for cross-domain `POST /api/habits/link-principle` ownership check on the target principle)
- UI factory receives `connection_fetch_backend` and `choices_ownership` as named kwargs via `ui_related_services` — same mapping mechanism, UI side

### Example 3: Multi-Service with UI Dependencies (Finance)

**File:** `/adapters/inbound/finance_routes.py`

```python
FINANCE_CONFIG = DomainRouteConfig(
    domain_name="finance",
    primary_service_attr="finance",
    api_factory=create_finance_api_routes,
    ui_factory=create_finance_ui_routes,
    api_related_services={
        # Format: {kwarg_name: container_attr}
        "user_service": "user",  # user_service=services.user
    },
    ui_related_services={
        # Format: {kwarg_name: container_attr}
        "user_service": "user",  # user_service=services.user
    },
)
```

**Key features:**
- BOTH API and UI need user_service (for admin role checks)
- Demonstrates symmetric dependencies across API/UI layers
- Finance routes require ADMIN role throughout

### Example 4: Optional Dependencies (Askesis)

**File:** `/adapters/inbound/askesis_routes.py`

```python
ASKESIS_CONFIG = DomainRouteConfig(
    domain_name="askesis",
    primary_service_attr="askesis",
    api_factory=create_askesis_api_routes,
    ui_factory=create_askesis_ui_routes,
    api_related_services={
        # Format: {kwarg_name: container_attr}
        # askesis_core_service is optional (Priority 1.1 implementation)
        "askesis_core_service": "askesis_core",  # askesis_core_service=services.askesis_core
    },
)
```

**Key features:**
- Shows optional dependencies (`askesis_core` may be None — routes guard with `if not askesis_core_service:`)
- DomainRouteConfig handles None gracefully via getattr
- Infrastructure dependencies (Neo4j driver) are encapsulated inside services, not passed through config. `AskesisCoreService.build_user_context()` owns the `UserContextBuilder` — routes never touch a raw driver

### Example 5: API-Only Pattern (Transcription)

**File:** `/adapters/inbound/transcription_routes.py`

```python
TRANSCRIPTION_CONFIG = DomainRouteConfig(
    domain_name="transcription",
    primary_service_attr="transcription",
    api_factory=create_transcription_api_routes,
    ui_factory=None,  # No UI routes for this domain
    api_related_services={},
)
```

**Key features:**
- API-only domain (no UI routes needed)
- `ui_factory=None` explicitly indicates no UI component
- Demonstrates single-purpose API services (audio transcription)
- Pattern used by: transcription, visualization, admin

### Example 7: Multi-Factory Pattern (Insights with History Routes)

**File:** `/adapters/inbound/insights_routes.py`

```python
INSIGHTS_CONFIG = DomainRouteConfig(
    domain_name="insights",
    primary_service_attr="insight_store",
    api_factory=create_insights_api_routes,
    ui_factory=create_insights_ui_routes,
    api_related_services={},
)


def create_insights_routes(app, rt, services, _sync_service=None):
    """
    Wire insights API and UI routes using configuration-driven registration.

    Demonstrates multi-factory pattern: DomainRouteConfig handles main routes,
    additional history routes registered separately.
    """
    # Register main API + UI routes via DomainRouteConfig
    routes = register_domain_routes(app, rt, services, INSIGHTS_CONFIG)

    # Additional history routes (separate from main API/UI)
    if services and services.insight_store:
        history_routes = create_insights_history_routes(app, rt, services.insight_store)
        routes.extend(history_routes)
        logger.info(f"  ✅ Insights history routes registered: {len(history_routes)} endpoints")

    return routes
```

**Key features:**
- Uses DomainRouteConfig for standard API + UI routes
- Extends pattern with custom history route registration
- Demonstrates composition: config handles 80% of work, custom logic adds specialized routes
- Pattern: DomainRouteConfig + manual extension (not all-or-nothing)
- History routes are domain-specific (not covered by standard CRUD)

### Example 8: Multi-Domain Composition (Pathways + Path Steps)

**Files:** `/adapters/inbound/pathways_routes.py` + `/adapters/inbound/path_steps_routes.py`

```python
# pathways_routes.py — LP config with IntelligenceRouteConfig (no CRUD — created via ingestion)
PATHWAYS_CONFIG = DomainRouteConfig(
    domain_name="pathways",
    primary_service_attr="lp",
    api_factory=create_pathways_api_routes,
    ui_factory=create_pathways_ui_routes,
    api_related_services={"user_service": "user", "user_progress": "user_progress"},
    ui_related_services={"user_progress": "user_progress", "ps_service": "ls"},
    intelligence=IntelligenceRouteConfig(scope=ContentScope.SHARED),
)

def create_pathways_routes(app, rt, services, _sync_service=None):
    routes = register_domain_routes(app, rt, services, PATHWAYS_CONFIG)
    # PS routes via its own DomainRouteConfig (soft-fail if ls service missing)
    routes.extend(register_domain_routes(app, rt, services, PS_CONFIG))
    return routes
```

```python
# path_steps_routes.py — standalone PS config (no CRUD — created via ingestion)
PS_CONFIG = DomainRouteConfig(
    domain_name="path-steps",
    primary_service_attr="ps",
    api_factory=create_path_steps_api_routes,
    api_related_services={"user_service": "user"},  # Services.user
    intelligence=IntelligenceRouteConfig(scope=ContentScope.SHARED),
)
```

**Key features:**
- Each domain has its own `DomainRouteConfig` with `IntelligenceRouteConfig`
- No `CRUDRouteConfig` — curriculum types (KU, PS, LP) are created via ingestion, not CRUD
- PS config lives in a separate file, imported by `pathways_routes.py`
- Both use `register_domain_routes()` — soft-fail if primary service is missing
- Demonstrates Curriculum domain pattern: `SHARED` intelligence, ingestion-based creation

### Example 9: Self-Contained Facade with Complex UI (LifePath)

**File:** `/adapters/inbound/lifepath_routes.py`

```python
LIFEPATH_CONFIG = DomainRouteConfig(
    domain_name="lifepath",
    primary_service_attr="lifepath",  # services.lifepath
    api_factory=create_lifepath_api_routes,
    ui_factory=create_lifepath_ui_routes,
    api_related_services={},  # Self-contained facade
)
```

**API Routes:** (`lifepath_api.py` - 121 lines)
- 4 JSON endpoints for vision capture, designation, alignment

**UI Routes:** (`lifepath_ui.py` - ~175 lines, thinned 2026-04-07)
- 5 UI routes with sidebar navigation layout
- HTML construction delegated to `ui/lifepath/` (dashboard, vision, alignment, nav)

**Key features:**
- Self-contained service facade (no api_related_services needed)
- All dependencies accessed via facade sub-services (.core, .alignment, .vision, .intelligence)
- Complex drawer layout UI with 7 presentation helper functions
- Carries a vestigial `services: Any = None` param (left over from the 2026-02-03 pass) — it stays `None` because `ui_related_services` is empty here; the factory needs no injected services (self-contained via the facade)
- Main file reduced from 589 → 32 lines (94.6% reduction)
- Demonstrates that even complex drawer layouts work with DomainRouteConfig

**Migration:** 2026-02-03 (see `/docs/migrations/LIFEPATH_ROUTES_MIGRATION_2026-02-03.md`)

---

### Example 10: Standard with UI Optional Dependency (Calendar)

**File:** `/adapters/inbound/calendar_routes.py`

```python
CALENDAR_CONFIG = DomainRouteConfig(
    domain_name="calendar",
    primary_service_attr="calendar",  # services.calendar
    api_factory=create_calendar_api_routes,
    ui_factory=create_calendar_ui_routes,
)
```

**API Routes:** (`calendar_api.py` - 1 route)
- `GET /api/v2/calendar/items/{item_id}` — `@rt` + `@boundary_handler`, returns `Result[Any]`

**UI Routes:** (`calendar_ui.py` - 8 routes)
- 1 redirect: `/events/calendar` → the current month
- 3 page shells: `/events/month/{y}/{m}`, `/events/week/{date}`, `/events/day/{date}` (chrome renders immediately; the grid loads via HTMX)
- 3 HTMX content fragments: month grid, week agenda, day agenda
- 1 HTMX fragment: item-details modal
- Module-level helpers: `_calendar_shell` (shared header + toolbar), page wrapper, navigation aliases (prev/next month/week/day)

**Key features:**
- **Minimal config:** the calendar wires no related services — both factories take only `(app, rt, calendar_service)`. All three views share one visual language via `_calendar_shell` + the component helpers in `ui/calendar/components.py`.
- **Shell + fragment split:** each page shell returns chrome (eyebrow, title, per-type legend, segmented switcher, Prev/Today/Next + Monthly-note toolbar) plus a `content_loading_placeholder`; the matching `*_content` route returns the grid/agenda fragment on HTMX load.
- **Redirect entry point:** `GET /events/calendar` issues a `RedirectResponse` to `/events/month/{y}/{m}` for the current month.
- **Item-details modal:** event chips carry `hx_get=/events/calendar/item-details/{uid}` with `hx_target="body"`, `hx_swap="beforeend"`; the modal manages its own Alpine `open` state.

**Migration:** 2026-02-03 (Phase 5)

---

### Example 12: Multi-Factory with Multiple Extensions (Orchestration)

**File:** `/adapters/inbound/orchestration_routes.py`

```python
ORCHESTRATION_CONFIG = DomainRouteConfig(
    domain_name="orchestration",
    primary_service_attr="goal_task_generator",  # services.goal_task_generator
    api_factory=create_goal_task_routes,         # Primary: 2 endpoints
)


def create_orchestration_routes(app, rt, services, _sync_service=None):
    routes = register_domain_routes(app, rt, services, ORCHESTRATION_CONFIG)

    if services and services.habit_event_scheduler:
        routes.extend(create_habit_event_routes(app, rt, services.habit_event_scheduler))

    if services and services.goals_intelligence:
        routes.extend(create_goals_intelligence_routes(
            app, rt, services.goals_intelligence, services.habits
        ))

    if services and services.principles:
        routes.extend(create_principle_alignment_routes(app, rt, services.principles))

    return routes
```

**Key features:**
- **Three extension factories** beyond the primary — the largest Multi-Factory in the codebase
- Each extension factory is independently guarded: if its service is unavailable, only that group is skipped
- `create_goals_intelligence_routes` receives two services (`goals_intelligence` + `habits`) as positional args — the closure captures both, no config change needed
- All 12 endpoints share a single bootstrap call (`create_orchestration_routes(app, rt, services)`) — zero bootstrap changes from pre-migration
- Primary service (`goal_task_generator`) chosen because it's the namesake orchestration service; the other three groups are extensions by nature

**When to reach for this variant:**
A route file groups endpoints by service rather than by domain. Each group is independently optional. Pick one group as primary; the rest become extension factories.

**Migration:** 2026-02-03 (Phase 6)

---

### Example 13: Multi-Factory with Related Services on Primary (Advanced)

**File:** `/adapters/inbound/advanced_routes.py`

```python
ADVANCED_CONFIG = DomainRouteConfig(
    domain_name="advanced",
    primary_service_attr="calendar_optimization",  # services.calendar_optimization
    api_factory=create_calendar_optimization_routes,
    api_related_services={
        "tasks": "tasks",    # services.tasks  — inline data pull
        "events": "events",  # services.events — inline data pull
    },
)


def create_advanced_routes(app, rt, services, _sync_service=None):
    routes = register_domain_routes(app, rt, services, ADVANCED_CONFIG)

    if services and services.jupyter_sync:
        routes.extend(create_jupyter_sync_routes(app, rt, services.jupyter_sync))

    if services and services.performance_optimization:
        routes.extend(create_performance_routes(app, rt, services.performance_optimization))

    return routes
```

**Key features:**
- **Primary factory pulls related services** (`tasks`, `events`) via `api_related_services` — the calendar optimization endpoints need live task/event data for the target date
- Extension factories are self-contained (each closes over a single service)
- Combines both DomainRouteConfig capabilities: config-driven related-service injection on the primary, manual extension for the rest
- Demonstrates that Multi-Factory and `api_related_services` are composable, not alternatives

**Migration:** 2026-02-03 (Phase 6)

---

## Related Patterns

### Route Factories

**DomainRouteConfig vs Route Factories:**

| Pattern | Scope | Purpose |
|---------|-------|---------|
| DomainRouteConfig | File-level | Wires entire domain (API + UI routes) |
| CRUDRouteFactory | Endpoint-level | Creates CRUD endpoints for single entity |
| StatusRouteFactory | Endpoint-level | Creates status transition endpoints |
| AnalyticsRouteFactory | Endpoint-level | Creates analytics endpoints |

**Usage together:**
```python
# Inside create_tasks_api_routes() - uses route factories
def create_tasks_api_routes(app, rt, tasks_service, user_service, goals_service, habits_service, prometheus_metrics=None):
    routes = []

    # Use CRUDRouteFactory for standard endpoints
    routes.extend(CRUDRouteFactory(
        service=tasks_service.core,
        scope=ContentScope.USER_OWNED,
        ...
    ).create_routes())

    # Use StatusRouteFactory for status changes
    routes.extend(StatusRouteFactory(
        service=tasks_service.core,
        ...
    ).create_routes())

    return routes

# tasks_routes.py - uses DomainRouteConfig
TASKS_CONFIG = DomainRouteConfig(
    api_factory=create_tasks_api_routes,  # Calls function above
    ...
)
```

**See:** `/docs/patterns/ROUTE_FACTORIES.md` for endpoint-level factory details.

### Service Bootstrap

**How services container is populated:**

The `services` parameter comes from `/services_bootstrap/`:

```python
# services_bootstrap/compose.py creates the container
services.tasks = TasksService(...)
services.goals = GoalsService(...)
services.habits = HabitsService(...)
services.user = UserService(...)

# DomainRouteConfig extracts them
primary_service = getattr(services, "tasks")  # From primary_service_attr
goals_service = getattr(services, "goals")    # From api_related_services["goals_service"]
```

**Service attribute naming:**
- Activity domains: Use domain name (e.g., `services.tasks`, `services.goals`)
- Shared services: Use bare domain name (e.g., `services.user`, `services.system`)
- Special cases: `services.event_bus`, `services.sync_service`

### Clean Architecture

**Separation of concerns:**

```
tasks_routes.py (Adapter Layer)
    ↓ wires
tasks_api.py (API Layer)
    ↓ uses
CRUDRouteFactory (Infrastructure Layer)
    ↓ calls
TasksService (Application Layer)
    ↓ uses
Task (Domain Layer)
```

DomainRouteConfig operates at the **Adapter Layer** - it wires API/UI to the application.

## Key Files

### Implementation

- **Core pattern:** `/adapters/inbound/route_factories/domain_route_factory.py`
  - Sub-config dataclasses:
    - `CRUDRouteConfig` (lines 55-65) - CRUD factory parameters
    - `QueryRouteConfig` (lines 68-76) - Query factory parameters
    - `IntelligenceRouteConfig` (lines 79-90) - Intelligence factory sentinel
  - `DomainRouteConfig` dataclass (lines 98-129) - Main configuration
  - `register_domain_routes()` function (lines 132-250) - Registration with config-driven factories
  - `create_activity_domain_route_config()` function (lines 253-320) - Activity Domain convenience function

### Current Users (38 files - 93% adoption)

All DomainRouteConfig routes are registered in Section 2 of `_wire_all_routes()` in `bootstrap.py` without `if services.X:` guards — the soft-fail in `register_domain_routes()` handles missing services.

**Activity (6):**
1. `/adapters/inbound/tasks_routes.py`
2. `/adapters/inbound/goals_routes.py`
3. `/adapters/inbound/habits_routes.py`
4. `/adapters/inbound/events_routes.py`
5. `/adapters/inbound/choices_routes.py`
6. `/adapters/inbound/principles_routes.py`

**Curriculum (6):**
7. `/adapters/inbound/ku_routes.py`
8. `/adapters/inbound/exercises_routes.py`
9. `/adapters/inbound/revised_exercises_routes.py`
10. `/adapters/inbound/pathways_routes.py` - LP + PS routes
11. `/adapters/inbound/askesis_routes.py`

**Submissions/Forms/Journals (4):**
14. `/adapters/inbound/submissions_routes.py`
15. `/adapters/inbound/journals_routes.py` (standalone journal domain)
16. `/adapters/inbound/form_templates_routes.py`
17. `/adapters/inbound/form_submissions_routes.py`

**Other Domains (13):**
17. `/adapters/inbound/finance_routes.py`
18. `/adapters/inbound/lifepath_routes.py`
19. `/adapters/inbound/context_routes.py`
20. `/adapters/inbound/insights_routes.py` (multi-factory)
21. `/adapters/inbound/search_routes.py`
22. `/adapters/inbound/analytics_routes.py`
23. `/adapters/inbound/calendar_routes.py`
24. `/adapters/inbound/ingestion_routes.py`
25. `/adapters/inbound/notifications_routes.py`
26. `/adapters/inbound/groups_routes.py`
27. `/adapters/inbound/teaching_routes.py`
28. `/adapters/inbound/transcription_routes.py`
29. `/adapters/inbound/monitoring_routes.py`

**Infrastructure (3):**
30. `/adapters/inbound/system_routes.py`
31. `/adapters/inbound/admin_routes.py`
32. `/adapters/inbound/auth_routes.py`

**Graph/Visualization (6):**
33. `/adapters/inbound/hierarchy_routes.py`
34. `/adapters/inbound/lateral_routes.py`
35. `/adapters/inbound/visualization_routes.py`
36. `/adapters/inbound/timeline_routes.py`
37. `/adapters/inbound/orchestration_routes.py` (multi-factory)
38. `/adapters/inbound/advanced_routes.py` (multi-factory)

**Hubs (2) — registered via DomainRouteConfig but categorized as Section 2 in bootstrap:**
- `/adapters/inbound/study_routes.py`
- `/adapters/inbound/curriculum_hub_routes.py`

### Justified Exceptions (2 files)

Files with legitimate complexity or minimal overhead warranting custom patterns:

- `graphql_routes.py` - Needs full `services` container for cross-domain GraphQL context (signature normalized)
- `metrics_routes.py` - Single endpoint, minimal overhead

**Note:** `ai_routes.py` was refactored (2026-03-23) to use its own config-driven pattern (`AIRouteSpec` dataclass + signature template factories), reducing 36 hand-written closures to a declarative spec list. Not DomainRouteConfig, but achieves the same goal of configuration over code.

## Common Patterns and Conventions

### Naming Consistency

**File naming:**
- Route file: `{domain}_routes.py`
- Config constant: `{DOMAIN}_CONFIG` (uppercase)
- Factory function: `create_{domain}_routes()`

**Import ordering:**
```python
# 1. API factory
from adapters.inbound.{domain}_api import create_{domain}_api_routes
# 2. UI factory
from adapters.inbound.{domain}_ui import create_{domain}_ui_routes
# 3. Infrastructure
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
```

### Service Attribute Patterns

**Common mappings:**

| Kwarg Name | Container Attr | Service Type |
|------------|----------------|--------------|
| `user_service` | `user` | UserService — `Services.user` (all domains) |
| `goals_service` | `goals` | GoalsService |
| `habits_service` | `habits` | HabitsService |
| `tasks_service` | `tasks` | TasksService |
| `events_service` | `events` | EventsService |
| `choices_service` | `choices` | ChoicesService |
| `principles_service` | `principles` | PrinciplesService |
| `prometheus_metrics` | `prometheus_metrics` | PrometheusMetrics (HTTP instrumentation) |

**Pattern:** Activity domains use short names (`goals`, `tasks`); `UserService` is `"user"` (not `"user_service"`). Infrastructure services (`prometheus_metrics`, `event_bus`) follow the same mapping contract — they live on `Services` alongside domain services and are resolved identically by `api_related_services`.

## Troubleshooting

### Issue: Routes not registered (empty list returned)

**Symptom:**
```
WARNING - Tasks routes registered without tasks service
```

**Cause:** Primary service is None (not available in services container)

**Fix:**
1. Check `services_bootstrap/compose.py` - is the service being created?
2. Verify `primary_service_attr` matches the attribute name on the container
3. Check bootstrap order - is the service created before route registration?

### Issue: Factory function fails with missing kwarg

**Symptom:**
```
TypeError: create_tasks_api_routes() missing required keyword argument 'goals_service'
```

**Cause:** `api_related_services` doesn't include required dependency

**Fix:**
```python
api_related_services={
    "goals_service": "goals",  # Add missing mapping
}
```

### Issue: Wrong service injected

**Symptom:**
Routes work but use wrong service (e.g., gets TasksService instead of GoalsService)

**Cause:** Incorrect container_attr in mapping

**Fix:**
```python
api_related_services={
    # WRONG:
    "goals_service": "tasks",  # Injects services.tasks (TasksService)

    # CORRECT:
    "goals_service": "goals",  # Injects services.goals (GoalsService)
}
```

### Issue: UI routes not registered

**Symptom:**
Logs show "API routes: 15 endpoints" but no "UI routes: X endpoints"

**Cause:** `ui_factory` is None or UI factory signature is incorrect

**Fix:**
1. Verify `ui_factory` is set: `ui_factory=create_{domain}_ui_routes`
2. Ensure the UI factory signature matches: `def create_{domain}_ui_routes(app, rt, {domain}_service, <named related services>)` — related services are positional/keyword params, not a `services` container
3. If the UI factory needs related services (e.g. `connection_fetch_backend`), wire them via `ui_related_services={"kwarg_name": "container_attr"}` so `register_domain_routes()` injects them by name

### Issue: TypeError with api_factory=None (UI-only pattern)

**Symptom:**
```
TypeError: 'NoneType' object is not callable
RuntimeError: Error registering nous routes
```

**Cause:** domain_route_factory.py attempts to call `config.api_factory()` without checking for None

**Fix (infrastructure):**
In `/adapters/inbound/route_factories/domain_route_factory.py` line 103, ensure null check exists:

```python
# ✓ CORRECT - with null check
if config.api_factory:
    api_routes = config.api_factory(app, rt, primary_service, **api_related)

# ✗ WRONG - missing null check
api_routes = config.api_factory(app, rt, primary_service, **api_related)
```

**Status:** Fixed in infrastructure as of 2026-02-03. UI-only pattern (`api_factory=None`) now fully supported.

**Use case:** Content-focused domains like NOUS that only need UI routes (no CRUD API operations)

### Issue: TypeError about NoneType

**Symptom:**
```
TypeError: unsupported operand type(s) for +: 'NoneType' and 'list'
```

**Cause:** Factory returns None instead of list

**Fix:**
```python
def create_{domain}_api_routes(app, rt, service):
    # ... register routes ...
    return []  # Add this line
```

## Performance Considerations

### Registration Time

DomainRouteConfig adds negligible overhead:
- Service extraction: O(n) where n = number of related services (typically 1-4)
- Route wiring: Same as manual pattern (delegates to factories)
- Logging: Minimal string formatting

**Benchmark (12 domains):**
- Manual pattern: ~30ms total registration
- DomainRouteConfig: ~31ms total registration
- Overhead: <1ms (3% increase, acceptable for improved maintainability)

### Runtime Performance

Zero runtime overhead - routes are registered once at application startup.

## Future Directions

### Potential Enhancements

1. **Type safety:** Add Protocols for factory function signatures
2. **Validation:** Pre-flight checks for required services
3. **Auto-discovery:** Automatically detect required services from factory signatures
4. **Middleware support:** Add before/after hooks for route registration
5. **Testing utilities:** Helper functions for testing DomainRouteConfig setups

### Migration Roadmap

**Phase 1 (Complete - 2025):** Activity domains (6/6)
- ✅ Tasks, Goals, Habits, Events, Choices, Principles

**Phase 2 (Complete - 2026-01-24):** Other standard domains (7/7)
- ✅ Learning (LP)
- ✅ Knowledge (KU)
- ✅ Context (UserContext)
- ✅ Reports (Meta-analysis)
- ✅ Finance (Admin bookkeeping)
- ✅ Askesis (AI assistants)
- ✅ Journal Projects

**Phase 3 (Complete - 2026-02-03):** Complex migrations (9/9)
- ✅ Tier 1 (5): Transcription, Visualization, Admin, Auth, Journals
- ✅ Tier 2 (3): System, Ingestion, Insights
- ✅ Tier 3 (1): NOUS (UI-only pattern)

**Phase 4 (Complete - 2026-02-03):** Large drawer layouts
- ✅ LifePath (589 → 32 lines, drawer layout)
- ✅ SEL (730 → 35 lines, drawer layout + categories)

**Phase 5 (Complete - 2026-02-03):** HTMX calendar
- ✅ Calendar (848 → 34 lines, Standard with UI optional dependency)

**Phase 6 (Complete - 2026-02-03):** Multi-Factory extensions
- ✅ Orchestration (387 → 326 lines, Multi-factory with 3 extensions)
- ✅ Advanced (359 → 306 lines, Multi-factory with related services on primary)

**Phase 7 (Complete - 2026-02-04):** Multi-Factory extension
- ✅ Assignments (Multi-factory, sharing extension uses separate primary service)

**Phase 8 (Complete - 2026-02-05):** Config-Driven Factory Registration
- ✅ All 6 Activity Domains (Tasks, Goals, Habits, Events, Choices, Principles)
- CRUD, Query, Intelligence factories moved from api_factory to config
- `create_activity_domain_route_config()` convenience function
- ~80-120 lines removed per domain (Tasks: 264 → 145 lines)
- Schema imports moved to *_routes.py
- StatusRouteFactory, AnalyticsRouteFactory, manual routes stay in api_factory
- 16 comprehensive tests added
- Zero regressions detected

**Phase 9 (Complete - 2026-03-11):** Non-Activity domain migrations (6 files)
- ✅ monitoring_routes.py, study_routes.py (simple migrations; ku_reading_routes.py merged into ku_routes.py)
- ✅ search_routes.py (service-extraction, SearchRouter as primary)
- ✅ hierarchy_routes.py, lateral_routes.py (loop-pattern, multi-service via kwargs)
- graphql_routes.py: signature normalized only (needs full services container)

**Summary:** 42 of 46 route files use DomainRouteConfig or equivalent config-driven patterns (91% adoption). 4 non-adopters: graphql_routes.py, metrics_routes.py, pwa_routes.py, library_routes.py (hub orchestrator). ai_routes.py was refactored (2026-03-23) to use AIRouteSpec config-driven generation. Bootstrap no longer wraps DomainRouteConfig routes in `if services.X:` guards — the soft-fail in `register_domain_routes()` handles missing services.

**Key Achievements:**
- All 4 patterns proven: Standard, API-only, UI-only, Multi-factory
- Config-driven factory registration for Activity Domains
- Multi-factory variant proven at scale: up to 3 extensions + related services on primary
- Infrastructure bug fixed (api_factory=None support)
- UI optional dependency pattern proven (calendar)
- Zero regressions detected across all phases

## References

### Documentation

- **Route Factories:** `/docs/patterns/ROUTE_FACTORIES.md` - Endpoint-level factories
- **Service Bootstrap:** `/services_bootstrap/` - Container creation
- **Clean Architecture:** `/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md` - Layer separation
- **Migration Summaries:**
  - `/docs/migrations/DOMAIN_ROUTE_CONFIG_MIGRATION_2026-01-24.md` - Phase 2 migration (6 files)
  - `/docs/migrations/DOMAIN_ROUTE_CONFIG_MIGRATION_2026-02-03.md` - Phase 3 migration (9 files)

### Related ADRs

- **ADR-030:** User context file consolidation (similar consolidation philosophy)
- **ADR-022:** Graph-native authentication (service extraction patterns)

### External Resources

- **FastHTML docs:** Route registration best practices
- **Dataclass patterns:** Using dataclasses for configuration
- **Dependency injection:** Service container patterns
