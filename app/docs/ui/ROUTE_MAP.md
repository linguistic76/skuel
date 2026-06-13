# Route Map

Per-page description of user-facing routes, grouped by navigation section. Routes live in `/adapters/inbound/*_routes.py`; UI components in `/ui/`; static assets in `/static/`.

For layout primitives (`BasePage`, `SidebarPage`, `AuthPage`) and shared components, see [UI_COMPONENT_PATTERNS.md](../patterns/UI_COMPONENT_PATTERNS.md).

---

## Admin Navigation

Admin navbar: SKUEL logo (left, → `/`) + empty center + avatar (→ `/`) + Sign out (icon+text). Admin home hub at `/` shows two cards: Admin (`/admin`) + Teaching (`/teaching/students`). Mobile: hamburger with Admin + Teaching + Sign out links. Icon links are hidden for admins.

---

## Regular User Navigation

Navbar icon links (left section, in order): **Hub** (`/home`) → **Tasks+** (`/tasks`) → **Groups** (`/groups`) → **Explore** (`/explore`). Right section: **Search** (`/search`) icon + notification bell + **Sign out** (`/logout`) icon. After login, regular users land on `/home`.

### `/groups` — Student-Facing Group-Shares Hub

Tabbed layout mirroring `/home`, with one tab per group the student is a member of (capped at `MAX_STUDENT_GROUPS = 4`, enforced server-side in `GroupService.add_member()`). Each tab shows a single "Recent Shares" block HTMX-loaded from `GET /api/groups/{group_uid}/shared/preview` — peer-authored `UserEntry`s linked via `(entry)-[:SHARED_WITH_GROUP]->(group)`, with own entries excluded and membership guarded by the Cypher `MATCH` on `(user)-[:MEMBER_OF]->(group)`. Zero-group students see an `EmptyState`. UI in `ui/groups/hub.py` + `ui/groups/shared_preview.py`; routes in `adapters/inbound/groups_hub_routes.py`; backing service method `UnifiedSharingService.get_user_entries_shared_with_group()`. Distinct from `/teaching/groups` (teacher-facing group management).

### `/explore` — Explore Hub

Discovery grid of Ku + PathStep entities with search/filter. Uses `SidebarPage` (wider `w-96`/384px) with graph-centered sidebar (shared across `/explore`, `/explore/ku/{uid}`, `/explore/ps/{uid}`); nav defined in `ui/explore/nav.py`, graph component in `ui/explore/graph.py`.

Sidebar hero is an interactive Vis.js force-directed graph (`ExploreGraphView`):

- **Hub mode:** the user's learning universe ("You" center node + studying Kus + in-progress PSes).
- **Entity mode:** centers on the current Ku/PS with lateral relationships.

Filter tabs (All/Learning/Saved) control both graph node highlighting and list visibility. Three supporting sections below the graph: Learning, Saved, Completed. Node colors: violet (`#8B5CF6`) for Ku, teal (`#14B8A6`) for PS, blue for "You". Graph expands to full-screen JS overlay on `document.body` (Escape or backdrop click to close) — bypasses sidebar `overflow:hidden` + `transform` traps by creating a second Vis.js network in a fresh overlay div. Alpine component: `exploreGraph` in `skuel.js`. API: `GET /api/explore/graph` returns hub learning universe as Vis.js JSON. Each sidebar item shows a type pill (violet=Ku, teal=PS). Unauthenticated users see the graph + "Sign in to track your learning". Detail pages center the graph on the current entity.

**PathStep detail (`/explore/ps/{uid}`)** is the **learning loop anchor** — authenticated users see three HTMX-loaded sections (Exercises with status pills, My Submissions, Feedback) via `/learning-loop/ps/{ps_uid}/*` fragment endpoints wired in `explore_ui.py` (`create_explore_ui_routes`); renderers in `ui/learning_loop/`.

**Ku detail (`/explore/ku/{uid}`)** carries a **"Mastery Self-Check"** section (authenticated only) —
the Knowledge dual-track surface (ADR-030): rate mastery (`MasteryLevel`) → see it against the
system-measured substance score. `POST /explore/ku/{uid}/mastery-checkin` (`@csrf_protected`) persists
a per-(user, Ku) check-in and swaps in the gap card + trend. UI: `ui/explore/ku_mastery.py`; route in
`learning_loop_routes.py`.

### `/self-checkin` — Dual-Track Self Check-In

The user-level dual-track perception-gap page (ADR-030): rate Productivity / Engagement / Decision
Quality and see each gap vs the system-measured reality. `POST /self-checkin/results`
(`@csrf_protected`) persists a check-in per rated dimension to the `:User` node and renders gap cards +
per-dimension trends. Route in `adapters/inbound/self_checkin_routes.py`, UI in `ui/self_checkin.py`
(shared gap primitives in `ui/dual_track_card.py`). The per-entity counterpart (Goals/Habits/Principles)
is a "Self-Assessment" section on each activity detail page → `POST /{domain}/dual-track/results`.

### `/home` — Post-Login Landing Hub

No `UserContext` on the page itself. Three-tab interface (Submissions / GradeBook / Library) with HTMX-loaded domain blocks per tab; Settings button in footer. `/submissions`, `/gradebook`, `/library` render the same `HomeHub()` with the matching tab pre-selected via the `active_tab` param. Hub view in `ui/home_hub.py`, route in `adapters/inbound/home_routes.py`.

Also registers `GET /api/personal-header` — HTMX fragment endpoint for the Focus+Velocity header used on all 6 Activity Domain list pages (Tasks, Goals, Habits, Events, Choices, Principles) and any future page that wants it without loading the full MEGA_QUERY on the critical path.

**Two patterns for Focus+Velocity:**
- `personal_header(context)` — when `UserContext` is already in scope (e.g. `/profile`)
- `personal_header_placeholder()` — everywhere else; renders an `hx-get="/api/personal-header" hx-trigger="load"` div that fills in after page render without blocking

Both live in `ui/patterns/personal_header.py`.

### `/profile` — Personal Overview Hub

Focus + Velocity via `personal_header(context)` (already has `UserContext` from its full page load), Activity Domains (6 HTMX-loaded blocks with colored headers and 3 priority-sorted cards each from `/api/profile/{slug}/preview`). Activity sidebar (shared across `/tasks`, `/goals`, `/habits`, `/events`, `/choices`, `/principles`) links back to `/profile`.

### `/ku` — Knowledge Index

Flat Ku listing with bookmarks + latest sidebar (pin button for bookmarking).

---

## Hub Sub-Pages (Same Three-Tab Interface)

### `/gradebook`

Renders `HomeHub(active_tab='gradebook')` — GradeBook tab pre-selected; block definitions in `ui/gradebook/hub.py` (`GRADEBOOK_BLOCKS`). Child pages use `SidebarPage` with GradeBook sidebar; nav defined in `ui/gradebook/nav.py`.

Study sub-pages — `/entry-reports`, `/entry-reports/detail`, `/activity-reports`, `/submit-activity-report`, `/revised-exercises`, `/revised-exercises/detail` — use `SidebarPage` via GradeBook sidebar.

### `/library`

Renders `HomeHub(active_tab='library')` — Library tab pre-selected; block definitions in `ui/library/hub.py` (`LIBRARY_BLOCKS`). Child pages use `SidebarPage` with Library sidebar; nav defined in `ui/library/nav.py`.

### `/submissions`

Renders `HomeHub(active_tab='submissions')` — Submissions tab pre-selected; block definitions in `ui/workbench/hub.py` (`SUBMISSIONS_BLOCKS`). Child pages use `SidebarPage` with Submissions sidebar; nav defined in `ui/workbench/nav.py`.

- `/upload` — user-facing bulk upload page; drag-and-drop YAML file upload with results display.
- `/submit` — exercise worksheet submission page.
- `/submissions/history` — exercise submissions with feedback status, view, and delete.

All three use the Submissions sidebar.

---

## Teaching

Teaching child pages (Students, Groups, Review Queue, Forms) use `SidebarPage` with Teaching sidebar; nav defined in `ui/teaching/nav.py`.

### `/teaching/forms`

Teachers view FormTemplate submissions — template list with counts, per-template submission list with user names, and read-only submission detail. Routes in `adapters/inbound/teaching_forms_ui.py`.

### `/teaching/students/{uid}` — Individual Student Hub

Nested hub (no sidebar) with 4 HTMX-loaded preview blocks (Needs Review, Revision Requested, Completed, KU Progress) showing actual submission/KU data inline via `/api/teaching/students/{uid}/{section}/preview`, linking to `/teaching/students/{uid}/submissions?tab=...` (Alpine section switching with student-specific sidebar).

**Exercises page** shows exercises from two sources merged by `ExerciseService.get_student_exercises_with_status()`:

1. `scope=assigned` exercises via `FOR_GROUP` group membership
2. `scope=personal` exercises linked via `RELATED_TO` to PathSteps the user is `IN_PROGRESS` in

Inline submission/feedback status pills (Not Submitted / Submitted / Feedback Available / Revision Requested) and context-sensitive action links. Exercise titles link to `GET /exercises/get?uid=` (student detail page with Submit + Download buttons; Markdown download via `GET /api/exercises/md?uid=`, renderer at `adapters/outbound/exercise_renderer.py`).

- **Ku tab** — only the user's bookmarked (PINNED) Ku
- **Path Steps tab** — only enrolled (IN_PROGRESS) steps
- **Resources tab** — `Resource` entities (admin-curated books, talks, films)

---

## Study

### `/tasks`, `/goals`

Read-focused views with cross-domain connections, detail pages, and `EntityRelationshipsSection`. Other activity data viewed via ActivityReport at `/activity-reports`.

### `/path-steps`

Lists all PathSteps with learning-state-aware enrollment buttons (Start / In Progress / Mastered). Clicking a PathStep navigates to `/path-steps/get?uid={uid}` — a reading page with markdown content, learning objectives, and action buttons using `BasePage(CUSTOM)`.

Other curriculum sub-pages (`/learning-paths`, `/exercises`) use `BasePage(STANDARD)`.

---

## Settings

### `/settings`

User preferences page (learning, scheduling, notifications, display, goals) — top-level page with `BasePage` (no sidebar). Route in `adapters/inbound/settings_routes.py`.
