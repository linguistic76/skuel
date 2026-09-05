---
title: "Tasks/Events Edge-Clear on Edit (\"\" → None)"
updated: 2026-09-05
status: "deferred"
registered: 2026-08-07
trigger: "next touch of the Tasks/Events edit forms"
check: "re-verify the bug still reproduces first"
---

# Tasks/Events Edge-Clear on Edit (`""` → None)

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

Extracted 2026-08-07 from [`done/update-intents.md`](done/update-intents.md) Phase 7 notes,
where it was scoped out as "a deferred UX bug, not One-Path teardown; track separately" —
this register is that separate tracking (it previously existed nowhere live).

Clearing an edge picker in the Tasks/Events edit forms submits `""`, which does not map to
`None`, so a linked edge cannot be cleared from the edit UI. Recorded 2026-06-05 during the
ADR-066 migration; **re-verify against the current edit routes on pickup** — two months of
form work have landed since.

**Enable when**: next touch of the Tasks/Events edit forms — a bug this small rides along.
