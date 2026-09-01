---
updated: 2026-08-26
---

# Route Map

Per-page description of user-facing routes, grouped by navigation section. Routes live in `/adapters/inbound/*_routes.py`; UI components in `/ui/`; static assets in `/static/`.

For layout primitives (`BasePage`, `SidebarPage`, `AuthPage`) and shared components, see [UI_COMPONENT_PATTERNS.md](../patterns/UI_COMPONENT_PATTERNS.md).

---

## Admin Navigation

Admin navbar: SKUEL logo (left, → `/`) + empty center + avatar (→ `/`) + Sign out (icon+text). Admin home hub at `/` shows two cards: Admin (`/admin`) + Teaching (`/teaching/students`). Mobile: hamburger with Admin + Teaching + Sign out links. Icon links are hidden for admins.

### `/admin/prereq-suggestions` — Prerequisite-Edge Suggestion Queue

Admin-only interactive queue (sidebar: "Prereq Edges"). "Generate suggestions" runs the on-demand pipeline (mid-band Ku-pair candidates → LLM judge on FULL tier; undirected pairs on CORE). Each row: pair titles + cosine + judge rationale, a relation/direction select, **Approve** (writes ONE Edge YAML into the content vault's `edges/` — lands in the graph on the next content sync) and **Reject** (client-side only; stateless v1). Routes in `adapters/inbound/admin_dashboard_ui.py`; components in `ui/admin/prereq_views.py`.

### `/admin/knowledge-health` — Knowledge-Subgraph Structural Health

Admin-only read-only gauge (sidebar: "Knowledge Health"; ADR-080 Horizon-1). One consolidated corpus-level report over the knowledge subgraph (Ku / PathStep / LearningPath / Exercise — telemetry excluded): a headline **GDS-readiness score** with a progress bar, node counts, Ku degree distribution, and structural-coverage cards (composition, prerequisite-DAG depth/coverage, ORGANIZES/MOC, lateral density, practice coverage). Below: **authoring-guidance flags** (content gaps to fill) and the **orphan-Ku list** (isolated concepts, each linking to `/explore/ku/{uid}`). Serves curriculum authoring today and is the density signal for the deferred GDS work (Horizon 2). Route in `adapters/inbound/admin_dashboard_ui.py` → `AdminOrchestrator.get_knowledge_health()` → `AnalyticsService.analyze_knowledge_subgraph_health()`; page in `ui/admin/pages.py`. Also available as `./dev knowledge-health` (CLI) and as knowledge-scoped Prometheus gauges. CORE-safe (pure graph analytics, no AI).

---

## Regular User Navigation

Navbar nav links (desktop center / mobile bottom nav, in order): **Today** (`/today`, mobile bottom nav only — no desktop nav item; the SKUEL brand link goes to `/explore` for authenticated users) → **Journals** (`/journals`) → **PathSteps** (`/path-steps`); the mobile bottom nav appends **Calendar** and **Search** tabs. Right section (icon buttons): **Search** (`/search`) and **Calendar** (`/cal`) — both desktop only, mobile folds them into the bottom nav → **Askesis** (`/askesis`) → **Shared with me** (`/profile/shared`) → notification bell → **Profile** avatar (`/profile`) → **Sign out** (`/logout`). Tasks and the other activity domains are reached via the Profile hub.

### `/groups` — Student-Facing Group-Shares Hub

Tabbed layout mirroring `/home`, with one tab per group the student is a member of (capped at `MAX_STUDENT_GROUPS = 4`, enforced server-side in `GroupService.add_member()`). Each tab shows a single "Recent Shares" block HTMX-loaded from `GET /api/groups/{group_uid}/shared/preview` — peer-authored `UserEntry`s linked via `(entry)-[:SHARED_WITH_GROUP]->(group)`, with own entries excluded and membership guarded by the Cypher `MATCH` on `(user)-[:MEMBER_OF]->(group)`. Zero-group students see an `EmptyState`. UI in `ui/groups/hub.py` + `ui/groups/shared_preview.py`; routes in `adapters/inbound/groups_hub_routes.py`; backing service method `UnifiedSharingService.get_user_entries_shared_with_group()`. Distinct from `/teaching/groups` (teacher-facing group management).

### `/explore` — Reading-First Explore Surface

Reading-column view (`max-w-[720px]` centered, `PageType.CUSTOM`, no sidebar) driven by `ExploreOrchestrator.get_reading_plan()`. Shell-first: shell loads immediately; `/explore/content` HTMX fragment delivers the plan. Alpine factory: `exploreReading` in `static/js/explore-reading.js`; the inline x-data seed carries minimal state (greeting, why-evidence, featured UID). All visual content is server-rendered in `ui/explore/reading_plan.py`.

**Sections (top to bottom) — real learner state only (de-faked 2026-07-04, care arc):**
1. **Greeting header** — time-of-day greeting (Alpine for greeting text); the "you finished X yesterday" line renders only from real read-history and collapses without it (no fabricated line until read-history intelligence exists).
2. **Hero article** — the next unread KU inside the user's active IN_PROGRESS PathStep (real "why"); falls back to the first library KU with an honest label. Read button + save toggle (Alpine optimistic).
3. **Path step** — the user's real IN_PROGRESS PathStep with its `USES_KU` composition and per-KU read state (read/current/upcoming) + capabilities tray (practice, apply, assessment, reflection, journal — varies by step).
4. **Ready rail / In-progress / Related** — stay collapsed (empty) until the ZPD reading-plan intelligence exists (future `UserContextIntelligence.get_ready_to_read_today`); the renderer collapses empty sections rather than inventing state.
5. **Library CTA** — links to `/explore/library`; shows real Ku count from DB.
6. **Keyboard hints** — `r` read · `w` why am I ready · `s` save · `/` search library.

**Routes:**
- `GET /explore` — reading surface shell
- `GET /explore/content` — reading plan HTMX fragment
- `GET /explore/read/{uid}` — KU reader alias (302 → `/explore/ku/{uid}`)
- `GET /explore/graph` — dedicated full-page learning graph (`calc(100vh - 220px)` tall; same `exploreGraph` Alpine component, hub mode)
- `GET /explore/library` — demoted full catalog (bento card grid, graph sidebar, same as old `/explore`). Facet bar (`render_explore_search_panel`): search box · TYPE (Ku/Path Step) · NOUS topic · dependent SUB-TOPIC cascade · SORT · "More filters" (learning level) · tag chips. Every facet is anonymous-safe (curriculum-scoped, graph-derived vocabularies), so non-registered viewers get the full bar.
- `GET /explore/library/content` — library HTMX fragment (renders the facet bar + first card page)
- `GET /api/explore/search` — filtered card grid (serves `/explore/library`); accepts `q, type, tag, nous, nous_subtopic, learning_level, sort, offset`
- `GET /api/explore/subtopics` — anonymous NOUS→sub-topic cascade fragment (`?nous=<topic>` → co-occurring sub-topics; public counterpart to the auth-gated `/search/subtopics`, but at the MERGED Ku + PathStep scope its catalog carries — `/search` narrows to the curriculum domains it returns)
- `GET /api/explore/graph` — Vis.js hub graph JSON (serves both `/explore/graph` and `/explore/library` sidebar)

**PathStep detail (`/explore/ps/{uid}`)** — reading-first column (`max-w-[760px]`, `BasePage(CUSTOM)`, no sidebar). Alpine component `pathstep` (registered in `static/js/ps-detail.js`) owns progress state (`not_started → learning → read`), bookmark toggle, and deps accordion. Action bar shows an animated progress track + adaptive CTA: when the PS has TaskTemplates, "Start learning" calls `POST /api/ps/{uid}/engage` (spawns activities); otherwise it toggles read-progress via `POST /explore/ps/{uid}/progress`. Mutation endpoints: `POST /explore/ps/{uid}/progress` (`state=learning|read`), `POST /explore/ps/{uid}/bookmark` (`on=true|false`), `GET /explore/ps/{uid}/tasks` (HTMX fragment: tasks spawned from this PS for the current user; reloads on `ps-engaged` event). Shell and content fragment in `learning_loop_routes.py` (`explore_ps_detail` / `explore_ps_content_fragment`); mutation routes in `path_steps_ui.py`; renderer in `ui/explore/ps_detail.py`. Below the tasks section, two HTMX-loaded learning loop sections appear for authenticated users: **Exercises** (`GET /learning-loop/ps/{uid}/exercises` — exercise list with submission status) and **Submissions & Feedback** (`GET /learning-loop/ps/{uid}/submissions-and-feedback`). The embedded forms fragment (`/learning-loop/ps/{uid}/forms`) is registered but not yet surfaced on the PS page. A **Related concepts** chip-row (`GET /explore/ps/{uid}/related` — lazy HTMX fragment, PS→PS vector similarity, read-time lens, FULL tier only; absent on CORE or when no neighbour clears the threshold) links to similar PathSteps. A **Related to your next step** chip-row (`GET /explore/next-step/related` — lazy HTMX fragment, user-scoped: the viewer's readiness-ranked ZPD proximal Kus, each with Ku→Ku vector neighbours labeled "related (unordered)"; FULL tier + authenticated only, absent on CORE / anonymous / empty zone) surfaces the learner's next concepts.

**Ku detail (`/explore/ku/{uid}`)** — reading-first column (`max-w-[700px]`, `BasePage(CUSTOM)`, no sidebar). Alpine component `kuReading` (registered in `static/js/ku-reading.js`) owns status toggle (Studying / Understood), bookmark, and mastery level. Below the prose: **Mastery Self-Check** (authenticated only) — the Knowledge dual-track surface (ADR-030): rate mastery (`MasteryLevel`) via segmented control → see it against the system-measured substance score. `POST /explore/ku/{uid}/mastery-checkin` (`@csrf_protected`) persists a per-(user, Ku) check-in and swaps in the gap card + trend. A **Related concepts** chip-row (`GET /explore/ku/{uid}/related` — lazy HTMX fragment, Ku→Ku vector similarity, read-time lens, FULL tier only; absent on CORE or when no neighbour clears the threshold) links to similar Kus. UI: `ui/explore/ku_detail.py`, `ui/explore/ku_mastery.py`; routes in `learning_loop_routes.py`.

### `/self-checkin` — Dual-Track Self Check-In

The user-level dual-track perception-gap page (ADR-030): rate Productivity / Engagement / Decision
Quality and see each gap vs the system-measured reality. `POST /self-checkin/results`
(`@csrf_protected`) persists a check-in per rated dimension to the `:User` node and renders gap cards +
per-dimension trends. Route in `adapters/inbound/self_checkin_routes.py`, UI in `ui/self_checkin.py`
(shared gap primitives in `ui/dual_track_card.py`). The per-entity counterpart (Goals/Habits/Principles)
is a "Self-Assessment" section on each activity detail page → `POST /{domain}/dual-track/results`.

### `/home` — Post-Login Landing Hub

Legacy hub superseded. `/submissions` and `/library` are standalone MOC root pages (sidebar-free card grids); `/gradebook` is the one received-feedback page (arc 2 C1). Route in `adapters/inbound/home_routes.py` only registers shared HTMX fragments (`/api/navbar/notification-badge`, `/api/personal-header`).

Also registers `GET /api/personal-header` — HTMX fragment endpoint for the Focus+Velocity header used on all 6 Activity Domain list pages (Tasks, Goals, Habits, Events, Choices, Principles) and any future page that wants it without loading the full MEGA_QUERY on the critical path.

**Two patterns for Focus+Velocity:**
- `personal_header(context)` — when `UserContext` is already in scope (today only the `/api/personal-header` endpoint itself)
- `personal_header_placeholder()` — everywhere else; renders an `hx-get="/api/personal-header" hx-trigger="load"` div that fills in after page render without blocking

Both live in `ui/patterns/personal_header.py`.

### `/profile` — Personal Overview Hub

Four tabs selected by `?tab=` (default `activities`), mirroring the loop (live it / study / submit / grade): **Activities** (6 Activity Domain accordion blocks, previews from `/api/profile/{slug}/preview`; Tasks section open on load), **Curriculum** (former Library blocks), **Submissions** (4 link buttons mirroring the `/submissions` sidebar — Sync, Exercises, Journals, History), **Reports** (former GradeBook blocks). Tab view in `ui/profile/hub.py`. Activity sidebar (shared across `/tasks`, `/goals`, `/habits`, `/choices`, `/principles`, `/journals`) links back to `/profile`. Calendar views (`/cal`, month/week) are navbar-only full-width pages — the sidebar's Events item still links there, but the calendar itself surfaces the activity domains via its legend/chips instead of the sidebar.

### `/profile/shared` — Shared With Me

Type-aware reviewing inbox of entities shared with the viewer via `SHARES_WITH` — today that means ADR-040 auto-shared feedback (EntryReports, RevisedExercises) and manually shared FormSubmissions, framed as *work shared with you for your attention* (feedback-loop UX arc 2 C4). Cards show title, entity-type badge, sharer, share date, and — when the item has an exercise subject (arc 1 C4) — an "on *{exercise}* · in *{path step}*" context line linking to the exercise/PathStep detail pages; detail links resolve per-type via `entity_detail_href()`. A FilterBar (Type · Shared by, options derived from the live inbox) narrows the cards server-side through the `/profile/shared/list-fragment` HTMX fragment. Reached from the inbox icon in the top navbar (next to the bell). Group shares surface on `/groups`, not here. View in `ui/profile/shared_view.py`; route in `adapters/inbound/user_profile_ui.py`.

### `/ku` — Knowledge Index

Flat Ku listing with bookmarks + latest sidebar (pin button for bookmarking).

---

## Hub Sub-Pages (Same Three-Tab Interface)

### `/gradebook`

THE received-feedback page (3→1 collapse, feedback-loop UX arc 2 C1+C2) — one exchange line per exercise, newest activity first: exercise title, derived status (**Waiting** / **Feedback received** / **Revision requested** — `ExchangeStatus.derive`), latest-activity date, source of the latest feedback (Teacher/AI), and lineage counts; each line opens its `/exchange` thread. Status chips + a Source select filter server-side through the `GET /gradebook/lines` HTMX fragment (one summary read: `get_student_exchange_summaries`, `_UserEntryReportQueryMixin`). Two conditional groups render below only when non-empty: **Activity reports** (flat list; request form at `/submit-activity-report`) and **Other feedback** (received reports outside any exchange). Route in `adapters/inbound/user_entry_ui.py` (`gradebook_page`); view in `ui/gradebook/summary.py`; sidebar (GradeBook · Request Activity Report) in `ui/gradebook/nav.py`.

The former list pages `/entry-reports`, `/activity-reports`, `/revised-exercises` are deleted (One Path Forward); their detail routes remain and render under the GradeBook sidebar:

- `/entry-reports/detail?uid=` — full report content with outcome badge + revision link.
- `/activity-reports/detail?uid=` — activity report detail (HTMX-loaded body).
- `/revised-exercises/detail?uid=` — revision instructions with feedback points + submit link.

The `/gradebook/{uid}` route renders submission detail for a specific `UserEntry` — including a fulfills-exercise badge (read from the `FULFILLS_EXERCISE` edge) with a "View exchange thread →" link, a "Request AI feedback" button (submission owner, FULL tier — posts to `POST /api/exercises/report`), and a "Map of Content" card section when the entry has outgoing `ORGANIZES` edges (emergent MOC, drawn by vault `moc: true` ingestion) — children link to their per-type detail pages via `ui/patterns/entity_links.py`.

### `/exchange?exercise={uid}[&student={uid}]`

Read-only exchange thread (feedback-loop UX arc C5) — one (student, root exercise) exchange rendered chronologically: submissions (all revisions, including entries against a `RevisedExercise`), feedback reports, and revision requests, each linking to its existing detail/action surface per viewer (student → `/gradebook/{uid}` / `/entry-reports/detail`; teacher → `/teaching/review/{uid}`). The viewer reads their own exchange; `student=` requires both report-download gates — the live TEACHER role plus a shared ACTIVE owned group — and the teacher-mode chain shows only entries `SHARED_WITH_GROUP` an active group the viewer owns (a multi-class student's other classroom stays invisible). Every denial serves the same rendered not-found page with a real HTTP 404 (404-not-403). Entry points: the Shared-With-Me card's exercise subject link, `/gradebook/{uid}`, the `/teaching/review/{uid}` fragment, and the learning-loop PS submissions rows. Route: `adapters/inbound/exchange_ui.py`; renderer: `ui/learning_loop/exchange_thread.py`.

### `/library`

MOC root page (no sidebar) — four cards linking to the four Library sub-pages. Defined in `adapters/inbound/library_ui.py` (`library_moc`). Child pages use `SidebarPage` with Library sidebar; nav defined in `ui/library/nav.py`.

- `/library/exercises` — exercises assigned via group membership, with submission and feedback status.
- `/library/resources` — admin-curated content (books, talks, films, podcasts, articles).
- `/library/resources/get?uid=…` — per-Resource descriptor page (reading-first BasePage, no sidebar). **Public** (Resource is SHARED/CURATED) — the citation click destination for the CITES_RESOURCE chips on PathStep/Ku detail pages; carries the external "Open source →" link.
- `/library/ku` — user's bookmarked atomic knowledge units.
- `/library/path-steps` — user's enrolled path steps.

### `/submissions`

MOC root page (no sidebar) — five cards linking to the five Submissions sub-pages. Defined in `adapters/inbound/user_entry_ui.py` (`submissions_moc`). Child pages use `SidebarPage` with Submissions sidebar; nav defined in `ui/workbench/nav.py`.

- `/submissions/exercise` — destination-driven exercise upload form (Teacher / AI Feedback / Portfolio coming-soon). Legacy `/submit` 302-redirects here.
- `/submissions/journal` — journal file-upload UX (Processing → Source → Browse → Process); alternative entry point to `/journals`.
- `/submissions/sync` — Obsidian bidirectional sync (primary personal-data ingestion path). Shows the privacy wall ("What SKUEL can see"): the exact vault folders a sync may read, from the live allowlist via `VaultReconciler.describe()`; users without a personal vault get a "no vault configured" note instead of the sync button. A secondary "Preview sync" button (`/settings/vault/preview`) reports what a sync WOULD do — ingest/delete counts with vault-relative examples — without writing anything (dry run; shares the sync consent gate). Legacy `/settings/vault` 301-redirects here; HTMX POST targets remain at `/settings/vault/sync`, `/settings/vault/preview`, and `/settings/vault/consent`.
- `/submissions/history` — exercise submissions with feedback status, view, and delete.
- `/submissions/knowledge` — knowledge notes (`pipeline: knowledge` entries) with their grounded-Ku chips; each chip links to the Ku reading page and carries a per-chip remove (`POST /api/user-entries/grounding/remove`) — the review surface for eager grounding writes (Entry-Enrichment PR 4). Renderer in `ui/user_entry/knowledge_notes.py`.

All four sub-pages use the Submissions sidebar (Exercise → Journal → Sync → History).

---

## Teaching

Teaching child pages (Students, Groups, Review Queue, Forms) use `SidebarPage` with Teaching sidebar; nav defined in `ui/teaching/nav.py`.

### `/teaching/queue` — Review Queue

Two link-tab views over the SAME student-scoped queue query (`get_review_queue_by_groups` — one collapse rule, per-entry `SHARED_WITH_GROUP` gate): **Needs review** (default; statuses submitted/active) and **Waiting for resubmit** (`?view=waiting`; status `revision_requested` — feedback-loop UX arc 2, C3). A resubmit supersedes the revision-requested copy in its lineage, automatically moving the exercise from Waiting back to Needs review. The per-student page's Needs Review / Revision Requested buckets read the same two scoped queues, so the surfaces never disagree. Routes in `adapters/inbound/teaching_ui.py`.

### `/teaching/forms`

Teachers view FormTemplate submissions — template list with counts, per-template submission list with user names, and read-only submission detail. Routes in `adapters/inbound/teaching_forms_ui.py`.

### `/teaching/students/{uid}` — Individual Student Hub

Nested hub (no sidebar) with 4 HTMX-loaded preview blocks (Needs Review, Revision Requested, Completed, KU Progress) showing actual submission/KU data inline via `/api/teaching/students/{uid}/{section}/preview`, linking to `/teaching/students/{uid}/submissions?tab=...` (Alpine section switching with student-specific sidebar).

**Exercises page** shows exercises from two sources merged by `ExerciseService.get_student_exercises_with_status()`:

1. `scope=assigned` exercises via `SHARED_WITH_GROUP` group membership
2. `scope=personal` exercises linked via `HAS_EXERCISE` to PathSteps the user is `IN_PROGRESS` in

Inline submission/feedback status pills (Not Submitted / In Progress / Submitted / Feedback Available / Revision Requested) and context-sensitive action links. "In Progress" reflects the vault exercise channel: a living vault entry declares the exercise via its `fulfills_exercise_uid` intent property with no turn-in edge yet — its action link ("View Entry →") opens the living entry at `/gradebook/{uid}`. A filed turn-in outranks declared intent (the living entry keeps its intent property forever). Exercise titles link to `GET /exercises/get?uid=` (student detail page with Submit + Download buttons; Markdown download via `GET /api/exercises/md?uid=`, renderer at `adapters/outbound/exercise_renderer.py`).

- **Ku tab** — only the user's bookmarked (PINNED) Ku
- **Path Steps tab** — only enrolled (IN_PROGRESS) steps
- **Resources tab** — `Resource` entities (admin-curated books, talks, films)

---

## Study

### `/journals`

Journal domain. The file/audio door is a zero-persistence workshop (ADR-073); the typed **discussion** door persists owner-private `:ConversationSession` + turns for revisit/continue (ADR-078) — understanding-agnostic (no `UserEntry`). Landing at `/journals`. Routes in `adapters/inbound/journals_routes.py`; UI in `ui/journals/__init__.py` + `ui/journals/chat_page.py`.

**FOUNDER tier** (`linguistic76`) — full three-stage DNWF. STANDARD tier sees a placeholder.

**Routes:**
- `GET  /journals` — tier-aware 3-column landing (collapsible journal sidebar · chat input · upload panel; `BasePage(CUSTOM)`, no Tasks+ sidebar). The sidebar carries the **revisit list** of the user's past discussions (ADR-078, owner-private) plus the "New Journal" reset
- `POST /journals/start` — open a discussion on typed text (both tiers; companion voice, user leads); returns the response **inline** (`HX-Retarget` `#journal-workspace`) and persists an owner-private `:ConversationSession` + opening turn pair (ADR-078 — revisit/continue) but **no `UserEntry`**, no redirect. FOUNDER source panel (canon-shelf checkboxes + vault toggle) grounds from message one
- `GET  /journals/discussion/{session_id}` — **continue** an owned discussion: rehydrate `#journal-workspace` from stored turns + restored source selection (404-not-403 on a non-owner)
- `POST /journals/discussion/{session_id}/delete` — delete an owned discussion (session + all turns); removes the revisit-list row (`@csrf_protected`)
- `GET  /journals/discussion/{session_id}/export` — download an owned discussion as a markdown transcript (a user-ownable copy, not a vault read-back)
- `POST /journals/discussion/{session_id}/rename` — inline-rename an owned discussion; re-renders the revisit-list row (`@csrf_protected`)
- `POST /journals/upload` — file/multi-file upload; transcribes/compiles to the user's own `je_out/` folder and returns an inline download fragment (no `UserEntry`). FOUNDER audio → transcript review → Scribe
- `POST /journals/folder-process` — batch-process `je_in/` → `je_out/` (shares the upload batch engine)
- `POST /journals/suggest-activities` — inert "Suggested activities" panel; takes reflection content in the body (no stored entry)
- `GET  /journals/{entry_uid}` — **periodic-notes-only** (`entry_kind` ∈ {daily, weekly, monthly}) → `PeriodicNotePage` with a compact calendar navigation sidebar (mini month grid, ← Calendar link, prev/next period nav). Any non-periodic uid → 404 (discussions are served by `/journals/discussion/{session_id}`, not this route).
- `GET  /journals/je-out/{filename}` — download a flat `je_out/` file (`.md`/`.txt`; single-user-local, path-containment-guarded)
- `POST /journals/follow-up` — reply to an AI response, keeping the session's canon/vault scope; branches on `session_id` (session-backed reads/appends turns from Neo4j; file/audio doors keep the stateless accumulator) (`@csrf_protected`)
- `POST /journals/stage1` — Stage 1 Scribe: faithful structural record of the raw entry (FOUNDER file/audio door) (`@csrf_protected`)
- `POST /journals/stage2` — Stage 2 Thought Partner: evaluative + reflective response across four roles (`@csrf_protected`)
- `POST /journals/stage3` — Stage 3 What Is Related: proposed graph connections (`@csrf_protected`)

Stages 1–3 and follow-up return HTMX fragments that swap `#journal-workspace` inline on `/journals`. `JournalService` (`core/services/journal/`) reads instruction files from `data/instructions/` and builds stage-specific system prompts. FULL tier only (requires `llm_caller`); returns an error fragment when `INTELLIGENCE_TIER=core`. File/DNWF compiled output is written to the user's own flat `je_out/` folder and surfaced as a download — nothing is persisted to Neo4j (ADR-073). Typed **discussions** persist to the owner-private `ConversationService` store (ADR-078) for revisit/continue — understanding-agnostic (never a `UserEntry`, embedding, or search entry).

### `/tasks`, `/goals`

Read-focused views with cross-domain connections, detail pages, and `EntityRelationshipsSection`. Other activity data viewed via ActivityReport in the GradeBook's Activity reports group (`/gradebook`).

### `/path-steps`

Lists all PathSteps as badge-labeled rows (HTMX fragment at `/path-steps/content`). Rows the session user is enrolled in (`IN_PROGRESS` edge) carry an additional "Enrolled" badge; the list itself is anonymous-readable. Clicking a PathStep navigates to `/explore/ps/{uid}` — the merged discovery/detail page with learning-state actions and the engagement flow.

Other curriculum sub-pages (`/learning-paths`, `/exercises`) use `BasePage(STANDARD)`.

---

## Settings

### `/settings`

User preferences page (learning, scheduling, notifications, display, goals) — top-level page with `BasePage` (no sidebar). Links to `/settings/devices`. Route in `adapters/inbound/settings_routes.py`.

### `/settings/devices`

Vault-agent device management (ADR-075): list enrolled devices (name, enrolled/last-seen, revoked state), generate a one-time pairing code (shown once), and revoke devices — revocation closes the device's live `WS /ws/agent` session. `BasePage`. Route in `adapters/inbound/device_routes.py`.
