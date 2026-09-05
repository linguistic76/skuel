---
title: "Event Attendance Wiring (ATTENDS) — Staged Build"
updated: 2026-09-05
status: "staged"
registered: 2026-08-26
trigger: "Mike schedules it — a future arc on his explicit decision (ADR-086 § Follow-ups)"
check: "PLANNED_METHODS carries the attendee triple; the wiring obligations live in ADR-086 § 3 + § Follow-ups"
---

# Event Attendance Wiring (`ATTENDS`) — Staged Build

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

Carried out of the ownership bundle when its closure record was archived — the bundle
itself is done: `docs/roadmap/done/ownership-bundle.md`.

#1119 retargeted the attendee triple (`add_attendee` / `remove_attendee` /
`get_event_attendees`) onto the designed
`(User)-[:ATTENDS {joined_at, role, added_by, status}]->(Event)` shape, with an
invite→accept consent state machine whose actor is always a service parameter from the auth
layer, never the request body. It is **staged, not abandoned**: registered in
`PLANNED_METHODS` (`scripts/detect_bloat.py`). ⚠️ Since #1119 the service methods call
same-named backend methods, so the detector's name-collision mask reports `add_attendee` /
`remove_attendee` as *stale* markings (measured 2026-08-29). What `./dev bloat` says about the
triple is ruled in § Catalog Copies in Code (item 2) — do not restate it here.

**The wiring obligations are recorded once, in ADR-086 § 3 and § Follow-ups** — self-add
eligibility gate, `OWNER_OR_ATTENDEE` visibility, creator auto-attend, ghost filter,
`max_attendees`, role enum. Read them there; do not re-summarise them here (a second copy
is a second thing to keep true).

⚠️ The eligibility gate is a **read-contract** obligation, not a nicety: unconditional
self-add plus `OWNER_OR_ATTENDEE` would let any authenticated user who obtains an event UID
join it and then read a private event — a direct bypass of ADR-085.

**Trigger:** Mike schedules it — a future arc on his explicit decision (ADR-086
§ Follow-ups). The surface stays staged until then.
