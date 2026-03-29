# Profile UI Components

*Last updated: 2026-03-29*

**Location:** `/ui/profile/`

This directory contains the Profile Hub UI — a **live actionable hub** that surfaces the user's active learning state.

## Overview

The Profile Hub (`/profile`) shows live content from `UserContext.build_rich()`:
- **Knowledge** — Bookmarked + recently viewed Kus with mastery %, namespace badges
- **Lessons** — Lessons being studied (via in-progress KUs)
- **Exercises** — Assigned work with inline Submit buttons + pending revisions
- **Reports** — HTMX lazy-loaded summaries (exercise + activity reports)
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
        _personal_header(context),          # Focus + Velocity
        _knowledge_section(context),        # Kus from knowledge_units_rich
        _lessons_section(context),          # current_lessons (uid + title)
        _exercises_section(context),        # unsubmitted_exercises + pending_revised_exercises
        _reports_section(),                 # HTMX lazy-load from /api/profile/reports/*
        _nous_section(),                    # Placeholder
        _settings_link(),
    )
```

### Data Sources (all from UserContext)

| Section | Fields Used |
|---------|-------------|
| Knowledge | `ku_bookmarked_uids`, `recently_viewed_ku_uids`, `knowledge_units_rich`, `knowledge_mastery` |
| Lessons | `current_lessons` (`list[CurrentLessonItem]` — uid + title) |
| Exercises | `unsubmitted_exercises` (5 items), `pending_revised_exercises` (5 items), `assigned_exercise_count` |
| Reports | HTMX endpoints (not in UserContext — separate service calls) |

### HTMX Endpoints (in user_profile_ui.py)

| Endpoint | Purpose |
|----------|---------|
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
