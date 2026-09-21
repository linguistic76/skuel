---
title: Route Factory Pattern
updated: '2026-09-21'
category: patterns
related_skills:
- domain-route-config
- fasthtml
related_docs: []
---
# Route Factory Pattern

## Related Skills

For implementation guidance, see:
- [@domain-route-config](../../.claude/skills/domain-route-config/SKILL.md)
- [@fasthtml](../../.claude/skills/fasthtml/SKILL.md)

## Overview

SKUEL uses **route factories** to eliminate boilerplate in API route definitions. Instead of writing 10+ nearly-identical routes per domain, factories generate routes from configuration.

## Available Factories

| Factory | Purpose | Routes Generated |
|---------|---------|------------------|
| **CRUDRouteFactory** | Standard CRUD operations | create, get, update, delete, list |
| **CommonQueryRouteFactory** | Common query patterns | user, by-status, goal, habit |
| **AnalyticsRouteFactory** | Analytics endpoints | domain-specific analytics |
| **IntelligenceRouteFactory** | Intelligence endpoints | context, analytics, insights |
| **create_activity_field_api_routes** | HTMX inline card field updates | POST /api/{domain}/{uid}/{field} (status, priority) |
| **create_activity_hierarchy_api_routes** | Shared Activity Domain hierarchy block | GET children (JSON + HTMX fragment), parent, hierarchy; POST add-child, remove-child |
| **create_activity_link_api_routes** | Cross-domain link endpoints | POST /api/{domain}/link-* → `{"linked": bool}` |
| **create_knowledge_patterns_api_route** | Knowledge-pattern intelligence read | GET /api/{domain}/knowledge-patterns |

The three `create_activity_*` function factories (July 2026) deduplicate the
per-domain `*_api.py` modules: each domain passes an
`ActivityHierarchyApiConfig` / `CrossDomainLinkSpec` tuple with its service
methods, and the factory owns auth, ownership verification, body parsing, and
response shape. The JSON and HTMX children variants render from one
ownership-checked fetch (One Path Forward).

**Field-update response contract.** `POST /api/{domain}/{uid}/{field}` answers a
failed ownership check through `refuse` — the not-found banner at **404**, or "Could
not load" at the fault's own status for a backend failure — swapped into the card slot
on the `X-SKUEL-Refusal` header (OWNERSHIP_VERIFICATION § UI Routes); a value or write
refusal (missing or invalid value, a failed write) is an error banner at 200 that the
card swaps into its own target. A successful update answers
the domain card with `HX-Trigger: {"activity-field-updated": {"domain", "field"}}`
(`FIELD_UPDATED_EVENT` in `activity_field_api_factory.py`), fired on the
requesting element and bubbling. A surface that must react to a *real* update —
the day view reloads after a status change — listens for that event
(`hx_on_activity_field_updated=`, htmx's `hx-on-<event>` spelling), never for
`event.detail.successful`.

## CRUDRouteFactory

Generates 5 standard CRUD routes with automatic ownership verification.

### Usage

```python
from adapters.inbound.route_factories import CRUDRouteFactory
from core.models.enums import ContentScope

# Activity domain (user-owned)
crud_factory = CRUDRouteFactory(
    service=tasks_service,
    domain_name="tasks",
    create_schema=TaskCreateRequest,
    update_schema=TaskUpdateRequest,
    uid_prefix="task",
    scope=ContentScope.USER_OWNED,  # Default - enforces ownership
)
crud_factory.register_routes(app, rt)

# Curriculum domain (shared) — uses FormTemplate as example since
# KU/PS/LP are created via ingestion, not CRUD
crud_factory = CRUDRouteFactory(
    service=form_template_service,
    domain_name="form-templates",
    create_schema=FormTemplateCreateRequest,
    update_schema=EntityUpdateRequest,
    uid_prefix="ft",
    scope=ContentScope.SHARED,  # Shared content, admin-only mutations
    require_role=UserRole.ADMIN,
)
crud_factory.register_routes(app, rt)
```

### Generated Routes

| Method | Path | Operation |
|--------|------|-----------|
| POST | `/api/{domain}/create` | Create |
| GET | `/api/{domain}/get?uid=...` | Get (with ownership check) |
| POST | `/api/{domain}/update?uid=...` | Update (with ownership check) |
| POST | `/api/{domain}/delete?uid=...` | Delete (with ownership check; cascades — OWNS edge means non-cascade could never succeed, G18) |
| GET | `/api/{domain}/list` | List (filtered by user) |

**Note:** the factory's reads and writes take the uid as a query parameter (`?uid=...`). A per-entity door written by hand or by the `create_activity_*` factories takes a path uid (`POST /api/tasks/{uid}/status`, `GET /api/path-steps/{uid}/organizers`) — both shapes are live; the CRUD factory is the query-param one.

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `service` | CRUDOperations[T] | required | Service implementing CRUD protocol |
| `domain_name` | str | required | Domain name for route paths |
| `create_schema` | type[BaseModel] | required | Pydantic schema for creation |
| `update_schema` | type[BaseModel] | required | Pydantic schema for updates |
| `uid_prefix` | str | None | Prefix for generated UIDs |
| `scope` | ContentScope | USER_OWNED | Content ownership model (USER_OWNED or SHARED) |
| `require_role` | UserRole | None | Required role — orthogonal to `scope`: the role check and the ownership check both apply |
| `role_gates_reads` | bool | True | With `require_role` set: `True` gates every route, `False` gates only create/update/delete (the Groups pattern — open reads, teacher-only mutations) |
| `user_service_getter` | Callable | None | Returns the `UserService` the role check reads; required when `require_role` is set |
| `base_path` | str | `/api/{domain}` | Custom base path |
| `request_create_method` | str | None | Name of a request-door create primitive on the service (`(create_schema, user_uid) -> Result[T]`). When set, the create route hands the VALIDATED REQUEST to that method instead of converting to an entity and calling `service.create(entity)`. Resolved fail-fast at construction. All six Activity Domains bind this (`create_task`, `create_goal`, …) so request-only link fields become edges instead of being accepted and silently dropped. |

**Create body → request door vs entity path.** With `request_create_method` set, the
create route is a request-door caller: Pydantic validates the body, then the domain's
primitive runs (validate → persist → admission-guarded edges → `*Created` + ADR-074
embedding events). Without it, the route converts the schema (via `entity_converter` or
the `CONVERTER_REGISTRY`) and calls `service.create(entity)` — fine for domains whose
requests carry no edge-only fields, silent field loss for domains whose requests do.
Guarded by `tests/unit/test_route_create_via_primitive.py`.

**Update body → typed update value (ADR-066).** The update route validates the body with
`update_schema`, then builds the service's update value generically: if the validated
schema is `SupportsToIntent` (every Activity Domain `*UpdateRequest` is — Tasks, Goals,
Habits, Events, Choices, Principles), the factory calls `schema.to_intent()` to produce the
frozen `*UpdateIntent`; otherwise (curriculum, forms, groups, templates) it falls back to a
`RawChanges` patch from `model_dump()`. Either way the value satisfies `SupportsToChanges`,
so the shared base materializes it once at `backend.update(uid, updates.to_changes())`. No
domain wiring is needed beyond pointing `update_schema` at the request model.

## Security: Content Scope

`CRUDRouteFactory`, `CommonQueryRouteFactory` and `IntelligenceRouteFactory` take a `scope`
parameter (default: `ContentScope.USER_OWNED`). `AnalyticsRouteFactory` takes `require_role`
only — its endpoints are user-scoped aggregates with no per-entity uid to verify.

### ContentScope Enum

```python
from core.models.enums import ContentScope

class ContentScope(str, Enum):
    USER_OWNED = "user_owned"  # User-specific with ownership checks
    SHARED = "shared"           # Public/shared, no ownership required
```

### When scope=USER_OWNED (Default)

1. `require_authenticated_user(request)` extracts user_uid (401 if not logged in)
2. `service.verify_ownership(uid, user_uid)` confirms ownership (404 if not owned)
3. Operation proceeds only if both checks pass

### When scope=SHARED

- No ownership verification
- Content accessible to all authenticated users
- Create operations still require authentication

### Domain-to-Scope Mapping

The domains that register a `CRUDRouteFactory` (census: `crud=CRUDRouteConfig(` in
`adapters/inbound/*_routes.py` plus the six `create_activity_domain_route_config` callers):

| Domains | scope | require_role |
|---------|-------|--------------|
| Tasks, Goals, Habits, Events, Choices, Principles | `ContentScope.USER_OWNED` | — |
| Exercises, RevisedExercises | `ContentScope.USER_OWNED` | `UserRole.TEACHER` |
| Groups | `ContentScope.USER_OWNED` | `UserRole.TEACHER`, `role_gates_reads=False` |
| FormTemplates | `ContentScope.SHARED` | `UserRole.ADMIN` |

Ku, PathStep and LearningPath register no CRUD factory — they are created by vault
ingestion. Finance is a Firefly III sidecar (ADR-052) with hand-written admin routes.

### Relationship to require_role

`scope` and `require_role` are orthogonal — the role check gates who may call the
route, the ownership check gates which entity the caller may reach, and both apply
when both are set (`crud_route_factory.py`, the `CRUDRouteFactory.__init__` docstring).
`role_gates_reads=False` narrows the role check to the three mutation routes.

## CommonQueryRouteFactory

Generates common query pattern routes.

```python
from adapters.inbound.route_factories.query_route_factory import CommonQueryRouteFactory

query_factory = CommonQueryRouteFactory(
    service=tasks_service,
    domain_name="tasks",
    supports_goal_filter=True,
    supports_habit_filter=False,
)
query_factory.register_routes(app, rt)
```

### Generated Routes

- `GET /api/{domain}/user` — the caller's entities; `?user_uid=` reads another user's (admin only)
- `GET /api/{domain}/by-status?status=...` — filter by status
- `GET /api/{domain}/goal?goal_uid=...` — entities related to a goal (`supports_goal_filter=True`: Tasks, Principles)
- `GET /api/{domain}/habit?habit_uid=...` — entities related to a habit (`supports_habit_filter=True`: Tasks, Events)

## AnalyticsRouteFactory

Generates analytics endpoints with custom handlers.

```python
from adapters.inbound.route_factories.analytics_route_factory import AnalyticsRouteFactory

async def handle_habit_analytics(service, params):
    uid = params.get("uid")
    period = params.get("period", "month")
    return await service.get_habit_analytics(uid, period)

analytics_factory = AnalyticsRouteFactory(
    service=habits_service,
    domain_name="habits",
    analytics_config={
        "habit_analytics": {
            "path": "/api/habits/analytics",  # Query params: ?uid=...&period=...
            "handler": handle_habit_analytics,
            "description": "Get analytics for a specific habit",
            "methods": ["GET"],
        },
    },
)
analytics_factory.register_routes(app, rt)
```

## IntelligenceRouteFactory

Generates the three routes of the route factory's own `IntelligenceOperations` protocol
(`adapters.inbound.route_factories.IntelligenceOperations` — three methods, distinct from
the ISP protocols in `core.ports.intelligence_protocols`). Eight domains register it —
the six Activity Domains through `create_activity_domain_route_config`, PathSteps and
LearningPaths through `IntelligenceRouteConfig(scope=ContentScope.SHARED)` — 24 routes
(re-count: `./dev health-claims` prints the catalog size; `grep -n IntelligenceRouteConfig
adapters/inbound/*_routes.py` names the two curriculum registrations).

### Clear Boundaries: Intelligence vs Analytics

| Factory | Purpose | Endpoints |
|---------|---------|-----------|
| **IntelligenceRouteFactory** | Standard 3 intelligence primitives | `GET /api/{domain}/context`, `GET /api/{domain}/analytics`, `GET /api/{domain}/insights` |
| **AnalyticsRouteFactory** | Custom domain-specific analytics | one path per config entry — the live consumer registers `GET /api/path-steps/analytics/summary` and `GET /api/path-steps/graph/structure` |

**Use IntelligenceRouteFactory** for the canonical intelligence endpoints that every domain provides.
**Use AnalyticsRouteFactory** for additional domain-specific analytics beyond the standard 3.

### Usage

```python
from adapters.inbound.route_factories import IntelligenceRouteFactory
from core.models.enums import ContentScope

# For Activity Domains (user-owned content)
intelligence_factory = IntelligenceRouteFactory(
    intelligence_service=tasks_service.intelligence,
    domain_name="tasks",
    scope=ContentScope.USER_OWNED,           # Default - enforces ownership
    ownership_service=tasks_service,         # Must implement verify_ownership(uid, user_uid)
)
intelligence_factory.register_routes(app, rt)

# For Curriculum Domains (shared content)
intelligence_factory = IntelligenceRouteFactory(
    intelligence_service=ps_service.intelligence,
    domain_name="path-steps",
    scope=ContentScope.SHARED,               # Curriculum content is shared
)
intelligence_factory.register_routes(app, rt)
```

### Generated Routes

| Method | Path | Operation |
|--------|------|-----------|
| GET | `/api/{domain}/context?uid=...&depth=2` | Entity with graph context |
| GET | `/api/{domain}/analytics?period_days=30` | User performance analytics |
| GET | `/api/{domain}/insights?uid=...&min_confidence=0.7` | Domain-specific insights |

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `intelligence_service` | IntelligenceOperations | required | Service implementing protocol |
| `domain_name` | str | required | Domain name for route paths |
| `base_path` | str | `/api/{domain}` | Custom base path |
| `enable_analytics` | bool | True | Enable analytics route |
| `enable_context` | bool | True | Enable context route |
| `enable_insights` | bool | True | Enable insights route |
| `scope` | ContentScope | USER_OWNED | Content ownership model |
| `ownership_service` | OwnershipVerifier | None | Service for ownership checks (required if scope=USER_OWNED) |

### Route Parameter Style

Routes use FastHTML function parameters with type hints for clean API design:

```python
async def context_route(request: Request, uid: str, depth: int = 2) -> Result[Any]:
async def analytics_route(request: Request, period_days: int = 30) -> Result[Any]:
async def insights_route(request: Request, uid: str, min_confidence: float = 0.7) -> Result[Any]:
```

### Security: Content Scope

When `scope=ContentScope.USER_OWNED`, `ownership_service` is required — the constructor
raises without it (fail-fast: a USER_OWNED factory that cannot verify ownership would be a
cross-user read). On the context and insights routes:
1. `require_authenticated_user(request)` extracts user_uid (401 if not logged in)
2. `ownership_service.verify_ownership(uid, user_uid)` confirms ownership
3. Returns **404** (not 403) to prevent UID enumeration attacks
4. Operation proceeds only if both checks pass

The analytics route is user-scoped (no entity uid) and skips step 2.

**Domain-to-Scope Mapping:**
- **Activity Domains** (user-owned): Tasks, Goals, Habits, Events, Choices, Principles → `scope=ContentScope.USER_OWNED`
- **Curriculum Domains** (shared): PathSteps (`/api/path-steps/*`), LearningPaths (`/api/pathways/*`) → `scope=ContentScope.SHARED`

## When to Use Factories vs Manual Routes

**Use Factories:**
- Standard CRUD operations → CRUDRouteFactory
- Inline card field updates (status, priority) → create_activity_field_api_routes
- Activity hierarchy block (children / parent / hierarchy / add-child / remove-child) → create_activity_hierarchy_api_routes
- Cross-domain link POSTs (owner + optional target verification) → create_activity_link_api_routes
- Common query patterns → CommonQueryRouteFactory

An ownership-verified route with a shape none of these express (a uid list, a verify-through-one-service-call-another, a conditional second entity) is a manual route: `require_authenticated_user` → `verify_entity_ownership` → the service call, in the handler.

**Use Manual Routes:**
- Custom body construction (field remapping, non-standard field names)
- Multi-step orchestration (calling multiple services)
- Extra parameters beyond entity UID (e.g., `option_uid`, `habit_uid`)
- UIDGenerator or ConversionService calls in the route handler

## Key Files

| File | Purpose |
|------|---------|
| `/adapters/inbound/route_factories/crud_route_factory.py` | CRUDRouteFactory |
| `/adapters/inbound/route_factories/query_route_factory.py` | CommonQueryRouteFactory |
| `/adapters/inbound/route_factories/analytics_route_factory.py` | AnalyticsRouteFactory |
| `/adapters/inbound/route_factories/intelligence_route_factory.py` | IntelligenceRouteFactory |
| `/adapters/inbound/route_factories/activity_field_api_factory.py` | create_activity_field_api_routes |
| `/adapters/inbound/route_factories/hierarchy_api_factory.py` | create_activity_hierarchy_api_routes |
| `/adapters/inbound/route_factories/activity_link_api_factory.py` | create_activity_link_api_routes, create_knowledge_patterns_api_route |
| `/adapters/inbound/route_factories/route_helpers.py` | verify_entity_ownership, require_owned_entity, query-param parsers |
| `/adapters/inbound/route_factories/__init__.py` | Exports |

## See Also

### Route Factory Documentation

This file is the canonical reference for route factories. See also:
- `/docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md` — config-driven route registration (builds on factories)

### Related Patterns

- `/docs/patterns/OWNERSHIP_VERIFICATION.md` - Ownership verification pattern
- `/docs/patterns/ERROR_HANDLING.md` - Result[T] error handling
