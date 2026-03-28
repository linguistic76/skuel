---
title: Route Factory Pattern
updated: '2026-03-23'
category: patterns
related_skills:
- fasthtml
related_docs: []
---
# Route Factory Pattern

*Last updated: 2026-03-23*

**March 2026 Update:** Added OwnershipRouteFactory for domain-specific ownership-verified routes (14 routes across 6 Activity Domains). Standardized service getters on `make_service_getter()`.

**January 2026 Update:** Replaced `verify_ownership` boolean parameter with explicit `ContentScope` enum for type-safe ownership patterns.
## Related Skills

For implementation guidance, see:
- [@fasthtml](../../.claude/skills/fasthtml/SKILL.md)


## Overview

SKUEL uses **route factories** to eliminate boilerplate in API route definitions. Instead of writing 10+ nearly-identical routes per domain, factories generate routes from configuration.

## Available Factories

| Factory | Purpose | Routes Generated |
|---------|---------|------------------|
| **CRUDRouteFactory** | Standard CRUD operations | create, get, update, delete, list |
| **StatusRouteFactory** | Status change operations | activate, pause, complete, archive, etc. |
| **CommonQueryRouteFactory** | Common query patterns | by-status, by-category, active, recent |
| **AnalyticsRouteFactory** | Analytics endpoints | domain-specific analytics |
| **IntelligenceRouteFactory** | Intelligence endpoints | context, analytics, insights |
| **QuickAddRouteFactory** | Quick-add form handling | POST /{domain}/quick-add |
| **OwnershipRouteFactory** | Ownership-verified domain routes | domain-specific GET/POST with ownership checks |
| **DashboardUIFactory** | Dashboard + view fragments | GET /{domain}, view/list, view/create, view/{third}, list-fragment |

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

# Curriculum domain (shared)
crud_factory = CRUDRouteFactory(
    service=lesson_service,
    domain_name="lesson",
    create_schema=LessonCreateRequest,
    update_schema=EntityUpdateRequest,
    uid_prefix="l",
    scope=ContentScope.SHARED,  # Curriculum content is shared
)
crud_factory.register_routes(app, rt)
```

### Generated Routes

| Method | Path | Operation |
|--------|------|-----------|
| POST | `/api/{domain}/create` | Create |
| GET | `/api/{domain}/get?uid=...` | Get (with ownership check) |
| POST | `/api/{domain}/update?uid=...` | Update (with ownership check) |
| POST | `/api/{domain}/delete?uid=...` | Delete (with ownership check) |
| GET | `/api/{domain}/list` | List (filtered by user) |

**Note:** SKUEL uses query parameters (`?uid=...`) instead of path parameters (`/{uid}`) for API routes, following FastHTML's "query parameters preferred" pattern.

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `service` | CRUDOperations[T] | required | Service implementing CRUD protocol |
| `domain_name` | str | required | Domain name for route paths |
| `create_schema` | type[BaseModel] | required | Pydantic schema for creation |
| `update_schema` | type[BaseModel] | required | Pydantic schema for updates |
| `uid_prefix` | str | None | Prefix for generated UIDs |
| `scope` | ContentScope | USER_OWNED | Content ownership model (USER_OWNED or SHARED) |
| `require_role` | UserRole | None | Required role (overrides scope when set) |
| `base_path` | str | `/api/{domain}` | Custom base path |

## StatusRouteFactory

Generates status change routes with automatic ownership verification.

### Usage (Simple Pattern)

For services using `(uid, **kwargs)` method signature:

```python
from adapters.inbound.route_factories import StatusRouteFactory, StatusTransition

status_factory = StatusRouteFactory(
    service=goals_service,
    domain_name="goals",
    transitions={
        "activate": StatusTransition(
            target_status="active",
            method_name="activate_goal",
        ),
        "pause": StatusTransition(
            target_status="paused",
            requires_body=True,
            body_fields=["reason", "until_date"],
            method_name="pause_goal",
        ),
        "complete": StatusTransition(
            target_status="completed",
            requires_body=True,
            body_fields=["notes", "date"],
            method_name="complete_goal",
        ),
        "archive": StatusTransition(
            target_status="archived",
            requires_body=True,
            body_fields=["reason"],
            method_name="archive_goal",
        ),
    },
)
status_factory.register_routes(app, rt)
```

### Usage (Typed Request Pattern)

For services using typed request objects (like HabitsService):

```python
from core.models.habit.habit_request import PauseHabitRequest, ResumeHabitRequest

status_factory = StatusRouteFactory(
    service=habits_service,
    domain_name="habits",
    transitions={
        "pause": StatusTransition(
            target_status="paused",
            requires_body=True,
            body_fields=["reason", "until_date"],
            request_builder=lambda uid, fields: PauseHabitRequest(
                habit_uid=uid,
                reason=fields.get("reason", "Paused"),
                until_date=fields.get("until_date"),
            ),
            method_name="pause_habit",
        ),
        "resume": StatusTransition(
            target_status="active",
            request_builder=lambda uid, fields: ResumeHabitRequest(habit_uid=uid),
            method_name="resume_habit",
        ),
    },
)
```

### Usage (Tasks - January 2026)

Tasks uses StatusRouteFactory for complete/uncomplete operations:

```python
status_factory = StatusRouteFactory(
    service=tasks_service,
    domain_name="tasks",
    transitions={
        "complete": StatusTransition(
            target_status="completed",
            requires_body=True,
            body_fields=["actual_minutes", "quality_score"],
            method_name="complete_task",
        ),
        "uncomplete": StatusTransition(
            target_status="in_progress",
            method_name="uncomplete_task",
        ),
    },
)
status_factory.register_routes(app, rt)
```

### Generated Routes

| Method | Path | Operation |
|--------|------|-----------|
| POST | `/api/{domain}/{action}?uid=...` | Status change |

Example: `POST /api/goals/pause?uid=goal.daily-exercise`

### StatusTransition Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `target_status` | str | required | Status value to set |
| `requires_body` | bool | False | Whether route expects JSON body |
| `body_fields` | list[str] | [] | Fields to extract from body |
| `method_name` | str | `{action}_{domain}` | Service method to call |
| `request_builder` | Callable | None | Function to build typed request object |
| `validate` | Callable | None | Optional validation function |
| `success_status` | int | 200 | HTTP status on success |

## OwnershipRouteFactory

Generates ownership-verified routes for domain-specific operations that don't fit CRUD, Status, or Query patterns. Follows the same architecture as StatusRouteFactory.

### Usage

```python
from adapters.inbound.route_factories import OwnershipRouteFactory, OwnershipRoute

ownership_factory = OwnershipRouteFactory(
    service=habits_service,
    domain_name="habits",
    routes=[
        # GET passthrough: service.get_habit_streak(entity_uid)
        OwnershipRoute(
            path="/api/habits/streak",
            method_name="get_habit_streak",
        ),
        # GET with typed query params: service.get_habit_progress(entity_uid, period="month")
        OwnershipRoute(
            path="/api/habits/progress",
            method_name="get_habit_progress",
            query_params={"period": "month"},
        ),
        # POST with Pydantic model: parse_json_body -> service.track_habit(model)
        OwnershipRoute(
            path="/api/habits/track",
            method_name="track_habit",
            request_schema=TrackHabitRequest,
            schema_extra_uid_field="habit_uid",
        ),
    ],
)
ownership_factory.register_routes(app, rt)
```

### Three Call Patterns

| Pattern | Config | Generated Call |
|---------|--------|----------------|
| GET passthrough | `request_schema=None` | `service.method(entity_uid)` |
| GET with params | `query_params={"period": "month", "limit": 20}` | `service.method(entity_uid, period=..., limit=...)` |
| POST with model | `request_schema=X, schema_extra_uid_field="habit_uid"` | `parse_json_body` -> `service.method(model)` |

Query param types are inferred from defaults: `int` defaults produce `int` values, `bool` defaults produce `bool`, everything else stays `str`.

### OwnershipRoute Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | str | required | Route path (e.g., "/api/habits/track") |
| `method_name` | str | required | Service method to call (supports dotted paths like "intelligence.analyze") |
| `request_schema` | type[BaseModel] | None | Pydantic model for POST body |
| `schema_extra_uid_field` | str | None | Field to inject entity UID into (e.g., "habit_uid") |
| `methods` | list[str] | None | HTTP methods (auto: POST if schema, GET otherwise) |
| `query_params` | dict[str, Any] | None | Query param defaults for GET routes |
| `include_user_uid` | bool | False | Pass user_uid as kwarg to service method |
| `success_status` | int | 200 | HTTP status on success |
| `uid_param` | str | None | Override factory-level uid_param for this route |

### Factory Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `service` | OwnershipOperations | required | Service implementing verify_ownership |
| `domain_name` | str | required | Domain name (e.g., "habits") |
| `routes` | list[OwnershipRoute] | required | Route configurations |
| `scope` | ContentScope | USER_OWNED | Content ownership model |
| `uid_param` | str | "uid" | Default query parameter name for entity UID |

### Adoption

14 routes across all 6 Activity Domains:
- **Habits:** track, untrack, streak, progress
- **Tasks:** impact, practice-opportunities
- **Goals:** milestones GET, habits GET
- **Events:** status update, attendees GET
- **Principles:** expressions GET, alignment-history, links GET, related
- **Choices:** impact analysis, predict quality

Routes with custom logic (UIDGenerator, multi-step orchestration, raw body construction) remain manual.

## Security: Content Scope

All factories support `scope` parameter (default: `ContentScope.USER_OWNED`).

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

| Category | Domains | scope |
|----------|---------|-------|
| **Activity** | Tasks, Goals, Habits, Events, Choices, Principles, Finance, Journals | `ContentScope.USER_OWNED` |
| **Curriculum** | KU, LS, LP, MOC | `ContentScope.SHARED` |

### Relationship to require_role

`scope` is orthogonal to `require_role`. When `require_role` is set:
- Role-based access controls everything
- `scope` is ignored (role = access control)
- Example: Finance domain uses `require_role=UserRole.ADMIN`

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

- `GET /api/{domain}/active` - Active entities
- `GET /api/{domain}/by-status?status=...` - Filter by status
- `GET /api/{domain}/recent` - Recently created/modified

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

Generates intelligence routes for the `IntelligenceOperations` protocol (January 2026).

**Rollout Complete (January 2026):** IntelligenceRouteFactory is now active across all 10 domains, generating 30 standardized endpoints.

### Clear Boundaries: Intelligence vs Analytics

| Factory | Purpose | Endpoints |
|---------|---------|-----------|
| **IntelligenceRouteFactory** | Standard 3 intelligence primitives | `/context`, `/analytics`, `/insights` |
| **AnalyticsRouteFactory** | Custom domain-specific analytics | `/analytics/summary`, `/analytics/trends`, etc. |

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
    intelligence_service=lesson_service.intelligence,
    domain_name="lesson",
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
async def context_route(request, uid: str, depth: int = 2) -> Result[dict[str, Any]]:
async def analytics_route(request, period_days: int = 30) -> Result[dict[str, Any]]:
async def insights_route(request, uid: str, min_confidence: float = 0.7) -> Result[list[dict[str, Any]]]:
```

### Security: Content Scope (January 2026)

When `scope=ContentScope.USER_OWNED` and `ownership_service` is provided:
1. `require_authenticated_user(request)` extracts user_uid (401 if not logged in)
2. `ownership_service.verify_ownership(uid, user_uid)` confirms ownership
3. Returns **404** (not 403) to prevent UID enumeration attacks
4. Operation proceeds only if both checks pass

**Domain-to-Scope Mapping:**
- **Activity Domains** (user-owned): Tasks, Goals, Habits, Events, Choices, Principles → `scope=ContentScope.USER_OWNED`
- **Curriculum Domains** (shared): KU, LS, LP, MOC → `scope=ContentScope.SHARED`

## QuickAddRouteFactory

Generates a single POST route for quick-add form handling. Each domain provides callables for entity creation and success/add-another rendering.

### Usage

```python
from adapters.inbound.route_factories import QuickAddConfig, QuickAddRouteFactory

async def create_task_from_form(form_data: dict[str, Any], user_uid: UserUID) -> Result[Task]:
    create_request = parse_task_create_request(form_data)
    return await tasks_service.create_task(create_request, user_uid)

async def render_task_success_view(user_uid: UserUID) -> Any: ...
async def render_task_add_another_view(user_uid: UserUID) -> Any: ...

config = QuickAddConfig(
    domain_name="tasks",
    required_field="title",
    create_entity=create_task_from_form,
    render_success_view=render_task_success_view,
    render_add_another_view=render_task_add_another_view,
)
QuickAddRouteFactory.register_route(rt, config)
```

### Generated Route

- `POST /{domain}/quick-add` — validates required field, runs extra validators, calls `create_entity`, handles add-another vs success response

## DashboardUIFactory

Generates 5 dashboard routes from a `DashboardUIConfig` frozen dataclass. Eliminates ~140 lines of boilerplate per Activity Domain (auth, error handling, view dispatch, page wrapping).

### Usage

```python
from adapters.inbound.route_factories import DashboardUIConfig, DashboardUIFactory

async def fetch_choices_context(user_uid: UserUID, filters: ActivityFilters) -> Any:
    return await choices_service.get_filtered_context(user_uid, filters.status, filters.sort_by)

def build_choices_page_context(svc_ctx: dict[str, Any], filters: ActivityFilters) -> Any:
    return ChoicesPageContext(entities=svc_ctx["entities"], filters=filters.to_dict(), stats=svc_ctx["stats"])

async def render_choices_create(user_uid: UserUID, svc_ctx: dict[str, Any]) -> Any:
    return ChoicesViewComponents.render_create_view(choice_types=CHOICE_TYPES, domains=DOMAINS)

async def render_choices_analytics(user_uid: UserUID, request: Any) -> Any:
    result = await choices_service.get_analytics_context(user_uid)
    if result.is_error:
        return render_error_banner("Failed to load analytics")
    return ChoicesViewComponents.render_analytics_view(analytics_data=result.value)

def render_choices_list_fragment(entities: list[Any]) -> Any:
    items = [ChoicesViewComponents._render_choice_item(c) for c in entities]
    return Div(*items if items else [EmptyState(title="No decisions found")], id="choice-list", cls="space-y-3")

DashboardUIFactory.register_routes(rt, DashboardUIConfig(
    domain_name="choices",
    title="Choices",
    subtitle="Make and track important decisions",
    default_view="list",
    views=("list", "create", "analytics"),
    parse_filters=parse_filters,
    fetch_filtered_context=fetch_choices_context,
    render_view_tabs=ChoicesViewComponents.render_view_tabs,
    render_list_view=ChoicesViewComponents.render_list_view,
    render_create_view=render_choices_create,
    render_third_view=render_choices_analytics,
    build_page_context=build_choices_page_context,
    render_list_fragment=render_choices_list_fragment,
    create_page=create_choices_page,
))
```

### Generated Routes

| Route | Purpose |
|-------|---------|
| `GET /{domain}` | Main dashboard — dispatches to list, create, or third view based on `?view=` param |
| `GET /{domain}/view/list` | HTMX fragment for list view tab |
| `GET /{domain}/view/create` | HTMX fragment for create view tab |
| `GET /{domain}/view/{third}` | HTMX fragment for calendar or analytics view tab |
| `GET /{domain}/list-fragment` | HTMX filtered list for filter updates |

### Variation Points

| Config Field | What It Absorbs |
|-------------|-----------------|
| `parse_filters` | Tasks uses `TaskFilters` (6 fields), Principles uses `PrincipleFilters` (4 fields), others use base `ActivityFilters` |
| `fetch_filtered_context` | Tasks passes 6 args, Principles 4, others 2 — each domain maps its filter object internally |
| `render_create_view` | Async — some domains need additional data (Tasks: projects, Events: event_types) |
| `render_third_view` | Calendar domains fetch all entities + parse calendar params; Analytics domains call a separate service method |
| `render_list_fragment` | Tasks delegates to `TodoistTaskComponents.render_task_list`; others wrap items in a standard Div |

### Two Structural Variants

- **Calendar domains** (Tasks, Goals, Habits, Events): Third view is `"calendar"` — fetches all entities, renders month/week/day
- **Analytics domains** (Choices, Principles): Third view is `"analytics"` — calls domain analytics service

## Migration Statistics

Example from Goals domain:
- Before: 323 lines manual route definitions
- After: ~270 lines with factories
- Reduction: 53 lines (16%)
- CRUD boilerplate eliminated: ~75 lines (88% handled by factory)

Example from Habits domain:
- Before: 334 lines manual route definitions
- After: ~190 lines with factories
- Reduction: ~144 lines (43%)

## When to Use Factories vs Manual Routes

**Use Factories:**
- Standard CRUD operations → CRUDRouteFactory
- Status change patterns → StatusRouteFactory
- Common query patterns → CommonQueryRouteFactory
- Ownership-verified GET/POST with simple service calls → OwnershipRouteFactory

**Use Manual Routes:**
- Custom body construction (field remapping, non-standard field names)
- Multi-step orchestration (calling multiple services)
- Extra parameters beyond entity UID (e.g., `option_uid`, `habit_uid`)
- UIDGenerator or ConversionService calls in the route handler

## Key Files

| File | Purpose |
|------|---------|
| `/adapters/inbound/route_factories/crud_route_factory.py` | CRUDRouteFactory |
| `/adapters/inbound/route_factories/status_route_factory.py` | StatusRouteFactory |
| `/adapters/inbound/route_factories/ownership_route_factory.py` | OwnershipRouteFactory |
| `/adapters/inbound/route_factories/query_route_factory.py` | CommonQueryRouteFactory |
| `/adapters/inbound/route_factories/analytics_route_factory.py` | AnalyticsRouteFactory |
| `/adapters/inbound/route_factories/intelligence_route_factory.py` | IntelligenceRouteFactory |
| `/adapters/inbound/route_factories/quick_add_factory.py` | QuickAddRouteFactory |
| `/adapters/inbound/route_factories/dashboard_ui_factory.py` | DashboardUIFactory |
| `/adapters/inbound/route_factories/__init__.py` | Exports |

## See Also

### Route Factory Documentation

This file is the canonical reference for route factories. See also:
- `/docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md` — config-driven route registration (builds on factories)

### Related Patterns

- `/docs/patterns/OWNERSHIP_VERIFICATION.md` - Ownership verification pattern
- `/docs/patterns/ERROR_HANDLING.md` - Result[T] error handling
