---
updated: 2026-09-05
---

# Deferred Work

**Context**: Items here are real, valuable improvements that are intentionally on hold. They are not rejected — they are waiting for usage data, business decisions, or production prerequisites that do not yet exist. Each item has an explicit trigger condition.

**Related**: `/docs/roadmap/security-hardening-deferred.md` — the security hardening backlog
(see its Priority Order table for current status).

**⚠️ Open privacy gap, deliberately unbuilt:** § *Vault Re-Sync Never Retracts a Share* — a vault note's
`audience:` is write-once-widen until share reconciliation is built. Read it before touching sharing fan-out
or planning a second user.

**How to read this file — it is a MOC (map of content):** one `##` per item. The heading is the
anchor — `blocked_by` pointers in `scripts/detect_bloat.py` and `§` citations in code resolve
against its core text, so it never changes without moving them. Under it: one link to the item's
**case file** and one line saying what the item is and what it waits on. Everything else — the why,
the history, the rulings — lives in the case file, and its trigger / check / status / registered /
ruled are that file's frontmatter properties. The MOC does not repeat them: `deferred-work.base`
renders them as a table in Obsidian, and a session derives the same table with
`grep -H -E '^(trigger|check|status):' docs/roadmap/*.md`.

---

## Shelved Intelligence Features

[Shelved Intelligence Features — Semantic Analysis residue, Discovery Analytics Phases 2+, Real-time Intelligence](shelved-intelligence-features.md) — Three fully scoped features — Semantic Analysis's residue, Discovery Analytics Phases 2+, Real-time Intelligence — each waiting on a data threshold, not on work.

## Decision Points

[Decision Points — Per-user Intelligence Tier](per-user-intelligence-tier.md) — Per-user intelligence tier: the pure function exists and is registered PLANNED; wiring waits on a billing model naming which roles get AI features.

## Mechanisms Awaiting a Consumer

[Mechanisms Awaiting a Consumer](mechanisms-awaiting-a-consumer.md) — Three complete generic mechanisms used in exactly one place — `filter_property` tier buckets, Ku↔Ku `PREREQUISITE_FOR` context, incoming-`DEPENDS_ON` dependents — not to be extended before a consumer asks.

## Habit-Rhythm Arc Follow-ups

[Habit-Rhythm Arc Follow-ups](habit-rhythm-arc-follow-ups.md) — Two follow-ups left open when the arc archived — habit rows in the weekly-note panel, and the `0m`/`15` non-positive-duration disagreement — gated on lived use or the next touch.

## EntryReport / ActivityReport Search

[EntryReport / ActivityReport Search](entry-report-activity-report-search.md) — BaseService search for the two report entities plus their hollow embedding maps — a product need, and the `blocked_by` anchor for two `PLANNED_EMBEDDING_MAPS` entries.

## Domain-level fulltext-first text search (D1(b) follow-on)

[Domain-level fulltext-first text search (D1(b) follow-on)](domain-fulltext-first-search.md) — Relevance-ranked text search for what remains on `/search` — ruled DEFERRED twice, scope inverted by the facet redesign, and the owner of the "Relevance" label fiction; read its two rulings before scoping a third time.

## Profile-Side Search for UserEntry, Exercise and RevisedExercise

[Profile-Side Search for UserEntry, Exercise and RevisedExercise](profile-side-search.md) — The one obligation the `/search` facet redesign created: search for the three domains it stripped, built on `/profile` — all three, on Mike's scheduling.

## ZPD Snapshot History & Trend Analysis

[ZPD Snapshot History & Trend Analysis](zpd-snapshot-history.md) — Keeping the ZPD snapshot timeline instead of only the latest node — waits on a consumer wanting progress trends and on enough snapshots to say anything.

## Content Linting — the two survivors

[Content Linting — the two survivors](content-linting-survivors.md) — The two content-lint ideas `validator.py` does not cover — a NOUS vocabulary check and lint-time orphan detection — waiting on authoring volume.

## Principles `_validate_update` Reform (or Deletion)

[Principles _validate_update Reform (or Deletion)](principles-validate-update-reform.md) — A stale, partly unsatisfiable update hook that `update_principle` bypasses — and the same class in Events — resolved only by a ruling: reform onto the intent or delete.

## Tasks/Events Edge-Clear on Edit (`""` → None)

[Tasks/Events Edge-Clear on Edit ("" → None)](tasks-events-edge-clear-on-edit.md) — Clearing an edge picker submits `""`, which never maps to `None` — a UX bug that rides along on the next edit-form touch, re-verified first.

## Skill↔Doc Backlink Reconciliation (post-canonicalization)

[Skill↔Doc Backlink Reconciliation (post-canonicalization)](skill-doc-backlink-reconciliation.md) — The 28 real backlink warnings the canonical-field validator surfaced, and the 3 drifted `## Related Skills` blocks — each a judgment call, neither blocking.

## Event Attendance Wiring (`ATTENDS`) — Staged Build

[Event Attendance Wiring (ATTENDS) — Staged Build](event-attendance-wiring.md) — The consent-carrying `ATTENDS` attendee triple, staged in `PLANNED_METHODS`; the wiring obligations live in ADR-086, and the build waits on Mike.

## LP Recommendation Backend Methods — Ruled *Build, Not Now*

[LP intelligence: two backend methods that were never built](lp-backend-recommendation-methods.md) — Two never-built backend methods behind LP recommendations — ruled *build, not now*; the three `Any | None` handles stay as the in-code markers.

## ContextRetriever's Three Write-Only Fields

[ContextRetriever's Three Write-Only Fields](context-retriever-write-only-fields.md) — `events_service`/`principles_service` are staged, not dead: the MEGA-QUERY projection + bundle fetch for both channels is the remaining work; the P1 disclosure is closed, the `event_template_uids` rename is HELD.

## ContextRetriever — Four Code-Shaped Findings

[ContextRetriever — Four Code-Shaped Findings](context-retriever-code-findings.md) — Four code-shaped findings in `context_retriever.py`, set aside for a deeper review taken in one sitting with the write-only fields above.

## KnowledgePracticed Subscriber

[KnowledgePracticed Subscriber](knowledgepracticed-subscriber.md) — The zero-subscriber event ruled to *earn* one: review scheduling is its named consumer; nothing is built until that surface is.

## Per-Node Substance Counters — the Unread Arm

[Per-Node Substance Counters — the Unread Arm](per-node-substance-counters.md) — The per-node counter arm and its 8 model methods have zero production readers — ruled keep staged; the writers keep accruing, and retroactive credit is parked with it.

## R4 Vault Inbound Propagation — Parked Build

[R4 Vault Inbound Propagation — Parked Build](r4-vault-inbound-propagation.md) — Vault-side checks, unchecks and edits of 🆔 lines propagating back into SKUEL — never wired, parked with a design sketch and the change-signal rule.

## ⚠️ Vault Re-Sync Never Retracts a Share

[Vault Re-Sync Never Retracts a Share](vault-resync-never-retracts-a-share.md) — Narrowing or removing `audience:` does nothing on re-sync — the one write-once-widen door, ruled leave-registered until share reconciliation is built.

## Vault Task Door Publishes No Task Events

[Vault Task Door Publishes No Task Events](vault-task-door-no-events.md) — The `type: task` frontmatter door persists through the bulk upsert with no event bus, so vault-authored completions publish no `TaskCompleted`.

## `HabitEventScheduler` Stamps a Goal on a Field `Event` Does Not Have

[HabitEventScheduler Stamps a Goal on a Field Event Does Not Have](habit-event-scheduler-dead-goal-stamp.md) — A dead `fulfills_goal_uid` stamp under a `type: ignore` — the real work is the `CONTRIBUTES_TO_GOAL` edge post-persist, guarded.

## Line Deletions Leave `EXTRACTED_FROM` Edges

[Line Deletions Leave EXTRACTED_FROM Edges](line-deletions-leave-extracted-from-edges.md) — Deleting a task LINE from a surviving note leaves its `EXTRACTED_FROM` edge and hash behind, feeding the extraction guards on every future sync.

## `UserLearningIntelligence` Write-Only Fields

[UserLearningIntelligence Write-Only Fields](user-learning-intelligence-write-only-fields.md) — A dataclass whose sources were deleted: everything but `current_masteries` and the velocity reading is written and never read — trim it, or name a consumer.

## Habit Streak Counters — Lost-Update Race + Future-Day Credit

[Habit Streak Counters — Lost-Update Race + Future-Day Credit](habit-streak-counters.md) — Read-then-write streak counters that can drop an increment, and future-day completions that inflate `current_streak` without bound — a semantics ruling, not a mechanical fix.

## Unwired `HabitCompletion` Model Methods — Wrong the Day They're Wired

[Unwired HabitCompletion Model Methods — Wrong the Day They're Wired](unwired-habit-completion-model-methods.md) — Four zero-consumer model methods, each wrong for a future completion the day anyone wires it — audit against the ruling first, or delete.

## `find_by` Datetime String-Binding — Three Habit Sites

[find_by Datetime String-Binding — Three Habit Sites](find-by-datetime-string-binding.md) — Three `find_by(completed_at__gte/__lte=)` reads whose bound is stringified — a natively-typed row silently vanishes; fix all three as ONE PR.

## Habit-Completion Persistence Bundle — Orphans, UID Collisions, Non-Atomic Day Uniqueness

[Habit-Completion Persistence Bundle — Orphans, UID Collisions, Non-Atomic Day Uniqueness](habit-completion-persistence-bundle.md) — Six persistence defects around the `HabitCompletion` node — orphans, uid collisions, non-atomic day uniqueness, stranded stats, a DISTINCT-day read, a refused untrack — plus the node-less third door; one shared lock-derived writer is the shape.

## `TaskUpdateRequest` Future `completion_date` — Create/Update Asymmetry

[TaskUpdateRequest Future completion_date — Create/Update Asymmetry](task-update-future-completion-date.md) — Create refuses a future `completion_date`, update passes one through — an unruled asymmetry inside Tasks; the habits ruling does not extend to it.

## "Vault Has Un-Synced Changes" Signal

["Vault Has Un-Synced Changes" Signal](vault-unsynced-changes-signal.md) — Telling the user a sync is worth running — the honest replacement for a reopen-only dirty flag; no last-sync state exists yet to build on.

## Per-Domain Chunking Knobs + Chunk-Type-Aware Retrieval

[Per-Domain Chunking Knobs + Chunk-Type-Aware Retrieval](per-domain-chunking-knobs.md) — Fragment fix and the eval instrument shipped; knob tuning waits on a measured miss, and `chunk_type_weights` + switching the Askesis intent filter on wait on a content-typing classifier — the `blocked_by` anchor for `_intent_to_chunk_types`.

## DSL-Bridge Grounding — Principles/Recent-Topics

[DSL-Bridge Grounding — Principles/Recent-Topics](dsl-bridge-grounding.md) — Threading `user_principles`/`recent_topics` through BOTH bridge callers once a keyed A/B shows goal grounding lifts recognition; the goal-link half is RETIRED by ruling.

## `HabitMissed` — Publisher-less Chain

[HabitMissed — Publisher-less Chain](habitmissed-publisher-less-chain.md) — A subscribed event with no publisher, ruled keep-staged; the publisher is a miss detector whose day model waits on the streak-semantics ruling — the `blocked_by` anchor for its `PLANNED_EVENTS` entry.

## PathStep → Ku Wiring Backlog — Ku-less PathSteps, PathStep-less Kus

[PathStep → Ku Wiring Backlog — Ku-less PathSteps, PathStep-less Kus](pathstep-ku-wiring-backlog.md) — One PathStep Askesis cannot ground and 67 Kus no PathStep composes (and no MOC organises) — a content backlog with three counts as its check.

## py314 Annotation Sweeps — UP037 Schedulable, TC002/TC003 Never

[py314 Annotation Sweeps — UP037 Schedulable, TC002/TC003 Never](py314-annotation-sweeps.md) — The UP037 mechanical sweep waits for a churn window; TC002/TC003 are a permanent ignore — the rationale lives in ADR-067 § Deferred.

## Parked Features — Memory-Only Until Now

[Parked Features — Memory-Only Until Now](parked-features.md) — Four feature-shaped threads — activity ledger, interest/engagement signal, icon provider swap, activity-templates re-homing — each with its ruled constraint and an absence check.

## Catalog Copies in Code — the duplicated-fact defect, measured

[Catalog Copies in Code — the duplicated-fact defect, measured](catalog-copies-in-code.md) — The class, its ten measured instances and the rule for new code; the stale-PLANNED gate and the `blocked_by` pointer form are built, the rest is Mike's to schedule.

## Dead-Doc-Links Instrument — Rulings + Scheduled Work

[Dead-Doc-Links Instrument — Rulings + Scheduled Work](dead-doc-links-instrument.md) — The rulings and the B1–B8 record of the instrument that took the check from 871 to 280; the residue is owned by the sweep-queue doc, and the duplicate ADR numbers stay noted, unscheduled.

## History-in-Code Sweep — the finder is built, the sweep is the queue

[History-in-Code Sweep — the finder is built, the sweep is the queue](history-in-code-sweep.md) — The finder ships advisory; the queue is its `--top 20` output, worked one file or cluster per PR, the why moved to the record, never deleted.

## Review Schedule

Review this document at the **September 2026 quarterly review**. The sections ARE the checklist:
walk every `##` above, open its case file, and test its `trigger:` against the world with its
`check:` — `deferred-work.base` (Obsidian) or the one-line grep in the header renders the same walk
as a table. Also run `./dev bloat --ready`: every READY `PLANNED` entry older than
`READY_AGING_DAYS` is a wire-or-delete ruling (the `planned-ready-aging` finding — INFO, never
gates; a DELAYED entry aging is expected and is not this), and read its embedding-maps block,
where every row is hollow by ruling and wiring one is ADR-074's quartet followed by deleting the
entry.

Items that hit their trigger condition before the next review should be unblocked immediately —
don't wait for the review.
