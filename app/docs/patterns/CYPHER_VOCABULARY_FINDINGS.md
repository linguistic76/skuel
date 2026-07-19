# Cypher Vocabulary Findings (SKUEL030 introduction sweep, 2026-07-19)

**Status:** open backlog. Every item here is baselined in
`scripts/lint_skuel.py::SkuelLinter.SKUEL030_BASELINE` (or suppressed with a
`// noqa: CYP011`), so it does not block CI — but none of it is *accepted*.

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

## 1. The `:Report` cluster — an entire wired backend querying a purged label

**Severity: highest.** `AnalyticsRelationshipBackend` is instantiated at
composition time (`services_bootstrap/_intelligence_hub.py`) and runs 13
`MATCH (report:Report ...)` queries. There is no `CREATE`/`MERGE` of `:Report`
anywhere in the repo — and `scripts/migrations/backfill_entity_type_property_2026_03.cypher`
*actively removes* the label:

```cypher
// Fix nodes that may have been ingested with wrong :Report label (stale config).
MATCH (n:Report) WHERE n:Entity
REMOVE n:Report
```

So every method on that backend — `link_report_to_entity`, `get_reports_for_goal`,
`count_entities_in_report`, … — has silently no-opped since March 2026.

The real labels are `NeoLabel.ACTIVITY_REPORT` (`"ActivityReport"`) and
`NeoLabel.ENTRY_REPORT` (`"EntryReport"`).

| Name | Kind | Sites |
|---|---|---|
| `Report` | label | `analytics_relationship_backend.py` ×13 |
| `INCLUDES_ENTITY` | edge | same file ×5 — used nowhere else |
| `REPORTS_ON_GOAL` | edge | same file ×5 — used nowhere else |

**Decision needed:** repoint the backend at `ActivityReport`/`EntryReport` and
register the two edges, or delete the backend if the feature is genuinely gone.
Not a mechanical fix — the two report types have different owners and scopes.

---

## 2. Label mismatches — the node exists under a different name

| Flagged | Real label | Site | Impact |
|---|---|---|---|
| `Domain` | `KnowledgeDomain` | `query_builders/faceted_query_builder.py:220,307,323` | Facet counts would come back empty. **Dormant** — `generate_facet_counts_query` has no production caller yet, so this bites the moment the explore catalog wires it up. |
| `Document` | — | `neo4j_adapter.py:223` | Bootstrap constraint for a label nothing writes. |
| `Conversation` | `ConversationSession` / `ConversationMessage` | `neo4j_adapter.py:224` | Same — a stale bootstrap constraint. |

---

## 3. Always-true completion filters (highest correctness risk after §1)

All of the form `WHERE NOT (x)<-[:REL]-(:User {uid: $user_uid})`. Because no
writer ever creates the edge, the `NOT` is **always true**, so every
dependency-chain query returns *unfiltered* results — the user's completed items
are never excluded.

This is the same bug class the 2026-07-10 `PRACTICES` audit found, replicated
four more times in one file (`adapters/persistence/neo4j/query/cypher/domain_queries.py`).

| Edge | Registered equivalent | Sites |
|---|---|---|
| `PRACTICES` | `APPLIES_KNOWLEDGE` (renamed by a 2026-06 migration) | `domain_queries.py:371,379`, `_adaptive_mixin.py:65`, `cross_domain_backend.py:42` |
| `ATTENDED` | `ATTENDS` / `PRACTICED_AT_EVENT` | `domain_queries.py:432,440` |
| `MADE_CHOICE` | `IMPLEMENTS_CHOICE` / `HAS_CHOICE` | `domain_queries.py:530,538` |
| `ADHERES_TO` | `EMBODIES_PRINCIPLE` / `ALIGNED_WITH_PRINCIPLE` | `domain_queries.py:490` |
| `COMPLETED` | `ENROLLED_IN {status:'completed'}` | `_lp_intelligence_mixin.py:173`, `faceted_query_builder.py:344,348` — `user_progress_backend.py:119` already documents that `:COMPLETED` never had a writer |

---

## 3b. `LEARNING` — a retired edge that still has a live writer

`tests/unit/test_no_legacy_patterns.py::test_no_legacy_relationship_name_learning`
asserts that `RelationshipName.LEARNING` must **not** exist:

> `RelationshipName.LEARNING` was replaced by `IN_PROGRESS` — must not exist.

But `UserBackend.record_learning_progress` (`user_backend.py:562`) still writes it:

```python
merged = await self._merge_user_edge(user_uid, knowledge_uid, "LEARNING", ...)
```

So the graph accumulates `(User)-[:LEARNING]->(Ku)` edges that every reader of
`IN_PROGRESS` is blind to — progress recorded through this method is invisible to
the learning-state queries that matter. `user_backend.py:966` also reads
`[r:LEARNING|MASTERED]`, so the write path and one read path agree with each other
while disagreeing with the rest of the system.

**This one is inverted from the rest of the file:** the name is deliberately
retired, so the fix is to repoint the *writer* to `IN_PROGRESS`, not to register
`LEARNING`. It was registered mid-review and reverted when the legacy test caught it.

---

## 3a. Bare `REQUIRES` — the prerequisite-chain traversal walks a non-existent edge

13 sites in `adapters/persistence/neo4j/query/cypher/domain_queries.py` traverse
`[:REQUIRES*1..{depth}]` or `[:REQUIRES]`. **No writer anywhere creates a bare
`REQUIRES` edge.** The registered names are `REQUIRES_TASK`, `REQUIRES_HABIT`,
`REQUIRES_PREREQUISITE`, `REQUIRES_PREREQUISITE_HABIT`, `REQUIRES_KNOWLEDGE`,
`REQUIRES_STEP`.

So the dependency-chain queries — the *core* of prerequisite/blocking-chain
analysis — traverse nothing and return empty chains. This compounds §3: the same
file's `WHERE NOT` completion filters are always-true, so these queries return
"no prerequisites, nothing completed" regardless of graph state.

Only visible once the scanner stopped skipping relationships whose *var-length
bound* was interpolated (`[:REQUIRES*1..{depth}]` — the type name is static, only
the depth is dynamic).

---

## 3c. `get_siblings` ignores 5 of the 7 edge types it filters on

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

## 4. Writer-less reads — designed, never built

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

## 5. Near-duplicates of registered names

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

## 6. `SemanticRelationshipType` names used as raw edge types

`EXTENDS_PATTERN` and `DEEPENS_UNDERSTANDING` exist only as semantic URIs
(`"learn:extends_pattern"`) in `core/infrastructure/relationships/semantic_relationships.py`
— different strings entirely. `_knowledge_context_mixin.py:80` matches them as
Neo4j edge types, which no writer creates.

---

## 7. Unreachable `.cypher` templates

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

## 8. `Expense` — enum and ingestion contradict each other

`core/models/enums/neo_labels.py` states:

> `EXPENSE` removed (ADR-052 Phase 5) — native expense module demolished

But the ingestion path survived: `core/services/ingestion/config.py:360` still
registers `entity_label="Expense"` and `detector.py:54` still maps
`type: expense` frontmatter to it. **A vault file with `type: expense` creates a
live `:Expense` node today** — one with no uniqueness constraint, since
`ensure_constraints("Expense")` looks for a file that does not exist.

`scripts/indexes.cypher:60` also creates an index on it.

Either the ingestion config is the leftover and should go, or `EXPENSE` belongs
back in `NeoLabel`. The current split — a writable label the source-of-truth enum
declares demolished — is the worst of both.

---

## 9. Two parallel conversation stores

Not a mismatch, but surfaced by the same sweep. `user_backend.py:886` writes
`(User)-[:HAS_MESSAGE]->(:ConversationMessage)` on every Askesis turn, while
ADR-078's `conversation_backend.py` writes
`(ConversationSession)-[:HAS_TURN]->(ConversationTurn)`.

Both were registered in this PR because both have live writers, but the older
path sits **outside** the ADR-078 "understanding wall" documented in
`neo_labels.py`. Reconciling them is open work.
