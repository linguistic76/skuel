---
title: "The PathStep's `GUIDED_BY_PRINCIPLE` (O2)"
updated: 2026-10-08
status: "deferred"
registered: "2026-10-04 (Activity Links arc, open item O2)"
ruled: "2026-10-04 — deferred by the founder (\"look at that closer later\")"
trigger: "the founder's ruling on keep-vs-move, or the next change to how a PathStep names its guiding principles (the `principle_uids` frontmatter field, PS_CONFIG's definition, or the PathStep intelligence reads)"
check: "`git grep -nw GUIDED_BY_PRINCIPLE -- core adapters` hits only the enum member, PS_CONFIG's one definition and `ps_intelligence_backend.py`; live: MATCH (a)-[r:GUIDED_BY_PRINCIPLE]->(b) RETURN labels(a), count(r) — PathStep sources only"
---

# The PathStep's `GUIDED_BY_PRINCIPLE` (O2)

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

The one open item the [Activity Links arc](done/activity-links-arc.md) (closed 2026-10-08) left
behind. [ADR-090 §7](../decisions/ADR-090-one-link-per-fact-a-view-per-domain.md) retires six edge
types from the links between Activities; `GUIDED_BY_PRINCIPLE` is the one that also has a source
outside the Activities, and the rulings cover links between Activities only.

## What is true now

- **Between Activities the type is gone.** The goal's use (its registry definition, the
  `connections.aligned_with_principle` frontmatter field, the goal → principle edges, the vault
  file's field) retired with PR 2 (#1504, 2026-10-05); the stored-edge migration left no goal-side
  edge, and the close row's census (2026-10-08) found none.
- **The PathStep's use stays, whole.** `RelationshipName.GUIDED_BY_PRINCIPLE`
  (`core/models/relationship_names.py`), PS_CONFIG's one definition
  (`core/models/relationship_registry.py`, the PathStep's `guiding_principles` from the
  `principle_uids` frontmatter field), its `GRAPH_CONTRACT.yaml` rows, and four reads in
  `adapters/persistence/neo4j/ps_intelligence_backend.py` (the PathStep intelligence's
  principle-aligned PathSteps). The live graph holds one edge,
  `ps.self-reflection.noticing-patterns` → `principle.observation-before-action`, authored by
  `Ps/Ps_dev/noticing-patterns_Ps.md` in the content vault.
- The type is therefore **not** in `scripts/health/stale_names.py`: it is live.

## The question deferred

Keep the type for that one curriculum source, or move the PathStep's guiding principles onto
another edge (e.g. the principle's own verb, as the Activities now use `SUPPORTS_GOAL` and
`INFORMS_CHOICE`). ADR-090 § Consequences counts the outcome either way: "five or six edge types
fewer". If the PathStep's use moves, `GUIDED_BY_PRINCIPLE` retires outright — enum member,
definition, contract rows, the frontmatter field's edge type, the stored edge (migrated) and the
vault file — under the arc's standing convention (the done arc doc § Standing conventions), and
the name joins `stale_names.py`.

Settle it in prose with the founder before the first edit, as every arc row was.
