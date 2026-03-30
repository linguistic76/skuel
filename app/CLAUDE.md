- We use uv for package management and for running files.

## Code Responsibility Philosophy
*Last updated: 2026-03-03*

**If you see a problem, fix it.** Don't look the other way. Take responsibility to make the code better.

When working in a file or area of the codebase, address problems you encounter — wrong comments, stale docs, security issues, DRY violations, naming inconsistencies. SKUEL does not reward passive observation of bad code.

**This is not a license for scope creep.** Fix what is genuinely wrong. Don't redesign systems you were not asked to touch. The distinction: a bug you notice while working nearby should be fixed; a large refactor you think would be nice requires a deliberate decision.

---

## One Path Forward - Core Development Philosophy
*Last updated: 2026-02-23*

**SKUEL does NOT maintain backward compatibility.** When a better pattern emerges, the old pattern is removed entirely. No legacy wrappers, no deprecation periods, no alternative paths. Update all call sites immediately. Dead code is deleted, not archived.

**Design Philosophy:** Type errors are teachers, showing us where components don't flow together properly. When errors appear, investigate the fundamental design first rather than working around with quick fixes.

**See:** `/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md`

## Entity and Ku

**Core Principle:** "Entity is the universal base. Ku is one type of Entity."

`Entity` is the base frozen dataclass for all 19 domain types. The `entity_type` field discriminates which kind of entity it is. The `parent_entity_uid` field tracks derivation chains.

- **Lesson** (`EntityType.LESSON`, extends `Curriculum`) — a unit for learning. Services in `core/services/lesson/`.
- **Ku** (`EntityType.KU`, extends `Entity`) — atomic knowledge unit. Lightweight ontology/reference node. Services in `core/services/ku/`.
- **Composition:** `(Lesson)-[:USES_KU]->(Ku)` — Lessons compose atomic Kus into coherent learning content.
- **Learning loop:** Lesson -> Exercise -> ExerciseSubmission -> ExerciseReport -> RevisedExercise -> ...

## Naming Conventions

**File Naming:** File names must reflect function. When Claude Code provides a randomly-generated plan file name, immediately rename it to a descriptive name.

**Parameter Naming:** Underscore prefix indicates placeholder for future implementation:
```python
async def get_learning_opportunities(
    self, _filters: dict[str, Any] | None = None  # Placeholder - not yet implemented
) -> Result[list[dict[str, Any]]]:
```

## Neo4j Infrastructure

**Core Principle:** "One Path Forward - Docker -> DigitalOcean -> AuraDB"

**Stage 1 (Current):** Docker-based Neo4j (`bolt://localhost:7687`). Plugin: APOC (meta only). APOC scoped to `apoc.meta.*` — domain services use pure Cypher (SKUEL001). Embeddings via HuggingFace Inference API (Python-side, no Neo4j plugin).

**Stage 2:** Droplet (Neo4j) + App Platform (app). Same config as local Docker.

**Stage 3:** AuraDB. Database-level API keys, `neo4j+s://` connection, automated backups.

**Code is environment-agnostic** — only `.env` configuration changes across stages.

**See:** `/docs/deployment/DO_MIGRATION_GUIDE.md`, `/docs/deployment/AURADB_MIGRATION_GUIDE.md`, `/docs/decisions/ADR-049-huggingface-embeddings-migration.md`

## Skills & Documentation Cross-Reference

**Core Principle:** "Local curated docs first, external lookup only when missing"

See [CROSS_REFERENCE_INDEX.md](/docs/CROSS_REFERENCE_INDEX.md) for the complete skill-to-documentation mapping.

**Key skill categories:** Foundation (python, pydantic, ui-css, chartjs), Web Framework (fasthtml, domain-route-config, ui-browser), UX (accessibility-guide, skuel-ui, ui-error-handling), Database (neo4j-cypher-patterns), Infrastructure (docker, prometheus-grafana), Architecture (result-pattern, base-analytics-service, base-ai-service, prompt-templates, learning-loop, skuel-search-architecture, user-context-intelligence), Security (security), Testing (pytest), Meta (docs-skills-evolution).

**Total:** 26 skills with comprehensive documentation mappings.

## Documentation Architecture

**Single Source of Truth:** `/home/mike/skuel/app/docs/`
- `docs/decisions/` - Architecture Decision Records (ADRs, 43 total)
- `docs/patterns/` - Implementation patterns
- `docs/architecture/` - System architecture
- `docs/INDEX.md` - Complete documentation index

**CLAUDE.md Purpose:** Quick-reference with pointers to detailed docs. Sections should be 10-20 lines max with `**See:**` pointers.

**Content Location (different purpose):** `/home/mike/0bsidian/skuel/docs/` contains Knowledge Unit content for ingestion, NOT technical documentation.

**Default Ingestion Vault:** `data/vault/` (i.e., `/home/mike/skuel/app/data/vault/`) is the default folder for content ingestion — Ku YAMLs, Lesson YAMLs, edge YAMLs, and markdown files. Configurable via `INGESTION_PATH` env var. The Obsidian vault at `/home/mike/0bsidian/skuel/data/vault/` mirrors this as the authoring source.

## Docstring Philosophy

**Three layers:** docstrings describe implementation, patterns describe approach, architecture describes design.

- **Always write:** Public APIs, complex functions, service classes, protocols
- **Skip:** Obvious one-liners, simple private helpers
- **Cross-reference:** `See: /docs/patterns/PATTERN_NAME.md`

**See:** `/docs/patterns/DOCSTRING_STANDARDS.md`

## Analog-to-Digital Development Model

**Core Principle:** "Plain English in, working code out"

SKUEL is built through an explicit human-AI partnership: domain authority (human) provides clarity of intent in plain language; technical translation (AI) provides architectural judgment and pattern consistency. The Activity DSL (`@context(task)`, `@when()`, `@priority()`) is the purest expression — users write near-natural language, the parser converts to typed structures.

Future collaborators should read SKUEL's plain-English domain descriptions and ADRs as the authoritative specification. The code is the translation, not the source of truth.

**See:** `/docs/dsl/DSL_SPECIFICATION.md`

## Analog + Digital Runtime Architecture

**Core Principle:** "The Analog layer is not a degraded version of the Digital layer — it is the foundation"

SKUEL separates runtime into two layers. The **Analog layer** (graph structure, CRUD, ingestion, keyword search, analytics, user context) is complete on its own — fully functional at $0 with no API keys. The **Digital layer** (embeddings, vector search, LLM feedback, Askesis) enhances the Analog layer with machine understanding. Toggle with `INTELLIGENCE_TIER=core|full` in `.env`.

**See:** `/docs/architecture/ANALOG_DIGITAL_ARCHITECTURE.md`, `/docs/architecture/GRACEFUL_DEGRADATION_ARCHITECTURE.md`

## SKUEL's 21 Entity Types + 5 Cross-Cutting Systems

**Core Principle:** "Everything flows toward the life path"

### The 21 Entity Types

| EntityType | What It Is | UID Format | Ownership |
|------------|-----------|-----------|-----------|
| Task | Work to be done | `task_{slug}_{random}` | User-owned |
| Goal | Outcome to achieve | `goal_{slug}_{random}` | User-owned |
| Habit | Behavior to build | `habit_{slug}_{random}` | User-owned |
| Choice | Decision to make | `choice_{slug}_{random}` | User-owned |
| Principle | Value to embody | `principle_{slug}_{random}` | User-owned |
| Event | Time commitment to keep | `event_{slug}_{random}` | User-owned |
| FormTemplate | General-purpose form definition | `ft_{slug}_{random}` | Admin-created, shared |
| FormSubmission | User response to a FormTemplate | `fs_{slug}_{random}` | User-owned |
| Finance | Admin-only bookkeeping | `expense_{random}` | Admin-only |
| Lesson | A unit for learning | `l_{slug}_{random}` | Admin-created, shared |
| Ku | Atomic knowledge unit | `ku_{slug}_{random}` | Admin-created, shared |
| Resource | Curated content (books, talks, films) | N/A | Admin-created, shared |
| PathStep | A collection of lessons | `ps:{random}` | Admin-created, shared |
| LearningPath | An ordered sequence of lesson collections | `lp:{random}` | Admin-created, shared |
| Exercise | Instruction template for practicing curriculum | N/A | Admin-created, shared |
| RevisedExercise | Targeted revision instructions after feedback | `re_{slug}_{random}` | Teacher-owned |
| ExerciseSubmission | Student work submitted against an Exercise | `es_{slug}_{random}` | User-owned |
| JeInput | Journal entry input (voice/text) | `ji_{slug}_{random}` | User-owned |
| JeOutput | Journal entry output (LLM-transformed) | `jo_{slug}_{random}` | User-owned |
| ActivityReport | Report about activity patterns over time | `ar_{random}` | User-owned |
| ExerciseReport | Teacher or AI report on an exercise submission | `sr_{random}` | User-owned |
| LifePath | The user's life direction | `lp_{random}` | User-owned |
| Groups | Teacher-student class management | `group_{slug}_{random}` | Teacher-owned |
| MOC | Non-linear KU navigation | N/A (emergent — any Entity with ORGANIZES) | Emergent |

### Behavioral Traits (ADR-047)

Entity types have behavioral traits — not category membership — that determine infrastructure behavior:

| Trait | Method | What It Determines |
|-------|--------|--------------------|
| **Ownership** | `requires_user_uid()` | User-owned vs shared (admin-created) |
| **Content Origin** | `content_origin()` | Where content comes from (Curated, Curriculum, User-Created, Report) |
| **Activity** | `is_activity()` | Shares Activity infrastructure (factory, facade, sub-services) |
| **Processable** | `is_processable()` | Goes through a processing pipeline |
| **Derived** | `is_derived()` | Has parent in derivation chain |

### Entity Type Groups

- **Activity (6):** Task, Goal, Habit, Event, Choice, Principle — facade pattern with `.core`, `.search`, `.intelligence`, `.ai` sub-services. Created via `create_common_sub_services()`. Events additionally has integration sub-services; **Calendar** cross-cutting system handles scheduling aggregation. **Read-focused UI:** All 6 domains have dedicated list + detail views with cross-domain connections and `EntityRelationshipsSection` — Tasks (`/tasks`), Goals (`/goals`), Habits (`/habits`), Events (`/events`), Choices (`/choices`), Principles (`/principles`). Principles use gravity-well pattern (incoming connections) like Goals. Activity data enters via `/upload`; also viewable via ActivityReport at `/activity-reports`.
- **Curriculum (5):** Lesson, Ku, PathStep, LearningPath, Exercise — `ContentScope.SHARED`, admin creates, all users read.
- **Submissions/Reports (3):** ExerciseSubmission, ExerciseReport, ActivityReport — the learning loop. Services in `core/services/submissions/` + `core/services/report/`.
- **Journal (2):** JeInput, JeOutput — standalone journal domain. `JeInput(UserOwnedEntity)`, `JeOutput(UserOwnedEntity)`. Relationship: `(JeOutput)-[:TRANSFORMS]->(JeInput)`. Pipeline: JE_INPUT(audio) -> Deepgram -> JE_INPUT(text) -> LLM -> JE_OUTPUT. Models in `core/models/journal/`, services in `core/services/journal/` (`JournalInputService` — CRUD + file upload, `JournalOutputService` — LLM processing).
- **Other:** Finance (admin-only), Resource (curated, not curriculum), Groups (ADR-040), RevisedExercise (teacher-owned hybrid), MOC (emergent via ORGANIZES), LifePath (the destination, alignment score 0.0-1.0).

### The 5 Cross-Cutting Systems

| System | Purpose |
|--------|---------|
| UserContext | ~250 fields of cross-domain state |
| Search | Unified search across all domains |
| Calendar | Aggregates Tasks, Events, Habits, Goals |
| Askesis | Pedagogical guide — ZPD-aware Socratic companion anchored to curriculum |
| Messaging | Notifications (planned) |

### Service Architecture Pattern

```
UniversalNeo4jBackend[T]  <- ONE instance per domain, NO wrappers
        |
    {Domain}Service       <- Facade orchestrates sub-services
        |
    Sub-services          <- .core, .search, .intelligence
```

**See:** `/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md`, `/docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md`, `/docs/architecture/ASKESIS_PEDAGOGICAL_ARCHITECTURE.md`

## Type Safety Architecture

**Core Principle:** "A type error from MyPy reveals a real design problem, not an annotation oversight"

| System | What it does |
|--------|-------------|
| **Three-Tier Type System** | Pydantic at edges, frozen dataclasses at core, DTOs between |
| **Protocol-Based DI** | Zero concrete dependencies in route signatures — all services injected as protocols |
| **Typed Protocol Returns** | ~170 protocol methods return specific models/TypedDicts; 0 `Result[Any]` in protocols (1 intentional in `base_service_interface.py`). Service-layer `Result[Any]` also narrowed. Route handlers: 0 `Result[Any]` across 27 API files (2 intentional `# boundary:` for FastHTML FT components) |
| **Any Usage Policy** | Every `Any` is justified (Category C boundary) or eliminated (Categories A + B) |
| **Search Protocol Generics** | All 6 `DomainSearchOperations` extensions parameterized with domain model type (`Goal`, `Event`, etc.), not `Entity` |
| **Enum-Enforced Boundaries** | `UserRole`, `ExerciseScope`, `SubmissionModality`, `EntityStatus`, `FeedbackCategory`, `MasteryImpact`, `ProcessorType`, `Visibility`, `EnrichmentMode` — zero raw string comparisons for roles, scopes, modalities, status checks, feedback categorization, mastery scoring, processor types, visibility levels, enrichment modes |

**Key type aliases** (from `core/models/type_hints.py`): `Neo4jProperties`, `FilterParams`, `RelationshipMetadata`

**Protocol return TypedDicts** (from `core/ports/query_types.py`): 148 TypedDicts — 21 for inputs (filters, payloads) + 127 for outputs (domain stats, system health, teacher review, visualization configs, intelligence, life path, lateral relationships, activity reports, UserContext field shapes, context intelligence, graph entity, curriculum structure, curriculum backend Cypher returns, journal cleanup stats). New protocol methods and route handlers should return a specific model or TypedDict, not `Result[Any]`. Use `Result.fail(result)` to propagate errors across type boundaries (not `return result`).

**FastHTML boundary** (no type stubs): `from adapters.inbound.fasthtml_types import RouteDecorator, FastHTMLApp, Request, RouteList`

**`Any` policy:** Category A (eliminate), Category B (use specific type like `Neo4jProperties`), Category C (permanent boundary — add `# boundary:` comment).

**See:** `docs/architecture/TYPE_SAFETY_DESIGN_PHILOSOPHY.md` (why), `docs/patterns/TYPE_SAFETY_OVERVIEW.md` (how), `docs/patterns/ANY_USAGE_POLICY.md`, `docs/patterns/MYPY_TYPE_SAFETY_PATTERNS.md`

## Three-Tier Type System

**Core Principle:** "Pydantic at the edges, pure Python at the core"

| Tier | Type | Mutability | Purpose |
|------|------|------------|---------|
| External | Pydantic Models | N/A | Validation & serialization |
| Transfer | DTOs | Mutable | Data movement between layers |
| Core | Domain Models | **Frozen** | Immutable business entities |

### Domain-First Model Hierarchy

```
Entity (~18 fields: uid, entity_type, title, description, status, tags, ...)
+-- UserOwnedEntity(Entity) +3 fields (user_uid, visibility, priority)
|   +-- Task, Goal, Habit, Event, Choice, Principle  (Activity)
|   +-- LifePath, ActivityReport, Submission, ExerciseReport, JeInput, JeOutput
+-- Ku(Entity) -- atomic knowledge unit (namespace, ku_category, aliases, source, sel_category)
+-- Curriculum(Entity) +21 fields -> Lesson, PathStep, LearningPath, Exercise
+-- Resource(Entity) +7 fields (Curated content)
```

**DTOs** mirror the hierarchy: `EntityDTO -> UserOwnedDTO, KuDTO, CurriculumDTO -> LessonDTO, ResourceDTO`

**Key enums:** `EntityType` (18 values), `EntityStatus` (14 values) — both in `entity_enums.py`.

**Neo4j Multi-Label:** `:Entity` (universal) + domain label (`:Task`, `:Goal`, etc.). Backend uses `base_label=NeoLabel.ENTITY`.

**See:** `/docs/patterns/three_tier_type_system.md`, `/docs/patterns/DOMAIN_PATTERNS_CATALOG.md`, `/docs/tutorials/DATA_FLOW_WALKTHROUGH.md`

## User Roles & Authentication

**Core Principle:** "Graph-native authentication - all auth data in Neo4j"

| Role | Level | Permissions |
|------|-------|-------------|
| REGISTERED | 0 | Free trial |
| MEMBER | 1 | Paid subscription |
| TEACHER | 2 | Member + create curriculum |
| ADMIN | 3 | Teacher + user management |

```python
from adapters.inbound.auth import UserUID, require_authenticated_user
user_uid: UserUID = require_authenticated_user(request)

# Role protection (use named function, not lambda - SKUEL012)
def get_user_service():
    return services.user_service

@require_admin(get_user_service)
async def admin_route(request, current_user): ...
```

**See:** `/docs/patterns/AUTH_PATTERNS.md`

## Unified User Architecture

**Core Principle:** "UserContext is THE single object for understanding a user's complete state"

One object (~250 fields), built by one query (MEGA-QUERY), consumed by all intelligence services. Carries core identity from the `User` model (`user_uid`, `username`, `display_name`, `email`, `user_role`) — only fetch `User` directly when you need `user.preferences`.

| Depth | Method | Use Case |
|-------|--------|----------|
| Standard | `build()` | API responses, ownership checks (~150 fields) |
| Rich | `build_rich()` | Intelligence, daily planning (~250 fields) |

**ZPD Capstone:** `build_rich()` computes `context.zpd_assessment` (ZPDAssessment) as its final step — the pedagogical gravity well that synthesizes curriculum graph, behavioral signals, life path alignment, and compound evidence into recommended learning actions. FULL tier only. See: `core/services/zpd/zpd_service.py`.

**Canonical Location:** `/core/services/user/unified_user_context.py`

**See:** `/docs/architecture/UNIFIED_USER_ARCHITECTURE.md`

## Analytics Architecture

**Core Principle:** "Analytics aggregate, they don't create"

Analytics is a meta-service, not a domain. No Analytics nodes in Neo4j. READ-ONLY queries across all domains.

**See:** `/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md`

## Dynamic Enum Pattern

**Core Principle:** "Enums define behavior, services consume it"

Presentation logic lives inside enum methods. Magic numbers live in `/core/constants.py`.

```python
Priority.get_color()                           # "#F59E0B"
EntityStatus.is_terminal()                     # Terminal state check
EntityStatus.from_search_text("in progress")   # [EntityStatus.ACTIVE]
ContextHealthScore.get_numeric()               # 0.0-1.0 scoring
```

**Consolidated Enums:** `/core/models/enums/` — one file per domain. Core discriminators in `entity_enums.py`.

**See:** `/docs/architecture/ENUM_ARCHITECTURE.md`, `/docs/architecture/PRIORITY_CONFIDENCE_ARCHITECTURE.md`

## Activity DSL & Domain Enums

```python
# EntityType -- 18 domain types (multi-label :Entity nodes in Neo4j)
EntityType.from_string("task")       # -> EntityType.TASK or None
EntityType.from_string("knowledge")  # -> EntityType.KU (alias support)

# NonKuDomain -- 4 non-Entity domains
class NonKuDomain(str, Enum):
    FINANCE, GROUP, CALENDAR, LEARNING = ...
```

**See:** `/docs/dsl/DSL_SPECIFICATION.md`, `/docs/dsl/DSL_USAGE_GUIDE.md`

## Protocol-Based Architecture

**Core Principle:** "Right type at the right boundary — concrete for facades, protocol for thin services"

**Protocol Location:** `core/ports/` — 18 protocol files, 65+ protocols covering all domains.

**Route-facing type strategy:**

| Tier | Services | Type Used | Why |
|------|----------|-----------|-----|
| **Facade** | Tasks, Goals, Habits, Events, Choices, Principles, KU, PS, LP | Concrete class | Facade IS the contract (~50 delegation methods) |
| **Thin/ISP** | Groups, Submissions, Sharing, etc. | ISP protocol | Routes use a narrow slice; protocol makes it explicit |

`*Operations` protocols in `domain_protocols.py` are **backend-level** — they type `self.backend` inside `BaseService[Op, T]`, NOT service-level contracts.

**BackendOperations Protocol Hierarchy:**
```
BackendOperations[T]  <- THE protocol (UniversalNeo4jBackend implements this)
    +-- CrudOperations[T]
    +-- EntitySearchOperations[T]
    +-- RelationshipCrudOperations
    +-- RelationshipQueryOperations
    +-- GraphTraversalOperations
    +-- LowLevelOperations
```

**UserOperations Protocol Hierarchy (ISP-compliant):**
```
UserOperations  <- composed protocol (UserBackend implements this)
    +-- UserCrudOperations (6)      <- UserCoreService
    +-- UserLearningStateOperations (8)  <- UserProgressRecorderService
    +-- UserActivityOperations (3)  <- UserActivityService
```

**IntelligenceOperations Protocol Hierarchy (ISP-compliant):**
```
IntelligenceOperations  <- composed protocol
    +-- KnowledgeIntelligenceOperations (4)  <- ActivityKnowledgeIntelligenceService (shared)
    +-- DomainIntelligenceOperations (7)     <- Per-domain intelligence services
```

**See:** `/docs/patterns/protocol_architecture.md`, `/docs/patterns/BACKEND_OPERATIONS_ISP.md`

## Async/Sync Design Pattern

**Core Principle:** "Async for I/O, sync for computation"

| Layer | Async | Sync |
|-------|-------|------|
| Database/Persistence | 100% | 0% |
| Service Layer | ~95% | ~5% |
| Data Conversion | 0% | 100% |
| Domain Models | 0% | 100% |

**Rule:** If you need `await` inside the function, make it `async def`. Otherwise use `def`.

## Data Flow Architecture

```
Content to Storage:
Markdown -> UnifiedIngestionService -> KnowledgeUnit -> GraphNode -> Neo4j

Request Processing:
HTTP -> FastHTML Route -> Pydantic -> Service -> Domain -> Repository -> Neo4j
```

## Knowledge Substance Philosophy

**Core Principle:** "Applied knowledge, not pure theory"

SKUEL measures knowledge by how it's LIVED. Substance tracking: Habits (0.10, max 0.30), Journals (0.07, max 0.20), Choices (0.07, max 0.15), Principles (0.07, max 0.15), Events (0.05, max 0.25), Tasks (0.05, max 0.25). Total capped at 1.0.

**See:** `/docs/architecture/knowledge_substance_philosophy.md`

## Error Handling

**Core Principle:** "Use `Result[T]` internally, convert to HTTP at boundaries"

- Use `.is_error` (not `.is_err`) for failure checks
- Use `Result.fail(result)` to propagate errors across type boundaries (not `Result.fail(result.expect_error())`)
- Use `.expect_error()` only when you need to _read_ the error (logging, branching on category)
- Use `require_found(result, resource, uid)` for the fetch + not-found guard pattern in routes
- Use `Errors` factory for creating errors
- Six error types: Validation, NotFound, Database, Integration, Business, System
- **Narrow exceptions:** Use specific types from `core/utils/exception_types.py` (`NEO4J_EXCEPTIONS`, `LLM_EXCEPTIONS`, `DATA_CONVERSION_EXCEPTIONS`, etc.) instead of bare `except Exception`. Annotate intentional broad catches with `# intentional-broad:`, `# safety-net:`, or `# skuel-lint: disable=SKUEL017` (SKUEL017). ✅ Zero violations — persistence layer uses `NEO4J_EXCEPTIONS`, API/UI boundaries use `# safety-net:` annotations.
- **Inline suppression:** `# skuel-lint: disable=SKUELXXX -- <reason>` (line) or `# skuel-lint: disable-file=SKUELXXX -- <reason>` (file-level). Supported: SKUEL005, SKUEL011, SKUEL012, SKUEL015, SKUEL017.

**See:** `/docs/patterns/ERROR_HANDLING.md`

## API Input Validation

**Core Principle:** "Validate at boundaries, fail fast with clear errors"

- **Query Parameters (GET):** Shared helpers in `route_helpers.py` (`parse_bool_query_param`, `parse_date_query_param`, `parse_csv_query_param`, `parse_pagination_params`, etc.)
- **JSON Bodies (POST):** Pydantic request models (auto-validated)
- **Request Model Location:** `core/models/{domain}/{domain}_request.py`
- **Error Codes:** Query params -> 400 Bad Request, JSON bodies -> 422 Unprocessable Entity

**See:** `/docs/patterns/API_VALIDATION_PATTERNS.md`

## Ownership Verification

**Core Principle:** "Return 'not found' for entities the user doesn't own"

| Pattern | Domains | Create | Read | Ownership Check |
|---------|---------|--------|------|-----------------|
| **USER_OWNED** | Activities, Submissions | User | Owner only | Yes (returns 404) |
| **SHARED** | KU, PS, LP | Admin only | All users | No (public) |
| **ADMIN_ONLY** | Finance | Admin only | Admin only | No (admin-gated) |

**Route helpers** (`from adapters.inbound.route_factories`):
- `verify_entity_ownership(service, uid, user_uid, domain)` — API routes. Returns error `Result` or `None`.
- `require_owned_entity(service, uid, user_uid, entity_name)` — UI routes. Returns `(entity, None)` or `(None, Response)`.

**See:** `/docs/patterns/OWNERSHIP_VERIFICATION.md`

## Content Origin Tiers

| Tier | ContentOrigin | EntityTypes | Description |
|------|--------------|---------|-------------|
| A | `CURATED` | Resource | Admin-curated content |
| B | `CURRICULUM` | Curriculum, PS, LP | Curriculum structure |
| C | `USER_CREATED` | Activities, Submission, JeInput, JeOutput, Life Path | User-generated |
| D | `REPORT` | ActivityReport, ExerciseReport | Analysis/reports |

`ContentScope` controls access, `ContentOrigin` classifies purpose. Derived from `EntityType`.

## Content Sharing

**Core Principle:** "Three-level visibility with relationship-based access control"

**Visibility:** PRIVATE (default) -> SHARED (SHARES_WITH relationship) -> PUBLIC (portfolio)

**Three Sharing Modes:** Manual sharing, Assignment auto-sharing (ADR-040), Group sharing (SHARED_WITH_GROUP)

**Service:** `from core.services.sharing import UnifiedSharingService` — entity-agnostic, methods: `share()`, `check_access()`, `set_visibility()`, group sharing.

**Teacher Review:** `TeacherReviewService` — `get_review_queue()`, `submit_report()`, `request_revision()`, `approve_report()`

**Graph:** `(user)-[:SHARES_WITH {shared_at, role, share_version}]->(entity)`, `(entity)-[:SHARED_WITH_GROUP]->(group)`

**See:** `/docs/patterns/SHARING_PATTERNS.md`, `/docs/decisions/ADR-038-content-sharing-model.md`, `/docs/decisions/ADR-040-teacher-assignment-workflow.md`

## Generic Programming Patterns

**Core Principle:** "One generic backend serves all 21 entity types"

```python
# Generic backend -- T constrained by DomainModelProtocol
backend = UniversalNeo4jBackend[Task](driver, NeoLabel.TASK, Task, base_label=NeoLabel.ENTITY)

# Generic service base -- B=protocol, T=domain model
class GoalsCoreService(BaseService[GoalsOperations, Goal]):
    _config = create_activity_domain_config(...)

# Generic type aliases (core/models/type_hints.py)
type Validator[T] = Callable[[T], list[str]]
type EntityFilter[T] = Callable[[T], bool]
type Scorer[T] = Callable[[T], Score]
```

**See:** `docs/patterns/TYPE_SAFETY_OVERVIEW.md`, `/docs/patterns/query_architecture.md`

## Infrastructure Helpers

**Location:** `/core/services/infrastructure/`

| Helper | Purpose |
|--------|---------|
| `PrerequisiteChecker` | Unified prerequisite checking (returns `PrerequisiteResult` with score, is_ready, blocking_reasons) |
| `LearningAlignmentBridge` | LP integration for any domain |
| `SemanticRelationshipLinker` | Semantic relationship ops |
| `RelationshipCreator` | Cross-domain rel creation |

## Fail-Fast Dependency Philosophy

**Core Principle:** "All dependencies are REQUIRED - no graceful degradation"

**Required at bootstrap:** Neo4j, OpenAI, Deepgram. **Only 2 valid `None` cases:** True circular dependencies, unimplemented features (explicit TODOs).

## UI Component Pattern

**Core Principle:** "BasePage for consistency, custom layouts for special cases"

| Page Type | Use Case |
|-----------|----------|
| STANDARD | Most pages (centered content) |
| CUSTOM | Full-width, page manages layout (SidebarPage) |

- Routes in `/adapters/inbound/*_routes.py`, UI in `/ui/`, Static in `/static/`
- Navbar has icon links: **⚛️** (Knowledge, `/ku`) + **Tasks** (check-square icon, `/tasks`) + **Goals** (target icon, `/goals`) + **⇄** (Submissions, `/submissions`) + avatar **U** (click → `/profile`; hover → Activity dropdown with Habits, Events, Choices, Principles) + logout icon. Curriculum and Study navbar dropdowns removed (2026-03-29).
- `/ku` is the Knowledge index — flat Ku listing with bookmarks + latest sidebar (pin button for bookmarking). `/profile` is THE main hub — a **live actionable hub** (not a card grid): Knowledge (bookmarked + recent Kus with mastery %), Lessons (actively studying), Exercises (assigned work with inline Submit buttons), Submissions (tabbed: My Submissions | Submit | Request Report — Alpine.js tabs + HTMX lazy-loaded fragments), Reports (HTMX lazy-loaded summaries), Nous (community feed placeholder). Data sourced from `UserContext.build_rich()`. Tasks (`/tasks`) and Goals (`/goals`) have read-focused views with cross-domain connections, detail pages, and `EntityRelationshipsSection`. Other activity data viewed via ActivityReport at `/activity-reports`. `/lessons` lists all lessons with learning-state-aware enrollment buttons (Start Lesson / In Progress / Mastered); clicking a lesson navigates to `/lesson/{uid}/details` — a full reading page with markdown content, TOC sidebar, learning objectives, metadata badges, and action buttons (Start Lesson, Mark as Read, Bookmark) using `BasePage(CUSTOM)`. Other curriculum sub-pages (`/path-steps`, `/learning-paths`, `/exercises`) and study sub-pages (`/submit`, `/submissions`, `/exercise-reports`, `/activity-reports`, `/submit-activity-report`) use `BasePage(STANDARD)` — **no sidebars** (curriculum + study sidebars removed 2026-03-29). Old `/submissions/*`, `/learn/*`, and `/ui/exercises` UI paths redirect 301 to the new top-level routes. `/transfer` retired (2026-03-29) — content moved to `/profile` Submissions section + entity-typed routes. `/upload` is the user-facing bulk upload page — drag-and-drop file upload with progress, uses `BasePage(STANDARD)`.

**Shared Components:** `PageHeader` (page title + subtitle + actions — adopted across all 6 Activity Domain dashboards, Study, Curriculum, Admin, Analytics, Calendar, and LifePath), `EmptyState` (empty lists — adopted across ~45 locations), `CardGenerator` (THE single card component — detail cards, list cards, teaching rows, insight cards; supports subtitle, metadata, extra, header_badges with FT pass-through), `StatsGrid`/`StatItem` (statistics grids), `StatusBadge` (delegates to `EntityStatus.get_badge_class()` for all 14 statuses), `render_error_banner`/`render_inline_error` (accessible error states — adopted across 25+ route files). All in `/ui/patterns/` or `/ui/feedback.py`.

**Page Contexts:** Per-domain TypedDicts in `/ui/page_contexts.py` define route→UI contracts with typed entities (`list[Task]`, etc.) and `total=True` for required fields. `render_list_view(ctx)` is the only signature — no dual-path. NOT in `core/ports/` — page contexts are UI concerns.

**Key Files:** `/ui/layouts/base_page.py`, `/ui/layouts/navbar.py`, `/ui/patterns/sidebar.py`, `/ui/patterns/` (PageHeader, form_generator, card_generator, etc.), `/ui/page_contexts.py`, `/ui/tokens.py` (spacing/layout), `/ui/palette.py` (centralized hex colors for visualization), `/ui/visualization/` (Chart.js/Vis.js/Gantt presentation adapters)

**See:** `/docs/patterns/UI_COMPONENT_PATTERNS.md`, `/docs/ui/COMPONENT_CATALOG.md`

## Alpine.js Architecture

| Layer | Tool | Purpose |
|-------|------|---------|
| UI State | Alpine.js | Modals, toggles, filtering |
| Server Communication | HTMX | Form submissions, loading |
| Pure Presentation | FastHTML | HTML generation |

**Key Files:** `/static/js/skuel.js` (ALL Alpine.data() components), `/static/vendor/alpinejs/alpine.3.14.8.min.js`

## PWA Mobile Strategy

**Core Principle:** "One format (HTML), installable everywhere — no app store dependency"

| Capability | Implementation |
|------------|---------------|
| Installability | Web app manifest (`/manifest.json`) |
| Offline support | Service worker (network-first HTML, cache-first static) |
| Offline indicator | `offlineIndicator` Alpine.js component + fixed bottom banner |
| Push notifications | Web Push API (future) |

**Key Files:** `static/manifest.json`, `static/service-worker.js`, `static/offline.html`, `ui/theme.py` (`pwa_headers()`)

**See:** `/docs/decisions/ADR-050-pwa-mobile-strategy.md`

## Lateral Relationships & Vis.js Graph Visualization

All 9 domains deployed (Tasks, Goals, Habits, Events, Choices, Principles, KU, PS, LP).

**Three Components:** BlockingChainView (vertical flow), AlternativesComparisonGrid (side-by-side), RelationshipGraphView (Vis.js force-directed graph).

**6 Lateral Relationship Types:** BLOCKS/BLOCKED_BY, PREREQUISITE_FOR/DEPENDS_ON, ALTERNATIVE_TO, COMPLEMENTARY_TO, SIBLING, RELATED_TO.

**Usage:** `EntityRelationshipsSection(entity_uid=entity.uid, entity_type="tasks")` — add to any detail page.

**See:** `/docs/architecture/RELATIONSHIPS_ARCHITECTURE.md`, `/docs/patterns/LATERAL_RELATIONSHIPS_VISUALIZATION.md`

## Event-Driven Architecture

**Core Principle:** "Events over dependencies"

**Event Naming:** `{domain}.{action}` (e.g., `task.completed`, `goal.achieved`)

**Auto-timestamp:** `BaseEvent.occurred_at` defaults to `datetime.now()` via `kw_only` field — never pass it manually. Override only for tests or event replay.

```python
from core.events.utils import publish_event
await publish_event(self.event_bus, TaskCompleted(task_uid=uid, user_uid=user_uid), self.logger)
```

**Location:** `/core/events/` — 65+ events across all domains

## 100% Dynamic Backend Pattern

**Core Principle:** "The plant grows on the lattice"

**4-Layer Architecture:** `*Operations protocol -> *Backend subclass -> *Service facade -> sub-services`

**Domain Backends** (19 in `domain_backends.py`): TasksBackend, EventsBackend, GoalsBackend, HabitsBackend, ChoicesBackend, PrinciplesBackend, LessonBackend, KuBackend, SubmissionsBackend, SharingBackend, LpBackend, ExerciseBackend, RevisedExerciseBackend, FormTemplateBackend, FormSubmissionBackend, ActivityReportBackend, LateralRelationshipBackend, GroupBackend, NotificationBackend.

Domain-specific relationship Cypher belongs on the domain backend. Cross-domain aggregation stays in services. Services call `self.backend.method_name()` — never inline Cypher via `execute_query()`. Use `cascade=True` for Activity Domains.

**`UniversalNeo4jBackend` is the hexagonal boundary** — Neo4j-specific code stops here. Neo4j is a committed architectural choice (ADR-044), not a swappable adapter.

**File Layout:** `universal_backend.py` is a shell; methods live in 6 mixin files: `_crud_mixin.py`, `_search_mixin.py`, `_relationship_query_mixin.py`, `_relationship_crud_mixin.py`, `_user_entity_mixin.py`, `_traversal_mixin.py`. `_hierarchy_mixin.py` provides `_HierarchyMixin` — generic parent-child hierarchy ops shared by all 6 Activity Domain backends (parameterized via `HierarchyConfig`). `LessonBackend` is further decomposed into 5 domain-specific mixins: `_organizes_mixin.py` (ORGANIZES relationships), `_learning_state_mixin.py` (VIEWED/IN_PROGRESS/MASTERED/BOOKMARKED/MARKED_AS_READ), `_semantic_mixin.py` (semantic relationships + graph analysis), `_knowledge_context_mixin.py` (context, discovery, readiness), `_adaptive_mixin.py` (practice, search, adaptive mastery). Shared validation helpers (`_validate_rel_name`, `_ALLOWED_ORDER_BY`) in `_backend_helpers.py`.

**See:** `/docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md`

## Search & Query Architecture

**Core Principle:** "SearchRouter is THE single path for all external search access"

**Three Query Systems:** UnifiedQueryBuilder (default), QueryBuilder (optimization), CypherGenerator (pure Cypher).

**Searchable Domains:** All 14 — Task, Goal, Habit, Event, Choice, Principle, Lesson, PS, LP, Exercise, RevisedExercise, Submission, FormTemplate, FormSubmission.

**DomainConfig** is THE single source of truth for BaseService configuration: `dto_class`, `model_class`, `search_fields`, `search_order_by`, `category_field`, `temporal_exclude_statuses`, `supports_user_progress`, `user_ownership_relationship`, `graph_enrichment_patterns`, etc.

**Factory functions:** `create_activity_domain_config()`, `create_curriculum_domain_config()`

**See:** `/docs/patterns/query_architecture.md`, `/docs/architecture/SEARCH_ARCHITECTURE.md`

## BaseService Architecture

**7 Mixins:** ConversionHelpers, CRUD, Search, Relationships, TimeQuery, UserProgress, Context.

**6 Activity Domains:** Tasks, Goals, Habits, Events, Choices, Principles. All use facade pattern with explicit `async def` delegation methods. Factory: `create_common_sub_services()`. Active sub-services: `.core`, `.search`, `.ai` (optional, FULL tier). **Shared:** `ActivityKnowledgeIntelligenceService` (`core/services/knowledge/`) provides domain-agnostic knowledge intelligence (suggestions, prerequisites, learning opportunities) for all 6 domains — wired into every facade via `self.knowledge_intelligence`.

**Essential Docs:** `/docs/guides/BASESERVICE_QUICK_START.md`, `/docs/reference/SUB_SERVICE_CATALOG.md`, `/docs/reference/BASESERVICE_METHOD_INDEX.md`, `/docs/architecture/SERVICE_TOPOLOGY.md`

## Unified Content Ingestion

**Core Principle:** "The hips of SKUEL — one of three foundational systems"

One-way pipeline: Markdown/YAML -> Neo4j. Dry-run mode, incremental ingestion, ingestion history, WebSocket progress, edge ingestion (relationship YAML files), full PS field wiring. 13 of 21 entity types are file-ingestible. **Markdown files require an explicit `type` field in frontmatter** — no silent defaults. **UID prefix validation** rejects UIDs that don't match the expected prefix for their entity type.

**Default Vault:** `data/vault/` (`/home/mike/skuel/app/data/vault/`) — the default folder for all ingestion content. Ku YAMLs (`ku_*.yaml`), Lesson YAMLs (`lesson_*.yaml`), Exercise YAMLs (`exercise_*.yaml`), edge YAMLs (`edges/edge_*.yaml`), and markdown files live here. Configurable via `INGESTION_PATH` env var.

**Import:** `from core.services.ingestion import UnifiedIngestionService`

**API:** `POST /api/ingest/file`, `POST /api/ingest/directory`, `POST /api/ingest/vault`, `POST /api/ingest/domain/{domain_name}`, `WS /ws/ingest/progress/{operation_id}`

**Per-User Upload:** `UserUploadService` enables authenticated users to bulk-upload content into isolated per-user vaults. Files are validated, stored under `VaultConfig.user_vaults_root/{user_uid}/`, and ingested via `UnifiedIngestionService`. **API:** `POST /api/upload` (file upload), **UI:** `GET /upload` (upload page), `POST /upload/files` (form submission). Import: `from core.services.ingestion.user_upload_service import UserUploadService`.

**See:** `/docs/architecture/CORE_SYSTEMS_ARCHITECTURE.md`, `/docs/patterns/UNIFIED_INGESTION_GUIDE.md`

## Curriculum Grouping Patterns

| Pattern | UID Format | Topology | Metaphor |
|---------|-----------|----------|----------|
| Ku | `ku_{slug}_{random}` | Atom | A single concept/fact |
| Lesson | `l_{slug}_{random}` | Unit | A unit for learning (composes Kus) |
| PS | `ps:{random}` | Collection | A collection of lessons |
| LP | `lp:{random}` | Path | An ordered sequence of lesson collections |

**Two Paths to Knowledge:** PS Path (structured, linear) and ORGANIZES Path (unstructured, graph, learner-directed). MOC is emergent identity — any Entity with ORGANIZES relationships.

**See:** `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md`

## KU UID Format

**Format:** `ku_{slug}_{random}` (flat UIDs, hierarchy in ORGANIZES relationships)

Hierarchy via `(parent)-[:ORGANIZES {order, importance}]->(child)` relationships. Multiple parents possible.

**See:** `/docs/decisions/ADR-013-ku-uid-flat-identity.md`, `/docs/patterns/UNIVERSAL_HIERARCHICAL_PATTERN.md`

## EntityTimestampMixin

Use for consistent timestamp/metadata handling: `timestamp_properties()`, `update_properties()`, `set_entity_metadata()`.

**See:** `/docs/patterns/entity_timestamp_mixin.md`

## Code Quality & Formatting

**Formatting:** Ruff. Run `./dev format` to format, `./dev quality` for full checks.

**Key SKUEL Linter Rules:**
- SKUEL001: No APOC in domain services [CRITICAL]
- SKUEL003: Use `.is_error` (not `.is_err`)
- SKUEL007: Use `Errors` factory
- SKUEL011: No `hasattr()` — use Protocol/isinstance/getattr
- SKUEL012: No lambda expressions — use named functions
- SKUEL013: Use `RelationshipName` enum
- SKUEL014: Use `EntityType`/`NonKuDomain` enum
- SKUEL015: No `print()` in production
- SKUEL016: No stale Poetry references — SKUEL uses uv
- SKUEL017: No bare `except Exception` — use specific types from `exception_types.py`

**MyPy:** `./dev quality` enforces **0 MyPy errors**. Per-module strictness overrides in `pyproject.toml`. Four globally-disabled codes: `type-var`, `arg-type`, `var-annotated`, `type-arg`. `assignment` is **enabled** — catches trailing-comma tuple bugs and real type mismatches. `core.services.*`, `core.ports.*` enforce `disallow_untyped_defs`. Domain backends suppress `misc` (MRO mixin conflicts). Narrow Neo4j property types with `int()`/`float()`/`str()` casts before arithmetic. Every new `Any` needs a `# boundary:` comment or should use a specific type.

**See:** `/docs/patterns/linter_rules.md`, `docs/patterns/mypy_pragmatic_strategy.md`

## Observability & Monitoring

**Core Principle:** "Prometheus tracks system health, Neo4j tracks user behavior"

- **Prometheus UI**: http://localhost:9090
- **Grafana Dashboards**: http://localhost:3000
- **Metrics Endpoint**: http://localhost:5001/metrics

47 metrics across 9 categories, 13 production alerts, 4 Grafana dashboards. AI/LLM cost tracking included.

**See:** `@prometheus-grafana` skill, `monitoring/README.md`, `OBSERVABILITY_PHASE1_COMPLETE.md`

## Logging Patterns

| Context | Tool |
|---------|------|
| Production runtime | `logger.*()` |
| Interactive CLI | `print()` |

```python
from core.utils.logging import get_logger
logger = get_logger("skuel.services.tasks")
```

## Graph-Native Comment Standard

Use `# GRAPH-NATIVE:` prefix for comments about relationship data stored as Neo4j edges.

**See:** `/docs/patterns/GRAPH_NATIVE_PLACEHOLDERS.md`

## HTTP Status Codes

POST (Create) -> 201, GET/PUT/DELETE -> 200, POST (Action) -> 200

## Route Factories

| Factory | Purpose |
|---------|---------|
| CRUDRouteFactory | Standard CRUD |
| StatusRouteFactory | Status changes |
| OwnershipRouteFactory | Ownership-verified domain routes (GET/POST with ownership checks) |
| CommonQueryRouteFactory | Query patterns |
| AnalyticsRouteFactory | Analytics |
| QuickAddRouteFactory | Quick-add form handling (6 domains) — removed for Activity Domains |
| DashboardUIFactory | Dashboard + view fragments + list fragment (6 domains) — removed for Activity Domains |

**UI Route Factories** (config + callables pattern): `QuickAddRouteFactory` and `DashboardUIFactory` eliminate UI route boilerplate across all 6 Activity Domains. Each domain provides named callables for domain-specific behavior; the factory handles auth, error handling, view dispatch, and page wrapping. `DashboardUIConfig` (frozen dataclass) captures variation points: filter parsing, service calls, view rendering, context building, and list fragment rendering.

All support `scope=ContentScope.USER_OWNED` (default) or `ContentScope.SHARED` (curriculum, with `require_role=UserRole.ADMIN`). `role_gates_reads=False` allows role-gated mutations with open reads (Groups pattern). Scope and role are orthogonal — both ownership verification and role checks apply independently.

**See:** `/docs/patterns/ROUTE_FACTORIES.md`

## Domain Route Configuration

**Core Principle:** "Configuration over code for route registration"

DomainRouteConfig eliminates route wiring boilerplate. Activity Domains use `create_activity_domain_route_config()` for config-driven CRUD/Query/Intelligence factories. Activity Domains now use manual route files (e.g., `tasks_routes.py`, `goals_routes.py`) for their read-focused UI pattern.

```python
TASKS_CONFIG = create_activity_domain_route_config(
    domain_name="tasks",
    primary_service_attr="tasks",
    api_factory=create_tasks_api_routes,
    ui_factory=create_tasks_ui_routes,
    create_schema=TaskCreateRequest,
    update_schema=TaskUpdateRequest,
    uid_prefix="task",
    ...
)

def create_tasks_routes(app, rt, services, _sync_service=None):
    return register_domain_routes(app, rt, services, TASKS_CONFIG)
```

**Adoption:** 42 of 46 route files. **Patterns proven:** Standard, API-only, UI-only, Multi-factory, Config-Driven. Upload routes (`upload_routes.py`) use DomainRouteConfig registration.

**See:** `/docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md`

## FastHTML Best Practices

- Query parameters over path parameters (`/tasks/get?uid=...`)
- POST for all mutations
- Type hints for automatic parameter extraction
- **Critical:** Do NOT use `routes = []` / `routes.append()` with `@rt()`. The decorator registers immediately.

**See:** `/docs/patterns/FASTHTML_ROUTE_REGISTRATION.md`

## Intelligence Services Architecture

**Core Principle:** "Graph analytics separated from AI — app runs without LLM dependencies"

| Layer | Base Class | Dependencies |
|-------|------------|--------------|
| Analytics | `BaseAnalyticsService` | Graph + Python (NO AI) |
| AI | `BaseAIService` | LLM + Embeddings (optional) |

**Intelligence Tier Toggle (ADR-043):** `INTELLIGENCE_TIER=core` ($0, analytics only) vs `INTELLIGENCE_TIER=full` (default, everything + AI). All 6 Activity Domain facades + 3 Curriculum facades have `.ai` (optional, `None` when `INTELLIGENCE_TIER=core`).

**UserContextIntelligence (Central Hub):** `get_ready_to_work_on_today()`, `get_optimal_next_path_steps()`, `calculate_life_path_alignment()`, `get_schedule_aware_recommendations()`

**See:** `/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md`, `/docs/decisions/ADR-043-intelligence-tier-toggle.md`

## Embedding Text Extraction

**Location:** `/core/utils/embedding_text_builder.py`

```python
from core.utils.embedding_text_builder import build_embedding_text
text = build_embedding_text(EntityType.TASK, {"title": "Fix bug", "description": "Details"})
```

**Supported:** All 13 content-bearing entity types — Lesson, Ku, Exercise, PathStep, LearningPath, Resource, RevisedExercise, Task, Goal, Habit, Event, Choice, Principle. Field mappings in `EMBEDDING_FIELD_MAPS`.

## Quick Reference: Key Files

| Purpose | Location |
|---------|----------|
| Service composition | `/services_bootstrap/` (package: `compose.py` orchestration, `_container.py` Services dataclass) |
| Base service | `/core/services/base_service.py` |
| Base analytics | `/core/services/base_analytics_service.py` |
| Knowledge intelligence | `/core/services/knowledge/` |
| Domain enums | `/core/models/enums/` |
| Protocols | `/core/ports/` |
| Generic backend | `/adapters/persistence/neo4j/universal_backend.py` |
| Event bus | `/core/events/event_bus.py` |
| Exception types | `/core/utils/exception_types.py` |
| Error boundary | `/core/utils/error_boundary.py` |
| Result helpers | `/adapters/inbound/result_helpers.py` (`require_found`) |
| Route factories | `/adapters/inbound/route_factories/` |
| User upload service | `/core/services/ingestion/user_upload_service.py` |
| Page contexts | `/ui/page_contexts.py` |
| Deepgram config | `/config/deepgram.toml` |
| ADRs | `/docs/decisions/` |
| Patterns | `/docs/patterns/` |
| Architecture | `/docs/architecture/` |
| Troubleshooting | `/docs/TROUBLESHOOTING.md` |

## Troubleshooting

**Server Won't Start:** Port in use (`lsof -ti:8000 | xargs kill -9`), import errors (check `fasthtml.common`).

**Routes Return 404:** Check both API and UI routes registered in `bootstrap.py`. Distinguish 401 (auth) vs 404 (missing).

**Type Errors:** Forward reference unions use `Optional["Type"]` not `"Type" | None`.

**See:** `/docs/TROUBLESHOOTING.md`
