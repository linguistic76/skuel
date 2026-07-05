# Profile UI Components

*Last updated: 2026-07-05*

**Location:** `/ui/profile/`

This directory contains the Profile Hub UI — the student's personal 3-tab home.

## Overview

The Profile Hub (`/profile`) has three tabs (Alpine `activeTab` state, `?tab=` deep links, WAI-ARIA tabs keyboard pattern):

- **Curriculum** — `LIBRARY_BLOCKS` (Resources / Ku / Path Steps / Exercises) as collapsible accordions
- **Reports** — `GRADEBOOK_BLOCKS` (Entry Reports / Activity Reports / Revisions) as collapsible accordions
- **Submissions** (default) — `SubmissionsTabPanel()` button panel mirroring the /submissions sidebar categories

Curriculum/Reports sections render via `HubAccordionBlockList` (`ui/patterns/hub.py`) — native `<details>`/`<summary>`, first section open per tab, previews HTMX-loaded with `intersect once` so a section only fetches when it is open and its tab visible. A default `/profile` load makes zero preview requests.

Uses `BasePage(STANDARD)` — no sidebar.

## Files

| File | Purpose |
|------|---------|
| `hub.py` | `ProfileHubView(active_tab)` — tab bar + tab panels |
| `domain_stats_config.py` | Configuration-driven stats extraction (for badge endpoints) |
| `badges.py` | Status & count badge components |
| `overview.py` | Detailed overview page components |
| `curriculum_views.py` | KU, LS, LP profile views |
| `preferences.py` | User preferences editor |
| `_shared.py` | Shared profile primitives |
| `__init__.py` | Public exports |

## Hub Sections (hub.py)

```python
def ProfileHubView(active_tab: str = "submissions") -> Div:
    return Div(
        _tab_bar(),      # Curriculum / Reports / Submissions (Alpine activeTab)
        _tab_panels(),   # LIBRARY_BLOCKS / GRADEBOOK_BLOCKS / SubmissionsTabPanel
    )
```

### Accordion Blocks

Each Curriculum/Reports section is a `HubAccordionBlock`:
- Summary row toggles: chevron (rotates via `group-open:`) + domain icon + uppercase label
- "View all →" `ButtonLink` on the right is the sole navigation (`@click.stop`)
- Preview panel loads 3 `HubPreviewCard`s (title + description snippet + status badge) from the block's `preview_url`

### HTMX Endpoints (in user_profile_ui.py)

| Endpoint | Purpose |
|----------|---------|
| `GET /api/profile/{slug}/preview` | Top 3 active items for an Activity Domain block |

## Configuration-Driven Domain Statistics

Used by the `/api/sidebar/badges` endpoint (not by the hub view itself).

```python
# /ui/profile/domain_stats_config.py
# DomainStatus lives in core/services/user/domain_health.py
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
