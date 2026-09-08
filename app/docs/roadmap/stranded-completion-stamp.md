---
title: "Stranded Completion Stamp — the Half the Guard Cannot Judge"
updated: 2026-09-08
status: "open — one prior-dependent half, awaiting a ruling on its cost"
registered: 2026-09-07
trigger: "next touch of StatusWriteGuard.refuse_if_prior_in or any of the five stamping chokepoints"
check: "PUT a bare completion_date onto an open task (no status in the patch). The stamp should not survive"
---

# Stranded Completion Stamp — the Half the Guard Cannot Judge

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to
`done/` when nothing in it remains open.*

The stamp's invariant is **non-null exactly when the entity is completed**. A stranded
stamp — non-null on an open entity — reads to every consumer as still-completed, and is
what `IngestionWriteBackend.clear_completion_stamps` exists to undo.

`_refuse_stranded_stamp` (`core/services/completion_stamp.py`) closes the half that can
be judged from the patch alone: a patch that sets a non-null stamp while **naming** a
status other than `COMPLETED`. The vault half is closed too (below). One half remains,
and it needs the entity's PRIOR state, which is why it is not a plain refusal.

**Measured 2026-09-07 against AuraDB `d2d160c4`:** zero stranded stamps live (Task
51 stamped / 0 stranded; Goal, Habit, Event, Choice 0 stamped). Both halves were latent,
not realized — nothing on the graph needs repairing, and the open half is a hole in the
contract rather than damage to undo.

## 1. A patch that carries a stamp and names no status — OPEN

`PUT /api/tasks/{uid}` with `{"completion_date": "2026-03-04"}` and no `status` resolves
against whatever status the node already holds. On an open entity the stamp strands.

Reproduced 2026-09-07 against a real graph: the update is accepted and the task persists
`status='active'`, `completion_date='2026-03-04'`.

**Why it is not simply refused.** Requiring the status in the same patch makes the rule
*unsatisfiable* rather than strict for Choice: `ChoiceUpdateRequest` exposes
`completed_at` and no `status` field at all, while the separate status endpoint sends
`status` alone — so a Choice correcting its own timestamp could never satisfy it. (Found
by Codex on #1297, after exactly that over-broad rule was written and had to be pulled
back.)

**The shape that fits.** `StatusWriteGuard.refuse_if_prior_in` — the guard's own
prior-conditional gate — set to every non-completed status. The cost to weigh first:
a refusal there returns `applied=False`, an *outcome* rather than an error, and the
services currently state in comments that they never refuse (`update_task`:
"this guard refuses nothing"). A user typing into the edit form deserves a message, not
a silent no-op, so the outcome has to become an error at the service seam — which is a
contract change across the five stamping chokepoints, not a one-line guard edit.
`ChoicesCoreService.update_choice` already does exactly this conversion for decision
immutability, so the shape is precedented; what is unpriced is doing it five times.

## 2. A vault file authored open-with-a-stamp, on FIRST ingest — CLOSED 2026-09-07

Reproduced 2026-09-07 against a real graph, then closed. A file authored

```
status: in_progress
completion_date: 2026-03-04
```

landed as `status='active'`, `completion_date='2026-03-04'`.

**Why the existing machinery missed it.** The vault door's clear was a *reopen* clear:
`UnifiedIngestionService._apply_status_transitions` fired it on a transition OUT of
completed, derived from the prior status the bulk upsert reads under the node's
write-lock. A create has no prior, so there was no transition and nothing cleared.

**The fix.** The clear is decided from the status the entity ENDS UP holding — the
file's when it declares one, otherwise the prior the upsert leaves standing — rather
than from a transition. `IngestStatusTransitions.reopened_uids` became
`stamp_clear_uids`, and an entity is listed when that resulting status is not
`completed` **and** it has a stamp to lose: either the prior was `completed` (a completed
node always carries one) or this write's payload declares a non-null stamp field. An
entity with no stamp to lose is never listed, so an ordinary sync carries nothing to a
write that could only no-op.

The narrowing is deliberate and is the one place this differs from the shape sketched
when the case file was written ("clear a stamp on any entity that persisted NOT
completed"). Handing the clear every ingested uid would also strip stamps this door
never wrote — including any left by half 1 above — which would make the vault door a
silent partial mitigation of a decision that is still open. The door tidies what the
door put there.

**Refusing the file was the wrong fix, and stays ruled out.** Putting the invariant in
`_stamp_target` — the half `validate_status_target` shares with the guard — makes the
ingestion validator reject the file outright. The vault is the source of truth for user
data and a leftover frontmatter line is something the door should tidy, not something it
rejects a file over.

⚠ **The clear stays conditional on the persisted state.** `clear_completion_stamps` only
touches an entity that is *not currently completed*, because the write happens at
end-of-sync for the directory door — a wide window in which an app writer may have
completed the entity through the guarded write. An unconditional clear would delete that
fresh stamp and leave a completed entity with none: the same invariant broken from the
other side.

Pinned by `tests/integration/test_vault_door_status_transitions.py` —
`test_a_new_file_authored_open_with_a_stamp_is_cleared`,
`test_re_ingesting_that_file_clears_the_stamp_again` (the line stays in the file, so
`n += props` re-writes the stamp every sync and the clear cannot be a one-time repair),
and `test_the_directory_door_spares_the_completed_files_in_the_same_sync`.

**Named cost of what remains:** until half 1 is closed, a bare stamp patch can plant a
permanent completion stamp on an open entity, and every consumer that reads the stamp as
"completed" believes it.
