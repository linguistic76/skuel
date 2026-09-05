---
title: "EntryReport / ActivityReport Search"
updated: 2026-09-05
status: "deferred"
registered: 2026-08-07
trigger: "a teacher workflow wants to search report content directly"
check: "product need; the two hollow report embedding maps in PLANNED_EMBEDDING_MAPS point here"
---

# EntryReport / ActivityReport Search

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

Extracted 2026-08-07 from
[`done/learning-loop-cross-domain-search.md`](done/learning-loop-cross-domain-search.md)
(levels 1–3b complete) — its "Future" section, previously tracked nowhere live. Both report
entities lack BaseService-based search: `EntryReportService` is an LLM generator, not a
BaseService (would need an `EntryReportSearchService`); `ActivityReportService` is standalone
(would need search methods or a BaseService wrapper). Lower priority by design: teachers
search by Exercise or Submission and navigate to feedback via relationships.

**Enable when**: a teacher workflow wants to search report *content* directly rather than
navigate to it — product need, not a data threshold.

**The embedding half rides this want** (2026-08-30): `EMBEDDING_FIELD_MAPS` carries hollow
`ENTRY_REPORT` and `ACTIVITY_REPORT` maps — no event class, nothing builds text — registered
in `PLANNED_EMBEDDING_MAPS` (`scripts/detect_bloat.py`) with `blocked_by` pointing here.
Completing them is ADR-074's quartet (event class, label, post-persist publish in the
writer, worker subscription), scheduled by the same trigger. Never rename this heading
without moving the two pointers — the detector fails `--check` on a dangling one.
