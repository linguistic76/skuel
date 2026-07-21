# Cypher Vocabulary Findings (SKUEL030 introduction sweep, 2026-07-19)

**Status: the vocabulary backlog is CLOSED as of tranche 5 (2026-07-20).** All of
§1–§8, §10 and §11 are resolved. The only baselined pairs left are §9's two,
deferred by decision to the semantic-relationship-layer roadmap Phase 1, which
also owns the §8 `HAS_PATH`/`ENROLLED_IN` reconciliation. **The natural successor
to this document is that roadmap, not a tranche 6.**

§12 and §13 remain open, but neither is a vocabulary finding: §12 is an
architectural reconciliation and §13 is a bloat/tooling list. The `KnowledgeDomain`
stack tranche 5 exposed (the largest item) is now **✅ RESOLVED — deleted** (2026-07-20,
its own PR), redundant with the Ku's live `nous` / `nous_subtopic` / `sel_category`
classification; see the §10 cascade note.

**These findings are a LOWER BOUND.** SKUEL030 checks whether a name is
*registered*, not whether anything *writes* it — and tranche 5 showed a writer
can exist in the source and still be unreachable. Registered-but-dead vocabulary
passes every rule in this repo cleanly; see the §13 audit-rule entry.

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
- **Tranche order:** T1 = §3+§4 (done) · T2 = §6 LEARNING fix+migration,
  §1 deletion, §11 Expense (done) · T3 = §7 per decision, §2 label mismatches
  (done) · T4 = §5 sibling filter, §8 near-duplicates (done) ·
  T5 = §10 unreachable `.cypher` templates (done). **The vocabulary backlog is
  closed** — the only baselined pairs left are §9's two, deferred to the
  semantic-layer roadmap. The natural successor is that roadmap's Phase 1, not
  another tranche.
- **§10 → DELETE, with the machinery** (T5 ruling): the templates plus
  `upsert_batch`, `ensure_constraints` and the file-backed template loader, which
  existed only to reach them. The `KnowledgeDomain` stack the deletion exposed as
  writer-less was **✅ deleted in its own PR** (2026-07-20) — enum members, service/
  backend/protocol, bootstrap wiring, `KnowledgeDomainView`, phantom `ku.knowledge_domain`
  indexes, and the faceted-query arms (repointed to the live `n.domain` property).
- **`USES_KU|CONTAINS_KNOWLEDGE` two-arm sites → SWEEP to the canonical triple**
  (T5 ruling, resolving the §8 follow-up). `TRAINS_KU` joins all five sites: a
  step's declared objectives count exactly as its content does.
- **§8 `HAS_PATH`/`ENROLLED_IN` → DEFERRED** with §9. Both are registered with
  live writers, so neither is a SKUEL030 finding; reconciling them means
  migrating real enrolment data and belongs to the semantic-layer roadmap.
- **Tranche 2 shipped (2026-07-20):** §6, §1 and §11 resolved as ratified —
  6 baseline pairs closed (38 → 32). One migration covers both graph-side
  changes: `scripts/migrations/retire_learning_edge_and_expense_label_2026_07.cypher`.
- **Tranche 3 shipped (2026-07-20):** §7 and §2 resolved as ratified, plus the
  §13 `"practice"` rider — **17 baseline pairs closed (32 → 15)**. Note the
  count: the plan said 13 (11 for §7), but §7 carried 14 pairs, not 11
  (`ContentMetadata` and `HAS_METADATA` each appear in two files). Migration:
  `drop_stale_bootstrap_constraints_2026_07.cypher` +
  `drop_orphaned_content_metadata_2026_07.cypher`.
  One public endpoint was removed with its dead reader —
  `GET /api/analytics/mood-analysis` — along with two always-zero UI stat tiles
  on the pathways analytics page. Both are called out in §7.
- **Tranche 4 shipped (2026-07-20):** §5 and §8 resolved — **13 baseline pairs
  closed (15 → 2)**, leaving only the two deferred §9 pairs. No migration: none
  of these names has ever had a writer, checked across the full history. Half
  the "registered twins" §8's table proposed turned out to be wrong endpoints —
  and the §5 suggestion was direction-wrong — so read that section's corrected
  table before trusting any triage note here. Two new guard modules:
  `tests/unit/test_hierarchy_vocabulary.py`,
  `tests/unit/test_curriculum_read_vocabulary.py`. Also carried the §13
  `"hierarchical"` rider and a third Python-side edge string in
  `domain_queries.py`.
- **Tranche 5 shipped (2026-07-20):** §10 resolved — the template tree and its
  loader machinery deleted. **No baseline pairs closed: §10 was CYP011-suppressed,
  not baselined**, so the tranche's obligation was owning the noqa removals
  instead. The suppression audit (SKUEL026) confirms it: 104 active / 104 used,
  no orphans. Also shipped the §13 **Python-edge-list scanner** — SKUEL030's
  second position — and swept the five two-arm `USES_KU|CONTAINS_KNOWLEDGE` sites
  to the canonical triple. The new scanner immediately paid for itself: it found
  a **fourth** Python-side edge list nobody had catalogued (§13).

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

## 2. Label mismatches — ✅ RESOLVED (tranche 3, 2026-07-20)

| Flagged | Real label | Resolution |
|---|---|---|
| `Domain` | `KnowledgeDomain` | **Repointed** in `query_builders/faceted_query_builder.py`, then **re-repointed to the live `n.domain` property** when the whole `KnowledgeDomain` stack was deleted (2026-07-20). The facet now counts/filters `Entity.domain`. |
| `Document` | — | **Deleted** — bootstrap constraint AND a `journals_fulltext` index, both in `neo4j_adapter.py`. |
| `Conversation` | `ConversationSession` / `ConversationMessage` | **Deleted** — stale bootstrap constraint. |

**The `Domain` repoint was not a rename.** `KnowledgeDomain`'s only two writers
(`bulk_knowledge_units.cypher`, `bulk_life_principles.cypher`) do
`MERGE (d:KnowledgeDomain {uid: dom})` and set nothing else — so the reads'
`d.name` / `{name: $domain}` named a property that is never written. Swapping
only the label would have traded one silent zero for another; the property moved
to `uid` in the same edit. (Same lesson as tranche 2: joining a live name
inherits its invariants — check the writers, not just the registry.)

> **⚠️ Corrected by tranche 5 — this repoint did not fix the silent zero.** Both
> "writers" named above were **unreachable templates** (§ 10), now deleted. There
> has never been a live writer for `:KnowledgeDomain` or `[:IN_DOMAIN]`, and the
> live graph holds zero of each, so the repointed facet still returns nothing.
> The section checked *what the writers set* but not *whether they could run* —
> the extra step the § 10 cascade note spells out. **The stack was retired
> (deleted) on 2026-07-20; the facet now uses the live `n.domain` property.**

`generate_facet_counts_query` is still production-caller-less (only the
`QueryBuilder` facade delegation at `query_builder.py:249` and a test asserting
that delegation), so it was repointed rather than deleted: it is a facade API
and a registered query template, not abandoned code.

**A third `:Document` site was hiding behind the file-level baseline.**
`neo4j_adapter.py` also created `journals_fulltext` on `(d:Document)` — and
`Neo4jSchemaManager.drop_stale_indexes` already listed that index as stale,
annotated *"label Document no longer exists"*. Bootstrap created on every
startup exactly what the schema manager was written to drop. Removing the pair
came with `scripts/migrations/drop_stale_bootstrap_constraints_2026_07.cypher`
for the two constraints, which linger in `SHOW CONSTRAINTS` on any environment
where bootstrap already ran (absent on dev; migration is a no-op there and was
run against it anyway to prove the syntax).

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

## 5. `get_siblings` ignores 5 of the 7 edge types it filters on — ✅ RESOLVED (tranche 4, 2026-07-20)

Was: `LateralRelationshipBackend.get_siblings` filtered
`type(r) IN ['SUBGOAL', 'SUBHABIT', 'SUBEVENT', 'SUBPRINCIPLE', 'SUBCHOICE',
'HAS_STEP', 'ORGANIZES']`. The bare `SUB*` forms are not `RelationshipName`
members and no writer creates them, so only `HAS_STEP` and `ORGANIZES` matched
and sibling lookup silently ignored every activity-hierarchy edge.

Found only after the scanner was extended to **predicate position** (`type(r) IN
[...]`), not just pattern position — vocabulary named in a `WHERE` filter fails
exactly as silently as vocabulary named in a `MATCH`.

**⚠️ The obvious repoint — `SUBGOAL` → `SUBGOAL_OF` — was direction-wrong, and
this document proposed it.** `_HierarchyMixin.create_hierarchy_relationship` is
the single writer and it creates a **bidirectional pair**: `HAS_SUB*` forward
`(parent)->(child)` and `SUB*_OF` inverse `(child)->(parent)`. The query
traverses `(parent)-[r]->(sibling)`, so the forward leg is the correct one;
substituting the `_OF` names would have matched the graph in the wrong direction
and traded one silent zero for another.

**Resolution.** The filter is now the live forward hierarchy vocabulary — the
six `HAS_SUB*` edges declared by the `HierarchyConfig` on each Activity backend,
plus `HAS_STEP` and `ORGANIZES`. `HAS_SUBTASK` joins the list; Tasks were simply
missing from the original seven.

Two consequences handled in the same commit:

- **The parent anchor was untyped.** `WHERE (parent)-[]->(entity {uid: …})` let
  *any* edge into the entity nominate a parent, so a `BLOCKS` or `OWNS` edge
  could manufacture a false parent whose real children then read as siblings.
  Both the anchor and the sibling edge are constrained to the same set now.
- **`get_cousins` had to move with it.** Its `NOT (parent1)-[]->(cousin)` "not a
  sibling" exclusion is only correct if both methods agree on what a parent edge
  is; it was untyped throughout. It now uses the same list.

Guarded by `tests/unit/test_hierarchy_vocabulary.py`, which also pins the read
vocabulary against every declared `HierarchyConfig` — a new sub-entity domain
that adds a config without adding its forward edge would otherwise be invisible
to every hierarchy read.

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

## 7. Writer-less reads — ✅ RESOLVED (tranche 3, 2026-07-20)

Executed the ratified REPOINT-OR-DELETE. 14 baseline pairs closed.

### Repointed onto live vocabulary

| Was | Now | Site |
|---|---|---|
| `HAS_PROGRESS` → `UserProgress` → `FOR_KNOWLEDGE`, `up.mastery_level >= 0.7` | `(:User)-[:MASTERED]->` | `user_progress_backend.calculate_knowledge_coverage` |
| same, as a prerequisite-completion count | `(:User)-[m:MASTERED]->(prereq)`, `count(m)` | `_lp_intelligence_mixin.get_next_adaptive_step` |
| same, plus "hasn't started yet" | `(:User)-[:IN_PROGRESS\|MASTERED]->` | `_lp_intelligence_mixin.get_recommended_path_steps` |
| `(velocity)<-[:HAS_VELOCITY]-(:MasteryRecord)` | the user's own MASTERED edges | `cross_domain_backend.get_learning_velocity_metrics` |

**Mastery is the edge's existence, not a score.** ADR-002 specified one node
carrying a continuous `mastery_level`; the live model splits that continuum in
two (IN_PROGRESS carries `progress`, MASTERED is terminal). Translating the
`>= 0.7` filter into `m.mastery_score >= 0.7` would have been the obvious
rename and a **new** silent-zero bug: `_AdaptiveMixin.track_mastery_completion`
creates MASTERED edges with no `mastery_score` at all, and its `mastery_level`
is a *string* (`'introduced'` / `'proficient'`), not a float. Existence is the
one invariant all four MASTERED writers share.

Two more consequences of joining that vocabulary:
- "hasn't started yet" needs **both** arms. MASTERED's writers DELETE the
  IN_PROGRESS edge, so the two are mutually exclusive and neither alone means
  "not yet engaged".
- **A mandatory MATCH that finds nothing kills the whole query — twice.** Both
  repointed reads inherited a `MATCH` where an `OPTIONAL MATCH` was needed
  (Codex P2s on #737):
  - `calculate_knowledge_coverage` anchored on
    `MATCH (user)-[:MASTERED]->(learned)`, so a user who has mastered nothing
    got zero rows and was told there are **no unlearned topics** — the exact
    inverse of the truth, for the learner it matters most to. Anchors on the
    `User` now, mastery OPTIONAL; `collect()` skips nulls so `learned_uids` is
    `[]`. Verified on dev: 0 topics before, 364 after.
  - `get_learning_velocity_metrics` required the `LearningVelocity` node, which
    only the `KnowledgeMastered` event handler upserts — so a user whose
    masteries all came through non-event writers reported `no_data` despite
    live MASTERED edges. The node is OPTIONAL now and `velocity` is nullable.
    The service's emptiness test moved onto `total_kus`, so `"no_data"` still
    means "no masteries" rather than degrading into a bogus all-zero
    `"steady"`.
  **This trap hides behind the very bug you are fixing:** the coverage query
  was *already* mandatory-matching before tranche 3 — it just never matched
  anything, so the zero-row collapse was invisible. Repointing a dead read onto
  live vocabulary turns latent structural bugs live. Check every `MATCH` in a
  repointed query for whether it should be `OPTIONAL`.
- **The velocity totals had to move together.** `recent_kus` counts MASTERED
  edges from all four writers, but `total_kus` was still read off
  `velocity.kus_mastered` — a counter only the `KnowledgeMastered` event
  handler increments. A mastery via a non-event writer bumped one and not the
  other, so `previous = total - recent` went NEGATIVE and the trend percentage
  silently collapsed to 0.0 (Codex P2 on #737). Both totals now come from the
  same MASTERED match; the node still supplies `paths_completed`, which has no
  edge form. **General rule: when a repoint changes where one operand of an
  arithmetic comparison comes from, move the other operand too or the
  comparison is no longer well-founded.** Guarded by
  `tests/unit/test_cross_domain_analytics_velocity.py` — note the trend string
  alone does *not* discriminate (the buggy path also reports "accelerating"),
  so the guard asserts the percentage.
- The mastery stamp is
  `coalesce(m.mastered_at, m.achieved_at, m.created_at, m.last_practiced)` —
  the four writers disagree on its name. The three creation stamps are safe to
  coalesce (all ON CREATE for the same event, one writer per edge). The
  `last_practiced` fallback is *required*, not defensive:
  `UserBackend.record_knowledge_mastery` — the writer behind the pathways
  progress route — stamps no creation timestamp at all, so without that arm its
  edges read as undated and vanish from every velocity window. Tranche 3 shipped
  the three-arm version and Codex caught it (P2 on #737). Ordering matters:
  an update stamp coalesced FIRST would hide a real creation stamp, which is
  tranche 2's lesson; coalesced LAST it only fills a genuine gap.

### Deleted (no live signal to repoint onto)

| Name | What went |
|---|---|
| `STRUGGLING_WITH`, `NEEDS_REVIEW` | Backend methods, protocol stubs, service helpers, the two `UserKnowledgeProfile` fields + `to_dict` keys, the `lp_service` analytics keys, and the two **UI stat tiles** that had always rendered `0`. Confirmed edge-vs-property: both are lowercase `RelationshipMetadata` *values* in `metadata_enums.py:120-121`, so there was never an edge to find. |
| `HAS_PREFERENCE` + `LearningPreference` | `_AdaptiveMixin.query_learning_preferences`, its protocol stub, and its sole caller `ps_adaptive_service._load_learning_preferences` (deleted rather than left yielding a constant `None`), plus the already-caller-less `create_learning_preference` factory. |
| `JournalAnalytics` | `get_journal_analytics`, `get_mood_analysis`, the `JournalMoodAnalysis` dataclass, the `mood_analysis` key on `get_combined_dashboard`, and **`GET /api/analytics/mood-analysis`**. Its writer went with ADR-054; the endpoint had been serving hardcoded placeholders (`average_mood=0.65`, `mood_trend="stable"`, fixed themes) to every caller. No UI consumed it. |
| `HAS_METADATA` + `ContentMetadata` | Clause-only: dead `OPTIONAL MATCH` no-ops inside three otherwise-live delete queries (`ingestion_backend`, `neo4j_content_adapter`, and the `cleanup_untracked_vault_entries` script). The write side was removed in July 2026 and the read side was left behind. |

**Removing a dead READ can still orphan real data.** The clauses were dead on
any graph that never had the writer — but the write was only removed in July
2026, so an environment whose content predates that still holds real
`:ContentMetadata` nodes, and those delete queries were the only thing pruning
them leaf-first. Without the clause, `DETACH DELETE content` merely detaches
them (Codex P2 on #737). `scripts/migrations/drop_orphaned_content_metadata_2026_07.cypher`
removes them once — both the still-attached and the already-orphaned — so the
reads can stay gone. Run it before/with deploying tranche 3 on a long-lived
environment.

**The `ContentMetadata` clauses were load-bearing in tests, not in production.**
Two integration tests seeded a fake `:ContentMetadata` node specifically to
prove the delete removed it (`test_ingestion_e2e`, `test_ingestion_chunking`);
both had to be updated in the same commit or they would fail. The unit guard in
`test_content_adapter_chunk_persistence` gained a matching assertion for the
delete query, so neither half can come back without a real writer.

The Python `ContentMetadata` dataclass (`core/models/ps_content/`) is unrelated
and untouched — it is an in-memory chunking model that is never persisted.

---

## 8. Near-duplicates of registered names — ✅ RESOLVED (tranche 4, 2026-07-20)

Two names for one concept means reads split across both and each sees half the
graph (or none). **Half the "registered twins" this table proposed were wrong** —
see the corrected column. Tranche 3's lesson held: name similarity does not
identify a twin, and the triage table is not authoritative.

| Unregistered | Twin this table proposed | What it actually became |
|---|---|---|
| `CONTAINS` (`lifepath_backend.py` ×4) | `USES_KU` | ✅ `USES_KU\|CONTAINS_KNOWLEDGE` — PathStep→Ku |
| `CONTAINS` (`cross_domain_backend.py`) | `USES_KU` | ❌ → `HAS_STEP`; this site is LearningPath→PathStep, not PathStep→Ku |
| `CONTRIBUTES_TO` | `CONTRIBUTES_TO_GOAL` | ✅ as proposed |
| `INCLUDES_KU` | `CONTAINS_KNOWLEDGE` | ❌ → `HAS_STEP`→PathStep→`USES_KU\|CONTAINS_KNOWLEDGE` |
| `INCLUDES_KNOWLEDGE` | `CONTAINS_KNOWLEDGE` | ❌ → same PathStep route |
| `CHILD_OF`, `PARENT_OF` | `HAS_CHILD` | ❌ → the six `HAS_SUB*` edges + `HAS_STEP`/`ORGANIZES` |
| `FUNDS_HABIT` | `FUNDS_TASK`, `FUNDS_EVENT` | ❌ → deleted; the "twins" are dead too |

### `CONTAINS_KNOWLEDGE` is not a LearningPath edge

`INCLUDES_KU` and `INCLUDES_KNOWLEDGE` both sat on a `LearningPath` anchor, and
`CONTAINS_KNOWLEDGE` — the proposed twin — is a **PathStep**→Ku edge. Renaming in
place would have named a relationship pair the graph cannot hold.

**The live graph has no LearningPath→Ku relationship of any type** (verified:
`USES_KU` is PathStep→Ku ×53, `HAS_STEP` is LearningPath→PathStep). A path
reaches a Ku through its PathSteps, or directly via the ingestible
`connections.required_knowledge` → `REQUIRES_KNOWLEDGE` prerequisite edge that
`LP_CONFIG` declares. All three reads (`_lp_progress_mixin` ×2,
`curriculum_backends.get_learning_path_uids`) now cover both routes.

Verified on dev: `get_ku_mastery_progress` for `lp.mindfulness-101` returned
**no rows before, `total_kus=7` after**.

**The PathStep→Ku alternation is a triple, not a pair.** The first cut of this
work used `USES_KU|CONTAINS_KNOWLEDGE` and omitted `TRAINS_KU` (Codex P2 on
#738). `TRAINS_KU` is registered, `PS_CONFIG` maps it to the ingestible
`trains_ku_uids`, and `USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU` is the established
triple — used by `ps_intelligence_backend.py:133` and
`curriculum_backends.py:171/198`, the last two *adjacent to code this tranche
edited*. A PathStep that declares its Kus as objectives rather than content
would have stayed invisible. **When joining an existing alternation, copy the
canonical one from a neighbour rather than composing it from the names you
happen to be fixing.**

> **Follow-up — ✅ RULED AND SWEPT (tranche 5).** Five pre-existing sites still
> used the two-arm pair: `_learning_state_mixin.py:269,271`,
> `exercise_backends.py:488` (+ two docstrings). Tranche 4 left them because the
> omission might have been deliberate — `USES_KU` is a step's *content* while
> `TRAINS_KU` is its *objectives*. **Ruling: they are the same question.** A
> PathStep's declared objectives are part of what it covers, so
> `detect_path_step_completion` must require them mastered and the exercise
> traversal must reach them; all five now use
> `USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU`.
>
> `TRAINS_KU` is live vocabulary, not a second `HAS_CHILD`: `relationship_registry`
> maps it to the ingestible `trains_ku_uids`, which the two-phase relationship
> template writes. Dev holds zero `TRAINS_KU` edges — that is data absence (no
> vault file authors the field yet), not a missing writer. The rewritten queries
> were run against the live graph: same 13 PathSteps / 53 edges as before, so the
> sweep is non-regressive on current data and correct for graphs that have them.

### `HAS_CHILD` is registered — and has no writer either

The `CHILD_OF`/`PARENT_OF` fix could not be "keep the registered arm". `HAS_CHILD`
is a `RelationshipName` member and `TASKS_CONFIG` declares it Task→Task
"subtasks", but **nothing writes it anywhere in the repo, and nothing ever has**
(checked across the full history). Its only apparent writer is a *docstring
example* in `BatchCypherBuilder.build_relationships_list`. The live parent→child
vocabulary is `_HierarchyMixin`'s six `HAS_SUB*` edges, so the hierarchy sites
took the same list as §5.

This is a class SKUEL030 cannot see: the rule checks membership, not liveness, so
a registered-but-writer-less name reads as clean.

`CHILD_OF` was also on the *outgoing* `child` pattern in `graph_traversal.py:65`,
where — being the child→parent leg — it would have returned parents as children.

### `FUNDS_HABIT`: the siblings are dead too

`FUNDS_TASK` and `FUNDS_EVENT` are registered, but neither has a writer; they are
residue of the native expense module ADR-052 demolished (§11). So there was no
live twin to repoint onto. The `FUNDS_*` arms are deleted from
`_TraversalMixin.get_batch_cross_domain_context`, and the `habits` result key
went with them — `FUNDS_HABIT` was the only edge that could ever populate it, and
leaving a permanently empty list would just relocate the silent zero. (That
method is itself production-caller-less — recorded in §13.)

### `CONTRIBUTES_TO`

Repointed to `CONTRIBUTES_TO_GOAL` in the MEGA-QUERY habits block, matching the
canonical `FULFILLS_GOAL|SUPPORTS_GOAL|CONTRIBUTES_TO_GOAL` alternation in
`_TraversalMixin.get_goal_aligned_entities`. Note for future work: `HABITS_CONFIG`
declares only `SUPPORTS_GOAL` as the Habit→Goal edge, so the other two arms are
registered-but-inert *for habits* specifically. Harmless in an alternation, and
narrowing it is a registry question rather than a vocabulary one.

### `HAS_PATH` / `ENROLLED_IN` — explicitly deferred

Unchanged and still open. Both are registered with live writers
(`_lp_step_mixin.py:421` and `UserBackend`), so neither is a SKUEL030 finding and
neither carries a baseline pair. Choosing a canonical enrolment edge means
migrating real data on both sides, which is a decision with a migration attached,
not a read repoint. It belongs with the semantic-layer roadmap alongside §9,
**not** in this backlog.

### Repointing these reads exposed three latent bugs

Same shape as tranche 3's: a dead read hides what is broken inside it.

- **`m.mastery_level * 0.6` would have thrown, not zeroed.**
  `LifePathBackend.calculate_knowledge_alignment` weighted `mastery_level`
  arithmetically, but `_AdaptiveMixin` is its only writer and sets the *strings*
  `'introduced'`/`'proficient'`. Confirmed against the live server: `RETURN
  'introduced' * 0.6` raises a type mismatch. Repointing `CONTAINS` without this
  fix would have converted a silent zero into a hard query failure the moment any
  adaptively-mastered Ku appeared. Now
  `CASE WHEN m IS NULL THEN 0.0 ELSE coalesce(m.mastery_score, 1.0) END` — the
  numeric property the other four writers set, with existence scoring 1.0 for the
  writer that records mastery without a score (tranche 3's "mastery is the edge's
  existence" rule, adapted to a query that genuinely needs a continuum).
- **`m.substance_score` has no writer at all**, so
  `get_knowledge_substance_stats` classified every Ku as theoretical and
  `embodied` was structurally always 0. Uses the same mastery expression as a
  proxy, matching the existing precedent in `PsContextService`
  (`substance_score=mastery  # Use mastery as substance proxy`). A true ADR-046
  Ku-grain substance rollup is roadmap work — no new writer was invented here.
- **`calculate_momentum` collapsed to zero rows on a user whose activity
  stopped.** Both week-window legs were mandatory `MATCH`es, so recent=0 returned
  no rows and the service fell back to its neutral `0.5` default instead of the
  declining branch — reporting "no data" for exactly the signal the metric
  exists to catch. Both are `OPTIONAL MATCH` now.
- `get_ku_mastery_progress` had the same trap on `MATCH (user)-[:MASTERED]->(ku)`:
  a user who has mastered nothing would have read as "this path has no Kus". The
  mastery test is an `EXISTS {}` predicate now, and an empty path yields one row
  of zeros rather than no rows (the service already guards `total_kus == 0`).

### No migration

Unlike tranche 3's `ContentMetadata`, **none of these names has ever had a
writer** — searched across the full history for any `MERGE`/`CREATE` of
`INCLUDES_KU`, `CONTAINS`, `FUNDS_HABIT`, `HAS_CHILD` or `PARENT_OF` in
`adapters/` or `core/`, at every commit. No environment can hold these edges, so
there is nothing to move. ("Dev has zero rows" was not the basis for this — the
writer history was.)

Guarded by `tests/unit/test_hierarchy_vocabulary.py` and
`tests/unit/test_curriculum_read_vocabulary.py`; every assertion was
revert-checked against the pre-fix code (13 of 16 fail on it — the three that
pass are pure registry invariants).

---

## 9. `SemanticRelationshipType` names used as raw edge types — ✅ RESOLVED (semantic-layer roadmap Phase 1, 2026-07-20)

**This section was wrong.** It read: "`_knowledge_context_mixin.py:80` matches
them as Neo4j edge types, which no writer creates." There *is* a writer, and it
is HTTP-reachable:

```
POST /api/path-steps/relationships   (@require_admin, live route)
  -> path_steps_api.py  create_step_relationship(relationship_type=req.type)
  -> ps_service.py      add_semantic_relationship(predicate=...)
  -> ps_semantic_service.py  repo.create_semantic_relationship(triple)
  -> _semantic_mixin.py      build_semantic_merge(triple)
  -> semantic_queries.py     MERGE (s)-[r:{to_neo4j_name()}]->(o)
```

`StepRelationshipCreateRequest.type` is validated against the full 81-member
`SemanticRelationshipType` enum, and the OLD `to_neo4j_name()` emitted the
namespace-stripped uppercase — so an admin POSTing `learn:extends_pattern` wrote a
real `[:EXTENDS_PATTERN]` edge. SKUEL030 was structurally blind to this: it lints
*reads* in `adapters/persistence/`, but the writer's edge name was computed at
runtime from the enum. So §9 was a **registry gap** (a second, unregistered
emitter), not a writer-less read. The read at `:80` was correct by intent — it
read exactly what the semantic writer emits. Live-graph rows: 0 (endpoint
unexercised — data absence, not dead vocabulary; cf. `TRAINS_KU` in §8's lesson).

**Resolution (roadmap Phase 1):** `to_neo4j_name()` now returns a
`RelationshipName` (the coarse edge bucket) via the 81-member
`SEMANTIC_TO_RELATIONSHIP_NAME` map; the precise namespaced predicate is preserved
as the `semantic_type` edge property in `build_semantic_merge`. A semantic type
can no longer emit unregistered vocabulary, by construction. `EXTENDS_PATTERN` /
`DEEPENS_UNDERSTANDING` both collapse to `RELATED_TO`, so the reader at `:80` was
repointed to `RELATED_TO` and both `SKUEL030_BASELINE` pairs are deleted (the
baseline is now empty). Delete/query-by-type gained a `semantic_type` filter so
the collapse does not turn a targeted delete into "delete every `RELATED_TO`
between these two nodes." Guarded by `tests/unit/test_semantic_neo4j_name_drift.py`;
round-tripped against the live graph (write → read → precise delete → survivor).

---

## 10. Unreachable `.cypher` templates — ✅ RESOLVED (tranche 5, 2026-07-20)

Was: five `// noqa-file: CYP011`-suppressed templates that could not execute.
**The unreachability claim held, and was broader than this section stated.**

`BulkUpsertBackend.ensure_constraints` resolved
`{entity_label.lower()}_constraints.cypher`; the files were named
`vectors.cypher` / `knowledge_units.cypher` / `life_principles.cypher`. **No
label has ever produced a matching filename, so the constraint path was a silent
no-op for every entity type from the day it was written** — including for the one
historical caller, which called `ensure_constraints("LifePrinciple")` and would
have needed `lifeprinciple_constraints.cypher`. There is no fallback that
rescues it: the second lookup only strips the subdirectory.

`upsert_batch` had **zero callers repo-wide** — protocol declaration plus
implementation, nothing else. Its one historical caller was
`scripts/ingest_knowledge_vault.py`, deleted in May 2026 (PR #56) as part of the
"never-functional conceptual-trajectory vector code"; these templates were
residue of that same demolition, missed at the time.

### Resolution — deleted, along with the machinery that loaded them

The whole `adapters/persistence/neo4j/cypher_templates/` tree is gone, plus
everything whose only purpose was reaching it: `upsert_batch` (and its
`template_name` parameter on `BulkUpsertOperations`), `ensure_constraints` on
both backend and port, `_get_template`, `_create_default_upsert_template`,
`CypherTemplate.from_file`, and `CypherExecutor.execute_constraints`. The two
live `ensure_constraints` call sites in the ingestion service and batch helper
went with it.

**Constraints did not go with it.** Real uniqueness constraints come from
`Neo4jAdapter` bootstrap and `Neo4jSchemaManager`; the deleted path had never
created one. The unrelated `IngestionTracker`/`IngestionHistory.ensure_constraints`
(backed by live DDL in `ingestion_backend.py`) is untouched.

**`bulk_knowledge_units.cypher` was equally dead and was NOT on this list** —
only because every label and edge in it is *registered*, so CYP011 never fired.
Same zero reachability, invisible to the rule. It was deleted with the rest.

### No migration

The labels `Vector`, `State`, `LifePrinciple`, `JournalEntry` and the edges
`MENTIONS_IN`, `GROUNDED_BY`, `FROM`, `TO` have zero rows on dev — but the basis
for shipping no migration is the writer history, per tranche 4's rule: the only
caller that could ever have run these templates was itself deleted 14 months
before, and the constraint half was unreachable from the first commit. No
environment can hold this data.

### The cascade: `KnowledgeDomain` / `IN_DOMAIN` were registered but writer-less — ✅ RESOLVED (deleted 2026-07-20)

**Outcome:** the whole stack was deleted in its own PR. `nous` / `nous_subtopic` /
`sel_category` already ship a live 3-level Ku taxonomy (120/121 Kus), so a separate
`:KnowledgeDomain` node was redundant, not staged. Deleted: `NeoLabel.KNOWLEDGE_DOMAIN`,
`RelationshipName.IN_DOMAIN`, `KnowledgeDomainService`/`Backend`/protocol, bootstrap
wiring, `KnowledgeDomainView`, the two phantom `ku.knowledge_domain` indexes; the
`faceted_query_builder` domain facet + template were repointed to the live `n.domain`
property. The analysis that led here:

The deleted templates were the **only** writers of `:KnowledgeDomain` and
`[:IN_DOMAIN]` in the entire repo. Both are registered
(`NeoLabel.KNOWLEDGE_DOMAIN`, `RelationshipName.IN_DOMAIN`), so SKUEL030 reads
every one of their call sites as clean. Live graph: **0 nodes, 0 edges.** No
vault file authors a `domains:` field, so there is no authoring surface either.

This means **tranche 3's § 2 `Domain` → `KnowledgeDomain` repoint traded one
silent zero for another.** § 2 called these two templates "KnowledgeDomain's only
two writers" — correct, but they cannot execute, and that section did not check.
The same trap it warned about ("joining a live name inherits its invariants —
check the writers") applies one level up: *check that the writer can run.*

Consequently dead, and deleted in the 2026-07-20 ruling:
`KnowledgeDomainService`, `KnowledgeDomainBackend`, its protocol, the bootstrap
wiring, and `KnowledgeDomainView` — `services.knowledge_domains` was referenced
nowhere but that service's own docstring example.

Guarded by `tests/unit/test_bulk_upsert_template_removal.py`, which pins that no
`.cypher` file returns under `adapters/persistence/` and that the live bulk-write
surface (`upsert_nodes`, `create_relationships`, `upsert_with_relationships`,
`delete_batch`) survived the deletion.

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
- **Python-side edge lists escape SKUEL030.** `cross_domain_backend.py:42`
  mapped `"practice": ["PRACTICES", "REINFORCES", "APPLIES_KNOWLEDGE"]` — the
  first two are not `RelationshipName` members and the live graph has neither.
  The names live in a Python list, not a Cypher string, so the scanner can't
  see them, and any alternation built from that map matched only the
  `APPLIES_KNOWLEDGE` arm. **✅ Fixed in tranche 3** (rider, no baseline pair)
  → `["REINFORCES_KNOWLEDGE", "APPLIES_KNOWLEDGE"]`. Extending the scanner to
  Python edge lists is still open.
  - ⚠️ **This entry originally named the wrong twin.** It said `REINFORCES`'s
    registered twin is `REINFORCES_HABIT`, and tranche 3 shipped that before
    Codex caught it (P2 on #737). Both names are registered and live, but they
    are different edges: `REINFORCES_HABIT` is `(Task|Event)->Habit`, while
    `REINFORCES_KNOWLEDGE` is `Habit->Ku` — the knowledge-practice edge
    `HABITS_CONFIG` maps and `link_habit_to_knowledge` writes. A *knowledge*
    practice lens must pair with `APPLIES_KNOWLEDGE`, matching the canonical
    `APPLIES_KNOWLEDGE|REINFORCES_KNOWLEDGE` alternation used elsewhere.
    **Lesson for T4's §8 near-duplicate work: "the registered twin" is not
    decided by name similarity. Two registered names that look like variants of
    one concept can be genuinely different edges with different endpoints —
    check what each one's writer actually connects before picking.**
- **The same dict has a second bad entry, deliberately left for T4.**
  `"hierarchical": ["HAS_CHILD", "PARENT_OF", "CHILD_OF"]` — `PARENT_OF` and
  `CHILD_OF` are not `RelationshipName` members either. Not fixed in tranche 3
  because §8 owns the `CHILD_OF`/`PARENT_OF`/`HAS_CHILD` reconciliation.
  **✅ Fixed in tranche 4** — takes §8's ruling: all three names were dead
  (`HAS_CHILD` included), so the entry is now the six `HAS_SUB*` edges plus
  `HAS_STEP`/`ORGANIZES`, identical to `get_siblings`.
- **A third Python-side edge string, found by the tranche-4 sweep.**
  `domain_queries.build_task_with_context` specified
  `"rel_types": "PARENT_OF|CHILD_OF"` for its subtasks block. Same blind spot,
  no baseline pair. **✅ Fixed in tranche 4** → `"SUBTASK_OF"`, which is the
  inverse leg `_HierarchyMixin` writes and matches the spec's existing
  `"incoming"` direction. (This sits inside the caller-less `*_with_context`
  family above; fixed rather than left because it costs nothing and the family's
  deletion ruling is still open.) Three such sites in three tranches made the
  scanner extension to Python edge lists the highest-value item on this list.
- **✅ The scanner extension shipped (tranche 5).** SKUEL030 now has two
  scanners: the Cypher one, and `_check_python_edge_lists` for names held in
  Python. It covers both shapes the three sites took — a list/tuple/set literal
  of bare edge names, and a bare `"A|B"` alternation string (the `rel_types`
  spec shape). Same file scope, baseline, suppression and severity: one rule,
  two positions.

  **The corroboration rule keeps false positives at zero.** A group of
  UPPER_SNAKE strings is read as graph vocabulary only when at least one member
  is a registered `RelationshipName` — that sibling is the evidence. Without it,
  every list of UPPER_SNAKE constants in the persistence layer (status codes,
  header names) would be flagged. **The deliberate trade: a group in which every
  name is wrong stays invisible.** That is the safe direction to fail, and all
  four known sites carried a registered sibling.
- **✅ A FOURTH Python-side edge list, found by the new scanner on its first
  run.** `crud_queries.build_hierarchy_query` defaulted to
  `["CONTAINS", "AGGREGATES", "HAS_STEP"]`. Neither `CONTAINS` nor `AGGREGATES`
  is a `RelationshipName` member or exists in the graph, and the sole caller
  (`_prereq_progress_mixin.get_hierarchy`) never passes the parameter — so every
  hierarchy read had only ever matched `HAS_STEP`, exactly §5's bug. Repointed to
  the live forward vocabulary, **copied from the neighbour** (`graph_traversal.py`
  lines 69–72, which walks the same bidirectional parent/child shape) rather than
  composed. Forward-only is load-bearing: the query already emits both
  `(parent)-[:R]->(n)` and `(n)-[:R]->(child)`, so adding the `SUB*_OF` inverses
  would make every child match as its own parent. Guarded in
  `tests/unit/test_hierarchy_vocabulary.py`.
- **`KnowledgeDomain` / `IN_DOMAIN` — the §10 cascade — ✅ RESOLVED (deleted 2026-07-20).**
  Both registered, neither with a reachable writer, zero rows live (§10). The
  product question ("is a Ku domain taxonomy planned?") was answered NO: the Ku
  already carries a live 3-level taxonomy (`nous` L1, `nous_subtopic` L2,
  `sel_category`; 120/121 Kus), and `nous` *is* the outermost layer `KnowledgeDomain`
  claimed to be. So the stack was DELETED, not registered in PLANNED: enum members
  (`NeoLabel.KNOWLEDGE_DOMAIN`, `RelationshipName.IN_DOMAIN`), `KnowledgeDomainService`/
  `Backend`/protocol, bootstrap wiring, `KnowledgeDomainView`, the two phantom
  `ku.knowledge_domain` indexes; the `faceted_query_builder` domain facet + template
  were repointed to the live `n.domain` property.
- **`_TraversalMixin.get_batch_cross_domain_context` is production-caller-less.**
  Found while removing its `FUNDS_*` arms (§8): only the protocol declaration in
  `base_protocols.py:961` and the implementation exist. Bloat finding, not a
  vocabulary one — left standing, wants its own One Path Forward ruling.
- **Registered names can be just as dead as unregistered ones.** `HAS_CHILD`,
  `FUNDS_TASK` and `FUNDS_EVENT` are all `RelationshipName` members with no
  writer anywhere in the repo's history (§8). SKUEL030 checks *membership*, not
  *liveness*, so this whole class is invisible to it and to this document's
  scan — the findings here are a lower bound. A "registered but writer-less"
  audit would be a natural companion rule.
  - **Tranche 5 added three more, and sharpened the definition.**
    `:KnowledgeDomain`, `[:IN_DOMAIN]` (§10) and `HAS_STEP`'s dead list-mates
    show the class is bigger than "no writer in the source": a writer can exist
    in the source and still be **unreachable**. The `bulk_*` templates were
    genuine `MERGE` statements for `KnowledgeDomain` — a grep for writers finds
    them and reports the name live. **So the audit rule needs two questions, not
    one: does a writer exist, and can anything call it?** Tranche 3's §2 asked
    only the first and shipped a repoint onto dead vocabulary because of it.
    A cheap high-signal proxy while the rule is unwritten: for any name whose
    only writers are in `.cypher` files or behind an optional parameter, check
    the live graph for a nonzero count before trusting it.
- **`EnhancedUserContext` is unreachable.** Found while tracing
  `learning_preferences` readers: the class in `user_intelligence.py` has zero
  references repo-wide, which also makes `update_intelligence`,
  `get_optimal_learning_session` and `get_dominant_content_preferences` dead.
  Left standing in tranche 3 (the `learning_preferences` field stays a typed
  `None`) because it is a bloat finding, not a vocabulary one — wants its own
  One Path Forward ruling.

---

## 14. LP-intelligence prerequisite queries were compile-broken (2026-07-21)

Found while writing the LifePath/LP-intelligence integration coverage
(backlog item #1); fixed in the same PR. Three
`_lp_intelligence_mixin` queries — `validate_path_prerequisites`,
`identify_path_blockers`, `get_optimal_path_recommendations` — had
never executed successfully:

- **Out-of-scope variables (Cypher compile error).** The shared
  `_build_prerequisite_subquery` aggregated with `WITH k, collect(...)`,
  dropping `path`/`step`/`r` that the very next clause referenced.
  `EXPLAIN` on the live server: `Variable `path` not defined`. Every
  call returned a database-error Result. Fixed with a `carry` parameter.
- **Phantom property, the §13 audit-rule class.** All three matched
  `(k:Entity {uid: step.knowledge_uid})` — no writer has ever set a
  singular `knowledge_uid` on PathStep nodes (KUs hang off steps as
  edges; `PathStep.knowledge_uids` is reconstructed from them). SKUEL030
  can't see it: it checks edge/label *names*, not node properties.
  Repointed onto the canonical `USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU`
  triple (T5 ruling, §8 follow-up).
- **Inverted prerequisite direction.** The subquery traversed
  `(k)<-[:REQUIRES_KNOWLEDGE*]-(prereq)` — collecting *dependents* of k,
  not prerequisites. Sanctioned direction everywhere else
  (GRAPH_CONTRACT.yaml, `UserProgressBackend.get_prerequisite_map`) is
  `(dependent)-[:REQUIRES_KNOWLEDGE]->(prerequisite)`. Flipped outgoing.
- Riders fixed in passing: the first step was silently dropped from
  validation (bare `MATCH` on earlier steps), and the optimal-path query
  emitted one readiness row per (step, ku) — the same path could appear
  several times in one recommendation list. `path.name` in its
  projection was also phantom (LPs carry `title`); the map projection now
  provides both keys.
- **Codex P2 on the fix itself:** validate/blockers still emitted one row
  per (step, ku), so a multi-KU step — the PathStep norm, every Ps = 2+
  Kus — counted once per KU in `total_steps`/`blocked_steps`. Both now
  UNWIND-aggregate to one row per step; the row field is accordingly
  `knowledge_uids` (list), not `knowledge_uid`.

Behavior is pinned by `tests/integration/test_lp_intelligence_consolidated.py`
against a seeded testcontainer graph.

**Ruling: implemented (2026-07-21).** `analyze_path_knowledge_scope`
(`lp_intelligence_service.py`) previously called four methods that exist
on no class (`get_knowledge_scope_summary`, `get_all_knowledge_uids`,
`knowledge_complexity_score`, `practice_coverage_score` on
`LearningPath`, whose `steps` property is always `()`), so it raised
`AttributeError` on any real path. Mike ruled knowledge scope is CORE LP
identity — implement, never delete. It is now a real graph aggregation:
`_lp_intelligence_mixin` gained `get_all_knowledge_uids` and
`get_knowledge_scope_summary`, which measure the `HAS_STEP` →
`USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU` fan-out plus `REQUIRES_KNOWLEDGE`
prerequisite depth (per-step-aggregated, so a multi-KU step counts once —
the Codex-P2 rule above). The service derives a structural
`complexity_score` (KU breadth × prerequisite depth). The protocol's
aspirational primary/supporting split was **dropped** — PS→KU edges carry
no importance weight, so no such distinction is asserted (a KU importance
scale, Markdown-heading-depth style, is a separate deferred arc).
Pinned by the `TestKnowledgeScope` class in
`tests/integration/test_lp_intelligence_consolidated.py`.

**Follow-up shipped (2026-07-21): `practice_coverage` is now real.** It was
the one remaining phantom in the scope dict. `identify_practice_gaps`
(`lp_intelligence_service.py`) iterates the path's steps
(`LpBackend.get_steps_raw`) and scores each by the canonical PS practice
measure — the fraction of the six activity-domain practice edges
(`BUILDS_HABIT`, `ASSIGNS_TASK`, `SCHEDULES_EVENT`, `SUPPORTS_GOAL`,
`GUIDED_BY_PRINCIPLE`, `INFORMS_CHOICE`) present, counted once in
`PsIntelligenceBackend.fetch_practice_counts`. LP reuses that measure via
the injected `ps_service.intelligence` rather than forking a second
definition (One Path Forward); the shared pure helper
`practice_completeness_from_summary` is the single source of the score.
The path-level mean folds into `analyze_path_knowledge_scope` as
`practice_coverage` (degrades to `null`, never fails the scope, if practice
intelligence is unwired). Pinned by the `TestPracticeGaps` class in the
same file.
