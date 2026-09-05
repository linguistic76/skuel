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

**Abandoned ≠ staged:** deliberately staged-but-unwired work is NOT dead code — register it in the bloat detector's PLANNED tier (`PLANNED_EVENTS`/`PLANNED_METHODS`/`PLANNED_TEMPLATES`/`PLANNED_EMBEDDING_MAPS` in `scripts/detect_bloat.py`) as a visible completion backlog. One Path Forward deletes the abandoned, never the staged.

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

| Pattern | UID (authored = stored) | Topology | Metaphor |
|---------|-----------|----------|----------|
| Ku | `ku.{ns}.{slug}` (API-generated: `ku_{slug}_{random}`) | Atom | A single concept/fact |
| PS | `ps.{namespace}.{slug}` | Content Unit | THE curriculum content entity (composes Kus) |
| LP | `lp.{namespace}.{slug}` | Path | An ordered sequence of path steps |

**Dot authoring (ratified 2026-08-14):** vault files author UIDs in dot form directly (`ku.{ns}.{slug}`) — authored = stored, verbatim. The colon spelling is retired and its input alias DELETED (the former `normalize_uid` shim) — a colon-spelled entity uid fails prefix validation loudly. Periodic `ue:daily:…` UIDs keep colons by design.

**Separator grammar (ratified 2026-08-14):** `-` joins words; `.` = authored-UID segments (middle segment = human-readable grouping hint, machine-opaque); `_` = generated-UID segments + filename type-prefix; `:` = internal machine identifiers ONLY (`ue:daily:…`, `edge:` sentinel, `transcription:`/`invoice:`), never an entity UID; family lives ONLY in edges (`ORGANIZES` etc.), never in UID strings. **See:** `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md § Separator Grammar`.

**Two Paths to Knowledge:** PS Path (structured, linear) and ORGANIZES Path (unstructured, graph, learner-directed). MOC is emergent identity — any Entity with ORGANIZES relationships. Authoring surface: `moc: true` frontmatter on any ingestible file → body links become `ORGANIZES {order}` edges (dangling links: silent in personal vaults, warned in content vault). **See:** `/docs/patterns/UNIFIED_INGESTION_GUIDE.md` § MOC files.

**Ku UID is flat & opaque** — hierarchy lives in `(parent)-[:ORGANIZES {order, importance}]->(child)` edges (multiple parents allowed), not in the UID. Two sanctioned forms — authored `ku.{ns}.{slug}` (vault) and generated `ku_{slug}_{random}` (API) — are BOTH valid; **never sniff type from the prefix** (spelling is provenance, not type information; determine entity kind by label/`entity_type`/edge).

**See:** `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md`, `/docs/decisions/ADR-013-ku-uid-flat-identity.md`, `/docs/patterns/UNIVERSAL_HIERARCHICAL_PATTERN.md`

### Content Origin Tiers

| Tier | ContentOrigin | EntityTypes | Description |
|------|--------------|---------|-------------|
| A | `CURATED` | Resource, FormTemplate (2) | Admin-curated content |
| B | `CURRICULUM` | Ku, PathStep, LearningPath, Exercise + the 6 Activity Templates (10) | Curriculum structure |
| C | `USER_CREATED` | the 6 Activities, UserEntry, LifePath, FormSubmission, Interaction, RevisedExercise (11) | User-generated |
| D | `REPORT` | ActivityReport, EntryReport (2) | Analysis/reports |

`ContentScope` controls access, `ContentOrigin` classifies purpose. Derived from `EntityType`.
**`RevisedExercise` is tier C, not B** — it is teacher-authored and `user_uid`-bearing, so its
origin is user-created even though its function is curricular. The rows above enumerate all 25
types (2+10+11+2) so they check themselves; `EntityType.<T>.content_origin()` is the authority.

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

**A facade being concrete to its callers does not license a concrete `self.backend`.** Both tiers type `self.backend` against a `core/ports` protocol — and SKUEL023 now also rejects `Any` / no annotation there, which cost exactly as much type safety as a concrete adapter did. It enforces both **unconditionally** — the facade allowlist that once parked KU/PS/LP and then UserService/UserContextBuilder/InsightStore was emptied and deleted in July 2026. There is no exempt path in `core/`.

**Trap:** same root word at both layers — verify the layer before retyping `self.backend` against an `*Operations` protocol; if service-layer and backend-layer method names diverge, you need a `*BackendOperations` protocol. ⚠️ **The suffix is not the layer.** The curriculum trio `KuOperations` / `PsOperations` / `LpOperations` are BACKEND protocols despite the route-facing suffix — all three extend `CurriculumOperations[T]` → `BackendOperations[T]`, satisfied by their `*Backend` adapter and by no service (`PsService` implements 8 of `PsOperations`' 142 members). Renaming the trio is an open question, ruled *state the layer, don't rename* (2026-08-20). ⚠️ **A handle that appears to hold a facade proves nothing — probe it.** An `Any`-typed deps container laundered five unsatisfiable annotations in `EntityExtractor` for months, and the "dual-layer `PsOperations`" doctrine built on one of them blocked a factory param for a month.

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

**Auto-timestamp:** `BaseEvent.occurred_at` defaults to `datetime.now()` via `kw_only` field — don't pass it for an event about something happening now. Pass it to carry a source occurrence forward when a handler publishes a *derived* event about the same moment (`PsPracticeService` → `KnowledgePracticed`), and for tests or event replay.

**Publish:** `await publish_event(self.event_bus, TaskCompleted(task_uid=uid, user_uid=user_uid), self.logger)` — import from `core.events` (there is no `core.events.utils`).

**Declaring an event:** `event_type: ClassVar[str] = "{domain}.{action}"` on the class — never a `@property`. It is a fact about the class, which is what lets `EVENT_REGISTRY` be **derived** by comprehension instead of hand-maintained; `BaseEvent.__init_subclass__` rejects a subclass that does not declare its own. A new event module must be imported in `core/events/__init__.py` — a comprehension cannot see what nobody imports, and `tests/unit/test_event_registry_derivation.py` fails if it is not. `list_event_types()` is the live catalog; there is no `ALL_EVENTS` (deleted 2026-08-17, zero consumers).

**See:** `/docs/patterns/event_driven_architecture.md`

## Data, Persistence & Search

### Neo4j Infrastructure

**Core Principle:** "One Path Forward - AuraDB Free is THE graph; local Docker Neo4j is an opt-in sandbox"

**Daily graph (cutover 2026-08-15):** **AuraDB Free** instance `d2d160c4` (US West, `neo4j+s://d2d160c4.databases.neo4j.io`), reached from the locally-run app. ⚠️ Aura usernames = the INSTANCE ID, not `neo4j` — credentials file authoritative; wrong username presents as Unauthorized, and Free refuses all user-admin Cypher (see AURADB_MIGRATION_GUIDE § 6.1). >72h idle → paused → manual console resume (`connect_with_retry` covers waking only). **Local Docker `skuel-neo4j`** (`bolt://localhost:7687`, `infrastructure/docker-compose.yml`) = STOPPED opt-in sandbox. Plugin: APOC (meta only). APOC scoped to `apoc.meta.*` — domain services use pure Cypher (SKUEL001). Embeddings via OpenAI `text-embedding-3-small` @1024 dims (Python-side, no Neo4j plugin; provider chokepoint `create_embedding_client()` — ADR-068). Committed end-state: Qwen chat + BGE-M3 embeddings (ADR-083 — dims frozen at `EmbeddingGeometry.DIMENSION`; no new OpenAI-required assumptions outside the two provider factories).

**Production (parked):** public hosting at skuel.app stays parked. When unparked: one droplet running `skuel-app` + Caddy (auto-TLS) via `docker-compose.production.yml`, talking to the same AuraDB Free instance over `neo4j+s://` (boot refuses plaintext schemes in production). Deploy via `./dev deploy` (rsync + build + `/health/ready` gate). The former intermediate stage (App Platform + Neo4j droplet) was skipped — see `NEO4J_SETUP_MIGRATION_SUMMARY.md`.

**Code is environment-agnostic** — only `.env` configuration changes between local and production.

**Per-query server-side timeout:** every query through the shared driver carries a server-side per-tx ceiling (`NEO4J_TRANSACTION_TIMEOUT`, default 120s; `0`=unbounded). Wired at compose via `TimedDriver` — single chokepoint, no call-site edits. Bulk ingestion wraps to 600s; startup DDL stays untimed (`Neo4jSchemaManager(raw_driver)` carve-out). Override per op with `neo4j_query_timeout(s)` / `unbounded_neo4j_query_timeout()`.

**Schema-change monitoring (opt-in, default OFF):** `SchemaChangeDetector` fingerprints the live schema, logs drift and keeps a migration history — that is its whole job: the cache-invalidating handler died with `query_builders/` (#1081) and the consumer-less handler seam was deleted 2026-08-29. On-demand via `Neo4jAdapter.check_schema_changes()`; or wire a background poll at startup with `NEO4J_SCHEMA_MONITORING=true` (+ `NEO4J_SCHEMA_MONITORING_INTERVAL`, default 900s, validated ≥1). Tier-independent (not `INTELLIGENCE_TIER`-gated) — off by default adds no always-on worker to CORE (the tier's guarantee is AI-scoped — the hourly `ProgressReportWorker` is a CORE Analog worker; see `GRACEFUL_DEGRADATION_ARCHITECTURE.md`). **See:** neo4j-cypher-patterns skill § 7.

**Server tuning (memory, JVM, Vector API — sandbox/self-host only; AuraDB manages its own):** all server config is `NEO4J_*` env vars on the `neo4j` service in the base compose `../infrastructure/docker-compose.yml` (repo root; the app `docker-compose.yml` extends it, overriding only deltas). The Java Vector API (SIMD) is enabled via `NEO4J_server_jvm_additional=--add-modules jdk.incubator.vector` — required for optimal performance of the vector indexes (boot creates the label set listed in `services_bootstrap/compose.py` — one list, not a count); `2026.x` warns without it.

**AuraDB three-horizon strategy (ADR-080):** AuraDB Free is live (cutover 2026-08-15); Neo4j Graph Data Science (GDS/AuraDS) deliberately deferred (density-gated; a Digital-layer enhancer, not part of the $0 core — GDS = pre-built graph algorithms, don't hand-roll). **Horizon 0 (shipped):** telemetry retention — `./dev telemetry-retention [--days N] [--dry-run]`, one-shot batched prune of unbounded-growth system telemetry (AuthEvent/SearchEvent/Interaction/stale VIEWED; saved `:ConversationSession` discussions EXCLUDED) keeps the graph under the Free node cap; startup connect-retry — `connect_with_retry` chokepoint in `Neo4jAdapter.connect` tolerates a paused/waking instance. `AURA-TEMPORARY:` marks self-host-only knobs — sandbox-only since the cutover, kept in compose for it. **Horizon 1:** author edge-first + the knowledge-health gauge (see Analytics below). Retention/connect-retry add no daemon to CORE (its guarantee is AI-scoped — "no AI background workers", not "no workers") (one-shot, not a loop).

**See:** `/docs/patterns/NEO4J_SERVER_TUNING.md`, `/docs/patterns/NEO4J_QUERY_TIMEOUT.md`, `/docs/decisions/ADR-064-neo4j-per-query-timeout.md`, `/docs/decisions/ADR-080-auradb-three-horizon-strategy.md`, `/docs/deployment/DO_MIGRATION_GUIDE.md`, `/docs/deployment/AURADB_MIGRATION_GUIDE.md`, `/docs/decisions/ADR-068-openai-embeddings-now-bge-later.md`

### Data Flow Architecture

```
Content to Storage:
Markdown → UnifiedIngestionService → KnowledgeUnit → GraphNode → Neo4j

Request Processing:
HTTP → FastHTML Route → Pydantic → Service → Domain → Repository → Neo4j
```

### Status-Guarded Writes (ADR-087)

**Core Principle:** "A status transition is decided BY the write, never before it"

Every status-bearing write in `core/services/` goes through `backend.update_with_status_guard(uid, updates, guard)` — one primitive on `_CrudMixin`, declared on `CrudOperations[T]`. The statement takes the node's write-lock BEFORE reading the prior status, applies the guard's prior-conditional patches, and **returns the prior**; services derive every verdict (`is_completion_transition` / `is_reopen_transition` / `is_repeat = not is_transition`) from that returned prior.

- **Build the guard, don't hand-write one:** `status_transition_guard(EntityType.X, changes)` in `core/services/completion_stamp.py` packages the legality check + stamp/clear conditions. `validate_status_target()` is the legality half alone — for Principle, which has no completion field and is deliberately NOT on the guard (its gate is target-only, so no race exists).
- **A raw writer is not exempt.** A write that sets a status outside its domain chokepoint still goes through the primitive — either with `status_transition_guard` (so a completed entity's stamp is cleared, not stranded) or a `refuse_if_prior_in` terminal set. Blind `backend.update({"status": ...})` is the bug this ADR removes.
- ⚠ **Leaving `CrudOperationsMixin.update` takes `_validate_update` off the path** — call the domain hook explicitly, gated on the fields that hook actually reads. A rule with no caller fails silently and looks like it passed.
- ⚠ **A same-day re-date is invisible to a same-day test** (Task/Goal stamp `date.today()`): backdate the stored stamp in the graph between the two writes.

**See:** `/docs/decisions/ADR-087-status-guarded-conditional-writes.md`

### Search & Query Architecture

**Core Principle:** "SearchRouter is THE single path for all external search access"

**One query builder + a Cypher function package:** `UnifiedQueryBuilder` (fluent facade over filter/limit/offset/order state — `query/unified_query_builder.py`; live callers reach it via `UniversalNeo4jBackend.query_builder`) and the `query/cypher/` package — **module-level `build_*` functions, not a class**. There is no `CypherGenerator` type: it was a design-notes proposal that was never built, and the name is not importable. Call the functions directly (`build_search_query(...)`, `build_semantic_context(...)`). The legacy `query_builders/` stack (`QueryBuilder` + optimizer/template-registry/validator/faceted/graph-context) was **deleted 2026-08-17** — constructed every boot, zero production invocations since 2026-05-12.

**Searchable Domains (SearchRouter):** 12 — Task, Goal, Habit, Event, Choice, Principle, Ku, PS, LP, Exercise, RevisedExercise, UserEntry. **Every OWNER_ONLY domain REQUIRES `user_uid`** — `SearchRouter.search()` refuses unscoped (the clause emits no ownership predicate without a user, so an unscoped call would return every user's rows); only PUBLIC and SCOPE_AWARE may be searched anonymously. UserEntry additionally is excluded from cross-domain sweeps and refused by name at `faceted_search`. Forms search via their own services (see SEARCH_ARCHITECTURE § Searchable Entity Types).

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
- **Deletions propagate** on incremental/smart runs (entity file deleted → entity deleted; Edge YAML deleted → relationship deleted; move/rename + mass-deletion guards). A target dropped from a registered frontmatter field loses its edge on the file's next ingest (both doors) — only edges the file itself authored are retracted, diffed from the `authored_edges` fingerprint on its tracker row.
- **Force re-ingest** (`force=True` engine flag / route `{"force": true}` / `./dev vault-sync --force`) re-processes unchanged files for re-chunk/migration campaigns but keeps the wall + deletion reconciliation (force ≠ full).
- **Preview** (`./dev vault-sync --preview [--vault content]`; personal: the "Preview sync" button / `POST /api/vault/preview`) is `VaultReconciler.preview` — the dry run of both halves (would-ingest / would-delete), nothing written. It applies the ingest gate's own no-type verdict (`is_non_entity_note`, the detector's predicate), so loose untyped notes are one `non_entity_notes` count, never phantom "new" files.
- **`UserEntryService.create_entry()` is the one convergence point** (ADR-054) — every door calls it **directly**, none through another. The two that get confused: the exercise **turn-in** (`/submit` → the canonical `/submissions/exercise` → `POST /api/user-entries/upload`, whose handler builds the request itself) never touches directory ingest; the **vault/YAML** door (`ingest_user_entry`, one caller — `UnifiedIngestionService.ingest_file()`) is on it. Other routes call `create_entry()` too — read `adapters/inbound/user_entry_api.py`, don't count from here. The vault is the source of truth for user data; `/submissions/sync` (Obsidian sync) is the primary personal-data path.

**Default Vault:** `/home/mike/0bsidian/0vault/` — configurable via `INGESTION_PATH` env var.

**Import:** `from core.services.ingestion import UnifiedIngestionService`

**API:** `POST /api/ingest/file`, `POST /api/ingest/vault`, `POST /api/ingest/domain/{domain_name}`, `POST /api/vault/sync/content`

**See:** `/docs/patterns/UNIFIED_INGESTION_GUIDE.md` (legacy YAML rejection, explicit `type` field rule, UID prefix validation, UserEntry `pipeline`/`audience` fields), `/docs/architecture/CORE_SYSTEMS_ARCHITECTURE.md`

### Obsidian VaultBridge (ADR-070)

**Core Principle:** "Obsidian is the personal knowledge layer; SKUEL is the structured backbone"

Bidirectional sync between a user's personal Obsidian vault and SKUEL. Tasks written to Obsidian as `- [ ] task title 🆔 sk_<6>`; task checkbox state is **outbound-only** — SKUEL writes `[x]` + `✅ date` on completion **and un-checks the line + strips the `✅ date` on a reopen** (byte-exact reverse, gated on a TRAILING `✅` token so it takes back only SKUEL's own write — a dateless `[x]` the user ticked, and a `✅ date` inside their own task text, are left alone; ADR-070 RDQ-2 amended 2026-08-24), while a vault-side check/uncheck/edit of a 🆔 line does NOT propagate back (extraction Guard 2b skips it; inbound propagation is designed in ADR-070 but parked — `docs/roadmap/deferred-work.md` § R4). Both outbound writes are driven by the sync's **state predicate**, never by `TaskCompleted`/`TaskReopened` — a status transition is consumed by the write that produced it and has no retry. The `🆔 sk_<6>` suffix is the join key — never strip it.

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

**Knowledge-health gauge (ADR-080 H1):** `KnowledgeHealthService` (`core/services/analytics/knowledge_health_service.py`) — a corpus-level `BaseAnalyticsService` (no AI, CORE-safe) over the knowledge subgraph (Ku/PathStep/LP/Exercise): degree distribution, orphan Kus, prerequisite-DAG depth/coverage, ORGANIZES/MOC coverage, a composite GDS-readiness score, authoring-guidance flags. Exposed via the `AnalyticsService` facade (`analyze_knowledge_subgraph_health`), admin `/admin/knowledge-health`, `./dev knowledge-health [--json]`, and 6 knowledge-scoped Prometheus gauges (fed by the existing 5-min graph-health poller). **A corpus/authoring gauge excludes user-generated data** (learner-state telemetry, PERSONAL/ASSIGNED exercises) and matches knowledge nodes by `entity_type`, not domain label. The report also carries an **embedding-coverage (retrievability) block** — per-label `embedding IS NULL` counts via `EmbeddingCoverageBackend`, deliberately corpus-wide incl. user-owned labels (retrievability ≠ authoring); remedy `./dev embed-backfill`. **See:** `/docs/tools/KNOWLEDGE_HEALTH.md`.

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

**Supported:** the keys of `EMBEDDING_FIELD_MAPS` — the map IS the list; no prose count is authoritative. A map declares WHAT would be embedded, not that anything is: a type is embedded only through an event class in `EMBEDDING_EVENT_TYPES` (`core/events/embedding_publisher.py`). A map with no event class is *hollow* (nothing builds text for it) and must be registered in `PLANNED_EMBEDDING_MAPS` (`scripts/detect_bloat.py` derives the hollow set on every run; an unregistered one fails `--check`). PathStep + Ku ENTITY vectors = frontmatter fields only; body semantics = CHUNK embeddings (`chunks_body_content` ingestion configs — lesson bodies live on the :Content subtree, read back via `UniversalNeo4jBackend.get_content`).

**Write paths (ADR-074):** ingestion never embeds inline — all create/update paths + both ingest doors publish `*EmbeddingRequested` post-persist through `core/events/embedding_publisher.py` → background worker (FULL tier; ingestion `event_bus` is None in CORE). One-shot script syncs (`./dev vault-sync`) subscribe the worker pre-sync and `drain()` post-sync — same event path, in-process. Backfill/staleness backstop: `scripts/generate_embeddings_batch.py [--stale|--audit]` (`--audit` = timestamp-free full-corpus hash sweep; default mode = `./dev embed-backfill`, fills embedding-NULL nodes only). Coverage gauge: per-label scan set + filters shared from `core/services/embeddings/retrievability.py`. Content-hash idempotency (ADR-074 §8): unchanged text never re-embeds — `embedding_text_hash` + `EmbeddingsService.verify_fresh_embeddings` skip BEFORE generation (worker + `--stale`); version outranks hash (a version bump always re-embeds). **See:** `/docs/decisions/ADR-074-post-persist-embedding-events.md`

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

**Read enforcement (ADR-085):** two chokepoints only — `build_search_visibility_clause()` (search strategies + `get_visible_to_user` by-UID reads) or route-mediated `verify_ownership`; bare `get()` is internal mechanics only (post-verification / system reads / PUBLIC domains); never add a third mechanism. The ownership edge is universal `:OWNS` with the `user_uid == :OWNS` owner invariant; Events attendance = staged `ATTENDS` design (ADR-086).

**See:** `/docs/patterns/OWNERSHIP_VERIFICATION.md`, `/docs/decisions/ADR-085-ownership-read-enforcement-contract.md`, `/docs/decisions/ADR-086-universal-owns-and-attends-attendance.md`

### Error Handling

**Core Principle:** "Use `Result[T]` internally, convert to HTTP at boundaries"

- Use `.is_error` (not `.is_err`) for failure checks
- Use `Result.fail(result)` to propagate errors across type boundaries (not `Result.fail(result.expect_error())`)
- Use `.expect_error()` only when you need to _read_ the error (logging, branching on category)
- Use `require_found(result, resource, uid)` for the fetch + not-found guard pattern in routes
- Use `Errors` factory for creating errors
- Seven error types: Validation, NotFound, Database, Integration, Business, System, Forbidden
- **Narrow exceptions:** Use specific types from `core/utils/exception_types.py` (`NEO4J_EXCEPTIONS`, `LLM_EXCEPTIONS`, `DATA_CONVERSION_EXCEPTIONS`, etc.) instead of bare `except Exception`. Annotate intentional broad catches with `# intentional-broad:`, `# safety-net:`, or `# skuel-lint: disable=SKUEL017` (SKUEL017). Convention: persistence layer uses `NEO4J_EXCEPTIONS`; API/UI boundaries use `# safety-net:` annotations.
- **Inline suppression:** `# skuel-lint: disable=SKUELXXX -- <reason>` (line) or `# skuel-lint: disable-file=SKUELXXX -- <reason>` (file-level). Supported: exactly `SkuelLinter.SUPPRESSIBLE_RULES` in `scripts/lint_skuel.py` (enumerated in `linter_rules.md`). Every lint run audits suppressions; one that suppresses nothing is flagged as SKUEL026 — delete it.

**See:** `/docs/patterns/ERROR_HANDLING.md`

### API Input Validation

**Core Principle:** "Validate at boundaries, fail fast with clear errors"

- **Query Parameters (GET):** Shared helpers in `route_helpers.py` (`parse_bool_query_param`, `parse_date_query_param`, `parse_csv_query_param`, `parse_pagination_params`, etc.)
- **JSON Bodies (POST):** Pydantic request models — either `parse_json_body(request, Model)` inside the handler, or `body: Model` in the signature (FastHTML binds it during parameter extraction, *before* the handler and `@boundary_handler` run, so `install_request_validation_guard` is what converts a rejected model; ⚠ never annotate an auto-bound body field as a `Literal` — FastHTML calls the annotation to coerce and `Literal(...)` raises `TypeError`, which no guard converts)
- **Request Model Location:** `core/models/{domain}/{domain}_request.py`
- **Error Codes:** both invalid query params and invalid JSON bodies → **400** (`ErrorCategory.VALIDATION`); 422 is `BUSINESS`, a rule violation, not a malformed input

**See:** `/docs/patterns/API_VALIDATION_PATTERNS.md`

### HTTP Status Codes

POST (Create) → 201, GET/PUT/DELETE → 200, POST (Action) → 200

### Route Factories

| Factory | Purpose |
|---------|---------|
| CRUDRouteFactory | Standard CRUD |
| create_activity_field_api_routes | Inline field updates incl. status (`POST /api/{domain}/{uid}/{field}`) |
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

**Key Files:** `/static/js/skuel.js` (the **shared** Alpine.data() components — NOT the whole registry: page-local bundles under `static/js/` register their own, and `tests/unit/docs/test_alpine_docs_registry.py` derives the union from every registrar; never count them in prose), `/static/vendor/alpinejs/alpine.3.14.8.min.js`

⚠ **Upgrading Alpine/HTMX touches two files:** the version constant in `ui/theme.py` **and** the versioned filename in `static/service-worker.js`'s `PRECACHE_URLS` — plus a `CACHE_VERSION` bump. `install` calls `cache.addAll()`, which rejects wholesale on a single 404, so a missed precache entry breaks service-worker install for every PWA client.

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

**Lateral relationship types:** the `RelationshipName` members in `_LATERAL_TYPES` (`core/models/relationship_names.py`; the `lateral` trait in the generated `GRAPH_CONTRACT.yaml`), inverses in `_LATERAL_INVERSES` — `PREREQUISITE_FOR` ↔ `REQUIRES_PREREQUISITE`; `DEPENDS_ON` is the separate Task scheduling edge, not a lateral type. The authoring UI exposes the subset its add-modal sub-forms POST to (`adapters/inbound/lateral_routes.py`).

**Usage:** `EntityRelationshipsSection(entity_uid=entity.uid, entity_type="tasks")` — add to any detail page.

**See:** `/docs/architecture/RELATIONSHIPS_ARCHITECTURE.md`, `/docs/patterns/LATERAL_RELATIONSHIPS_VISUALIZATION.md`

## Tooling, Quality & Process

### Code Quality & Formatting

**Formatting:** Ruff. `./dev format` to format, `./dev quality` for full checks (Ruff + MyPy + audit scripts).

**Dead-code detection (advisory):** `./dev bloat` — staged-but-unwired work belongs in `PLANNED_EVENTS`/`PLANNED_METHODS`/`PLANNED_TEMPLATES`/`PLANNED_EMBEDDING_MAPS` in `scripts/detect_bloat.py`, not the trash — each entry a `PlannedEntry(readiness, reason, since=…)` (`READY` = fully specified, no decision first; `DELAYED` = waits on a decision or an absent surface; `./dev bloat --ready` lists the READY slice) — but a **stale** registration is a WARNING and fails `--check`, as does a **dangling `blocked_by`** (an entry's optional pointer at the `deferred-work.md` heading holding its blocker — core text, never a restatement) and an **unregistered hollow embedding map** (a field map with no event class and no registration — the hollow set is derived, the registry annotates it). Stale means exactly one thing: the registered subject is GONE. *"Looks wired now"* never gates in any tier — every liveness engine here over-approximates by design, so a became-live signal is reported as masked, printed and never demanded. Scope = events/methods/templates/embedding field maps ONLY — a clean run is NOT evidence for fields, dataclasses, enum members, or config knobs (those are found by review; the field-map tier's phantom-field check is advisory forever). **See:** `/docs/tools/BLOAT_DETECTION.md`

**Docs-staleness check (automatic):** `.claude/hooks/post-commit-docs.sh` fires after `git commit` and flags docs/skills that reference changed files for semantic staleness review. **See:** `/docs/tools/AUTOMATIC_DOCS_CHECK.md`

**SKUEL Linter Rules** — the rules most often hit, not the full registry (`RULE_DOCS` in `scripts/lint_skuel.py` is); full detail in `/docs/patterns/linter_rules.md`:

| Rule | Guards | Severity |
|------|--------|----------|
| SKUEL001 | No `apoc.*` above the boundary — `core/`, `adapters/inbound/`, `ui/`; below it, backends author pure Cypher — the runtime calls no APOC; whole-namespace match, `apoc.meta.*` included (docstring-aware; unsuppressable) | CRITICAL |
| SKUEL003 | `.is_error` not `.is_err` | ERROR |
| SKUEL007 | `Errors` factory (incl. `str(...)` wraps) — services + `adapters/inbound/`, `ui/` | WARNING |
| SKUEL011 | No `hasattr()` — Protocol/isinstance/getattr | ERROR |
| SKUEL012 | No lambda — named functions | ERROR |
| SKUEL013 | `RelationshipName` enum — services + `adapters/inbound/`, `ui/` | ERROR |
| SKUEL014 | `EntityType`/`NonKuDomain` enum — services + `adapters/inbound/`, `ui/` | ERROR |
| SKUEL015 | No `print()` in production — runtime code logs through `logger.*()`; `print()` is for interactive CLIs | WARNING |
| SKUEL016 | No Poetry refs — SKUEL uses uv. Line-based, so comments and docstrings are in scope; naming the pattern in order to ban it is what `# skuel-lint: disable=SKUEL016` is for | WARNING |
| SKUEL017 | No bare `except Exception` — specific types from `exception_types.py` | ERROR |
| SKUEL019 | `get_credential()` not raw `os.getenv()` on credential names | ERROR |
| SKUEL020 | `request: Request` not `request: Any` in handlers (causes FastHTML 400) | ERROR |
| SKUEL021 | No raw Cypher above the boundary — `core/`, `adapters/inbound/`, `ui/`; all Cypher in `adapters/persistence/neo4j/` (docstring-aware). Composition root (`services_bootstrap/`) is deliberately out of scope — it may ping the driver it built | ERROR |
| SKUEL022 | No `adapters/` imports in `core/` — `core/` depends on a `core/ports` protocol and the adapter is injected (ADR-044); `TYPE_CHECKING`-only imports exempt | ERROR |
| SKUEL023 | `self.backend` in `core/` must name a `core/ports` protocol — not a concrete adapter class (direction), and not `Any`/unannotated (strength). Strength fires on classes that **assign** `self.backend` *and* on declaration-only class-body `backend: Any` (the mixin shape — dead declarations included, where the fix is deletion), *and* on a class that merely **inherits** `backend` from a `Base*[Any, ...]` or bare `Base*` parameterisation — annotating `__init__` does NOT fix that one, only parameterising the base does. Handles named anything other than `backend` stay uncovered **by ruling, not by omission** (Scope C, 2026-08-20 — measured: an AST trigger would fire on a constructor-inferred, already-checked handle) | ERROR |
| SKUEL024 | No `cls=` + `**kwargs` collision in FT helpers — fix: `cls=f"...{cls}".strip()` | ERROR |
| SKUEL025 | No deleted Activity `*UpdatePayload` — use `*UpdateIntent` or `*UpdateRequest.to_intent()` | ERROR |
| SKUEL026 | No suppression comments that suppress nothing (per-run audit) | WARNING |
| SKUEL027 | No runtime `adapters` imports in `ui/` — `ui/` renders what routes hand it, shared code moves inward; `TYPE_CHECKING`-only exempt (SKUEL022's ui/ sibling) | ERROR |
| SKUEL028 | `Result.fail(result)` to propagate — never `Result.fail(...expect_error())` | ERROR |
| SKUEL029 | No `async def` without `await` — async for I/O, sync for computation (suppress protocol/lifecycle-required async) | ERROR |
| SKUEL030 | Every label / edge in `adapters/persistence/` Cypher must be a `NeoLabel` / `RelationshipName` member — Neo4j matches zero rows on an unknown name instead of erroring (`.cypher` half is CYP011) | WARNING |
| SKUEL031 | No stale pip refs (`pip/pip3 install\|uninstall\|freeze`, `python -m pip`, incl. `uv pip install`) — uv is the one path (`uv add`/`uv sync`); SKUEL016's pip sibling — same line-based scope (docstrings included), suppress with `# skuel-lint: disable=SKUEL031` | WARNING |
| SKUEL032 | No runtime `ui` imports in `core/` — return a `core/ports/query_types` row, build the display type in `ui/` (ADR-058; SKUEL022's presentation-side twin) | ERROR |
| SKUEL033 | No docstring *opening* with a Cypher clause, or *hosting* a query (≥2 clause-leading lines), in `core/services`, `core/orchestrator`, `core/ports`, `core/models` — state intent + the guarantee, not the backend's query. Scope transcribed from SERVICE_DOCSTRING_STYLE.md's table (`core/utils/` excluded — its USAGE EXAMPLES are sanctioned) | WARNING |
| SKUEL034 | No substring test against a uid (`"tech" in knowledge_uid.lower()`) — entity kind comes from label / `entity_type` / edge, never UID spelling (ADR-013 never-sniff). A *collection* (`x in ku_uids`) is exempt, but that exemption does NOT survive serialization — `str(uids)` / `f"{uids}"` / `join(uids)` are flagged. `startswith` / `split` out of scope by ruling — their four live sites are sanctioned | ERROR |

**MyPy:** `./dev quality` enforces **0 errors**. Key strictness:
- `arg-type` on all first-party trees (`core/`, `services_bootstrap/`, `adapters/`, `ui/`); `tests`/`scripts` exempt
- `assignment` enabled — catches trailing-comma tuple bugs and real type mismatches
- `disallow_untyped_defs` on `core.services.*`, `core.ports.*`
- Two backend cluster modules (`activity_backends`, `curriculum_backends`) suppress `misc` (an MRO conflict on `get_related_entities`; measured backlog 8)
- Every new `Any` needs `# boundary:` comment; narrow Neo4j property types with `int()`/`float()`/`str()` casts before arithmetic
- **Suppressions are audited** — `./dev health-mypy` (SKUEL026's mypy analogue) flags any `disable_error_code` entry measuring 0 errors, any module pattern earning 0 inside a multi-pattern block, and any override block mypy reports as `unused section(s)`. Verified per (block, code) pair and per pattern. ⚠ Probe a suppression by editing the config, never with `mypy --enable-error-code` — the CLI flag sits below per-module config sections in mypy's precedence and reads as a clean pass over a scope that disables the code. Weekly CI; deliberately NOT in `./dev health` (~80s). **See:** `/docs/tools/HEALTH_CHECKS.md § 5`, `docs/patterns/mypy_pragmatic_strategy.md § Probing Whether a Suppression Is Still Needed`

**See:** `/docs/patterns/linter_rules.md`, `docs/patterns/mypy_pragmatic_strategy.md`

### Dependency Versioning (Python + JS)

**Core Principle:** "Latest stable by default — pins are deliberate and documented"

- Target the latest stable CPython (currently **3.14**, pinned in `.python-version`); `>=` floors in `pyproject.toml` track the locked latest, not a historical minimum. `./dev deps` lists outdated direct deps + the intentional pins.
- **Two intentional caps — never bump in a routine upgrade:** `neo4j==5.26.0` (conservative driver pin, Bolt-forward-compatible with the calendar-line server; driver version is *decoupled* from server version — ADR-044 + ADR-067 §3) and `deepgram-sdk<5.0.0` (5.x is a breaking rewrite).
- **Neo4j server policy:** latest *published* monthly of the *calendar* line (`YYYY.MM`); pinned exactly in `../infrastructure/docker-compose.yml` (never a floating tag). Bump ~monthly (each monthly is hotfixed only until the next ships); upgrades are forward/in-place, downgrades unsupported. 5.26 LTS is the no-treadmill alternative (ADR-067 §3a).
- ✅ **Renovate is LIVE** (Mend-hosted App, since 2026-08-05 — ADR-067 §5): grouped, PR-only dependency bumps (no auto-merge; intentional pins excluded) plus a Dependency Dashboard issue; run logs at the Mend portal, not the repo. It was configured-but-never-run until 2026-08-05 and briefly in Mend "Silent" mode — both historical. Still verify each bump locally (`./dev quality` + `./dev test-integration`) before merge — CI's `py`/`js` path filters include the lockfiles (`uv.lock`, `package-lock.json`), so Renovate bumps do trigger the relevant `tests/unit/` + `tests/integration/` (Neo4j testcontainer) / vitest jobs.
- **CVE audits are ONE path (2026-08-07):** `scripts/audit_dependencies.sh` runs **osv-scanner over both lockfiles** (`uv.lock` + `package-lock.json`, **all severities**) — it is `./dev quality` check 8, `./dev audit-deps`, the **required** `dep_audit` CI job, and the daily `../.github/workflows/dependency-audit.yml`. Every finding is fixed or accepted in `app/osv-scanner.toml` with a `reason` + `ignoreUntil` expiry (ADR-067 §6e; pip-audit and direct `npm audit` invocations are retired — the binary pin + checksum live in `.github/actions/install-osv-scanner`). The script refuses to run under `UV_FROZEN`/`UV_LOCKED` (they silently gut its `uv lock --check` staleness gate).
- **JS/Node (ADR-067 §6):** on a JS advisory, `npm ls <pkg>` for the parent, then **check for a patched release inside the range already declared** before any bump or `overrides` (an `overrides` entry is a pin and outlives its advisory). **Node 24 (LTS Krypton)** since 2026-08-05 (migrated off EOL Node 20), which keeps jsdom on `^30`/undici 8.x. Node is pinned in **three places that must move together** — all `^24.15.0` (jsdom-30's floor on the 24 line): `../.github/workflows/ci.yml` (`js_tests`), `engines.node` in `app/package.json`, and `app/.nvmrc` (`24`, the closest nvm can express). `app/.npmrc` sets `engine-strict=true` so `npm ci`/`npm install` **hard-fail** below the floor on any local path (not just nvm).
- Ruff `target-version` is `py314`. **TC002/TC003 are ignored permanently** (ruled 2026-08-28 — a TYPE_CHECKING move breaks any annotation evaluated at runtime, and FastHTML handler signatures are); **UP037 is one scheduled mechanical sweep** (tree-wide) — trigger/check in `deferred-work.md` § py314 Annotation Sweeps, rationale in ADR-067 § Deferred. Black lags at `py312` (see `[tool.black]`).

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
- **Present tense, no history:** a comment or docstring states what the code does now. What it used to do, which PR changed it and when belong to the commit message and the ADR or `done/` doc; a comment may point at the record, never retell it — `git log -S<name>` is the history mechanism.
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
- `app/plans/` (**gitignored**, outside `docs/`) — the thinking surface: drafts, arc prompts, investigations, half-formed design. Zero ceremony; free to be wrong, free to delete. **Nothing tracked may cite it** — that prohibition IS the graduation trigger: the moment a docstring, test, CLAUDE.md, or a memory file needs to point at a document, it must be tracked, so it graduates. Same rule for `~/.claude/plans/` and the memory directory — both are outside the repo and invisible to CI, worktrees, and clones. Finished scratch moves to `app/plans/done/` — same gitignored tier, no ceremony. `plans/done/` and `docs/roadmap/done/` are **not** two archives of the same thing: the separator is citation, not doneness. A doc that graduates *moves* out of `plans/` entirely, so nothing is ever in both.
- `docs/roadmap/` — **live plans only** (open, deferred, staged — anything still waiting on a trigger); `docs/roadmap/done/` — completed/executed roadmap docs. A doc graduating out of `plans/` lands in whichever of the two matches its state; already-executed work goes **straight to `done/`**. **No third destination to weigh** — a settled, code-cited contract is a `done/` doc, not a `patterns/` doc. `done/` is a **citable archive, not a graveyard**: 20+ code sites cite `done/zpd-service-architecture.md`, `done/update-intents.md`, and `done/secrets-out-of-worktree.md` as design rationale. Move a doc to `done/` when nothing in it remains open, updating every inbound reference (several live in code comments, which the cross-reference validator does not check — `git grep` the basename). The live folder answers "what might still happen."
- `docs/INDEX.md` — Curated documentation index (hand-maintained, not a full listing — an absent entry does NOT mean an absent doc)
- **`docs/roadmap/deferred-work.md` is a MOC (ruled 2026-09-04):** one `##` per item — the heading is the anchor `blocked_by` pointers and `§` code citations resolve against, so its core text never changes without moving them — then one link to the item's **case file** (`docs/roadmap/<slug>.md`, same move-to-`done/` lifecycle) and one line. The body lives in the case file, with `trigger:` / `check:` / `status:` / `registered:` / `ruled:` as its frontmatter properties; the MOC never restates them (`deferred-work.base` renders them as a table in Obsidian; `grep -H -E '^(trigger|check|status):' docs/roadmap/*.md` elsewhere).
- **Link form (ruled 2026-09-04):** a docs→docs markdown link is written **relative to the citing file** (`../patterns/X.md`; a sibling is `X.md`) — the form Obsidian generates and the only one its rename propagation reaches (`docs/` opens as a vault). Everything else — a doc citing code, a skill or this file citing a doc — stays repo-root-absolute (`/docs/…`). `./dev docs-links` names strays; `--apply` rewrites the ones that resolve (dead targets stay with the sweep queue; generated indexes emit the form themselves). **See:** `/docs/tools/HEALTH_CHECKS.md`.

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
