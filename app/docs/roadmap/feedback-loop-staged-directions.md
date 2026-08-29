# Feedback-Loop Staged Directions — Peer Feedback, Reply Artifact, Read-State

**Status:** STAGED — not scheduled. Intent + un-staging gates only; **no code exists for
any item here, and none should exist while this doc is the artifact.** Written 2026-08-01
at the close of feedback-loop UX arcs 1 (#902–#905) and 2 (#906–#908), which deferred
these deliberately. The arc contracts record *that* they were deferred; this doc records
*what was already decided*, *which seams the arcs left ready*, and *what un-stages each
item* — so a future session (or elicitation) starts from rulings, not from scratch.
**Related:** `done/feedback-loop-ux-arc.md`, `done/feedback-loop-ux-arc2.md` (both arcs
complete, archived 2026-08-21), ADR-040, ADR-054,
`docs/patterns/SHARING_PATTERNS.md`.

Durable rulings quoted below are founder decisions (2026-08-01 elicitations) — do not
re-litigate them outside the item's own future elicitation.

---

## 1. Peer feedback (requires its own elicitation)

**Settled rulings (arc 2):**

- *Who gave feedback is a filter, not a surface.* Teacher / AI today, **peer later** —
  when peer feedback lands it joins the existing Source filters, it does not get its own
  page or hub.
- The **variant-share wrinkle** is real and undecided: the founder's instinct includes a
  mode where a peer shares *a similar piece of their own*, not (only) a review of the
  graded artifact. This shapes the entity design and must be answered before any schema.
- Explicitly: **no entity, no edge, no UI** until the elicitation happens.

**Seams already in place (verified at arc close):**

- `ReportSource` was left peer-compatible: **additive, not free**. Landing "peer" means
  adding a typed `ReportSource` enum member + its labels
  (`core/models/enums/pipeline.py` — it is a closed `StrEnum`; never persist a raw
  string) and one `_SOURCE_OPTIONS` row in the GradeBook Source filter
  (`ui/gradebook/summary.py` — `normalize_exchange_filters` clamps unknown sources to
  `all`, so an unregistered value silently stops filtering). The arc 2 "no schema or
  filter rework" ruling means exactly this: the additions slot in without redesigning
  the filter model. The Shared-With-Me Shared-by filter derives its options from live
  data and genuinely needs nothing.
- `SHARES_WITH` edges all carry `shared_at` + `role`; `share_version` exists **only** on
  the generic `UnifiedSharingService.share` door — the report/revision Cyphers and
  `auto_share_with_student` write edges without it. `created_by` is stamped by every
  **user-authored** writer (arc 2 PR 3 — sharer attribution and the Shared-by filter key
  on it); AI-generated reports pass `author_uid=None` *by design* (no human sharer —
  `created_by` is null, provenance is carried by `processor_type` / the Source filter,
  and the item simply contributes no Shared-by option). A peer writer must stamp
  `created_by` and must not assume complete sharer/version metadata on every existing
  edge.
- The exchange thread (`/exchange`, `get_exchange_thread_raw`) renders the artifact chain
  generically — a peer artifact anchored into the chain would surface there without a new
  page.
- Authorization class rule: non-owner access to entry content requires an
  **entity-specific grant** — a direct `SHARES_WITH` edge (ADR-054 audiences via
  `AudienceResolver`) or a per-entry `SHARED_WITH_GROUP` share. The arc 1 PR 4 rule
  (Codex-enforced twice) is the teacher-mode instance of this: group-membership
  *authority* alone never substitutes for the per-entry grant. Peer read access must be
  designed inside that rule, not around it — which grant a peer gets is elicitation
  question 3.

**Known gap the peer work must close (verified 2026-08-01):** the direct `SHARES_WITH`
edge is *not* an end-to-end content grant for UserEntries today. `share_with_users` →
`AudienceResolver.resolve_and_share` → `UnifiedSharingService.share` writes only the
edge; entries default `PRIVATE`, and `check_access` honors a direct share only at
`SHARED` visibility. The Shared-With-Me card still appears (the inbox query has no
entity-visibility predicate) but its UserEntry link targets `/gradebook/{uid}`, whose
fetch is **ownership-only** — the recipient gets a 404 behind a visible card. Peer
feedback therefore needs (a) the visibility transition (or an explicit share-implies-
shared rule) decided at share time, and (b) a non-owner entry read surface that honors
`check_access` — the teacher-mode `/exchange` chain read is the pattern, not
`/gradebook/{uid}`.

**Un-staging gate:** a real second user working in a shared group — the elicitation needs
an actual peer workflow to verify (`verify-workflow-before-arc-scoping`), not a
hypothetical one. Questions the elicitation must answer:

1. Review of the graded artifact, a shared "similar piece", or both (the variant wrinkle)?
2. Is peer feedback an `EntryReport` with a peer `ReportSource`, or a distinct entity?
   (Leaning from the rulings: reuse — the filter framing presumes one report stream.)
3. Which **entity-specific grant** does a peer get — a direct `SHARES_WITH` edge, a
   per-entry `SHARED_WITH_GROUP` share, or an invitation artifact that resolves into one
   of those? (Bare group membership is not an option — the class rule above.)
4. Does peer feedback participate in mastery/substance, or is it social-only at first?
5. Teacher visibility: does the teacher see peer exchanges in the queue, or are they a
   parallel student-space lane?

**Do not, while staged:** add a `peer` enum member, a placeholder entity type, or an
unused route. An unused enum member is dead code the bloat detector cannot see, and it
would silently pre-answer question 2.

## 2. Reply-message artifact (lightweight student response)

**Settled rulings (arc 1):**

- *The exchange is the artifact chain, not lockstep.* After a report, a RevisedExercise is
  **one option** — a lightweight free-text student reply is another possible artifact.
  Format and anchoring deliberately undecided.
- *"The artifacts are the central focus of messaging … how the artifacts are linked
  together visually."* A reply is a chain artifact, **not** the seed of a chat system.
- `Interaction` is a one-way audit record (`RECORDS` / `INTERACTION_DURING`) — verified
  and ruled **not** a reply home.

**Seams already in place:**

- The exchange chain (`FULFILLS_EXERCISE` → `REPORT_FOR` → `RESPONDS_TO_REPORT` /
  `REVISES_EXERCISE` → `FULFILLS_REVISED_EXERCISE`) and the `/exchange` thread view are
  the natural anchor and surface; the thread's union-read pattern extends to one more
  artifact type without a new page.
- `UserEntry` already carries `pipeline` / `audience` machinery (ADR-054) if the answer to
  anchoring is "a UserEntry variant responding to a report" rather than a new EntityType.

**Open questions for its elicitation:**

1. Anchoring: new EntityType, or a `UserEntry` variant with a `RESPONDS_TO_REPORT`-class
   edge to the report it answers?
2. Does a reply notify the teacher? Notifications currently fire **teacher→student only**
   — a reply is the first student→teacher event, a small but real capability step.
3. Does a reply change `ExchangeStatus`? (A reply is not a resubmit; presumption from the
   waiting rulings: it must NOT move the copy back into Needs review — but a teacher may
   still want to see it.)

**Un-staging gate:** observed need in real exchange use — a student wanting to respond to
a report without resubmitting. With one user (founder in all roles), this cannot be
observed yet.

## 3. Read-state on shared items

**Settled rulings:** waiting/attention is a **filter, not a badge** (both arcs); read-state
on the Shared-With-Me inbox was considered and deferred in both arcs — "no substrate until
peer feedback exists" for owed-response state, and no volume to make read/unread matter.

**Substrate note (why this stays cheap):** the learning-state layer already MERGEs
per-user edges of exactly this shape — `VIEWED` (`last_viewed_at`, view count) and
`MARKED_AS_READ` (`_learning_state_mixin.py`, user→curriculum today) — so the *pattern*
is proven. The existing edges are **not directly reusable**: both UserContext queries
(`user_context_queries.py`, MEGA + CONSOLIDATED) match `VIEWED`/`MARKED_AS_READ` against
any `:Entity` with no type filter and feed the results into knowledge state
(`ku_view_data`, `ku_marked_as_read_uids`) — pointing them at inbox items would
contaminate learner context. Inbox read-state therefore needs a **distinct relationship**
(preferred — context queries stay untouched) or explicit entity-type filtering added to
those queries first. Surfaced as an Unread **filter chip** on `/profile/shared`. Two more
constraints: telemetry retention (ADR-080 H0) prunes stale `VIEWED` edges — an inbox
read-state edge must explicitly join that retention discussion (attention state is
probably *not* prunable telemetry) — and any new relationship name must be registered in
`RelationshipName` (SKUEL030).

**Un-staging gate:** share volume — more than one active sharer and enough items that
"which of these have I looked at" is a real question. Likely rides along with whichever of
§1/§2 lands first rather than shipping alone.

## 4. Subject-exercise filter (pointer only)

Already stated where it belongs: the arc 2 contract rejects it **with a volume gate**
("add when volume exists"). Listed here only so the staged set is enumerated in one place
— this doc adds no new intent for it.

**Pagination — DROPPED 2026-08-29. Not staged, not tracked, no gate.** `/search`'s
pagination was ruled DROP and shipped as top-N (#555 closed, PR #1181); the founder
extended the same ruling to these lists. The volume gate is *withdrawn*, not merely unmet:
pagination is not waiting on volume, it is not planned. Re-proposing it is a fresh
decision, not an un-staging. The arc records in `done/` that still read "pagination (still
deferred, #555)" are pinned history of what arc 2 decided on 2026-08-01; this ruling
supersedes them.

---

## While staged

The staging artifact for all of the above is **this document** — there is deliberately no
staged code, so nothing here belongs in the bloat detector's PLANNED tier. If any item
starts, it gets its own elicitation → choices-doc (contract) → PR plan, per the arc
workflow; the rulings above carry forward as its starting constraints.
