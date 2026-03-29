# Shelved: entity_dashboard.py (SharedUIComponents)

**Shelved:** 2026-03-29
**Reason:** Built for Activity Domain dashboards (Tasks, Goals, Habits, Events, Choices, Principles) which were shelved on 2026-03-28. The only active consumer was `render_stats_cards()` in admin views, which has been migrated to the typed `StatsGrid` / `StatItem` pattern from `ui/patterns/stats_grid.py`.

**What's here:**
- `SharedUIComponents` class — generic dashboard rendering (entity list, grid, filter, search, stats, detail view, empty state, section header, quick actions)
- `SharedUIComponentsExamples` class — example usage patterns

**Revival path:** If Activity Domain dashboards are un-shelved, evaluate whether `StatsGrid` + `CardGenerator` + `EmptyState` (the current pattern set) covers the use cases, or whether this file's higher-level dashboard composition is needed.
