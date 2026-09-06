---
title: "Tasks/Events Edge-Clear on Edit (\"\" → None)"
updated: 2026-09-06
status: "done"
registered: 2026-08-07
closed: 2026-09-06
---

# Tasks/Events Edge-Clear on Edit (`""` → None)

Extracted 2026-08-07 from [`update-intents.md`](update-intents.md) Phase 7 notes, where it
was scoped out as "a deferred UX bug, not One-Path teardown; track separately".

**Recorded claim (2026-06-05):** clearing an edge picker in the Tasks/Events edit forms
submits `""`, which does not map to `None`, so a linked edge cannot be cleared from the
edit UI.

## Outcome: the bug does not reproduce — the mechanism works

Re-verified 2026-09-06 by driving the production path, as the register's `check:` demanded.
`parse_form_body` (`adapters/inbound/form_helpers.py`) maps a blank form value to `None`,
the field then sits in `model_fields_set`, and `to_intent()` carries `None` — the ADR-066
explicit-clear signal. Both facades already consume it: `TasksService._sync_relationship_edges`
deletes the edges of that kind and appends no replacement candidate, and
`EventsService._replace_edge` deletes without creating. Reverting the mapping to
"omit blanks" makes the clear unreachable again, which is how the claim was confirmed to be
about that one seam.

The mapping predates the record — it landed 2026-03-23 with the `parse_form_body` helper,
and the edit routes were converged onto that helper afterwards. The claim was recorded
against a door that had already moved.

## What was actually wrong, and what closed the item

- **A comment asserted the opposite of the code.** `adapters/inbound/events_ui.py` read
  "Fields the user left blank stay UNSET and are not written" — false for any field the
  edit form renders, which is every field a user can blank. A reader trusting it would
  conclude clearing is impossible, which is plausibly how the stale claim survived two
  re-reads. Corrected on both doors, each now naming the `"" → None` step.
- **The seam had no test.** The render half was pinned
  (`tests/unit/ui/test_activity_forms_render.py`) and the graph half was pinned
  (`tests/integration/test_task_goal_edge_update_roundtrip.py`), but nothing covered the
  form→intent step between them. `tests/unit/adapters/test_edit_form_edge_clear.py` now
  does, deriving the picker names from the rendered edit form so a rename on one side of
  the seam fails instead of silently dropping the value. It also pins the other half of
  the contract — a field the edit form does not render stays `UNSET`, so
  `applies_knowledge_uids` is never blanked into an edge wipe on save.

Tasks and Events remain the only two edit forms carrying pickers; `GoalEditForm` has none
(`GoalUpdateRequest` exposes no single-UID cross-domain field).
