---
title: "Line Deletions Leave EXTRACTED_FROM Edges"
updated: 2026-09-15
status: "done — the extraction pre-pass retires an edge whose line is gone by both keys (🆔 absent, digest on no 🆔-less line); the task stays; a stripped token is re-minted by the outbound injection arm; the 🆔 is written in front of a trailing ✅ so the done marker stays trailing"
registered: 2026-08-24
trigger: "the R4 build, or the next reconciler touch"
check: "tests/integration/test_vault_done_date_hash_roundtrip.py::TestDeletedLinesRetireTheirEdges (3 end-to-end cases); one ./dev vault-sync --force retires the pre-fix dangling edges on files unchanged since"
---

# Line Deletions Leave `EXTRACTED_FROM` Edges

*Case file for the former [deferred-work.md](../deferred-work.md) entry of the same name.*

**Status: ✅ DONE — 2026-09-15.** Built on the "next reconciler touch" trigger — see *What
landed* at the end. The heading is kept verbatim: `scripts/cleanup_duplicate_vault_tasks.py`
and `scripts/detect_bloat.py` cite it by name.

Deletion propagation is FILE-level (entity file deleted → entity deleted). Deleting a task LINE
from a note that still exists leaves the `EXTRACTED_FROM` edge (and its hash) behind. Observed
live in the #1143 read-only census (2026-08-23): 5 🆔-bearing edges point into
`Weekly/2026-W28.md`, whose file holds no checkbox line at all; edge ids in that PR's thread.
(The same census's other 43 hash-orphan edges are bridge/DSL prose entities that never had a
physical line — expected, and any fix must leave those alone.)

**Candidate fix (as registered):** retire the edge (or blank its hash) when a sync finds the
line gone from its file — scoped to edges that ever had a physical line (`vault_id`-bearing).
**Named cost while open:** dead provenance rows fed the extraction guards' read on every future
sync of the entry, forever — and the same text typed back later hashed into the dead edge and
was swallowed by Guard 2 (no task, no 🆔, and smart mode then checkpointed the file, so nothing
would ever extract it).

## What landed (2026-09-15)

**Retire, don't blank — and the verdict needs both keys.** The edge is *deleted*, not
blanked: an edge-less task is exactly the shape a deleted *note* already leaves its tasks in
(the hygiene audit and the duplicate-task cleanup both treat it as legitimate history), and a
blanked edge would have been a third shape every reader of `EXTRACTED_FROM` had to learn. The
first cut retired on "🆔 absent from the text" alone and the existing already-checked-line
test caught it: that test rewrites the note without the injected 🆔, which under a pure-🆔
rule reads as a deleted-and-retyped line and re-mints a duplicate COMPLETED task — the #1143
shape all over again. **A stripped token is not a deleted line.** So an edge's line is gone
only when BOTH of ADR-070's keys are: its 🆔 appears nowhere in the raw text (the token scan,
not the parse — a 🆔 inside a code fence is still on a line the write-back can find) AND no
🆔-less parsed line hashes to its digest.

- **Where:** the extraction pre-pass in `ActivityExtractorService.extract_and_create`, ahead
  of the Guard 2b refresh — inbound, so Guard 2's exact-match set is clean in the *same*
  ingest as a delete-and-retype (an outbound-only detector would have let Guard 2 swallow the
  retyped line first, and smart mode checkpoint the file). Persisted by
  `UserEntryProcessingService` through `UserEntryService.delete_extracted_from_links` →
  `_RelationshipCrudMixin.delete_extracted_from_links`, **keyed on `(entity_uid, vault_id)` as
  read** so a concurrently re-keyed edge is left alone; a failure fails the run at
  `persist_links` like any provenance write (the file stays out of the checkpoint, the next
  sync retries). Recorded as `retired_links` in the run summary.
- **The task stays.** A vault-side line deletion is not a SKUEL deletion while inbound
  propagation is parked (§ R4). No sync counter, no warning: a warning flips the header to
  "finished with problems" over routine tidying, and the count is one plumb away if wanted.
- **The stripped-token half needed the reconciler.** Its injection arm now runs for any edge
  whose 🆔 the file does not carry (`not vault_id or vault_id not in present_ids`), finds the
  line by digest, and re-mints — re-keying the edge through the existing persist. Before, a
  stale 🆔 sat on the write-back arm forever, aiming `mark_done` at an id no line carried.
- **A second pre-existing defect surfaced from that:** `apply_inject_id` appended the 🆔
  after a trailing `✅ date`, un-trailing the marker `apply_mark_done` keys its no-op on, so
  the next sync appended a second date to an already-done line — reachable today through the
  hand-authored `- [x] … ✅ date` create door. The 🆔 now goes in front of the marker (the
  plugin's own order); the 🆔-blind digest is the same either side.
- **Residual, by design:** the same-edit race — a task completed in SKUEL whose unchecked line
  is deleted and retyped *before* the write-back lands reads as a stripped token (re-keyed,
  then checked off), not as a new occurrence. After the write-back the `✅` inside the digest
  tells them apart. And Guard 4's no-provenance-write rule (Kody #501) still leaves a line
  retyped for an ACTIVE task merged but untracked — the cleanup script's LINE-BACKED class,
  unchanged by this work and R4's to close.
- **Historical edges** (the W28 five, and any file unchanged since its deletion) are retired
  by one `./dev vault-sync --force` — a plain sync skips unchanged files before the pre-pass
  runs.
