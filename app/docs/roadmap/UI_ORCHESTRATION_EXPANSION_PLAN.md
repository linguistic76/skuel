# UI Orchestration Expansion Roadmap

**Status:** Active | **Last Updated:** 2026-04-07

## The "Dependency Gravity" Problem

As SKUEL has grown, Hub pages (Dashboards, Overviews, Lists) must assemble data from 5-10 different micro-services to render a single complex UI page.

Without an orchestrator layer, route files become **Service Locators** with massive dependency-injection signatures — violating Clean Architecture by pulling business logic into the HTTP presentation layer.

**The Solution:** The UI Orchestrator Pattern (see `/docs/patterns/UI_ORCHESTRATOR_PATTERN.md`).
By isolating view needs into a dedicated Facade layer (`app/core/orchestrator/`), UI route files become thin and focused on layout alone.

---

## Phase 1 & 2: Completed (all 4 orchestrators hardened)

All orchestrators now follow the **Fail-Fast Dependency Philosophy** — typed `TYPE_CHECKING` imports, no `| None` defaults for required services, no `if not self._service` guards.

- [x] **User Profile Hub** (`user_profile_ui.py`) → `ProfileOrchestrator` — 9 → 1. Intelligence moved in; partial-failure isolation per intelligence call.
- [x] **Submissions Hub** (`submissions_routes.py` + 4 sub-factories) → `SubmissionsOrchestrator` — 9 → 1. Eliminated multi-factory injection pattern.
- [x] **Explore Hub** (`explore_ui.py`) → `ExploreOrchestrator` — 5 → 1. Absorbed 80-line concurrent loader + 90-line Vis.js graph builder.
- [x] **Library Hub** (`library_ui.py`) → `LibraryOrchestrator` — 6 → 1. Unified UID-resolve → batch-fetch pattern for bookmarked KUs and enrolled PathSteps.

---

## Phase 3: Future Candidates

The following UI routing modules have been identified as high-priority candidates for the UI Orchestrator Pattern, based on their file size, complexity, and the number of cross-domain services they import:

### 1. Teaching & Review Hub (`teaching_ui.py`)
- **Impact:** High
- **Why:** The teacher dashboard has to pull from Users (rosters), Submissions (queue), Reports, Exercises, and Analytics to accurately display the "needs review" state.
- **Goal:** `TeacherOrchestrator` -> `get_teacher_dashboard_state(teacher_uid)`.

### 2. Administrator Dashboard (`admin_dashboard_ui.py`)
- **Impact:** High
- **Why:** Inherently needs an app-wide snapshot of System Health, Users, Transcriptions, System queues, and Graph Database integrity.
- **Goal:** `AdminOrchestrator` -> Provide unified metrics and system state without injecting `user_service`, `db_service`, `transcription_service`, `metrics_service`, etc.


### 5. Journal / Timeline Hub (`journals_ui.py`)
- **Impact:** Low
- **Why:** Although the file is very large (46KB), much of it may be specialized UX components rather than cross-domain dependencies. Still, a `JournalOrchestrator` could abstract timeline generation algorithms away from the presentation logic.
