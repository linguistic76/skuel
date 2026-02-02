- We use poetry for package management and for running files.

## One Path Forward - Core Development Philosophy
*Last updated: 2026-01-31*

**SKUEL does NOT maintain backward compatibility.** When a better pattern emerges, the old pattern is removed entirely.

**What this means for development:**
- **No legacy wrappers** - Don't create compatibility shims for old code
- **No deprecation periods** - Old patterns are deleted, not deprecated
- **No alternative paths** - One way to accomplish each task
- **Update all call sites** - When patterns change, update everything immediately
- **Remove, don't archive** - Dead code is deleted from the codebase

**Examples:**
```python
# Ingestion service - use package, not monolith
from core.services.ingestion import UnifiedIngestionService  # THE path

# Domain enums - single source of truth
from core.models.enums.finance_enums import ExpenseStatus  # Not defined in multiple files

# Curriculum protocols - unified location
from core.services.protocols import LpOperations  # Not ku_protocols.py
```

**Design Philosophy:** Type errors are teachers, showing us where components don't flow together properly. When errors appear, investigate the fundamental design first rather than working around with quick fixes. Deal with fundamentals. Deal with the core.

**See:** `/docs/architecture/ARCHITECTURE_OVERVIEW.md`

## Naming Conventions

**File Naming:** File names must reflect function. When Claude Code provides a randomly-generated plan file name (e.g., `radiant-shimmying-map.md`), immediately rename it to a descriptive name.

**Parameter Naming:** Underscore prefix indicates placeholder for future implementation:
```python
async def get_learning_opportunities(
    self, _filters: dict[str, Any] | None = None  # Placeholder - not yet implemented
) -> Result[list[dict[str, Any]]]:
```

## Neo4j Infrastructure

**Core Principle:** "One Path Forward - Docker for development, AuraDB for production"

**Current Setup (Development):** Docker-based Neo4j
- Connection: `bolt://localhost:7687`
- GenAI plugin: Enabled via `NEO4J_PLUGINS='["genai"]'` in docker-compose.yml
- API keys: Per-query token passing (OPENAI_API_KEY environment variable)
- Setup guide: `/docs/development/GENAI_SETUP.md`

**Production Migration:** AuraDB
- Migration guide: `/docs/deployment/AURADB_MIGRATION_GUIDE.md`
- Database-level API keys (no per-query passing)
- Connection: `neo4j+s://xxx.databases.neo4j.io`
- Automated backups, 99.95% uptime SLA

**Key Difference:**
- Docker: Per-query `token` parameter with OpenAI API key
- AuraDB: API key configured at database level via console

**Code is environment-agnostic** - only `.env` configuration changes for Docker vs AuraDB.

**See:** `.claude/skills/neo4j-genai-plugin/` for GenAI plugin patterns

## Skills & Documentation Cross-Reference

**Core Principle:** "Local curated docs first, external lookup only when missing"

**Cross-Reference System:**
- Skills use "Deep Dive Resources" section to link to architecture docs
- Docs use "Quick Start" or "Related Skills" section to link to skills
- See [CROSS_REFERENCE_INDEX.md](/docs/CROSS_REFERENCE_INDEX.md) for complete mapping

| Skill | Primary Documentation | Related Patterns |
|-------|----------------------|------------------|
| **Foundation Layer** | | |
| python | `/docs/patterns/three_tier_type_system.md`, `/docs/patterns/protocol_architecture.md` | ASYNC_SYNC_DESIGN_PATTERN.md |
| pydantic | `/docs/patterns/three_tier_type_system.md`, `/docs/patterns/API_VALIDATION_PATTERNS.md` | DOMAIN_PATTERNS_CATALOG.md |
| tailwind-css | `/docs/patterns/UI_COMPONENT_PATTERNS.md` | — |
| daisyui | `/docs/patterns/UI_COMPONENT_PATTERNS.md` | — |
| chartjs | `/docs/architecture/ADMIN_DASHBOARD_ARCHITECTURE.md` | — |
| **Web Framework** | | |
| fasthtml | `/docs/patterns/FASTHTML_ROUTE_REGISTRATION.md`, `/docs/patterns/ROUTE_FACTORIES.md` | DOMAIN_ROUTE_CONFIG_PATTERN.md |
| html-htmx | `/docs/patterns/UI_COMPONENT_PATTERNS.md` | HTMX_ACCESSIBILITY_PATTERNS.md |
| html-navigation | `/docs/patterns/UI_COMPONENT_PATTERNS.md` | — |
| js-alpine | `/docs/architecture/ALPINE_JS_ARCHITECTURE.md` | UI_COMPONENT_PATTERNS.md |
| **UX & Accessibility** | | |
| accessibility-guide | `/docs/patterns/HTMX_ACCESSIBILITY_PATTERNS.md` | UI_COMPONENT_PATTERNS.md |
| base-page-architecture | `/docs/patterns/UI_COMPONENT_PATTERNS.md` | — |
| custom-sidebar-patterns | `/docs/patterns/UI_COMPONENT_PATTERNS.md` | — |
| skuel-component-composition | `/docs/patterns/UI_COMPONENT_PATTERNS.md` | HIERARCHY_COMPONENTS_GUIDE.md |
| skuel-form-patterns | `/docs/patterns/API_VALIDATION_PATTERNS.md` | PERFORMANCE_MONITORING.md |
| ui-error-handling | `/docs/patterns/ERROR_HANDLING.md` | RETURN_TYPE_ERROR_PROPAGATION.md |
| **Database** | | |
| neo4j-cypher-patterns | `/docs/architecture/NEO4J_DATABASE_ARCHITECTURE.md`, `/docs/patterns/query_architecture.md` | CYPHER_VS_APOC_STRATEGY.md |
| neo4j-genai-plugin | `/docs/development/GENAI_SETUP.md` | search_service_pattern.md |
| **Monitoring** | | |
| prometheus-grafana | `/monitoring/README.md`, `/OBSERVABILITY_PHASE1_COMPLETE.md` | PERFORMANCE_MONITORING.md |
| **SKUEL Architecture** | | |
| result-pattern | `/docs/patterns/ERROR_HANDLING.md` | RETURN_TYPE_ERROR_PROPAGATION.md |
| base-analytics-service | `/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md`, `/docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md` | 7 pattern docs |
| base-ai-service | `/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md` | — |
| activity-domains | `/docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md` | OWNERSHIP_VERIFICATION.md |
| curriculum-domains | `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md` | OWNERSHIP_VERIFICATION.md |
| skuel-search-architecture | `/docs/architecture/SEARCH_ARCHITECTURE.md` | query_architecture.md |
| user-context-intelligence | `/docs/architecture/UNIFIED_USER_ARCHITECTURE.md` | — |
| **Testing** | | |
| pytest | `/docs/patterns/TESTING_PATTERNS.md`, `/TESTING.md` | GRAPH_ACCESS_PATTERNS.md |
| **Meta** | | |
| docs-skills-evolution | `/docs/patterns/DOCSTRING_STANDARDS.md`, `/docs/decisions/ADR-TEMPLATE.md` | Cross-reference validation |

**Total:** 28 skills with comprehensive documentation mappings

## Documentation Architecture

**Single Source of Truth:** `/home/mike/skuel/app/docs/`
- `docs/decisions/` - Architecture Decision Records (ADRs)
- `docs/patterns/` - Implementation patterns
- `docs/architecture/` - System architecture
- `docs/INDEX.md` - Complete documentation index

**CLAUDE.md Purpose:** Quick-reference with pointers to detailed docs. Sections should be 10-20 lines max with `**See:**` pointers.

**Content Location (different purpose):** `/home/mike/0bsidian/skuel/docs/` contains Knowledge Unit content for ingestion, NOT technical documentation.

**Documentation Evolution:** See `@docs-skills-evolution` for how documentation and skills evolve with the tech stack. Includes library upgrade workflows, pattern deprecation process, and cross-reference validation.

## Docstring Philosophy

**Core Principle:** "Three layers - docstrings describe implementation, patterns describe approach, architecture describes design"

| Layer | Location | Purpose | Audience |
|-------|----------|---------|----------|
| Implementation | Docstrings | What does THIS do? | Code readers, IDE users |
| Pattern | /docs/patterns/ | How do we solve this? | Implementers |
| Architecture | /docs/architecture/ | Why is it designed this way? | Architects, new devs |

**When to Write Docstrings:**
- Always: Public APIs, complex functions, service classes, protocols
- Skip: Obvious one-liners, simple private helpers

**Cross-Reference Pattern:**
```python
"""
Brief description.

See: /docs/patterns/PATTERN_NAME.md
See: /docs/architecture/ARCHITECTURE_NAME.md
"""
```

**See:** `/docs/patterns/DOCSTRING_STANDARDS.md`

## Architecture Decision Records (ADRs)

**Location:** `/docs/decisions/` (33 ADRs)
**Template:** `/docs/decisions/ADR-TEMPLATE.md`
**See:** `/docs/INDEX.md` for complete listing

## Analog-to-Digital Development Model

**Core Principle:** "Plain English in, working code out"

SKUEL is developed through analog-to-digital collaboration where domain ideas are expressed in plain language and converted to type-safe code.

```
Analog (Human)              Digital (Code)
"14 domains"           ->   EntityType enum
"Tasks have deadlines" ->   Task.due_date: date
"Everything flows      ->   SERVES_LIFE_PATH
 toward life path"          relationship type
```

The Activity DSL (`@context(task)`, `@when()`, `@priority()`) is the purest expression - users write near-natural language, the parser converts to typed structures.

**See:** `/docs/dsl/DSL_SPECIFICATION.md`

## SKUEL's 14-Domain + 5-System Architecture

**Core Principle:** "Everything flows toward the life path"

### The 14 Domains

| # | Domain | Group | UID Format | Purpose |
|---|--------|-------|-----------|---------|
| 1-6 | Tasks, Goals, Habits, Events, Choices, Principles | Activity | `{type}_{slug}_{random}` | User activities |
| 7 | Finance | Finance | `expense_{random}` | Admin-only bookkeeping |
| 8-10 | KU, LS, LP | Curriculum | `ku_{slug}_{random}`, `ls:{random}`, `lp:{random}` | Knowledge organization |
| 11-12 | Journals, Assignments | Content | `journal_{random}`, `assignment_{random}` | Processing |
| 13 | MOC | Organizational | `ku_{slug}_{random}` (MOC is a KU) | Non-linear KU navigation |
| 14 | LifePath | Destination | `lp_{random}` | "Am I living my life path?" |

### Domain Category Details

**Activity Domains (6)** - User-facing entities with harmonized patterns:
- All use facade pattern with `.core`, `.search`, `.intelligence` sub-services
- All created via `create_common_sub_services()` factory in `activity_domain_config.py`
- User-owned content with ownership verification
- Protocol-typed: `TasksOperations`, `GoalsOperations`, etc.
- **Detail pages:** All 6 domains have `/{domain}/{uid}` routes with lateral relationships visualization (Phase 5)

**Finance Domain (1)** - Standalone bookkeeping, NOT an Activity Domain:
- Admin-only access (no ownership checks, ADMIN role required)
- Does NOT use `BaseService` or `BaseAnalyticsService`
- No intelligence service - pure bookkeeping
- Unique: budgets, expense categories, recurring expenses

**Curriculum Domains (3)** - Shared content (user-creatable, publicly readable):
- `ContentScope.SHARED` - any authenticated user can create, all users can read
- `_user_ownership_relationship = None` - no ownership verification needed
- KU (point), LS (edge), LP (path) - three grouping patterns
- Core + search services extend `BaseService`
- **NOT admin-only** - differs from Finance which requires ADMIN role
- **Detail pages:** `/ku/{uid}`, `/ls/{uid}`, `/lp/{uid}` routes with lateral relationships (Phase 5, placeholder data)

**Content/Processing Domains (2)**:
- `/journals` - Voice + text submission (type=JOURNAL hardcoded)
- `/assignments` - All file types dashboard

**Organizational Domain (1)** - MOC (Map of Content):
- MOC is NOT a separate entity - it IS a KU with ORGANIZES relationships
- A KU "is" a MOC when it has outgoing ORGANIZES to other KUs (emergent identity)
- Two paths to knowledge: LS (structured) vs MOC (exploratory, Montessori-inspired)
- Same KU accessible via both paths; progress tracked on KU itself

**LifePath Domain (1)** - The Destination:
- Philosophy: "The user's vision is understood via words, UserContext via actions"
- Bridges VISION (declared intent) with ACTION (behavior)
- Alignment score 0.0-1.0 across 5 dimensions: knowledge 25%, activity 25%, goal 20%, principle 15%, momentum 15%
- All domains connect via `SERVES_LIFE_PATH` relationships

### The 5 Cross-Cutting Systems

| System | Purpose |
|--------|---------|
| UserContext | ~240 fields of cross-domain state |
| Search | Unified search across all domains |
| Calendar | Aggregates Tasks, Events, Habits, Goals |
| Askesis | Life context synthesis + recommendations |
| Messaging | Notifications (planned) |

### Service Architecture Pattern

```
UniversalNeo4jBackend[T]  <- ONE instance per domain, NO wrappers
        |
    {Domain}Service       <- Facade orchestrates sub-services
        |
    Sub-services          <- .core, .search, .intelligence
```

All domains use `UniversalNeo4jBackend[T]` directly. Activity domains use `create_common_sub_services()` factory.

### Cross-Domain Relationships

All 14 domains connect through Neo4j graph relationships:

```
Knowledge (ku:) <--> Activity Domains
    |
    +-- APPLIES_KNOWLEDGE (Tasks, Events apply KU)
    +-- REQUIRES_KNOWLEDGE (Goals need KU)
    +-- REINFORCES_KNOWLEDGE (Habits strengthen KU)

Goals <--> Tasks, Habits, Principles, LifePath
    |
    +-- FULFILLS_GOAL (Tasks contribute to Goals)
    +-- SUPPORTS_GOAL (Habits maintain Goals)
    +-- ALIGNED_WITH_PRINCIPLE (Principles guide Goals)

Principles <--> Goals, Choices
    |
    +-- GUIDES_GOAL (Principles inform Goal setting)
    +-- GUIDES_CHOICE (Principles inform decisions)

LifePath <--> All Domains
    |
    +-- ULTIMATE_PATH: (User)-[:ULTIMATE_PATH]->(Lp)
    +-- SERVES_LIFE_PATH: (Entity)-[:SERVES_LIFE_PATH]->(Lp)
```

**Relationship Service Methods** (`UnifiedRelationshipService`):
- `link_to_life_path(entity_uid, life_path_uid, contribution_type, score)`
- `get_life_path_contributors(life_path_uid, entity_types, min_score)`
- `get_related_uids(entity_type, uid, relationship_type, direction)`

**Lateral Relationship Types** (Phase 5 - within-domain relationships):
- `BLOCKS` / `BLOCKED_BY` - Dependency blocking (asymmetric)
- `PREREQUISITE_FOR` / `DEPENDS_ON` - Knowledge prerequisites (asymmetric)
- `ALTERNATIVE_TO` - Mutually exclusive options (symmetric)
- `COMPLEMENTARY_TO` - Synergistic pairing (symmetric)
- `SIBLING` - Same parent in hierarchy (symmetric)
- `RELATED_TO` - General association (symmetric)

**Lateral Service Methods** (`LateralRelationshipService`):
- `create_lateral_relationship(source_uid, target_uid, type, metadata)`
- `get_blocking_chain(entity_uid)` - Transitive blocking dependencies (Phase 5)
- `get_alternatives_with_comparison(entity_uid)` - Side-by-side comparison (Phase 5)
- `get_relationship_graph(entity_uid, depth)` - Vis.js network format (Phase 5)

### Key Implementation Files

| Component | File |
|-----------|------|
| Domain Enums | `/core/models/shared_enums.py` |
| Base Service | `/core/services/base_service.py` |
| Base Analytics | `/core/services/base_analytics_service.py` |
| Domain Config | `/core/services/domain_config.py` |
| Service Composition | `/core/utils/services_bootstrap.py` |
| Generic Backend | `/adapters/persistence/neo4j/universal_backend.py` |

**See:** `/docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md`, `/docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md`

## Three-Tier Type System

**Core Principle:** "Pydantic at the edges, pure Python at the core"

| Tier | Type | Mutability | Purpose |
|------|------|------------|---------|
| External | Pydantic Models | N/A | Validation & serialization |
| Transfer | DTOs | Mutable | Data movement between layers |
| Core | Domain Models | **Frozen** | Immutable business entities |

**Infrastructure Field Filtering (ADR-037):**
Embeddings (`embedding`, `embedding_version`, etc.) are automatically filtered out from DTOs. Embeddings are search infrastructure stored in Neo4j, not domain data. Application code doesn't need raw 1536-dimensional vectors.

### Pattern Selection (Two Patterns)

SKUEL uses two approved patterns: **Pattern A (Three-Tier)** for most domains, **Pattern B (Two-Tier)** for simple bookkeeping.

**Decision Matrix**:

```
Does the domain have 3+ business logic methods?
├─ YES → Pattern A (Three-Tier) ✅ [Default]
└─ NO  → Is domain admin-only bookkeeping?
    ├─ YES → Pattern B (Two-Tier) ✅ [Exception]
    └─ NO  → Pattern A (Three-Tier) ✅ [Default]
```

| Pattern | Files | Tiers | Use For | Domains |
|---------|-------|-------|---------|---------|
| **A: Three-Tier** | 4-5 | Pydantic→DTO→Domain | Complex logic, immutability | Tasks, Goals, Habits, Events, Choices, Principles, KU, LS, LP, Assignments, User, LifePath (12 domains) |
| **B: Two-Tier** | 2 | Pydantic→DTO | Simple CRUD, minimal logic | Finance, Journals (2 domains) |

**Rule**: Default to Pattern A unless domain is genuinely simple (admin-only bookkeeping, no business logic).

Key: Frozen dataclasses with `__post_init__` for dynamic defaults, `DomainModelProtocol` for generics (Pattern A only).

**See:**
- `/docs/patterns/three_tier_type_system.md` - Pattern details
- `/docs/patterns/DOMAIN_PATTERNS_CATALOG.md` - Complete examples
- `/docs/decisions/ADR-035-tier-selection-guidelines.md` - Decision rationale
- `/docs/tutorials/DATA_FLOW_WALKTHROUGH.md` - Step-by-step example

## User Roles & Authentication

**Core Principle:** "Graph-native authentication - all auth data in Neo4j"

| Role | Level | Permissions |
|------|-------|-------------|
| REGISTERED | 0 | Free trial |
| MEMBER | 1 | Paid subscription |
| TEACHER | 2 | Member + create curriculum |
| ADMIN | 3 | Teacher + user management |

**Auth Patterns:**
```python
from core.auth import UserUID, require_authenticated_user

user_uid: UserUID = require_authenticated_user(request)  # Returns "user_{name}"

# Role protection (use named function, not lambda - SKUEL012)
def get_user_service():
    return services.user_service

@require_admin(get_user_service)
async def admin_route(request, current_user): ...
```

**See:** `/docs/patterns/AUTH_PATTERNS.md`, `/docs/decisions/ADR-022-graph-native-authentication.md`

## Unified User Architecture

**Core Principle:** "Context is the source of truth, stats are computed views"

`UserContext` (~240 fields) is THE authoritative source for all user state. `ProfileHubData` is a computed view.

**Canonical Location:** `/core/services/user/unified_user_context.py`

**Context Builder Modules:**
- `user_context_builder.py` - Orchestration (`build()`, `build_rich()`)
- `user_context_queries.py` - MEGA-QUERY
- `user_context_extractor.py` - Result parsing
- `user_context_populator.py` - Context population

**Context Depth (Standard vs Rich):**
| Depth | Method | Fields | Use Case |
|-------|--------|--------|----------|
| Standard | `build()` | UIDs only (~150) | API responses, lightweight checks |
| Rich | `build_rich()` | UIDs + entities + graph (~240) | Intelligence, planning |

Use `context.require_rich_context("operation")` to validate rich context at runtime.

**See:** `/docs/architecture/UNIFIED_USER_ARCHITECTURE.md`, `/docs/decisions/ADR-030-usercontext-file-consolidation.md`

## Reports Architecture

**Core Principle:** "Reports aggregate, they don't create"

Reports is a meta-service, not a domain. No Report nodes in Neo4j. READ-ONLY queries across all domains.

**See:** `/docs/architecture/REPORTS_ARCHITECTURE.md`

## Dynamic Enum Pattern

**Core Principle:** "Enums define behavior, services consume it"

Presentation logic lives inside enum methods. Magic numbers live in `/core/constants.py`.

```python
Priority.get_color()                      # Dynamic enum methods
ActivityStatus.is_terminal()
ContextHealthScore.get_numeric()          # 0.0-1.0 scoring
ContextHealthScore.get_icon()             # 🟢 for EXCELLENT
GraphDepth.DEFAULT                        # Named constants
```

**Consolidated Enums:** `/core/models/enums/` - one file per domain (finance_enums.py, activity_enums.py, user_enums.py, etc.)

**Health Scoring Pattern:** Use typed enums (ContextHealthScore, FinancialHealthTier) instead of string literals for all health/quality assessments.

**See:** `/docs/patterns/ENUM_CONSOLIDATION_PATTERN.md`

## Activity DSL & EntityType

**Core Principle:** "Clear domain language -> clear types -> enforceable contracts"

```python
class EntityType(str, Enum):
    TASK, HABIT, GOAL, EVENT, PRINCIPLE, CHOICE, FINANCE = ...  # Activity
    KU, LS, LP = ...  # Curriculum
    MOC = "moc"  # Organizational (MOC IS a KU with ORGANIZES relationships)
    LIFEPATH = "lifepath"  # Destination

# Type-safe context checking
if EntityType.TASK in activity.contexts:  # MyPy verified!

# Key methods
EntityType.from_string("task")  # -> EntityType.TASK or None
EntityType.get_canonical()      # Normalizes aliases (KNOWLEDGE -> KU)
```

**See:** `/docs/dsl/DSL_SPECIFICATION.md`, `/docs/dsl/DSL_USAGE_GUIDE.md`

## Protocol-Based Architecture

**Core Principle:** "Zero port dependencies - all services use Protocol interfaces exclusively"

**Status (January 2026):** ✅ **100% Protocol Compliance Achieved**
- Zero concrete type dependencies in route signatures
- All services use protocol-based backends
- All facade services have MyPy-visible protocol declarations
- Full type safety across 27+ services

**Protocol Location:** `core/services/protocols/` - 8 protocol files covering all domains

**Key Protocol Categories:**

| Category | File | Purpose | Count |
|----------|------|---------|-------|
| **Backend** | `base_protocols.py` | ISP-compliant backend operations | 7 protocols |
| **Domains** | `domain_protocols.py` | Business logic (Tasks, Goals, etc.) | 9 protocols |
| **Facades** | `facade_protocols.py` | MyPy declarations for delegated methods | 9 protocols |
| **Curriculum** | `curriculum_protocols.py` | KU, LS, LP operations | 4 protocols |
| **Search** | `search_protocols.py` | Search and query operations | 8 protocols |
| **Infrastructure** | `infrastructure_protocols.py` | EventBus, UserOperations, etc. | 5 protocols |
| **Intelligence** | `intelligence_protocols.py` | Analytics operations | 1 protocol |
| **Askesis** | `askesis_protocols.py` | Cross-cutting intelligence | 5 protocols |

**Facade Protocols (9 total):**
Make FacadeDelegationMixin-generated methods visible to MyPy:
- `TasksFacadeProtocol`, `GoalsFacadeProtocol`, `HabitsFacadeProtocol`
- `EventsFacadeProtocol`, `ChoicesFacadeProtocol`, `PrinciplesFacadeProtocol`
- `KuFacadeProtocol`, `LpFacadeProtocol`, `LsFacadeProtocol`

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

**Usage Pattern:**

```python
# Routes use facade protocols
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from core.services.protocols.facade_protocols import TasksFacadeProtocol

def create_tasks_api_routes(
    app: Any,
    rt: Any,
    tasks_service: TasksFacadeProtocol,  # Protocol, not concrete
) -> list[Any]:
    # MyPy knows all 45+ delegated methods
    await tasks_service.schedule_task(...)  # ✓ Type-safe
```

**Relationship Service Patterns:**

| Pattern | Use Case |
|---------|----------|
| Config-Driven (UnifiedRelationshipService) | Activity domains (6) |
| Direct Driver | Curriculum, Journal, User |

**Protocol-Mixin Compliance (January 2026):**
✅ **100% alignment achieved** - All 7 BaseService mixins match their protocol interfaces.

Automated verification via:
- TYPE_CHECKING blocks in all 7 mixins (zero runtime cost)
- 29 comprehensive tests (catches all mismatches)
- MyPy enforcement (compile-time verification)

```bash
# Verify protocol compliance
poetry run pytest tests/unit/test_protocol_mixin_compliance.py -v
# Expected: 29 passed
```

**See:** `/docs/patterns/protocol_architecture.md`, `/docs/patterns/BACKEND_OPERATIONS_ISP.md`, `/docs/migrations/PROTOCOL_MIXIN_ALIGNMENT_COMPLETE_2026-01-29.md`

## Async/Sync Design Pattern

**Core Principle:** "Async for I/O, sync for computation"

| Layer | Async | Sync |
|-------|-------|------|
| Database/Persistence | 100% | 0% |
| Service Layer | ~95% | ~5% |
| Data Conversion | 0% | 100% |
| Domain Models | 0% | 100% |

**Rule:** If you need `await` inside the function, make it `async def`. Otherwise use `def`.

**See:** `/docs/patterns/ASYNC_SYNC_DESIGN_PATTERN.md`

## Data Flow Architecture

```
Content to Storage:
Markdown -> UnifiedMarkdownSync -> KnowledgeUnit -> GraphNode -> Neo4j

Request Processing:
HTTP -> FastHTML Route -> Pydantic -> Service -> Domain -> Repository -> Neo4j
```

## Knowledge Substance Philosophy

**Core Principle:** "Applied knowledge, not pure theory"

SKUEL measures knowledge by how it's LIVED. Substance tracking across five domains:

| Type | Weight | Max | Rationale |
|------|--------|-----|-----------|
| Habits | 0.10 | 0.30 | Lifestyle integration |
| Journals | 0.07 | 0.20 | Metacognition |
| Choices | 0.07 | 0.15 | Decision wisdom |
| Events | 0.05 | 0.25 | Practice/embodiment |
| Tasks | 0.05 | 0.25 | Real-world application |

**See:** `/docs/architecture/knowledge_substance_philosophy.md`

## Error Handling

**Core Principle:** "Use `Result[T]` internally, convert to HTTP at boundaries"

**Quick Reference:**
- Use `.is_error` (not `.is_err`) for failure checks
- Use `Errors` factory for creating errors
- Six error types: Validation, NotFound, Database, Integration, Business, System

**See:** `/docs/patterns/ERROR_HANDLING.md`

## API Input Validation

**Core Principle:** "Validate at boundaries, fail fast with clear errors"

SKUEL validates all external input at API boundaries to prevent 500 errors. Use appropriate strategies based on input type:

**Query Parameters (GET routes):** Helper functions
```python
# Boolean parsing (handles true/1/yes/on)
include_predictions = parse_bool_param(params, "include_predictions", default=True)

# Enum validation (whitelist check)
time_window_result = validate_time_window(params.get("time_window", "7d"))
if time_window_result.is_error:
    return time_window_result  # 400 with clear error
```

**JSON Bodies (POST routes):** Pydantic request models
```python
# Pydantic model auto-validates structure, types, constraints
@rt("/api/context/task/complete", methods=["POST"])
@boundary_handler(success_status=200)
async def complete_task(
    request: Request,
    task_uid: str,
    body: TaskCompletionRequest  # Auto-parsed & validated
) -> Result[Any]:
    return await service.complete_task_with_context(
        completion_context=body.context,  # Type-safe access
        reflection_notes=body.reflection,
    )
```

**Request Model Location:** `core/models/{domain}/{domain}_request.py`

**Error Codes:**
- Query params → 400 Bad Request (via `Result.fail()`)
- JSON bodies → 422 Unprocessable Entity (via Pydantic)

**See:** `/docs/patterns/API_VALIDATION_PATTERNS.md`

## Ownership Verification

**Core Principle:** "Return 'not found' for entities the user doesn't own"

```python
await service.verify_ownership(uid, user_uid)  # Returns entity or NotFound
await service.get_for_user(uid, user_uid)      # Get with ownership check
```

**Access Patterns (ContentScope):**

| Pattern | Domains | Create | Read | Ownership Check |
|---------|---------|--------|------|-----------------|
| **USER_OWNED** | Tasks, Goals, Habits, Events, Choices, Principles, Journals | User | Owner only | Yes (returns 404 if not owner) |
| **SHARED** | KU, LS, LP (MOC is KU-based) | Any authenticated user | All users | No (content is public) |
| **ADMIN_ONLY** | Finance | Admin role only | Admin only | No (admin-gated at route) |

**Key distinction**: SHARED ≠ ADMIN_ONLY. Curriculum domains (KU/LS/LP) are user-creatable, while Finance requires admin role.

**See:** `/docs/patterns/OWNERSHIP_VERIFICATION.md`

## Content Sharing (Phase 1: Assignments)

**Core Principle:** "Three-level visibility with relationship-based access control"

**Visibility Model:**
```
PRIVATE (default) → Owner only
SHARED            → Owner + users with SHARES_WITH relationship
PUBLIC            → Anyone (portfolio showcase)
```

**Use Case:** Student completes assignment → shares with teacher → teacher views in "Shared With Me" inbox.

**Service:**
```python
from core.services.assignments import AssignmentSharingService

# Share assignment
await sharing_service.share_assignment(
    assignment_uid="assignment_123",
    owner_uid="user_student",
    recipient_uid="user_teacher",
    role="teacher"  # teacher, peer, mentor, viewer
)

# Check access
await sharing_service.check_access(assignment_uid, user_uid)  # Returns Result[bool]

# Set visibility
await sharing_service.set_visibility(assignment_uid, owner_uid, Visibility.PUBLIC)
```

**UI Routes:**
- `/assignments/{uid}` - Sharing controls (owner only)
- `/profile/shared` - "Shared With Me" inbox
- `/api/assignments/share` - Share with user
- `/api/assignments/shared-with-me` - Inbox API

**Quality Control:** Only `COMPLETED` assignments can be shared (prevents sharing failed/processing work).

**Graph Pattern:**
```cypher
(user:User)-[:SHARES_WITH {shared_at, role}]->(assignment:Assignment)
```

**Phase 2:** Extend to Events (same infrastructure, different entity type).

**See:** `/docs/patterns/SHARING_PATTERNS.md`, `/docs/decisions/ADR-038-content-sharing-model.md`

## Generic Programming Patterns

**Key Patterns:**
1. Generic Repository[T] - `/core/patterns/repository.py`
2. CypherGenerator - Pure Cypher query building
3. Result[T] Pattern - Results internally, `@boundary_handler` at boundaries
4. BaseAdapter Pattern - Single `update_to_dict` for all adapters

**See:** `/docs/patterns/query_architecture.md`, `/docs/patterns/CLEAN_PATTERNS.md`

## Infrastructure Helpers

**Location:** `/core/services/infrastructure/`

Reusable patterns for cross-cutting concerns:

| Helper | Purpose | Used By |
|--------|---------|---------|
| `PrerequisiteHelper` | Unified prerequisite checking | TasksPlanningService, TasksSchedulingService |
| `LearningAlignmentHelper` | LP integration for any domain | TasksSchedulingService, GoalsSchedulingService |
| `SemanticRelationshipHelper` | Semantic relationship ops | All domain services |
| `RelationshipCreationHelper` | Cross-domain rel creation | All domain services |

**PrerequisiteHelper Usage:**
```python
from core.services.infrastructure import PrerequisiteHelper, PrerequisiteResult

result: PrerequisiteResult = PrerequisiteHelper.check_prerequisites(
    required_knowledge_uids=["ku_python-basics_abc123"],
    required_task_uids=["task_setup-env_xyz789"],
    context=user_context,
)
# result.score (0.0-1.0), result.is_ready, result.blocking_reasons
```

## Fail-Fast Dependency Philosophy

**Core Principle:** "All dependencies are REQUIRED - no graceful degradation"

**Required at bootstrap:** Neo4j, OpenAI, Deepgram

**Only 2 valid `None` cases:** True circular dependencies, unimplemented features (explicit TODOs)

**Exception:** `CalendarService` is an aggregation meta-service with optional dependencies.

## UI Component Pattern

**Core Principle:** "BasePage for consistency, custom layouts for special cases"

- Routes (`/adapters/inbound/*_routes.py`) - HTTP handling
- Components (`/components/*.py`) - Pure presentation
- Static (`/static/css/`, `/static/js/`) - CSS/JS assets
- Design System (`/ui/`) - Primitives, patterns, layouts, tokens

**Unified UX Design System:**

| Page Type | Sidebar | Container | Use Case |
|-----------|---------|-----------|----------|
| STANDARD | None | `max-w-6xl` | Most pages |
| HUB | Left (w-64) | Flexible | Admin Dashboard |
| CUSTOM | STANDARD + custom | Flexible | Profile Hub (/nous-style sidebar) |

**Evolution (2026-02-01):** Profile Hub migrated from legacy `ProfileLayout` to `BasePage` with custom `/nous`-style sidebar. This provides explicit control while maintaining consistency.

**Key Files:**
- `/ui/layouts/base_page.py` - Unified page wrapper (`BasePage`)
- `/ui/layouts/page_types.py` - Page type enum and config
- `/ui/profile/layout.py` - Profile Hub custom sidebar (`build_profile_sidebar`, `create_profile_page`)
- `/ui/tokens.py` - Spacing, container, card tokens
- `/ui/patterns/` - PageHeader, SectionHeader components

**Profile Hub Pattern:**
```python
from ui.profile.layout import create_profile_page

return create_profile_page(
    content=main_content,
    domains=domain_items,
    request=request,  # Auto-detects auth/admin
)
```

**See:** `/docs/patterns/UI_COMPONENT_PATTERNS.md`

## Alpine.js Architecture

**Core Principle:** "Alpine.js handles UI state, HTMX handles server communication"

| Layer | Tool | Purpose |
|-------|------|---------|
| UI State | Alpine.js | Modals, toggles, filtering |
| Server Communication | HTMX | Form submissions, loading |
| Pure Presentation | FastHTML | HTML generation |

**Key Files:**
- `/static/js/skuel.js` - ALL Alpine.data() components
- `/static/vendor/alpinejs/alpine.3.14.8.min.js` - Self-hosted, version-pinned

**See:** `/.claude/skills/js-alpine/`

## Lateral Relationships & Vis.js Graph Visualization

**Core Principle:** "Interactive relationship visualization across all domains"

**Status:** ✅ Phase 5 Complete (2026-02-01) - All 9 domains deployed, 100% tested

**Three Components:**
1. **BlockingChainView** - Vertical flow chart with depth-based layout
2. **AlternativesComparisonGrid** - Side-by-side comparison table
3. **RelationshipGraphView** - Interactive Vis.js force-directed graph

**Usage:**
```python
from ui.patterns.relationships import EntityRelationshipsSection

# Add to any detail page
EntityRelationshipsSection(
    entity_uid=entity.uid,
    entity_type="tasks",  # or goals, habits, events, choices, principles, ku, ls, lp
)
```

**Integrated Domains (9):** Tasks, Goals, Habits, Events, Choices, Principles, KU, LS, LP

**Detail Page Routes:** `/{domain}/{uid}` for all domains

**Graph Features:**
- Force-directed layout with physics simulation
- Drag nodes, zoom, pan
- Click node to navigate
- Color-coded edges (BLOCKS=red, PREREQUISITES=orange, ALTERNATIVES=blue, COMPLEMENTARY=green)
- Depth control (1-3 levels)

**Key Files:**
- `/ui/patterns/relationships/` - 4 UI components
- `/core/services/lateral_relationships/lateral_relationship_service.py` - 3 graph query methods
- `/static/vendor/vis-network/` - Vis.js library (v9.1.9)
- `/static/js/skuel.js` - relationshipGraph Alpine component

**API Endpoints (per domain):**
- `GET /api/{domain}/{uid}/lateral/chain` - Blocking chain data
- `GET /api/{domain}/{uid}/lateral/alternatives/compare` - Comparison data
- `GET /api/{domain}/{uid}/lateral/graph` - Vis.js format (nodes + edges)

**Testing:**
- 40/40 automated tests passing (9 unit tests + 31 verification checks)
- 92 API routes verified on running server
- Zero breaking changes, fully backward compatible

**See:** `/PHASE5_COMPLETE.md`, `/docs/architecture/LATERAL_RELATIONSHIPS_CORE.md`, `/docs/patterns/LATERAL_RELATIONSHIPS_VISUALIZATION.md`

## Event-Driven Architecture

**Core Principle:** "Events over dependencies"

**Event Naming:** `{domain}.{action}` (e.g., `task.completed`, `goal.achieved`)

**Implementation:**
```python
from core.events.utils import publish_event
await publish_event(self.event_bus, TaskCompleted(task_uid=uid, user_uid=user_uid), self.logger)
```

**Location:** `/core/events/` - 60+ events across all domains

**See:** `/docs/patterns/event_driven_architecture.md`

## 100% Dynamic Backend Pattern

**Core Principle:** "The plant grows on the lattice"

Use `UniversalNeo4jBackend[T]` directly - no wrapper classes.

```python
tasks_backend = UniversalNeo4jBackend[Task](driver, "Task", Task)
tasks = await backend.find_by(priority='high', due_date__gte=date.today())
```

**Driver Access:**
- `self.backend.method()` - Standard CRUD, search
- `self.backend.driver.execute_query()` - Complex graph queries

**Cascade Deletion:** Use `cascade=True` for Activity Domains (auto-created user relationships exist).

**See:** `/docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md`

## Search & Query Architecture

**Core Principle:** "SearchRouter is THE single path for all external search access"

**Three Query Systems:**
- UnifiedQueryBuilder - Default for new code
- QueryBuilder - Optimization/templates
- CypherGenerator - Pure Cypher generation

**SearchRouter orchestrates all search:**
- `/search` routes -> `SearchRouter.faceted_search()`
- `/api/search/unified` -> `SearchRouter.advanced_search()`

**Searchable Domains:** All 9 - Task, Goal, Habit, Event, Choice, Principle, KU, LS, LP (MOC is KU-based)

**BaseService Configuration** (ONE PATH FORWARD - January 2026):

All services use **DomainConfig** - THE single source of truth for configuration.

| Configuration Field | Purpose | Default |
|---------------------|---------|---------|
| `dto_class` | DTO class for serialization | Required |
| `model_class` | Domain model class | Required |
| `search_fields` | Fields for text search | `("title", "description")` |
| `search_order_by` | Default sort field | `"created_at"` |
| `category_field` | Field for categorization | `"category"` |
| `supports_user_progress` | Enable progress tracking | `False` |
| `user_ownership_relationship` | Ownership rel type | `"OWNS"` (None for shared) |
| `graph_enrichment_patterns` | Graph context patterns | `()` |
| `prerequisite_relationships` | For `get_prerequisites()` | `()` |
| `enables_relationships` | For `get_enables()` | `()` |

**Inherited Methods:** `search()`, `get_by_status()`, `get_by_category()`, `list_categories()`, `get_prerequisites()`, `get_enables()`, `verify_ownership()`

**Configuration Example (Activity Domains):**
```python
from core.services.domain_config import create_activity_domain_config

class GoalsSearchService(BaseService[GoalsOperations, Goal]):
    _config = create_activity_domain_config(
        dto_class=GoalDTO,
        model_class=Goal,
        domain_name="goals",
        date_field="target_date",
        completed_statuses=(ActivityStatus.COMPLETED.value,),
        category_field="domain",  # Goals use 'domain' for categorization
    )
```

**Configuration Example (Curriculum Domains):**
```python
from core.services.domain_config import create_curriculum_domain_config

class KuSearchService(BaseService[KuOperations, KnowledgeUnit]):
    _config = create_curriculum_domain_config(
        dto_class=KuDTO,
        model_class=KnowledgeUnit,
        domain_name="ku",
        search_fields=("title", "description", "content"),
        category_field="domain",
    )
```

**Migration Status:** ✅ 100% complete (34 services migrated - January 2026)
- Activity domains: 25 services (6 core, 6 search, 13 specialized)
- Curriculum domains: 2 services (LS, LP core)
- Content domains: 3 services (Transcript, Journal core/project)
- Assignment domain: 3 services (core, search, submission)
- Infrastructure: 1 service (UnifiedRelationshipService)

**See:**
- `/docs/migrations/DOMAINCONFIG_MIGRATION_COMPLETE.md` - Migration guide
- `/docs/patterns/query_architecture.md` - Query patterns
- `/docs/architecture/SEARCH_ARCHITECTURE.md` - Search architecture

## BaseService Architecture Documentation

**Core Principle:** "Documentation-first discoverability"

SKUEL's BaseService architecture uses 7 focused mixins + facade pattern with 3-11 specialized sub-services per domain. Complete reference documentation available:

**Essential Documentation:**
- `/docs/guides/BASESERVICE_QUICK_START.md` - New developer onboarding (<30 min)
- `/docs/reference/SUB_SERVICE_CATALOG.md` - Which service does what (decision trees, patterns)
- `/docs/reference/BASESERVICE_METHOD_INDEX.md` - Complete method listing (auto-generated)
- `/docs/architecture/SERVICE_TOPOLOGY.md` - Architecture diagrams (data flow, dependencies)

**Architecture Overview:**
- **7 Mixins:** ConversionHelpers, CRUD, Search, Relationships, TimeQuery, UserProgress, Context
- **6 Activity Domains:** Tasks (7 sub-services), Goals (9), Habits (8), Events (7), Choices (4), Principles (7)
- **Facade Pattern:** Auto-delegation via FacadeDelegationMixin (~35-50 methods per facade)
- **Factory Pattern:** `create_common_sub_services()` eliminates ~80 lines of boilerplate

**Quick Reference:**
```python
# Production: Use facade (auto-delegates to sub-services)
from core.services.tasks_service import TasksService
result = await tasks_service.create_task(request, user_uid)

# Testing: Direct sub-service access
from core.services.tasks import TasksCoreService
core = TasksCoreService(backend=mock_backend)
```

**Implementation Files:**
- `/core/services/base_service.py` - Foundation with 7 mixins
- `/core/services/protocols/base_service_interface.py` - Protocol for type checking & IDE autocomplete
- `/core/services/mixins/facade_delegation_mixin.py` - Auto-delegation pattern
- `/core/utils/activity_domain_config.py` - Factory for common sub-services
- `/core/utils/service_introspection.py` - Generic service utilities (type-safe examples)

**Type Safety with BaseServiceInterface:**
Use `BaseServiceInterface[Any, Any]` for type hints when passing services generically:
```python
from core.services.protocols.base_service_interface import BaseServiceInterface
from core.utils.service_introspection import get_service_capabilities

# IDE autocompletes all BaseService methods (search, get_by_status, etc.)
capabilities = await get_service_capabilities(any_service)
```

**Automation:**
- `/scripts/generate_method_index.py` - Auto-generates method index from code
- Run: `poetry run python scripts/generate_method_index.py`

## Unified Content Ingestion

**Core Principle:** "One path forward for all content ingestion"

**Import:**
```python
from core.services.ingestion import UnifiedIngestionService
```

**API Endpoints:**
- `POST /api/ingest/file` - Single file
- `POST /api/ingest/directory` - Batch
- `POST /api/ingest/vault` - Obsidian vault sync

**See:** `/docs/patterns/UNIFIED_INGESTION_GUIDE.md`

## Curriculum Grouping Patterns

**Core Principle:** "Three patterns, two access paths"

| Pattern | UID Format | Topology | Metaphor |
|---------|-----------|----------|----------|
| KU | `ku_{slug}_{random}` | Point | A single brick |
| LS | `ls:{random}` | Edge | A step in a staircase |
| LP | `lp:{random}` | Path | The full staircase |

**Two Paths to Knowledge (Montessori-Inspired):**
- **LS Path:** Structured, linear, teacher-directed curriculum (KU → LS → LP)
- **MOC Path:** Unstructured, graph, learner-directed exploration (KU organizing KUs via ORGANIZES)

**MOC Architecture (January 2026):** MOC is NOT a separate entity - it IS a KU with ORGANIZES relationships. A KU "is" a MOC when it has outgoing ORGANIZES relationships (emergent identity).

**See:** `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md`, `/docs/domains/moc.md`

## KU UID Format

**Core Principle:** "Identity is independent of location" (Universal Hierarchical Pattern - 2026-01-30)

**Format:** `ku_{slug}_{random}` (flat UIDs, hierarchy in ORGANIZES relationships)

**Examples:**
```
ku_meditation-basics_a1b2c3d4    (Service-created)
ku.meditation-basics              (Markdown ingestion - legacy)
```

**Hierarchy via Relationships:**
```cypher
// MOC Pattern - KU organizing KUs
(moc:Ku {uid: "ku_yoga-fundamentals_abc123"})
  -[:ORGANIZES {order: 1, importance: "core"}]->
(child:Ku {uid: "ku_meditation-basics_xyz789"})
```

**Service Methods:**
```python
await ku_service.organize_ku(parent_uid, child_uid, order, importance)
await ku_service.get_subkus(parent_uid, depth=1)
await ku_service.get_parent_kus(ku_uid)  # Multiple parents possible!
```

**See:**
- `/docs/decisions/ADR-013-ku-uid-flat-identity.md` - Decision & implementation
- `/docs/patterns/UNIVERSAL_HIERARCHICAL_PATTERN.md` - Complete pattern guide

## MetadataManagerMixin

Use for consistent timestamp/metadata handling: `timestamp_properties()`, `update_properties()`, `set_entity_metadata()`.

**See:** `/docs/patterns/metadata_manager_mixin.md`

## Code Quality & Formatting

**Formatting:** Ruff. Run `./dev format` to format, `./dev quality` for full checks.

**SKUEL Linter Rules (key):**
- SKUEL001: No APOC in domain services [CRITICAL]
- SKUEL003: Use `.is_error` (not `.is_err`) [auto-fix]
- SKUEL007: Use `Errors` factory
- SKUEL011: No `hasattr()` - use Protocol/isinstance/getattr
- SKUEL012: No lambda expressions - use named functions
- SKUEL013: Use `RelationshipName` enum
- SKUEL014: Use `EntityType` enum
- SKUEL015: No `print()` in production

**Avoiding Common Violations:**

```python
# SKUEL011: hasattr() - use alternatives
# BAD:
if hasattr(obj, "method"):
# GOOD - for type checking:
if isinstance(obj, SomeProtocol):
# GOOD - for optional attributes:
value = getattr(obj, "attr", default)
# GOOD - for sentinel pattern:
_NOT_FOUND = object()
if getattr(obj, "attr", _NOT_FOUND) is not _NOT_FOUND:

# SKUEL012: lambdas - use named functions
# BAD:
sorted(items, key=lambda x: x.score)
# GOOD:
def by_score(item: Item) -> int:
    return item.score
sorted(items, key=by_score)
```

**See:** `/docs/patterns/linter_rules.md`

## Observability & Monitoring

**Core Principle:** "Measure what matters - real-time operational intelligence"

SKUEL uses **Prometheus + Grafana** for metrics collection and visualization, following the Prometheus-primary architecture pattern (ADR-036).

### Quick Access

- **Prometheus UI**: http://localhost:9090
- **Grafana Dashboards**: http://localhost:3000
- **Metrics Endpoint**: http://localhost:5001/metrics
- **Skill Guide**: `@prometheus-grafana` - Expert guide for instrumentation

### The Stack

**Metrics**: 47 across 9 categories (System, HTTP, Database, Events, Domains, Relationships, Search, Queries, AI Services)
**Alerts**: 14 production alerts (2 critical, 11 warning) with runbooks
**Dashboards**: 4 Grafana dashboards (System Health, Domain Activity, Graph Health, User Journey)

### Key Metrics Categories

| Category | Count | Examples |
|----------|-------|----------|
| System | 3 | CPU, memory, Neo4j health |
| HTTP | 3 | Requests, latency, errors |
| Database | 3 | Query performance, errors |
| Events | 6 | Event bus health, handler performance |
| Domains | 3 | Entity creation/completion |
| Relationships | 14 | Graph density, dependencies |
| Search | 3 | Search performance, similarity |
| Queries | 3 | Operation timing |
| **AI Services** | 9 | OpenAI costs, embedding pipeline |

### AI/LLM Cost Tracking (Phase 1 - January 2026)

**8 new metrics** for monitoring expensive AI operations:

**OpenAI API Metrics** (4):
- `skuel_openai_requests_total` - Request count by model
- `skuel_openai_duration_seconds` - API latency (p50/p95/p99)
- `skuel_openai_tokens_total` - Token consumption (cost tracking)
- `skuel_openai_errors_total` - Error classification (rate_limit, timeout, auth)

**Embedding Pipeline** (3):
- `skuel_embedding_queue_size` - Queue backlog by type (entity/chunk)
- `skuel_embeddings_processed_total` - Success/failure rates by entity type
- `skuel_embedding_batch_size` - Batch size distribution

**Deepgram Transcription** (1):
- `skuel_transcription_requests_total` - Request tracking

### Production Alerts

**14 alerts** with severity levels and runbooks:

**Critical (2)**:
- HighErrorRate - HTTP error rate >5% for 5m
- Neo4jDown - Database unavailable for 1m

**Warning (11)**:
- SlowHttpRequests, SlowDatabaseQueries, HighDatabaseErrorRate
- HighEventHandlerErrorRate, SlowEventHandlers
- HighOrphanedEntityCount, LongDependencyChains
- HighOpenAIErrorRate, EmbeddingQueueBacklog, HighEmbeddingFailureRate, SlowOpenAICalls

**Alert UI**: http://localhost:9090/alerts

### Common Tasks

```bash
# Start monitoring stack
docker compose up -d prometheus grafana

# View metrics
curl http://localhost:5001/metrics | grep skuel_

# Validate configuration
./scripts/validate_prometheus_config.sh

# Run test suite
./scripts/test_observability_phase1.sh
```

### Documentation

**Primary Docs**:
- `monitoring/README.md` - Quick start guide
- `.claude/skills/prometheus-grafana/SKILL.md` - Complete metrics reference (43 metrics)
- `.claude/skills/prometheus-grafana/ALERTING.md` - Alert runbooks and patterns
- `.claude/skills/prometheus-grafana/INSTRUMENTATION.md` - How to add metrics

**Implementation Docs**:
- `OBSERVABILITY_PHASE1_COMPLETE.md` - Full implementation guide
- `OBSERVABILITY_CHANGES_SUMMARY.md` - Quick changes reference

**Architecture**:
- Prometheus as single source of truth (no export lag)
- Optional in-memory cache for debugging (last 100 items, lossy)
- Zero runtime overhead (~1-2 microseconds per operation)
- Real-time AI cost tracking enables optimization

**See**: `/.claude/skills/prometheus-grafana/` for complete observability documentation

## Logging Patterns

**Core Principle:** "Right tool for each context"

| Context | Tool |
|---------|------|
| Production runtime | `logger.*()` |
| Interactive CLI | `print()` |
| Docstring examples | `print()` |

```python
from core.utils.logging import get_logger
logger = get_logger("skuel.services.tasks")
```

**See:** `/docs/patterns/LOGGING_PATTERNS.md`

## Graph-Native Comment Standard

**Core Principle:** "Domain models are pure - relationships live in the graph"

Use `# GRAPH-NATIVE:` prefix for comments about relationship data stored as Neo4j edges.

```python
# GRAPH-NATIVE: {field}_uids removed - query via service.relationships.get_{entity}_{relationship}()
```

**See:** `/docs/patterns/GRAPH_NATIVE_PLACEHOLDERS.md`

## HTTP Status Codes

POST (Create) -> 201, GET/PUT/DELETE -> 200, POST (Action) -> 200

**See:** `/docs/patterns/http_status_codes.md`

## Route Factories

**Core Principle:** "Configuration over repetition"

| Factory | Purpose |
|---------|---------|
| CRUDRouteFactory | Standard CRUD |
| StatusRouteFactory | Status changes |
| CommonQueryRouteFactory | Query patterns |
| AnalyticsRouteFactory | Analytics |

All support `scope=ContentScope.USER_OWNED` (default) for multi-tenant security.

**ContentScope Values:**
- `ContentScope.USER_OWNED` - User-specific content with ownership verification (Activity domains)
- `ContentScope.SHARED` - Public/shared content (Curriculum domains: KU, LS, LP)

**Example:**
```python
from core.models.enums import ContentScope

# Activity domain (user-owned)
CRUDRouteFactory(
    service=tasks_service,
    scope=ContentScope.USER_OWNED,  # Default
    ...
)

# Curriculum domain (shared)
CRUDRouteFactory(
    service=ku_service,
    scope=ContentScope.SHARED,
    ...
)
```

**See:** `/docs/patterns/ROUTE_FACTORIES.md`

## Domain Route Configuration

**Core Principle:** "Configuration over code for route registration"

DomainRouteConfig pattern eliminates route wiring boilerplate (80 lines → 15 lines per domain).

**Pattern:**
```python
{DOMAIN}_CONFIG = DomainRouteConfig(
    domain_name="tasks",
    primary_service_attr="tasks",  # services.tasks
    api_factory=create_tasks_api_routes,
    ui_factory=create_tasks_ui_routes,
    api_related_services={
        # Format: {kwarg_name: container_attr}
        "user_service": "user_service",  # Passed as user_service=services.user_service
        "goals_service": "goals",        # Passed as goals_service=services.goals
    },
)

def create_tasks_routes(app, rt, services, _sync_service=None):
    return register_domain_routes(app, rt, services, TASKS_CONFIG)
```

**Current users:** 12 of 27 route files (44% adoption)
- Activity domains (6): tasks, goals, habits, events, choices, principles
- Other domains (6): learning, knowledge, context, reports, finance, askesis

**See:** `/docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md`, `/docs/migrations/DOMAIN_ROUTE_CONFIG_MIGRATION_2026-01-24.md`

## FastHTML Best Practices

**Core Principle:** "Remove ceremony, leverage smart defaults"

- Query parameters over path parameters (`/tasks/get?uid=...`)
- POST for all mutations
- Type hints for automatic parameter extraction

**Critical:** Do NOT use `routes = []` / `routes.append()` with `@rt()`. The decorator registers immediately.

**See:** `/docs/patterns/FASTHTML_ROUTE_REGISTRATION.md`

## Intelligence Services Architecture

**Core Principle:** "Graph analytics separated from AI - app runs without LLM dependencies"

**Two-Tier Design:**

| Layer | Base Class | Dependencies |
|-------|------------|--------------|
| Analytics | `BaseAnalyticsService` | Graph + Python (NO AI) |
| AI | `BaseAIService` | LLM + Embeddings (optional) |

All 10 domain `*_intelligence_service.py` files extend `BaseAnalyticsService`. AI features go in separate `*_ai_service.py` files.

**UserContextIntelligence (Central Hub):**
- `get_ready_to_work_on_today()` - THE FLAGSHIP
- `get_optimal_next_learning_steps()`
- `calculate_life_path_alignment()`
- `get_schedule_aware_recommendations()`

**Location:** `core/services/user/intelligence/` (modular package)

**See:** `/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md`

## Embedding Text Extraction

**Core Principle:** "Single source of truth for embedding field mappings"

**Location:** `/core/utils/embedding_text_builder.py`

**Usage:**
```python
from core.utils.embedding_text_builder import build_embedding_text
from core.models.shared_enums import EntityType

# From dict (ingestion path)
text = build_embedding_text(EntityType.TASK, {"title": "Fix bug", "description": "Details"})

# From model (background worker path)
text = build_embedding_text(EntityType.TASK, task_model)
```

**Field Mappings:** See `EMBEDDING_FIELD_MAPS` in the utility for canonical field list per entity type.

**Supported Entity Types:** KU, Task, Goal, Habit, Event, Choice, Principle (7 total)

**Key Design:**
- KU uses double newline separator (`\n\n`) for semantic section separation
- All other domains use single newline (`\n`)
- Graceful handling of missing/empty fields (returns empty string, no exceptions)
- Duck typing via `getattr()` with sentinel pattern (SKUEL011 compliant)

## Quick Reference: Key Files

| Purpose | Location |
|---------|----------|
| Service composition | `/core/utils/services_bootstrap.py` |
| Base service | `/core/services/base_service.py` |
| Base analytics | `/core/services/base_analytics_service.py` |
| Domain enums | `/core/models/shared_enums.py` |
| Protocols | `/core/services/protocols/` |
| Generic backend | `/adapters/persistence/neo4j/universal_backend.py` |
| Event bus | `/core/events/event_bus.py` |
| Route factories | `/adapters/inbound/route_factories.py` |
| ADRs | `/docs/decisions/` |
| Patterns | `/docs/patterns/` |
| Architecture | `/docs/architecture/` |
| Troubleshooting | `/docs/TROUBLESHOOTING.md` |

## Troubleshooting

**Core Principle:** "Document errors when fixed"

Common deployment and development issues with solutions:

**Server Won't Start:**
- Port 8000 in use: `lsof -ti:8000 | xargs kill -9 2>/dev/null || true`
- Embeddings service error: Now optional (graceful degradation to keyword search)
- Import errors: Check FastHTML components from `fasthtml.common`, not `core.ui.daisy_components`

**Routes Return 404:**
- Check if both API and UI routes registered in `bootstrap.py`
- Verify route factory called: `grep "routes registered" /tmp/server.log`
- Distinguish 401 (auth required, route exists) vs 404 (route missing)

**Type Errors:**
- Forward reference unions: Use `Optional["Type"]` not `"Type" | None`
- Missing imports: `Any`, `Optional`, `Union` from `typing`

**See:** `/docs/TROUBLESHOOTING.md` for complete diagnostic guide
