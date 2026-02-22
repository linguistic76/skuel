---
name: domain-route-config
description: Expert guide for SKUEL's DomainRouteConfig pattern — configuration-driven route registration for *_routes.py files. Use when wiring domain routes, creating new route files, migrating routes to DomainRouteConfig, or when the user mentions DomainRouteConfig, route registration, routes file, domain routes, register_domain_routes, or *_routes.py.
allowed-tools: Read, Grep, Glob
---

# DomainRouteConfig: Configuration-Driven Route Registration

> "Configuration over code for route registration"

DomainRouteConfig eliminates boilerplate in `*_routes.py` files by replacing ~80 lines of manual service extraction, validation, and wiring with a ~15-line declarative config. Used by 25 of 35 route files (71% adoption). Four proven pattern variants cover every route registration scenario in SKUEL.

---

## Quick Reference

### The 6 Configuration Fields

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `domain_name` | `str` | Yes | Human-readable name for logging (e.g., `"tasks"`) |
| `primary_service_attr` | `str` | Yes | Attribute name on the services container (e.g., `"tasks"` → `services.tasks`) |
| `api_factory` | `Callable \| None` | Yes* | Function that registers API routes. `None` for UI-only domains |
| `ui_factory` | `Callable \| None` | No | Function that registers UI routes. `None` for API-only domains |
| `api_related_services` | `dict[str, str]` | No | Service dependencies for the API factory (see Service Mapping Contract) |
| `ui_related_services` | `dict[str, str]` | No | Service dependencies for the UI factory (deprecated as of 2026-02-03 — UI factories use standard `services` param) |

\* At least one of `api_factory` or `ui_factory` must be non-None.

### Import Surface

```python
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
```

Both are exported from `adapters/inbound/route_factories/__init__.py`. The implementation lives in `adapters/inbound/route_factories/domain_route_factory.py` (119 lines).

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
    "user_service": "user_service",  # kwarg matches attr (common)
    "goals_service": "goals",        # kwarg differs from attr (also common)
}

# register_domain_routes() resolves it at runtime:
api_factory(
    app, rt, primary_service,
    user_service=services.user_service,   # getattr(services, "user_service")
    goals_service=services.goals,         # getattr(services, "goals")
)
```

**Service attribute naming convention:**
- Activity domains use short names: `services.tasks`, `services.goals`, `services.habits`
- Shared services use full names: `services.user_service`
- Special cases: `services.event_bus`, `services.driver`

**None is valid.** If `getattr(services, attr)` returns `None` (service not yet bootstrapped), the `None` is passed through. The factory must handle optional dependencies with default parameters:

```python
def create_tasks_api_routes(app, rt, tasks_service, goals_service=None, ...):
    ...  # goals_service may be None
```

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

## The 4 Pattern Variants

### 1. Standard (API + UI) — Default

**When to use:** Any domain with both API endpoints and UI pages. This is the default for all Activity Domains and most other domains.

**Exemplar:** `adapters/inbound/tasks_routes.py`

```python
from adapters.inbound.tasks_api import create_tasks_api_routes
from adapters.inbound.tasks_ui import create_tasks_ui_routes
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes

TASKS_CONFIG = DomainRouteConfig(
    domain_name="tasks",
    primary_service_attr="tasks",
    api_factory=create_tasks_api_routes,
    ui_factory=create_tasks_ui_routes,
    api_related_services={
        "user_service": "user_service",
        "goals_service": "goals",
        "habits_service": "habits",
    },
)


def create_tasks_routes(app, rt, services, _sync_service=None):
    """Wire tasks API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, TASKS_CONFIG)


__all__ = ["create_tasks_routes"]
```

**Zero related services variant** (simplest form): `adapters/inbound/ku_routes.py`

```python
KU_CONFIG = DomainRouteConfig(
    domain_name="ku",
    primary_service_attr="ku",
    api_factory=create_ku_api_routes,
    ui_factory=create_ku_ui_routes,
    api_related_services={},  # No dependencies beyond primary service
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

### 3. UI-Only — `api_factory=None`

**When to use:** Content-focused domains that only need server-rendered pages, with no CRUD API of their own. Example: Nous (knowledge exploration UI backed by KU's API).

**Critical detail:** `api_factory` is typed as `Callable[..., list[Any]]` (not `Optional`), but the runtime check `if config.api_factory:` in `register_domain_routes()` (line ~97 of `domain_route_factory.py`) handles `None` safely. This null guard was added during the Nous migration — without it, `api_factory=None` would raise `TypeError: 'NoneType' object is not callable`. Do not remove this check.

**Exemplar:** `adapters/inbound/nous_routes.py`

```python
NOUS_CONFIG = DomainRouteConfig(
    domain_name="nous",
    primary_service_attr="ku",           # Nous uses KU's service (no separate service)
    api_factory=None,                    # UI-only — no API routes
    ui_factory=create_nous_ui_routes,
    api_related_services={},
    ui_related_services={},
)
```

Note `primary_service_attr="ku"` — Nous doesn't have its own service; it reuses the KU service. The primary service attr doesn't have to match the domain name.

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
) -> list[Any]:                      # Return [] — @rt() registers as side effect
    ...
    return []
```

### UI Factory (standardized 2026-02-03)

```python
def create_{domain}_ui_routes(
    _app: Any,                       # FastHTML app (prefixed _ if unused)
    rt: Any,                         # Route decorator
    {domain}_service: ServiceType,   # Primary service (positional)
    services: Any = None,            # Full container (standard param, replaces ui_related_services)
) -> list[Any]:
    ...
    return []
```

**Key requirements:**
1. Positional order: `app`, `rt`, `primary_service` — always in this order
2. All related services must have defaults (typically `None`) — they may not be bootstrapped yet
3. Return `list[Any]` — never `None`. FastHTML registers routes via `@rt()` decorator side effects, so the return is always `[]`
4. UI factories use a single `services: Any = None` parameter instead of individual kwargs (2026-02-03 standardization)

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

### 3. Returning None from a factory

```python
# BAD — returns None implicitly
def create_tasks_api_routes(app, rt, tasks_service):
    @rt("/api/tasks")
    async def get_tasks(): ...
    # no return statement → None

# GOOD — always return []
def create_tasks_api_routes(app, rt, tasks_service):
    @rt("/api/tasks")
    async def get_tasks(): ...
    return []
```

The Multi-Factory pattern calls `routes.extend(...)` on the return value. `None.extend()` is a `TypeError`.

### 4. Forgetting the null guard in UI-only domains

```python
# BAD — if someone removes the null guard from domain_route_factory.py:
# config.api_factory(app, rt, ...)  # TypeError when api_factory is None

# The guard at domain_route_factory.py line ~97 MUST stay:
if config.api_factory:
    config.api_factory(app, rt, primary_service, **api_related)
```

Don't refactor `register_domain_routes()` without preserving both null guards (api_factory and ui_factory).

### 5. Using ui_related_services for new code

```python
# BAD — deprecated as of 2026-02-03
ui_related_services={
    "user_service": "user_service",
}

# GOOD — UI factories receive the full services container via standard param
# In the UI factory:
def create_tasks_ui_routes(_app, rt, tasks_service, services=None):
    if services:
        user_service = services.user_service  # Access via container if needed
```

---

## Key Source Files

| File | Role |
|------|------|
| `adapters/inbound/route_factories/domain_route_factory.py` | The dataclass + `register_domain_routes()` — source of truth (119 lines) |
| `adapters/inbound/route_factories/__init__.py` | Export surface: `DomainRouteConfig`, `register_domain_routes` |
| `adapters/inbound/tasks_routes.py` | Exemplar: Standard pattern with related services |
| `adapters/inbound/ku_routes.py` | Exemplar: Standard pattern, no related services |
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
- [ROUTE_FACTORIES.md](/docs/patterns/ROUTE_FACTORIES.md) — Endpoint-level factories (CRUDRouteFactory, StatusRouteFactory) that are called *inside* the factories wired by DomainRouteConfig
- [FASTHTML_ROUTE_REGISTRATION.md](/docs/patterns/FASTHTML_ROUTE_REGISTRATION.md) — Why routes register via decorator side effects (the reason factories return `[]`)

**Migration:**
- [DOMAIN_ROUTE_CONFIG_MIGRATION_2026-02-03.md](/docs/migrations/DOMAIN_ROUTE_CONFIG_MIGRATION_2026-02-03.md) — Phase 3 migration: 9 files, all 4 patterns proven, infrastructure bug fix
