# Activity Domain Views Consolidation

**Context**: The 6 Activity Domain view files (`ui/activities/*_views.py`) share three
structural patterns that are repeated verbatim with only domain-specific data swapped in.
This is a table, not 6 modules. The refactor is purely internal — no user-facing behaviour
changes.

---

## Current State

The route layer is already consolidated: `adapters/inbound/*_ui.py` files are ~50-line
delegations to `ActivityUIConfig` + `create_activity_ui_routes` in `activity_ui_factory.py`.

The UI layer beneath that has three repeated patterns across
`tasks_views.py`, `goals_views.py`, `habits_views.py`, `events_views.py`,
`choices_views.py`, `principles_views.py`:

### 1. `{Domain}StatsBar` (6×)

Same outer structure: build a `StatItem` list, return `StatsGrid`. However, the stats
*source* has split into two consumers with different metric needs:

| Consumer | Source | Events | Choices | Principles |
|----------|--------|--------|---------|------------|
| Service layer (`ListContext`) | `activity_stats.py` | active, scheduled, today | active, pending, decided | total, core, active |
| View layer (StatsBar) | inline | upcoming, today, completed | pending, decided, avg_satisfaction | core, active, well_aligned |

`avg_satisfaction` (float aggregation + display formatting) and `well_aligned` (alignment
history) are genuinely display-layer concerns. `Events.upcoming` uses the `is_upcoming()`
domain method, which differs semantically from the service layer's `scheduled`. These cannot
be cleanly merged into `activity_stats.py` without polluting it with UI logic.

**StatsBar consolidation is not viable.** The divergence is intentional — two consumers,
two metric sets. Leave the view-layer stats inline.

### 2. `{DOMAIN}_FILTER_CONFIG` (6×)

`FilterBarConfig` instances with domain-specific `FilterSelect` options and sort key lists.
Pure data that currently lives as code.

### 3. `{Domain}List` (6×)

Nearly identical structure:
```python
def {Domain}List(items, connections_map=None):
    if not items:
        return Div(EmptyState(...), id="{domain}-list")
    cards = [{Domain}Card(item, ...) for item in items]
    return Div(*cards, id="{domain}-list", cls="mt-4 space-y-3")
```
Only the id, `EmptyState` text, and card function differ.

---

## Already Consolidated (Do Not Re-Do)

- `core/utils/activity_stats.py` — all 6 `compute_*_stats()` functions live here
- `ui/activities/_shared.py` — `safe_id`, `MetadataField`, `ConnectionBadges`,
  `ConnectionSummary`, `CONNECTION_ICONS`, `PRIORITY_ORDER`
- `adapters/inbound/activity_ui_factory.py` — `ActivityUIConfig`, route factory

`{Domain}Card` and `{Domain}DetailView` are legitimately domain-specific and should stay
in their own files.

---

## Proposed Refactor

### A. Generic `ActivityList` in `_shared.py`

```python
from typing import Callable
from fasthtml.common import FT

def ActivityList(
    items: list,
    domain: str,          # "task", "goal", etc. — used for id and EmptyState
    card_fn: Callable,    # e.g. TaskCard
    connections_map: dict[str, list[dict[str, str]]] | None = None,
) -> FT:
    list_id = f"{domain}-list"
    if not items:
        return Div(
            EmptyState(
                title=f"No {domain}s found",
                description=f"Sync your Obsidian vault to add {domain}s, or adjust your filters.",
                action_text="Sync Vault",
                action_href="/settings/vault",
            ),
            id=list_id,
        )
    cards = [card_fn(item, connections_map.get(item.uid, []) if connections_map else [])
             for item in items]
    return Div(*cards, id=list_id, cls="mt-4 space-y-3")
```

### ~~B. `StatsBarConfig` table~~ — Not viable

The `StatsBarConfig` table approach assumed all 6 domains would produce stats from the same
source. They don't — see Pattern 1 analysis above. The service layer and the view layer need
different metrics; the inline stats in Events/Choices/Principles view files are correct as-is.
Do not attempt this consolidation.

### C. `FILTER_CONFIGS` dict in `filter_bar.py`

```python
FILTER_CONFIGS: dict[str, FilterBarConfig] = {
    "tasks": FilterBarConfig(...),
    "goals": FilterBarConfig(...),
    ...
}
```

Existing module-level constants (`TASK_FILTER_CONFIG`, etc.) become aliases or are removed;
import sites updated.

---

## Status

Patterns A and C are **complete** (2026-04-10). Pattern B (StatsBar) is closed — not viable.

---

## Files to Touch

StatsBar (Pattern 1) is not worth consolidating — skip it. Only Patterns A and C are viable.

| File | Change |
|------|--------|
| `ui/activities/_shared.py` | Add `ActivityList` |
| `ui/activities/filter_bar.py` | Add `FILTER_CONFIGS` dict; keep aliases for existing names |
| `ui/activities/{domain}_views.py` × 6 | Replace `{Domain}List` and `{DOMAIN}_FILTER_CONFIG` with shared equivalents |
| `adapters/inbound/{domain}_ui.py` × 6 | Update imports if names change |
