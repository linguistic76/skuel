---
title: Model-to-Adapter Dynamic Architecture
updated: 2026-05-26
category: patterns
related_skills: []
related_docs:
- /docs/patterns/BACKEND_OPERATIONS_ISP.md
---

# Model-to-Adapter Dynamic Architecture
**Date:** October 3, 2025 (Updated: May 26, 2026)
**Status:** 100% Dynamic - All domains use domain backend subclasses or UniversalNeo4jBackend[T]. Inline Cypher migration complete (Phases 1-8, 11-14). `execute_query()` standardization complete (Phase 9). PsBackend decomposed into 5 mixins (Phase 10). LpBackend decomposed into 3 mixins (Phase 12). 5 new standalone backends for infrastructure services (Phase 13). Final execute_query cleanup across 11 services (Phase 14). Fail-fast dependency philosophy enforced across all services.

## Executive Summary

The architecture is **100% dynamic** for model-to-adapter connections. The introspection-based design with `UniversalNeo4jBackend` and `Neo4jGenericMapper` means changes to domain models automatically ripple to adapters.

---

## July 2026 Update: PrereqCandidateBackend (Discovery Analytics PR 4)

New standalone READ-ONLY **`PrereqCandidateBackend`** (`adapters/persistence/neo4j/prereq_candidate_backend.py`) behind the **`PrereqSuggestionBackendOperations`** port (`core/ports/curriculum_protocols.py`). Feeds the admin prerequisite-edge suggestion queue: `get_kus_with_embeddings` (in-process pairwise cosine — no vector index round-trips), `get_ku_ku_edges` (pair exclusion incl. transitive coverage), `get_ku_titles` (approve-time existence check). Same standalone shape as `SearchEventBackend` below — takes the shared `QueryExecutor` directly, since it reads across Kus rather than serving one entity type's CRUD. This feature never writes to the graph; its only write is an Edge YAML file into the content vault (`EdgeFileWriterPort` / `ContentVaultEdgeWriter` — filesystem adapter, not a Neo4j backend). **See:** `/docs/intelligence/SEMANTIC_ANALYSIS_ROADMAP.md` § 2.

---

## July 2026 Update: SearchEventBackend (Discovery Analytics Phase 1)

New standalone **`SearchEventBackend`** (`adapters/persistence/neo4j/search_event_backend.py`) behind the **`SearchEventBackendOperations`** port (`core/ports/search_protocols.py`). Persists and aggregates `:SearchEvent` behavioral-log nodes (`NeoLabel.SEARCH_EVENT` — a plain infrastructure node like `:ContentChunk`, not an EntityType). Like `InsightBackend`/`CrossDomainBackend`, it takes the shared `QueryExecutor` directly rather than extending `UniversalNeo4jBackend`. Methods: `record_search_event` (written by `SearchEventRecorder`, the `search.executed` subscriber), `get_search_gaps` (zero/low-result content-gap aggregation), `count_search_events` (the 1000+ discovery-analytics trigger). **See:** `/docs/intelligence/DISCOVERY_ANALYTICS_ROADMAP.md`.

---

## May 2026 Update: Connection-Fetch Backend Below the Boundary (ADR-044)

`core/utils/connection_fetcher.py` — which both authored AND executed cross-domain Cypher via an injected `QueryExecutor` — was the last live raw-Cypher leak in `core/`. Its two queries moved verbatim into a new standalone **`ConnectionFetchBackend`** (`adapters/persistence/neo4j/connection_fetch_backend.py`) behind the **`ConnectionFetchOperations`** port (`core/ports/connection_fetch_protocols.py`; methods `fetch_entity_connections(config, uids)` + `fetch_source_pathstep(ps_uid)`). Like `CrossDomainBackend` / `InsightBackend`, it takes the shared `QueryExecutor` directly rather than extending `UniversalNeo4jBackend`.

The source file was renamed `core/utils/connection_configs.py` and is now **pure data** — the `ConnectionConfig` dataclass + the 6 per-domain constants (`TASK_CONNECTION_CONFIG`, …). `config_lookup_label` is typed `NeoLabel`, so the interpolated node-label seam is enum-typed at the source and `validate_label`-checked in the backend before interpolation.

**Wiring:** `create_all_backends()` now takes the shared `query_executor` and builds the backend; it flows through the `Services` container and each Activity Domain's `ui_related_services`, so all 6 UI factories receive the port as `ActivityUIConfig.backend` (was `<svc>.core.backend`). Call sites became `config.backend.fetch_entity_connections(config.connection_config, uids)` and `config.backend.fetch_source_pathstep(uid)`.

**Guard:** `tests/unit/test_core_utils_boundary.py` — AST-based, docstring-immune — bans neo4j driver imports, `execute_query` calls, and *used* raw-Cypher strings in `core/utils/` (`neo4j.exceptions` exempt per ADR-063). Widening SKUEL021's line-scan gate to `core/utils/` with a docstring-aware scanner remains a noted follow-up.

**Commit:** `2a596acc` (PR #75). **See:** `/docs/decisions/ADR-044-neo4j-committed-architectural-choice.md`.

---

## May 2026 Update: Per-Query Server-Side Timeout via TimedDriver (ADR-064)

The 100% dynamic backend pattern leaves ~124 `session.run(...)` sites across 24 files in `adapters/persistence/neo4j/`, each opening its own `self.driver.session()` (mixin pattern under `UniversalNeo4jBackend`). Plus `Neo4jQueryExecutor`, `CypherExecutor` (ingestion `begin_transaction`), and `IngestionWriteBackend.driver.execute_query` — all parallel paths. Until PR #89, none of them set a server-side per-query timeout, so a runaway Cypher only stopped when the client gave up.

The neo4j 5.x driver has no global "default tx timeout" knob (per-query timeout is only via `neo4j.Query(text, timeout=)` for `session.run` and `begin_transaction(timeout=)` for explicit transactions). Rather than edit 124 sites + add a SKUEL023 lint rule, the chokepoint was *created* by wrapping the one shared `AsyncDriver` at the composition root:

- `services_bootstrap/compose.py:117` (immediately after driver validation, before any consumer):
  ```python
  raw_driver = driver
  driver = TimedDriver(raw_driver, default_timeout=config.database.transaction_timeout or None)
  ```
- `TimedDriver.session()` returns a `TimedSession` that auto-wraps `str` queries in `Query(text, timeout=resolved)` on `.run()` (respects a caller-supplied `Query`, no clobber), injects `timeout=resolved` into `.begin_transaction()` when caller passed none (so `CypherExecutor` ingestion `tx.run` calls inherit), and delegates everything else via `__getattr__`.
- `Neo4jSchemaManager` is constructed from `raw_driver` (not the wrapped one) — startup vector / full-text / domain-index DDL on a populated `:Entity` label can exceed 120s legitimately. Migration scripts that build their own `Neo4jConnection` bypass the wrapper for the same reason.

**Override mechanism:** a `contextvars.ContextVar` with a `_UNSET` sentinel (distinguishes "no override" from "explicitly unbounded `None`"); the context managers `neo4j_query_timeout(seconds)` and `unbounded_neo4j_query_timeout()` set it. Default 120s (`DatabaseConfig.transaction_timeout`, env `NEO4J_TRANSACTION_TIMEOUT`, `0`=unbounded). Bulk ingestion (`BulkUpsertBackend.{ensure_constraints, upsert_batch, upsert_with_relationships}`) wraps to 600s. MEGA-QUERY + analytics: no wrap (typical 5–30s).

**Why this is structurally correct:** the "no chokepoint" framing in the old docstrings was a real constraint, and the right answer wasn't to spray the timeout across 124 sites. It was to *create* the chokepoint by wrapping the one driver object — exactly the same move ADR-044 made for raw Cypher (consolidate at the adapter boundary). `CypherExecutor` is annotated `session: AsyncSession` and the backends hold `driver: AsyncDriver`, so the executor receives an `AsyncSession` and there is no in-tree mismatch — the `TimedDriver`/`TimedSession` proxies are duck-typed to satisfy those interfaces and flow through the composition boundary as the neo4j driver type. This passes cleanly even though `arg-type` is now enforced on `adapters/` (no global disable involved). If a proxy were ever passed where the concrete type is statically required, the fix is a small `SessionLike` Protocol, not a redesign. The `LiteralString` pyright friction is centralized in one `_as_timed_query` helper.

**Dead code removal:** `DatabaseConfig.query_timeout` (60.0, unused) deleted — only `transaction_timeout` maps to a real neo4j mechanism. Stale "unwired pending a session chokepoint" notes in `unified_config.py` and `neo4j_connection.py` rewritten to point at `TimedDriver`.

**Commit:** `c865dc61` (PR #89). **See:** [`docs/patterns/NEO4J_QUERY_TIMEOUT.md`](NEO4J_QUERY_TIMEOUT.md) (how-to + override + when-to-wrap), [`/docs/decisions/ADR-064-neo4j-per-query-timeout.md`](../decisions/ADR-064-neo4j-per-query-timeout.md) (driver-wrapper vs explicit-helper, ContextVar choice).

---

## May 2026 Update: AI Vendor SDKs Below the Boundary (W1 / ADR-063)

The hexagonal-boundary principle that put all Neo4j Cypher below `adapters/persistence/neo4j/` (ADR-044, SKUEL021/SKUEL022) was extended to the **external vendor SDKs**. The `openai`, `anthropic`, and `huggingface_hub` clients were moved out of `core/services/` into `adapters/external/`, behind real `core/ports` protocols — the same way the Neo4j driver sits behind `UniversalNeo4jBackend`.

```
adapters/external/
    llm/
        openai_adapter.py        # OpenAIChatAdapter — implements ChatCompletionPort
        anthropic_adapter.py     # AnthropicChatAdapter — implements ChatCompletionPort
        dsl_bridge_factory.py    # create_llm_dsl_bridge() — reads credential, builds OpenAIChatAdapter
    embeddings/
        huggingface_adapter.py   # HuggingFace inference client — implements EmbeddingClientOperations
    deepgram/
        adapter.py               # Deepgram transcription adapter
```

**Ports** (`core/ports/`): `llm_protocols.py` (`ChatCompletionPort.complete(messages, *, system_prompt, model, ...) -> Result[LLMCompletion]`) and `embeddings_protocols.py` (`EmbeddingClientOperations.embed(text) -> Result[list[float]]`, plus the Neo4j-storage `EmbeddingsBackendOperations`).

**Consumers stay in `core/`, SDK-free:** `LLMService`, `UnifiedLLMCaller`, `ProgressReportGenerator`, `ContentEnrichmentService`, `EmbeddingsService`, and `LLMDSLBridgeService` each take an **injected** port — they never construct a client or read a credential. The API key is read at the composition root (`services_bootstrap/`) and the concrete adapter is injected, mirroring the Neo4j backend wiring. `core/services/ai_service.py` was deleted (collapsed into the chat adapters); only `core/utils/exception_types.py` may import the SDK exception classes, guarded by `tests/unit/test_llm_sdk_boundary.py`.

**See:** `/docs/decisions/ADR-063-llm-embeddings-sdk-ports.md`.

---

## February 2026 Update: Backend Mixin Decomposition

`universal_backend.py` grew to 4,214 lines and was decomposed into a shell + 5 focused mixin files, mirroring the `BaseService` mixin decomposition done in January 2026.

**Result:** The same `UniversalNeo4jBackend[T]` API — unchanged for all 25+ callers in `services_bootstrap/`. Only the internal file layout changed.

```
adapters/persistence/neo4j/
    universal_backend.py          # ~527 lines (shell: __init__, helpers)
    _crud_mixin.py                # CrudOperations[T]
    _search_mixin.py              # EntitySearchOperations[T] — find_by_date_range, search, find_by, count, health_check, get_domain_context_raw, execute_query
    _search_raw_mixin.py          # _SearchRawMixin — text_search_raw, relationship_traversal_raw, graph_aware_search_raw, array ops, distinct_values_raw, faceted_search_raw
    _temporal_mixin.py            # _TemporalMixin — user_activity_range_raw, due_soon_raw, overdue_raw
    _prereq_progress_mixin.py     # _PrereqProgressMixin — prerequisite_traversal, hierarchy_query_raw
    _context_query_mixin.py       # _ContextQueryMixin — context_query_raw, basic_context_query_raw
    _relationship_query_mixin.py  # RelationshipQuery + EdgeMetadata + fluent relate() API
    _relationship_ordered_mixin.py# Ordered/hierarchical traversals + lateral-getter convenience wrappers
    _relationship_crud_mixin.py   # RelationshipCrud + validation helpers
    _user_entity_mixin.py         # Generic user-entity ops (5 methods)
    _traversal_mixin.py           # GraphTraversalOperations
    _hierarchy_mixin.py           # HierarchyConfig + _HierarchyMixin (6 hierarchy methods for Activity Domains)
    _backend_helpers.py           # Shared validation: _validate_rel_name(), _ALLOWED_ORDER_BY
    _organizes_mixin.py           # _OrganizesMixin — ORGANIZES relationship management (12 methods)
    _learning_state_mixin.py      # _LearningStateMixin — VIEWED/IN_PROGRESS/MASTERED/BOOKMARKED (13 methods)
    _semantic_mixin.py            # _SemanticMixin — semantic relationships + graph analysis (11 methods)
    _knowledge_context_mixin.py   # _KnowledgeContextMixin — context, discovery, readiness (13 methods)
    _adaptive_mixin.py            # _AdaptiveMixin — practice, search, adaptive mastery (10 methods)
    _lp_step_mixin.py             # _LpStepMixin — LP step management CRUD + path CRUD (14 methods)
    _lp_progress_mixin.py         # _LpProgressMixin — KU mastery progress + search queries (6 methods)
    _lp_intelligence_mixin.py     # _LpIntelligenceMixin — intelligence + adaptive learning (8 methods)
    _user_entry_crud_mixin.py     # _UserEntryCrudMixin — UserEntry CRUD + content-search operations
    _user_entry_lifecycle_mixin.py # _UserEntryLifecycleMixin — UserEntry lifecycle (exercise processing, temporal/thematic relationships)
    _user_entry_assessment_mixin.py # _UserEntryAssessmentMixin — assessment scoring + teacher-review workflow
    _user_entry_report_query_mixin.py # _UserEntryReportQueryMixin — report-relationship cross-joins + learning-loop chain reads
    _user_entry_content_mixin.py  # _UserEntryContentMixin — content enrichment operations
    backends/
        activity_backends.py      # HabitsBackend, GoalsBackend, TasksBackend, EventsBackend, ChoicesBackend, PrinciplesBackend
        curriculum_backends.py    # KuBackend, PsBackend, LpBackend
        exercise_backends.py      # ExerciseBackend, RevisedExerciseBackend, EntryReportBackend
        user_entry_backend.py     # UserEntryBackend (shell over 5 _user_entry_*_mixin files + shared _OrganizesMixin)
        sharing_backend.py        # SharingBackend
        forms_backends.py         # FormTemplateBackend, FormSubmissionBackend
        templates_backends.py     # TaskTemplateBackend, GoalTemplateBackend, HabitTemplateBackend, EventTemplateBackend, ChoiceTemplateBackend, PrincipleTemplateBackend
        collab_backends.py        # GroupBackend, LateralRelationshipBackend, NotificationBackend, ReviewQueueBackend
        misc_backends.py          # ActivityReportBackend, ResourceBackend, InteractionBackend, ReportScheduleBackend, ActivityReportGeneratorBackend
```

**Class declaration:**
```python
class UniversalNeo4jBackend[T: DomainModelProtocol](
    _CrudMixin[T],
    _SearchMixin[T],
    _SearchRawMixin[T],
    _TemporalMixin[T],
    _PrereqProgressMixin[T],
    _ContextQueryMixin[T],
    _RelationshipQueryMixin[T],
    _RelationshipCrudMixin[T],
    _UserEntityMixin[T],
    _TraversalMixin,
):
```

**Security (March 2026):** All base mixin files validate interpolated values before Cypher string building. `_relationship_crud_mixin.py` validates relationship types in `_build_direction_pattern()` — the single choke point for all relationship pattern Cypher. `_traversal_mixin.py` validates pipe-separated relationship patterns in `traverse()` and `find_path()`. `_search_mixin.py` and `_user_entity_mixin.py` validate field names via `validate_field_name()` with safe-default fallback. Validators live in `core/utils/validation_helpers.py` and `crud_queries.py`.

**Cross-mixin dependencies** use `TYPE_CHECKING` stubs (zero runtime cost, MyPy-verified).

**Commit:** `dc77a7a` — 2675/2677 tests pass (2 pre-existing failures).

**See:** `/docs/patterns/BACKEND_OPERATIONS_ISP.md` for full mixin boundary map.
**See:** `/docs/decisions/ADR-044-neo4j-committed-architectural-choice.md` — Neo4j is a committed architectural choice; `UniversalNeo4jBackend` is the hexagonal boundary.

---

## March 2026 Update: Domain Backends Extended to All Domains

**All domains with relationship-specific Cypher now have typed domain backends.**

### What Changed

Four new domain backends added under `adapters/persistence/neo4j/backends/`:

| Backend | Methods moved from |
|---------|-------------------|
| `KuBackend` | `ku_organization_service.py` — 7 ORGANIZES methods |
| `SubmissionsBackend` | `submissions_sharing_service.py` — 8 SHARES_WITH methods |
| `LpBackend` | `lp_progress_service.py` — 2 mastery progress queries |
| `ExerciseBackend` | `exercise_service.py` — 3 curriculum link methods |

**Rule:** Domain-specific relationship Cypher belongs on the domain backend. Cross-domain aggregation stays in services.

**4-layer consistency achieved across all domains:**
```
*Operations protocol → *Backend subclass → *Service facade → sub-services
```

### March 24, 2026 Update: Hierarchy Mixin + Curriculum Relationship CRUD

**`_HierarchyMixin`** added to `_hierarchy_mixin.py` — generic parent-child hierarchy operations shared by all 6 Activity Domain backends. Parameterized via `HierarchyConfig` frozen dataclass (relationship names, node labels, optional entity_type filter).

**6 mixin methods:** `get_children_raw`, `get_parent_raw`, `get_hierarchy_raw`, `create_hierarchy_relationship` (with cycle detection), `remove_hierarchy_relationship`, `would_create_cycle`.

**Activity backends updated (6):** All extend `_HierarchyMixin`. Each sets a `_hierarchy_config` class attribute. `get_stats_for_user()` moved from services to backends. ~790 lines of inline Cypher removed from 5 core services.

| Backend | Hierarchy Config |
|---------|-----------------|
| `TasksBackend` | HAS_SUBTASK / SUBTASK_OF, Entity |
| `GoalsBackend` | HAS_SUBGOAL / SUBGOAL_OF, Entity |
| `HabitsBackend` | HAS_SUBHABIT / SUBHABIT_OF, Habit |
| `EventsBackend` | HAS_SUBEVENT / SUBEVENT_OF, Entity |
| `PrinciplesBackend` | HAS_SUBPRINCIPLE / SUBPRINCIPLE_OF, Principle |
| `ChoicesBackend` | HAS_SUBCHOICE / SUBCHOICE_OF, Entity (node_filter: entity_type='choice') |

**Curriculum backends extended:**

| Backend | Methods Added |
|---------|-------------|
| `PsBackend` | 4 CONTAINS_KNOWLEDGE methods + 5 CRUD methods: `create_step_node`, `get_step_with_knowledge`, `update_step_fields`, `delete_step_node`, `list_steps_raw` |
| `LpBackend` | 5 HAS_STEP methods: `get_steps_raw`, `get_parent_path_raw`, `add_step_to_path`, `remove_step_from_path`, `reorder_steps` |
| `GoalsBackend` | 4 progress-helper methods: `find_linked_goals_for_task`, `count_linked_tasks`, `find_linked_goals_for_habit`, `count_linked_habits_avg_streak` |
| `KuBackend` | 2 substance methods: `batch_increment_substance`, `increment_substance` |

**Protocols updated:** `EventsOperations`, `ChoicesOperations`, `PrinciplesOperations` now extend `HierarchyOperations`. `PsOperations`, `LpOperations`, `GoalsOperations` gained method signatures for the new backend methods.

**March 24, 2026 Update: Remaining 12 Services Migrated**

Phase 5 completed the backend delegation refactor — ~46 inline Cypher queries from 12 service files moved to domain backends. Two new backends created: `GroupBackend` (6 OWNS/MEMBER_OF methods) and `NotificationBackend` (5 HAS_NOTIFICATION methods). All existing backends extended: `PsBackend` (then named `LessonBackend`, +18 user progress/graph context methods), `KuBackend` (+6 usage/search methods), `SubmissionsBackend` (+14 exercise processing/relationship/assessment methods), `ExerciseBackend` (+6 methods), `RevisedExerciseBackend` (+4 methods), `HabitsBackend` (+4 badge methods), `FormTemplateBackend` (+1), `FormSubmissionBackend` (+1).

**File layout:**
```
adapters/persistence/neo4j/
    _hierarchy_mixin.py           # HierarchyConfig + _HierarchyMixin (6 generic methods)
    backends/                     # 9 cluster files holding the 27 domain subclasses (see "April 2026 Update" below)
```

### March 25, 2026 Update: Report + Teacher Review Services Migrated (Phase 4)

Two more services migrated to domain backends — zero inline Cypher remains in either service.

**New backend:** `ActivityReportBackend` (6 methods):
| Method | What It Does |
|--------|-------------|
| `get_history` | Query ActivityReports by subject_uid |
| `annotate` | Save annotation/revision on owned ActivityReport |
| `get_annotation` | Get annotation state for owned ActivityReport |
| `get_admin_snapshots` | Privacy audit: admin-written reports received by user |
| `get_shares_granted` | Privacy audit: SHARES_WITH access to user's entities |
| `get_report_schedule` | Privacy audit: active report schedule |

**Existing backends extended:**
| Backend | Methods Added |
|---------|-------------|
| `SubmissionsBackend` | +9 teacher review methods: `get_review_queue`, `create_report_node`, `approve_and_get_linked_kus`, `get_submissions_for_exercise_review`, `get_students_summary`, `get_student_submissions_for_teacher`, `get_submission_detail_for_teacher`, `get_dashboard_stats`, `verify_teacher_has_group_access`. Typed report reads live on `EntryReportBackend.list_for_submission` (2026-04) — the prior dict-returning `get_report_history` was deleted when EntryReport was promoted to a first-class typed read path |
| `ExerciseBackend` | +1: `get_exercises_with_submission_counts` |
| `GroupBackend` | +2: `get_teacher_groups_with_stats`, `get_group_detail` |

**Fail-fast cleanup:**
- `ActivityReportService`: `executor` dependency removed, `event_bus` made required
- `TeacherReviewService`: `executor` replaced with 3 required typed backends (`SubmissionsBackend`, `ExerciseBackend`, `GroupBackend`), `event_bus` made required

### March 25, 2026 Update: Lateral Relationship Service Migrated (Phase 5)

14 inline Cypher queries migrated from `LateralRelationshipService` to a new `LateralRelationshipBackend`.

**New backend:** `LateralRelationshipBackend` (14 methods):

| Category | Methods |
|----------|---------|
| **CRUD (4)** | `create_relationship`, `delete_relationship`, `create_inverse`, `delete_inverse` |
| **Query (6)** | `get_relationships`, `get_siblings`, `get_cousins`, `get_blocking_chain`, `get_alternatives_comparison`, `get_relationship_graph` |
| **Validation (4)** | `check_entities_exist`, `check_same_parent`, `check_same_depth`, `check_no_cycles` |

**Architecture:** Standalone backend with `executor` (like `NotificationBackend`), not `UniversalNeo4jBackend[T]` — operates on relationships across entity types, not CRUD on a single type.

**Protocol:** `LateralRelationshipBackendOperations` in `service_protocols.py`.

**Fail-fast cleanup:** `executor: QueryExecutor` replaced with `backend: LateralRelationshipBackendOperations`.

### March 26, 2026 Update: ContextRetriever Cypher Migration + Dead Code Removal (Phase 11)

Migrated 4 inline Cypher queries from `ContextRetriever` (which bypassed the backend layer via `graph_intel.execute_query()`) to domain backends. Deleted `CrossDomainQueries` (762 lines, zero callers — dead code).

**New backend methods:**
- `KuBackend.get_unmastered_prerequisites()` — prerequisite chains (depth 1..3) filtered by mastery
- `KuBackend.count_dependents()` — impact score for gap analysis
- `_KnowledgeContextMixin.get_cited_resources()` — CITES_RESOURCE traversal for PS bundles
- `_LearningStateMixin.get_user_learning_context()` — single-query learning state (mastered, learning, blocked, paths, tasks, goals)

**ContextRetriever** now delegates to `ku_backend` and `ps_backend` (injected via `AskesisDeps`). `_build_user_learning_context_query()` deleted. `@requires_graph_intelligence` decorator removed from methods that no longer use `graph_intel`.

**Remaining inline Cypher** in `_life_path_mixin.py` (7 queries) and `planning_mixin.py` (2 queries) is correctly placed — executes through `self.backend.execute_query()` and is entity-agnostic/config-driven.

### April 11, 2026 Update: LP + PS Search Service Cypher Migration + LpBackend Mixin Decomposition + KuOperations Protocol (Phase 12)

Three changes completing curriculum domain infrastructure parity:

**1. PS + LP Search Service Cypher Migration (8 queries → 0 `execute_query` calls in services):**

| Service File | Queries Migrated | Backend |
|---|---|---|
| `ps_search_service.py` | 4 | PsBackend: `get_steps_for_learning_path`, `get_standalone_steps`, `get_steps_using_ku`, `get_prioritized_steps` |
| `lp_search_service.py` | 3 | LpBackend: `get_paths_aligned_with_goal`, `get_paths_by_knowledge`, `get_user_paths_prioritized` |
| `lp_progress_service.py` | 1 | LpBackend: `get_paths_containing_step` |

**Service type narrowing:** `PsSearchService` now typed as `BaseService["PsOperations", PathStep]` (was `BackendOperations[PathStep]`). `LpSearchService` → `LpOperations`. This gives search services access to domain-specific backend methods via the protocol.

**2. LpBackend Mixin Decomposition (28 methods → 3 focused mixins):**

| Mixin | Methods | Responsibility |
|-------|---------|----------------|
| `_LpStepMixin` | 14 | Step management CRUD + path CRUD |
| `_LpProgressMixin` | 6 | KU mastery progress + search queries |
| `_LpIntelligenceMixin` | 8 | Intelligence + adaptive learning |

Follows the same pattern as PsBackend's 5-mixin decomposition. LpBackend is now ~20 lines inheriting from all 3 mixins.

**3. KuOperations Protocol Created:**

`KuOperations(BackendOperations["Ku"], Protocol)` in `curriculum_protocols.py` — 23 method signatures organized into 6 sections (reverse traversal, namespace/alias search, substance metrics, relationship queries, prerequisite/dependency queries, learning state). Exported via `core/ports/__init__.py`.

**Protocols updated:** `PsOperations` gained 4 search method signatures. `LpOperations` gained 4 search method signatures (including `get_paths_containing_step`).

### April 11, 2026 Update: 5 Standalone Infrastructure Backends + Cross-Domain Backend Expansion (Phase 13)

Created 5 new standalone typed backends for infrastructure and cross-domain services that previously used raw `QueryExecutor`/`execute_query`. Also expanded `CrossDomainBackend` with 9 admin stats methods.

**New standalone backends:**

| Backend | File | Methods | Migrated From |
|---------|------|---------|---------------|
| `VectorSearchBackend` | `vector_search_backend.py` | 5 | `Neo4jVectorSearchService` (was `self.executor`) |
| `IngestionBackend` | `ingestion_backend.py` | 15 | `IngestionHistoryService`, `IngestionTracker` (+3 deletion-propagation methods, 2026-06-12) |
| `JupyterSyncBackend` | `jupyter_sync_backend.py` | 9 | `JupyterNeo4jSyncService` |
| `EmbeddingsBackend` | `embeddings_backend.py` | 3 | `EmbeddingsService` (the worker stores through it) |
| `KnowledgeDomainBackend` | `knowledge_domain_backend.py` | 3 | `KnowledgeDomainService` |

**CrossDomainBackend expansion (+9 methods):** `get_entity_system_metrics`, `get_all_users_progress`, `get_user_ku_detail`, `get_user_submissions_detail`, `get_user_activity_detail`, `get_learning_metrics`, `get_user_overview_stats`, `get_user_learning_goal_progress`, `get_system_health`. Migrated from `AdminStatsService` and `UserStatsAggregator`.

**Protocols created:** `VectorSearchBackendOperations`, `IngestionBackendOperations`, `JupyterSyncBackendOperations`, `EmbeddingsBackendOperations`, `KnowledgeDomainBackendOperations`, `CrossDomainBackendOperations` (expanded).

**Total:** 45 `execute_query` calls migrated from 10 services into typed backend methods. All services now call `self.backend.method_name()` instead of raw Cypher.

### April 11, 2026 Update: Final execute_query Cleanup (Phase 14)

15 remaining `execute_query` calls migrated from 11 service files into typed backend methods. This completes the execute_query migration — no domain or intelligence service contains inline Cypher.

**New backend methods:**

| Backend | Method | Migrated From |
|---------|--------|---------------|
| `EventsBackend` | `count_recent_reschedules` | `EventsIntelligenceService` |
| `EventsBackend` | `count_events_in_date_range` | `EventsIntelligenceService` |
| `TasksBackend` | `get_transitive_dependencies` | `TasksIntelligenceService` |
| `PrinciplesBackend` | `get_choice_influence_stats` | `PrinciplesIntelligenceService` |
| `SubmissionsBackend` | `get_submissions_for_path_step` | `SubmissionsSearchService` |
| `SubmissionsBackend` | `create_goal_support_relationships` | `SubmissionsRelationshipService` |
| `_LpStepMixin` | `get_next_step_sequence` | `PsSearchService` |
| `_TraversalMixin` | `get_citation_export` | `KuCoreService` |
| `_TraversalMixin` | `get_goal_aligned_entities` | `GoalsIntelligenceService` |
| `_TraversalMixin` | `find_uids_by_semantic_filter` | `GraphIntelligenceService` |
| `_TraversalMixin` | `get_batch_cross_domain_context` | `GraphIntelligenceService` |
| `CrossDomainBackend` | `get_journal_entries_in_range` | `CrossDomainQueryService` |

**Remaining exempted `execute_query` usage (infrastructure, not domain):**
- `schema_service.py` — 9 DDL/schema introspection queries (`CALL db.labels()`, `SHOW INDEXES`)
- `user_context_queries.py` — 3 MEGA-QUERY fragments (full user state snapshot)
- Ingestion pipeline — 5 raw driver calls (bulk cross-domain writes)
- `semantic_relationship_linker.py` — 1 call through backend (tolerated)

### April 12, 2026 Update: domain_backends.py Split into backends/ Cluster Package (Phase 15)

`domain_backends.py` (4892 lines, 27 classes) was split into 9 cluster files under `adapters/persistence/neo4j/backends/`, then the old module was deleted entirely. All call sites import directly from the cluster file — e.g. `from adapters.persistence.neo4j.backends.activity_backends import TasksBackend`.

**New cluster files** (grouped by concern, not by source line order):

| File | Classes |
|---|---|
| `backends/activity_backends.py` | HabitsBackend, GoalsBackend, TasksBackend, EventsBackend, ChoicesBackend, PrinciplesBackend |
| `backends/curriculum_backends.py` | KuBackend, PsBackend, LpBackend |
| `backends/exercise_backends.py` | ExerciseBackend, RevisedExerciseBackend, EntryReportBackend |
| `backends/submissions_backend.py` | SubmissionsBackend (shell over 5 `_submission_*_mixin` files) |
| `backends/sharing_backend.py` | SharingBackend |
| `backends/forms_backends.py` | FormTemplateBackend, FormSubmissionBackend |
| `backends/journal_backends.py` | JournalInputBackend, JournalOutputBackend |
| `backends/collab_backends.py` | GroupBackend, LateralRelationshipBackend, NotificationBackend, ReviewQueueBackend |
| `backends/misc_backends.py` | ActivityReportBackend, ResourceBackend, InteractionBackend, ReportScheduleBackend, ActivityReportGeneratorBackend |

`backends/__init__.py` re-exports every class. The old `domain_backends.py` shim was deleted — all call sites import directly from the cluster file.

**mypy override:** the existing `disable_error_code = ["misc"]` rule (for intentional MRO overrides from composed mixins) now applies to each of the 9 cluster modules.

**Behavioral change:** none. MRO verified for `SubmissionsBackend`, `PsBackend`, `LpBackend`. `./dev quality` passes; targeted backend tests (53) green; 3891 non-e2e tests pass with the only failures being pre-existing on HEAD.

**Commit:** `c4652ced`.

### March 26, 2026 Update: PsBackend Mixin Decomposition (Phase 10)

`PsBackend` (then named `LessonBackend` — 1,248 lines, 54 methods) was 2x the next-largest backend. Decomposed into 5 focused mixins following the `_HierarchyMixin` pattern. The backend shell is now ~20 lines inheriting from all 5 mixins — pure structural refactor, no behavioral changes.

| Mixin | Methods | Responsibility |
|-------|---------|----------------|
| `_OrganizesMixin` | 12 | ORGANIZES relationship management |
| `_LearningStateMixin` | 14 | User progress: VIEWED, IN_PROGRESS, MASTERED, BOOKMARKED, MARKED_AS_READ + learning context |
| `_SemanticMixin` | 11 | Semantic relationships + graph analysis (hub scores, prereq chains) |
| `_KnowledgeContextMixin` | 14 | Context, discovery, readiness (USES_KU, connected activities, learning gaps) + cited resources |
| `_AdaptiveMixin` | 10 | Practice, keyword/vector search, adaptive mastery tracking |

Shared validation helpers (`_validate_rel_name`, `_ALLOWED_ORDER_BY`) extracted to `_backend_helpers.py`.

**Reuse potential:** `_LearningStateMixin` methods are entity-agnostic internally — `ExerciseBackend` or `KuBackend` can add it to their bases when learning state tracking is needed.

### March 26, 2026 Update: execute_query() Standardization (Phase 9)

Standardized all 33 domain backend methods across 8 backends to use `self.execute_query()` instead of direct `self.driver.session()` + `session.run()`. Also fixed 3 `HabitsBackend` methods that returned raw `bool` instead of `Result[bool]`.

**Backends converted:** GoalsBackend (4), TasksBackend (4), EventsBackend (3), PsBackend (then named LessonBackend, 10), KuBackend (1), SubmissionsBackend (5), JournalInputBackend (3), JournalOutputBackend (2).

**Result:** Zero `self.driver.session()` calls remain in the domain backends. All queries route through `execute_query()` which provides centralized session management, the driver-closed guard, and consistent `Result[list[dict]]` returns. Net reduction of 156 lines of try/except boilerplate.

**Rule enforced:** Domain backends call `self.execute_query()`. Services call named backend methods. No code bypasses the centralized query path.

### March 26, 2026 Update: Backend Hardening + Service Cypher Migration (Phase 8)

Hardened 3 backend methods against Cypher injection and migrated 17 inline Cypher queries from 5 service files to domain backends.

**Security hardening (two layers):**

*Backend mixins (`_backend_helpers.py`):*
- `_validate_rel_name()` — rejects relationship names with non-`[A-Z0-9_]` characters
- `_ALLOWED_ORDER_BY` — whitelist for `ORDER BY` field names (prevents injection via order_by parameter)
- `find_connected_activities()` — `node_label` typed `NeoLabel`, `rel_types` typed `list[RelationshipName | str]`, `limit` parameterized as `$limit`
- `delete_semantic_relationship()` / `query_relationships_by_type()` — `rel_name` validated, `direction` typed `Literal["outgoing", "incoming", "both"]`

*Query builders (`_helpers.py` — shared by all 5 modules):*
- `validate_label()` — checks against `NeoLabel` enum allowlist before label interpolation
- `validate_identifier()` — regex `^[a-zA-Z_][a-zA-Z0-9_]*$` before field/relationship/property interpolation
- Applied to 17 functions across `crud_queries.py`, `domain_queries.py`, `relationship_queries.py`, `semantic_queries.py`, `intelligence_queries.py`

**Service → Backend migrations:**

| Service File | Queries | Backend |
|---|---|---|
| `choices/_behavioral_signals_mixin.py` | 0 | Cross-domain reads migrated to `CrossDomainQueryService`; 3 dead methods deleted |
| `report/report_relationship_service.py` | 5 | SubmissionsBackend (+5 methods: `get_pending_submissions_raw`, `get_unsubmitted_exercises_raw`, `get_report_summary_raw`, `get_learning_loop_chain_raw`, `get_submission_chain_raw`) |
| `ku/ku_relationships.py` | 6 | KuBackend (+7 methods: `get_related_knowledge_uids`, `get_broader_concept_uids`, `get_narrower_concept_uids`, `get_learning_path_uids`, `get_applying_task_uids`, `get_practicing_event_uids`, `get_reinforcing_habit_uids`) |
| `submissions/submissions_relationship_service.py` | 1 | SubmissionsBackend (+1 method: `get_supported_goal_uids`) |

**Deprecated pattern eliminated:** `ku_relationships.py` no longer uses `graph_service.repo.execute_query()` — uses named `KuBackend` methods via `_get_uids_from_backend()` helper.

**Protocol updated:** `PsOperations` (then named `LessonOperations`) in `curriculum_protocols.py` — `find_connected_activities()` signature tightened (`NeoLabel`, `RelationshipName`, `Literal`).

### March 25, 2026 Update: PathStep Domain Cypher Migration (Phase 7)

The largest single migration — 35 inline Cypher queries from 8 PathStep service files (then named `lesson/`) moved to 31 named backend methods on what is now `PsBackend`. The `neo4j_adapter` dependency was removed from 5 services entirely.

**PsBackend extended (+31 methods), later decomposed into 5 mixins (Phase 10):**

| Category | Methods | Mixin (Phase 10) |
|----------|---------|-------------------|
| **Practice (2)** | `find_kus_practiced_by_event`, `increment_practice_count` | `_AdaptiveMixin` |
| **Search (2)** | `find_similar_by_keywords`, `search_by_keywords` | `_AdaptiveMixin` |

> Chunk vector search (`semantic_search_chunks`) was lifted out of `_AdaptiveMixin`
> into `VectorSearchBackend` so chunk retrieval lives next to the rest of the
> vector-index operations. See `adapters/persistence/neo4j/vector_search_backend.py`
> and `core/ports/vector_search_protocols.py`.
| **Application Discovery (3)** | `find_connected_activities`, `find_path_steps_containing_ku`, `find_learning_paths_teaching_ku` | `_KnowledgeContextMixin` |
| **Context (3)** | `find_ready_to_learn`, `find_learning_gaps`, `find_reinforcement_candidates` | `_KnowledgeContextMixin` |
| **Semantic (6)** | `create_semantic_relationship`, `query_semantic_neighborhood`, `delete_semantic_relationship`, `query_relationships_by_type`, `discover_semantic_bridges`, `infer_transitive_relationships` | `_SemanticMixin` |
| **Graph (8)** | `link_prerequisite`, `link_parent_child`, `query_user_mastery_for_prereqs`, `find_learning_recommendations`, `compute_hub_scores`, `query_foundational_knowledge`, `find_prerequisite_chain`, `find_next_steps` | `_SemanticMixin` + `_KnowledgeContextMixin` |
| **Adaptive (5)** | `track_mastery_completion`, `query_user_masteries`, `query_active_learning_paths`, `query_completed_learning_paths`, `query_learning_preferences` | `_AdaptiveMixin` |

**Protocol:** 31 new methods added to the curriculum protocol (then named `LessonOperations`, now `PsOperations`) in `curriculum_protocols.py`.

**neo4j_adapter eliminated from (service names at time of Phase 7, prior to the Lesson → PathStep merge):**
- `LessonGraphService` — `__init__(repo, graph_intel)` (was `repo, neo4j_adapter, graph_intel`)
- `LessonSemanticService` — `__init__(repo, intelligence)` (was `repo, neo4j_adapter, intelligence`)
- `LessonApplicationDiscoveryService` — `__init__(repo)` (was `repo, neo4j_adapter`)
- `LessonContextService` — `__init__(repo)` (was `repo, neo4j_adapter`)
- `LessonAdaptiveService` — `__init__(backend, user_service)` (was `ku_backend, user_service`)

**Factory:** `create_lesson_sub_services()` (now `create_ps_sub_services()`) no longer accepts `neo4j_adapter` parameter.

**Bootstrap:** `_create_learning_services()` no longer accepts or passes `neo4j_adapter`.

### March 25, 2026 Update: Broader Fail-Fast Sweep (Phase 6)

Eliminated optional-dep fallback patterns across 7 files, enforcing One Path Forward:

| File | Pattern Removed | Fix |
|------|----------------|-----|
| `ku/ku_relationships.py` | Caught errors, returned `Result.ok([])` | Removed try/except, errors propagate via `Result.fail()` |
| `ps/ps_search_service.py` (then `lesson/lesson_search_service.py`) | Semantic search fail → silent keyword fallback | Error propagates when FULL tier; keyword used only when CORE tier |
| `visualization_service.py` | Optional deps + demo/mock data | All 4 service deps required, demo data deleted |
| `calendar_service.py` | Optional deps + `if self.X_service:` guards + demo data | All 3 deps required, null guards + demo methods deleted |
| `insight_generation_service.py` | `if not self.tasks_service: return []` | `RuntimeError` if tasks_service missing |
| `llm_service.py` | `ImportError → mock provider` fallback | `ImportError` propagates — if provider selected, library must be installed |
| `instruction_resolver.py` | Unknown mode → silent default | `Errors.validation()` on unknown enrichment mode |

Also removed CalendarService exception from CLAUDE.md's fail-fast dependency philosophy.

---

## January 2026 Update: Wrapper Classes Removed

**Deleted ~2,000 lines** of wrapper code from curriculum domains (PS, LP, MOC).

### What Changed

| Domain Group | Before | After |
|--------------|--------|-------|
| **Activity (6)** | Per-domain wrapper classes | UniversalNeo4jBackend[T] ✅ |
| **Curriculum (3)** | Wrapper backends | UniversalNeo4jBackend[T] ✅ |
| **Content/Org (3)** | Mixed | UniversalNeo4jBackend[T] ✅ |
| **Finance (1)** | UniversalNeo4jBackend[T] | UniversalNeo4jBackend[T] ✅ |

**Note:** Activity Domains later gained typed domain backend subclasses (February 2026) and Curriculum/Submissions followed (March 2026). The distinction is: old "wrappers" duplicated generic CRUD; new domain backends ADD domain-specific methods on top of the universal base.

### New Helper Methods

`_build_direction_pattern()` added to consolidate ~30 lines of duplicated Cypher pattern building:

```python
def _build_direction_pattern(
    self,
    relationship_type: str,
    direction: Direction,
    rel_var: str | None = None,
    target_label: str | None = None,
) -> Result[str]:
    """Build Cypher pattern for directional relationship traversal."""
```

### Query Execution Patterns

| Pattern | When to Use | Example |
|---------|-------------|---------|
| `self.backend.method()` | **Services** — all domain queries | `await self.backend.find_by(status="active")` |
| `self.execute_query(query, params)` | **Domain backends only** — domain-specific Cypher | `await self.execute_query(query, {"uid": uid})` |

**Rule (Phase 9):** Domain backends call `self.execute_query()`. Services call named backend methods. Zero `self.driver.session()` calls in any `backends/` file.

**Nuance:** This rule covers domain CRUD and domain-specific queries. Most cross-domain aggregation services (e.g., `UserProgressService`, `AdminStatsService`) now use typed standalone backends (Phase 13). Two exceptions remain using `QueryExecutor` directly: `user_context_queries.py` (MEGA-QUERY) and `CrossDomainQueryService` (targeted cross-domain reads). Infrastructure services like `Neo4jSchemaService` still use `execute_query` legitimately. Domain sub-services also use `self.backend.execute_query()` for complex one-off queries. See [query_architecture.md — `execute_query` in Services](query_architecture.md#execute_query-in-services--permitted-tiers) for the full tier breakdown.

### Fail-Fast Alignment

Driver guards (`if not self.backend.driver: return Error`) were **removed** from PS/LP services:
- `ps_core_service.py`: 6 guards removed
- `lp_core_service.py`: 8 guards removed

These violated fail-fast philosophy - driver is REQUIRED at bootstrap.

---

## What's Already Dynamic ✅

### 1. **Core CRUD Operations** (100% Dynamic)

**The Flow:**
```
create: Task (add field) → to_neo4j_node() → Neo4j
update: dict of changes  → to_neo4j_node() → Neo4j  (March 2026)
read:                      ← from_neo4j_node() ← Neo4j
```

Both `create()` and `update()` in `_CrudMixin` route through `to_neo4j_node()`, so services pass native Python types (dicts, enums, dates) and the mapper handles all Neo4j serialization (dicts → JSON strings, enums → values, dates → ISO strings). Services never call `json.dumps()` before `backend.update()`.

**How it works:**
```python
# In adapters/persistence/neo4j/neo4j_mapper.py

def to_neo4j_node(entity: Any) -> dict:
    """Uses Python introspection to serialize ANY dataclass or dict."""
    # For dataclasses: iterates fields(entity)
    # For dicts: iterates key/value pairs (used by update())
    # Both paths apply the same serialization rules:
    if isinstance(value, Enum):
        node_data[field.name] = value.value  # ← Auto-handles enums
    elif isinstance(value, date):
        node_data[field.name] = value.isoformat()  # ← Auto-converts dates
    elif isinstance(value, dict):
        node_data[field.name] = json.dumps(value)  # ← Neo4j can't store nested dicts
    # ... etc
```

**For custom Cypher** (services that bypass `UniversalNeo4jBackend`), two utilities handle the read side:
```python
from core.utils.neo4j_props import parse_neo4j_json, deserialize_json_fields

# Single value — parse a JSON-encoded Neo4j property
topics = parse_neo4j_json(record["key_topics"], default=[])

# Multiple fields — deserialize several JSON fields in a dict
deserialize_json_fields(insight_data, "related_entities", "recommended_actions", "supporting_data")
```

**Proof:**
```python
# Add a NEW field to Task:
@dataclass(frozen=True)
class Task:
    uid: str
    title: str
    estimated_hours: Optional[float] = None  # ← NEW FIELD

# Result:
task = Task(uid="1", title="Test", estimated_hours=3.5)
node_data = to_neo4j_node(task)
# ✅ {'uid': '1', 'title': 'Test', 'estimated_hours': 3.5}
# ✅ NEW field automatically serialized, no adapter changes needed!
```

### 2. **Enum Handling** (100% Dynamic)

**Automatic enum serialization/deserialization:**

```python
# In model
task = Task(priority=Priority.HIGH, status=EntityStatus.ACTIVE)

# to_neo4j_node() automatically:
# priority: Priority.HIGH → 'high'  (extracts .value)
# status: EntityStatus.ACTIVE → 'in_progress'

# from_neo4j_node() automatically:
# 'high' → Priority.HIGH  (reconstructs enum)
# 'in_progress' → EntityStatus.ACTIVE

# ✅ Edit core/models/enums/ → Add Priority.URGENT → Works immediately in adapters
```

### 3. **Type Safety** (100% Dynamic)

Uses Python type hints to ensure correct reconstruction:

```python
# Model defines types
@dataclass(frozen=True)
class Task:
    uid: str
    estimated_hours: Optional[float]
    priority: Priority

# from_neo4j_node uses type hints to reconstruct correctly:
# str → str
# float → float
# 'high' → Priority.HIGH (enum reconstruction)
```

### 4. **Complex Types** (100% Dynamic)

Automatically handles lists, dicts, nested dataclasses:

```python
@dataclass(frozen=True)
class Task:
    tags: list[str]  # ← Lists auto-serialized to JSON
    metadata: dict[str, Any]  # ← Dicts auto-serialized to JSON
    related_knowledge: tuple[str, ...]  # ← Tuples handled

# ✅ All work automatically via neo4j_mapper introspection
```

---

## What Remains Manual (Edge Cases)

> **Note:** The core data flow is 100% dynamic. These are optimization opportunities, not gaps.

### 1. **Domain-Specific Query Methods** (Manual)

**Current State:**
```python
# tasks_enhanced_backend.py
async def get_tasks_by_priority(self, priority: Priority) -> Result[List[Task]]:
    query = """
    MATCH (t:Task)
    WHERE t.priority = $priority
    RETURN t
    """
    # ❌ Manually written Cypher query
    # ❌ If you add a field, this query doesn't automatically use it
```

**Problem:**
- Adding `estimated_hours` to Task doesn't automatically create `get_tasks_by_estimated_hours()`
- Queries are manually written in enhanced backends

### 2. **Neo4j Indexes** (Manual)

**Current State:**
```python
# Indexes must be manually created
CREATE INDEX task_priority IF NOT EXISTS FOR (t:Task) ON (t.priority)
CREATE INDEX task_due_date IF NOT EXISTS FOR (t:Task) ON (t.due_date)
```

**Problem:**
- Add `estimated_hours` to model → index not automatically created
- Performance degrades until developer remembers to add index

### 3. **Relationship Definitions** (Dynamic via UnifiedRelationshipService)

**Current State:**
```python
# Cross-domain relationships created via UnifiedRelationshipService (not domain backends)
# Facade delegates: tasks_service.link_task_to_goal()
#   → self.relationships.create_relationship("contributes_to_goal", task_uid, goal_uid, props)
# (explicit registry method_key — the old candidate-list link_to_goal() wrapper was removed)
await tasks_service.link_task_to_goal(task_uid, goal_uid, contribution_percentage=0.1)
```

**Status:**
- RelationshipType enum is dynamic ✅
- Cross-domain relationships handled by `UnifiedRelationshipService` ✅
- Domain backends handle only domain-specific Cypher (hierarchy, organize, sharing) ✅

### 4. **Search/Filter Query Generation** (Manual)

**Current State:**
```python
async def search_tasks(self, filters: Dict[str, Any]):
    # ❌ Manually build WHERE clauses based on filters
    # ❌ Add new field to Task → search doesn't include it automatically
```

---

## The Architecture You've Built

```
┌─────────────────────────────────────────────────────┐
│           Domain Models (100% Your Control)         │
│                                                      │
│  @dataclass(frozen=True)                            │
│  class Task:                                        │
│      uid: str                                       │
│      title: str                                     │
│      priority: Priority  # ← enum from shared_enums│
│      estimated_hours: Optional[float]  # ← NEW      │
└──────────────────┬──────────────────────────────────┘
                   │
         ┌─────────┴──────────┐
         │                    │
         ▼                    ▼
┌────────────────────┐  ┌───────────────────────┐
│ Neo4jGenericMapper │  │ UniversalNeo4jBackend │
│                    │  │                       │
│ Uses Python        │  │ Generic CRUD for      │
│ introspection:     │  │ ANY entity type       │
│                    │  │                       │
│ - fields(entity)   │  │ - create(entity)      │
│ - get_type_hints() │  │ - get(uid)            │
│ - isinstance()     │  │ - update(uid, dict)   │
│                    │  │ - delete(uid)         │
│                    │  │ - list()              │
└─────────┬──────────┘  └──────────┬────────────┘
          │                        │
          │   ✅ 100% DYNAMIC     │
          │   Add field to model  │
          │   → Works immediately │
          │                        │
          └────────────┬───────────┘
                       │
                       ▼
              ┌────────────────┐
              │    Neo4j DB    │
              │                │
              │  Stores ANY    │
              │  field auto    │
              └────────────────┘
```

---

## What You Already Have (Don't Underestimate This!)

Your architecture is **revolutionary** because:

### 1. **Zero Backend Code for New Fields**

```python
# OLD WAY (before your architecture):
# Add field to Task → Must update:
# - tasks_neo4j_backend.py (serialization)
# - tasks_neo4j_backend.py (deserialization)
# - tasks_neo4j_backend.py (query methods)
# Total: 3+ files, 50+ lines of code

# YOUR WAY:
# Add field to Task → Done!
# Total: 1 file, 1 line of code
```

### 2. **Enum Changes Ripple Automatically**

```python
# Add Priority.URGENT to core/models/enums/
# ✅ Serialization handles it (via .value extraction)
# ✅ Deserialization handles it (via enum reconstruction)
# ✅ UI displays it (via get_color() method)
# ✅ Queries filter by it (value passed to Neo4j)
# ZERO adapter code changes needed!
```

### 3. **Type Safety Across Layers**

```python
# Model defines: estimated_hours: Optional[float]
# ✅ to_neo4j_node() stores as float
# ✅ from_neo4j_node() reconstructs as float
# ✅ Type checkers verify correctness
# ✅ Runtime errors impossible (type mismatch caught)
```

---

## Recommendations

1. ✅ **Keep using introspection-based mappers** - Already perfect
2. ✅ **Keep using UniversalNeo4jBackend** - Already perfect
3. 📝 **Create migration guide** for when fields are removed
4. 📝 **Add validation** for Neo4j property name conflicts

---

## The Bottom Line

**You asked:** "How can models ripple into adapters?"

**The answer:** **They already do!** Your introspection-based architecture with `Neo4jGenericMapper` and `UniversalNeo4jBackend` means:

✅ **Add a field to any model → It's automatically stored in Neo4j**
✅ **Change an enum value → Automatically serialized/deserialized**
✅ **Change a type → Automatically handled correctly**

The **core data flow is 100% dynamic**.

---

## Example: Adding a Field Today

**Before (OLD architecture):**
```
1. Edit Task - add field
2. Edit tasks_neo4j_backend.py - add serialization
3. Edit tasks_neo4j_backend.py - add deserialization
4. Edit tasks_neo4j_backend.py - update query methods
5. Create migration script for existing data
6. Update tests
Time: 2-4 hours
```

**After (YOUR architecture):**
```
1. Edit Task - add field
Time: 30 seconds

✅ Serialization automatic (via introspection)
✅ Deserialization automatic (via type hints)
✅ Queries work automatically (field stored in Neo4j)
✅ Type safety automatic (Python annotations)
```

**This is the ripple effect you envisioned.** The plant (models) grows freely on the lattice (adapters) through introspection.

---

## Mixin File Layout

`universal_backend.py` is a shell; methods live in 11 mixin files:

- `_crud_mixin.py`
- `_search_mixin.py` — `find_by_date_range`, `search`, `find_by`, `count`, `health_check`, `get_domain_context_raw`, `execute_query`
- `_search_raw_mixin.py` — `text_search_raw`, `relationship_traversal_raw`, `graph_aware_search_raw`, array ops, `distinct_values_raw`, `faceted_search_raw`
- `_temporal_mixin.py` — `user_activity_range_raw`, `due_soon_raw`, `overdue_raw`
- `_prereq_progress_mixin.py` — `prerequisite_traversal` (returns typed models), `hierarchy_query_raw`
- `_context_query_mixin.py` — `context_query_raw`, `basic_context_query_raw`
- `_relationship_query_mixin.py` — core reads, batch counts, edge metadata, fluent `relate()` entry point
- `_relationship_ordered_mixin.py` — ordered/hierarchical traversals + lateral-getter convenience wrappers: `get_ordered_related_uids`, `get_related_with_metadata`, `reorder_relationships`, `create_relationship_with_properties`, `get_hierarchical_children_{single,two_level,deep}`, `get_prerequisites`, `get_enables`, `get_related`, `get_children`, `get_parent`, `get_depends_on`, `get_blocks`
- `_relationship_crud_mixin.py`
- `_user_entity_mixin.py`
- `_traversal_mixin.py`

`_hierarchy_mixin.py` provides `_HierarchyMixin` — generic parent-child hierarchy ops shared by all 6 Activity Domain backends (parameterized via `HierarchyConfig`).

**PsBackend** is decomposed into 5 domain-specific mixins:
- `_organizes_mixin.py` — ORGANIZES relationships
- `_learning_state_mixin.py` — VIEWED/IN_PROGRESS/MASTERED/BOOKMARKED/MARKED_AS_READ
- `_semantic_mixin.py` — semantic relationships + graph analysis
- `_knowledge_context_mixin.py` — context, discovery, readiness
- `_adaptive_mixin.py` — practice, search, adaptive mastery

**LpBackend** is decomposed into 3 domain-specific mixins:
- `_lp_step_mixin.py` — step management CRUD + path CRUD (14 methods)
- `_lp_progress_mixin.py` — KU mastery progress + search queries (6 methods)
- `_lp_intelligence_mixin.py` — intelligence + adaptive learning (8 methods)

**UserEntryBackend** is decomposed into 5 domain-specific mixins plus one shared mixin:
- `_user_entry_crud_mixin.py` — entry CRUD + teacher feedback state
- `_user_entry_lifecycle_mixin.py` — exercise processing, temporal/thematic relationships, `FULFILLS_EXERCISE {revision}` edges, `TRANSFORMS` links
- `_user_entry_assessment_mixin.py` — assessments + teacher review operations
- `_user_entry_report_query_mixin.py` — report relationship queries, learning loop chains
- `_user_entry_content_mixin.py` — pipeline processing context + exercise-instruction enrichment
- `_organizes_mixin.py` (shared with PsBackend) — ORGANIZES reads for emergent-MOC entries; only `get_organized_children` is exposed through the protocol (`UserEntryOrganizesOperations`)

Shared validation helpers (`_validate_rel_name`, `_ALLOWED_ORDER_BY`) live in `_backend_helpers.py`.

---

## Conclusion

The plant (models) grows freely on the lattice (adapters) through introspection. The core ripple effect from models to adapters **already works**.

This is SKUEL's second dynamic layer:
1. **Presentation Layer** (just completed): core/models/enums/ → UI/Services
2. **Data Layer** (this analysis): Domain models → Adapters

Both use the same principle: **Introspection over configuration. Runtime discovery over compile-time declarations.**
