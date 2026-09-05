---
title: "Principles _validate_update Reform (or Deletion)"
updated: 2026-09-05
status: "ruling needed"
registered: 2026-08-07
trigger: "next substantive touch of the Principles (or Events) update path"
check: "ruling: reform the rules onto the intent, or delete the hook"
---

# Principles `_validate_update` Reform (or Deletion)

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

Extracted 2026-08-07 from [`done/update-intents.md`](done/update-intents.md) Phase-7 notes
("Reforming these rules onto the intent is tracked separately") — this register is that
tracking; it previously existed only in code docstrings and the archive.

`PrinciplesCoreService._validate_update` is stale in three of its four rules (keys on
`label` not `title`; the strength rule's casing never matches; the well-established rule
demands a `modification_reason` field that exists nowhere — **unsatisfiable**), yet it is
still live on the base `update` contract. `update_principle` deliberately bypasses it
backend-direct, because routing through `super().update` would activate the unsatisfiable
gate and block CORE/STRONG description edits. Resolution is a ruling, not just work: reform
the rules onto the intent (making both paths validate identically), or delete the hook per
the create-rules precedent in the same file (#963 — length bounds belong to the request
model). Either way the two-path behavioral split ends.

**Same class, found 2026-08-24 (ADR-087 PR-3), in Events**: `EventsCoreService._validate_update`
Rule 2 keys on `duration_minutes`, and two of the three fields its past-event exception allows
(`notes`, `quality_score`) are likewise absent from `EventUpdateIntent` — so this door cannot
reach them at all. Rule 1 and the `tags` exception ARE live and are now pinned by tests. Smaller
than the Principles case (nothing here is *unsatisfiable*, just unreachable), and the same
ruling settles both: reform the rules onto the intent, or delete what the intent cannot carry.

**Enable when**: next substantive touch of the Principles update path — do not let a new
caller reach the base `update` contract before this is resolved.
