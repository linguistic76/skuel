---
title: Admin Dashboard Architecture
updated: 2025-12-07
status: current
category: architecture
tags:
- architecture
- admin
- ui
- dashboard
- security
related:
- ROUTING_ARCHITECTURE.md
- USER_MODEL_ARCHITECTURE.md
related_skills:
- chartjs
---

# Admin Dashboard Architecture

**Last Updated**: December 7, 2025
## Related Skills

For implementation guidance, see:
- [@chartjs](../../.claude/skills/chartjs/SKILL.md)


## Overview

The Admin Dashboard provides a centralized UI for system administration at `/admin`. It follows SKUEL's established UI patterns (ProfileLayout, SharedUIComponents) while enforcing ADMIN-only access through role-based decorators.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         ADMIN DASHBOARD                                  │
│                         /admin/*                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      SECURITY LAYER                                      │
│                                                                          │
│   @require_admin(get_user_service)                                      │
│       ↓                                                                  │
│   Validates: 1. Authenticated (401 if not)                              │
│              2. ADMIN role (403 if not)                                 │
│              3. Injects current_user into handler                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      UI LAYER                                            │
│                                                                          │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │ AdminLayout (ui/admin/layout.py)                                │   │
│   │                                                                  │   │
│   │   ┌──────────────┐    ┌────────────────────────────────────┐   │   │
│   │   │   Sidebar    │    │         Main Content               │   │   │
│   │   │              │    │                                    │   │   │
│   │   │  Overview    │    │   AdminUIComponents                │   │   │
│   │   │  Users       │    │   AdminAnalyticsComponents         │   │   │
│   │   │  Analytics   │    │   AdminSystemComponents            │   │   │
│   │   │  System      │    │                                    │   │   │
│   │   │  Finance →   │    │   (from components/admin_*)        │   │   │
│   │   │              │    │                                    │   │   │
│   │   └──────────────┘    └────────────────────────────────────┘   │   │
│   └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      SERVICE LAYER                                       │
│                                                                          │
│   UserService          SystemService         Domain Services             │
│   ├─ list_users()      ├─ get_health_status()  ├─ tasks_service         │
│   ├─ get_user()        └─ get_health_summary() ├─ habits_service        │
│   ├─ update_role()                             ├─ goals_service         │
│   ├─ deactivate_user()                         └─ ...                   │
│   └─ activate_user()                                                    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## File Structure

```
/home/mike/skuel/app/
├── ui/admin/
│   ├── __init__.py              # Module exports
│   └── layout.py                # AdminLayout, AdminNavItem, create_admin_page
│
├── components/
│   └── admin_components.py      # AdminUIComponents, AdminAnalyticsComponents,
│                                # AdminSystemComponents
│
├── adapters/inbound/
│   ├── admin_routes.py          # API routes (/api/admin/users/*)
│   └── admin_dashboard_ui.py    # UI routes (/admin/*)
│
└── scripts/dev/
    └── bootstrap.py             # Route registration (lines 332-336)
```

---

## Route Structure

| Route | Method | Purpose | File:Line |
|-------|--------|---------|-----------|
| `/admin` | GET | Overview dashboard | `admin_dashboard_ui.py:61` |
| `/admin/users` | GET | User management list | `admin_dashboard_ui.py:125` |
| `/admin/users/{uid}` | GET | User detail view | `admin_dashboard_ui.py:232` |
| `/admin/users/partial` | GET | HTMX filtered list | `admin_dashboard_ui.py:181` |
| `/admin/users/{uid}/role-form` | GET | HTMX role change form | `admin_dashboard_ui.py:307` |
| `/admin/analytics` | GET | Analytics dashboard | `admin_dashboard_ui.py:329` |
| `/admin/system` | GET | System health | `admin_dashboard_ui.py:391` |

### Existing API Endpoints (Reused)

| Route | Method | Purpose | File |
|-------|--------|---------|------|
| `/api/admin/users` | GET | List users (JSON) | `admin_routes.py:59` |
| `/api/admin/users/{uid}` | GET | Get user (JSON) | `admin_routes.py:119` |
| `/api/admin/users/{uid}/role` | POST | Change role | `admin_routes.py:170` |
| `/api/admin/users/{uid}/deactivate` | POST | Deactivate | `admin_routes.py:237` |
| `/api/admin/users/{uid}/activate` | POST | Activate | `admin_routes.py:288` |

---

## Component Architecture

### AdminLayout (ui/admin/layout.py)

Follows the ProfileLayout pattern with admin-specific navigation:

```python
@dataclass
class AdminNavItem:
    name: str       # "Users"
    slug: str       # "users"
    icon: str       # Emoji
    href: str       # "/admin/users"
    badge: str | None = None
    external: bool = False  # For Finance link

ADMIN_NAV_ITEMS = [
    AdminNavItem("Overview", "overview", "📊", "/admin"),
    AdminNavItem("Users", "users", "👥", "/admin/users"),
    AdminNavItem("Analytics", "analytics", "📈", "/admin/analytics"),
    AdminNavItem("System", "system", "⚙️", "/admin/system"),
    AdminNavItem("Finance", "finance", "💰", "/finance", badge="→", external=True),
]
```

### AdminUIComponents (components/admin_components.py)

User management UI components:

| Method | Purpose |
|--------|---------|
| `render_role_badge(role)` | Color-coded role badge (admin=red, teacher=orange, etc.) |
| `render_status_badge(is_active)` | Active/Inactive status indicator |
| `render_user_card(user)` | Full user card with actions |
| `render_user_table(users)` | Tabular user list |
| `render_role_change_form(user)` | HTMX role change form |
| `render_user_stats(stats)` | Stats cards (total, by role) |
| `render_role_filter(role)` | Role filter dropdown |
| `render_status_filter(status)` | Status filter dropdown |

### AdminAnalyticsComponents

| Method | Purpose |
|--------|---------|
| `render_analytics_dashboard(data)` | Full analytics view |
| `render_user_distribution(stats)` | Role distribution bars |
| `render_activity_stats(data)` | Activity count cards |

### AdminSystemComponents

| Method | Purpose |
|--------|---------|
| `render_health_dashboard(data)` | System health view |
| `render_overall_status(status)` | Status indicator (healthy/warning/critical) |
| `render_component_health_card(name, data)` | Individual component status |
| `render_components_grid(components)` | Grid of component cards |
| `render_health_summary(summary)` | Stats cards for components |

---

## Security Model

### Role-Based Access Control

All admin routes use `@require_admin` decorator:

```python
def get_user_service():
    return services.user_service

@rt("/admin/users")
@require_admin(get_user_service)
@boundary_handler()
async def admin_users_list(request, current_user: Any):
    # current_user is injected by decorator
    # Guaranteed to be ADMIN role
    ...
```

### Role Hierarchy

```
REGISTERED (0) < MEMBER (1) < TEACHER (2) < ADMIN (3)
```

### HTTP Status Codes

| Status | Condition |
|--------|-----------|
| 200 | Success |
| 401 | Not authenticated |
| 403 | Authenticated but not ADMIN |
| 404 | User not found |

### Navbar Integration

When an admin is logged in, the navbar shows "Admin Dashboard" instead of "Profile Hub":

```python
# ui/layouts/navbar.py
def create_navbar(
    current_user: str | None = None,
    is_authenticated: bool = False,
    active_page: str = "",
    is_admin: bool = False,  # Shows Admin Dashboard if True
) -> NotStr:
```

**How `is_admin` is determined:**

- Admin pages (`/admin/*`): Always pass `is_admin=True`
- Profile pages (`/profile/*`): Check `user.can_manage_users()`
- Other pages: Can use `is_current_user_admin(request, user_service)` helper

**Helper function:**

```python
from core.auth import is_current_user_admin

# In route function
is_admin = await is_current_user_admin(request, services.user_service)
navbar = create_navbar(..., is_admin=is_admin)
```

---

## HTMX Integration

The dashboard uses HTMX for dynamic updates without full page reloads:

### User Filtering

```html
<!-- Role filter triggers partial update -->
<select hx-get="/admin/users/partial"
        hx-target="#user-list"
        hx-trigger="change"
        hx-include="[name='status']">
```

### Role Change Form

```html
<!-- Load form inline -->
<button hx-get="/admin/users/{uid}/role-form"
        hx-target="#role-form-{uid}"
        hx-swap="innerHTML">
    Edit Role
</button>

<!-- Form submits via HTMX -->
<form hx-post="/api/admin/users/{uid}/role"
      hx-swap="outerHTML"
      hx-target="#user-card-{uid}">
```

---

## Data Flow Example: Change User Role

```
1. Admin clicks "Edit Role" on user card
   │
   ▼
2. HTMX GET /admin/users/{uid}/role-form
   │
   ▼
3. Server returns role change form HTML
   │
   ▼
4. Form inserted into #role-form-{uid}
   │
   ▼
5. Admin selects new role, clicks Save
   │
   ▼
6. HTMX POST /api/admin/users/{uid}/role
   │
   ▼
7. API validates, calls UserService.update_role()
   │
   ▼
8. Server returns updated user card HTML
   │
   ▼
9. HTMX replaces #user-card-{uid} with new content
```

---

## Patterns Used

### 1. Layout Pattern (ProfileLayout → AdminLayout)

Sidebar + content layout with:
- Collapsible sidebar on desktop
- Overlay drawer on mobile
- localStorage persistence for sidebar state

### 2. Component Composition (SharedUIComponents)

Reuses stats cards pattern:

```python
AdminUIComponents.render_user_stats(stats)
# Uses SharedUIComponents.render_stats_cards internally
```

### 3. Named Function Pattern (SKUEL012)

No lambdas in route decorators:

```python
# ✅ Correct
def get_user_service():
    return services.user_service

@require_admin(get_user_service)

# ❌ Wrong (SKUEL012 violation)
@require_admin(lambda: services.user_service)
```

### 4. Result[T] with @boundary_handler

All routes return Result[T], converted to HTTP at boundaries:

```python
@rt("/admin/users")
@require_admin(get_user_service)
@boundary_handler()  # Converts Result[T] → HTTP response
async def admin_users_list(request, current_user):
    # Return Result.ok(...) or Result.fail(...)
```

---

## Adding New Admin Sections

To add a new admin section (e.g., `/admin/logs`):

### 1. Add Navigation Item

```python
# ui/admin/layout.py
ADMIN_NAV_ITEMS = [
    ...
    AdminNavItem("Logs", "logs", "📋", "/admin/logs"),
]
```

### 2. Add Components (if needed)

```python
# components/admin_components.py
class AdminLogsComponents:
    @staticmethod
    def render_log_entry(log: dict) -> Div:
        ...
```

### 3. Add Route

```python
# adapters/inbound/admin_dashboard_ui.py
@rt("/admin/logs")
@require_admin(get_user_service)
@boundary_handler()
async def admin_logs(request, current_user: Any):
    content = Div(...)
    return create_admin_page(
        content=content,
        active_section="logs",
        admin_username=current_user.display_name,
        title="Logs",
    )
```

---

## Related Documentation

- **User Roles**: `/docs/decisions/ADR-018-user-roles-four-tier-system.md`
- **Route Patterns**: `/docs/patterns/ROUTE_FACTORIES.md`
- **SharedUIComponents**: `/docs/patterns/COMPONENT_PATTERNS.md` (TODO)
- **ProfileLayout**: `/ui/profile/layout.py` (reference implementation)

---

## Key Files Quick Reference

| File | Purpose |
|------|---------|
| `ui/admin/layout.py` | AdminLayout, AdminNavItem, create_admin_page |
| `components/admin_components.py` | User/Analytics/System UI components |
| `adapters/inbound/admin_dashboard_ui.py` | Dashboard UI routes |
| `adapters/inbound/admin_routes.py` | API routes (JSON) |
| `core/auth/roles.py` | @require_admin decorator |
| `scripts/dev/bootstrap.py:332-336` | Route registration |
