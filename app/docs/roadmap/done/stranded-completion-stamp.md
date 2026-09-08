---
title: "Stranded Completion Stamp — the Halves the Guard Could Not Judge"
updated: 2026-09-08
status: "closed 2026-09-07 — both halves shipped (#1298, #1299)"
registered: 2026-09-07
ruled: 2026-09-07
---

# Stranded Completion Stamp — the Halves the Guard Could Not Judge

*Completed case file. The invariant it defends is live in
[../../decisions/ADR-087-status-guarded-conditional-writes.md](../../decisions/ADR-087-status-guarded-conditional-writes.md).*

The stamp's invariant is **non-null exactly when the entity is completed**. A stranded
stamp — non-null on an open entity — reads to every consumer as still-completed.

`_refuse_stranded_stamp` (#1297) closed the half judgeable from the patch alone: a patch
that sets a non-null stamp while **naming** a status other than `COMPLETED`. Two halves
remained, both needing the entity's PRIOR state. Both were reproduced against a real
graph on 2026-09-07 before anything was built, and both are now closed.

**Measured on AuraDB `d2d160c4`, 2026-09-07:** zero stranded stamps live (Task 51 stamped
/ 0 stranded; Goal, Habit, Event, Choice 0 stamped). Both halves were latent, not
realized — nothing needed repairing.

## 1. A patch that carries a stamp and names no status — closed by #1299

`PUT /api/tasks/{uid}` with `{"completion_date": "2026-03-04"}` and no `status` resolved
against whatever status the node already held; on an open entity the stamp stranded.
Reproduced: the update was accepted and the task persisted `status='active'`,
`completion_date='2026-03-04'`.

**Why requiring the status was ruled out.** It makes the rule *unsatisfiable* rather than
strict for Choice: `ChoiceUpdateRequest` exposes `completed_at` and no `status` field at
all, while the separate status endpoint sends `status` alone. (Found by Codex on #1297,
after exactly that over-broad rule was written and had to be pulled back.)

**What shipped.** The claim travels to the write as the prior it *requires*.
`StatusWriteGuard` gained `refuse_unless_prior_in` — the gate stated as a precondition
rather than an enumerated complement, because the complement would miss a node carrying
no status property at all (a vault file can erase one) and go stale the day an
`EntityStatus` member is added. `_bare_stamp_gate` sets it to `{completed}` for exactly
this patch shape, and the five stamping chokepoints convert the resulting `applied=False`
into `stranded_stamp_error`, sourced from the status the write itself saw.

**Refusal over silent clear — the ruling.** The write could have dropped the
contradicting stamp instead (`patch_if_prior_not_in`, one function, no contract change),
which is what the vault door and `TaskUpdateRequest.resolve_completion_date` do when a
status IS named: *status wins*. Mike ruled refusal on 2026-09-07, because here the stamp
is the caller's ONLY edit — discarding it and answering 200 tells them nothing. The
accepted cost was the conversion at five seams; `ChoicesCoreService.update_choice` already
had it for decision immutability and now disambiguates the two gates.

**The doors, enumerated before building.** Only `TaskUpdateRequest` and
`EventUpdateRequest` (status available) and `ChoiceUpdateRequest` (no status field) can
send this shape; Goal and Habit update requests carry no stamp field, no internal caller
builds a bare-stamp intent, and only `status`/`priority` have inline field routes. Habit
cannot reach it at all — `HabitUpdateIntent` has no `completed_at` — so its seam reads
`applied` for the primitive's contract, not for a live rule. The message names both
remedies ("complete it first, or name status in the same update") because no single one
is open at every door.

## 2. A vault file authored open-with-a-stamp, on FIRST ingest — closed by #1298

A file authored `status: in_progress` beside `completion_date: 2026-03-04` landed
verbatim: `status='active'`, `completion_date='2026-03-04'`.

**Why the existing machinery missed it.** The vault door's clear was a *reopen* clear,
fired on a transition OUT of completed. A create has no prior, so there was no transition
and nothing cleared. The guard does not reach the door at all — it `MERGE`s in bulk.

**What shipped.** The clear is decided from the status the entity ENDS UP holding — the
file's when it declares one, otherwise the prior the upsert leaves standing.
`IngestStatusTransitions.reopened_uids` became `stamp_clear_uids`, listing an entity when
that resulting status is not `completed` **and** it has a stamp to lose (the prior was
completed, or this write's payload declares one). Narrower than "every entity that
persisted not completed": handing the clear every ingested uid would also strip stamps
this door never wrote, which at the time would have silently mitigated half 1 while its
ruling was still open.

**Refusing the file stays ruled out.** The vault is the source of truth for user data, so
the door tidies a leftover frontmatter line rather than rejecting the note.

⚠ **The clear is conditional on the persisted state.** `clear_completion_stamps` touches
only an entity that is *not currently completed*, because the write lands at end-of-sync
for the directory door — a wide window in which an app writer may have completed the
entity through the guarded write. An unconditional clear would delete that fresh stamp
and leave a completed entity with none: the same invariant broken from the other side.

## Pins

- `tests/unit/test_status_transition_guard.py` — the gate's shape per domain, and that
  the refusal message stays reachable from a door with no status field.
- `tests/unit/services/test_completion_stamping.py` — each chokepoint's conversion, the
  Choice gate ordering, and the pin that fails if `HabitUpdateIntent` ever gains a stamp.
- `tests/integration/test_status_guarded_update.py` — the primitive honours the
  precondition against a real graph, including a node with no status property.
- `tests/integration/test_stranded_stamp_doors.py` — the Task and Choice doors end to end.
- `tests/integration/test_vault_door_status_transitions.py` — first ingest, re-ingest,
  and a completed sibling in the same sync.
