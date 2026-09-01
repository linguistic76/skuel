---
title: Admin Dashboard Architecture
updated: 2026-07-10
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
- UNIFIED_USER_ARCHITECTURE.md
related_skills:
- chartjs
- ui-orchestrator
---
# Admin Dashboard Architecture

**Last Updated**: April 7, 2026 (AdminOrchestrator — resolved dependency gravity)

## Related Skills

For implementation guidance, see:
- [@chartjs](../../.claude/skills/chartjs/SKILL.md)
- [@ui-orchestrator](../../.claude/skills/ui-orchestrator/SKILL.md)

## Overview

The Admin Dashboard provides a centralized UI for system administration at `/admin`. It follows SKUEL's established UI patterns (ProfileLayout, StatsGrid) while enforcing ADMIN-only access through role-based decorators.

The overview page displays quick-action cards (Users, Analytics, Finance, Ingestion) in a 3-column grid. The sidebar provides navigation to 6 sections: Overview, Users, Analytics, System, Finance, and Ingestion.

> **Note:** KU progression tracking is a pedagogical concern — accessible per-student at `/teaching/students/{uid}/submissions?tab=ku` (KU Progress section), not a sysadmin tool.

### User Management Features

The user management section (`/admin/users`) provides:

- **Users table** with inline activity counts (Tasks, Goals, Habits, KUs mastered) per user
- **User detail page** (`/admin/users/{uid}`) focused on account management:
  - **Activity Domains** — Task/Goal/Habit/Event/Choice/Principle counts with active/completed breakdowns
  - **Learning Progress** — KU viewed/in-progress/mastered counts with link to `/teaching/students/{uid}` (student hub)
  - **Session Activity** — Login and session counts
  - Links to `/teaching/students/{uid}` (student hub with HTMX preview blocks: Needs Review, Revision Requested, Completed, KU Progress)
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
│   │   │  System      │    │                                    │   │   │
│   │   │  Finance →   │    │   (from ui/admin/)        │   │   │
│   │   │  Ingestion → │    │                                    │   │   │
│   │   └──────────────┘    └────────────────────────────────────┘   │   │
│   └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      ORCHESTRATOR LAYER                                  │
│                                                                          │
│   AdminOrchestrator  (core/orchestrator/admin_orchestrator.py)          │
│   ├─ get_system_status()          → SystemService.get_health_status()   │
│   ├─ get_full_health_status()     → SystemService (with error guard)    │
│   ├─ get_user(uid)                → UserService.get_user()              │
│   ├─ get_users_with_activity_counts() → AdminStatsService               │
│   ├─ get_user_role_counts()       → AdminStatsService                   │
│   ├─ get_user_detail_stats(uid)   → AdminStatsService                   │
│   ├─ _get_activity_entity_counts() → AdminStatsService (private)        │
│   └─ get_analytics_data()         → role_counts + entity_counts +      │
│                                      search gaps/event total            │
│                                                                          │
│   user_service property           → exposed for @require_admin          │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      SERVICE LAYER                                       │
│                                                                          │
│   UserService          SystemService         AdminStatsService            │
│   ├─ list_users()      ├─ get_health_status()  ├─ get_user_detail_stats()│
│   ├─ get_user()        └─ get_health_summary() ├─ get_users_with_activity_counts()│
│   ├─ update_role()                             ├─ get_entity_system_metrics()│
│   ├─ deactivate_user()                         ├─ get_all_users_progress()│
│   └─ activate_user()                           ├─ get_user_ku_detail()   │
│                                                ├─ get_activity_entity_counts()│
│                                                └─ get_user_role_counts() │
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

ADMIN_SIDEBAR_ITEMS = [
    SidebarItem("Overview", "/admin", "overview", icon="📊"),
    SidebarItem("Users", "/admin/users", "users", icon="👥"),
    SidebarItem("Analytics", "/admin/analytics", "analytics", icon="📈"),
    SidebarItem("System", "/admin/system", "system", icon="⚙️"),
    SidebarItem("Finance", "/finance", "finance", icon="💰", badge_text="→"),
    SidebarItem("Ingestion", "/ingest", "ingestion", icon="📥", badge_text="→"),
]
# KU progress accessible per-student at /teaching/students/{uid}/submissions?tab=ku
```

### AdminUIComponents (ui/admin/views.py)

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

### AdminAnalyticsComponents

| Method | Purpose |
|--------|---------|
| `render_analytics_dashboard(data)` | Full analytics view |
| `render_user_distribution(stats)` | Role distribution bars |
| `render_activity_stats(data)` | Activity count cards |
| `render_search_gaps(gaps, event_total)` | Zero/low-result search queue table + running `:SearchEvent` total vs the Phase-2 trigger |

### AdminLearningComponents (ui/admin/views.py)

KU learning progression components — **used by the Teaching student submissions page** (`/teaching/students/{uid}/submissions?tab=ku`), not by admin routes.

| Method | Purpose |
|--------|---------|
| `render_ku_system_metrics(metrics)` | System-wide KU stats cards (total KUs, viewed, in progress, mastered) |
| `render_user_progress_table(users)` | All-users KU progress table with mastery counts |
| `render_user_ku_summary(summary)` | Individual user KU summary cards |
| `render_user_ku_detail_list(ku_list)` | Per-KU detail table for a user (status, views, time spent) |

**AdminStatsService** (`core/services/admin_stats_service.py`):

Cross-domain aggregation queries, injected with the `CrossDomainBackend` (plus an optional `SearchEventBackend` for the discovery-analytics read side). Registered on `Services` dataclass as `services.admin_stats`.

| Method | Purpose |
|--------|---------|
| `get_user_detail_stats(user_uid)` | 14-field user stats: activity counts, learning, sessions |
| `get_users_with_activity_counts(role_filter, active_only)` | All users with task/goal/habit/KU counts for list table |
| `get_entity_system_metrics()` | Aggregate KU counts, VIEWED/IN_PROGRESS/MASTERED totals |
| `get_all_users_progress()` | Per-user KU progress (mastered, in_progress, viewed counts) |
| `get_user_ku_detail(user_uid)` | Detailed KU list for a user with relationship data |
| `get_activity_entity_counts()` | System-wide Task/Habit/Goal/Journal counts via single Cypher COUNT query |
| `get_user_role_counts()` | User counts grouped by role via single Cypher GROUP BY query |
| `get_search_gaps(max_result_count, days, limit)` | Zero/low-result search queue (content authoring) — empty list when no search-event backend is wired |
| `get_search_event_total()` | Running `:SearchEvent` count vs the 1,000+ Phase-2 analytics trigger |

**`get_user_detail_stats` returns:**

```python
Result[dict[str, int]]  # Keys:
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

All methods use pure Cypher via `QueryExecutor` (no APOC — SKUEL001 compliant). Each returns `Result[T]` with proper error propagation.

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
get_user_service = make_service_getter(services.user)

@rt("/admin/users")
@require_admin(get_user_service)
@boundary_handler()
async def admin_users_list(request, current_user: Any = None):
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

### Admin Home Hub

Admin users land on `/` after login, which renders a hub page with two cards:
- **Admin** → `/admin` (dashboard, user management, analytics, system health)
- **Teaching** → `/teaching` (hub page: Students, Groups, Review Queue, Forms)

The navbar for admin users shows a **SKUEL** logo in the left section linking to `/`. The center section is empty (no text nav links). The right section has the admin avatar (linking to `/`) and a Sign out link (icon+text). On mobile, the hamburger menu shows Admin, Teaching, and Sign out links.

Regular users redirect to `/home` after login — a post-login landing hub with Focus+Velocity header, Submissions previews, GradeBook previews, and 4 navigational cards (Tasks+, Explore, Library, Settings).

**How `is_admin` is determined:**

- Session flag: `get_is_admin(request)` — set at login, no DB call
- Full check: `is_current_user_admin(request, user_service)` — DB lookup
- Admin pages (`/admin/*`): Always pass `is_admin=True` via `@require_admin`

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
   └─ services.admin_stats.get_user_detail_stats(uid) → Result[dict]
         └─ Single Cypher query with incremental WITHs:
            OWNS → Task/Goal/Habit/Event/Choice/Principle (counts)
            VIEWED/IN_PROGRESS/MASTERED → Ku (learning)
            HAS_SESSION/HAD_AUTH_EVENT → Session/AuthEvent (activity)
   │
   ▼
2. AdminUIComponents.render_user_activity_stats(stats, uid)
   │
   ├─ Activity Domains section (6 stat cards via StatsGrid)
   ├─ Learning Progress section (3 stat cards + link → /teaching/students/{uid})
   └─ Session Activity section (2 stat cards)

3. "Student Work" card links out to:
   └─ /teaching/students/{uid}  (student hub: Needs Review, Revision Requested, Completed, KU Progress HTMX preview blocks)
```

**Design decision: AdminStatsService vs UserContext**

The admin user detail page uses `AdminStatsService` (cross-domain aggregation queries) rather than `UserContext` because:
- **UserContext** is designed for the logged-in user's intelligence ("What should I work on?")
- **Admin inspection** needs simple counts ("What has this user done?")
- Dedicated queries are lighter (14 fields vs ~240 in UserContext)
- Queries span User, Activity, Learning, and Session nodes — no single domain backend covers them

---

## Patterns Used

### 1. Layout Pattern (ProfileLayout → AdminLayout)

Sidebar + content layout with:
- Collapsible sidebar on desktop
- Overlay drawer on mobile
- localStorage persistence for sidebar state

### 2. Component Composition (StatsGrid)

Reuses stats cards pattern:

```python
AdminUIComponents.render_user_stats(stats)
# Uses StatsGrid with typed StatItem instances internally
```

### 3. Service Getter Pattern (SKUEL012)

No lambdas in route decorators — use `make_service_getter`:

```python
# ✅ Correct
get_user_service = make_service_getter(services.user)

@require_admin(get_user_service)

# ❌ Wrong (SKUEL012 violation)
@require_admin(lambda: services.user)
```

### 4. Partial Failure Banners

Service methods return `Result[T]`. Routes conditionally render `render_error_banner(msg, severity="warning")` per section on failure.

`AdminOrchestrator.get_system_status()` returns `dict[str, Any]` — never raises. On error it returns `{"status": "unknown", "healthy": False}`. Routes check the `healthy` key:

```python
system_status = await orchestrator.get_system_status()

system_status_content = (
    render_error_banner("System status unavailable", severity="warning")
    if not system_status.get("healthy", True)
    else _render_system_summary(system_status)
)
```

`get_analytics_data()` is partial-failure tolerant — returns zero-value fallbacks for each failed sub-query rather than surfacing a top-level error:

```python
analytics_data = await orchestrator.get_analytics_data()
AdminAnalyticsComponents.render_analytics_dashboard(analytics_data)
```

**Applied to:** system status (overview), user stats (users list), activity entity counts + search gaps/event total (analytics), detail stats (user detail). KU metrics + user progress are handled per-student in the Teaching UI (`/teaching/students/{uid}/submissions?tab=ku`).

**March 2026 — Service extraction:** `_get_user_stats` helper deleted. User role counts and activity entity counts now use efficient Cypher COUNT queries on `AdminStatsService` (`get_user_role_counts`, `get_activity_entity_counts`) instead of fetching full entity lists just to count them.

### 5. Result[T] with @boundary_handler

All API routes return Result[T], converted to HTTP at boundaries:

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
# ui/admin/views.py
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
async def admin_logs(request, current_user: Any = None):
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
- **StatsGrid**: `/ui/patterns/stats_grid.py` (typed statistics display)
- **ProfileLayout**: `/ui/profile/layout.py` (reference implementation)

---

## Key Files Quick Reference

| File | Purpose |
|------|---------|
| `ui/admin/layout.py` | AdminLayout, AdminNavItem, create_admin_page |
| `ui/admin/views.py` | User/Analytics/System/Learning UI components |
| `adapters/inbound/admin_dashboard_ui.py` | Dashboard UI routes |
| `adapters/inbound/admin_routes.py` | API routes (JSON) |
| `core/auth/roles.py` | @require_admin decorator |
| `scripts/dev/bootstrap.py:332-336` | Route registration |
