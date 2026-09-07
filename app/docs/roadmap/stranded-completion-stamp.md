---
title: "Stranded Completion Stamp — the Halves the Guard Cannot Judge"
updated: 2026-09-07
status: "open — two prior-dependent halves"
registered: 2026-09-07
trigger: "next touch of UnifiedIngestionService._apply_status_transitions, the bulk-upsert node template, or StatusWriteGuard.refuse_if_prior_in"
check: "author a NEW vault file with an open status and a completion_date; and PUT a bare completion_date onto an open task. Neither stamp should survive"
---

# Stranded Completion Stamp — the Halves the Guard Cannot Judge

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to
`done/` when nothing in it remains open.*

The stamp's invariant is **non-null exactly when the entity is completed**. A stranded
stamp — non-null on an open entity — reads to every consumer as still-completed, and is
what `IngestionWriteBackend.clear_completion_stamps` exists to undo.

`_refuse_stranded_stamp` (`core/services/completion_stamp.py`) closes the half that can
be judged from the patch alone: a patch that sets a non-null stamp while **naming** a
status other than `COMPLETED`. Two halves remain, and both need the entity's PRIOR
state, which is why neither is a plain refusal.

## 1. A patch that carries a stamp and names no status

`PUT /api/tasks/{uid}` with `{"completion_date": "2026-03-04"}` and no `status` resolves
against whatever status the node already holds. On an open entity the stamp strands.

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

## 2. A vault file authored open-with-a-stamp, on FIRST ingest

Reproduced 2026-09-07 against a real graph. A file authored

```
status: in_progress
completion_date: 2026-03-04
```

lands as `status='active'`, `completion_date='2026-03-04'`.

**Why the existing machinery misses it.** The vault door's clear is a *reopen* clear:
`UnifiedIngestionService._apply_status_transitions` fires it on a transition OUT of
completed, derived from the prior status the bulk upsert reads under the node's
write-lock. A create has no prior, so there is no transition and nothing clears. The
re-ingest case IS covered and pinned
(`tests/integration/test_vault_door_status_transitions.py::test_reopen_clears_a_stamp_the_file_still_carries`);
only the first ingest is open.

**Why the guard does not reach it.** The vault door `MERGE`s through the bulk upsert
rather than going through `update_with_status_guard`. The two doors enforce this
invariant by different mechanisms, and only the app-side one is closed.

**Refusing the file is the wrong fix, and is ruled out.** Putting the invariant in
`_stamp_target` — the half `validate_status_target` shares with the guard — makes the
ingestion validator reject the file outright. The vault is the source of truth for user
data and a leftover frontmatter line is something the door should tidy, not something it
rejects a file over. The fix belongs in the post-persist step: clear a stamp on any
entity that persisted NOT completed, not only on one that transitioned out of completed.

⚠ **The clear must stay conditional on the persisted state.** `clear_completion_stamps`
only touches an entity that is *not currently completed*, because the write happens at
end-of-sync for the directory door — a wide window in which an app writer may have
completed the entity through the guarded write. An unconditional clear deletes that
fresh stamp and leaves a completed entity with none: the same invariant broken from the
other side.

**Named cost:** until both are closed, a hand-authored vault file or a bare stamp patch
can plant a permanent completion stamp on an open entity, and every consumer that reads
the stamp as "completed" believes it.
