---
title: "Structured-List Items Silently Corrupt Without a Nested `uid:`"
updated: 2026-09-06
status: "registered"
registered: 2026-09-06
trigger: "the next touch of Goal/Choice authoring, or the first vault-authored milestone or option that comes back wrong"
check: "`git grep -n 'milestones' core/services/ingestion/validator.py` — empty until a gate exists"
---

# Structured-List Items Silently Corrupt Without a Nested `uid:`

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/`
when nothing in it remains open. Found while driving the vault door in the
[activity-templates-vault-door](done/activity-templates-vault-door.md) arc, PR-2.*

Three fields take a list of maps rather than a list of strings: `milestones` (Goal and
GoalTemplate), `options` (Choice and ChoiceTemplate), and `expressions` (Principle and
PrincipleTemplate). `Milestone` and `ChoiceOption` both declare a **required** `uid`;
`PrincipleExpression` does not, which is why only two of the three are affected.

Authored with the `uid`, the round trip is clean — verified 2026-09-06 against the live graph
through the real read path:

```python
milestones: [{"uid": "ms.1", "title": "M1", "target_value": 1.0}]
# → (Milestone(uid='ms.1', title='M1', …),)
```

Authored **without** it, the read does not fail. `Neo4jGenericMapper.from_node` logs a
`Failed to convert field` warning and falls back to assigning the raw value, so the frozen
dataclass ends up holding the JSON **string** where a `tuple[Milestone, ...]` is declared —
and for a template, `_copy_through` copies that string onto the spawned instance. The write
reported success; nothing downstream is told.

This is the same shape as the offset gate PR-1 shipped in the same arc: a structured value
that persists happily and rebuilds as something wrong. It is **not** template-specific — Goal
and Choice are both vault-ingestible today and have carried this since they were, so the fix
belongs at the shared ingest gate, not on the six template configs.

**The fix**, when it is scheduled: `validate_entity_data` rejects a list-of-maps field whose
element dataclass requires `uid` when any item omits it, with one actionable per-file message —
the division of labour the `created_at` and offset gates already use. Deriving the required-key
set from the element dataclass rather than listing three field names keeps it honest when a
fourth structured field appears.

**Interim:** [ACTIVITY_TEMPLATE_AUTHORING.md § Structured lists](../guides/ACTIVITY_TEMPLATE_AUTHORING.md)
tells template authors to write the `uid`. Goal and Choice authoring has no equivalent note.

**Named cost:** a milestone or option authored without a nested `uid` is stored, reported as
ingested, and read back as a string — so the goal shows no milestones and the choice shows no
options, with a warning in the log as the only signal.
