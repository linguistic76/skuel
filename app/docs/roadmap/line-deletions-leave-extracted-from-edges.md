---
title: "Line Deletions Leave EXTRACTED_FROM Edges"
updated: 2026-09-05
status: "registered"
registered: 2026-08-24
trigger: "the R4 build, or the next reconciler touch"
check: "census shape in the case file; re-probe the W28 edges before building"
---

# Line Deletions Leave `EXTRACTED_FROM` Edges

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

Deletion propagation is FILE-level (entity file deleted → entity deleted). Deleting a task LINE
from a note that still exists leaves the `EXTRACTED_FROM` edge (and its hash) behind. Observed
live in the #1143 read-only census (2026-08-23): 5 🆔-bearing edges point into
`Weekly/2026-W28.md`, whose file holds no checkbox line at all; edge ids in that PR's thread.
(The same census's other 43 hash-orphan edges are bridge/DSL prose entities that never had a
physical line — expected, and any fix must leave those alone.)

**Candidate fix:** retire the edge (or blank its hash) when a sync finds the line gone from its
file — scoped to edges that ever had a physical line (`vault_id`-bearing).
**Trigger:** the R4 build (a reconciliation branch needs honest provenance) or the next
reconciler touch.
**Named cost:** dead provenance rows feed the extraction guards' read on every future sync of
the entry, forever.
