---
updated: 2026-09-26
---

# Deferred Work

**Context**: Items here are real, valuable improvements that are intentionally on hold. They are not rejected — they are waiting for usage data, business decisions, or production prerequisites that do not yet exist. Each item has an explicit trigger condition.

**Related**: `/docs/roadmap/security-hardening-deferred.md` — the security hardening backlog
(see its Priority Order table for current status).

**Closed privacy gap:** § *Vault Re-Sync Never Retracts a Share* closed 2026-09-26 — a vault note is a
draft and is never shared (R9), so a re-sync has no share to retract.

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

[Habit-Rhythm Arc Follow-ups](habit-rhythm-arc-follow-ups.md) — One follow-up still open from the arc — the `0m`/`15` non-positive-duration disagreement, gated on the next touch of the scheduling service; the weekly-note-panel item closed when that panel was removed (2026-09-18).

## EntryReport / ActivityReport Search

[EntryReport / ActivityReport Search](entry-report-activity-report-search.md) — BaseService search for the two report entities plus their hollow embedding maps — a product need, and the `blocked_by` anchor for two `PLANNED_EMBEDDING_MAPS` entries.

## Domain-level fulltext-first text search (D1(b) follow-on)

[Domain-level fulltext-first text search (D1(b) follow-on)](domain-fulltext-first-search.md) — Relevance-ranked text search for what remains on `/search` — ruled DEFERRED twice, scope inverted by the facet redesign, and the owner of the "Relevance" label fiction; read its two rulings before scoping a third time.

## Lived-Output Search for UserEntry, Exercise and RevisedExercise

[Lived-Output Search for UserEntry, Exercise and RevisedExercise](lived-output-search.md) — The one obligation the `/search` facet redesign created: search for the three domains it stripped, one box per list (`/submissions/history`, `/library/exercises`, `/gradebook`) — all three, on Mike's scheduling.

## ZPD Snapshot History & Trend Analysis

[ZPD Snapshot History & Trend Analysis](zpd-snapshot-history.md) — Keeping the ZPD snapshot timeline instead of only the latest node — waits on a consumer wanting progress trends and on enough snapshots to say anything.

## Content Linting — the two survivors

[Content Linting — the two survivors](content-linting-survivors.md) — The two content-lint ideas `validator.py` does not cover — a NOUS vocabulary check and lint-time orphan detection — waiting on authoring volume.

## Principles `_validate_update` Reform (or Deletion)

[Principles _validate_update Reform (or Deletion)](principles-validate-update-reform.md) — A stale, partly unsatisfiable update hook that `update_principle` bypasses — and the same class in Events — resolved only by a ruling: reform onto the intent or delete.

## Event Attendance Wiring (`ATTENDS`) — Staged Build

[Event Attendance Wiring (ATTENDS) — Staged Build](event-attendance-wiring.md) — The consent-carrying `ATTENDS` attendee triple, staged in `PLANNED_METHODS`; the wiring obligations live in ADR-086, and the build waits on Mike.

## LP Recommendation Backend Methods — Ruled *Build, Not Now*

[LP intelligence: two backend methods that were never built](lp-backend-recommendation-methods.md) — Two never-built backend methods behind LP recommendations — ruled *build, not now*; the three `Any | None` handles stay as the in-code markers.

## ContextRetriever's Three Write-Only Fields

[ContextRetriever's Three Write-Only Fields](context-retriever-write-only-fields.md) — `events_service`/`principles_service` are staged, not dead: the MEGA-QUERY projection + bundle fetch for both channels is the remaining work; the P1 disclosure is closed, the `event_template_uids` rename is DONE.

## ContextRetriever — Four Code-Shaped Findings

[ContextRetriever — Four Code-Shaped Findings](context-retriever-code-findings.md) — Four code-shaped findings in `context_retriever.py`, set aside for a deeper review taken in one sitting with the write-only fields above.

## KnowledgePracticed Subscriber

[KnowledgePracticed Subscriber](knowledgepracticed-subscriber.md) — The zero-subscriber event ruled to *earn* one: review scheduling is its named consumer; nothing is built until that surface is.

## Per-Node Substance Counters — the Unread Arm

[Per-Node Substance Counters — the Unread Arm](per-node-substance-counters.md) — The per-node counter arm and its 8 model methods have zero production readers — ruled keep staged; the writers keep accruing, and retroactive credit is parked with it.

## ⚠️ Vault Re-Sync Never Retracts a Share

[Vault Re-Sync Never Retracts a Share](done/vault-resync-never-retracts-a-share.md) — CLOSED 2026-09-26 (Submit & Share arc PR 8): a vault note is a draft, never shared; its `audience:` applies only to the frozen copy `status: submitted` files, so a re-sync has nothing to retract.

## Sharing HTTP Door — Operations on Existing Shares

[Sharing HTTP Door — Operations on Existing Shares](sharing-http-door.md) — the revoke half shipped 2026-09-25 (Submit & Share arc PR 6b: `POST /api/user-entries/{uid}/share` / `/unshare`, the Share panel, *Your wall* as the access list; the two access-list methods deleted); `UnifiedSharingService.set_visibility` is the one member still without a caller, waiting on the PUBLIC reader (a portfolio listing).

## Form-Submission Recipient Read — a Form Shared With You Still 404s

[Form-Submission Recipient Read — a Form Shared With You Still 404s](form-submission-recipient-read.md) — A FormSubmission shared with a person is listed on their Shared page and opens as not-found (`get_submission` is owner-only); a non-goal of the Submit & Share arc, whose PR 5 builds the audience read this reuses.

## Structured-List Items Silently Corrupt Without a Nested `uid:`

[Structured-List Items Silently Corrupt Without a Nested uid](structured-list-items-need-a-nested-uid.md) — `milestones` and `options` authored without the `uid` their element dataclass requires read back as the raw JSON string; the fix is a shared ingest gate, not six template configs.

## A Frontmatter Edge Whose Target Does Not Exist Yet Is Silent

[A Frontmatter Edge Whose Target Does Not Exist Yet Is Silent](frontmatter-edge-target-missing-is-silent.md) — Every `*_uids:` channel drops an edge whose target node is absent and reports nothing; MOC body links already warn, the structural channels do not.

## `UserLearningIntelligence` Write-Only Fields

[UserLearningIntelligence Write-Only Fields](user-learning-intelligence-write-only-fields.md) — A dataclass whose sources were deleted: everything but `current_masteries` and the velocity reading is written and never read — trim it, or name a consumer.

## Habit Streak Counters — Lost-Update Race + Future-Day Credit

[Habit Streak Counters — Lost-Update Race + Future-Day Credit](habit-streak-counters.md) — Read-then-write streak counters that can drop an increment, and future-day completions that inflate `current_streak` without bound — a semantics ruling, not a mechanical fix.

## Unwired `HabitCompletion` Model Methods — Wrong the Day They're Wired

[Unwired HabitCompletion Model Methods — Wrong the Day They're Wired](unwired-habit-completion-model-methods.md) — Four zero-consumer model methods, each wrong for a future completion the day anyone wires it — audit against the ruling first, or delete.

## Habit-Completion Persistence Bundle — Orphans, UID Collisions, Non-Atomic Day Uniqueness

[Habit-Completion Persistence Bundle — Orphans, UID Collisions, Non-Atomic Day Uniqueness](habit-completion-persistence-bundle.md) — Six persistence defects around the `HabitCompletion` node — orphans, uid collisions, non-atomic day uniqueness, stranded stats, a DISTINCT-day read (moot under the one-per-day ruling), a refused untrack — plus the node-less third door; one shared lock-derived writer is the shape.

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

## Parked Features — Memory-Only Until Now

[Parked Features — Memory-Only Until Now](parked-features.md) — Three feature-shaped threads — activity ledger, interest/engagement signal, icon provider swap — each with its ruled constraint and an absence check.

## Label-Generic Vector Rung Has No Index for Most Domains

[Label-Generic Vector Rung Has No Index for Most Domains](label-generic-vector-rung.md) — `/search`'s Semantic-boost and Learning-aware toggles silently do nothing for seven domains that have no per-label vector index; the fix is the `Entity` index plus an `entity_type` filter, not seven more indexes.

## SEL Journey Fragments — staged behind a surface not yet designed

[SEL Journey Fragments — staged behind a surface not yet designed](sel-journey-fragments-staged.md) — The two `/api/path-steps/*-html` fragments and `ui/patterns/curriculum_adaptive.py` have no page that loads them; PLANNED tier until a journey surface is designed or a ruling deletes them with the JSON twins kept.

## Embedded Forms Fragment — staged behind the PathStep page that dropped it

[Embedded Forms Fragment — staged behind the PathStep page that dropped it](embedded-forms-fragment-staged.md) — `/learning-loop/ps/{ps_uid}/forms` (+ its POST twin) and `ui/learning_loop/embedded_forms.py` have no page that loads them since the reading-first PathStep redesign; PLANNED tier until the forms section returns to `/explore/ps/{uid}` or a ruling deletes them with the `EMBEDS_FORM` edge kept.

## History-in-Code Sweep — the finder is built, the sweep is the queue

[History-in-Code Sweep — the finder is built, the sweep is the queue](history-in-code-sweep.md) — The finder ships advisory over code AND prose (`--docs`); the queue is its output, worked one file or cluster per PR, the why moved to the record, never deleted.

## Symbol Claims in Docs — the queue, and the instrument that would order it

[Symbol Claims in Docs — the queue, and the instrument that would order it](symbol-claims-in-docs.md) — Backticked class / call / member claims that resolve to nothing: measured by the docs de-fiction pass and deliberately not swept — the scanner is unbuilt, the case file carries its method as the spec and the five verdicts a confirmed claim takes.

## Goals and Choices as Weekly-Calendar Chips

[Goals and Choices as Weekly-Calendar Chips](weekly-goals-choices-chips.md) — Founder wish recorded 2026-09-11 while ruling the calendar priority-lens arc; deferred because it contradicts M4, R2 and S1 outright — re-elicit after living with the priority-lens week view, amending those rulings by letter.

## Goal Tally Membership Changes Don't Recompute

[Goal Tally Membership Changes Don't Recompute](goal-tally-membership-changes.md) — A goal's task tally is recomputed only when a linked task changes status. Linking, unlinking or deleting a task, or editing its `completion_updates_goal`, leaves the stored figure stale until the next completion or reopen.

## Mixed Goals Get No Event-Driven Progress

[Mixed Goals Get No Event-Driven Progress](mixed-goal-event-progress.md) — Neither completion handler recomputes a `MIXED` goal. The blend they had fed each result into the next, and it was deleted unshipped in #1407. A real recompute through `ProgressCalculator` waits on one ruling: what a mixed goal's habit half measures.

## Tasks+ / One-Chrome Follow-ons

[Tasks+ / One-Chrome Follow-ons — Explore's Phone Form, the Doorless Census, the Tabs Widget, Three Small Rulings](tasks-plus-follow-ons.md) — What the one-chrome arc left outside itself by ruling: Explore's phone form + the MOC-roots question (D5), the ten doorless surfaces (D8), the `ui/enum_helpers.py` census, the `ui/patterns/tabs.py` <!-- planned --> extraction for both same-page switchers, sidebar group dividers, the "Transcribe" rename (D7) and PWA first-run — each its own PR, each waiting on a ruling or a first snapshot.

## Ingest Transition Obligation Durability

[Ingest Transition Obligation Durability](ingest-transition-obligation-durability.md) — A status transition the ingest doors discover is graph state, not recorded intent, so a failure between the committed status write and the publish loses the cascade permanently — and since D.0 the app door has the same property one step later (a failed `TaskCompleted` subscriber, with no re-click replay); closing it needs an outbox, and the ordering it fights with is the one that has to win.

## Field-Name Guarding in Cypher

[Field-Name Guarding in Cypher — Which Guarantee, and Where](field-name-guarding-in-cypher.md) — Five backend sites interpolate a property name their caller supplies through none of the layer's three guarantees; ruled to stay that way because every caller passes a literal, a registry constant, or sits behind a PLANNED surface — the case file names the one seam that would make it live in a line (`PsService.list_steps`' `**kwargs`) and holds the measurement that `ORDER BY` on a non-returned property is a paginated disclosure oracle.

## Development Machine Capacity

[Development Machine Capacity — what is memory-gated today, and what changes on a bigger machine](development-machine-capacity.md) — Every bound the 15 GB development laptop put in the tree (8 unit workers, the serial composed session, the testcontainer JVM caps, no `./dev quality` beside a test session, bounded foreground waits) with its file:line and its measurement, and per row what a ≥ 32 GB / ≥ 16 GB-VRAM machine changes — after re-measuring, never by copying a number — and what stays a code-side ceiling regardless.

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
