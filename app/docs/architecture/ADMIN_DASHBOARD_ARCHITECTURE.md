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

**Last Updated**: February 8, 2026 (User Statistics Overhaul)
## Related Skills

For implementation guidance, see:
- [@chartjs](../../.claude/skills/chartjs/SKILL.md)


## Overview

The Admin Dashboard provides a centralized UI for system administration at `/admin`. It follows SKUEL's established UI patterns (ProfileLayout, SharedUIComponents) while enforcing ADMIN-only access through role-based decorators.

The overview page displays quick-action cards (Users, Analytics, Finance, Ingestion) in a 3-column grid. The sidebar provides navigation to 7 sections: Overview, Users, Analytics, Learning, System, Finance, and Ingestion.

### User Management Features

The user management section (`/admin/users`) provides:

- **Users table** with inline activity counts (Tasks, Goals, Habits, KUs mastered) per user
- **User detail page** (`/admin/users/{uid}`) with comprehensive statistics:
  - **Activity Domains** — Task/Goal/Habit/Event/Choice/Principle counts with active/completed breakdowns
  - **Learning Progress** — KU viewed/in-progress/mastered counts with link to detailed KU page
  - **Session Activity** — Login and session counts
  - Reports and Report Projects lists
  - Role management and account actions
- **HTMX filtering** — Role and status dropdowns update the table without page reload
- **Data source** — All stats queried via pure Cypher against Neo4j (not UserContext), following the same pattern as the Learning Dashboard

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
│   │   │  Learning    │    │   AdminLearningComponents          │   │   │
│   │   │  System      │    │                                    │   │   │
│   │   │  Finance →   │    │   (from components/admin_*)        │   │   │
│   │   │  Ingestion → │    │                                    │   │   │
│   │   └──────────────┘    └────────────────────────────────────┘   │   │
│   └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      SERVICE LAYER                                       │
│                                                                          │
│   UserService          SystemService         Neo4j Driver (Direct)       │
│   ├─ list_users()      ├─ get_health_status()  ├─ User detail stats     │
│   ├─ get_user()        └─ get_health_summary() ├─ Users list + counts   │
│   ├─ update_role()                             ├─ KU system metrics     │
│   ├─ deactivate_user()                         ├─ User KU progress      │
│   └─ activate_user()                           └─ User KU detail        │
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
│                                # AdminSystemComponents, AdminLearningComponents
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
| `/admin/learning` | GET | KU learning overview | `admin_dashboard_ui.py` |
| `/admin/learning/user/{uid}` | GET | Per-user KU detail | `admin_dashboard_ui.py` |
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
    AdminNavItem("Learning", "learning", "📚", "/admin/learning"),
    AdminNavItem("System", "system", "⚙️", "/admin/system"),
    AdminNavItem("Finance", "finance", "💰", "/finance", badge="→", external=True),
    AdminNavItem("Ingestion", "ingestion", "📥", "/ingest", badge="→", external=True),
]
```

### AdminUIComponents (components/admin_components.py)

User management UI components:

| Method | Purpose |
|--------|---------|
| `render_role_badge(role)` | Color-coded role badge (admin=red, teacher=orange, etc.) |
| `render_status_badge(is_active)` | Active/Inactive status indicator |
| `render_user_card(user)` | Full user card with actions |
| `render_user_table(users)` | Basic tabular user list (legacy) |
| `render_users_table(users)` | Dense table with activity count columns (Tasks, Goals, Habits, KUs) |
| `render_user_activity_stats(stats, uid)` | User detail stats: activity domains + learning + sessions |
| `render_role_change_form(user)` | HTMX role change form |
| `render_user_stats(stats)` | Stats cards (total, by role) |
| `render_role_filter(role)` | Role filter dropdown |
| `render_status_filter(status)` | Status filter dropdown |
| `render_user_reports_list(reports)` | Per-user reports table (user detail page) |
| `render_user_projects_list(projects)` | Per-user report projects table (user detail page) |

### AdminAnalyticsComponents

| Method | Purpose |
|--------|---------|
| `render_analytics_dashboard(data)` | Full analytics view |
| `render_user_distribution(stats)` | Role distribution bars |
| `render_activity_stats(data)` | Activity count cards |

### AdminLearningComponents (components/admin_components.py)

KU learning progression monitoring:

| Method | Purpose |
|--------|---------|
| `render_ku_system_metrics(metrics)` | System-wide KU stats cards (total KUs, viewed, in progress, mastered) |
| `render_user_progress_table(users)` | All-users KU progress table with mastery counts |
| `render_user_ku_summary(summary)` | Individual user KU summary cards |
| `render_user_ku_detail_list(ku_list)` | Per-KU detail table for a user (status, views, time spent) |

**Cypher Helpers** (in `admin_dashboard_ui.py`):

| Function | Purpose |
|----------|---------|
| `_get_user_detail_stats(services, uid)` | 14-field user stats: activity counts, learning, sessions |
| `_get_users_with_activity_counts(services, role, active)` | All users with task/goal/habit/KU counts for list table |
| `_get_ku_system_metrics(services)` | Aggregate KU counts, VIEWED/IN_PROGRESS/MASTERED totals |
| `_get_all_users_ku_progress(services)` | Per-user KU progress (mastered, in_progress, viewed counts) |
| `_get_user_ku_detail(services, uid)` | Detailed KU list for a user with relationship data |

**`_get_user_detail_stats` returns:**

```python
{
    "tasks_total": 0, "tasks_completed": 0,       # OWNS → Task
    "goals_total": 0, "goals_active": 0,           # OWNS → Goal
    "habits_total": 0, "habits_active": 0,          # OWNS → Habit
    "events_total": 0,                              # OWNS → Event
    "choices_total": 0,                             # OWNS → Choice
    "principles_total": 0,                          # OWNS → Principle
    "ku_viewed": 0, "ku_in_progress": 0,            # VIEWED/IN_PROGRESS → Ku
    "ku_mastered": 0,                               # MASTERED → Ku
    "session_count": 0,                             # HAS_SESSION → Session
    "login_count": 0,                               # HAD_AUTH_EVENT → AuthEvent
}
```

All helpers use pure Cypher via `services.neo4j_driver.execute_query()` (no APOC — SKUEL001 compliant). Each returns graceful defaults (`{}` or `[]`) on error.

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

### Data Flow: User Detail Statistics

```
1. Admin navigates to /admin/users/{uid}
   │
   ├─ UserService.get_user(uid) → user identity
   ├─ _get_user_detail_stats(services, uid) → 14-field stats dict
   │     └─ Single Cypher query with incremental WITHs:
   │        OWNS → Task/Goal/Habit/Event/Choice/Principle (counts)
   │        VIEWED/IN_PROGRESS/MASTERED → Ku (learning)
   │        HAS_SESSION/HAD_AUTH_EVENT → Session/AuthEvent (activity)
   ├─ reports_core.get_recent_reports(uid) → reports list
   └─ assignments.list_user_projects(uid) → projects list
   │
   ▼
2. AdminUIComponents.render_user_activity_stats(stats, uid)
   │
   ├─ Activity Domains section (6 stat cards via SharedUIComponents)
   ├─ Learning Progress section (3 stat cards + KU detail link)
   └─ Session Activity section (2 stat cards)
```

**Design decision: Direct Cypher vs UserContext**

The admin user detail page uses direct Neo4j queries rather than `UserContext` because:
- **UserContext** is designed for the logged-in user's intelligence ("What should I work on?")
- **Admin inspection** needs simple counts ("What has this user done?")
- Direct queries are lighter (14 fields vs ~240 in UserContext)
- Follows the existing Learning Dashboard pattern (`_get_ku_system_metrics`, etc.)

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
| `components/admin_components.py` | User/Analytics/System/Learning UI components |
| `adapters/inbound/admin_dashboard_ui.py` | Dashboard UI routes |
| `adapters/inbound/admin_routes.py` | API routes (JSON) |
| `core/auth/roles.py` | @require_admin decorator |
| `scripts/dev/bootstrap.py:332-336` | Route registration |
