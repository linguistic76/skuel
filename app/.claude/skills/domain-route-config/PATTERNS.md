# DomainRouteConfig Pattern Variants — Problem/Solution Pairs

Problem-solution pairs for each variant, with trade-off analysis and a decision guide.

---

## Pattern Comparison Table

| Pattern | `api_factory` | `ui_factory` | Manual block? | Use When |
|---------|---------------|--------------|---------------|----------|
| **Standard** | ✓ | ✓ | No | Default — API + UI routes |
| **API-Only** | ✓ | `None` | No | No UI pages (data/processing endpoints) |
| **UI-Only** | `None` | ✓ | No | No CRUD API (content display only) |
| **Multi-Factory** | ✓ | ✓ | Yes | Standard routes + a third factory for extras |

---

## Decision Guide

```
Does the domain have API routes?
├── YES
│   ├── Does it also have UI routes?
│   │   ├── YES
│   │   │   ├── Do ALL routes fit into one api_factory + one ui_factory?
│   │   │   │   ├── YES → Standard
│   │   │   │   └── NO  → Multi-Factory (config for main, manual for extras)
│   │   │   └──
│   │   └── NO  → API-Only
│   └──
└── NO
    └── Does it have UI routes?
        ├── YES → UI-Only
        └── NO  → Not a domain route file (nothing to register)
```

---

## Problem 1: Standard (API + UI)

### Problem

A new Activity domain (e.g., Habits) needs both JSON API endpoints and server-rendered pages. Writing manual service extraction, null checks, and wiring for every domain produces near-identical files.

### Solution

```python
HABITS_CONFIG = DomainRouteConfig(
    domain_name="habits",
    primary_service_attr="habits",
    api_factory=create_habits_api_routes,
    ui_factory=create_habits_ui_routes,
    api_related_services={
        "user_service": "user_service",
        "goals_service": "goals",
    },
)

def create_habits_routes(app, rt, services, _sync_service=None):
    return register_domain_routes(app, rt, services, HABITS_CONFIG)
```

### Trade-offs

| Pro | Con |
|-----|-----|
| Consistent across all Activity Domains | Factories must match canonical signature |
| Service extraction is declarative | No custom logic between API and UI registration |
| Soft-fail if primary service is missing | Related services that don't exist return `None` silently |

### When it breaks down

The factory signature contract is rigid: `(app, rt, primary_service, **kwargs)`. If a factory needs something that isn't a service (e.g., a config object, a file path), that dependency doesn't fit the mapping model. In that case, either pass it through a service facade or fall back to a manual route file.

---

## Problem 2: API-Only

### Problem

A domain like Transcription exposes only processing endpoints (`POST /api/transcribe`). There are no pages to render, so a `ui_factory` would be an empty function.

### Solution

```python
TRANSCRIPTION_CONFIG = DomainRouteConfig(
    domain_name="transcription",
    primary_service_attr="transcription",
    api_factory=create_transcription_api_routes,
    ui_factory=None,
    api_related_services={},
)
```

### Trade-offs

| Pro | Con |
|-----|-----|
| Explicit: `None` documents that no UI exists | If UI is added later, config must be updated |
| `register_domain_routes()` skips UI wiring entirely | — |

### When to use vs. Standard

If there's even a single UI page (index, dashboard, settings), use Standard. API-Only is strictly for domains whose user-facing surface is entirely through other domains' UIs (e.g., transcription results appear in the Journals UI).

---

## Problem 3: UI-Only

### Problem

Nous is a knowledge exploration experience backed entirely by KU's API. It needs server-rendered pages but has no CRUD endpoints of its own. Setting `api_factory` to a no-op function would be misleading.

### Solution

```python
NOUS_CONFIG = DomainRouteConfig(
    domain_name="nous",
    primary_service_attr="ku",       # Reuses KU's service
    api_factory=None,                # Explicit: no API routes
    ui_factory=create_nous_ui_routes,
    api_related_services={},
    ui_related_services={},
)
```

### Trade-offs

| Pro | Con |
|-----|-----|
| Explicit intent: `None` documents no API exists | Requires the null guard in `register_domain_routes()` to remain |
| `primary_service_attr` can point to another domain's service | Slightly non-obvious: domain name ≠ service attr |

### The null-guard story

During the Nous migration, `register_domain_routes()` called `config.api_factory(...)` unconditionally. With `api_factory=None`, this raised `TypeError: 'NoneType' object is not callable`. The fix was a one-line guard:

```python
# domain_route_factory.py
if config.api_factory:   # ← this check
    config.api_factory(app, rt, primary_service, **api_related)
```

The symmetric guard for `ui_factory` already existed. **Do not remove either guard** when refactoring `register_domain_routes()`.

---

## Problem 4: Multi-Factory

### Problem

Insights has a standard dashboard (API + UI) plus a separate history page that was added in a later phase. The history routes come from a third factory (`create_insights_history_routes`). Cramming everything into a single `api_factory` or `ui_factory` would violate the single-responsibility constraint.

### Solution

```python
INSIGHTS_CONFIG = DomainRouteConfig(
    domain_name="insights",
    primary_service_attr="insight_store",
    api_factory=create_insights_api_routes,
    ui_factory=create_insights_ui_routes,
    api_related_services={},
)

def create_insights_routes(app, rt, services, _sync_service=None):
    # Config handles the standard 80%
    routes = register_domain_routes(app, rt, services, INSIGHTS_CONFIG)

    # Manual block handles the extra 20%
    if services and services.insight_store:
        history_routes = create_insights_history_routes(app, rt, services.insight_store)
        routes.extend(history_routes)

    return routes
```

### Trade-offs

| Pro | Con |
|-----|-----|
| Config handles the common case; custom code only for exceptions | The manual block reintroduces some of the boilerplate config eliminates |
| Incremental: existing domains can add routes without rewriting | Manual block must mirror the null-guard pattern manually |
| Clean composition: each factory has one job | If many extra factories accumulate, consider a different architecture |

### The null-guard pattern in manual blocks

The manual block mirrors exactly what `register_domain_routes()` does for the primary service:

```python
if services and services.{service_attr}:
    extra = create_extra_routes(app, rt, services.{service_attr})
    routes.extend(extra)
```

Two checks: `services` is not None (container exists), and the specific service attribute is not None (service was bootstrapped). Both are required.

---

## Integration with Route Factories

DomainRouteConfig operates at the **file level** — it wires which factories run. The factories themselves use **endpoint-level** factories internally:

```
tasks_routes.py          ← DomainRouteConfig (file-level wiring)
  └── tasks_api.py       ← create_tasks_api_routes()
        ├── CRUDRouteFactory     ← endpoint-level: create, get, list, update, delete
        └── StatusRouteFactory   ← endpoint-level: activate, complete, archive
```

DomainRouteConfig and CRUDRouteFactory/StatusRouteFactory are not alternatives — they operate at different layers and are used together.
