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
from typing import TYPE_CHECKING, Any
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.foo_service import FooService
    from core.services.bar_service import BarService
    from core.services.optional_intelligence import OptionalIntelligence


class {Name}Orchestrator:
    """Facade for the {Name} Hub UI layer.

    All service dependencies are required — bootstrap raises if any are missing
    (Fail-Fast Dependency Philosophy).

    ``optional_intelligence`` is the one legitimate optional: it is ``None``
    when ``INTELLIGENCE_TIER=core``.
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

    # Proxy methods — thin delegations to underlying services
    async def get_items(self, user_uid: str) -> Result[list[Any]]:
        return await self._foo.list_items(user_uid)

    # Aggregation methods — absorb multi-step inline logic
    async def get_hub_summary(self, user_uid: str) -> Result[dict[str, Any]]:
        """Aggregate data from multiple services for the hub page."""
        ...
```

**Design Rules:**
- Use `TYPE_CHECKING` imports for all service type hints — concrete types, not `Any`
- All required services are positional parameters with **no default** — fail at bootstrap if missing
- Only `INTELLIGENCE_TIER`-gated services are legitimately `| None`
- Never guard required services with `if not self._service` — they are always present
- Return `Result` from all public methods
- Proxy methods are thin delegations; aggregation methods absorb real multi-step logic

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
if services and services.{name}_orchestrator:
    create_{name}_ui_routes(app, rt, orchestrator=services.{name}_orchestrator)
```

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
| `ProfileOrchestrator` | `profile_orchestrator.py` | 9 | User Profile |
| `SubmissionsOrchestrator` | `submissions_orchestrator.py` | 9 | Submissions |
| `ExploreOrchestrator` | `explore_orchestrator.py` | 5 | Explore & Knowledge |
| `LibraryOrchestrator` | `library_orchestrator.py` | 6 | Library / Assets |

## Anti-Patterns to Avoid

1. **God Orchestrator** — One orchestrator serving multiple unrelated pages. Each orchestrator should be 1:1 with a Hub.
2. **API Reuse** — Orchestrators are for the UI rendering layer only. API routes should call domain services directly.
3. **Write-Heavy Orchestrator** — Orchestrators are Read-Model focused. Write operations should be thin pass-throughs.
4. **Duplicate Orchestrator** — If two hubs need the same data, extract a shared service method, don't create overlapping orchestrators.

## Related Docs

- [`UI_ORCHESTRATOR_PATTERN.md`](/docs/patterns/UI_ORCHESTRATOR_PATTERN.md) — Pattern definition
- [`UI_ORCHESTRATION_EXPANSION_PLAN.md`](/docs/roadmap/UI_ORCHESTRATION_EXPANSION_PLAN.md) — Roadmap
- [`DOMAIN_ROUTE_CONFIG_PATTERN.md`](/docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md) — The simpler pattern for single-service CRUD pages
