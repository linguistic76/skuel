---
title: "ZPD Snapshot History & Trend Analysis"
updated: 2026-11-20
status: "deferred"
registered: 2026-08-07
trigger: "a ZPD-over-time consumer exists (progress trends, teacher dashboards)"
check: "MATCH (h:ZPDHistory) RETURN count(h) for accrual"
---

# ZPD Snapshot History & Trend Analysis

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

Extracted 2026-08-07 from [`done/zpd-service-architecture.md`](done/zpd-service-architecture.md)
(implemented) — the deliberately-MVP corner: a single `:ZPDHistory` node per user stores only
the LATEST snapshot (`adapters/persistence/neo4j/zpd_snapshot_backend.py` — "full snapshot
history (timeline arrays, trend analysis) is deferred post-MVP"). Snapshots are written on
pedagogically significant events, so the trigger stream already exists; what is deferred is
keeping the timeline and reading trends from it.

**Enable when**: a consumer wants ZPD-over-time (student progress trends, teacher dashboards) —
and enough snapshot-writing events have accrued for a timeline to say anything.

The history's one read, `ZPDSnapshotBackend.get_latest_snapshot`, is registered staged for that
consumer (`PLANNED_METHODS` in `scripts/detect_bloat.py`, `blocked_by` this entry). It is on no
port and returns the raw row, so wiring it adds a `ZPDSnapshotOperations` member and a typed row.
