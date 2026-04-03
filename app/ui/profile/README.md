# Profile UI Components

*Last updated: 2026-04-03*

**Location:** `/ui/profile/`

This directory contains the Profile Hub UI — a **live actionable hub** that surfaces the user's active learning state.

## Overview

The Profile Hub (`/profile`) shows live content:
- **Activity Domains** — All 6 (Tasks, Goals, Habits, Events, Choices, Principles) visible as scrollable blocks. Each block has a colored domain header (icon + clickable title + "View all" link) and 3 priority-sorted cards loaded via HTMX from `/api/profile/{slug}/preview`.
- **Nous** — Community knowledge feed (placeholder)
- **Personal Header** — Focus (current task) + Velocity (momentum indicator)

Uses `BasePage(STANDARD)` — no sidebar.

## Files

| File | Purpose |
|------|---------|
| `hub.py` | `ProfileHubView(context)` — live actionable sections |
| `domain_stats_config.py` | Configuration-driven stats extraction (for badge endpoints) |
| `badges.py` | Status & count badge components |
| `overview.py` | Detailed overview page components |
| `curriculum_views.py` | KU, LS, LP profile views |
| `preferences.py` | User preferences editor |
| `_shared.py` | Shared profile primitives |
| `__init__.py` | Public exports |

## Hub Sections (hub.py)

```python
def ProfileHubView(context: UserContext) -> Div:
    return Div(
        _activities_section(),              # All 6 Activity Domain blocks
        _nous_section(),                    # Placeholder
        _settings_link(),
        _personal_header(context),          # Focus + Velocity
    )
```

### Activity Domain Blocks

Each of the 6 Activity Domains renders as a scrollable block via `_activity_domain_block()`:
- Colored header: domain icon + clickable title (links to `/{domain}`) + "View all →" link
- HTMX lazy-loaded cards from `/api/profile/{slug}/preview` (top 3 active items by priority)
- Bottom border separator between blocks

### HTMX Endpoints (in user_profile_ui.py)

| Endpoint | Purpose |
|----------|---------|
| `GET /api/profile/{slug}/preview` | Top 3 active items for an Activity Domain block |
| `GET /api/profile/reports/exercise-summary` | 5 most recent exercise reports |
| `GET /api/profile/reports/activity-summary` | 5 most recent activity reports |

## Configuration-Driven Domain Statistics

Used by the `/api/sidebar/badges` endpoint (not by the hub view itself).

```python
# /ui/profile/domain_stats_config.py
DOMAIN_STATS_CONFIG: dict[str, DomainStatsConfig] = {
    "tasks": DomainStatsConfig(
        count_fn=tasks_count,
        active_fn=tasks_active,
        status_fn=DomainStatus.calculate_tasks_status,
        status_args_fn=tasks_status_args,
    ),
    # ... 5 more activity domains
}
```

## Related Documentation

- [/docs/patterns/HUB_PAGE_PATTERN.md](/docs/patterns/HUB_PAGE_PATTERN.md) — Hub page implementation pattern
- [/docs/design-principles/HUB_PAGES.md](/docs/design-principles/HUB_PAGES.md) — Design rationale
- [/docs/architecture/UNIFIED_USER_ARCHITECTURE.md](/docs/architecture/UNIFIED_USER_ARCHITECTURE.md) — UserContext details
- [/CLAUDE.md](/CLAUDE.md#ui-component-pattern) — Quick reference
