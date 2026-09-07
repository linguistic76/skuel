---
title: "Stranded Completion Stamp on Vault First Ingest"
updated: 2026-09-07
status: "open — needs a fix at the ingest seam"
registered: 2026-09-07
trigger: "next touch of UnifiedIngestionService._apply_status_transitions or the bulk-upsert node template"
check: "author a NEW vault file with an open status and a completion_date; the stamp must not survive the ingest"
---

# Stranded Completion Stamp on Vault First Ingest

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to
`done/` when nothing in it remains open.*

A vault file authored with an open status **and** a completion stamp strands the stamp
on FIRST ingest. Reproduced 2026-09-07 against a real graph:

```
status: in_progress
completion_date: 2026-03-04
```

lands as `status='active'`, `completion_date='2026-03-04'` — an entity that reads to
every consumer as still completed, which is exactly the state
`IngestionWriteBackend.clear_completion_stamps` exists to prevent.

**Why the existing machinery misses it.** The vault door's clear is a *reopen* clear:
`UnifiedIngestionService._apply_status_transitions` fires it on a transition OUT of
completed, derived from the prior status the bulk upsert reads under the node's
write-lock. A create has no prior, so there is no transition and nothing clears. The
re-ingest case IS covered and pinned
(`tests/integration/test_vault_door_status_transitions.py::test_reopen_clears_a_stamp_the_file_still_carries`);
only the first ingest is open.

**Why the ADR-087 guard fix does not reach it.** `_refuse_stranded_stamp` (ruled and
shipped 2026-09-07, see [done/task-update-future-completion-date.md](done/task-update-future-completion-date.md))
is called from `status_transition_guard`, and the vault door does not go through
`update_with_status_guard` — it `MERGE`s through the bulk upsert. The two doors enforce
the invariant by different mechanisms, and only the app-side one was closed.

**Refusing the file is the wrong fix, and is ruled out.** It was tried first, by putting
the invariant in `_stamp_target` — the half `validate_status_target` shares with the
guard — and it made the ingestion validator reject the file outright. The vault is the
source of truth for user data and a leftover frontmatter line is something the door
should tidy, not something it should reject a file over. The fix belongs in the
post-persist step: clear a stamp on any entity that persisted NOT completed, not only
on one that transitioned out of completed.

⚠ **The clear must stay conditional on the persisted state.** The existing clear is
deliberately conditional (`clear_completion_stamps` only touches an entity that is *not
currently completed*) because the write happens at end-of-sync for the directory door —
a wide window in which an app writer may have completed the entity through the guarded
write. An unconditional clear would delete that fresh stamp and leave a completed entity
with none: the same invariant broken from the other side.

**Named cost:** until fixed, a hand-authored vault file can plant a permanent
completion stamp on an open entity, and every consumer that reads the stamp as
"completed" believes it.
