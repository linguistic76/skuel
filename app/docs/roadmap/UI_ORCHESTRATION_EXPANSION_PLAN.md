# UI Orchestration Expansion Roadmap

**Status:** Active | **Last Updated:** 2026-04-07

## The "Dependency Gravity" Problem

As SKUEL has grown, Hub pages (Dashboards, Overviews, Lists) must assemble data from 5-10 different micro-services to render a single complex UI page.

Without an orchestrator layer, route files become **Service Locators** with massive dependency-injection signatures — violating Clean Architecture by pulling business logic into the HTTP presentation layer.

**The Solution:** The UI Orchestrator Pattern (see `/docs/patterns/UI_ORCHESTRATOR_PATTERN.md`).
By isolating view needs into a dedicated Facade layer (`app/core/orchestrator/`), UI route files become thin and focused on layout alone.

---

## Phase 1–4: Completed (all 6 orchestrators hardened)

All orchestrators follow the **Fail-Fast Dependency Philosophy** — typed `TYPE_CHECKING` imports, no `| None` defaults for required services, no `if not self._service` guards.

- [x] **User Profile Hub** (`user_profile_ui.py`) → `ProfileOrchestrator` — 9 → 1. Intelligence moved in; partial-failure isolation per intelligence call.
- [x] **Submissions Hub** (`submissions_routes.py` + 4 sub-factories) → `SubmissionsOrchestrator` — 9 → 1. Eliminated multi-factory injection pattern.
- [x] **Explore Hub** (`explore_ui.py`) → `ExploreOrchestrator` — 5 → 1. Absorbed 80-line concurrent loader + 90-line Vis.js graph builder.
- [x] **Library Hub** (`library_ui.py`) → `LibraryOrchestrator` — 6 → 1. Unified UID-resolve → batch-fetch pattern for bookmarked KUs and enrolled PathSteps.
- [x] **Teaching & Review Hub** (`teaching_ui.py`) → `TeacherOrchestrator` — 4 → 1. Review queue, student list, groups, KU detail consolidated; `admin_stats` optional (degrades gracefully).
- [x] **Admin Dashboard** (`admin_dashboard_ui.py`) → `AdminOrchestrator` — 3 → 1. Eliminated `_get_system_status(services)` helper repeated across 4 routes; `get_analytics_data()` collapses two service calls into one aggregated method.

---

## Phase 5: Future Candidates

### Journal / Timeline Hub (`journals_ui.py`)
- **Impact:** Low
- **Why:** Although the file is very large (46KB), much of it may be specialized UX components rather than cross-domain dependencies. Still, a `JournalOrchestrator` could abstract timeline generation algorithms away from the presentation logic.
