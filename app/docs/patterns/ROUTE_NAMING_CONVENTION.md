---
title: Route File Naming Convention
updated: '2026-02-02'
category: patterns
related_skills:
- fasthtml
related_docs: []
---
# Route File Naming Convention

*Last updated: 2026-01-12*
## Related Skills

For implementation guidance, see:
- [@fasthtml](../../.claude/skills/fasthtml/SKILL.md)


## Overview

SKUEL uses a consistent three-tier pattern for route file organization in `/adapters/inbound/`.

## Standard Naming Pattern

| Tier | Purpose | Naming | Example |
|------|---------|--------|---------|
| **Entry Point** | Wiring factory that composes API + UI | `{domain}_routes.py` | `tasks_routes.py` |
| **API Layer** | Pure JSON REST endpoints | `{domain}_api.py` | `tasks_api.py` |
| **UI Layer** | FastHTML HTML rendering | `{domain}_ui.py` | `tasks_ui.py` |

## Architecture

```
{domain}_routes.py    <- Entry point (thin wiring factory)
    |
    +-- imports {domain}_api.py   <- Pure JSON API endpoints
    |
    +-- imports {domain}_ui.py    <- FastHTML HTML rendering
```

## Example: Tasks Domain

```python
# tasks_routes.py (entry point)
from adapters.inbound.tasks_api import create_tasks_api_routes
from adapters.inbound.tasks_ui import create_tasks_ui_routes

def create_tasks_routes(app, rt, services):
    create_tasks_api_routes(app, rt, services.tasks)
    create_tasks_ui_routes(app, rt, services.tasks)
```

## Domains Using This Pattern

| Domain | Entry Point | API | UI |
|--------|-------------|-----|-----|
| Tasks | `tasks_routes.py` | `tasks_api.py` | `tasks_ui.py` |
| Goals | `goals_routes.py` | `goals_api.py` | `goals_ui.py` |
| Habits | `habits_routes.py` | `habits_api.py` | `habits_ui.py` |
| Events | `events_routes.py` | `events_api.py` | `events_ui.py` |
| Choices | `choices_routes.py` | `choices_api.py` | `choice_ui.py` |
| Principles | `principles_routes.py` | `principles_api.py` | `principles_ui.py` |
| Knowledge | `knowledge_routes.py` | `knowledge_api.py` | `knowledge_ui.py` |
| Pathways | `pathways_routes.py` | `pathways_api.py` | `pathways_ui.py` |
| Reports | `reports_routes.py` | `reports_api.py` | `reports_ui.py` |
| Askesis | `askesis_routes.py` | `askesis_api.py` | `askesis_ui.py` |
| Context | `context_routes.py` | `context_aware_api.py` | `context_aware_ui.py` |

## Standalone Routes (No Three-Tier)

Some routes don't need the three-tier pattern:

| File | Reason |
|------|--------|
| `auth_routes.py` | Authentication only (no separate UI) |
| `search_routes.py` | Search aggregation service |
| `admin_routes.py` | Admin API + UI combined |
| `calendar_routes.py` | Calendar aggregation |
| `ingestion_routes.py` | Content ingestion |

## Naming Conventions

1. **Use plural names**: `tasks_`, `goals_`, `habits_`, `choices_` (not singular)
2. **Entry point is `_routes.py`**: Not `_factory.py` or `_routes_clean.py`
3. **API is `_api.py`**: Pure JSON endpoints
4. **UI is `_ui.py`**: FastHTML HTML rendering

## Migration History

- **2026-01-12**: Renamed `_routes_clean.py` files to `_routes.py`
- **2026-01-12**: Renamed `choice_api.py` to `choices_api.py` for plural consistency

## See Also

- `/docs/patterns/ROUTE_FACTORIES.md` - Route factory patterns (CRUDRouteFactory, etc.)
- `/docs/patterns/FASTHTML_ROUTE_REGISTRATION.md` - FastHTML route registration patterns
- `/.claude/skills/fasthtml/routing-patterns.md` - FastHTML routing patterns
