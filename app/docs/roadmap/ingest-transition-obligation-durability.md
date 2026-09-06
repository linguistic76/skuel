---
title: "Ingest Transition Obligation Durability"
updated: 2026-09-06
status: "open — design needed"
trigger: "a report of a vault-completed entity whose cascade did not run, OR a second writer of ingest-time status transitions"
check: "no instrumentation today; the loss is silent by construction — count ERROR logs from `_publish_completions` / the reopen-clear, or add a counter, before deciding it is worth an outbox"
registered: "2026-09-06 (Codex #1290 round 2, rejected in-PR as out of scope)"
---

# Ingest Transition Obligation Durability

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

## The gap

The vault doors decide a status transition from the prior status the bulk upsert reads under the
node's write-lock (ADR-087, PR #1290). That prior is **graph state**, not recorded intent — so the
obligation it creates exists only for the duration of the call that discovered it.

Between the node's `status: completed` committing and the completion event publishing, the
directory door does phase-2 relationships, edge files, the metadata stamp, deletion reconciliation
and the MOC pass; the single-file door does the tracker retraction, the metadata stamp, embeddings,
chunking and its own MOC pass. Any failure in that stretch — several of which are early `return`s,
and the MOC pass can raise — skips the publish.

**Nothing retries it, and nothing can.** On the next sync the upsert reads the prior as `completed`,
classification correctly reports a repeat, and the event is never published. The cascade — goal
progress, PS engagement auto-complete, productivity analytics, context invalidation — is lost
permanently for that entity, with no signal beyond an ERROR log at the time.

The same applies to the reopen-clear: a failed `clear_completion_stamps` strands the completion
stamp on a non-completed entity, and the next ingest reads a non-completed prior and sees nothing
to do.

## Why the ordering cannot fix it

The publish sits late in the call **by design** (#1290 round 1): a completion event is consumed
synchronously — `EventBus.publish_async` awaits its subscribers — and those subscribers traverse the
entity's edges (`PsPracticeService.handle_event_completed` follows `APPLIES_KNOWLEDGE`, which the
Task and Event relationship configs author). Publishing earlier hands them an entity with no edges,
they find nothing, and the cascade is lost anyway — the same outcome by a different route.

So the two pressures are genuinely opposed, and the ordering one wins: a cascade that runs against
an incomplete graph is wrong every time, while a cascade lost to a mid-sync failure is rare.

## Why it is not novel

SKUEL already records this property from the other side. ADR-070's outbound vault writes are driven
by the sync's **state predicate**, never by `TaskCompleted`/`TaskReopened`, precisely because
*"a status transition is consumed by the write that produced it and has no retry"* (CLAUDE.md §
Obsidian VaultBridge). The vault door's completion cascade now extends the reach of that known
property. It does not introduce it.

## What closing it would take

A durable record of the obligation, written in the same transaction as the status change and
cleared once the publish succeeds — an outbox. Sketch, not a plan:

1. The upsert writes a pending-transition marker alongside the status (same statement, so it cannot
   be lost separately from the write that created it).
2. The post-persist step publishes, then clears the marker.
3. A sweep at the start of the next sync — or a one-shot script — republishes markers still standing.

Each step has real questions the sketch does not answer: what the marker is (node property vs. a
`:PendingTransition` node), whether a republished event is distinguishable from a first publish
(`is_repeat` semantics), and whether the sweep can tell a crashed publish from one still in flight.
**That is why this is a design, not a patch.**

## Do not do the cheap version

Retrying by re-reading status would republish on every sync for every completed entity — the exact
`--force` noise the transition gate exists to prevent. The obligation has to be recorded, not
inferred.
