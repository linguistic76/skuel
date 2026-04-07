# UI Orchestration Expansion Roadmap 🚀

**Status:** Active | **Last Updated:** 2026-04-06

## The "Dependency Gravity" Problem

As SKÜEL has grown, our "Hub" pages (Dashboards, Overviews, Lists) have grown increasingly complex. These backend-rendered FastHTML routes must assemble data from 5-10 different micro-services to render a single complex UI page. 

Without an orchestrator layer, the route files become **Service Locators** with massive dependency-injection signatures. This violates Clean Architecture by pulling deep backend interactions and domain-level business logic (such as filtering or formatting specific model states) into the HTTP presentation layer.

**The Solution:** The UI Orchestrator Pattern (see [`UI_ORCHESTRATOR_PATTERN.md`](/docs/patterns/UI_ORCHESTRATOR_PATTERN.md)).
By isolating these specific view needs into a dedicated Facade layer (`app/core/orchestrator/`), the UI routing files become very thin, focusing purely on FastHTML routing and layout.

---

## Completed Orchestrators

### 1. ✅ User Profile Hub — `ProfileOrchestrator`
- **File:** `app/core/orchestrator/profile_orchestrator.py`
- **Routes:** `user_profile_ui.py`
- **Services Consolidated:** 9 → 1 (Tasks, Goals, Habits, Events, Choices, Principles, Reports, Sharing, Context)
- **Key Win:** Moved terminal-state filtering and cross-domain priority sorting out of FastHTML templates

### 2. ✅ Submissions Hub — `SubmissionsOrchestrator`
- **File:** `app/core/orchestrator/submissions_orchestrator.py`
- **Routes:** `submissions_routes.py`, `submissions_ui.py`, `exercise_reports_ui.py`, `activity_reports_ui.py`, `revised_exercises_ui.py`
- **Services Consolidated:** 9 → 1 (Submissions, Processing, Exercises, Search, Core, TeacherReview, Users, ActivityReports, RevisedExercises)
- **Key Win:** Collapsed a massive multi-factory injection pattern where `submissions_routes.py` was manually wiring 9 services across 4 sub-factories

### 3. ✅ Explore & Knowledge Hub — `ExploreOrchestrator`
- **File:** `app/core/orchestrator/explore_orchestrator.py`
- **Routes:** `explore_routes.py`, `explore_ui.py` (API factory + UI factory)
- **Services Consolidated:** 5 → 1 (KU, PathStep, UserRelationship, Exercises, SubmissionsSearch)
- **Key Win:** Absorbed the 80-line `_load_explore_data()` concurrent query helper and the 90-line Vis.js graph generation into the orchestrator. Also eliminated the `DomainRouteConfig` boilerplate

### 4. ✅ Library / Asset Hub — `LibraryOrchestrator`
- **File:** `app/core/orchestrator/library_orchestrator.py`
- **Routes:** `library_routes.py`, `library_ui.py`
- **Services Consolidated:** 6 → 1 (Exercises, Resources, KU, PathStep, Submissions, UserRelationship)
- **Key Win:** Deduplicated multi-step query logic (pin-resolve → batch-fetch) that was duplicated across both the tab handlers AND the hub preview handlers

---

## Pending Candidates

The following UI routing modules have been identified as future candidates, based on their file size, complexity, and the number of cross-domain services they import:

### 1. Teaching & Review Hub (`teaching_ui.py`)
- **Impact:** High
- **Why:** The teacher dashboard has to pull from Users (rosters), Submissions (queue), Reports, Exercises, and Analytics to accurately display the "needs review" state.
- **Goal:** `TeacherOrchestrator` → `get_teacher_dashboard_state(teacher_uid)`.

### 2. Administrator Dashboard (`admin_dashboard_ui.py`)
- **Impact:** High
- **Why:** Inherently needs an app-wide snapshot of System Health, Users, Transcriptions, System queues, and Graph Database integrity.
- **Goal:** `AdminOrchestrator` → Provide unified metrics and system state without injecting `user_service`, `db_service`, `transcription_service`, `metrics_service`, etc.

### 3. Journal / Timeline Hub (`journals_ui.py`)
- **Impact:** Low
- **Why:** Although the file is very large (46KB), much of it may be specialized UX components rather than cross-domain dependencies. Still, a `JournalOrchestrator` could abstract timeline generation algorithms away from the presentation logic.

---

## When NOT to Create an Orchestrator

- **Standard CRUD Pages** — Single-entity views like `/tasks` or `/habits` that only interact with one service. Use `DomainRouteConfig`.
- **Simple Associations** — A UI element that just needs a single related field. Pass the service directly.
- **Cross-Domain Business Invariants** — If a business rule spans domains (e.g., "Deleting a goal cancels all its tasks"), use an Application Service or Domain Event, not a UI Orchestrator.
