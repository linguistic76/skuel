# UI Orchestration Expansion Roadmap

**Status:** Active | **Last Updated:** 2026-04-07

## The "Dependency Gravity" Problem

As SKUEL has grown, Hub pages (Dashboards, Overviews, Lists) must assemble data from 5-10 different micro-services to render a single complex UI page.

Without an orchestrator layer, route files become **Service Locators** with massive dependency-injection signatures — violating Clean Architecture by pulling business logic into the HTTP presentation layer.

**The Solution:** The UI Orchestrator Pattern (see `/docs/patterns/UI_ORCHESTRATOR_PATTERN.md`).
By isolating view needs into a dedicated Facade layer (`app/core/orchestrator/`), UI route files become thin and focused on layout alone.

---

## Phase 1–6: Completed (all 9 orchestrators hardened)

All orchestrators follow the **Fail-Fast Dependency Philosophy** — typed `TYPE_CHECKING` imports, no `| None` defaults for required services, no `if not self._service` guards.

- [x] **User Profile Hub** (`user_profile_ui.py`) → `ProfileOrchestrator` — 9 → 1. Intelligence moved in; partial-failure isolation per intelligence call.
- [x] **Submissions Hub** (`submissions_routes.py` + 4 sub-factories) → `SubmissionsOrchestrator` — 9 → 1. Eliminated multi-factory injection pattern.
- [x] **Explore Hub** (`explore_ui.py`) → `ExploreOrchestrator` — 5 → 1. Absorbed 80-line concurrent loader + 90-line Vis.js graph builder.
- [x] **Library Hub** (`library_ui.py`) → `LibraryOrchestrator` — 6 → 1. Unified UID-resolve → batch-fetch pattern for bookmarked KUs and enrolled PathSteps.
- [x] **Teaching & Review Hub** (`teaching_ui.py`) → `TeacherOrchestrator` — 4 → 1. Review queue, student list, groups, KU detail consolidated; `admin_stats` optional (degrades gracefully).
- [x] **Admin Dashboard** (`admin_dashboard_ui.py`) → `AdminOrchestrator` — 3 → 1. Eliminated `_get_system_status(services)` helper repeated across 4 routes; `get_analytics_data()` collapses two service calls into one aggregated method.
- [x] **Journal / Timeline Hub** (`journals_ui.py`) → `JournalOrchestrator` — 6 → 1. Compound `get_journal_for_download()` consolidates ownership check + TRANSFORMS lookup; centralises `journal_output_service` availability guards (CORE tier) into one place.
- [x] **Activity Review Admin Hub** (`activity_review_ui.py`) → `ActivityReviewOrchestrator` — 4 → 1. Collapses ActivityReportOperations + ReviewQueueOperations + UserService + UserContextBuilder; `context_builder` gracefully returns `Result.fail` when unavailable.
- [x] **Pathways UI** (`pathways_ui.py`) → `PathwaysOrchestrator` — 3 → 1. Wraps LpService with UserProgressService injection; all `lp_service.method(user_uid, user_progress)` calls simplified to `orchestrator.method(user_uid)` in routes.
- [x] **Lateral Relationships API** (`lateral_routes.py`) → `LateralRelationshipsOrchestrator` — 7 → 1. Absorbed `_create_relationship` / `_get_relationships` module-level helpers; routes extract `user_uid` themselves and delegate; `lateral_service` property exposes the raw service for `LateralRouteFactory` construction (necessary since the factory lives in the adapter layer). Replaced `DomainRouteConfig` with direct early-return wiring. Route file: 399 → 285 lines.
