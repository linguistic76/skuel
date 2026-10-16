---
title: "LP Adaptive Reads Await an Edge-Weight Writer"
updated: 2026-10-16
status: "registered"
registered: 2026-10-10
ruled: "2026-10-10 — the founder: the three LP adaptive reads are staged (PLANNED), not deleted"
trigger: "a writer for the semantic edge fields — an Edge-YAML authoring field for the three no door writes (difficulty_gap, semantic_distance, typical_learning_order) and for strength, or an embedding-derived semantic_distance"
check: "MATCH ()-[r:ENABLES_KNOWLEDGE|REQUIRES_KNOWLEDGE]->() RETURN count(r.difficulty_gap) AS difficulty_gap, count(r.typical_learning_order) AS typical_learning_order — 0 and 0 until a writer exists"
---

# LP Adaptive Reads Await an Edge-Weight Writer

**Status:** registered 2026-10-10 — ruled *staged* by the founder: keep the three
reads, register them, delete nothing. Registered in
[`deferred-work.md`](deferred-work.md) § LP Adaptive Reads Await an Edge-Weight
Writer, and in `scripts/detect_bloat.py` `PLANNED_METHODS` as three DELAYED
entries, each keyed on its `core/services/lp/lp_intelligence_service.py` method
and on that method's `core/services/lp_service.py` delegation.

## What is staged

Three LP intelligence reads rank knowledge by weights on its
`ENABLES_KNOWLEDGE` / `REQUIRES_KNOWLEDGE` edges. The queries live in the backend
mixin `adapters/persistence/neo4j/_lp_intelligence_mixin.py`; the service
methods are in `core/services/lp/lp_intelligence_service.py`, reached through
the `LpService` delegations in `core/services/lp_service.py`.

| Read | Edge fields it weighs | Default when the field is absent |
|---|---|---|
| `find_learning_sequence(start_uid, goal_uid)` | `typical_learning_order` | 999 |
| `get_next_adaptive_step(current_step_uid, user_uid)` | `confidence`, `strength`, `difficulty_gap` | 1.0, 1.0, 0.3 |
| `get_recommended_path_steps(user_uid, max_difficulty, limit)` | `confidence`, `strength`, `difficulty_gap`, `semantic_distance` | 1.0, 1.0, 0.3, 0.5 |

`get_recommended_path_steps` also filters on the weight:
`coalesce(r.difficulty_gap, 0.3) <= $max_difficulty`.

**No production caller.** Outside the backend → service → facade delegation
chain, nothing in `adapters/`, `core/`, `ui/`, `services_bootstrap/` or
`scripts/` calls the three, by attribute or by name string. Only
`tests/integration/test_lp_intelligence_consolidated.py` calls them, through the
facade. Each name is defined at four sites (the mixin, the protocol in
`core/ports/curriculum_protocols.py`, the service, the facade), so `./dev bloat`
reports the entries as "liveness unverifiable". That finding is informational
and never gates.

## What the defaults cost on today's graph

Nothing writes `difficulty_gap`, `semantic_distance` or `typical_learning_order`,
and the live edges carry no `confidence` or `strength` either. A read-only probe
of the daily graph on 2026-10-10 found 13 `ENABLES_KNOWLEDGE` and 3
`REQUIRES_KNOWLEDGE` edges, with each of the five fields set on none of them.
`difficulty_gap`, `semantic_distance` and `typical_learning_order` are not even
property keys in the database. So every weight
these reads compute is its `coalesce` default, which is a constant:

- `get_next_adaptive_step` scores every candidate at `1.0 * 0.6 + 1.0 * 0.4`, so
  its ranking comes down to the `LIMIT 1` tie-break.
- `get_recommended_path_steps` reports `difficulty_gap` 0.3 and
  `semantic_distance` 0.5 for every step. A `max_difficulty` below 0.3 empties
  the result. At 0.3 or above the difficulty filter excludes nothing.
- `find_learning_sequence` orders by 999 everywhere. Its `ORDER BY` also has no
  effect **with** a writer: it sorts one row per edge of a single shortest path,
  and every row returns the same node list. When the writer lands, the read has
  to be reshaped as well, by choosing among candidate paths by order.

The integration test proves the reads work on weighted edges. Its fixture sets
the fields with a raw Cypher `SET`, which is not a writer.

## Where "next enabled step" lives today

The ZPD proximal zone. `adapters/persistence/neo4j/zpd_backend.py` § "Step 2 —
proximal expansion" reads forward enablement, including `ENABLES_KNOWLEDGE`,
without any edge weights. It is live in the FULL tier through `ZPDService` and
`UserContext.zpd_assessment`. The three reads here are the weighted refinement
of that question. They are not a second home for it.

## The writer that would complete it

- **The intended carrier:** `EdgeMetadata` (`core/models/semantic/edge_metadata.py`)
  holds all five fields, and its `to_neo4j_properties` would write them. The
  three factories that set them, `create_prerequisite_metadata`,
  `create_enables_metadata` and `create_related_metadata`, have no caller,
  tests included. None of them sets `typical_learning_order`. The one backend
  method that writes an `EdgeMetadata` onto an edge,
  `_relationship_query_mixin.update_edge_metadata`, has no caller either.
- **What is authorable today:**
  - `confidence`: by Edge YAML. It is on the preparer's property allowlist
    (`core/services/ingestion/preparer.py`, the optional-evidence-fields loop).
  - `strength`: by no door. It is not on the allowlist, and the admin door that
    wrote it on a semantic edge between path steps is retired (ADR-091).
  - `difficulty_gap`, `semantic_distance`, `typical_learning_order`: no door
    writes them.
- **The completing change**, either of:
  1. Authoring fields. Add the missing names to the Edge YAML preparer
     allowlist, so the content vault can state them on the edges it already
     declares.
  2. An embedding-derived `semantic_distance`, computed from the two
     endpoints' vectors. That is a **Digital-layer** feature: it needs
     `INTELLIGENCE_TIER=full`, embeddings, and an answer to what it means when
     the tier is `core`. It gets its own arc. It does not belong in the PR that
     wires these reads.

Either way the PLANNED entries come out when a surface calls the reads, and the
`check:` above stops reading 0.
