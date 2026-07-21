# Semantic Relationship Layer — Development Roadmap

*Created: 2026-07-19*
*Status: PLANNED — staged capability, not abandoned (One Path Forward: staged ≠ abandoned)*
*Owner decision: Mike, 2026-07-19 — "Not abandoned. I want to plan this for future."*

---

## What this is

`core/infrastructure/relationships/semantic_relationships.py` implements RDF-triple
thinking for relationship precision: instead of one generic `RELATED_TO`, edges carry
namespaced semantic meaning (`learn:requires_theoretical_understanding`,
`habit:reinforces`, `concept:specializes`). The module provides:

- **`RelationshipNamespace`** — 8 namespaces (`learn`, `task`, `habit`, `cross`, `time`, `skill`, `concept`, `moc`)
- **`SemanticRelationshipType`** — 81 namespaced predicates with behavior:
  `to_neo4j_name()` (namespace-stripped UPPER name for Cypher), `is_blocking`,
  `get_inverse()`, `to_semantic()` (progressive enhancement from generic `RelationshipType`)
- **`RelationshipMetadata`** — RDF-reification-inspired edge metadata (confidence,
  temporal validity, evidence, strength)
- **`TripleBuilder`** — subject–predicate–object construction

## Current state (audited 2026-07-19)

The layer is **wired and consumed** — this is not dead code:

| Consumer | Role |
|---|---|
| `core/services/infrastructure/semantic_relationship_linker.py` | Cross-domain semantic linking (`.via(semantic_type.to_neo4j_name())`) |
| `core/services/ps/ps_semantic_service.py` | PathStep semantic operations |
| `adapters/persistence/neo4j/_semantic_mixin.py` | Backend semantic traversals |
| `adapters/persistence/neo4j/query/cypher/semantic_queries.py` | Query builders incl. `create_semantic_relationship` (write path) |
| `adapters/persistence/neo4j/query/unified_query_builder.py` | Semantic-aware query composition |
| Vector search (`neo4j_vector_search_service.py`, `vector_search_backend.py`) | Semantic-enhanced search |
| Facades: `tasks_service`, `goals_service`, `choices_service`, `habits/_orchestration_mixin`, `relationships/_intelligence_mixin` | Domain entry points |

**But it is disjoint from the two central relationship authorities:**

1. **`RelationshipName`** (170 members, `relationship_names.py`) — the canonical Neo4j
   edge vocabulary, lint-enforced (SKUEL013). `SemanticRelationshipType` bypasses it:
   `to_neo4j_name()` emits edge names (`DEVELOPS_SKILL`, `REQUIRES_KNOWLEDGE`, …) that
   sometimes collide with `RelationshipName` members and sometimes exist only in the
   semantic layer. Two enums can emit the same edge string with no cross-check.
2. **`relationship_registry.py`** — the declarative node↔relationship map. Semantic
   edges are not registered, so enrichment/search config is blind to them.
3. **The Learning Loop** — none of the loop edges (`FULFILLS_EXERCISE`, `REPORT_FOR`,
   `RESPONDS_TO_REPORT`, `REVISES_EXERCISE`) participate in the semantic layer.

## Why it matters (the vision)

The semantic layer is the natural home for **machine reasoning over the graph**:
inverse inference (`get_inverse()`), blocking detection (`is_blocking`), namespace-scoped
traversal, and edge metadata (confidence/evidence/temporal validity) are exactly what
Askesis and ZPD need to reason about *why* entities connect, not just *that* they do.
It is the Digital-layer enrichment of the Analog relationship vocabulary.

## Development plan

### Phase 1 — Reconcile the vocabularies (foundation) — ✅ DONE (2026-07-20, PR #TBD)

The precondition for everything else: one edge name, one owner. **Shipped.**

- ✅ Collision/mapping audit: 81 semantic members → 6 collide with a `RelationshipName`
  value, 75 were semantic-only (unregistered). Two members even collided *within* the
  enum (`cross:related_to`/`moc:related_to`, `concept:child_of`/`moc:child_of`) because
  `to_neo4j_name()` discarded the namespace.
- ✅ Authority rule (ratified as written): **`RelationshipName` owns every string that
  reaches Neo4j.** `to_neo4j_name()` returns a `RelationshipName` via the 81-member
  `SEMANTIC_TO_RELATIONSHIP_NAME` map (name-aligned/direction-clear → the matching
  semantic edge; ambiguous → `RELATED_TO`, the coarse bucket). No semantic type can emit
  unregistered vocabulary again, by construction.
- ✅ **Precision preserved as an edge property**, not lost to the collapse: `build_semantic_merge`
  (and the linker's fluent `.relate()` path) write `semantic_type: "learn:extends_pattern"`.
  This also disambiguates the two intra-enum collisions and gives Phases 3–4 a real
  substrate. Delete/query-by-type gained a `semantic_type` filter to stay precise.
- ✅ Drift test: `tests/unit/test_semantic_neo4j_name_drift.py`.
- ✅ Closed the SKUEL030 baseline entirely (§9's two pairs); `test_lint_skuel.py`'s
  baseline fixture rewritten to inject a synthetic entry.

**What the audit changed for later phases:** §9 turned out NOT to be a writer-less read —
the live admin route `POST /api/path-steps/relationships` reaches `build_semantic_merge`,
so the semantic layer was a *second live emitter*, not dead code. That strengthens the
case for Phase 2 (register the edges) and Phase 4 (reason over them): the write path is
real, only unexercised (0 live rows). The `semantic_type` property Phase 1 introduced is
the natural key for the registry work in Phase 2 and the confidence-weighted traversal in
Phase 4 — both should key on it, not on the coarse `RelationshipName`. Sequence 2→3→4 still
holds.

### Phase 2 — Register semantic edges declaratively

- Add semantic edge definitions to `relationship_registry.py` (or a
  registry section generated from the semantic enum) so enrichment/search see them.
- Surface `RelationshipMetadata` fields (confidence, evidence, valid_from/until) as
  sanctioned edge properties in the registry definitions.

### Phase 3 — Learning-loop semantic annotation — ⚠️ RESOLVED, mostly deferred (2026-07-21, PR #TBD)

Step Zero (the Phase-2 lesson applied: *register/annotate a name only with a verified
consumer*) re-derived both parts from the live code + graph and found the roadmap's
original wording — written before Phase 1's property model — is consumer-gated decoration
(Part A) and a silent regression (Part B). Both original bullets are struck; what shipped is
a small, consumed slice.

**Part A — annotate loop edges (`FULFILLS_EXERCISE` ⇒ `learn:provides_practical_application`,
etc.) — DEFERRED into Phase 4.** No consumer exists today:
- All four loop edges are written as plain `MERGE`/`CREATE`, no `semantic_type`, never
  through `build_semantic_merge` (`_user_entry_lifecycle_mixin.py`; `exercise_backends.py`).
  Zero live edges carry a `semantic_type` property.
- The only loop-edge *reader*, ZPD Step 6, traverses `FULFILLS_EXERCISE` **structurally**
  (a join to `APPLIES_KNOWLEDGE`) — it never reads the edge's meaning. No reasoner consumes
  loop-edge semantics.
- Annotating now would be the KnowledgeDomain trap in miniature (registered ≠ consumed).
  **Fold Part A into Phase 4**: annotate a loop edge only when Phase 4's reasoner actually
  reads it. Preferred mechanism when that day comes: a **static curated map**
  `RelationshipName → SemanticRelationshipType` (loop edges only — the inverse of the
  many-to-one `SEMANTIC_TO_RELATIONSHIP_NAME` is one-to-many and useless), consulted by the
  reasoner. Write `semantic_type` onto the edge itself only if a Cypher filter needs it.

**Part B — "let ZPD consume `is_blocking` instead of the hardcoded edge list" — DECLINED
as a regression. A de-hardcoding refactor shipped instead.** The premise was wrong twice:
- ZPD's edge lists were **not** sloppy. `zpd_backend.py` uses THREE deliberately-different,
  direction-correct, documented, test-frozen sets: proximal expansion (Step 2) follows
  `PREREQUISITE_FOR|ENABLES|ENABLES_KNOWLEDGE` **forward** (enablement); readiness (Step 3)
  and blocking gaps (Step 5) follow **only** `<-[:PREREQUISITE_FOR]-` incoming (an enabler is
  an invitation, never a gate — ruling 2026-07-10).
- `SemanticRelationshipType.is_blocking` resolves — via `SEMANTIC_TO_RELATIONSHIP_NAME` — onto
  the coarse edges `{REQUIRES_KNOWLEDGE, BLOCKS, PRECEDES}`. **None is `PREREQUISITE_FOR`**;
  no semantic type maps to `PREREQUISITE_FOR` at all. Live counts: ZPD's gate traverses 9
  `PREREQUISITE_FOR` edges; the `is_blocking` set is 4 disjoint edges. Wiring ZPD to
  `is_blocking` would silently swap the "what should I learn next" traversal for a mismatched
  edge set — a regression. `is_blocking` also has **zero consumers** anywhere (grep confirms).
- **What shipped instead** (`zpd_backend.py`): the three sets were de-hardcoded into named,
  `RelationshipName`-derived constants (`_PROXIMAL_EXPANSION_EDGES`, `_PREREQUISITE_GATE_EDGE`)
  and the query is built from them via byte-identical `.replace()` — one source of truth per
  set, same direction discipline, **no traversal change** (emitted Cypher byte-identical,
  pinned by `test_zpd_backend_query_shape.py`, which also asserts the gate is *not* sourced
  from the `is_blocking` vocabulary). NOT `is_blocking`.

**Net for Phase 4:** Part A rides along — when a reasoner needs loop-edge meaning, add the
curated map + its first reader together. `is_blocking` stays unwired unless a *new* consumer
genuinely wants blocking-detection over the coarse `{REQUIRES_KNOWLEDGE, BLOCKS, PRECEDES}`
edges (a different question from ZPD's prerequisite gate).

### Phase 4 — Intelligence consumption (Digital layer)

- Askesis: namespace-scoped retrieval ("show me `concept:` structure around this Ku").
- Inverse materialization or query-time inversion via `get_inverse()`.
- Confidence-weighted traversal using `RelationshipMetadata.confidence` in ranking.

## Non-goals

- Migrating loop edge names to namespaced forms — the loop vocabulary is settled
  (decision 2026-07-19: keep `FULFILLS_EXERCISE` / `REPORT_FOR` / `REVISES_EXERCISE` /
  `RESPONDS_TO_REPORT`).
- Full RDF/OWL tooling. The RDF influence is *thinking discipline*, not a triple-store
  migration; Neo4j remains the committed store (ADR-044).

## Related

- `/docs/architecture/RELATIONSHIPS_ARCHITECTURE.md`
- `/docs/architecture/ENUM_ARCHITECTURE.md`
- ADR-026 (unified relationship registry), ADR-044 (Neo4j committed choice)
- Learning-loop contract work (2026-07 DSL review): EntryReport registry config,
  persistence-layer enum enforcement
