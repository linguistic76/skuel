# Feedback-Loop UX — Design & Choices (Arc 1: fix it, make it legible, thread it)

**Status:** Confirmed — scope picked by the founder 2026-08-01 after workflow elicitation +
ground-truth verification (live graph + code + authed headless-Chrome pass). Arc 1 covers:
loop-integrity fixes, feedback legibility, and the exchange thread view. Deferred to a
follow-up arc: waiting filters (both directions), GradeBook 3→1 collapse, Shared-With-Me
hub filters. Explicitly deferred with no schedule: student reply-message artifact, teacher
vault file-delivery. This document is the arc's source of truth.
**Related:** ADR-040 (teacher exercise workflow), ADR-054 (UserEntry consolidation),
PR #895 (review-queue newest-copy collapse), `docs/ui/ROUTE_MAP.md`,
`docs/patterns/SHARING_PATTERNS.md`.

---

## Intent

The teacher↔student exercise exchange is the learning loop made social. Founder ruling
(2026-08-01): **"messaging" in SKUEL is not a chat system — the artifacts ARE the messages;
what's missing is how they are linked together visually.** The chain
UserEntry → EntryReport → (RevisedExercise) → UserEntry is fully edge-linked in the graph
today; this arc makes the exchange (a) *correct in delivery*, (b) *legible*, and
(c) *visible as one thread*.

## Settled fundamentals (founder rulings, 2026-08-01)

1. **The exchange is the artifact chain, not lockstep.** After a report, a RevisedExercise
   is *one option*, not an automatic next step. A lightweight free-text student reply is a
   possible future artifact — explicitly **deferred** (no entity, edge, or UI in this arc).
2. **Waiting matters in both directions** (student waiting for feedback; teacher waiting
   for a resubmit) and is a **filter**, not a badge — follow-up arc.
3. **GradeBook 3→1 collapse** is wanted for clarity; **Shared-With-Me as active hub** is
   the inclination but "don't merge too much at once" — both follow-up arc.
4. The reading/browse loop (`/search`, `/explore`) is a satisfaction, not arc material.

## Verified ground truth (2026-08-01)

- **Bug A — teacher feedback invisible on `/entry-reports`.** Two report-creation paths:
  `AssessmentService.create_assessment()` writes `ASSESSMENT_OF` + `SHARES_WITH`;
  the teacher-review path (`TeacherReviewService.submit_report` /
  `EntryReportService` → `create_report_node()`, `exercise_backends.py:855-930`) writes
  **only** `SHARES_WITH`. The `/entry-reports` listing reads via `ASSESSMENT_OF` only
  (`_user_entry_assessment_mixin.py:99-106`). Confirmed live: both existing teacher
  reports lack the edge → page shows "No reports yet" while Shared-With-Me shows both.
- **Inconsistency B — queue vs per-student page.** `/teaching/queue` applies the #895
  newest-copy collapse + status ∈ {submitted, active}; the per-student Needs Review
  (`get_student_entries_for_teacher`, `_user_entry_assessment_mixin.py:309-348`) has **no
  collapse**, so it lists superseded copies the queue correctly drops.
- The full chain is edge-linked: `(ue)-[:FULFILLS_EXERCISE {revision}]->(ex)`,
  `(er)-[:REPORT_FOR]->(ue)`, `(re)-[:RESPONDS_TO_REPORT]->(er)`,
  `(re)-[:REVISES_EXERCISE]->(ex)`, `(ue2)-[:FULFILLS_REVISED_EXERCISE]->(re)`. A thread
  view requires **no schema change**.
- Report titles are hardcoded at creation (`"Feedback: {submission_uid[:30]}"`,
  `teacher_review_service.py:190`; `"AI Feedback: …"`, `entry_report_service.py:477-481`)
  — hence raw-UID cards. The Shared-With-Me query
  (`sharing_backend.py:209-222`) joins no context (no exercise/PS/submission), has no
  filters, no pagination, no read-state.
- `Interaction` is a live one-way audit record (`RECORDS`/`INTERACTION_DURING`) — not a
  reply mechanism. Notifications fire teacher→student only. Live graph has zero
  RevisedExercise nodes (revision half never exercised with real data). All five feedback
  surfaces render with zero JS/Alpine errors under real login (`scripts/authed_smoke.py`).

## Choices

**C1 — Canonical report-visibility anchor (fix Bug A).** Chosen: **ownership**. Every
EntryReport about a student's work carries `(student)-[:OWNS]->(report)` (EntryReport is a
`UserOwnedEntity`; live teacher-review reports already have it). The `/entry-reports`
listing reads by OWNS + `entity_type`, and `ASSESSMENT_OF` is **deleted** — writes, reads,
protocol methods, registry entry (One Path Forward; grep confirms all 18 references are
contained in the assessment path — no analytics or external consumers).
*Rejected:* dual-writing `ASSESSMENT_OF` in `create_report_node()` (keeps two parallel
edges meaning the same thing); reading via `REPORT_FOR`→entry→`OWNS` chain (2-hop, and
misses any report legitimately not anchored to an entry).
*Guard:* if implementation reveals AssessmentService reports that exist with **no** student
OWNS and no way to derive one, stop and surface — do not force the convergence.

**C2 — One "needs review" rule (fix Inconsistency B).** Chosen: parameterize the queue
query (`get_review_queue_by_groups`) with an optional student scope; the per-student page's
Needs Review section calls the same method. One collapse rule, two surfaces. Superseded
copies belong to history/Completed, never Needs Review.
*Rejected:* copying the collapse WHERE-clause into the per-student query (drift re-emerges
— that is exactly how this bug was born).

**C3 — Human titles at creation.** Chosen: reports are titled from their subject at
creation — `Feedback on '{exercise.title}'` (teacher) / `AI feedback on '{exercise.title}'`
(AI), falling back to the entry title, never a raw UID. One-shot retitle script for
existing nodes (live count: 2).
*Rejected:* display-time re-titling only (leaves stored garbage; violates structural
correctness).

**C4 — Context join for Shared-With-Me cards.** Chosen: extend `query_shared_with_me` with
per-type OPTIONAL MATCHes resolving the subject exercise (EntryReport via
`REPORT_FOR`→`FULFILLS_EXERCISE`; RevisedExercise via `REVISES_EXERCISE`) and PathStep when
linked; return a typed row (`core/ports/query_types` TypedDict). Card gains an
"on *{exercise}*" line linking into the exchange (C5). No filters/pagination this arc.

**C5 — The exchange thread view.** A read-only page rendering one (student, root exercise)
exchange as a chronological thread: entries (all revisions, incl.
`FULFILLS_REVISED_EXERCISE`-linked), reports, revision requests — interleaved, each item
linking to its existing detail/action surface. No new mutations: submitting stays at
`/submissions/exercise`, teacher actions stay at `/teaching/review/{uid}`.
- **Route:** `GET /exchange?exercise={uid}` (viewer is the student) with optional
  `&student={uid}` for teachers — query params over path params per FastHTML conventions.
  Access: owner, or teacher via the same active-owned-group gate as report download;
  404-not-403 otherwise.
- **Backend:** one method returning the whole chain in one Cypher (no N+1 stitching in the
  service).
- **Renderer:** `ui/learning_loop/exchange_thread.py`.
- **Entry points:** Shared-With-Me card, `/gradebook/{uid}`, `/teaching/review/{uid}`, and
  the learning-loop PS submissions fragment.
*Rejected:* extending `/gradebook/{uid}` (submission-anchored — wrong key; the thread spans
submissions); embedding only in PS detail (buries the exchange; the PS fragment links to it
instead).

## Non-goals (this arc)

Reply-message artifact; waiting filters; GradeBook collapse; Shared-With-Me filters or hub
merge; teacher vault file-delivery (CLI `export_submissions.py`/`import_reports.py` remain
the offline path); pagination; notification changes.

## PR plan (contract)

Each PR: fresh context; branch from **updated** main (`git pull --ff-only` first);
`./dev format` + `./dev quality` + targeted tests; runtime verification via
`uv run python scripts/authed_smoke.py --base-url http://localhost:8000 --pages <touched>`
plus a live-graph spot check; commit → PR → Codex review → consideration note → merge
(standing authorization). This doc ships with PR 1.

| PR | Scope | Acceptance (live case) |
|----|-------|------------------------|
| 1 | C1 — report-visibility convergence + `ASSESSMENT_OF` deletion + OWNS backfill script | linguistic76 sees both existing teacher reports on `/entry-reports`; quality green |
| 2 | C2 — needs-review single source | Per-student page stops listing superseded "List your Tasks v1"; queue and student page agree |
| 3 | C3 + C4 — titles at creation + retitle script + context join + card update | Shared-With-Me card reads "Feedback on 'List your Tasks'" with working context link |
| 4 | C5 — exchange thread view + 4 entry links | `/exchange?exercise=…` renders the live List-your-Tasks chain for the student AND for admin-as-teacher; authed smoke clean incl. the new page |
