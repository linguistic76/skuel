---
title: "ADR-087: Status-Guarded Conditional Writes"
updated: 2026-08-24
status: accepted
category: decisions
tags: [adr, decisions, concurrency, status, completion-stamp, neo4j, write-path]
related: [ADR-030, ADR-066, ADR-044]
related_skills: [neo4j-cypher-patterns, activity-domains, result-pattern]
---

# ADR-087: Status-Guarded Conditional Writes

**Status:** Accepted
**Date:** 2026-08-24
**Deciders:** MCF
**Arc:** Conditional-write primitive (successor to cascade-idempotency #1126–#1136).
**Related:** ADR-030 (node-lock sentinel, at-most-once execution), ADR-066 (typed update
intents), ADR-044 (Neo4j as a committed choice), `core/services/completion_stamp.py`.

## Context

Every status-bearing write in SKUEL is a read-then-write. The chokepoint reads the entity,
computes a verdict in Python — `is_completion_transition` / `is_reopen_transition` /
`is_repeat` / a terminal-state gate — and then issues a blind `SET n += $props`. The read
takes no lock, so two concurrent writers observe the same prior and both act on it.

Codex flagged this shape five times across the cascade-idempotency arc (#1127, #1128,
#1131, #1133, #1136). The concrete hazards:

- **The stamp invariant breaks.** `completion_date` is supposed to be non-null exactly
  when the task is completed. Today's Undo posts a reopen through
  `POST /api/tasks/{uid}/status` while the complete may still be in flight (the complete
  is the slower request — it reads the task and its relationships first). A complete that
  serializes *after* the reopen still holds the pre-reopen read, sees "already completed",
  declines to stamp, and writes `status=completed` with no `completion_date`.
- **`is_repeat` is approximate.** The cascade deliberately re-runs on a repeat completion
  (a repair path), and `is_repeat` is the seam that tells counting handlers to skip while
  recomputing handlers keep working. Derived from a pre-read, two concurrent completes can
  both report `is_repeat=False`, so a counting handler counts one task twice.
- **Terminal gates leak.** `_trigger_task` reads the status, finds it non-terminal, and
  writes `scheduled` — over a cancellation that landed in between.

The race is not theoretical at this shape. Measured on Neo4j 2026.06.0, four concurrent
completes on one node, 40 trials: **39 of 40 trials** produced two, three, or four writers
that each believed they had performed the first completion.

Three mechanisms were available and none fit. A bare compare-and-set
(`MATCH … WHERE n.status = $expected SET …`) evaluates its predicate lock-free, so it has
exactly the same defect — it narrows the window without closing it (the same latent
weakness `mark_engagement_terminal` carries today). `apoc.lock.nodes` is refused by
SKUEL001. An explicit transaction around a read and a write is what ADR-030 needed, but
only because appending inside a JSON string cannot be expressed in Cypher.

## Decision

**One primitive, on the universal CRUD mixin: `update_with_status_guard`.** The write
statement itself captures the prior status *under the node's write-lock*, applies
caller-supplied patches selected by that prior, and **returns the prior**. Services derive
every verdict from the returned prior using the same pure helpers they already call.

1. **Prior-status-return is the contract.** `StatusGuardedOutcome` carries `applied`,
   `prior_status`, and `entity`. `is_completion_transition(outcome.prior_status, changes)`
   and its reopen mirror are unchanged functions — only their argument became exact. This
   is what makes `is_repeat` exact by construction (`not is_transition`) instead of
   duplicating completion semantics anywhere new.

2. **Conditions are set-membership of the prior, nothing more.** The caller always knows
   the TARGET status before the write; only the PRIOR is unknown. So `StatusWriteGuard`
   holds three knobs — `refuse_if_prior_in`, `patch_if_prior_in`, `patch_if_prior_not_in` —
   and the backend never needs to know what `completed` means. Completion semantics stay
   in `core/services/completion_stamp.py`.

3. **Lock before read.** The statement's first `SET` writes a `_sg_lock` sentinel, which
   acquires the node's exclusive write-lock; every clause below runs under it, and the
   sentinel is removed in the same statement so it never lingers. This is ADR-030's
   mechanism in single-statement form. A unique token per call keeps it a genuine property
   write that no same-value optimization can elide.

4. **One auto-commit statement, no managed retry.** Unlike ADR-030's JSON append, the
   conditional merge is fully Cypher-expressible, so no Python runs between the read and
   the write and no explicit transaction is needed. Execution goes through `_run_single`
   (`session.run`) — at-most-once, the same duplication-vs-loss ruling ADR-030 made. A rare
   transient surfaces as a `Result.fail` the caller propagates, never a silent re-run whose
   returned prior would misreport the verdict.

5. **Guarded-out is an outcome, not an error.** `applied=False` means the prior was in the
   refuse set and the node is untouched. Not-found is the error. Guard evaluation happens
   after the `MATCH`, so a returned row proves existence and no row proves absence — one
   query leg distinguishes them.

6. **The protocol grows on `CrudOperations[T]`.** Every domain protocol already extends
   `BackendOperations[T] → CrudOperations[T]`, the implementation lives once on
   `_CrudMixin`, and the guarded write is a peer of `update` — the one way a status-bearing
   write is done (One Path Forward). `StatusWriteGuard` / `StatusGuardedOutcome` live in
   `core/models/update_contracts.py` beside the other write-path value types.

## Mechanics

```cypher
MATCH (n:{label} {uid: $uid})
{default filter clause}
SET n.`_sg_lock` = $lock_token          -- takes the node write-lock BEFORE the read
WITH n, n.status AS prior
REMOVE n.`_sg_lock`
WITH n, prior, coalesce(prior, '') AS prior_key
WITH n, prior, prior_key, (NOT prior_key IN $refuse_statuses) AS applied
SET n += CASE WHEN applied THEN $updates ELSE {} END
SET n += CASE WHEN applied AND prior_key IN $patch_in_statuses THEN $patch_in ELSE {} END
SET n += CASE WHEN applied AND NOT prior_key IN $patch_not_in_statuses
         THEN $patch_not_in ELSE {} END
RETURN n AS node, prior AS prior, applied AS applied
```

Parameter defaults make every unused knob a no-op: `refuse_statuses=[]` never refuses,
`patch_in_statuses=[]` makes `x IN []` false, and `patch_not_in={}` makes the always-true
`NOT x IN []` branch merge nothing. `prior_key = coalesce(prior, '')` gives null-safe
membership; the raw `prior` is what comes back, and mapping an unrecognized value to
"absent" stays with `_coerce_status` at the service.

`updated_at` is stamped Python-side into `$updates`, so it rides the same conditional merge
and a guarded-out write leaves the node byte-identical. All three payloads pass through
`to_neo4j_node`, so storage shapes match every other write (dates and datetimes persist as
ISO strings — **the writer decides the storage type**, and computing a stamp in Cypher would
quietly change it) and a `None` survives to `SET n += {field: null}`, which REMOVES the
property. That null-merge *is* the reopen clear.

**Why the lock is load-bearing, measured.** 40 trials × 4 concurrent completes on one node,
Neo4j 2026.06.0: with the lock-first `SET`, exactly one writer saw a non-completed prior in
**40/40** trials. With the identical statement minus that one line, **39/40** trials produced
two to four such writers. The lock is the mechanism; the `CASE` merges alone are not.

## Consequences

- `is_repeat` becomes exact by construction rather than approximate.
- The status chokepoints move backend-direct, off `CrudOperationsMixin.update`'s double
  read. The generic mixin stays the non-status seam and is untouched.
- `BaseService.update_status` is **deleted** — zero production callers, and a status write
  now belongs to the domain chokepoint that owns its guard.
- `completion_transition_patch` (the read-then-write form) and `status_transition_guard`
  (the write-time form) coexist during the migration, sharing one validated front half
  (`_stamp_target`) so the legality check and the authority rule cannot drift. The
  Python-side form retires when its last caller migrates.
- **Two domain rules migrated whole, not just the stamps.** A rule whose verdict depends
  on the prior status is the same staleness class this ADR closes, so where the rule's
  other half is caller-side knowledge it moves into the guard:
  - Goals' **reopen progress reset** rides the guard's prior-conditional patch alongside
    the stamp clear, because both condition on "was it COMPLETED?". Note the stamp patch
    is *absent* when the caller supplies its own `achieved_date` (the authority rule is
    about the stamp field, and says nothing about progress), so the reset constructs that
    patch when needed rather than merely extending it.
  - Choices' **decision immutability** becomes a `refuse_if_prior_in`. Which fields an
    update touches is known before the write, so only the prior-status half is left for
    the write to decide. It is still checked against the advisory pre-read as a fast
    path — that check can only ever be stale in the harmless direction, since no door
    moves a choice back out of a decided status, while the direction that matters is
    real: `make_decision` moves a DRAFT choice to ACTIVE with a raw write that never
    passes through the chokepoint.
- **Moving a chokepoint backend-direct takes `_validate_update` off the path.** The
  facades route the generic CRUD to these methods, so the inherited
  `CrudOperationsMixin.update` hook is the *only* thing that was running the domain rules
  — and it stops running once the write leaves the mixin. Every migrated chokepoint calls
  the hook explicitly, and each has a test pinning that its rules still fire and still
  refuse. This is the "correction #14" class: a rule that has no caller fails silently and
  looks like it passed.
- **`today.js`'s request queue stays**, and was completed rather than retired. The
  primitive makes each write's verdict exact under any interleaving; it cannot ORDER two
  opposing HTTP requests, and no server-side guard can decide which of two the user MEANT
  to win. A reopen that lands before an in-flight complete still leaves the task completed
  under a card reading "not done" — the #1133 P1 hazard the queue exists to prevent.
  Verdict correctness and request ordering are different problems needing different
  mechanisms. The queue was also one-directional — it chained the reopen behind the
  complete, but not a *re-complete* behind the reopen — and is now keyed per task
  (`_pendingWrites`), which orders opposing writes to one task without serializing
  different tasks behind each other's cascades.

## Scope

Deliberately **out**, by name:

- **Counter races** — habit streak read-modify-write, duration-calibration EMA, goal
  progress accumulation. A numeric read-modify-write needs an increment-style or lock
  primitive, not a status guard. Registered in `docs/roadmap/deferred-work.md`.
- **Non-status guards** — the Principle strength old-value read, past-event immutability,
  ownership checks. Advisory reads stay advisory.
- **Relationship-edge CAS** — `mark_engagement_terminal` and `remove_attendee` guard on
  edge properties, a different seam. `mark_engagement_terminal`'s `WHERE`-clause CAS has
  the lock-free weakness described above; it is documented here and **not** fixed by this
  arc.
- **Principles' own chokepoint.** Its gate is target-only legality (`valid_statuses`),
  which is prior-INdependent, so no read-then-write race exists there. Migrating it would
  be uniformity theater. It does still *call* `completion_transition_patch`, for that
  legality check alone (Principle has no completion field, so the patch is always empty) —
  so retiring the Python-side form means giving Principles a legality-only successor
  (`_stamp_target` already is one), not simply deleting the function. Confirmed by MCF,
  2026-08-24; the reason is stated at the site so a future reader meets it there rather
  than reading the exception as an oversight.
- **`ChoicesCoreService.make_decision`'s raw status write.** It moves a choice to ACTIVE
  outside the chokepoint, which is what makes Choices' decision-immutability race real —
  but it is a decision-finalization writer with its own event provenance, not a status
  chokepoint, and DRAFT → ACTIVE is not a completion transition. Registered for the PR-4
  straggler sweep alongside `TasksProgressService.unblock_task_if_ready`.
- **ADR-030's check-in store** stays exactly as it is.

## Alternatives rejected

| Alternative | Why not |
|---|---|
| `MATCH … WHERE n.status = $expected` CAS | Evaluates lock-free; measured 39/40 failing trials. Narrows the window, does not close it. |
| Explicit transaction around read + write | ADR-030 needed one because a JSON append is not Cypher-expressible. This condition is, so no Python runs between read and write. |
| `apoc.lock.nodes` | Refused by SKUEL001 (APOC is scoped to `apoc.meta.*`). |
| Compute the stamp in Cypher (`date()`) | The writer decides storage type; a Cypher-side stamp would silently persist a native temporal where every other writer persists an ISO string. |
| A narrow ISP protocol for guarded writes | The guarded write is a peer of `update`, implemented once on the universal mixin, and every domain protocol already reaches `CrudOperations[T]`. A second protocol would be a second path. |
| Managed-retry execution (`execute_write`) | A retry after an unknown commit outcome could re-run the statement and return a prior that misreports the verdict. At-most-once is the correct trade, as in ADR-030. |
