# SKUEL — Claude Code Project Instructions

Quick-reference for working in this codebase: terse givens, each pointing (`**See:**`) to the authoritative doc for detail. Sections are grouped under themed banners below. Editorial rule: keep sections short — prose and examples live in the linked docs, not here (see [Documentation Architecture](#documentation-architecture)).

## Working Conventions & Development Philosophy

- We use uv for package management and for running files.
- **Preferred document format: Markdown (`.md`).** Downloadable content (exercises, worksheets, reports) is served as `.md` so users can open, edit, and respond in any text editor or Obsidian. PDF is reserved for finance (invoices). Never introduce a new binary document format when `.md` will do.

### Code Responsibility Philosophy

**If you see a problem, fix it.** Don't look the other way. Take responsibility to make the code better.

When working in a file or area of the codebase, address problems you encounter — wrong comments, stale docs, security issues, DRY violations, naming inconsistencies. SKUEL does not reward passive observation of bad code.

**This is not a license for scope creep.** Fix what is genuinely wrong. Don't redesign systems you were not asked to touch. The distinction: a bug you notice while working nearby should be fixed; a large refactor you think would be nice requires a deliberate decision.

### One Path Forward - Core Development Philosophy

**SKUEL does NOT maintain backward compatibility.** When a better pattern emerges, the old pattern is removed entirely. No legacy wrappers, no deprecation periods, no alternative paths. Update all call sites immediately. Dead code is deleted, not archived.

**Abandoned ≠ staged:** deliberately staged-but-unwired work is NOT dead code — register it in the bloat detector's PLANNED tier (`PLANNED_EVENTS`/`PLANNED_METHODS`/`PLANNED_TEMPLATES` in `scripts/detect_bloat.py`) as a visible completion backlog. One Path Forward deletes the abandoned, never the staged.

**Design Philosophy:** Type errors are teachers, showing us where components don't flow together properly. When errors appear, investigate the fundamental design first rather than working around with quick fixes.

**See:** `/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md`

### Analog-to-Digital Development Model

**Core Principle:** "Plain English in, working code out"

Explicit human-AI partnership: the human provides intent in plain language, the AI provides architectural judgment and pattern consistency. The Activity DSL (`@context(task)`, `@when()`, `@priority()`) is its purest expression — near-natural language parsed into typed structures. Plain-English domain descriptions and ADRs are the authoritative specification; the code is the translation, not the source of truth.

**See:** `/docs/dsl/DSL_SPECIFICATION.md`

### Analog + Digital Runtime Architecture

**Core Principle:** "The Analog layer is not a degraded version of the Digital layer — it is the foundation"

SKUEL separates runtime into two layers. The **Analog layer** (graph structure, CRUD, ingestion, keyword search, analytics, user context) is complete on its own — fully functional at $0 with no API keys. The **Digital layer** (embeddings, vector search, LLM feedback, Askesis) enhances the Analog layer with machine understanding. Toggle with `INTELLIGENCE_TIER=core|full` in `.env`.

**See:** `/docs/architecture/ANALOG_DIGITAL_ARCHITECTURE.md`, `/docs/architecture/GRACEFUL_DEGRADATION_ARCHITECTURE.md`

### Fail-Fast Dependency Philosophy

**Core Principle:** "All dependencies are REQUIRED - no graceful degradation"

**Required at bootstrap:** Neo4j (always). OpenAI and Deepgram are FULL-tier only — not read in CORE mode. **Only 2 valid `None` cases:** True circular dependencies, unimplemented features (explicit TODOs).

### Knowledge Substance Philosophy

**Core Principle:** "Applied knowledge, not pure theory"

SKUEL measures knowledge by how it's LIVED. Substance accrues from lived activity across Habits, UserEntry (grounded knowledge/je_pro entries — explicit `@ku()` refs via EXTRACT_ACTIVITIES ADR-069 + vector grounding via `EntryGroundingService`; two writers, one `KnowledgeReflectedInEntry` event), Choices, Principles, Events, and Tasks — each with a per-contribution weight and a per-domain cap. Total capped at 1.0.

**See:** `/docs/architecture/knowledge_substance_philosophy.md`

## Domain Model & Content

### Entity and Ku

**Core Principle:** "Entity is the universal base. Ku is one type of Entity."

`Entity` is the base frozen dataclass for all 25 domain types. The `entity_type` field discriminates which kind of entity it is. The `parent_entity_uid` field tracks derivation chains.

- **PathStep** (`EntityType.PATH_STEP`, extends `Curriculum`) — THE curriculum content entity. Composes Kus into learning content and sits within LearningPaths. Services in `core/services/ps/`. Facade: `PsService` in `core/services/ps_service.py`.
- **Ku** (`EntityType.KU`, extends `Entity`) — atomic knowledge unit. Lightweight ontology/reference node. Services in `core/services/ku/`.
- **Exercise** (`EntityType.EXERCISE`, extends `Curriculum`) — the instruction template that closes the learning loop. Four scopes: `PERSONAL` (user's AI-feedback template; optional PathStep anchor dual-writes `Exercise.path_step_uid` + the `HAS_EXERCISE` edge), `ASSIGNED` (teacher → group, ADR-040), `ASSESSMENT` (formal test + scoring rubric), `CURRICULUM` (content-vault-authored shared content, no user owner, not API-creatable). Service: `ExerciseService` in `core/services/exercises/exercise_service.py`.
- **Composition:** `(PathStep)-[:USES_KU]->(Ku)` — PathSteps compose atomic Kus into coherent learning content. `(PathStep)-[:HAS_EXERCISE]->(Exercise)` — PathSteps anchor PERSONAL exercises.
- **Learning loop (4 phases):** Exercise → UserEntry → EntryReport → RevisedExercise → UserEntry → ... The PathStep detail page (`/explore/ps/{uid}`) surfaces the loop — HTMX-loads exercises (with status), entries, and feedback via `/learning-loop/ps/{ps_uid}/*` fragments.
- **Knowledge principle:** PathStep IS knowledge. Exercise is APPLIED knowledge — subordinate to PathStep, not a peer. This hierarchy mirrors `Goal.fulfills_goal_uid`: `Exercise.path_step_uid` is a hierarchy-membership property (persisted at creation, dual-written with the `HAS_EXERCISE` edge), not a scoring/enrichment field. `EntityType.EXERCISE.is_applied_knowledge()` → `True`; `EntityType.LEARNING_PATH.is_curriculum_structure()` → `True`. **See:** `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md`

### SKUEL's 25 EntityTypes + 5 Cross-Cutting Systems

**Core Principle:** "Everything flows toward the life path"

**Two lenses (ADR-055):** Subsystems (7 subsystems × 3 sections) vs. 3-Layer (Curriculum → Action → Feedback). The **5 Cross-Cutting Systems** (UserContext, Search, Calendar, Askesis, Messaging) are infrastructure orthogonal to both lenses.

**The 25 EntityType values** cluster as: Activity (6: Task, Goal, Habit, Event, Choice, Principle), Activity Templates (6: TaskTemplate, GoalTemplate, HabitTemplate, EventTemplate, ChoiceTemplate, PrincipleTemplate — PS-owned, spawn instances on engagement), Curriculum (4: Ku, PathStep, LearningPath, Exercise), Forms (2: FormTemplate, FormSubmission), Learning loop (4: UserEntry, EntryReport, ActivityReport, Interaction), Other (3: RevisedExercise, LifePath, Resource).

**Not EntityTypes:** MOC is emergent (any Entity with ORGANIZES edges). Group lives in `NonKuDomain` (ADR-053). Finance is a Firefly III sidecar (ADR-052), admin-only.

**Service architecture:** `UniversalNeo4jBackend[T]` → `{Domain}Service` facade → sub-services. `.core` / `.search` / `.intelligence` / `.ai` are the *common* slots, not the whole set — `PsService` has 14, `HabitsService` 13, `AnalyticsService` none of the four. Read the facade's `__init__`; calling a sub-service from a caller is the documented API, with two narrow exceptions. **See:** `/docs/architecture/SERVICE_TOPOLOGY.md § When a caller may reach a sub-service`

**See:** `/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md` (full table, traits, UID formats), `/docs/architecture/SEVEN_SUBSYSTEMS.md`, `/docs/architecture/THREE_LAYER_LENS.md`, `/docs/architecture/ASKESIS_PEDAGOGICAL_ARCHITECTURE.md`, `/docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md`

### Curriculum Grouping Patterns

| Pattern | UID authored (vault) → stored (graph) | Topology | Metaphor |
|---------|-----------|----------|----------|
| Ku | `ku:{ns}:{slug}` → `ku.{ns}.{slug}` (API-generated: `ku_{slug}_{random}`) | Atom | A single concept/fact |
| PS | `ps:{namespace}:{slug}` → `ps.{namespace}.{slug}` | Content Unit | THE curriculum content entity (composes Kus) |
| LP | `lp:{namespace}:{slug}` → `lp.{namespace}.{slug}` | Path | An ordered sequence of path steps |

**Colon → dot normalization:** ingestion rewrites `:` → `.` in every UID (`normalize_uid`, `core/services/ingestion/preparer.py` — entity `uid:`, rel-config fields, edge `from`/`to`). Vault files author colons; the graph stores dots. Never compare file↔graph UIDs raw.

**Two Paths to Knowledge:** PS Path (structured, linear) and ORGANIZES Path (unstructured, graph, learner-directed). MOC is emergent identity — any Entity with ORGANIZES relationships. Authoring surface: `moc: true` frontmatter on any ingestible file → body links become `ORGANIZES {order}` edges (dangling links: silent in personal vaults, warned in content vault). **See:** `/docs/patterns/UNIFIED_INGESTION_GUIDE.md` § MOC files.

**Ku UID is flat & opaque** — hierarchy lives in `(parent)-[:ORGANIZES {order, importance}]->(child)` edges (multiple parents allowed), not in the UID. Two sanctioned forms — authored `ku.{ns}.{slug}` (vault) and generated `ku_{slug}_{random}` (API) — are BOTH valid; **never sniff type from the prefix** (spelling is provenance, not type information; determine entity kind by label/`entity_type`/edge).

**See:** `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md`, `/docs/decisions/ADR-013-ku-uid-flat-identity.md`, `/docs/patterns/UNIVERSAL_HIERARCHICAL_PATTERN.md`

### Content Origin Tiers

| Tier | ContentOrigin | EntityTypes | Description |
|------|--------------|---------|-------------|
| A | `CURATED` | Resource | Admin-curated content |
| B | `CURRICULUM` | Curriculum, PS, LP | Curriculum structure |
| C | `USER_CREATED` | Activities, UserEntry, LifePath | User-generated |
| D | `REPORT` | ActivityReport, EntryReport | Analysis/reports |

`ContentScope` controls access, `ContentOrigin` classifies purpose. Derived from `EntityType`.

### Content Sharing

**Core Principle:** "Three-level visibility with relationship-based access control"

**Visibility:** PRIVATE (default) → SHARED (SHARES_WITH relationship) → TEAM (group-scoped) → PUBLIC (portfolio)

**Three Sharing Modes:** Manual sharing, Assignment auto-sharing (ADR-040), Group sharing (SHARED_WITH_GROUP)

**Service:** `from core.services.sharing import UnifiedSharingService` — entity-agnostic, methods: `share()`, `check_access()`, `set_visibility()`, group sharing.

**Teacher Review:** `TeacherReviewService` — `get_review_queue()`, `submit_report()`, `request_revision()`, `approve_report()`

**Graph:** `(user)-[:SHARES_WITH {shared_at, role, share_version}]->(entity)`, `(entity)-[:SHARED_WITH_GROUP]->(group)`

**See:** `/docs/patterns/SHARING_PATTERNS.md`, `/docs/decisions/ADR-038-content-sharing-model.md`, `/docs/decisions/ADR-040-teacher-exercise-workflow.md`

### Naming Conventions

- **Files:** Names must reflect function. Rename randomly-generated plan file names immediately.
- **Parameters:** Underscore prefix (`_filters`, `_ctx`) marks a placeholder for future implementation.
- **Entities / edges / variants:** EntityType = noun, Relationship = verb, Variant = enum field. **See:** `/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md § Naming Convention`.
- **Emission rule:** aliases (`ps`, `lp`) are input-only — `from_string()` resolves them at the boundary; every machine channel (payloads, stamps, option values) speaks canonical enum values. Route segments (`/explore/ps/`) are naming, not entity_type values. **See:** `/docs/architecture/ENUM_ARCHITECTURE.md § Canonical Values vs Aliases`.

## Type System & Enums

### Type System

**Core Principle:** "Pydantic at the edges, pure Python at the core; a type error from MyPy reveals a real design problem"

**Three tiers:** Pydantic (external validation) → DTOs (data movement) → frozen dataclasses (core domain).

**Domain-First Model Hierarchy:**
```
Entity (~18 fields: uid, entity_type, title, description, status, tags, ...)
+-- UserOwnedEntity(Entity) — Task, Goal, Habit, Event, Choice, Principle, LifePath, ActivityReport, UserEntry, EntryReport
+-- Ku(Entity) — atomic knowledge unit (nous, aliases, sel_category; former namespace/ku_category/source fully removed 2026-07-06)
+-- Curriculum(Entity) +21 fields → PathStep, LearningPath, Exercise
+-- Resource(Entity) +7 fields (Curated content)
```
DTOs mirror the hierarchy: `EntityDTO → UserOwnedDTO, KuDTO, CurriculumDTO → PathStepDTO, ResourceDTO`

**Key enums:** `EntityType` (25 values), `EntityStatus` (14 values) — `entity_enums.py`. **Neo4j Multi-Label:** `:Entity` (universal) + domain label (`:Task`, `:Goal`, etc.). Backend uses `base_label=NeoLabel.ENTITY`.

**Enum-Enforced Boundaries:** `UserRole`, `ExerciseScope`, `SubmissionModality`, `EntityStatus`, `FeedbackCategory`, `MasteryImpact`, `Pipeline`, `ReportSource`, `Visibility`, `EnrichmentMode` — zero raw string comparisons.

**Search Protocol Generics:** All 6 `DomainSearchOperations` extensions parameterized with domain model type (`Goal`, `Event`, etc.), not `Entity`.

**Type aliases** (`core/models/type_hints.py`): `Neo4jProperties`, `FilterParams`, `RelationshipMetadata`. **Protocol return TypedDicts** (`core/ports/query_types.py`): all domain stats, system health, intelligence outputs — handlers return `Result[FT]` (fragments), `Result[Goal]` (models), or `Response` (redirects). `Result[Any]` in a handler is a regression.

**FastHTML boundary** (no `py.typed`): `RouteDecorator`/`FastHTMLApp`/`Request` protocols for signatures; `Result[FT]` for fragment returns; `*c: Any, **kwargs: Any` inside FT factories = `# boundary: fasthtml-elements`; ASGI plumbing = `# boundary: fasthtml-app`.

**`Any` policy:** A = eliminate, B = use specific type (e.g. `Neo4jProperties`), C = permanent boundary (`# boundary:` comment). The rule: "`Any` must mean *genuinely heterogeneous*."

**See:** `docs/architecture/TYPE_SAFETY_DESIGN_PHILOSOPHY.md`, `docs/patterns/TYPE_SAFETY_OVERVIEW.md`, `docs/patterns/ANY_USAGE_POLICY.md`, `/docs/patterns/three_tier_type_system.md`, `/docs/patterns/MYPY_TYPE_SAFETY_PATTERNS.md`

### Dynamic Enum Pattern

**Core Principle:** "Enums define behavior, services consume it"

Presentation logic lives inside enum methods (e.g. `Priority.get_color()`, `EntityStatus.is_terminal()`, `ContextHealthScore.get_numeric()`). Magic numbers live in `/core/constants.py`. Consolidated enums in `/core/models/enums/` — one file per domain; core discriminators in `entity_enums.py`.

**See:** `/docs/architecture/ENUM_ARCHITECTURE.md`, `/docs/architecture/PRIORITY_CONFIDENCE_ARCHITECTURE.md`

### Activity DSL & Domain Enums

`EntityType` (25 values) covers multi-label `:Entity` Neo4j nodes; `NonKuDomain` (FINANCE, GROUP, CALENDAR, LEARNING) covers the 4 non-Entity domains. Both expose `from_string()` with alias support (e.g. `"knowledge"` → `EntityType.KU`) — aliases are input-only (see [Naming Conventions](#naming-conventions) § Emission rule).

**See:** `/docs/dsl/DSL_SPECIFICATION.md`, `/docs/dsl/DSL_USAGE_GUIDE.md`

## Services, Backends & Events

### Protocol-Based Architecture

**Core Principle:** "Right type at the right boundary — concrete for facades, protocol for thin services"

**Protocol Location:** `core/ports/`. Two layers with distinct suffixes:
- **`*BackendOperations`** — type `self.backend` inside services
- **`*Operations`** — route-facing API that thin services expose

The table below is about **how a route refers to the service** — not about what the service types `self.backend` against:

| Tier | Services | Type a route uses | Why |
|------|----------|-----------|-----|
| **Facade** | Tasks, Goals, Habits, Events, Choices, Principles, KU, PS, LP | Concrete class | Facade IS the contract (~50 delegation methods) |
| **Thin/ISP** | Groups, UserEntry, Sharing, etc. | ISP protocol | Routes use a narrow slice; protocol makes it explicit |

**A facade being concrete to its callers does not license a concrete `self.backend`.** Both tiers type `self.backend` against a `core/ports` protocol; SKUEL023 enforces it **unconditionally** — the facade allowlist that once parked KU/PS/LP and then UserService/UserContextBuilder/InsightStore was emptied and deleted in July 2026. There is no exempt path in `core/`.

**Trap:** same root word at both layers — verify the layer before retyping `self.backend` against an `*Operations` protocol; if service-layer and backend-layer method names diverge, you need a `*BackendOperations` protocol.

**See:** `/docs/patterns/protocol_architecture.md`, `/docs/patterns/BACKEND_OPERATIONS_ISP.md`

### Generic Programming Patterns

**Core Principle:** "One generic backend serves all 25 entity types"

Generic backend `UniversalNeo4jBackend[T]` (T constrained by `DomainModelProtocol`); generic service base `BaseService[Op, T]` (Op=protocol, T=domain model); generic type aliases in `core/models/type_hints.py` — `Validator[T]`, `EntityFilter[T]`, `Scorer[T]`.

**See:** `docs/patterns/TYPE_SAFETY_OVERVIEW.md`, `/docs/patterns/query_architecture.md`

### BaseService Architecture

**6 Mixins:** ConversionHelpers, CRUD, Search, Relationships, TimeQuery, Context.

**6 Activity Domains:** Tasks, Goals, Habits, Events, Choices, Principles. All use facade pattern with explicit `async def` delegation methods. Factory: `create_common_sub_services()` (supports `skip` parameter for facades that override sub-services). Active sub-services: `.core`, `.search`, `.ai` (optional, FULL tier). **Shared:** `ActivityKnowledgeIntelligenceService` (`core/services/knowledge/`) — 4 delegation methods via `KnowledgeIntelligenceDelegationMixin`, inherited by all 6 facades.

**Harmony without over-generalization:** All 6 domains share the same 7 common sub-services (`core`, `search`, `relationships`, `intelligence`, `event_handler`, `learning`, `knowledge_intelligence`) — no domain opts out. Domain-specific sub-services (Habits `completions`, Events `habit_integration`, Principles `alignment`) preserve uniqueness inside it.

**Decomposition rule:** line counts guide, coherence determines. >350 lines (intelligence) / >700 lines (facade) are advisory signals that trigger a merit check — extract only on 4+ coherent methods whose extraction genuinely improves the host; "over the threshold but coherent" is a valid, documented end state (see the doc's Deliberately Long registry). **Floor:** inline back when a mixin is <250 lines, single-consumer, and mostly delegates to one dependency — don't extract just to satisfy a line count. **See:** `/docs/patterns/SERVICE_DECOMPOSITION_RULE.md`

**Essential Docs:** `/docs/guides/BASESERVICE_QUICK_START.md`, `/docs/reference/SUB_SERVICE_CATALOG.md`, `/docs/reference/BASESERVICE_METHOD_INDEX.md`, `/docs/architecture/SERVICE_TOPOLOGY.md`

### 100% Dynamic Backend Pattern

**Core Principle:** "The plant grows on the lattice"

**4 layers:** `*Operations` protocol → `*Backend` subclass → `{Domain}Service` facade → sub-services.

Domain backends live in clustered files under `adapters/persistence/neo4j/backends/` (activity, curriculum, exercise, user_entry, sharing, forms, collab, misc) and standalone files for cross-cutting backends. Import from the cluster file directly.

**Rules:** Domain-specific Cypher belongs on the domain backend; cross-domain aggregation stays in services; services call `self.backend.method_name()` (never inline `execute_query()`). `cascade=True` for Activity Domains.

**`UniversalNeo4jBackend` is the hexagonal boundary** — Neo4j is a committed architectural choice (ADR-044), not a swappable adapter.

**See:** `/docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md` (full backend inventory + mixin layout)

### Infrastructure Helpers

**Location:** `/core/services/infrastructure/`

| Helper | Purpose |
|--------|---------|
| `PrerequisiteChecker` | `check_prerequisites()` → `PrerequisiteResult` (score, is_ready, missing_knowledge, blocking_reasons); `build_learning_requirements()` → `LearningRequirements`. **See:** `/docs/patterns/PREREQUISITE_CHECKER_PATTERN.md` |
| `LearningAlignmentBridge` | LP integration for any domain |
| `SemanticRelationshipLinker` | Semantic relationship ops |

### Async/Sync Design Pattern

**Rule:** async for I/O (database, service calls), sync for computation and data conversion. If you need `await` inside the function, make it `async def`. Otherwise use `def`.

### Event-Driven Architecture

**Core Principle:** "Events over dependencies"

**Event Naming:** `{domain}.{action}` (e.g., `task.completed`, `goal.achieved`). **Location:** `/core/events/`

**Auto-timestamp:** `BaseEvent.occurred_at` defaults to `datetime.now()` via `kw_only` field — never pass it manually. Override only for tests or event replay.

**Publish:** `await publish_event(self.event_bus, TaskCompleted(task_uid=uid, user_uid=user_uid), self.logger)` — import from `core.events.utils`.

## Data, Persistence & Search

### Neo4j Infrastructure

**Core Principle:** "One Path Forward - local Docker for dev, droplet + AuraDB Free for production"

**Local (dev):** Docker-based Neo4j (`bolt://localhost:7687`, `infrastructure/docker-compose.yml`). Plugin: APOC (meta only). APOC scoped to `apoc.meta.*` — domain services use pure Cypher (SKUEL001). Embeddings via OpenAI `text-embedding-3-small` @1024 dims (Python-side, no Neo4j plugin; provider chokepoint `create_embedding_client()` — ADR-068). Committed end-state: Qwen chat + BGE-M3 embeddings (ADR-083 — dims frozen at `EmbeddingGeometry.DIMENSION`; no new OpenAI-required assumptions outside the two provider factories).

**Production:** one droplet running `skuel-app` + Caddy (auto-TLS) via `docker-compose.production.yml`, talking to **Neo4j AuraDB Free** over `neo4j+s://` (boot refuses plaintext schemes in production). Deploy via `./dev deploy` (rsync + build + `/health/ready` gate). The former intermediate stage (App Platform + Neo4j droplet) was skipped — see `NEO4J_SETUP_MIGRATION_SUMMARY.md`.

**Code is environment-agnostic** — only `.env` configuration changes between local and production.

**Per-query server-side timeout:** every query through the shared driver carries a server-side per-tx ceiling (`NEO4J_TRANSACTION_TIMEOUT`, default 120s; `0`=unbounded). Wired at compose via `TimedDriver` — single chokepoint, no call-site edits. Bulk ingestion wraps to 600s; startup DDL stays untimed (`Neo4jSchemaManager(raw_driver)` carve-out). Override per op with `neo4j_query_timeout(s)` / `unbounded_neo4j_query_timeout()`.

**Schema-change monitoring (opt-in, default OFF):** `SchemaChangeDetector` fingerprints the live schema and invalidates query-optimization caches on drift. On-demand via `Neo4jAdapter.check_schema_changes()`; or wire a background poll at startup with `NEO4J_SCHEMA_MONITORING=true` (+ `NEO4J_SCHEMA_MONITORING_INTERVAL`, default 900s, validated ≥1). Tier-independent (not `INTELLIGENCE_TIER`-gated) — off by default keeps the CORE-tier "no background workers" guarantee. **See:** neo4j-cypher-patterns skill § 7.

**Server tuning (memory, JVM, Vector API):** all server config is `NEO4J_*` env vars on the `neo4j` service in the base compose `../infrastructure/docker-compose.yml` (repo root; the app `docker-compose.yml` extends it, overriding only deltas). The Java Vector API (SIMD) is enabled via `NEO4J_server_jvm_additional=--add-modules jdk.incubator.vector` — required for optimal performance of the 7 vector indexes (Entity/ContentChunk/ReferenceChunk/Goal/Task/Ku/PathStep embeddings); `2026.x` warns without it.

**AuraDB three-horizon strategy (ADR-080):** committed to AuraDB Free soon; Neo4j Graph Data Science (GDS/AuraDS) deliberately deferred (density-gated; a Digital-layer enhancer, not part of the $0 core — GDS = pre-built graph algorithms, don't hand-roll). **Horizon 0 (shipped):** telemetry retention — `./dev telemetry-retention [--days N] [--dry-run]`, one-shot batched prune of unbounded-growth system telemetry (AuthEvent/SearchEvent/Interaction/stale VIEWED; saved `:ConversationSession` discussions EXCLUDED) keeps the graph under the Free node cap; startup connect-retry — `connect_with_retry` chokepoint in `Neo4jAdapter.connect` tolerates a paused/waking instance. `AURA-TEMPORARY:` marks self-host-only knobs that drop on migration. **Horizon 1:** author edge-first + the knowledge-health gauge (see Analytics below). Retention/connect-retry preserve the CORE "no background workers" guarantee (one-shot, not a loop).

**See:** `/docs/patterns/NEO4J_SERVER_TUNING.md`, `/docs/patterns/NEO4J_QUERY_TIMEOUT.md`, `/docs/decisions/ADR-064-neo4j-per-query-timeout.md`, `/docs/decisions/ADR-080-auradb-three-horizon-strategy.md`, `/docs/deployment/DO_MIGRATION_GUIDE.md`, `/docs/deployment/AURADB_MIGRATION_GUIDE.md`, `/docs/decisions/ADR-068-openai-embeddings-now-bge-later.md`

### Data Flow Architecture

```
Content to Storage:
Markdown → UnifiedIngestionService → KnowledgeUnit → GraphNode → Neo4j

Request Processing:
HTTP → FastHTML Route → Pydantic → Service → Domain → Repository → Neo4j
```

### Search & Query Architecture

**Core Principle:** "SearchRouter is THE single path for all external search access"

**Three Query Systems:** UnifiedQueryBuilder (default), QueryBuilder (optimization), CypherGenerator (pure Cypher).

**Searchable Domains (SearchRouter):** 12 — Task, Goal, Habit, Event, Choice, Principle, Ku, PS, LP, Exercise, RevisedExercise, UserEntry. UserEntry search REQUIRES `user_uid` (privacy line — refused unscoped; excluded from cross-domain sweeps). Forms search via their own services (see SEARCH_ARCHITECTURE § Searchable Entity Types).

**Ownership scoping:** every strategy (text/tags/graph/faceted) is scoped by the domain's `SearchVisibility` declaration on DomainConfig — `OWNER_ONLY` (Activities, UserEntry), `PUBLIC` (PS/LP/KU), `SCOPE_AWARE` (Exercise: curriculum visible to all, owned scopes via OWNS/SHARES_WITH/group membership). One Cypher composition point: `build_search_visibility_clause()`. **See:** SEARCH_ARCHITECTURE § Ownership Scoping.

**DomainConfig** is THE single source of truth for BaseService configuration: `dto_class`, `model_class`, `search_fields`, `search_order_by`, `category_field`, `temporal_exclude_statuses`, `supports_user_progress`, `user_ownership_relationship`, `search_visibility`, `graph_enrichment_patterns`, etc.

**Factory functions:** `create_activity_domain_config()`, `create_curriculum_domain_config()`

**See:** `/docs/patterns/query_architecture.md`, `/docs/architecture/SEARCH_ARCHITECTURE.md`

### EntityTimestampMixin

Use for Neo4j property-dict timestamp helpers: `update_properties()` (updates), `timestamp_properties()` (creation). Sole inheritor is `TranscriptionService` — grep `EntityTimestampMixin` to confirm before assuming wider adoption.

**See:** `/docs/patterns/entity_timestamp_mixin.md`

## Content Ingestion & Vault

### Unified Content Ingestion

**Core Principle:** "The hips of SKUEL — one of three foundational systems"

One-way pipeline: Markdown/YAML → Neo4j; most EntityTypes are file-ingestible.

- **Human-initiated per event** (ADR-070 Decision 9 — no background watcher). Three doors: the personal-vault "Sync from Obsidian" button, the admin "Sync content vault" button (`POST /api/vault/sync/content`, the one directory-ingest path), and one-shot `./dev vault-sync` (`scripts/vault_bridge_sync.py`, in-process reconciler).
- **Deletions propagate** on incremental/smart runs (entity file deleted → entity deleted; Edge YAML deleted → relationship deleted; move/rename + mass-deletion guards).
- **Force re-ingest** (`force=True` engine flag / route `{"force": true}` / `./dev vault-sync --force`) re-processes unchanged files for re-chunk/migration campaigns but keeps the wall + deletion reconciliation (force ≠ full).
- `/submit` (exercise) uses `UserEntryService.create_entry()` via `core/services/ingestion/user_entry_ingestion.py` (ADR-054), not the directory door. The vault is the source of truth for user data; `/settings/vault` (Obsidian bidirectional sync) is the primary personal-data path.

**Default Vault:** `/home/mike/0bsidian/0vault/` — configurable via `INGESTION_PATH` env var.

**Import:** `from core.services.ingestion import UnifiedIngestionService`

**API:** `POST /api/ingest/file`, `POST /api/ingest/vault`, `POST /api/ingest/domain/{domain_name}`, `POST /api/vault/sync/content`

**See:** `/docs/patterns/UNIFIED_INGESTION_GUIDE.md` (legacy YAML rejection, explicit `type` field rule, UID prefix validation, UserEntry `pipeline`/`audience` fields), `/docs/architecture/CORE_SYSTEMS_ARCHITECTURE.md`

### Obsidian VaultBridge (ADR-070)

**Core Principle:** "Obsidian is the personal knowledge layer; SKUEL is the structured backbone"

Bidirectional sync between a user's personal Obsidian vault and SKUEL. Tasks written to Obsidian as `- [ ] task title 🆔 sk_<6>`; completions (`[x]` + `✅ date`) propagate back to SKUEL. The `🆔 sk_<6>` suffix is the join key — never strip it.

- `VAULT_ROOT` — the PRIMARY personal vault (`/home/mike/0bsidian/skuel/`), distinct from `INGESTION_PATH` (content vault `0vault/`)
- **Per-user roots:** `VAULT_ROOT` is owner-bound (`SKUEL_PERSONAL_VAULT_OWNER`, defaults to the `SKUEL_DEFAULT_USER_UID` chain); any other user resolves to `{SKUEL_USER_VAULTS_ROOT}/{user_uid}/` or gets a clear not-found — no code path serves one user another user's vault
- `VaultBridgePort` / `FilesystemVaultAdapter` / `VaultReconciler` — hexagonal port/adapter/reconciler triple
- First-run consent gate guards the FIRST sync end to end (read + write) — nothing is ingested before consent; vault-root containment guard prevents upload-entry contamination
- **Transport toggle:** `VAULT_TRANSPORT=filesystem|local_agent` (ADR-075, default filesystem) — `local_agent` reaches personal vaults through the user's connected `skuel-vault-agent` via a server-side staging mirror; content vault always stays filesystem

**See:** `/docs/decisions/ADR-070-bidirectional-vault-bridge.md`, `/docs/decisions/ADR-075-local-agent-vault-transport.md`

## Intelligence & User Context

### Unified User Architecture

**Core Principle:** "UserContext is THE single object for understanding a user's complete state"

One object (~250 fields), built by one query (MEGA-QUERY), consumed by all intelligence services. Carries core identity from the `User` model (`user_uid`, `username`, `display_name`, `email`, `user_role`) — only fetch `User` directly when you need `user.preferences`.

| Depth | Method | Use Case |
|-------|--------|----------|
| Standard | `build()` | API responses, ownership checks (~150 fields) |
| Rich | `build_rich()` | Intelligence, daily planning (~250 fields) |

**ZPD Capstone:** `build_rich()` computes `context.zpd_assessment` (ZPDAssessment) as its final step — the pedagogical gravity well that synthesizes curriculum graph, behavioral signals, life path alignment, and compound evidence into recommended learning actions. FULL tier only. See: `core/services/zpd/zpd_service.py`.

**Canonical Location:** `/core/services/user/unified_user_context.py`

**See:** `/docs/architecture/UNIFIED_USER_ARCHITECTURE.md`

### Analytics Architecture

**Core Principle:** "Analytics aggregate, they don't create"

Analytics is a meta-service, not a domain. No Analytics nodes in Neo4j. READ-ONLY queries across all domains.

**Knowledge-health gauge (ADR-080 H1):** `KnowledgeHealthService` (`core/services/analytics/knowledge_health_service.py`) — a corpus-level `BaseAnalyticsService` (no AI, CORE-safe) over the knowledge subgraph (Ku/PathStep/LP/Exercise): degree distribution, orphan Kus, prerequisite-DAG depth/coverage, ORGANIZES/MOC coverage, a composite GDS-readiness score, authoring-guidance flags. Exposed via the `AnalyticsService` facade (`analyze_knowledge_subgraph_health`), admin `/admin/knowledge-health`, `./dev knowledge-health [--json]`, and 6 knowledge-scoped Prometheus gauges (fed by the existing 5-min graph-health poller). **A corpus/authoring gauge excludes user-generated data** (learner-state telemetry, PERSONAL/ASSIGNED exercises) and matches knowledge nodes by `entity_type`, not domain label.

**See:** `/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md`, `/docs/decisions/ADR-080-auradb-three-horizon-strategy.md`

### Intelligence Services Architecture

**Core Principle:** "Graph analytics separated from AI — app runs without LLM dependencies"

| Layer | Base Class | Dependencies |
|-------|------------|--------------|
| Analytics | `BaseAnalyticsService` | Graph + Python (NO AI) |
| AI | `BaseAIService` | LLM + Embeddings (optional) |

**Intelligence Tier Toggle (ADR-043):** `INTELLIGENCE_TIER=core` ($0, analytics only) vs `INTELLIGENCE_TIER=full` (default). All 6 Activity Domain + 2 Curriculum facades have `.ai` (optional, `None` when `INTELLIGENCE_TIER=core`).

**LLM/embedding SDK clients (ADR-063):** `openai`/`anthropic`/`huggingface_hub` clients live in `adapters/external/llm/` + `adapters/external/embeddings/`, behind `ChatCompletionPort` / `EmbeddingClientOperations`. `core/` is SDK-client-free (only `exception_types.py` imports SDK exception classes). Guarded by `tests/unit/test_llm_sdk_boundary.py` (fails closed on any new vendor import).

**No LLM-generated Cypher, and no GraphRAG framework in the product runtime.** SKUEL deliberately does not use `neo4j-graphrag` or `langchain-neo4j`'s `text2cypher` (both left the tree with the `langchain-*` removal, 2026-07-27; `mcp-neo4j-cypher` remains a dev-group tool, and production builds `uv sync --no-dev`). Intent is classified by embedding similarity — the LLM only generates the answer, and never writes a query. Retrieval is deterministic, reviewed, parameterized Cypher below `UniversalNeo4jBackend` (SKUEL001/SKUEL021 gate *where* Cypher may be authored; CYP003 gates parameterization). The decisive reason is multi-tenancy — generated Cypher has no enforced `user_uid` scoping, which is a data-leak *class*, not a tuning problem. The only shape we would consider for open-ended querying is **LLM tool-selection** (model picks a vetted tool + typed args; `user_uid` injected server-side) — a design sketch, not scheduled.

**See:** `/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md`, `/docs/decisions/ADR-043-intelligence-tier-toggle.md`, `/docs/decisions/ADR-063-llm-embeddings-sdk-ports.md`, `/docs/roadmap/askesis-tool-selection-queries.md` (why not text2cypher/GraphRAG + the tool-selection alternative)

### Embedding Text Extraction

**Location:** `/core/utils/embedding_text_builder.py` — `build_embedding_text(EntityType, dict) -> str`

**Supported:** 16 content-bearing entity types (all 6 Activity Domains + Curriculum + Resource + RevisedExercise + UserEntry + EntryReport + FormTemplate + FormSubmission). Field mappings in `EMBEDDING_FIELD_MAPS`. PathStep + Ku ENTITY vectors = frontmatter fields only; body semantics = CHUNK embeddings (`chunks_body_content` ingestion configs — lesson bodies live on the :Content subtree, read back via `UniversalNeo4jBackend.get_content`).

**Write paths (ADR-074):** ingestion never embeds inline — all create/update paths + both ingest doors publish `*EmbeddingRequested` post-persist through `core/events/embedding_publisher.py` → background worker (FULL tier; ingestion `event_bus` is None in CORE). One-shot script syncs (`./dev vault-sync`) subscribe the worker pre-sync and `drain()` post-sync — same event path, in-process. Backfill/staleness backstop: `scripts/generate_embeddings_batch.py [--stale|--audit]` (`--audit` = timestamp-free full-corpus hash sweep). Content-hash idempotency (ADR-074 §8): unchanged text never re-embeds — `embedding_text_hash` + `EmbeddingsService.verify_fresh_embeddings` skip BEFORE generation (worker + `--stale`); version outranks hash (a version bump always re-embeds). **See:** `/docs/decisions/ADR-074-post-persist-embedding-events.md`

## Web Layer: Auth, Routing, API & UI

### User Roles & Authentication

**Core Principle:** "Graph-native authentication - all auth data in Neo4j"

| Role | Level | Permissions |
|------|-------|-------------|
| REGISTERED | 0 | Free trial |
| MEMBER | 1 | Paid subscription |
| TEACHER | 2 | Member + create curriculum |
| ADMIN | 3 | Teacher + user management |

Auth: `require_authenticated_user(request) -> UserUID` (from `adapters.inbound.auth`); role gates like `@require_admin(get_user_service)` take a named function, not a lambda (SKUEL012).

**See:** `/docs/patterns/AUTH_PATTERNS.md`

### Ownership Verification

**Core Principle:** "Return 'not found' for entities the user doesn't own"

| Pattern | Domains | Create | Read | Ownership Check |
|---------|---------|--------|------|-----------------|
| **USER_OWNED** | Activities, UserEntry | User | Owner only | Yes (returns 404) |
| **SHARED** | KU, PS, LP | Admin only | All users | No (public) |
| **ADMIN_ONLY** | Finance | Admin only | Admin only | No (admin-gated) |

**Route helpers** (`from adapters.inbound.route_factories`):
- `verify_entity_ownership(service, uid, user_uid, domain)` — API routes. Returns error `Result` or `None`.
- `require_owned_entity(service, uid, user_uid, entity_name)` — UI routes. Returns `(entity, None)` or `(None, Response)`.

**See:** `/docs/patterns/OWNERSHIP_VERIFICATION.md`

### Error Handling

**Core Principle:** "Use `Result[T]` internally, convert to HTTP at boundaries"

- Use `.is_error` (not `.is_err`) for failure checks
- Use `Result.fail(result)` to propagate errors across type boundaries (not `Result.fail(result.expect_error())`)
- Use `.expect_error()` only when you need to _read_ the error (logging, branching on category)
- Use `require_found(result, resource, uid)` for the fetch + not-found guard pattern in routes
- Use `Errors` factory for creating errors
- Seven error types: Validation, NotFound, Database, Integration, Business, System, Forbidden
- **Narrow exceptions:** Use specific types from `core/utils/exception_types.py` (`NEO4J_EXCEPTIONS`, `LLM_EXCEPTIONS`, `DATA_CONVERSION_EXCEPTIONS`, etc.) instead of bare `except Exception`. Annotate intentional broad catches with `# intentional-broad:`, `# safety-net:`, or `# skuel-lint: disable=SKUEL017` (SKUEL017). Convention: persistence layer uses `NEO4J_EXCEPTIONS`; API/UI boundaries use `# safety-net:` annotations.
- **Inline suppression:** `# skuel-lint: disable=SKUELXXX -- <reason>` (line) or `# skuel-lint: disable-file=SKUELXXX -- <reason>` (file-level). Supported: SKUEL005, SKUEL011–SKUEL015, SKUEL017–SKUEL025, SKUEL027–SKUEL030, SKUEL032. Every lint run audits suppressions; one that suppresses nothing is flagged as SKUEL026 — delete it.

**See:** `/docs/patterns/ERROR_HANDLING.md`

### API Input Validation

**Core Principle:** "Validate at boundaries, fail fast with clear errors"

- **Query Parameters (GET):** Shared helpers in `route_helpers.py` (`parse_bool_query_param`, `parse_date_query_param`, `parse_csv_query_param`, `parse_pagination_params`, etc.)
- **JSON Bodies (POST):** Pydantic request models (auto-validated)
- **Request Model Location:** `core/models/{domain}/{domain}_request.py`
- **Error Codes:** Query params → 400 Bad Request, JSON bodies → 422 Unprocessable Entity

**See:** `/docs/patterns/API_VALIDATION_PATTERNS.md`

### HTTP Status Codes

POST (Create) → 201, GET/PUT/DELETE → 200, POST (Action) → 200

### Route Factories

| Factory | Purpose |
|---------|---------|
| CRUDRouteFactory | Standard CRUD |
| StatusRouteFactory | Status changes |
| OwnershipRouteFactory | Ownership-verified domain routes (GET/POST with ownership checks) |
| CommonQueryRouteFactory | Query patterns |
| AnalyticsRouteFactory | Analytics |
All support `scope=ContentScope.USER_OWNED` (default) or `ContentScope.SHARED` (curriculum, with `require_role=UserRole.ADMIN`). `role_gates_reads=False` allows role-gated mutations with open reads (Groups pattern). Scope and role are orthogonal — both ownership verification and role checks apply independently.

**See:** `/docs/patterns/ROUTE_FACTORIES.md`

### Domain Route Configuration

**Core Principle:** "Configuration over code for route registration"

DomainRouteConfig eliminates route wiring boilerplate. All 6 Activity Domains use `create_activity_domain_route_config()` for config-driven CRUD / Query / Intelligence registration. Three wiring patterns exist — **A) DomainRouteConfig** (default), **B) Orchestrator** (explore/lateral/library), **C) Manual `@rt()`** (home, settings, submissions_hub). `ai_routes.py` uses its own `AIRouteSpec`.

**See:** `/docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md` (full config fields, wiring decision guide, worked example)

### FastHTML Best Practices

- Query parameters over path parameters (`/tasks/get?uid=...`)
- POST for all mutations
- Type hints for automatic parameter extraction
- **Critical:** Do NOT use `routes = []` / `routes.append()` with `@rt()`. The decorator registers immediately.

**See:** `/docs/patterns/FASTHTML_ROUTE_REGISTRATION.md`

### UI Component Pattern

**Core Principle:** "BasePage for consistency, AuthPage for unauthenticated flows"

| Layout | Use Case |
|--------|----------|
| `BasePage(STANDARD)` | Most pages (centered content, navbar) |
| `BasePage(CUSTOM)` | Full-width, page manages layout (SidebarPage) |
| `AuthPage()` | Unauthenticated pages (login, register, landing — no navbar/chrome) |

All three load CSS through `build_head()` (pre-compiled Tailwind + vendored JS). Never hand-assemble `<link>` tags or use `NotStr` for full HTML documents. Routes in `/adapters/inbound/*_routes.py`, UI in `/ui/`, static in `/static/`.

**Page Contexts:** Per-domain TypedDicts in `/ui/page_contexts.py` define route→UI contracts with typed entities (`list[Task]`, etc.). `render_list_view(ctx)` is the only signature. NOT in `core/ports/` — page contexts are UI concerns.

**See:**
- `/docs/ui/ROUTE_MAP.md` — per-page descriptions grouped by navigation section (Admin / Regular / Teaching / Study / Settings)
- `/docs/patterns/UI_COMPONENT_PATTERNS.md` — shared components (`PageHeader`, `CardGenerator`, `StatsGrid`, `ButtonLink`, badges, `AlpineModal`, etc.) + Key UI Files inventory
- `/docs/ui/COMPONENT_CATALOG.md` — component catalog

### Alpine.js Architecture

| Layer | Tool | Purpose |
|-------|------|---------|
| UI State | Alpine.js | Modals, toggles, filtering |
| Server Communication | HTMX | Form submissions, loading |
| Pure Presentation | FastHTML | HTML generation |

**Key Files:** `/static/js/skuel.js` (ALL Alpine.data() components), `/static/vendor/alpinejs/alpine.3.14.8.min.js`

### PWA Mobile Strategy

**Core Principle:** "One format (HTML), installable everywhere — no app store dependency"

| Capability | Implementation |
|------------|---------------|
| Installability | Web app manifest (`/manifest.json`) |
| Offline support | Service worker (network-first HTML, cache-first static) |
| Offline indicator | `offlineIndicator` Alpine.js component + fixed bottom banner |
| Push notifications | Web Push API (future) |

**Key Files:** `static/manifest.json`, `static/service-worker.js`, `static/offline.html`, `ui/theme.py` (`pwa_headers()`)

**See:** `/docs/decisions/ADR-050-pwa-mobile-strategy.md`

### Lateral Relationships & Vis.js Graph Visualization

Available on all 9 domains (Tasks, Goals, Habits, Events, Choices, Principles, KU, PS, LP).

**Three Components:** BlockingChainView (vertical flow), AlternativesComparisonGrid (side-by-side), RelationshipGraphView (Vis.js force-directed graph).

**6 Lateral Relationship Types:** BLOCKS/BLOCKED_BY, PREREQUISITE_FOR/DEPENDS_ON, ALTERNATIVE_TO, COMPLEMENTARY_TO, SIBLING, RELATED_TO.

**Usage:** `EntityRelationshipsSection(entity_uid=entity.uid, entity_type="tasks")` — add to any detail page.

**See:** `/docs/architecture/RELATIONSHIPS_ARCHITECTURE.md`, `/docs/patterns/LATERAL_RELATIONSHIPS_VISUALIZATION.md`

## Tooling, Quality & Process

### Code Quality & Formatting

**Formatting:** Ruff. `./dev format` to format, `./dev quality` for full checks (Ruff + MyPy + audit scripts).

**Dead-code detection (advisory):** `./dev bloat` — staged-but-unwired work belongs in `PLANNED_EVENTS`/`PLANNED_METHODS`/`PLANNED_TEMPLATES` in `scripts/detect_bloat.py`, not the trash. Scope = events/methods/templates ONLY — a clean run is NOT evidence for fields, dataclasses, enum members, or config knobs (those are found by review). **See:** `/docs/tools/BLOAT_DETECTION.md`

**Docs-staleness check (automatic):** `.claude/hooks/post-commit-docs.sh` fires after `git commit` and flags docs/skills that reference changed files for semantic staleness review. **See:** `/docs/tools/AUTOMATIC_DOCS_CHECK.md`

**SKUEL Linter Rules** — full detail in `/docs/patterns/linter_rules.md`:

| Rule | Guards | Severity |
|------|--------|----------|
| SKUEL001 | No `apoc.*` above the boundary — `core/`, `adapters/inbound/`, `ui/`; whole-namespace match, `apoc.meta.*` included (docstring-aware; unsuppressable) | CRITICAL |
| SKUEL003 | `.is_error` not `.is_err` | ERROR |
| SKUEL007 | `Errors` factory (incl. `str(...)` wraps) — services + `adapters/inbound/`, `ui/` | WARNING |
| SKUEL011 | No `hasattr()` — Protocol/isinstance/getattr | ERROR |
| SKUEL012 | No lambda — named functions | ERROR |
| SKUEL013 | `RelationshipName` enum — services + `adapters/inbound/`, `ui/` | ERROR |
| SKUEL014 | `EntityType`/`NonKuDomain` enum — services + `adapters/inbound/`, `ui/` | ERROR |
| SKUEL015 | No `print()` in production | ERROR |
| SKUEL016 | No Poetry refs — SKUEL uses uv | ERROR |
| SKUEL017 | No bare `except Exception` — specific types from `exception_types.py` | ERROR |
| SKUEL019 | `get_credential()` not raw `os.getenv()` on credential names | ERROR |
| SKUEL020 | `request: Request` not `request: Any` in handlers (causes FastHTML 400) | ERROR |
| SKUEL021 | No raw Cypher above the boundary — `core/`, `adapters/inbound/`, `ui/`; all Cypher in `adapters/persistence/neo4j/` (docstring-aware). Composition root (`services_bootstrap/`) is deliberately out of scope — it may ping the driver it built | ERROR |
| SKUEL022 | No `adapters/` imports in `core/` — `TYPE_CHECKING`-only imports exempt | ERROR |
| SKUEL024 | No `cls=` + `**kwargs` collision in FT helpers — fix: `cls=f"...{cls}".strip()` | ERROR |
| SKUEL025 | No deleted Activity `*UpdatePayload` — use `*UpdateIntent` or `*UpdateRequest.to_intent()` | ERROR |
| SKUEL026 | No suppression comments that suppress nothing (per-run audit) | WARNING |
| SKUEL027 | No runtime `adapters` imports in `ui/` — `TYPE_CHECKING`-only exempt (SKUEL022's ui/ sibling) | ERROR |
| SKUEL028 | `Result.fail(result)` to propagate — never `Result.fail(...expect_error())` | ERROR |
| SKUEL029 | No `async def` without `await` — async for I/O, sync for computation (suppress protocol/lifecycle-required async) | ERROR |
| SKUEL030 | Every label / edge in `adapters/persistence/` Cypher must be a `NeoLabel` / `RelationshipName` member — Neo4j matches zero rows on an unknown name instead of erroring (`.cypher` half is CYP011) | WARNING |
| SKUEL031 | No stale pip refs (`pip/pip3 install\|uninstall\|freeze`, `python -m pip`, incl. `uv pip install`) — uv is the one path (`uv add`/`uv sync`); SKUEL016's pip sibling | WARNING |
| SKUEL032 | No runtime `ui` imports in `core/` — return a `core/ports/query_types` row, build the display type in `ui/` (ADR-058; SKUEL022's presentation-side twin) | ERROR |
| SKUEL033 | No docstring *opening* with a Cypher clause, or *hosting* a query (≥2 clause-leading lines), in `core/services`, `core/orchestrator`, `core/ports`, `core/models` — state intent + the guarantee, not the backend's query. Scope transcribed from SERVICE_DOCSTRING_STYLE.md's table (`core/utils/` excluded — its USAGE EXAMPLES are sanctioned) | WARNING |

**MyPy:** `./dev quality` enforces **0 errors**. Key strictness:
- `arg-type` on all first-party trees (`core/`, `services_bootstrap/`, `adapters/`, `ui/`); `tests`/`scripts` exempt
- `assignment` enabled — catches trailing-comma tuple bugs and real type mismatches
- `disallow_untyped_defs` on `core.services.*`, `core.ports.*`
- Domain backends suppress `misc` (an MRO conflict on `get_related_entities`; measured backlog 8)
- Every new `Any` needs `# boundary:` comment; narrow Neo4j property types with `int()`/`float()`/`str()` casts before arithmetic
- **Suppressions are audited** — `./dev health-mypy` (SKUEL026's mypy analogue) flags any `disable_error_code` entry measuring 0 errors and any override block mypy reports as `unused section(s)`. Verified per (block, code) pair, since the same code can sit in two blocks. Weekly CI; deliberately NOT in `./dev health` (~80s). **See:** `/docs/tools/HEALTH_CHECKS.md § 5`

**See:** `/docs/patterns/linter_rules.md`, `docs/patterns/mypy_pragmatic_strategy.md`

### Dependency Versioning (Python + JS)

**Core Principle:** "Latest stable by default — pins are deliberate and documented"

- Target the latest stable CPython (currently **3.14**, pinned in `.python-version`); `>=` floors in `pyproject.toml` track the locked latest, not a historical minimum. `./dev deps` lists outdated direct deps + the intentional pins.
- **Two intentional caps — never bump in a routine upgrade:** `neo4j==5.26.0` (conservative driver pin, Bolt-forward-compatible with the calendar-line server; driver version is *decoupled* from server version — ADR-044 + ADR-067 §3) and `deepgram-sdk<5.0.0` (5.x is a breaking rewrite).
- **Neo4j server policy:** latest *published* monthly of the *calendar* line (`YYYY.MM`); pinned exactly in `../infrastructure/docker-compose.yml` (never a floating tag). Bump ~monthly (each monthly is hotfixed only until the next ships); upgrades are forward/in-place, downgrades unsupported. 5.26 LTS is the no-treadmill alternative (ADR-067 §3a).
- ✅ **Renovate is LIVE** (Mend-hosted App, since 2026-08-05 — ADR-067 §5): grouped, PR-only dependency bumps (no auto-merge; intentional pins excluded) plus a Dependency Dashboard issue; run logs at the Mend portal, not the repo. It was configured-but-never-run until 2026-08-05 and briefly in Mend "Silent" mode — both historical. Still verify each bump locally (`./dev quality` + `./dev test-integration`) before merge — CI's `py`/`js` path filters include the lockfiles (`uv.lock`, `package-lock.json`), so Renovate bumps do trigger the relevant `tests/unit/` + `tests/integration/` (Neo4j testcontainer) / vitest jobs.
- **JS/Node (ADR-067 §6):** on an `npm audit` failure, `npm ls <pkg>` for the parent, then **check for a patched release inside the range already declared** before any bump or `overrides` (an `overrides` entry is a pin and outlives its advisory). `npm audit` is `./dev quality` check 8; in CI it runs **only** via the daily `../.github/workflows/dependency-audit.yml` (both ecosystems, diff-independent, files an issue). That job is **advisory, never a required check** — npm has no `.pip-audit-ignore` equivalent, so a gating job would wedge every merge on an unfixable advisory (ADR-067 §6e). **Node 20 is EOL (2026-04-30)** and caps jsdom at `^29`/undici 7.x. There is no `engines` field and no `.nvmrc`, so Node is pinned **only** in two workflow files that must move together: `../.github/workflows/ci.yml` (`js_tests`) and `../.github/workflows/dependency-audit.yml` (`js_audit`). Bumping one and not the other leaves the security audit on a different toolchain than the tests.
- Ruff `target-version` is `py314`; TC002/TC003/UP037 are ignored to isolate their ~1024-site deferred sweep (runtime-risky w/ Pydantic/FastHTML — see the `[tool.ruff]` ignore list). Black lags at `py312` (see `[tool.black]`).

**See:** `/docs/decisions/ADR-067-dependency-upgrade-policy.md`

### PR Review Workflow

**Core Principle:** "Reviews are advisory and a flaky service can't deadlock a merge — but the gate is never cleared by a timer, only by a read verdict"

- **CI Gate** is the sole automatic check.
- **Codex** is on-demand via `scripts/request_codex_review.sh <PR#>` — run it AFTER the final push (the gate drops the label on synchronize). The script polls patiently in-bash (Codex can take >13 min — #317) and **never labels without a real verdict**: on timeout the gate stays RED (exit 3) and proceeding past a genuine outage is a deliberate human call, not a timer. Exit codes: 0 clean+labeled / 2 findings-read / 3 timeout.
- The required **`Codex Review Gate`** clears via a PR-side consideration note (accept/reject + why) plus the `codex-considered` label — *considered*, not necessarily agreed with. Apply it via `scripts/apply_codex_considered.sh <PR#>`, never a bare `gh pr edit --add-label` (a gate run still queued from the last push race-strips a hand-applied label, #584; the script drains in-flight runs and confirms the gate goes green).
- **Merge policy (standing, 2026-07-25):** once CI Gate + Codex Review Gate are green AND an AI review verdict (Codex or Kody) on the final content was obtained and considered, merge autonomously — `gh pr merge <PR#> --squash --delete-branch` as a bare command (no pipes/compounds); no per-merge ask. Docs-only PRs: the Codex gate auto-passes with no verdict, so summon the review explicitly first. Stacked PRs: rebase the child onto `main` BEFORE deleting the base branch — base deletion auto-closes stacked PRs unrecoverably (#806→#807). **See:** PR_WORKFLOW.md § Merge policy.

**See:** `/docs/development/PR_WORKFLOW.md`, `.github/workflows/README.md` (repo root), `AGENTS.md` (repo root)

### Observability & Monitoring

**Core Principle:** "Prometheus tracks system health, Neo4j tracks user behavior"

- **Prometheus UI**: http://localhost:9090
- **Grafana Dashboards**: http://localhost:3000
- **Metrics Endpoint**: http://localhost:8000/metrics

Metrics across 7 categories (HTTP, Database, Event Bus, Domains, Relationships, Queries, AI), 14 alerting rules, and 4 Grafana dashboards (System Health, Domain Activity, Graph Health, Event Bus). The stack is dev-only (`./dev up-monitoring`); production runs no Prometheus/Grafana — one surface (`/metrics`, PR #803), blocked publicly at Caddy, read on-droplet via `docker compose exec`. AuraDB cap guard in production is the in-app poller check (`check_aura_cap_headroom`, WARNING >80% / ERROR >95% of cap, thresholds in `AuraDBCaps` drift-pinned to the alert exprs). Emit-first: no metric definition without live emission in the same change.

**See:** `@prometheus-grafana` skill, `monitoring/README.md`

### Logging Patterns

| Context | Tool |
|---------|------|
| Production runtime | `logger.*()` |
| Interactive CLI | `print()` |

```python
from core.utils.logging import get_logger
logger = get_logger("skuel.services.tasks")
```

`main.py` calls `setup_logging()` once at startup: level from `config.application.log_level` (`LOG_LEVEL` env), renderer from `config.application.log_format` (JSON everywhere except the local/development splits, which use text). Output goes to stdout AND rotating files — `logs/skuel.log` (daily, 7 backups) + `logs/skuel_errors.log` (ERROR-only, 14 backups); `logs/` is cwd-relative (`/app/logs` in containers, repo root locally, gitignored). Request-scoped lines carry `request_id` automatically. Never call `setup_logging()` from scripts or tests.

**See:** `/docs/patterns/LOGGING_PATTERNS.md`

### Graph-Native Comment Standard

Use `# GRAPH-NATIVE:` prefix for comments about relationship data stored as Neo4j edges.

**See:** `/docs/patterns/GRAPH_NATIVE_PLACEHOLDERS.md`

### Docstring Philosophy

**Three layers:** docstrings describe implementation, patterns describe approach, architecture describes design.

- **Always write:** Public APIs, complex functions, service classes, protocols
- **Skip:** Obvious one-liners, simple private helpers
- **Cross-reference:** `See: /docs/patterns/PATTERN_NAME.md`
- **Intent, not mechanism — in `core/services/`, `core/orchestrator/`, `core/ports/`, `core/models/`:** describe WHAT the operation means in domain language; reference the backend for HOW (`Backend: KuBackend.get_path_steps_using`). Cypher belongs in backend / `core/utils/` docstrings. SKUEL021 skips docstrings (correctly — prose can't execute), but **SKUEL033 enforces both a docstring that OPENS with a clause and one that HOSTS a query** across all four trees; naming a clause mid-sentence stays legal (a TypedDict documenting the `RETURN` alias its row mirrors is documenting the contract). The authority on scope is the linked doc's table, not this line. Note `MERGE` is an upsert — state the idempotency rather than flattening it to "Create".

**See:** `/docs/patterns/DOCSTRING_STANDARDS.md`, `/docs/patterns/SERVICE_DOCSTRING_STYLE.md`

### Skills & Documentation Cross-Reference

**Core Principle:** "Local curated docs first, external lookup only when missing"

See [CROSS_REFERENCE_INDEX.md](/docs/CROSS_REFERENCE_INDEX.md) for the complete skill-to-documentation mapping.

**Key skill categories:** Foundation (python, pydantic, ui-css, chartjs), Web Framework (fasthtml, domain-route-config, ui-browser), UX (accessibility-guide, skuel-ui, ui-error-handling), Database (neo4j-cypher-patterns), Infrastructure (docker, prometheus-grafana), Architecture (result-pattern, base-analytics-service, base-ai-service, prompt-templates, learning-loop, skuel-search-architecture, user-context-intelligence), Security (security), Testing (pytest), Meta (docs-skills-evolution).

### Documentation Architecture

**Single Source of Truth:** `/home/mike/skuel/app/docs/`
- `docs/decisions/` — Architecture Decision Records
- `docs/patterns/` — Implementation patterns
- `docs/architecture/` — System architecture
- `docs/INDEX.md` — Complete documentation index

**CLAUDE.md Purpose:** Quick-reference with pointers to detailed docs. Sections should be 10-20 lines max with `**See:**` pointers. Prose and examples belong in the linked docs, not here.

**Content Vault:** `/home/mike/0bsidian/0vault/` — Obsidian vault for content authoring (Ku / PathStep / edge YAMLs, markdown). Default ingestion source; override with `INGESTION_PATH` env var. NOT technical documentation.

## Reference

### Quick Reference: Key Files

| Purpose | Location |
|---------|----------|
| Service composition | `/services_bootstrap/` (package: `compose.py` orchestration, `_container.py` Services dataclass) |
| Base service | `/core/services/base_service.py` |
| Base analytics | `/core/services/base_analytics_service.py` |
| Knowledge intelligence | `/core/services/knowledge/` |
| Knowledge-health gauge (ADR-080 H1) | `/core/services/analytics/knowledge_health_service.py` + backend in `/adapters/persistence/neo4j/backends/curriculum_backends.py`; `scripts/knowledge_health_report.py` (`./dev knowledge-health`) |
| Telemetry retention (ADR-080 H0) | `/adapters/persistence/neo4j/telemetry_retention_backend.py`; `scripts/telemetry_retention.py` (`./dev telemetry-retention`); startup connect-retry in `/adapters/persistence/neo4j/neo4j_connection.py` (`connect_with_retry`) |
| Domain enums | `/core/models/enums/` |
| Graph contract view | `/docs/reference/GRAPH_CONTRACT.yaml` — generated; after enum/registry changes run `uv run python scripts/generate_graph_contract.py` (drift-tested) |
| Protocols | `/core/ports/` |
| Generic backend | `/adapters/persistence/neo4j/universal_backend.py` |
| Event bus | `/adapters/infrastructure/event_bus.py` (protocols: `/core/ports/infrastructure_protocols.py`) |
| Exception types | `/core/utils/exception_types.py` |
| Error boundary | `/core/utils/error_boundary.py` |
| Result helpers | `/adapters/inbound/result_helpers.py` (`require_found`) |
| Route factories | `/adapters/inbound/route_factories/` |
| UserEntry services | `/core/services/user_entry/` (ADR-054 — replaces former `submissions/` + `journal/`) |
| Page contexts | `/ui/page_contexts.py` |
| Deepgram config | `/config/deepgram.toml` |
| ADRs | `/docs/decisions/` |
| Patterns | `/docs/patterns/` |
| Architecture | `/docs/architecture/` |
| Troubleshooting | `/docs/TROUBLESHOOTING.md` |

### Troubleshooting

**Server Won't Start:** Port in use (`lsof -ti:8000 | xargs kill -9`), import errors (check `fasthtml.common`).

**Routes Return 404:** Check both API and UI routes registered in `bootstrap.py`. Distinguish 401 (auth) vs 404 (missing).

**Type Errors:** Forward reference unions use `Optional["Type"]` not `"Type" | None`.

**See:** `/docs/TROUBLESHOOTING.md`
