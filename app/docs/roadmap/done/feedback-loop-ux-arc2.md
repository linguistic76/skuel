---
updated: 2026-08-21
---

# Feedback-Loop UX — Design & Choices (Arc 2: GradeBook centerpiece, waiting both ways, inbox identity)

**Status:** COMPLETE — all 3 PRs merged (#906–#908); moved to done/ 2026-08-21 (triage
pass verified C1–C4 live in code). Originally CONFIRMED 2026-08-01 (founder go-ahead) —
scoped 2026-08-01
after workflow elicitation + ground-truth verification (live graph + code map + authed
headless-Chrome pass, both roles, all nine page-loads clean). Successor to Arc 1
(`docs/roadmap/done/feedback-loop-ux-arc.md`, PRs #902–#905). This document is the arc's source
of truth.
**Related:** ADR-040, ADR-054, PR #895 (newest-copy collapse), Arc 1 contract,
`docs/patterns/SHARING_PATTERNS.md`, `docs/ui/ROUTE_MAP.md`.

---

## Intent

Arc 1 made the exchange correct, legible, and visible as one thread. Arc 2 answers
"**where do I stand?**" — in both directions — without new capabilities, chat, or badges.

## Settled fundamentals (founder rulings, 2026-08-01 elicitation)

1. **Two directions, two homes.** *GradeBook = feedback I receive* (on my work);
   *Shared-With-Me = work others shared with me* (my reviewing inbox — the mirror of
   `/teaching/queue`, generalized). The earlier "Shared-With-Me as feedback hub" framing is
   superseded by this split; no hub-merge ("don't merge too much at once" stands).
2. **Who gave feedback is a filter, not a surface.** Teacher / AI today; **peer** later.
   Arc 2 only keeps the source-filter naming peer-compatible; the peer-feedback capability
   (including the "share a similar piece, not the graded artifact" variant wrinkle) is
   **staged for its own future elicitation** — no entity, edge, or UI now.
3. **GradeBook clarity = per-exercise lines** (founder-confirmed): newest activity first,
   each line carrying a waiting/delivered status and opening its `/exchange` thread. Not a
   flat list of individual reports.
4. **Waiting is a filter, not a badge** (Arc 1 ruling, still binding): status text on a
   line and filter chips are in; nav badge counts are out.
5. Teacher-side waiting lives on `/teaching/queue` (the page already swept daily).

## Verified ground truth (2026-08-01)

- **Live corpus:** 2 EntryReports (both teacher→linguistic76, retitled by #904; OWNS +
  `visibility='shared'` per #902), **0 ActivityReports, 0 RevisedExercises, 0
  `revision_requested` entries** — the revision path has never run with real data. 61
  UserEntries, of which only 5 (4 exercises) are exercise-anchored; Shared-With-Me contains
  exactly the 2 reports (full overlap with received feedback today).
- **Student waiting derivable live:** latest entry per exercise (the #895
  revision/created_at collapse) with no `REPORT_FOR` report → waiting (2 live cases);
  with report → delivered (2 live cases).
- **Teacher waiting derivable, zero live instances:**
  `TeacherReviewService.request_revision` sets entry status `REVISION_REQUESTED`
  (`teacher_review_service.py:290`); `get_review_queue_by_groups` already accepts
  `status_filter` + `student_uid` (post-#903), and its collapse drops a revision-requested
  copy once a newer resubmit exists in the teacher's active groups — so
  `status_filter=['revision_requested']` on the same query IS the waiting-for-resubmit set.
  The per-student page already buckets `revision` separately
  (`teacher_orchestrator.py:94-135`).
- **`/gradebook` already exists as a hub** of three cards (`ui/gradebook/hub.py`) +
  sidebar (`ui/gradebook/nav.py`) pointing at `/entry-reports`, `/activity-reports`,
  `/revised-exercises`; `/gradebook/{uid}` is the entry-anchored detail (keep). The three
  list pages have no filters; `/activity-reports` has a client-side time filter only.
- **Shared-With-Me query** (`sharing_backend.py:197-246`, post-#904) returns
  `SharedWithMeItem` with subject exercise/PS context; no filters/pagination; sharer is
  resolved from `entity.created_by` → User.
- **Filter precedent:** `FilterBarConfig`/`FilterSelect` + HTMX fragment
  (`ui/activities/filter_bar.py`, `FILTER_CONFIGS`) — server-side filtering,
  `hx-trigger="change"`. No Alpine filter logic; keep it that way.
- **Type trap:** `UserEntry.created_at` is a STRING property; report/RE timestamps are
  native ZONED DATETIME. Any new chain Cypher emits every timestamp via `toString()` and
  interleaves in Python treating naive stamps as UTC (#905 convention). Lineage must be
  `FULFILLS_EXERCISE` ∪ (`FULFILLS_REVISED_EXERCISE`→`REVISES_EXERCISE`→exercise), the
  `get_exchange_thread_raw` pattern — never assume resubmits carry `FULFILLS_EXERCISE`.
- Authed smoke: all six affected surfaces + `/exchange` clean as linguistic76;
  `/teaching/queue`, `/teaching`, teacher-mode `/exchange` clean as admin.

## Choices

**C1 — GradeBook 3→1: one page at `/gradebook`.** Chosen: the hub-of-cards and the three
list pages are **replaced** by one page at `/gradebook` (One Path Forward — list routes
`/entry-reports`, `/activity-reports`, `/revised-exercises` deleted; **detail routes
stay**; every inbound link — navbar/sidebar/hub blocks/cards — repointed). Default view:
**per-exercise exchange lines**, newest activity first — line = exercise title, status
(C2), latest-activity timestamp, source of latest feedback — linking to
`/exchange?exercise={uid}`. Two conditional groups below: **Activity reports** (flat,
OWNS + entity_type; hidden when empty — live count 0) and **Other feedback** (reports
whose entry has no exercise lineage, or no entry; hidden when empty — live count 0; this
is the C1-Arc-1 guard surfaced in UI form). Backend: **one new one-Cypher summary read**
(`get_student_exchange_summaries(student_uid)` on the user_entry report-query mixin →
typed row in `core/ports/query_types`) — per exercise: latest lineage entry
(uid/status/created_at), latest report on that entry (uid/created_at/processor_type),
counts. *Rejected:* flat merged list (founder picked per-exercise clarity); per-exercise
N+1 over `get_exchange_thread` (violates the arc's one-Cypher convention); keeping the
hub page as a fourth surface.

**C2 — Student-side Waiting = status chips on GradeBook.** Chosen: each exercise line
derives one status — **Waiting** (latest entry submitted/active, no report on it),
**Feedback received** (report exists on latest entry), **Revision requested** (latest
entry status `REVISION_REQUESTED` — ball in student's court). Chips filter the lines:
All · Waiting · Feedback received · Revision requested; plus a **Source** filter
(Teacher / AI via `processor_type`, value-set deliberately open for "Peer" later — ruling
2). Server-side via the summary read + HTMX fragment (FilterBar pattern). *Rejected:*
waiting as a computed badge anywhere in nav (ruling 4); a separate `/waiting` page.

**C3 — Teacher-side Waiting = queue filter.** Chosen: `/teaching/queue` gains a
filter/tab pair — **Needs review** (default, today's queue) and **Waiting for resubmit**
(`status_filter=['revision_requested']` through the *same* `get_review_queue_by_groups`
query — same collapse, same per-entry `SHARED_WITH_GROUP` gate, so a resubmit
automatically moves the copy from Waiting back to Needs review). Per-student page's
existing `revision` bucket must agree with the scoped filter (extend the #903 integration
pins). *Rejected:* a new dedicated query (drift risk — C2-Arc-1's lesson); deriving
waiting from report-delivery timestamps (status is the explicit signal; timestamps add
nothing but the string/datetime trap).

**C4 — Shared-With-Me: light filters + inbox identity.** Chosen: `query_shared_with_me`
gains optional `entity_type` and `sharer_uid` WHERE params (parameterized, additive);
page gets a FilterBar (Type · Shared by) + HTMX fragment, and copy reframing the page as
*"shared with you for your attention"* (review-inbox identity). No waiting filter here —
"do I owe a response" has no substrate until peer feedback exists (ruling 2). *Rejected:*
waiting/read-state on shares (no substrate; read-state stays deferred); subject-exercise
filter (only 2 live items — add when volume exists); pagination (still deferred, #555);
hub-merge (ruling 1).

## Non-goals (this arc)

Peer feedback capability (entity/edges/UI) and the variant-share wrinkle; reply-message
artifact; hub-merge; nav badge counts; read-state; pagination; notification changes;
teacher vault file-delivery; any change to needs-review semantics (the scoped queue stays
the single rule; `NEEDS_REVIEW_STATUSES` stays action-form-availability only).

*Post-arc note (2026-08-01):* the deferred items' settled rulings, ready seams, and
un-staging gates are recorded in `feedback-loop-staged-directions.md`.

## Standing conventions that bind every PR here

Per-entry `SHARED_WITH_GROUP` gate for any teacher read of entry content; outage ≠
not-found at every hop (only NOT_FOUND/FORBIDDEN collapse to the hidden 404; real-404
`HTMLResponse` idiom for denials); report bodies fall back `content` ↔
`processed_content`; received-feedback reads exclude `visibility='private'`;
`RelationshipName`/`NeoLabel` interpolation in ALL Cypher including scripts; TypedDicts
referencing DTOs import at RUNTIME (PEP 649); timestamps `toString()`-ed at the Cypher
boundary, naive = UTC.

## PR plan (contract)

Each PR: fresh context; branch from **updated** main (`git pull --ff-only` first);
`./dev format` + `./dev quality` + targeted tests; runtime verification via
`scripts/authed_smoke.py --base-url http://localhost:8000 --pages <touched>` (admin pass
via the #903 credential recipe where teacher surfaces are touched) plus a live-graph spot
check; commit → PR → Codex review → consideration note → merge (standing authorization).
This doc ships with PR 1.

| PR | Scope | Acceptance (live case) |
|----|-------|------------------------|
| 1 | C3 — teacher Waiting-for-resubmit filter on `/teaching/queue` + per-student agreement pins | Admin requests revision on a live waiting entry (e.g. "The Gentle Return") — **first live run of the revision path**: entry leaves Needs review, appears under Waiting for resubmit, per-student page agrees; the created RevisedExercise renders in `/exchange` |
| 2 | C1+C2 — GradeBook 3→1 at `/gradebook` (summary read, per-exercise lines, status+source chips, conditional groups, three list routes deleted, links repointed) | linguistic76's `/gradebook` shows 4 exercise lines with correct mixed statuses (incl. PR 1's live Revision requested); old list URLs gone; authed smoke clean incl. `/gradebook` |
| 3 | C4 — Shared-With-Me filters + inbox copy | Type/Shared-by filters narrow the 2 live items correctly; fragment filtering works with zero JS errors |

PR 1 precedes PR 2 deliberately: its acceptance creates the live `revision_requested` +
RevisedExercise data that lets PR 2 demonstrate all three statuses on a real graph.
