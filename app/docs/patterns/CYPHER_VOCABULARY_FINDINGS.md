# Cypher Vocabulary Findings (SKUEL030 introduction sweep, 2026-07-19)

**Status:** open backlog, being worked in tranches. Every open item is baselined
in `scripts/lint_skuel.py::SkuelLinter.SKUEL030_BASELINE` (or suppressed with a
`// noqa: CYP011`), so it does not block CI — but none of it is *accepted*.

## Decision log (Mike, 2026-07-20)

- **§1 `:Report` cluster → DELETE** the whole `AnalyticsRelationshipBackend`
  (tranche 2). The audit found it consumer-less on top of label-less: the
  factory stores it as `self.analytics` and no code calls any of its 12
  methods; the live report stack is `ReportRelationshipService` + `REPORT_FOR`.
- **§7 writer-less reads → REPOINT-OR-DELETE** (tranche 3): repoint
  `HAS_PROGRESS`/`UserProgress`/`MasteryRecord` reads onto the live
  `MASTERED`/`IN_PROGRESS`/`ENROLLED_IN` vocabulary; delete reader paths with
  no live equivalent (`STRUGGLING_WITH`, `NEEDS_REVIEW`, `LearningPreference`,
  `JournalAnalytics`, `ContentMetadata`). No new writers inside this backlog —
  wanted features go to the roadmap instead.
- **§9 semantic-as-edge → DEFERRED** to semantic-relationship-layer roadmap
  Phase 1. Pairs stay baselined until that work reconciles them.
- **Tranche order:** T1 = §3+§4 (done below) · T2 = §6 LEARNING fix+migration,
  §1 deletion, §11 Expense (done below) · T3 = §7 per decision, §2 label
  mismatches · T4 = §5 sibling filter, §8 near-duplicates.
- **Tranche 2 shipped (2026-07-20):** §6, §1 and §11 resolved as ratified —
  6 baseline pairs closed (38 → 32). One migration covers both graph-side
  changes: `scripts/migrations/retire_learning_edge_and_expense_label_2026_07.cypher`.

The baseline holds **`(file, name)` pairs**, so only the known call sites are
exempt: introducing any of these names in a *new* file still fails the rule. It
is a shrinking list — fixing an item means deleting its entries, and a test fails
if a baselined name later gets registered or a baselined path disappears.

## Why these are findings, not style nits

Neo4j validates neither node labels nor relationship types. `MATCH (r:Report)`
against a label that does not exist raises nothing — it returns zero rows,
silently, forever. Every item below is a query that reads vocabulary nothing
writes, which means it returns nothing (or, for `WHERE NOT` filters, everything).

Fixing them changes query semantics, so they are deliberately excluded from the
PR that introduced the rule. See `docs/patterns/linter_rules.md § SKUEL030`.

---

## 1. The `:Report` cluster — ✅ RESOLVED (tranche 2, 2026-07-20)

**Was the highest-severity item.** `AnalyticsRelationshipBackend` was
instantiated at composition time (`services_bootstrap/_intelligence_hub.py`) and
ran 13 `MATCH (report:Report ...)` queries against a label
`scripts/migrations/backfill_entity_type_property_2026_03.cypher` actively
removes — so `link_report_to_entity`, `get_reports_for_goal`,
`count_entities_in_report`, … had all silently no-opped since March 2026.
`INCLUDES_ENTITY` and `REPORTS_ON_GOAL` existed nowhere else in the repo.

**Resolution — deleted**, per Mike's ratified decision. The backend was
consumer-less on top of label-less: the intelligence factory stored it as
`self.analytics` and no code called any of its 12 methods; the live report stack
is `ReportRelationshipService` + `REPORT_FOR` against
`NeoLabel.ACTIVITY_REPORT` / `NeoLabel.ENTRY_REPORT`. Removed together:
`adapters/persistence/neo4j/analytics_relationship_backend.py`, the
`AnalyticsRelationshipOperations` protocol and its `core/ports` export, the hub
wiring, and the `analytics` parameter/attribute on
`UserContextIntelligenceFactory` + `UserContextIntelligence` (12 → 11 required
domain services).

---

## 2. Label mismatches — the node exists under a different name

| Flagged | Real label | Site | Impact |
|---|---|---|---|
| `Domain` | `KnowledgeDomain` | `query_builders/faceted_query_builder.py:220,307,323` | Facet counts would come back empty. **Dormant** — `generate_facet_counts_query` has no production caller yet, so this bites the moment the explore catalog wires it up. |
| `Document` | — | `neo4j_adapter.py:223` | Bootstrap constraint for a label nothing writes. |
| `Conversation` | `ConversationSession` / `ConversationMessage` | `neo4j_adapter.py:224` | Same — a stale bootstrap constraint. |

---

## 3. Always-true completion filters — ✅ RESOLVED (tranche 1, 2026-07-20)

Was: filters of the form `WHERE NOT (x)<-[:REL]-(:User {uid: $user_uid})` on
edges (`PRACTICES`, `ATTENDED`, `MADE_CHOICE`, `ADHERES_TO`, `COMPLETED`) no
writer creates — the `NOT` was always true. Same bug class as the 2026-07-10
`PRACTICES` audit.

**Resolution:**

- The four `domain_queries.py` filter sites lived inside the caller-less
  `build_{task,goal,habit,event,principle,choice}_dependencies` builders —
  **deleted**, together with the orphaned helpers only they called
  (`build_knowledge_prerequisites`, `build_unmastered_prerequisite_chain` —
  which also carried an unregistered `MASTERED_BY` default the scanner couldn't
  see — and `build_multi_domain_context`). Mike explicitly superseded the
  2026-07-10 "PLANNED, not delete" bloat ruling for the habit/principle pair:
  the staged user story (dependency chains on detail pages) is already served
  by lateral relationships + BlockingChainView, so the two
  `_PHANTOM_EDGE_CHAIN_BUILDERS` entries left `detect_bloat.py` with them.
- The two **live** `COMPLETED` sites were repointed onto real vocabulary:
  `_lp_intelligence_mixin.get_optimal_path_recommendations` now filters
  `NOT (u)-[:ENROLLED_IN {status: 'completed'}]->(path)` (the state
  `UserBackend.complete_learning_path` actually writes), and the
  `progressive_learning_search` faceted template filters on `MASTERED`.

---

## 4. Bare `REQUIRES` prerequisite chains — ✅ RESOLVED (tranche 1, 2026-07-20)

Was: 13 sites in `domain_queries.py` traversing `[:REQUIRES*1..{depth}]` /
`[:REQUIRES]` — an edge nothing writes (registered names are `REQUIRES_TASK`,
`REQUIRES_HABIT`, `REQUIRES_PREREQUISITE`, `REQUIRES_PREREQUISITE_HABIT`,
`REQUIRES_KNOWLEDGE`, `REQUIRES_STEP`), so every dependency chain came back
empty.

**Resolution:** every site sat inside the same dead dependency builders as §3 —
resolved by the same deletion. `build_simple_prerequisite_chain` (live via
`_semantic_mixin`, callers pass real edge names) was kept.

Only visible once the scanner stopped skipping relationships whose *var-length
bound* was interpolated (`[:REQUIRES*1..{depth}]` — the type name is static, only
the depth is dynamic).

---

## 5. `get_siblings` ignores 5 of the 7 edge types it filters on

`adapters/persistence/neo4j/backends/collab_backends.py:413`:

```cypher
AND type(r) IN ['SUBGOAL', 'SUBHABIT', 'SUBEVENT', 'SUBPRINCIPLE',
                 'SUBCHOICE', 'HAS_STEP', 'ORGANIZES']
```

The registered names are `SUBGOAL_OF`, `SUBHABIT_OF`, … — the bare forms are not
`RelationshipName` members and no writer creates them. Only `HAS_STEP` and
`ORGANIZES` in that list are real, so sibling lookup silently ignores every
activity-hierarchy edge it was written to find.

Found only after the scanner was extended to **predicate position** (`type(r) IN
[...]`), not just pattern position — vocabulary named in a `WHERE` filter fails
exactly as silently as vocabulary named in a `MATCH`.

**Fix is a semantics change** — correcting the list makes `get_siblings` start
returning rows it has never returned — so it is baselined here rather than fixed
in the rule's own PR.

---

## 6. `LEARNING` — ✅ RESOLVED (tranche 2, 2026-07-20)

Was: `tests/unit/test_no_legacy_patterns.py::test_no_legacy_relationship_name_learning`
asserts `RelationshipName.LEARNING` must **not** exist (replaced by
`IN_PROGRESS`), yet `UserBackend.record_knowledge_progress` still wrote it — so
the graph accumulated `(User)-[:LEARNING]->(Ku)` edges every `IN_PROGRESS`
reader was blind to. The one **active-writer** bug in this file.

**Resolution:** inverted from the rest of the file — the *writer* moved, the
name stayed retired.

- `record_knowledge_progress` now merges `IN_PROGRESS` with the property shape
  `UserProgressBackend.record_progress` already writes (`progress`,
  `started_at` via `coalesce` so it stays create-only, `time_invested_minutes`,
  `difficulty_rating`, `last_accessed`).
- Both readers repointed: `user_backend.get_active_learners` matches
  `[r:IN_PROGRESS|MASTERED]` and coalesces the three real recency stamps
  (`last_accessed` / `last_activity_at` / `last_practiced`) instead of the
  now-unwritten `last_updated`; the MEGA-QUERY knowledge block in
  `user_context_queries.py` drops the `LEARNING` alternation arm (its `ELSE 0.5`
  score branch went with it — only `MASTERED` and `IN_PROGRESS` reach it now).
- Historical edges fold over via
  `scripts/migrations/retire_learning_edge_and_expense_label_2026_07.cypher`,
  which merges into an existing `IN_PROGRESS` edge where one exists and converts
  the rest. Idempotent; the dev graph had zero `LEARNING` edges, so it ships for
  prod-shaped graphs.

---

## 7. Writer-less reads — designed, never built

`user_progress_backend.py` is the densest cluster. `HAS_PROGRESS` and
`FOR_KNOWLEDGE` trace to `docs/decisions/ADR-002-user-progress-service-query.md`,
which still refers to a `Curriculum` label that a migration renamed to `Ku` —
suggesting the whole `UserProgress` node model was specified but never
implemented.

| Name | Kind | Note |
|---|---|---|
| `HAS_PROGRESS`, `FOR_KNOWLEDGE` | edge | ADR-002's unbuilt UserProgress model |
| `STRUGGLING_WITH`, `NEEDS_REVIEW` | edge | **Also exist as *property* values** in `core/models/enums/metadata_enums.py:120-121` — likely edge-vs-property confusion rather than a missing writer |
| `HAS_VELOCITY` + `MasteryRecord` | edge + label | Only occurrence repo-wide; empty `OPTIONAL MATCH` inside an otherwise live query |
| `HAS_PREFERENCE` + `LearningPreference` | edge + label | `ps_adaptive_service.py::_load_learning_preferences` therefore always yields `None` |
| `JournalAnalytics` | label | Its 3 sibling analytics nodes each have an upsert; this one lost its writer with ADR-054 |
| `HAS_METADATA` + `ContentMetadata` | edge + label | Read and deleted, never created — harmless `OPTIONAL MATCH` no-ops |

---

## 8. Near-duplicates of registered names

Two names for one concept means reads split across both and each sees half the
graph (or none).

| Unregistered | Registered twin | Note |
|---|---|---|
| `CONTAINS` | `USES_KU` | PathStep→Ku composition; also LearningPath→PathStep in `cross_domain_backend.py:705` |
| `CONTRIBUTES_TO` | `CONTRIBUTES_TO_GOAL` | `graph_models.py:63` writes the short form; `cross_domain_backend.py` reads the long one |
| `INCLUDES_KU` | `CONTAINS_KNOWLEDGE` | only integration-test fixtures write `INCLUDES_KU` |
| `INCLUDES_KNOWLEDGE` | `CONTAINS_KNOWLEDGE` | alternation partner; only the registered arm has a writer, so this arm is permanently empty |
| `CHILD_OF`, `PARENT_OF` | `HAS_CHILD` | `graph_traversal.py:63` alternates all three |
| `FUNDS_HABIT` | `FUNDS_TASK`, `FUNDS_EVENT` | adjacent lines in `_traversal_mixin.py`; siblings registered, this one is not and has no writer |

`HAS_PATH` is the same shape but **was registered** (it has a live writer at
`_lp_step_mixin.py:421`) — it still overlaps `ENROLLED_IN`, which
`UserBackend` treats as canonical. Reconciling the two is open work.

---

## 9. `SemanticRelationshipType` names used as raw edge types

`EXTENDS_PATTERN` and `DEEPENS_UNDERSTANDING` exist only as semantic URIs
(`"learn:extends_pattern"`) in `core/infrastructure/relationships/semantic_relationships.py`
— different strings entirely. `_knowledge_context_mixin.py:80` matches them as
Neo4j edge types, which no writer creates.

---

## 10. Unreachable `.cypher` templates

Suppressed with `// noqa-file: CYP011`. Three files cannot execute:

- `cypher_templates/upserts/bulk_vectors.cypher`
- `cypher_templates/upserts/bulk_life_principles.cypher`
- `cypher_templates/constraints/vectors.cypher`
- (plus `constraints/knowledge_units.cypher`, `constraints/life_principles.cypher`)

`BulkUpsertBackend.ensure_constraints` resolves `{entity_label.lower()}_constraints.cypher`
— no file matches that pattern — and `upsert_batch` only loads a named template
when a caller passes `template_name=`, which no production caller does.

They are the sole source of the labels `Vector`, `State`, `LifePrinciple`,
`JournalEntry` and the edges `MENTIONS_IN`, `GROUNDED_BY`, `FROM`, `TO`. Live
embeddings use `NeoLabel.EMBEDDING_VECTOR` + native vector indexes; this is the
pre-ADR-068 shape.

**One Path Forward says delete them.**

---

## 11. `Expense` — ✅ RESOLVED (tranche 2, 2026-07-20)

Was: `core/models/enums/neo_labels.py` records `EXPENSE` as removed (ADR-052
Phase 5, native expense module demolished), but the ingestion path survived —
`core/services/ingestion/config.py` still registered `entity_label="Expense"`
and `detector.py` mapped `type: expense` onto it, so a vault file created a
live `:Expense` node with no uniqueness constraint (`ensure_constraints`
resolved a filename that does not exist). `scripts/indexes.cypher` indexed it too.

**Resolution — the ingestion config was the leftover, and it is gone.** The
`NonKuDomain.FINANCE` ingestion config, the `expense`/`finance` type mappings,
and the `:Expense` date index are deleted, along with the `:Expense` arm of the
three `ingestion_backend.py` uid-bearing-shape queries (live shapes are now
`:Entity` and `:Group`) and the dead `"expense:"` entry in the uid-prefix →
label map.

`type: expense` no longer falls through to a silent mislabel: `detect_entity_type`
rejects `expense` and `finance` explicitly with an ADR-052 message, checked
*before* the `NonKuDomain.from_string()` fallback that would otherwise resolve
them right back. Finance remains the admin-only Firefly III sidecar, which is
not vault-ingestible. Stray nodes are swept by the tranche-2 migration.

---

## 12. Two parallel conversation stores

Not a mismatch, but surfaced by the same sweep. `user_backend.py:886` writes
`(User)-[:HAS_MESSAGE]->(:ConversationMessage)` on every Askesis turn, while
ADR-078's `conversation_backend.py` writes
`(ConversationSession)-[:HAS_TURN]->(ConversationTurn)`.

Both were registered in this PR because both have live writers, but the older
path sits **outside** the ADR-078 "understanding wall" documented in
`neo_labels.py`. Reconciling them is open work.

---

## 13. New findings from the tranche-1 audit (2026-07-20)

Surfaced while verifying §3/§4; not vocabulary violations themselves, so they
carry no baseline pairs — recorded here so they don't get lost.

- **The `*_with_context` family looks caller-less.** `build_entity_with_context`
  plus the 8 per-domain wrappers (`build_task_with_context` …
  `build_principle_with_context`, ~840 lines of `domain_queries.py`) have no
  production callers — only docstring mentions. The registry-driven
  `context_query_generator.generate_context_query` (January 2026) appears to be
  the live successor. Needs its own caller sweep + One Path Forward ruling; if
  dead, `domain_queries.py` shrinks to the prerequisite-chain + time-based
  query sections.
- **Python-side edge lists escape SKUEL030.** `cross_domain_backend.py:42` maps
  `"practice": ["PRACTICES", "REINFORCES", "APPLIES_KNOWLEDGE"]` — the first
  two are not `RelationshipName` members (`REINFORCES`'s registered twin is
  `REINFORCES_HABIT`; live graph has only the latter). The names live in a
  Python list, not a Cypher string, so the scanner can't see them. Any
  alternation built from that map matches only the `APPLIES_KNOWLEDGE` arm.
  Fold into the §7/T3 pass (same file) or extend the scanner later.
