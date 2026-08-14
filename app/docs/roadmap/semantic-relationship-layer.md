# Semantic Relationship Layer — Development Roadmap

*Created: 2026-07-19*
*Status: SUBSTRATE COMPLETE — Phases 1–3 shipped; Phase 4 (consumption) RE-SCOPED and deferred
until a product feature demands it (staged ≠ abandoned). Not abandoned.*
*Owner decision: Mike, 2026-07-19 — "Not abandoned. I want to plan this for future."; re-scope
confirmed 2026-07-21.*

---

## What this is

`core/infrastructure/relationships/semantic_relationships.py` implements RDF-triple
thinking for relationship precision: instead of one generic `RELATED_TO`, edges carry
namespaced semantic meaning (`learn:requires_theoretical_understanding`,
`habit.reinforces`, `concept:specializes`). The module provides:

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

### Phase 4 — Intelligence consumption (Digital layer) — ⚠️ RE-SCOPED, consumption deferred (2026-07-21, PR #TBD)

Step Zero (the Phase-2/3 lesson applied: *build a reader only with a verified consumer
AND verified data*) re-derived all three bullets from the **live code + running graph**.
Result: every bullet is both **consumer-gated** and **data-gated** today. The vocabulary +
property + write-path substrate is fully staged and already threaded through several
graceful-degradation readers — what is missing everywhere is a *reasoner* consumer and any
`semantic_type` **data**. None of the three has a slice that is simultaneously consumed,
data-backed, and net-new-valuable, so consumption is **deferred until a product feature creates
demand** (staged ≠ abandoned — One Path Forward). The three Phase-4 *consumption* surfaces
(Askesis namespace-prefix retrieval, `get_inverse()` consumption, semantic-confidence ranking)
are future features with **no code yet**, so there is nothing to register in the bloat detector.
What *is* staged-and-registered is the semantic **write path** — `create_semantic_*_relationship`
(the four domain facades), `remove_semantic_relationship`, and `infer_relationships` all sit in
`scripts/detect_bloat.py` PLANNED tiers, and `./dev bloat` reports no structurally-dead findings.

**The data gate (measured against the running graph, 2026-07-21):**
- **0 live edges carry `semantic_type`.** The whole semantic write path is live-but-unexercised.
- `confidence` lives entirely on **analog** edges — `APPLIES_KNOWLEDGE`(57), `ENABLES`(26),
  `RELATED_TO`(12), `COMPLEMENTARY_TO`(4), `SIMILAR_TO`(3), `PREREQUISITE_FOR`(3),
  `EXACERBATED_BY`(1) — **none** written by `build_semantic_merge`.

**Bullet A — Askesis namespace-scoped retrieval — DEFERRED (no consumer, no data).**
- Askesis reads nothing semantic: zero `semantic_type` / `SemanticRelationshipType` /
  `find_by_semantic_filter` hits under `core/services/askesis`. This is net-new consumer wiring.
- The *existing* `find_by_semantic_filter` (live via `choices_api` →
  `find_choices_aligned_with_principle`; the goals/habits twins are unreached-by-route) is
  **exact-value-set** filtering — `r.semantic_type IN config.semantic_types` (`_traversal_mixin.py`
  `find_uids_by_semantic_filter`) — **not** namespace-**prefix** scoping (`learn:*`, `concept:*`).
  Over the 0-row graph it returns empty. "Namespace-scoped retrieval" as worded is a different,
  net-new capability with no caller.

**Bullet B — Inverse materialization / query-time inversion (`get_inverse()`) — DEFERRED (zero
readers, no data).**
- `SemanticRelationshipType.get_inverse()` has **zero external consumers** — the only uses are
  self-referential inside `semantic_relationships.py` (`SemanticTriple.get_inverse` / `TripleBuilder`).
  Materializing or query-time-inverting would be building the **first** reader, over an empty edge set.
  Pure decoration today — the KnowledgeDomain trap in miniature.

**Bullet C — Confidence-weighted traversal — REDUNDANT / MISFRAMED (the consumed confidence is a
*different* one).**
- The confidence-weighted traversal that is **already consumed** rides on **analog** edges:
  `_context_query_mixin.py` (`coalesce(r.confidence, 1.0) >= $min_confidence` over the cross-domain
  context path), written by `_learning_state_mixin.py` (`r.confidence = mastery_score`). This is
  learning-progress/grounding confidence, **not** `RelationshipMetadata.confidence`.
- On **semantic** edges, a confidence *threshold* reader already exists and is live
  (`find_uids_by_semantic_filter`, choices route) — but it filters, it does not *rank*, and it
  reads 0 rows. `RelationshipMetadata.confidence` always writes (default `1.0`), so the substrate
  is correct; it simply has no data and no distinct ranking consumer. Bullet C as worded would
  either duplicate the analog case or rank an empty set.

**A reinforcing discovery — the substrate already degrades gracefully.** `semantic_type` is
*already* read by several **live** paths that all handle the 0-row case correctly:
`vector_search_backend.py` (`COALESCE(r.semantic_type, type(r))`), the choices filter
(`find_uids_by_semantic_filter`), and the `get_relationships_by_type` query-by-type path behind
`GET /api/path-steps/relationships`. The matching **write** path (`POST` on the same endpoint →
`create_step_relationship`, admin-only) is live but unexercised. The *delete*-by-type path
(`remove_semantic_relationship`) is **staged, not live** — it has no DELETE route and stays in the
bloat detector's PLANNED tier. So the vocabulary is not merely staged — its read side is threaded
through real readers. The gap is exclusively **a reasoner consumer + data**, not plumbing.

**Net — what unblocks Phase 4 consumption (do these *together*, not before):**
- A real product feature that reads semantic meaning (an Askesis `concept:`-structure surface, or a
  confidence-**ranked** recommendation UI), wired end-to-end with graceful degradation.
- Real `semantic_type` data — either the admin write route gets exercised, or an
  ingestion/enrichment path emits semantic edges.
- **Part A of Phase 3 rides along here**: when a reasoner needs loop-edge meaning, add the curated
  static `RelationshipName → SemanticRelationshipType` map (loop edges only) **and its first reader**
  in the same change — never the map alone.
- Any new `SemanticRelationshipType` annotation surface must resolve through `to_neo4j_name()`
  (a `RelationshipName`) and never emit a raw string — `test_semantic_neo4j_name_drift.py` enforces
  this; extend it if a new annotation surface appears.

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
