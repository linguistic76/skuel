# DomainRouteConfig Quick Reference

Fast lookup for copy-paste templates and common pitfalls.

---

## Template 0: Activity Domain — Use for the 6 Activity Domains

The highest-level convenience. Pre-populates CRUD, Query, and Intelligence route factories automatically. Use for Tasks, Goals, Habits, Events, Choices, Principles.

```python
from adapters.inbound.route_factories import (
    create_activity_domain_route_config,
    register_domain_routes,
)
from adapters.inbound.{domain}_api import create_{domain}_api_routes
from adapters.inbound.{domain}_ui import create_{domain}_ui_routes
from core.models.entity_requests import EntityUpdateRequest as {Domain}UpdateRequest
from core.models.{domain}.{domain}_request import {Domain}CreateRequest

{DOMAIN}_CONFIG = create_activity_domain_route_config(
    domain_name="{domain}",
    primary_service_attr="{domain}",
    api_factory=create_{domain}_api_routes,
    ui_factory=create_{domain}_ui_routes,
    create_schema={Domain}CreateRequest,
    update_schema={Domain}UpdateRequest,
    uid_prefix="{domain}",
    supports_goal_filter=False,
    supports_habit_filter=False,
    api_related_services={
        # "goals_service": "goals",  # add as needed
    },
    prometheus_metrics_attr="prometheus_metrics",
)


def create_{domain}_routes(app, rt, services, _sync_service=None):
    return register_domain_routes(app, rt, services, {DOMAIN}_CONFIG)


__all__ = ["create_{domain}_routes"]
```

**Exemplar:** `adapters/inbound/tasks_routes.py` (copy for any Activity Domain)

---

## Template 1: Standard (API + UI) — Non-Activity Domains

Default for any domain with both API and UI routes.

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
        # "factory_kwarg_name": "services_container_attr",
    },
)


def create_{domain}_routes(app, rt, services, _sync_service=None):
    """Wire {domain} API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, {DOMAIN}_CONFIG)


__all__ = ["create_{domain}_routes"]
```

---

## Template 2: API-Only

For domains with no UI pages (e.g., transcription, visualization).

```python
from adapters.inbound.{domain}_api import create_{domain}_api_routes
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes

{DOMAIN}_CONFIG = DomainRouteConfig(
    domain_name="{domain}",
    primary_service_attr="{domain}",
    api_factory=create_{domain}_api_routes,
    ui_factory=None,  # API-only
    api_related_services={},
)


def create_{domain}_routes(app, rt, services, _sync_service=None):
    """Wire {domain} API routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, {DOMAIN}_CONFIG)


__all__ = ["create_{domain}_routes"]
```

---

## Template 3: UI-Only

For content-focused domains with no CRUD API (e.g., Nous). Note: `primary_service_attr` can point to another domain's service.

```python
from adapters.inbound.{domain}_ui import create_{domain}_ui_routes
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes

{DOMAIN}_CONFIG = DomainRouteConfig(
    domain_name="{domain}",
    primary_service_attr="{backing_service}",  # May differ from domain name
    api_factory=None,  # UI-only — null guard in register_domain_routes() handles this
    ui_factory=create_{domain}_ui_routes,
    api_related_services={},
    ui_related_services={},
)


def create_{domain}_routes(app, rt, services, _sync_service=None):
    """Wire {domain} UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, {DOMAIN}_CONFIG)


__all__ = ["create_{domain}_routes"]
```

---

## Template 4: Multi-Factory

DomainRouteConfig for standard routes + manual registration for extras.

```python
from typing import Any

from adapters.inbound.{domain}_api import create_{domain}_api_routes
from adapters.inbound.{domain}_extra_ui import create_{domain}_extra_routes
from adapters.inbound.{domain}_ui import create_{domain}_ui_routes
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.{domain}")

{DOMAIN}_CONFIG = DomainRouteConfig(
    domain_name="{domain}",
    primary_service_attr="{domain}",
    api_factory=create_{domain}_api_routes,
    ui_factory=create_{domain}_ui_routes,
    api_related_services={},
)


def create_{domain}_routes(app: Any, rt: Any, services: Any, _sync_service=None) -> list[Any]:
    """Wire {domain} routes: standard via config, extras manually."""
    # Standard routes via DomainRouteConfig
    routes = register_domain_routes(app, rt, services, {DOMAIN}_CONFIG)

    # Extra routes registered manually (same null-guard pattern)
    if services and services.{domain}:
        extra = create_{domain}_extra_routes(app, rt, services.{domain})
        routes.extend(extra)
        logger.info(f"✅ {Domain} extra routes registered: {{len(extra)}} endpoints")

    return routes


__all__ = ["create_{domain}_routes"]
```

---

## Service Mapping Syntax

```python
api_related_services={
    "kwarg_name": "container_attr",
    # ────────────   ──────────────
    # param name     attr on services
    # in factory     container
}
```

**Common mappings (copy-paste ready):**

| Kwarg Name | Container Attr | When to Use |
|------------|----------------|-------------|
| `"user_service"` | `"user_service"` | Auth / ownership checks |
| `"goals_service"` | `"goals"` | Cross-domain goal linking |
| `"habits_service"` | `"habits"` | Cross-domain habit linking |
| `"tasks_service"` | `"tasks"` | Cross-domain task linking |
| `"events_service"` | `"events"` | Cross-domain event linking |
| `"driver"` | `"driver"` | Direct Neo4j driver access |

---

## Common Pitfalls

| Symptom | Cause | Fix |
|---------|-------|-----|
| Routes silently missing | `container_attr` doesn't match actual attribute on `services` | Check `services_bootstrap.py` for the real attr name |
| `TypeError: 'NoneType' object is not callable` | `api_factory=None` without null guard in `register_domain_routes` | Null guard must exist at `domain_route_factory.py` line ~97 |
| `TypeError: unsupported operand type(s) for +: 'NoneType' and 'list'` | Factory returns `None` instead of `[]` | Add `return []` at end of factory |
| `TypeError: missing required keyword argument` | Factory param not in `api_related_services` | Add the mapping to `api_related_services` |
| Wrong service injected silently | `container_attr` points to wrong service | Verify key → value mapping matches intent |
| UI factory gets unexpected kwargs | Using `ui_related_services` (deprecated) | Switch to `services: Any = None` param in UI factory |
