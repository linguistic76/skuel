- We use poetry for package management and for running files.

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

- **Article** (`EntityType.ARTICLE`, extends `Curriculum`) — essay-like teaching composition. Services in `core/services/article/`.
- **Ku** (`EntityType.KU`, extends `Entity`) — atomic knowledge unit. Lightweight ontology/reference node. Services in `core/services/ku/`.
- **Composition:** `(Article)-[:USES_KU]->(Ku)` — Articles compose atomic Kus into narrative.
- **Learning loop:** Article -> Exercise -> ExerciseSubmission -> ExerciseReport -> RevisedExercise -> ...

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

**Stage 1 (Current):** Docker-based Neo4j (`bolt://localhost:7687`). Plugins: GenAI + APOC (meta only). APOC scoped to `apoc.meta.*` — domain services use pure Cypher (SKUEL001).

**Stage 2:** Droplet (Neo4j) + App Platform (app). Same config as local Docker.

**Stage 3:** AuraDB. Database-level API keys, `neo4j+s://` connection, automated backups.

**Code is environment-agnostic** — only `.env` configuration changes across stages.

**See:** `/docs/deployment/DO_MIGRATION_GUIDE.md`, `/docs/deployment/AURADB_MIGRATION_GUIDE.md`, `/docs/development/GENAI_SETUP.md`

## Skills & Documentation Cross-Reference

**Core Principle:** "Local curated docs first, external lookup only when missing"

See [CROSS_REFERENCE_INDEX.md](/docs/CROSS_REFERENCE_INDEX.md) for the complete skill-to-documentation mapping.

**Key skill categories:** Foundation (python, pydantic, ui-css, chartjs), Web Framework (fasthtml, domain-route-config, ui-browser), UX (accessibility-guide, skuel-ui, ui-error-handling), Database (neo4j-cypher-patterns, neo4j-genai-plugin), Infrastructure (docker, prometheus-grafana), Architecture (result-pattern, base-analytics-service, base-ai-service, prompt-templates, learning-loop, skuel-search-architecture, user-context-intelligence), Security (security), Testing (pytest), Mobile (hyperview), Meta (docs-skills-evolution).

**Total:** 27 skills with comprehensive documentation mappings.

## Documentation Architecture

**Single Source of Truth:** `/home/mike/skuel/app/docs/`
- `docs/decisions/` - Architecture Decision Records (ADRs, 43 total)
- `docs/patterns/` - Implementation patterns
- `docs/architecture/` - System architecture
- `docs/INDEX.md` - Complete documentation index

**CLAUDE.md Purpose:** Quick-reference with pointers to detailed docs. Sections should be 10-20 lines max with `**See:**` pointers.

**Content Location (different purpose):** `/home/mike/0bsidian/skuel/docs/` contains Knowledge Unit content for ingestion, NOT technical documentation.

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
| Article | Teaching composition (essay-like) | `a_{slug}_{random}` | Admin-created, shared |
| Ku | Atomic knowledge unit | `ku_{slug}_{random}` | Admin-created, shared |
| Resource | Curated content (books, talks, films) | N/A | Admin-created, shared |
| LearningStep | Step in a learning path | `ls:{random}` | Admin-created, shared |
| LearningPath | Ordered sequence of steps | `lp:{random}` | Admin-created, shared |
| Exercise | Instruction template for practicing curriculum | N/A | Admin-created, shared |
| RevisedExercise | Targeted revision instructions after feedback | `re_{slug}_{random}` | Teacher-owned |
| ExerciseSubmission | Student work submitted against an Exercise | `es_{slug}_{random}` | User-owned |
| JournalSubmission | Reflective writing (voice/text) | N/A | User-owned |
| ActivityReport | Report about activity patterns over time | `ar_{random}` | User-owned |
| ExerciseReport | Teacher or AI report on an exercise submission | `sr_{random}` | User-owned |
| JournalReport | AI report on a journal submission | `sr_{random}` | User-owned |
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

- **Activity (6):** Task, Goal, Habit, Event, Choice, Principle — facade pattern with `.core`, `.search`, `.intelligence` sub-services. Created via `create_common_sub_services()`. Events additionally has integration sub-services; **Calendar** cross-cutting system handles scheduling aggregation.
- **Curriculum (5):** Article, Ku, LearningStep, LearningPath, Exercise — `ContentScope.SHARED`, admin creates, all users read.
- **Submissions/Reports (5):** ExerciseSubmission, JournalSubmission, ExerciseReport, JournalReport, ActivityReport — the learning loop. Services in `core/services/submissions/` + `core/services/report/`.
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
| **Any Usage Policy** | Every `Any` is justified (Category C boundary) or eliminated (Categories A + B) |

**Key type aliases** (from `core/models/type_hints.py`): `Neo4jProperties`, `FilterParams`, `RelationshipMetadata`

**FastHTML boundary** (no type stubs): `from adapters.inbound.fasthtml_types import RouteDecorator, FastHTMLApp, Request, RouteList`

**`Any` policy:** Category A (eliminate), Category B (use specific type like `Neo4jProperties`), Category C (permanent boundary — add `# boundary:` comment).

**See:** `docs/patterns/TYPE_SAFETY_OVERVIEW.md`, `docs/patterns/ANY_USAGE_POLICY.md`, `docs/patterns/MYPY_TYPE_SAFETY_PATTERNS.md`

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
|   +-- LifePath, ActivityReport, Submission -> Journal, SubmissionReport
+-- Ku(Entity) -- atomic knowledge unit (namespace, ku_category, aliases, source)
+-- Curriculum(Entity) +21 fields -> Article, LearningStep, LearningPath, Exercise
+-- Resource(Entity) +7 fields (Curated content)
```

**DTOs** mirror the hierarchy: `EntityDTO -> UserOwnedDTO, KuDTO, CurriculumDTO -> ArticleDTO, ResourceDTO`

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

One object (~250 fields), built by one query (MEGA-QUERY), consumed by all intelligence services.

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

**Protocol Location:** `core/ports/` — 10 protocol files, 60+ protocols covering all domains.

**Route-facing type strategy:**

| Tier | Services | Type Used | Why |
|------|----------|-----------|-----|
| **Facade** | Tasks, Goals, Habits, Events, Choices, Principles, KU, LS, LP | Concrete class | Facade IS the contract (~50 delegation methods) |
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

SKUEL measures knowledge by how it's LIVED. Substance tracking: Habits (0.10, max 0.30), Journals (0.07, max 0.20), Choices (0.07, max 0.15), Events (0.05, max 0.25), Tasks (0.05, max 0.25).

**See:** `/docs/architecture/knowledge_substance_philosophy.md`

## Error Handling

**Core Principle:** "Use `Result[T]` internally, convert to HTTP at boundaries"

- Use `.is_error` (not `.is_err`) for failure checks
- Use `Errors` factory for creating errors
- Six error types: Validation, NotFound, Database, Integration, Business, System

**See:** `/docs/patterns/ERROR_HANDLING.md`

## API Input Validation

**Core Principle:** "Validate at boundaries, fail fast with clear errors"

- **Query Parameters (GET):** Helper functions (`parse_bool_param`, `validate_time_window`)
- **JSON Bodies (POST):** Pydantic request models (auto-validated)
- **Request Model Location:** `core/models/{domain}/{domain}_request.py`
- **Error Codes:** Query params -> 400 Bad Request, JSON bodies -> 422 Unprocessable Entity

**See:** `/docs/patterns/API_VALIDATION_PATTERNS.md`

## Ownership Verification

**Core Principle:** "Return 'not found' for entities the user doesn't own"

| Pattern | Domains | Create | Read | Ownership Check |
|---------|---------|--------|------|-----------------|
| **USER_OWNED** | Activities, Submissions | User | Owner only | Yes (returns 404) |
| **SHARED** | KU, LS, LP | Admin only | All users | No (public) |
| **ADMIN_ONLY** | Finance | Admin only | Admin only | No (admin-gated) |

**See:** `/docs/patterns/OWNERSHIP_VERIFICATION.md`

## Content Origin Tiers

| Tier | ContentOrigin | EntityTypes | Description |
|------|--------------|---------|-------------|
| A | `CURATED` | Resource | Admin-curated content |
| B | `CURRICULUM` | Curriculum, LS, LP | Curriculum structure |
| C | `USER_CREATED` | Activities, Submission, Journal, Life Path | User-generated |
| D | `REPORT` | ActivityReport, SubmissionReport | Analysis/reports |

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

**Core Principle:** "One generic backend serves all 18 entity types"

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
| `PrerequisiteHelper` | Unified prerequisite checking (returns `PrerequisiteResult` with score, is_ready, blocking_reasons) |
| `LearningAlignmentHelper` | LP integration for any domain |
| `SemanticRelationshipHelper` | Semantic relationship ops |
| `RelationshipCreationHelper` | Cross-domain rel creation |

## Fail-Fast Dependency Philosophy

**Core Principle:** "All dependencies are REQUIRED - no graceful degradation"

**Required at bootstrap:** Neo4j, OpenAI, Deepgram. **Only 2 valid `None` cases:** True circular dependencies, unimplemented features (explicit TODOs). **Exception:** `CalendarService` is an aggregation meta-service with optional dependencies.

## UI Component Pattern

**Core Principle:** "BasePage for consistency, custom layouts for special cases"

| Page Type | Sidebar | Use Case |
|-----------|---------|----------|
| STANDARD | None | Most pages |
| HUB | Left (w-64) | Admin Dashboard |
| CUSTOM | STANDARD + custom | Profile Hub |

- Routes in `/adapters/inbound/*_routes.py`, UI in `/ui/`, Static in `/static/`
- Navbar has icon links: **A** (Activities, `/activities`) and **L** (Learn, `/learn`) + avatar **U** (Profile, `/profile`)
- `/profile` is lean (Focus + Steady + Settings). Activity domains at `/activities/{domain}` with sidebar. Learning at `/learn` with Study/Practice/Pathways sidebar.
- All sidebars unified into `SidebarPage` from `ui/patterns/sidebar.py`

**Key Files:** `/ui/layouts/base_page.py`, `/ui/layouts/navbar.py`, `/ui/patterns/sidebar.py`, `/ui/patterns/` (PageHeader, form_generator, card_generator, etc.)

**See:** `/docs/patterns/UI_COMPONENT_PATTERNS.md`

## Alpine.js Architecture

| Layer | Tool | Purpose |
|-------|------|---------|
| UI State | Alpine.js | Modals, toggles, filtering |
| Server Communication | HTMX | Form submissions, loading |
| Pure Presentation | FastHTML | HTML generation |

**Key Files:** `/static/js/skuel.js` (ALL Alpine.data() components), `/static/vendor/alpinejs/alpine.3.14.8.min.js`

## Hyperview Mobile Strategy

**Core Principle:** "One backend, two formats — HTML for web, HXML for mobile"

| Platform | Format | Framework |
|----------|--------|-----------|
| Web | HTML | HTMX |
| Mobile | HXML | Hyperview (React Native) |

**Status:** Groundwork phase. **Key Files:** `/core/hxml/elements.py`, `/adapters/inbound/negotiation.py`

**See:** `/docs/decisions/ADR-039-hyperview-mobile-strategy.md`

## Lateral Relationships & Vis.js Graph Visualization

All 9 domains deployed (Tasks, Goals, Habits, Events, Choices, Principles, KU, LS, LP).

**Three Components:** BlockingChainView (vertical flow), AlternativesComparisonGrid (side-by-side), RelationshipGraphView (Vis.js force-directed graph).

**6 Lateral Relationship Types:** BLOCKS/BLOCKED_BY, PREREQUISITE_FOR/DEPENDS_ON, ALTERNATIVE_TO, COMPLEMENTARY_TO, SIBLING, RELATED_TO.

**Usage:** `EntityRelationshipsSection(entity_uid=entity.uid, entity_type="tasks")` — add to any detail page.

**See:** `/docs/architecture/RELATIONSHIPS_ARCHITECTURE.md`, `/docs/patterns/LATERAL_RELATIONSHIPS_VISUALIZATION.md`

## Event-Driven Architecture

**Core Principle:** "Events over dependencies"

**Event Naming:** `{domain}.{action}` (e.g., `task.completed`, `goal.achieved`)

```python
from core.events.utils import publish_event
await publish_event(self.event_bus, TaskCompleted(task_uid=uid, user_uid=user_uid), self.logger)
```

**Location:** `/core/events/` — 65+ events across all domains

## 100% Dynamic Backend Pattern

**Core Principle:** "The plant grows on the lattice"

**4-Layer Architecture:** `*Operations protocol -> *Backend subclass -> *Service facade -> sub-services`

**Domain Backends** (all in `domain_backends.py`): TasksBackend, EventsBackend, GoalsBackend, HabitsBackend, ChoicesBackend, PrinciplesBackend, ArticleBackend, KuBackend, SubmissionsBackend, SharingBackend, LpBackend, ExerciseBackend, RevisedExerciseBackend, FormTemplateBackend, FormSubmissionBackend.

Domain-specific relationship Cypher belongs on the domain backend. Cross-domain aggregation stays in services. Use `cascade=True` for Activity Domains.

**`UniversalNeo4jBackend` is the hexagonal boundary** — Neo4j-specific code stops here. Neo4j is a committed architectural choice (ADR-044), not a swappable adapter.

**File Layout:** `universal_backend.py` is a shell; methods live in 6 mixin files: `_crud_mixin.py`, `_search_mixin.py`, `_relationship_query_mixin.py`, `_relationship_crud_mixin.py`, `_user_entity_mixin.py`, `_traversal_mixin.py`.

**See:** `/docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md`

## Search & Query Architecture

**Core Principle:** "SearchRouter is THE single path for all external search access"

**Three Query Systems:** UnifiedQueryBuilder (default), QueryBuilder (optimization), CypherGenerator (pure Cypher).

**Searchable Domains:** All 14 — Task, Goal, Habit, Event, Choice, Principle, Article, LS, LP, Exercise, RevisedExercise, Submission, FormTemplate, FormSubmission.

**DomainConfig** is THE single source of truth for BaseService configuration: `dto_class`, `model_class`, `search_fields`, `search_order_by`, `category_field`, `temporal_exclude_statuses`, `supports_user_progress`, `user_ownership_relationship`, `graph_enrichment_patterns`, etc.

**Factory functions:** `create_activity_domain_config()`, `create_curriculum_domain_config()`

**See:** `/docs/patterns/query_architecture.md`, `/docs/architecture/SEARCH_ARCHITECTURE.md`

## BaseService Architecture

**7 Mixins:** ConversionHelpers, CRUD, Search, Relationships, TimeQuery, UserProgress, Context.

**6 Activity Domains:** Tasks (7 sub-services), Goals (9), Habits (8), Events (7), Choices (4), Principles (7). All use facade pattern with explicit `async def` delegation methods. Factory: `create_common_sub_services()`.

**Essential Docs:** `/docs/guides/BASESERVICE_QUICK_START.md`, `/docs/reference/SUB_SERVICE_CATALOG.md`, `/docs/reference/BASESERVICE_METHOD_INDEX.md`, `/docs/architecture/SERVICE_TOPOLOGY.md`

## Unified Content Ingestion

**Core Principle:** "The hips of SKUEL — one of three foundational systems"

One-way pipeline: Markdown/YAML -> Neo4j. Dry-run mode, incremental ingestion, ingestion history, WebSocket progress, edge ingestion (relationship YAML files), full LS field wiring.

**Import:** `from core.services.ingestion import UnifiedIngestionService`

**API:** `POST /api/ingest/file`, `POST /api/ingest/directory`, `POST /api/ingest/vault`, `POST /api/ingest/domain/{domain_name}`, `WS /ws/ingest/progress/{operation_id}`

**See:** `/docs/architecture/CORE_SYSTEMS_ARCHITECTURE.md`, `/docs/patterns/UNIFIED_INGESTION_GUIDE.md`

## Curriculum Grouping Patterns

| Pattern | UID Format | Topology | Metaphor |
|---------|-----------|----------|----------|
| Ku | `ku_{slug}_{random}` | Atom | A single concept/fact |
| Article | `a_{slug}_{random}` | Composition | A teaching narrative (composes Kus) |
| LS | `ls:{random}` | Edge | A step in a staircase |
| LP | `lp:{random}` | Path | The full staircase |

**Two Paths to Knowledge:** LS Path (structured, linear) and ORGANIZES Path (unstructured, graph, learner-directed). MOC is emergent identity — any Entity with ORGANIZES relationships.

**See:** `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md`

## KU UID Format

**Format:** `ku_{slug}_{random}` (flat UIDs, hierarchy in ORGANIZES relationships)

Hierarchy via `(parent)-[:ORGANIZES {order, importance}]->(child)` relationships. Multiple parents possible.

**See:** `/docs/decisions/ADR-013-ku-uid-flat-identity.md`, `/docs/patterns/UNIVERSAL_HIERARCHICAL_PATTERN.md`

## MetadataManagerMixin

Use for consistent timestamp/metadata handling: `timestamp_properties()`, `update_properties()`, `set_entity_metadata()`.

**See:** `/docs/patterns/metadata_manager_mixin.md`

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

**MyPy:** Strict where it matters, gradual everywhere else. Per-module overrides in `pyproject.toml`. Three globally-disabled codes: `type-var`, `assignment`, `arg-type`. Every new `Any` needs a `# boundary:` comment or should use a specific type.

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
| CommonQueryRouteFactory | Query patterns |
| AnalyticsRouteFactory | Analytics |

All support `scope=ContentScope.USER_OWNED` (default) or `ContentScope.SHARED` (curriculum, with `require_role=UserRole.ADMIN`).

**See:** `/docs/patterns/ROUTE_FACTORIES.md`

## Domain Route Configuration

**Core Principle:** "Configuration over code for route registration"

DomainRouteConfig eliminates route wiring boilerplate. Activity Domains use `create_activity_domain_route_config()` for config-driven CRUD/Query/Intelligence factories.

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

**Adoption:** 38 of 41 route files. **Patterns proven:** Standard, API-only, UI-only, Multi-factory, Config-Driven.

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

**Intelligence Tier Toggle (ADR-043):** `INTELLIGENCE_TIER=core` ($0, analytics only) vs `INTELLIGENCE_TIER=full` (default, everything + AI).

**UserContextIntelligence (Central Hub):** `get_ready_to_work_on_today()`, `get_optimal_next_learning_steps()`, `calculate_life_path_alignment()`, `get_schedule_aware_recommendations()`

**See:** `/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md`, `/docs/decisions/ADR-043-intelligence-tier-toggle.md`

## Embedding Text Extraction

**Location:** `/core/utils/embedding_text_builder.py`

```python
from core.utils.embedding_text_builder import build_embedding_text
text = build_embedding_text(EntityType.TASK, {"title": "Fix bug", "description": "Details"})
```

**Supported:** All 13 content-bearing entity types — Article, Ku, Exercise, LearningStep, LearningPath, Resource, RevisedExercise, Task, Goal, Habit, Event, Choice, Principle. Field mappings in `EMBEDDING_FIELD_MAPS`.

## Quick Reference: Key Files

| Purpose | Location |
|---------|----------|
| Service composition | `/services_bootstrap.py` |
| Base service | `/core/services/base_service.py` |
| Base analytics | `/core/services/base_analytics_service.py` |
| Domain enums | `/core/models/enums/` |
| Protocols | `/core/ports/` |
| Generic backend | `/adapters/persistence/neo4j/universal_backend.py` |
| Event bus | `/core/events/event_bus.py` |
| Route factories | `/adapters/inbound/route_factories.py` |
| ADRs | `/docs/decisions/` |
| Patterns | `/docs/patterns/` |
| Architecture | `/docs/architecture/` |
| Troubleshooting | `/docs/TROUBLESHOOTING.md` |

## Troubleshooting

**Server Won't Start:** Port in use (`lsof -ti:8000 | xargs kill -9`), import errors (check `fasthtml.common`).

**Routes Return 404:** Check both API and UI routes registered in `bootstrap.py`. Distinguish 401 (auth) vs 404 (missing).

**Type Errors:** Forward reference unions use `Optional["Type"]` not `"Type" | None`.

**See:** `/docs/TROUBLESHOOTING.md`
