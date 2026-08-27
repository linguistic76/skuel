---
title: Documentation Index
updated: 2026-08-11
status: current
category: index
tags: [index, navigation, documentation]
related: []
---

# SKUEL Documentation Index

> **⚠️ SINGLE SOURCE OF TRUTH:** All technical documentation lives in `/docs/`
>
> `/home/mike/0bsidian/skuel/docs/` contains **content** (KU docs), NOT technical documentation.

> **Hand-maintained — there is no generator.** This index is a *curated* subset of `docs/`, not
> a listing of it: rows sit under the section that fits them (an ADR can belong under
> Architecture), and the descriptions are written, not derived. Add a row when you add a doc
> worth finding; `./dev health-links` flags any row pointing at a file that no longer exists.
>
> **Row format:** two cells — a markdown link to the doc, then a one-line description. There is
> deliberately no line-count or last-updated column: both are derivable (`wc -l <path>`,
> `git log -1 --format=%ad -- <path>`) and both had drifted badly once hand-transcribed (only 5
> of the 150 transcribed line-counts, 3%, still matched the file), so they were removed rather
> than re-synced.
>
> **One table is deliberately three cells:** the Roadmap section's **Completed
> (`docs/roadmap/done/`)** table keeps a `Completed` date between the link and the description.
> That date is the point of that table rather than derivable metadata, so it stays; all 16 of its
> rows carry a description as well.
>
> **The description cell is filled in progressively — 96 of 283 data rows have one today**
> (283 excludes the 20 table-header rows; 187 cells are still empty). An empty
> cell means *not yet written*, never "nothing worth saying"; the row still earns its place by
> being listed. Descriptions carried over from the old table, which shoehorned them into its
> `Lines` column; the rest are being written as docs get touched. Write the description when you
> add or edit a row — do not bulk-generate them, since a derived one-liner is exactly the kind of
> approximate prose this index was rewritten to stop carrying.

> **New here? Read [START_HERE.md](START_HERE.md) first.** It covers what SKUEL is, the entity types, how a request flows, and the key patterns — in 5 minutes.

> **📝 Documentation Standards:**
> - **File Naming:** UPPERCASE for major reference docs/guides, lowercase for specific patterns
> - **Full Standards:** See [README.md](README.md#documentation-standards)

## Quick Links

- [Domains](#domains) - Entity type architecture documentation
- [Architecture](#architecture) - System design and domain structure
- [Patterns](#patterns) - Implementation patterns and coding standards
- [DSL](#dsl) - Activity DSL specification and usage
- [Decisions](#decisions) - Architecture Decision Records
- [Guides](#guides) - Step-by-step implementation guides
- [Tools](#tools) - Developer tooling and maintenance scripts
- [Reference](#reference) - Templates and checklists
- [Features](#features) - Implemented features with complete documentation
- [Migrations](#migrations) - Database and code migration guides

## Skills Quick Reference

For hands-on implementation, invoke these skills:
- [@python](../.claude/skills/python/SKILL.md) - Python patterns
- [@result-pattern](../.claude/skills/result-pattern/SKILL.md) - Error handling
- [@base-analytics-service](../.claude/skills/base-analytics-service/SKILL.md) - Analytics services
- [All skills](../.claude/skills/skills_metadata.yaml)

See [CROSS_REFERENCE_INDEX.md](CROSS_REFERENCE_INDEX.md) for skills ↔ docs mapping.

---

## Design Principles

*Core principles governing every technical decision — see [Design Principles](design-principles/README.md)*

| Document | Description |
|----------|-------------|
| [One Path Forward](design-principles/ONE_PATH_FORWARD.md) | When a better pattern emerges, the old one is deleted entirely |
| [Fail Fast](design-principles/FAIL_FAST.md) | Dependencies are required; errors surface immediately with clear reports |
| [Leverage Maintained Software](design-principles/LEVERAGE_MAINTAINED_SOFTWARE.md) | Adopt established open-source software over bespoke alternatives |
| [Type Safety as Ontology](design-principles/TYPE_SAFETY_AS_ONTOLOGY.md) | Enums and types define what the app *is*, not just what it accepts |
| [Limited Backward Compatibility](design-principles/LIMITED_BACKWARD_COMPATIBILITY.md) | No legacy wrappers, no deprecation periods, no historical references |
| [Analog-Digital Independence](design-principles/ANALOG_DIGITAL_INDEPENDENCE.md) | The Analog layer is the foundation, not a degraded Digital layer |

---

## Domains

*Entity Types with behavioral traits — see [Entity Type Architecture](architecture/ENTITY_TYPE_ARCHITECTURE.md)*

| Document | Description |
|----------|-------------|
| [Domains Overview](domains/README.md) | Complete entity type reference |
| [Tasks](domains/tasks.md) | Work items with dependencies and deadlines |
| [Goals](domains/goals.md) | Objectives with milestones and progress |
| [Habits](domains/habits.md) | Recurring behaviors with streak tracking |
| [Events](domains/events.md) | Calendar items with scheduling |
| [Choices](domains/choices.md) | Decisions with outcome tracking |
| [Principles](domains/principles.md) | Values that guide goals and choices |
| [Finance](domains/finance.md) | Hybrid — Firefly III for expenses/budgets/reporting, local for invoices (admin-only, ADR-052) |
| [KU (Knowledge Unit)](domains/ku.md) | Atomic knowledge unit (point topology) |
| [PS (Path Step)](domains/ps.md) | THE curriculum content entity — composes Kus (collection topology) |
| [LP (Learning Path)](domains/lp.md) | Complete learning sequences (path topology) |
| [Submissions + Reports](architecture/LEARNING_LOOP_ARCHITECTURE.md) | Exercise→UserEntry→EntryReport→RevisedExercise (4-phase learning loop, anchored to PathStep via HAS_EXERCISE) |
| [Journals](architecture/JOURNALS_DOMAIN_ARCHITECTURE.md) | Journal workflows on the UserEntry domain (JE_INPUT → JE_OUTPUT, AI-processed; ADR-054) |
| Groups | Teacher-student class management (ADR-040) — doc pending |
| [MOC (Map of Content)](domains/moc.md) | Non-linear navigation (graph topology via ORGANIZES) |
| [LifePath](domains/lifepath.md) | "Am I living my life path?" |

---

## Architecture

*System architecture, domain structure, and design decisions*

| Document | Description |
|----------|-------------|
| [Admin Dashboard Architecture](architecture/ADMIN_DASHBOARD_ARCHITECTURE.md) | |
| [Alpine.js Architecture](architecture/ALPINE_JS_ARCHITECTURE.md) | |
| [Curriculum Grouping Patterns: KU, PS, LP + MOC Organization](architecture/CURRICULUM_GROUPING_PATTERNS.md) | |
| **[Cross-Domain UID Patterns: Structural Anchors vs Enrichment Links](architecture/CROSS_DOMAIN_UID_PATTERNS.md)** | **The rule for all cross-domain UID fields across Activity + Curriculum domains — persisted anchors vs DERIVED enrichment links** |
| **[Enum Architecture](architecture/ENUM_ARCHITECTURE.md)** | |
| **[Priority & Confidence Architecture](architecture/PRIORITY_CONFIDENCE_ARCHITECTURE.md)** | |
| [Finance Categories System (LEGACY — superseded by ADR-052)](architecture/FINANCE_CATEGORIES_GUIDE.md) | |
| **[Learning Loop Architecture](architecture/LEARNING_LOOP_ARCHITECTURE.md)** | |
| **[Learning Progress Event Chain](architecture/LEARNING_PROGRESS_EVENT_CHAIN.md)** | |
| [Knowledge Substance Philosophy](architecture/knowledge_substance_philosophy.md) | |
| **[Type Safety Design Philosophy](architecture/TYPE_SAFETY_DESIGN_PHILOSOPHY.md)** | **Why types matter for SKUEL's ontology, security, and raw-to-typed lifecycle** |
| **[Model Architecture](architecture/MODEL_ARCHITECTURE.md)** | |
| **[Relationships Architecture](architecture/RELATIONSHIPS_ARCHITECTURE.md)** | |
| **[Report Architecture](architecture/REPORT_ARCHITECTURE.md)** | |
| [SKUEL Entity Type Architecture](architecture/ENTITY_TYPE_ARCHITECTURE.md) | |
| **[The 7 Subsystems — Functional Organization](architecture/SEVEN_SUBSYSTEMS.md)** | **Ku / Curriculum / Activity / Learning Loop / User / Groups / Askesis — Object·Context·Meta split + 7×3 MVP matrix** |
| **[The 3-Layer Lens — A Cross-Cutting View](architecture/THREE_LAYER_LENS.md)** | **Curriculum → Action → Feedback; how to read SKUEL operationally (Model B, companion to Entity Types = Model A)** |
| [SKUEL Routing Architecture: Routes, Services, and ...](architecture/ROUTING_ARCHITECTURE.md) | |
| [Search Architecture - Unified Search System](architecture/SEARCH_ARCHITECTURE.md) | |
| [Service Architecture: File Organization & Topology](architecture/SERVICE_TOPOLOGY.md) | |
| [User Architecture — Model, Auth, Roles, UserContext](architecture/UNIFIED_USER_ARCHITECTURE.md) | |
| **[PWA Mobile Strategy](decisions/ADR-050-pwa-mobile-strategy.md)** | |
| **[How Askesis Works](architecture/ASKESIS_HOW_IT_WORKS.md)** | **Plain-English explanation of both halves: intelligence synthesis + guided RAG pipeline** |
| [Askesis Architecture](architecture/ASKESIS_ARCHITECTURE.md) | |
| [Askesis Pedagogical Architecture](architecture/ASKESIS_PEDAGOGICAL_ARCHITECTURE.md) | ZPD-aware Socratic companion vision — how Askesis teaches, not how it is built |
| [Askesis Socratic Architecture](architecture/ASKESIS_SOCRATIC_ARCHITECTURE.md) | PS-scoped Socratic pipeline — PsBundle, PedagogicalIntent, SocraticEngine, ZPD integration |
| **[Canon Citation & Discussion Design](architecture/CANON_CITATION_DESIGN.md)** | **Decision-support for a companion that quotes + cites the canon shelf: quotation-policy / location-granularity / faithfulness / surface choices, reuse map, Phases A–D (see ADR-076)** |
| [Analytics Architecture](architecture/ANALYTICS_ARCHITECTURE.md) | |
| [Core Systems Architecture](architecture/CORE_SYSTEMS_ARCHITECTURE.md) | |
| **[Service Topology](architecture/SERVICE_TOPOLOGY.md)** | |
| **[Audio Transcription Architecture](architecture/AUDIO_TRANSCRIPTION_ARCHITECTURE.md)** | **Config-driven Deepgram options, utterance formatting, batch pipeline, intelligence features** |

## Configuration

*External service configuration files*

| Document | Description |
|----------|-------------|
| **[Deepgram Configuration Guide](configuration/DEEPGRAM_CONFIG.md)** | **All Deepgram transcription options — model, formatting, utterances, intelligence, vocabulary** |

## Patterns

*Implementation patterns, coding standards, and best practices*

| Document | Description |
|----------|-------------|
| **[API Input Validation Patterns](patterns/API_VALIDATION_PATTERNS.md)** | |
| [Async/Sync Design Pattern](patterns/ASYNC_SYNC_DESIGN_PATTERN.md) | |
| [BackendOperations Protocol Architecture](patterns/BACKEND_OPERATIONS_ISP.md) | |
| [Code Quality Enforcement - Linter Rules](patterns/linter_rules.md) | |
| [Constants Usage Guide](patterns/constants_usage_guide.md) | |
| [Context-First Relationship Pattern](patterns/CONTEXT_FIRST_RELATIONSHIP_PATTERN.md) | |
| [PrerequisiteChecker & the Learning-Requirements Lens](patterns/PREREQUISITE_CHECKER_PATTERN.md) | |
| [Domain-Specific Hooks Pattern](patterns/DOMAIN_SPECIFIC_HOOKS.md) | |
| **[Lateral Relationships Visualization Pattern](patterns/LATERAL_RELATIONSHIPS_VISUALIZATION.md)** | |
| [Error Handling Architecture](patterns/ERROR_HANDLING.md) | |
| [Event-Driven Architecture](patterns/event_driven_architecture.md) | |
| [FastHTML Type Hints Pattern Guide](patterns/FASTHTML_TYPE_HINTS_GUIDE.md) | |
| [UnifiedRelationshipService - Configuration-Driven](patterns/UNIFIED_RELATIONSHIP_SERVICE.md) | |
| [Graph Access Patterns Guide](patterns/GRAPH_ACCESS_PATTERNS.md) | |
| [HTTP Status Codes - REST Best Practices](patterns/http_status_codes.md) | |
| **[Knowledge Application Tracking](patterns/KNOWLEDGE_APPLICATION_TRACKING.md)** | |
| **[Insight Action Tracking Pattern](patterns/INSIGHT_ACTION_TRACKING.md)** | |
| [Logging Patterns](patterns/LOGGING_PATTERNS.md) | |
| [EntityTimestampMixin - Consistent Timestamp & Meta...](patterns/entity_timestamp_mixin.md) | |
| [Model-to-Adapter Dynamic Architecture](patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md) | |
| [MyPy Pragmatic Strategy - Making Peace with 2200 E...](patterns/mypy_pragmatic_strategy.md) | |
| [nous_subtopic Facet - Mechanism](patterns/NOUS_SUBTOPIC_FACET.md) | |
| [Neo4j Server Tuning (memory, JVM, Vector API)](patterns/NEO4J_SERVER_TUNING.md) | |
| [Performance Monitoring System](patterns/PERFORMANCE_MONITORING.md) | |
| [Protocol Architecture](patterns/protocol_architecture.md) | |
| [Protocol LSP Compliance Pattern](patterns/PROTOCOL_LSP_COMPLIANCE.md) | |
| [Pure Cypher vs APOC: Strategic Decision Guide](patterns/CYPHER_VS_APOC_STRATEGY.md) | |
| [Intent-Based Graph Traversal](patterns/INTENT_BASED_TRAVERSAL.md) | |
| [Query Architecture](patterns/query_architecture.md) | |
| [Curriculum Query Patterns](patterns/curriculum/curriculum_query_patterns.md) | |
| [Pedagogical Questions](intelligence/PEDAGOGICAL_QUESTIONS.md) | |
| [Return Type Error Propagation Pattern](patterns/RETURN_TYPE_ERROR_PROPAGATION.md) | |
| [SearchService Pattern for Activity Domains](patterns/search_service_pattern.md) | |
| **[Three-Tier Type System](patterns/three_tier_type_system.md)** | |
| **[Type Safety Architecture Overview](patterns/TYPE_SAFETY_OVERVIEW.md)** | |
| **[Any Usage Policy](patterns/ANY_USAGE_POLICY.md)** | |
| **[MyPy Type Safety Patterns](patterns/MYPY_TYPE_SAFETY_PATTERNS.md)** | |
| [Trial Limits Infrastructure](patterns/TRIAL_LIMITS.md) | |
| [Service Consolidation Patterns](patterns/SERVICE_CONSOLIDATION_PATTERNS.md) | |
| [Unified Ingestion Guide](patterns/UNIFIED_INGESTION_GUIDE.md) | |
| [FastHTML Route Registration](patterns/FASTHTML_ROUTE_REGISTRATION.md) | |
| [Standalone Service Pattern](patterns/STANDALONE_SERVICE_PATTERN.md) | |
| [Secondary Entity Pattern](patterns/SECONDARY_ENTITY_PATTERN.md) | |
| [Configuration-Driven Service Architecture](patterns/CONFIGURATION_DRIVEN_SERVICE_ARCHITECTURE.md) | |
| [Auth Patterns](patterns/AUTH_PATTERNS.md) | |
| [Ownership Verification](patterns/OWNERSHIP_VERIFICATION.md) | |
| **[Content Sharing Patterns](patterns/SHARING_PATTERNS.md)** | |
| **[Route Decorator Architecture](patterns/ROUTE_DECORATOR_ARCHITECTURE.md)** | |
| [Route Factories](patterns/ROUTE_FACTORIES.md) | |
| [Route Naming Convention](patterns/ROUTE_NAMING_CONVENTION.md) | |
| [Error Handling Decorators](patterns/error_handling_decorators.md) | |
| [UID Boundary Conversion](patterns/UID_BOUNDARY_CONVERSION.md) | |
| [Query Patterns](patterns/QUERY_PATTERNS.md) | |
| **[Integration Testing Patterns](patterns/TESTING_PATTERNS.md)** | |
| **[UI Component Patterns](patterns/UI_COMPONENT_PATTERNS.md)** | |
| **[Shell-First Page Loading Pattern](patterns/SHELL_FIRST_PAGE_PATTERN.md)** | |
| **[FormGenerator Guide](patterns/FORM_GENERATOR_GUIDE.md)** | |
| **[Sibling Signal Pattern](patterns/SIBLING_SIGNAL_PATTERN.md)** | **Peer-to-peer cross-domain intelligence consultation between the 6 Activity Domains (companion to ADR-057; proposed shape, no code yet)** |
| **[Shared Signal Pattern](patterns/SHARED_SIGNAL_PATTERN.md)** | **Cross-cutting infrastructure → every-peer consultation (companion to Sibling Signal; the `ActivityKnowledgeIntelligenceService` precedent already productionizes this shape)** |

## Dsl

*Activity DSL grammar, usage, and implementation*

| Document | Description |
|----------|-------------|
| [SKUEL Activity DSL - Formal Specification](dsl/DSL_SPECIFICATION.md) | |
| [SKUEL Activity DSL - Implementation Guide](dsl/DSL_IMPLEMENTATION.md) | |
| [SKUEL Activity DSL - Usage Guide](dsl/DSL_USAGE_GUIDE.md) | |

## Decisions

*Architecture Decision Records (ADRs)*

| Document | Description |
|----------|-------------|
| [ADR-001: Single Complex Query for Unified User Con...](decisions/ADR-001-unified-user-context-single-query.md) | |
| [ADR-002: Knowledge Coverage Calculation Query](decisions/ADR-002-user-progress-service-query.md) | |
| [ADR-003: Journal Context Gathering Query](decisions/ADR-003-journals-service-query.md) | |
| [ADR-004: Ready-to-Learn Knowledge Unit Query](decisions/ADR-004-ku-graph-service-query.md) | |
| [ADR-005: Ready-to-Learn Knowledge Query Architectu...](decisions/ADR-005-ready-to-learn-knowledge-query.md) | |
| [ADR-006: Knowledge Gaps for Goals Query Architectu...](decisions/ADR-006-knowledge-gaps-for-goals-query.md) | |
| [ADR-007: Graph-Sourced-Context-Builder Query Archi...](decisions/ADR-007-graph-sourced-context-builder-query.md) | |
| [ADR-008: Learning Path Blocker Identification Quer...](decisions/ADR-008-lp-validation-service-query.md) | |
| [ADR-009: Optimal Learning Path Recommendation Quer...](decisions/ADR-009-lp-validation-service-query.md) | |
| [ADR-010: Moc-Core-Service Query Architecture](decisions/ADR-010-moc-core-service-query.md) | |
| [ADR-011: Life Path Alignment Query Architecture](decisions/ADR-011-life-path-alignment-query.md) | |
| [ADR-012: Cross-Domain Knowledge Applications Query...](decisions/ADR-012-cross-domain-knowledge-applications-query.md) | |
| [ADR-013: KU UID Flat Identity](decisions/ADR-013-ku-uid-flat-identity.md) | |
| [ADR-014: Unified Content Ingestion](decisions/ADR-014-unified-ingestion.md) | |
| [ADR-015: MEGA-QUERY Rich Queries Completion](decisions/ADR-015-mega-query-rich-queries-completion.md) | |
| [ADR-016: Context Builder Decomposition](decisions/ADR-016-context-builder-decomposition.md) | |
| [ADR-017: Relationship Service Unification](decisions/ADR-017-relationship-service-unification.md) | |
| [ADR-018: Four-Tier User Role System](decisions/ADR-018-user-roles-four-tier-system.md) | |
| [ADR-019: Transcription Service Simplification](decisions/ADR-019-transcription-service-standalone.md) | |
| [ADR-020: FastHTML Route Registration Pattern](decisions/ADR-020-fasthtml-route-registration-pattern.md) | |
| [ADR-021: User Context Intelligence Modularization](decisions/ADR-021-user-context-intelligence-modularization.md) | |
| [ADR-022: Graph-Native Authentication](decisions/ADR-022-graph-native-authentication.md) | |
| [ADR-023: Unified BaseService Architecture](decisions/ADR-023-curriculum-baseservice-migration.md) | |
| [ADR-024: BaseAnalyticsService Migration](decisions/ADR-024-base-intelligence-service-migration.md) | |
| [ADR-025: Service Consolidation Patterns](decisions/ADR-025-service-consolidation-patterns.md) | |
| [ADR-026: Unified Relationship Registry](decisions/ADR-026-unified-relationship-registry.md) | |
| [ADR-027: Knowledge Carrier Protocol](decisions/ADR-027-knowledge-carrier-protocol.md) | |
| [ADR-028: KU & MOC Unified Relationship Migration](decisions/ADR-028-ku-moc-unified-relationship-migration.md) | |
| [ADR-029: GraphNative Service Removal](decisions/ADR-029-graphnative-service-removal.md) | |
| [ADR-030: UserContext File Consolidation](decisions/ADR-030-usercontext-file-consolidation.md) | |
| [ADR-031: BaseService Mixin Decomposition](decisions/ADR-031-baseservice-mixin-decomposition.md) | |
| [ADR-032: Search Routes Explicit Dependency Injection](decisions/ADR-032-search-routes-explicit-di.md) | |
| [ADR-034: Semantic Search Phase 1 Enhancement](decisions/ADR-034-semantic-search-phase1-enhancement.md) | |
| [ADR-035: Tier Selection Guidelines](decisions/ADR-035-tier-selection-guidelines.md) | |
| [ADR-036: Prometheus Primary Cache Pattern](decisions/ADR-036-prometheus-primary-cache-pattern.md) | |
| **[ADR-037: Lateral Relationships Visualization (Phase 5)](decisions/ADR-037-lateral-relationships-visualization-phase5.md)** | |
| **[ADR-038: Content Sharing Model](decisions/ADR-038-content-sharing-model.md)** | |
| **[ADR-050: PWA Mobile Strategy](decisions/ADR-050-pwa-mobile-strategy.md)** | |
| **[ADR-040: Teacher Exercise Workflow](decisions/ADR-040-teacher-exercise-workflow.md)** | |
| **[ADR-041: Unified Ku Model](decisions/ADR-041-unified-ku-model.md)** | |
| **[ADR-042: Privacy as First-Class Citizen](decisions/ADR-042-privacy-as-first-class-citizen.md)** | |
| **[ADR-043: Intelligence Tier Toggle](decisions/ADR-043-intelligence-tier-toggle.md)** | |
| **[ADR-044: Neo4j as Committed Architectural Choice](decisions/ADR-044-neo4j-committed-architectural-choice.md)** | |
| **[ADR-045: Priority & Confidence as First-Class Customization Dials](decisions/ADR-045-priority-confidence-customization-dials.md)** | |
| **[ADR-046: Activity Domains Connect to Ku via Graph Edges](decisions/ADR-046-activity-domains-not-ku-subtypes.md)** | |
| **[ADR-047: Entity Types Replace Domain Categories](decisions/ADR-047-entity-types-replace-domain-categories.md)** | |
| **[ADR-048: Adaptive Learning Loop Architecture](decisions/ADR-048-adaptive-learning-loop.md)** | |
| **[ADR-052: Firefly III Replaces SKUEL Expense/Budget/Reporting](decisions/ADR-052-firefly-iii-finance-integration.md)** | |
| **[ADR-053: Groups First-Class + Unified Sharing](decisions/ADR-053-groups-first-class-and-unified-sharing.md)** | |
| **[ADR-054: UserEntry — Unified User-Authored Content](decisions/ADR-054-user-entry-unified-submissions.md)** | |
| **[ADR-055: Architectural Lenses — Subsystems + 3-Layer Lens](decisions/ADR-055-architectural-lenses.md)** | **Model A (7 Subsystems / EntityTypes) + Model B (3-Layer Lens); adopts "Subsystems" vocabulary** |
| **[ADR-056: Service-Layer Label Split — entity_label + config_lookup_label](decisions/ADR-056-service-layer-label-split.md)** | **DomainConfig.entity_label split into Neo4j base-label + LABEL_CONFIGS registry key; LABEL_CONFIGS["Entity"] → PS_CONFIG alias deleted; factories fail-fast on missing keys** |
| **[ADR-057: Activity-Domain Sibling Signals](decisions/ADR-057-activity-domain-sibling-signals.md)** | **Design-only (Proposed): narrow ISP protocols in core/ports/ for cross-domain intelligence consultation at judgment time; 6 ways-of-acting, 3 mutual axes + 7 diagonals; companion Shared Signal pattern for cross-cutting infrastructure → peer consultation** |
| **[ADR-060: UserContext as Single Source of Truth — Awareness Slice Protocols Retired](decisions/ADR-060-userctx-single-source-of-truth.md)** | **11 ISP "awareness slice" protocols (`TaskAwareness`, `KnowledgeAwareness`, `FullAwareness`, etc.) deleted; UserContext is the contract; 751 lines removed; type-level minimum-context guarantee was theoretical and outweighed by drift cost** |
| **[ADR-061: Spawn-Layer Consolidation — DomainSpawnSpec Registry](decisions/ADR-061-spawn-layer-consolidation.md)** | **Accepted/implemented: affirm the template/instance two-entity split; collapsed the six `_build_*` builders + scattered per-domain spawn tables into one `DomainSpawnSpec` registry + generic `_build` with import-time fail-fast validation (near-zero type cost — `_persist` already `Any`-typed); document `source_path_step_uid` vs `SPAWNED_FROM` authority; explicitly reject an authoring-fields mixin** |
| **[ADR-063: LLM & Embedding SDKs Behind Ports](decisions/ADR-063-llm-embeddings-sdk-ports.md)** | **Accepted/implemented (W1, extends ADR-044): `openai`/`anthropic`/`huggingface_hub` clients moved out of `core/services/` behind `ChatCompletionPort` + `EmbeddingClientOperations` into `adapters/external/`; `ai_service.py` collapsed into the chat adapters; credential reads moved to the composition root; guard test `test_llm_sdk_boundary.py` (only `exception_types.py` may import the SDK exception classes). Delivered as PRs #67–#71** |
| **[ADR-066: Typed Update Intents (frozen `*UpdateIntent`, one update path)](decisions/ADR-066-typed-update-intents.md)** | **Accepted/implemented — ✅ COMPLETE (2026-06-05): replaced the unsound, decorative `*UpdatePayload` TypedDicts with frozen `*UpdateIntent` dataclasses (`UNSET` sentinel + `to_changes()`); collapsed the four-way write boundary into ONE service-contract update path (validated + event-firing) plus an explicit `# raw-write:` bypass for full-DTO/system writes. Shared `CrudOperationsMixin[B, T, U]` parameterized over the update type `U` (`SupportsToChanges`, default `RawChanges` — `core/models/update_contracts.py`). All six Activity Domains migrated; the six activity `*UpdatePayload` TypedDicts, `_intent_from_mapping` funnels, and facade `Mapping` overrides deleted. PRs #228, #230–233, #236, #238; phased plan in [docs/roadmap/done/update-intents.md](roadmap/done/update-intents.md)** |
| **[ADR-068: OpenAI Embeddings Now, BGE Long-Term](decisions/ADR-068-openai-embeddings-now-bge-later.md)** | **Accepted/implemented: `text-embedding-3-small` @1024 (API `dimensions` param) behind the `create_embedding_client()` provider chokepoint; BGE/HF adapter staged for the long-term swap; `HuggingFaceEmbeddingsService` renamed `EmbeddingsService` (provider-agnostic, reads model/dimension/max_input_chars off the port); EMBEDDING_VERSION v3 = single version source (worker stores through the service); `EmbeddingConfig`/`config.genai` deleted; stale 1536-dim vector indexes recreated at 1024 (`create_vector_indexes.py --recreate`); backfill script made service-mediated + field-map-aware. Supersedes ADR-049 in provider choice only** |
| **[ADR-069: EXTRACT_ACTIVITIES Pipeline + EntryReport Convergence](decisions/ADR-069-extract-activities-pipeline-and-entry-report.md)** | **UserEntry `Pipeline` enum (JOURNAL / EXTRACT_ACTIVITIES / KNOWLEDGE / REFERENCE); ExerciseReport renamed EntryReport (`er_` UIDs); LLM journal responses as PRIVATE self-owned EntryReports** |
| **[ADR-070: Bidirectional VaultBridge — Obsidian ↔ SKUEL Task Sync](decisions/ADR-070-bidirectional-vault-bridge.md)** | **`🆔 sk_<6>` join keys, `[x]`+`✅ date` round-trip, first-run consent gate; `VaultBridgePort`/`FilesystemVaultAdapter`/`VaultReconciler`; ingestion is human-initiated per event (Decision 9 — no background watcher)** |
| **[ADR-071: SKUEL-Owned Tailwind Component Layer](decisions/ADR-071-skuel-tailwind-component-layer.md)** | **Implemented: FrankenUI/monsterui removed; pre-compiled Tailwind + `ui/primitives.py` component layer; Decision 3 (icons) superseded by ADR-072** |
| **[ADR-072: Server-Rendered Inline-SVG Icons](decisions/ADR-072-server-rendered-inline-svg-icons.md)** | **Lucide runtime deleted (non-idempotent `data-lucide` mutation loop); `Icon()` renders inline SVG from `_icon_data.py` harvested by `scripts/gen_icons.py`; supersedes ADR-071 Decision 3** |
| **[ADR-073: Journals Zero-Persistence + Vault as Memory Channel](decisions/ADR-073-journals-zero-persistence-vault-memory.md)** | **Journals persist ZERO to Neo4j (workshop, not storage); vault sync is the only doorway SKUEL learns through; je_raw/je_pro = disk-only few-shot exemplars** |
| **[ADR-074: Post-Persist Embedding Events — Ingestion Never Embeds Inline](decisions/ADR-074-post-persist-embedding-events.md)** | **One `publish_embedding_requested` chokepoint for both ingest doors + all in-app create/update paths (`changed_fields` gate); ingestion `event_bus` tier-gated (CORE → None); shared PathStep chunk step both doors + empty-body clear path; PathStep ENTITY vector = frontmatter, body = CHUNK vectors; `--stale` backfill for script-mode syncs. PRs #487/#488/PR 3** |
| **[ADR-075: Stage-2 LocalAgentVaultAdapter — Hosted Vault Sync Transport](decisions/ADR-075-local-agent-vault-transport.md)** | **Design ADR (B1 of the Stage-2 sub-arc): TLS + per-device Ed25519 auth end-to-end to the app (ciphertext-only re-scoped to a future dumb relay); pairing-code enrollment → `(User)-[:HAS_DEVICE]->(Device)`; outbound-only `WS /ws/agent` with challenge–signature handshake + JSON-RPC-ish envelope (`describe_wall`/`list_changed_since`/`read_note`/`write_task_updates`, vault-relative paths); server-side staging mirror feeds the existing ingest engine (smart-mode hash skip + deletion valves reused verbatim); agent-side wall is primary, server wall = defense in depth; `VAULT_TRANSPORT=filesystem\|local_agent` (default filesystem). IMPLEMENTED: B2 (device identity + channel), B3 (`agent/skuel_vault_agent.py`), B4 (`LocalAgentVaultAdapter` + `VaultMirrorPuller` mirror pull + `VAULT_TRANSPORT` toggle)** |
| **[ADR-076: Canon Quotation & Citation Policy](decisions/ADR-076-canon-quotation-and-citation-policy.md)** | **Proposed (doc-first): the canon journal companion MAY quote + cite the shelf — hybrid grounded-RAG (infuse by default, quote-on-demand, always cite). Supersedes the roadmap "voice-infused, not quoted" prompt-default. Location = structural anchors (chapter/section/position + Resource deep-link; EPUB has no pages). Faithfulness = quote only retrieved text, never fabricate. See `architecture/CANON_CITATION_DESIGN.md`** |
| **[ADR-077: Companion Grounding via a Shared Corpus-Scope Seam](decisions/ADR-077-askesis-canon-scoped-retrieval.md)** | **Askesis (PS-scoped) & Journals (vault-scoped) share ONE retrieve-and-cite contract; scoped-retrieval seam + `to_teaching_block` framing. Phase 1 shipped #612/#613** |
| **[ADR-078: Discussion Sessions Are Stored but Never Understood](decisions/ADR-078-discussion-sessions-stored-not-understood.md)** | **Amends ADR-073 §1/§3 with ONE carve-out: owner-private discussion sessions persist to Neo4j for revisit/continue only — never reaching context builder, embeddings, SearchRouter, ZPD, or any intelligence surface. Stored ≠ understood; the vault doorway stays the only channel in. Doc-first gate for the discussion-first arc P2 (founder confirmation pending)** |
| **[ADR-079: Discourse Sidecar for NOUS Community Forums (Staged)](decisions/ADR-079-discourse-sidecar-nous-forums.md)** | **Proposed, staged-not-scheduled: Discourse (NOT Disqus) as a Firefly-style sidecar when community scale arrives — DiscourseConnect SSO (SKUEL = identity provider), reconciler-synced category per NOUS topic (`nous_subtopic` → tags), iframe embeds on Ku/PS pages, `adapters/external/discourse/` behind a port; forum posts are never entities. Activation trigger + prerequisites inside** |
| **[ADR-080: AuraDB Three-Horizon Strategy & GDS Deferral](decisions/ADR-080-auradb-three-horizon-strategy.md)** | **Accepted direction (H2/GDS staged): move to AuraDB Free soon; defer Neo4j Graph Data Science until content density justifies it. Three horizons on one graph — H0 Free readiness (telemetry retention + paused-instance tolerance), H1 author edge-first + a structural-health gauge, H2 slot GDS behind a port born only then. GDS = Digital-layer enhancer (ADR-043), AuraDB Free ≠ AuraDS (separate paid tier), each deferred capability has an Analog fallback. Discipline: don't hand-roll graph algorithms (`# GDS-FUTURE:`/`PLANNED_METHODS`), don't build a speculative port now. Grounded in live-graph density measurement** |
| **[ADR-081: Journals Companion — Authored Instructions + UserContext Grounding](decisions/ADR-081-journals-companion-authored-instructions-and-grounding.md)** | **Accepted (LLM-root arc Phase 3, Journals MVP slice): the typed companion gets a real authored instruction home — committed default floor per JournalMode + optional founder-local override (D1=B) — and real `UnifiedUserContext.build()` grounding via a curated projection replacing the six-titles digest (D2=B). Two DISTINCT instruction sets per surface, NO cross-chat memory; shared substrate = UserContext + shelf behind the privacy wall. DNWF triad = spirit not stages (typed chat stays free-form). PR1 instruction home → PR2 grounding** |
| **[ADR-082: Askesis Instruction Home — Authored Pedagogy Floors + Grounding Projection](decisions/ADR-082-askesis-instruction-home-and-grounding.md)** | **Accepted (LLM-root arc, Askesis slice — reuses ADR-081's authoring approach + grounding seam, never the content): founder-local override at the registry chokepoint (`data/instructions/{template_id}.md`; containment guard lifted to `core/utils/instruction_files.py`) + authored `askesis_stance` fragment heading BOTH answer branches (guided AND facet/context-aware — parity is D3); `render_askesis_grounding` projection with per-turn `build_rich()` kept (D2 → PR2); the 4 unrendered templates staged as `PLANNED_TEMPLATES` (D4, `askesis_ku_bridge` first candidate). Durable sessions + shelf access-rights = future discussions. PR1 instruction home → PR2 grounding** |
| **[ADR-083: Qwen + BGE End-State — Committed Destination, Staged Convergence](decisions/ADR-083-qwen-bge-end-state-commitment.md)** | **Accepted: upgrades ADR-081's north star to a committed destination — Qwen chat + BGE embeddings end-state, interim OpenAI embeddings + OpenAI/Anthropic switcher fully supported. BGE target = BGE-M3 (8k context kills the chunk-truncation conflict; same 1024-dim dense). Design rules bind new code: 1024 dims frozen (`EmbeddingGeometry.DIMENSION`), embedding-text budgets judged against the end-state window, no new OpenAI-required assumptions outside the two factories, provider swaps only at the chokepoints. Roadmap: Arc 1 BGE-M3 readiness → Arc 2 Qwen in the switcher (`qwen*` route, hosted serving) → Arc 3 embeddings switcher + v4 cutover (postponed)** |
| **[ADR-084: Compact Font-Size Tokens (Micro Type Scale)](decisions/ADR-084-compact-font-size-tokens.md)** | **Accepted, implemented (PR1–PR6, audit strict since 2026-08-15): named compact type-scale tokens in `input.css` `@theme inline` replace 289 arbitrary Tailwind font sizes; font-size only, no line-height companions; audit guardrail blocks new arbitrary values. Extends ADR-071** |
| **[ADR-085: Ownership Read-Enforcement Contract](decisions/ADR-085-ownership-read-enforcement-contract.md)** | **Accepted (ownership bundle, 2026-08-21): every read on behalf of a user passes one of TWO chokepoints — `build_search_visibility_clause()` (search strategies + `get_visible_to_user` by-UID) or route-mediated `verify_ownership`; `get_visible_to_user` promoted to THE audience-aware service-to-service by-UID read; bare `get()` legal only as internal mechanics (post-verification / not-on-behalf-of-a-user / PUBLIC); NO third audience-policy mechanism ever (self-anchored user-context reads carry an every-projection-tied-to-the-anchor obligation instead). Carries the G1–G7 read-side gap census as the closure worklist** |
| **[ADR-086: Universal `:OWNS` Ratified; Attendance Is `ATTENDS`](decisions/ADR-086-universal-owns-and-attends-attendance.md)** | **Accepted (ownership bundle, 2026-08-21): `(User)-[:OWNS]->` is THE ownership edge — four write doors named, `user_uid == :OWNS` owner invariant ratified (property-scoped reads sound); the paper per-domain `HAS_*`/`MADE_REFLECTION` family + registry `ownership_relationship` field + gravity writers collapse (supersedes ADR-026's ownership declaration). Full Events attendance DESIGN, staged not wired: `ATTENDS {joined_at, role, added_by, status}` with invite→accept consent state machine, actor from auth layer, creator auto-attends, future `OWNER_OR_ATTENDEE` visibility, GDPR semantics (organizer-deletion question parked by name). `User.uid` uniqueness constraint ruled in** |
| **[ADR-087: Status-Guarded Conditional Writes](decisions/ADR-087-status-guarded-conditional-writes.md)** | **Accepted (conditional-write arc, 2026-08-24): every status write was a read-then-write whose read took no lock — measured 39/40 trials produced 2-4 concurrent writers each believing they performed the first completion, which is how a complete serialized after a reopen left `status=completed` with no `completion_date`. New `update_with_status_guard` on `_CrudMixin` (declared on `CrudOperations[T]`): the statement takes the node's write-lock BEFORE reading the prior (ADR-030's sentinel, single-statement form), applies `StatusWriteGuard`'s prior-conditional patches, and RETURNS the prior — services derive `is_completion_transition` / `is_reopen_transition` / **exact `is_repeat`** from it with the same pure helpers. Guarded-out is `Result.ok(applied=False)`, not-found is the error; auto-commit, no managed retry (at-most-once). `BaseService.update_status` deleted. Scoped OUT by name: counter races, non-status guards, edge CAS, Principles (prior-independent gate). today.js's request queue RETAINED — the primitive fixes each write's VERDICT, not the ORDER of two opposing requests** |
| [ADR-XXX: [Short Title of Decision]](decisions/ADR-TEMPLATE.md) | |

## Tools

*Developer tooling — scripts and automation for codebase maintenance*

| Document | Description |
|----------|-------------|
| **[Codebase Health Checks](tools/HEALTH_CHECKS.md)** | Dead modules, broken doc links, stale names, cross-refs (`./dev health`) |
| **[Bloat Detection](tools/BLOAT_DETECTION.md)** | AST-sound dead-event + dead-method detection, Vulture-backed (`./dev bloat`) |
| [Automatic Documentation Check](tools/AUTOMATIC_DOCS_CHECK.md) | Post-commit hook that suggests doc updates after code changes |
| [Knowledge-Health Gauge](tools/KNOWLEDGE_HEALTH.md) | Corpus-level knowledge-subgraph structural health, ADR-080 H1 (`./dev knowledge-health`) |

---

## User Guides

*Practical usage guides for SKUEL workflows and tools*

| Document | Description |
|----------|-------------|
| [Tasks User Guide](guides/TASKS_USER_GUIDE.md) | Full guide: create, sub-tasks, goal links, PS engagement, Obsidian round-trip |
| **[Documentation Freshness](user-guides/documentation-freshness.md)** | How SKUEL's three doc freshness systems work together (hooks + health checks + cross-refs) |
| **[Zone of Proximal Development](user-guides/zpd.md)** | How ZPD works — current zone, proximal zone, readiness scores, behavioral enrichment |
| **[Journal Privacy](user-guides/journal-privacy.md)** | Who can see journal entries, SKUEL's policy commitment, and field-level encryption roadmap |
| **[Context DSL Cheat-Sheet](user-guides/context-dsl-cheatsheet.md)** | Quick reference for @context() Activity Lines — context types, optional tags, full example |

---

## Guides

*Step-by-step implementation and migration guides*

| Document | Description |
|----------|-------------|
| **[GitHub Fundamentals - Local to Remote Workflow](guides/GITHUB_FUNDAMENTALS.md)** | |
| **[PR-Based Development Workflow](development/PR_WORKFLOW.md)** | |
| [Intelligence Route Factory - Usage Guide](guides/INTELLIGENCE_ROUTE_FACTORY_USAGE.md) | |
| [HTMX Version Standardization Guide](guides/HTMX_VERSION_STANDARDIZATION.md) | |
| [Protocol Implementation Guide](guides/PROTOCOL_IMPLEMENTATION_GUIDE.md) | |
| **[Curriculum Developer Guide](guides/CURRICULUM_DEVELOPER_GUIDE.md)** | |
| **[YAML Authoring Guide](guides/YAML_AUTHORING_GUIDE.md)** | |
| **[Tasks User Guide](guides/TASKS_USER_GUIDE.md)** | |
| **[Voice Journaling and Obsidian Guide](guides/VOICE_JOURNALING_AND_OBSIDIAN_GUIDE.md)** | |
| **[Vault Agent Guide](guides/VAULT_AGENT_GUIDE.md)** | |
| **[Linter Guide](guides/LINTER_GUIDE.md)** | |
| **[UV Package Manager Guide](guides/UV_GUIDE.md)** | |
| **[Troubleshooting Guide](TROUBLESHOOTING.md)** | |

## Deployment

*The one production path — droplet (app + Caddy) → AuraDB Free*

| Document | Description |
|----------|-------------|
| [Neo4j Setup Migration Summary](deployment/NEO4J_SETUP_MIGRATION_SUMMARY.md) | History of the deployment docs + the decision that collapsed three stages to one path |
| [Droplet Deployment Guide](deployment/DO_MIGRATION_GUIDE.md) | Deploying skuel.app: droplet stack, `./dev deploy`, operations runbook |
| [AuraDB Migration Guide](deployment/AURADB_MIGRATION_GUIDE.md) | Moving the graph data: local Docker Neo4j → AuraDB Free |

---

## Reference

*Templates, checklists, and reference materials*

| Document | Description |
|----------|-------------|
| [Code Review Checklist - Phase 7.3](reference/CODE_REVIEW_CHECKLIST.md) | |
| [Placeholder Parameter Index](reference/PLACEHOLDER_INDEX.md) | |
| [Protocol Definition Template](reference/templates/protocol_definition.md) | |
| [Protocol Reference Guide](reference/PROTOCOL_REFERENCE.md) | |
| [Search Models Reference](reference/models/SEARCH_MODELS.md) | |
| [Search Service Methods Reference](reference/SEARCH_SERVICE_METHODS.md) | |
| [Service Creation Template](reference/templates/service_creation.md) | |

## Intelligence

*AI features, roadmaps, and vision documents*

| Document | Description |
|----------|-------------|
| [Discovery Analytics Implementation Roadmap](roadmap/DISCOVERY_ANALYTICS_ROADMAP.md) | |
| [Canon — Book-as-Journaling-Companion](roadmap/canon-journaling-companion.md) | |

## Features

*Implemented features with complete documentation*

| Document | Description |
|----------|-------------|
| **[SEL Adaptive Curriculum](features/SEL_ADAPTIVE_CURRICULUM.md)** | |

## Migrations

*Database and code migration guides*

| Document | Description |
|----------|-------------|
| [**DomainConfig Migration Complete**](migrations/DOMAINCONFIG_MIGRATION_COMPLETE.md) | |
| [**BaseService Improvements 2026-01-29**](migrations/BASESERVICE_IMPROVEMENTS_2026-01-29.md) | |
| [Domain Route Config Migration - Phase 2](migrations/DOMAIN_ROUTE_CONFIG_MIGRATION_2026-01-24.md) | |
| **[Domain Route Config Migration - Phase 3](migrations/DOMAIN_ROUTE_CONFIG_MIGRATION_2026-02-03.md)** | |
| [Neo4j Label Standardization Migration Plan](migrations/NEO4J_LABEL_STANDARDIZATION.md) | |
| [Ports to Protocols Migration History](migrations/PORTS_TO_PROTOCOLS_MIGRATION.md) | |
| [Assignments Routes Refactoring](migrations/assignments-refactoring-2026-01-25.md) | |
| [Visualization Routes Refactoring](migrations/visualization-refactoring-2026-01-25.md) | |
| [Service Refactoring Analysis](migrations/service-refactoring-analysis-2026-01-25.md) | |
| [Service Layer Refactoring Complete](migrations/service-layer-refactoring-complete-2026-01-25.md) | |
| [Context Health Score Enum Improvement](migrations/health-score-enum-improvement-2026-01-25.md) | |
| **[Lateral Relationships Implementation Complete](migrations/LATERAL_RELATIONSHIPS_COMPLETE_2026-01-31.md)** | |
| [KU Route Naming Standardization](migrations/KU_ROUTE_NAMING_STANDARDIZATION_2026-02-02.md) | |
| **[UI Factory Signature Standardization](migrations/UI_FACTORY_SIGNATURE_STANDARDIZATION_2026-02-03.md)** | |
| **[SEL Routes UX Modernization](migrations/SEL_UX_MODERNIZATION_2026-02-03.md)** | |
| **[SEL Routes DomainRouteConfig Migration](migrations/SEL_ROUTES_MIGRATION_2026-02-03.md)** | |
| [Config-Driven Factories Migration](migrations/CONFIG_DRIVEN_FACTORIES_MIGRATION_2026-02-05.md) | |
| [Profile Hub Modernization](migrations/PROFILE_HUB_MODERNIZATION_2026-02-01.md) | |
| [Embedding Infrastructure Alignment](migrations/EMBEDDING_INFRASTRUCTURE_ALIGNMENT_2026-02-01.md) | |
| [Protocol Mixin Alignment Complete](migrations/PROTOCOL_MIXIN_ALIGNMENT_COMPLETE_2026-01-29.md) | |
| [Relationship Registry Rename](migrations/RELATIONSHIP_REGISTRY_RENAME_2026-02-08.md) | |
| **[Domain Backends Position 2 Complete](migrations/DOMAIN_BACKENDS_POSITION_2_COMPLETE_2026-03-01.md)** | |

## Roadmap

*Deferred work with explicit triggers and review schedule*

| Document | Description |
|----------|-------------|
| [The learning-aligned create verb](roadmap/learning-aligned-create-verb.md) | Ideas preserved from the deleted LearningAlignmentBridge create half: act-on-a-learning-recommendation and LP→calendar schedule, with the primitive/template build surface to use when either becomes a lived need; census of remaining dict-door creates (GoalTaskGenerator, HabitEventScheduler) |
| [BGE Embeddings Migration (ADR-083 Arc 3)](roadmap/bge-embeddings-migration.md) | Cutover from OpenAI to BGE-M3 embeddings: factory swap + `EMBEDDINGS_PROVIDER` env var, `EMBEDDING_VERSION` v3→v4, `HF_API_TOKEN`, batch re-embed; no index rebuild (both 1024-dim); independent of Arc 2 |
| [Deferred Work](roadmap/deferred-work.md) | Intelligence features and decision points deferred until data/business prerequisites exist |
| [Security Hardening — Deferred](roadmap/security-hardening-deferred.md) | The security hardening backlog — see its Priority Order table for current status (most items now shipped or closed) |
| [Teacher-Askesis Interface — Deferred](roadmap/teacher-askesis-interface-deferred.md) | Teacher view/adjust/annotate interface; requires ZPDService + Neo4j persistence first |
| **[Askesis Tool-Selection Queries — why not text2cypher](roadmap/askesis-tool-selection-queries.md)** | **Why SKUEL does not adopt `langchain-neo4j`'s `text2cypher` (`GraphCypherQAChain`) — multi-tenancy, SKUEL001/021, determinism — plus the design sketch for the safe alternative (LLM picks a vetted tool + typed args; `user_uid` injected server-side). Status: not scheduled. Read before proposing LLM-generated Cypher.** |

### Completed (`docs/roadmap/done/`)

*Finished plans, moved out of the live folder when nothing in them remained open (see CLAUDE.md § Documentation Architecture). Records, not work.*

| Document | Completed | Description |
|----------|-----------|-------------|
| [The Reopen Vault Surface](roadmap/done/reopen-vault-surface.md) | 2026-08-24 | Both PRs (#1151, #1152): `WriteResult.updates_applied` carries per-update outcomes so a minted 🆔 persists only when its own injection landed (fail-closed), and a task reopen un-checks its Obsidian line and strips the `✅` date — driven by a state predicate, never by `TaskReopened`, which stays published and deliberately unsubscribed |
| [The Ownership Bundle (ADR-085 / ADR-086)](roadmap/done/ownership-bundle.md) | 2026-08-21 | All 4 PRs (#1118–#1121): universal `:OWNS` ratified and the paper `HAS_*` family deleted, attendees retargeted onto `ATTENDS`, the read-side gap census G1–G7 closed, `DomainConfig.ownership_property` added for `Group`, and a `User.uid` uniqueness constraint applied to the live graph. The staged attendance wiring lives in [Deferred Work](roadmap/deferred-work.md) |
| [Completion Stamping → Cascade Idempotency → Conditional Writes](roadmap/done/completion-stamping-and-conditional-writes.md) | 2026-08-24 | Three chained arcs (#1122–#1125, #1126–#1136, #1145–#1150) from one truth-pass residue: canonical completion stamps replacing the mutable `updated_at` proxy, `TaskCompleted.is_repeat` for repeatable cascades, and ADR-087's `update_with_status_guard` — the lock-before-read primitive that made `is_repeat` exact. Vault inbound propagation stays parked in [Deferred Work](roadmap/deferred-work.md) |
| [`/search` Facet Redesign](roadmap/done/search-facet-redesign.md) | 2026-08-26 | All 6 PRs (#1155–#1160): `/search` is the 6 Activity Domains + Ku; Type dropdown, Nous-driven knowledge mode, and the NOUS + tag facet vocabularies scoped to what the page returns. LearningPaths ruled *navigated, not searched*. The one open obligation — profile-side search — lives in [Deferred Work](roadmap/deferred-work.md) |
| [ZPDService — Design & Architecture](roadmap/done/zpd-service-architecture.md) | 2026-03 | ZPDService + ZPDBackend architecture: ZPDAssessment, graph traversal, readiness scores, behavioral enrichment — implemented |
| [Semantic Analysis Implementation Roadmap](roadmap/done/SEMANTIC_ANALYSIS_ROADMAP.md) | 2026-07-10 | All three approved items shipped (#598–#600): concept-cluster chips, admin prereq suggestion queue, ZPD semantic feed; data-gated residue lives in [Deferred Work](roadmap/deferred-work.md) |
| [Resources/ Reference Library — Ingestion Roadmap](roadmap/done/resources-reference-library.md) | 2026-07 | Tier 1 pointing/citations shipped (#562–#566); Tier 2 superseded by the canon shelf; "point at the raw" graduated into CANON_CITATION_DESIGN.md |
| [Feedback-Loop UX — Design & Choices (Arc 1)](roadmap/done/feedback-loop-ux-arc.md) | 2026-08-01 | All 4 PRs (#902–#905): report-visibility on student `OWNS` (`ASSESSMENT_OF` deleted), needs-review single source, human report titles, Shared-With-Me context join, `/exchange` thread view |
| [Feedback-Loop UX — Design & Choices (Arc 2)](roadmap/done/feedback-loop-ux-arc2.md) | 2026-08-02 | All 3 PRs (#906–#908): GradeBook 3→1 per-exercise lines, waiting/source chips, teacher Waiting-for-resubmit queue view, Shared-With-Me filters + inbox identity |
| [Calendar Act-From Arc](roadmap/done/calendar-act-from-arc.md) | 2026-08-02 | All 7 PRs (#913–#917, #919, #920): truthful month grid, per-day habit completion, modal reschedule, day-lens + quick-add, source-aware defer |
| [UI Orchestration Expansion](roadmap/done/UI_ORCHESTRATION_EXPANSION_PLAN.md) | 2026-04 | All 10 orchestrators shipped and hardened; the pattern lives in UI_ORCHESTRATOR_PATTERN.md |
| [Conversation Neo4j Persistence](roadmap/done/conversation-neo4j-persistence-deferred.md) | 2026-07-13 | Resolved by ADR-078: persistence half shipped (stored-not-understood); pedagogical half rejected — do not implement its backend spec |
| [W-Series Docs/Skills Review](roadmap/done/w-series-docs-skills-review.md) | 2026-05-26 | Docs-only sweep from the W1 implementation thread, 9 files |
| [Typed Update Intents migration](roadmap/done/update-intents.md) | 2026-06-05 | ADR-066 phased execution: all six Activity Domains on frozen `*UpdateIntent`, base parameterized over `U`, every alternative deleted |
| [Calendar Periodic-Notes Arc](roadmap/done/calendar-periodic-notes-arc.md) | 2026-08-03 | All four PRs shipped the day the arc was confirmed |
| [Habit-Rhythm Arc](roadmap/done/habit-rhythm-arc.md) | 2026-08-04 | M1–M7 shipped (#927/#933/#934); open follow-ups extracted to [Deferred Work](roadmap/deferred-work.md) |
| [One Dependency Scanner (osv-scanner)](roadmap/done/dependency-scanner-consolidation.md) | 2026-08-07 | pip-audit + npm audit retired for one measured scanner over both lockfiles (#978) |
| [JS/Node Dependency Surface](roadmap/done/js-dependency-surface.md) | 2026-08-07 | The undici-incident review: all six decisions resolved (Renovate live, Node 24, accept mechanism via #978) |
| [Edge Ingestion Support](roadmap/done/edge-ingestion-support.md) | 2026-03-08 | Edge YAML files ingested as typed, evidence-bearing relationships; the three design questions ruled closed 2026-08-08 (shipped behavior is the decision) |
| [Goal Event-Handler Extraction](roadmap/done/event-handler-extraction-goals.md) | 2026-03-20 | GoalEventHandlerService with 3 handlers; GoalsRecommendationService deleted |
| [Activity Views Consolidation](roadmap/done/activity-views-consolidation.md) | 2026-04-10 | Patterns A and C complete; Pattern B (StatsBar) closed — not viable |
| [Cypher Seam Hard-Gate Options](roadmap/done/cypher-seam-hard-gate-options.md) | 2026-05-31 | Question superseded: the `arg-type` sweep made the NeoLabel/RelationshipName seam a hard CI gate; blast-radius analysis retained as history |
| [Learning Loop Cross-Domain Search](roadmap/done/learning-loop-cross-domain-search.md) | 2026-03 | Levels 1–3b all complete: graph-aware search for the loop entities + chain traversal |
| [Secrets Out of the Worktree](roadmap/done/secrets-out-of-worktree.md) | 2026-07 | Stages 1–3 shipped; OS keychain is the canonical store |
| [Journals Discussion-First — Design & Choices](roadmap/done/journals-discussion-first.md) | 2026-07-13 | The arc SoT: two doors converging into one grounded conversation; P1→P3 shipped (#627–#640); post-arc items live in [journals-discussion-deferred](roadmap/journals-discussion-deferred.md) |
| [Journals Discussion Storage P2](roadmap/done/journals-discussion-storage-p2.md) | 2026-07-13 | The stored substrate: ConversationSession/Turn + understanding wall; in-arc refinements all shipped (source-selection restore, deterministic titles, export) |
| [Journals Discussion Storage P3](roadmap/done/journals-discussion-storage-p3.md) | 2026-07-13 | Opt-in persistence reconciliation: ephemeral default + Save on both doors; PR1–PR3 shipped, arc complete |
| [Path-Keyed Identity for uid-less Vault UserEntries](roadmap/done/uidless-vault-entry-identity-upsert.md) | 2026-07-12 | The contract the UserEntry ingest door cites: path = identity, the three reuse gates, private-flip chunk retraction (#616) |
| [Content-Hash Move Detection](roadmap/done/hash-assisted-move-detection.md) | 2026-07-12 | Renames preserve identity: exact-hash then mutual-best similarity over the residual; T=0.8 empirics and the both-sides candidacy gates (#617, #618) |
| [MOC + Knowledge Channel — Design Rulings](roadmap/done/moc-knowledge-channel-design-notes.md) | 2026-07-05 | Vault map, MOC as emergent identity, and the Phase 0 vault-exercise-channel rulings R1–R7 (#506–#511) |

## Examples

*Demos and example workflows*

| Document | Description |
|----------|-------------|
| [Mindfulness 101 Demo](examples/mindfulness-101-demo.md) | |

## Technical Debt

*Known limitations and technical debt*

| Document | Description |
|----------|-------------|
| [Analytics Untyped-Seam Defects](technical_debt/ANALYTICS_UNTYPED_SEAM_DEFECTS.md) | |
| [LifePath Alignment Debt](technical_debt/LIFEPATH_ALIGNMENT_DEBT.md) | OPEN — habits score zero in every dimension; a designated path's label and `entity_type` disagree |
| [MyPy Limitations in Universal Backend](technical_debt/MYPY_BACKEND_LIMITATIONS.md) | |
| [Return Value Type Errors Analysis](technical_debt/RETURN_VALUE_ERRORS_ANALYSIS.md) | |

## Top-Level

*Top-level documentation files*

| Document | Description |
|----------|-------------|
| [Claude Quick Start Guide](CLAUDE_QUICKSTART.md) | |
| [SKUEL Documentation Hub](README.md) | |

---

## Coverage

This index is curated, not exhaustive: just under a third of the markdown under `docs/` is not
listed, spread across every section. A doc absent from a table is not necessarily absent from
the tree.

For what is actually on disk, ask the tree rather than this file:

```bash
find docs -name '*.md' | wc -l
```