---
name: ui-orchestrator
description: How to create and wire a UI Orchestrator to resolve Dependency Gravity in Hub pages
---

# UI Orchestrator Skill

## Purpose

This skill guides the creation of **UI Orchestrators** — Application Facade classes that consolidate multiple domain service dependencies into a single injection point for complex Hub/Dashboard UI pages.

## When to Apply

Apply this pattern when a FastHTML route file (or its factory function) requires **4+ distinct domain services** to render its page. Typical indicators:

- The route registration has a long `getattr(services, ...)` or keyword-arg mapping
- The factory function signature lists 5+ service parameters
- Inline data-loading helpers perform concurrent `asyncio.gather` calls across multiple services
- The same multi-step query (e.g., resolve UIDs → batch-fetch entities) is duplicated across handlers

## Files Involved

| File | Role |
|------|------|
| `app/core/orchestrator/{name}_orchestrator.py` | The orchestrator class |
| `app/services_bootstrap/_container.py` | Register the orchestrator in the `Services` dataclass |
| `app/services_bootstrap/compose.py` | Instantiate and wire the orchestrator |
| `app/adapters/inbound/{name}_routes.py` | Simplified route registration |
| `app/adapters/inbound/{name}_ui.py` | Refactored UI factory |

Naming is a template, not a law — some hubs combine routes + UI in one file
(`admin_dashboard_ui.py`, `user_profile_ui.py`, `today_routes.py`), and
`TodayOrchestrator` lives in `ui/today/orchestrator.py` (its output is a view
shape consumed only by the Today page, so it sits with its consumer rather
than in `core/orchestrator/`).

## Step-by-Step

### 1. Create the Orchestrator

```bash
# File: app/core/orchestrator/{name}_orchestrator.py
```

```python
"""
{Name} UI Orchestrator
=======================
Application orchestrator for the {Name} Hub.

All service dependencies are required — bootstrap raises if any are missing
(Fail-Fast Dependency Philosophy).
"""
from typing import TYPE_CHECKING, TypedDict

from core.models.foo import Foo
from core.models.bar import Bar
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.foo_service import FooService
    from core.services.bar_service import BarService
    from core.services.optional_intelligence import OptionalIntelligence


class FooBarView(TypedDict):
    """Bundled view returned by get_foo_bar_view."""
    foo: Foo
    bar: Bar | None


class {Name}Orchestrator:
    """Facade for the {Name} Hub UI layer.

    All service dependencies are required — bootstrap raises if any are missing
    (Fail-Fast Dependency Philosophy).

    ``optional_intelligence`` is the classic legitimate optional: it is ``None``
    when ``INTELLIGENCE_TIER=core``. A service may also be optional for graceful
    degradation of a non-essential hub block (e.g. ``AdminOrchestrator``'s
    ``system_service``, ``TeacherOrchestrator``'s ``admin_stats``) — but every
    optional must have a documented reason; never default a service to ``None``
    just to make wiring easier.
    """

    def __init__(
        self,
        foo_service: "FooService",          # required — no default
        bar_service: "BarService",          # required — no default
        optional_intelligence: "OptionalIntelligence | None",  # legitimate optional (tier)
    ):
        self._foo = foo_service
        self._bar = bar_service
        self._intelligence = optional_intelligence

    # Proxy methods — thin delegations that preserve the service's typed return
    async def get_items(self, user_uid: str) -> Result[list[Foo]]:
        return await self._foo.list_items(user_uid)

    # Compositions — absorb multi-step logic that used to live inline in routes
    async def get_foo_bar_view(self, foo_uid: str, user_uid: str) -> Result[FooBarView]:
        """Fetch foo + its optional bar in one call.

        Collapses the route's fetch → access-check → enrichment dance so the
        route handler becomes a single orchestrator call + one error branch.
        """
        foo_result = await self._foo.get(foo_uid)
        if foo_result.is_error:
            return Result.fail(foo_result)
        foo = foo_result.value

        access = await self._foo.check_access(foo.uid, user_uid)
        if access.is_error or not access.value:
            return Result.fail(Errors.not_found("Foo", foo_uid))

        bar: Bar | None = None
        bar_result = await self._bar.get_by_foo(foo.uid)
        if bar_result.is_ok:
            bar = bar_result.value

        view: FooBarView = {"foo": foo, "bar": bar}
        return Result.ok(view)
```

**Design Rules:**
- Use `TYPE_CHECKING` imports for all service type hints — concrete types, not `Any`
- All required services are positional parameters with **no default** — fail at bootstrap if missing
- Only `INTELLIGENCE_TIER`-gated services are legitimately `| None`
- Never guard required services with `if not self._service` — they are always present
- **Typed returns, not `Result[Any]`.** Every method surfaces the typed model its delegated service already returns (`Result[Task]`, `Result[list[EntryReport]]`, `Result[MyView]`). `Result[Any]` and `**kwargs: Any` are forbidden at this boundary — they throw away type information the service layer spent effort producing. Declare a local `TypedDict` for composite views rather than falling back to `dict[str, Any]`.
- **Proxy methods are thin delegations; compositions absorb real multi-step logic.** If you find a route handler running two or more orchestrator calls in sequence to act on related data (fetch → guard → enrich), that composition belongs on the orchestrator, not in the route. A pass-through-only orchestrator is a dependency bag, not an orchestrator.
- **Cross-Domain Authority Checks.** Orchestrators must enforce UI-level constraints and cross-user context permissions (e.g., verifying a teacher has authority over a given student's timeline) before routing fetching requests to downstream domain services.
- **No scope leak.** A method belongs on an orchestrator only if the hub actually calls it. Single-caller pass-throughs for logic that lives in a different domain should either be inlined at the call site or folded into a composition that owns the orchestration purpose.
- Only add composite methods when a hub page actually calls them — don't build aggregation methods speculatively for pages that don't exist yet

### 2. Register in Container

Edit `app/services_bootstrap/_container.py`:

```python
# Add to the TYPE_CHECKING block:
from core.orchestrator.{name}_orchestrator import {Name}Orchestrator

# Add to the Services dataclass (in the "Orchestrators" section):
{name}_orchestrator: "{Name}Orchestrator | None" = None
```

### 3. Wire in Compose

Edit `app/services_bootstrap/compose.py`. Add the instantiation **after** all domain services are created but **before** the `Services(...)` constructor:

```python
from core.orchestrator.{name}_orchestrator import {Name}Orchestrator

{name}_orchestrator = {Name}Orchestrator(
    service_a=my_service_a,
    service_b=my_service_b,
)
logger.info("✅ {Name} Orchestrator created")
```

Then add to the `Services(...)` constructor:

```python
services = Services(
    ...,
    {name}_orchestrator={name}_orchestrator,
)
```

### 4. Simplify Route Registration

Edit `app/adapters/inbound/{name}_routes.py`:

```python
# Before:
create_{name}_ui_routes(
    app, rt,
    service_a=getattr(services, "a", None),
    service_b=getattr(services, "b", None),
    service_c=getattr(services, "c", None),
)

# After:
assert services.{name}_orchestrator is not None, "{Name}Orchestrator not initialised"
create_{name}_ui_routes(app, rt, orchestrator=services.{name}_orchestrator)
```

Two wiring variants exist in the codebase — both acceptable:
- **Explicit param** (admin): bootstrap asserts and passes `orchestrator=` as above.
- **Extract inside** (profile, today): bootstrap passes the full `services`
  container and the route file pulls `services.{name}_orchestrator` itself
  (with the same not-None assert). Prefer the explicit param for new hubs; use
  extract-inside only when the route file already takes `services` for other
  reasons.

### 5. Refactor UI Factory

Edit `app/adapters/inbound/{name}_ui.py`:

1. **Update the signature:** Replace all service params with `orchestrator: Any`
2. **Replace service calls:** `service_a.method()` → `orchestrator.method()`
3. **Remove unused imports:** e.g., `EntityType` if the filtering moved into the orchestrator
4. **Sidebar compatibility:** If a sidebar renderer still needs raw services, expose them via `@property` on the orchestrator:

```python
@property
def ku_service(self) -> Any:
    return self._ku
```

### 6. Verify

```bash
# Check compilation
uv run python -c "from services_bootstrap.compose import compose_services; print('OK')"

# Check for stale references
grep -rn 'service_a\|service_b' app/adapters/inbound/{name}_ui.py
```

## Existing Orchestrators

| Orchestrator | File | Services | Hub |
|---|---|---|---|
| `AdminOrchestrator` | `admin_orchestrator.py` | 3 | Admin Dashboard |
| `ProfileOrchestrator` | `profile_orchestrator.py` | 7 | User Profile |
| `UserEntryOrchestrator` | `user_entry_orchestrator.py` | 9 | UserEntry (Submissions + Journals / Timeline; owns `get_entry_report_view` + `get_entry` compositions) |
| `ExploreOrchestrator` | `explore_orchestrator.py` | 5 | Explore & Knowledge |
| `LibraryOrchestrator` | `library_orchestrator.py` | 6 | Library / Assets |
| `TeacherOrchestrator` | `teacher_orchestrator.py` | 2 | Teaching & Review |
| `ActivityReviewOrchestrator` | `activity_review_orchestrator.py` | 4 | Activity Review Admin Hub |
| `PathwaysOrchestrator` | `pathways_orchestrator.py` | 2 | Pathways UI |
| `LateralRelationshipsOrchestrator` | `lateral_relationships_orchestrator.py` | 7 | Lateral Relationships API |
| `CalendarOptimizationOrchestrator` | `calendar_optimization_orchestrator.py` | 3 | Calendar Optimization API + cross-domain scheduling intelligence (busy times, slot suggestions, conflict detection, calendar density) |
| `TodayOrchestrator` | `ui/today/orchestrator.py` (view-layer exception) | 7 | Today page |

## Related Pattern: OOB Swaps for Shared-Data Hub Blocks

The Orchestrator pattern solves *service dependency gravity* (many services → one facade). A complementary pattern solves *DB query gravity* on hub preview blocks: when N hub blocks all need the same underlying data, collapsing their N HTMX endpoints into one combined OOB endpoint eliminates duplicate round-trips.

**Example — StudentHub (canonical):**

Before: 3 preview blocks each fired their own endpoint → 3 identical `get_student_submissions()` DB calls.  
After: one `GET /api/teaching/students/{uid}/submissions/preview` endpoint calls `_get_bucketed_submissions()` once and returns 3 OOB fragments.

```python
# Combined endpoint — one DB call, three panel updates
@rt("/api/teaching/students/{uid}/submissions/preview")
async def student_submissions_preview(request, uid, ...):
    pending, revision, completed, _ = await _get_bucketed_submissions(user_uid, uid)

    def _make_fragment(slug, rows, empty_label):
        content = HubPreviewGrid([...]) if rows else HubPreviewEmpty(empty_label)
        return Div(content, id=f"hub-panel-{slug}", hx_swap_oob="true")

    return Div(
        _make_fragment("pending",   pending,   "submissions needing review"),
        _make_fragment("revision",  revision,  "revision requests"),
        _make_fragment("completed", completed, "completed submissions"),
    )
```

```python
# Hub component — passive OOB targets + single hidden trigger
oob_trigger = Div(
    hx_get=f"{base_api}/submissions/preview",
    hx_trigger="load",
    hx_swap="none",   # no main swap — all updates are OOB
)
blocks = [
    HubBlockData(..., slug="pending",   preview_url=None),  # passive OOB target
    HubBlockData(..., slug="revision",  preview_url=None),  # passive OOB target
    HubBlockData(..., slug="completed", preview_url=None),  # passive OOB target
    HubBlockData(..., slug="ku", preview_url=".../ku/preview"),  # independent
]
```

**Decision:** Use OOB when 2+ hub blocks share the same DB query. Blocks with independent queries keep their own `preview_url` and self-load normally.

**See also:** `docs/patterns/HUB_PAGE_PATTERN.md` → "Pattern: OOB Swaps for Shared-Data Hub Blocks" and `ui-browser` skill → "HTMX: Out-of-Band (OOB) Swaps".

## Anti-Patterns to Avoid

1. **God Orchestrator** — One orchestrator serving multiple unrelated pages. Each orchestrator should be 1:1 with a Hub.
2. **API Reuse** — Orchestrators are for the UI rendering layer only. API routes should call domain services directly.
3. **Write-Heavy Orchestrator** — Orchestrators are Read-Model focused. Write operations should be thin pass-throughs.
4. **Duplicate Orchestrator** — If two hubs need the same data, extract a shared service method, don't create overlapping orchestrators.

## Related Docs

- [`UI_ORCHESTRATOR_PATTERN.md`](/docs/patterns/UI_ORCHESTRATOR_PATTERN.md) — Pattern definition
- [`UI_ORCHESTRATION_EXPANSION_PLAN.md`](/docs/roadmap/done/UI_ORCHESTRATION_EXPANSION_PLAN.md) — Roadmap
- [`DOMAIN_ROUTE_CONFIG_PATTERN.md`](/docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md) — The simpler pattern for single-service CRUD pages
