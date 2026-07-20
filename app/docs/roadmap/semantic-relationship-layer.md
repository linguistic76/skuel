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

### Phase 3 — Learning-loop semantic annotation

- Annotate loop edges with semantic meaning: e.g. `FULFILLS_EXERCISE` ⇒
  `learn:provides_practical_application`; `RESPONDS_TO_REPORT` ⇒
  `learn:informed_by_knowledge`-family. The loop keeps its edge names; the semantic
  layer adds the reasoning dimension.
- Let ZPD consume `is_blocking` semantics for prerequisite reasoning instead of
  hardcoded relationship lists (`zpd_backend.py` currently hardcodes
  `PREREQUISITE_FOR|ENABLES|ENABLES_KNOWLEDGE`).

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
