# UI Orchestration Expansion Roadmap 🚀

**Status:** Proposed | **Last Updated:** 2026-04-06

## The "Dependency Gravity" Problem

As SKÜEL has grown, our "Hub" pages (Dashboards, Overviews, Lists) have grown increasingly complex. These backend-rendered FastHTML routes must assemble data from 5-10 different micro-services to render a single complex UI page. 

Without an orchestrator layer, the route files become **Service Locators** with massive dependency-injection signatures. This violates Clean Architecture by pulling deep backend interactions and domain-level business logic (such as filtering or formatting specific model states) into the HTTP presentation layer.

**The Solution:** The UI Orchestrator Pattern (see `/docs/patterns/UI_ORCHESTRATOR_PATTERN.md`).
By isolating these specific view needs into a dedicated Facade layer (`app/core/orchestrator/`), the UI routing files become very thin, focusing purely on FastHTML routing and layout.

---

## Phase 1: Completed
- [x] **User Profile Hub** (`user_profile_ui.py`): Resolved via `ProfileOrchestrator`. Collapsed 9 individual service dependencies down into 1.

---
- [x] **Submissions Hub** (`submissions_routes.py` & `submissions_ui.py`):
  - **Dependencies:** Tracks submissions, processing engines, exercises, core tracking, teacher review, search, and users.
  - **Complexity:** Requires a heavy `create_submissions_ui_orchestrator` method just to inject 9 services to 4 different sub-factories (`submissions_ui`, `activity_reports_ui`, `exercise_reports_ui`, `revised_exercises_ui`).
  - **Proposed Fix:** Create a `SubmissionsOrchestrator` that exposes exact Read models (e.g. `get_student_submissions()`, `get_recent_reviews()`) so the UI doesn't have to piece them together.

- explore
  - library

  ## 2 do

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
