---
title: SKUEL Architecture — 14 Domains + 5 Cross-Cutting Systems
updated: 2026-03-03
status: current
category: architecture
version: 5.0.0
tags:
- architecture
- domain
- fourteen
related:
- ADR-040-teacher-assignment-workflow
- ADR-041-unified-ku-model
---

# SKUEL Architecture

## Executive Summary

SKUEL is a **knowledge-centric productivity platform** where every operation connects to and enriches understanding. **Knowledge is the fertile soil from which all activity grows.**

### 14 Domains + 5 Cross-Cutting Systems

| Category | Domains | Purpose |
|----------|---------|---------|
| **Activity (6)** | Tasks, Goals, Habits, Events, Principles, Choices | What I DO |
| **Finance (1)** | Finance | What I MANAGE (standalone) |
| **Curriculum (3)** | KU, LearningStep, LearningPath | What I LEARN |
| **Submissions + Feedback (1)** | Submissions + Feedback | How I PROCESS |
| **Organizational (2)** | Groups, MOC | How I ORGANIZE |
| **LifePath (1)** | LifePath | Where I'm GOING |

**Cross-Cutting Systems (5)**: UserContext (✅), Search (✅), Calendar (✅), Askesis (✅), Messaging (📋 planned)

**Core Philosophy**: "Everything flows toward the life path."

---

## Architecture Layers

```
External World (HTTP/Files)
        ↓
┌────────────────────────────────────────────────────────┐
│                    INBOUND LAYER                        │
│  FastHTML Routes → Pydantic → @boundary_handler        │
│  Location: /adapters/inbound/                          │
│  Pattern: DomainRouteConfig → API + UI route factories │
└────────────────────────────────────────────────────────┘
        ↓ Services container
┌────────────────────────────────────────────────────────┐
│                    SERVICE LAYER                        │
│  Business Logic with Protocol Dependencies             │
│  Location: /core/services/                             │
│  Returns: Result[T] for all operations                 │
└────────────────────────────────────────────────────────┘
        ↓ Protocol interfaces
┌────────────────────────────────────────────────────────┐
│                    DOMAIN LAYER                         │
│  Frozen Domain Models (Dataclasses)                    │
│  Location: /core/models/                               │
│  Pattern: Three-Tier (Pydantic → DTO → Domain)         │
└────────────────────────────────────────────────────────┘
        ↓ Backend protocols
┌────────────────────────────────────────────────────────┐
│                    PERSISTENCE LAYER                    │
│  UniversalNeo4jBackend + Domain Backends               │
│  Location: /adapters/persistence/neo4j/                │
│  Storage: Neo4j Graph Database                         │
└────────────────────────────────────────────────────────┘
```

**Routing flow:** Bootstrap builds `Services` container → route factories receive services → API/UI handlers call service methods → `@boundary_handler` converts `Result[T]` to HTTP responses. Routes know services; services know protocols; backends know the database. Zero concrete cross-layer dependencies.

**Key files:**
- `services_bootstrap.py` — wires all backends + services
- `core/ports/` — all protocol interfaces (10 files)
- `adapters/persistence/neo4j/universal_backend.py` — generic backend (6-mixin shell, ~527 lines)

---

## Domain Model Architecture

### Model Hierarchy

```
Entity (~18 fields: uid, entity_type, title, description, status, tags, ...)
├── UserOwnedEntity(Entity) +3 fields (user_uid, visibility, priority)
│   ├── Task, Goal, Habit, Event, Choice, Principle  (Activity)
│   ├── LifePath                                      (Destination)
│   ├── ActivityReport                                (Activity feedback — no file fields)
│   └── Submission → Journal, SubmissionFeedback      (Submissions/Feedback)
├── Curriculum(Entity) +21 fields (base class only)
│   └── Ku(Curriculum) + LearningStep, LearningPath, Exercise
└── Resource(Entity) +7 fields                        (Curated content)
```

### DTO Hierarchy

```
EntityDTO (~18 fields)
├── UserOwnedDTO(EntityDTO) +3 → TaskDTO, GoalDTO, HabitDTO, EventDTO, ChoiceDTO, PrincipleDTO
├── UserOwnedDTO → ActivityReportDTO              (no file fields)
├── UserOwnedDTO → SubmissionDTO → JournalDTO, SubmissionFeedbackDTO
├── CurriculumDTO(EntityDTO) → KuDTO, LearningStepDTO, LearningPathDTO, ExerciseDTO
└── ResourceDTO(EntityDTO)
```

Cross-domain services use `ENTITY_TYPE_CLASS_MAP` for generic entity deserialization.

### Neo4j Multi-Label

Every entity node gets two labels: `:Entity` (universal) + domain-specific (`:Task`, `:Goal`, etc.).

**`NeoLabel` enum** (`/core/models/enums/neo_labels.py`):

| Category | Labels |
|----------|--------|
| Universal | `:Entity` (all entity nodes) |
| Activity (6) | `:Task`, `:Goal`, `:Habit`, `:Event`, `:Choice`, `:Principle` |
| Curriculum (4) | `:Curriculum`, `:Resource`, `:LearningStep`, `:LearningPath` |
| Content (4) | `:Submission`, `:Journal`, `:ActivityReport`, `:SubmissionFeedback` |
| Instruction | `:Exercise` |
| Destination | `:LifePath` |

User relationships use `:OWNS`. Entity creation always produces dual labels:

```cypher
CREATE (n:Entity:Task {uid: $uid, ...})
CREATE (n:Entity:Goal {uid: $uid, ...})
```

**Key files:**
- `/core/models/entity.py` — `Entity` + `UserOwnedEntity` base classes
- `/core/models/enums/entity_enums.py` — `EntityType` (16 values), `EntityStatus`

---

## The 14-Domain Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         THE DESTINATION (Domain #14)                     │
│                              ┌─────────────┐                             │
│                              │  LIFEPATH   │                             │
│                              └──────┬──────┘                             │
│                   Everything flows toward the life path                  │
└──────────────────────────────────────┬──────────────────────────────────┘
                                       │
        ┌──────────────────────────────┼──────────────────────────────┐
        │                              │                              │
        ▼                              ▼                              ▼
┌──────────────┐            ┌─────────────────┐            ┌───────────────┐
│CONTENT/PROC  │            │ACTIVITY DOMAINS │            │  CURRICULUM   │
│ (1 domain)   │            │ (6) + FINANCE   │            │  DOMAINS (3)  │
│              │            │ What I DO       │            │ What I LEARN  │
│ Submissions  │◄──────────►│ • Tasks         │◄──────────►│ • KU (point)  │
│  + Feedback  │            │ • Habits        │            │ • LS (edge)   │
│              │            │ • Goals         │            │ • LP (path)   │
│──────────────│            │ • Events        │            └───────────────┘
│ORGANIZATIONAL│            │ • Principles    │
│ (2 domains)  │            │ • Choices       │
│ • Groups     │            │ ─────────────── │
│ • MOC        │            │ • Finance (1)   │
└──────────────┘            └─────────────────┘
                                       │
                                       ▼
        ┌────────────────────────────────────────────────────────────┐
        │                 CROSS-CUTTING SYSTEMS (5)                   │
        │   UserContext • Search • Calendar • Askesis • Messaging     │
        │   + Analytics (meta-service — not a domain)                 │
        └────────────────────────────────────────────────────────────┘
```

---

## Domain Categories

### 1. Activity Domains (6) — What I DO

Independent entities users create, track, and complete. All inherit from `UserOwnedEntity(Entity)`.

| Domain | Model | Purpose | Key Characteristics |
|--------|-------|---------|---------------------|
| **Tasks** | `Task` | Work items to complete | One-time, deadline-driven |
| **Habits** | `Habit` | Behaviors to build | Recurring, streak-tracked |
| **Goals** | `Goal` | Outcomes to achieve | Milestones, progress-measured |
| **Events** | `Event` | Time commitments | Scheduled, calendar-based |
| **Principles** | `Principle` | Values to embody | Guiding philosophy |
| **Choices** | `Choice` | Decisions to make | Options, outcome-tracked |

**Service pattern** (all 6 domains):

```
{Domain}Service (Facade)
├── .core          → {Domain}CoreService        (CRUD + status transitions)
├── .search        → {Domain}SearchService      (Discovery)
├── .relationships → UnifiedRelationshipService ({DOMAIN}_CONFIG)
└── .intelligence  → {Domain}IntelligenceService (Analytics — NO AI)
```

Common sub-services created via `create_common_sub_services()` factory (`core/utils/activity_domain_config.py`). Domain-specific sub-services (e.g., `PlanningService`, `SchedulingService`) added after.

**Access model**: `ContentScope.USER_OWNED` — user creates, only owner sees via `(User)-[:OWNS]->(Entity)`.

---

### 2. Finance Domain (1) — What I MANAGE

Finance is its **own domain group**, NOT an Activity Domain.

| Domain | Purpose | Key Characteristics |
|--------|---------|---------------------|
| **Finance** | Resources to manage | Income, expenses, budgets — **admin-only** |

Standalone facade with 4 sub-services (Core, Budget, Reporting, Invoice). No intelligence service, no relationship configuration. All Finance routes require ADMIN role.

---

### 3. Curriculum Domains (3) — What I LEARN

Educational foundation through three grouping patterns. All inherit from `Curriculum(Entity)`.

| Pattern | UID Format | Topology | Purpose |
|---------|-----------|----------|---------|
| **KU** | `ku_{slug}_{random}` | Point | Atomic unit of knowledge |
| **LS** | `ls:{random}` | Edge | Single step in a learning journey |
| **LP** | `lp:{random}` | Path | Complete learning sequence |

**Two paths to knowledge (Montessori-inspired):**
- **LS Path**: Structured, linear, teacher-directed (KU → LS → LP)
- **MOC Path**: Unstructured, graph, learner-directed (any Entity ORGANIZES others)

**Access model**: `ContentScope.SHARED` + `require_role=UserRole.ADMIN` — admin creates, all users read.

**Service architecture:**
```
KuService (facade)
├── KuCoreService          – CRUD
├── KuSearchService        – Search & discovery
├── KuGraphService         – Graph navigation
├── KuSemanticService      – Semantic relationships
├── KuLpService            – Learning path integration
├── KuPracticeService      – Practice tracking
├── KuOrganizationService  – MOC organization/navigation
└── KuInteractionService   – VIEWED → IN_PROGRESS → MASTERED

LpService (facade)
├── LpCoreService, LpValidationService, LpContextService
├── LpAnalysisService, LpAdaptiveService, LpProgressService
└── LpRelationshipService, LpSearchService

LsService (facade)
└── LsCoreService, LsRelationshipService, LsSearchService
```

**Knowledge Substance Philosophy** — knowledge measured by how it's LIVED:

| Application | Weight | Max |
|-------------|--------|-----|
| Habits | 0.10 | 0.30 |
| Journals | 0.07 | 0.20 |
| Choices | 0.07 | 0.15 |
| Events | 0.05 | 0.25 |
| Tasks | 0.05 | 0.25 |

**See:** `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md`

---

### 4. Submissions + Feedback (1) — How I PROCESS

The educational loop: `Ku → Exercise → Submission → Feedback`. Activity Domains are equal entry points via `ACTIVITY_REPORT`.

| EntityType | Inherits | ProcessorType | Description |
|------------|---------|---------------|-------------|
| `SUBMISSION` | `Submission(UserOwnedEntity)` | `HUMAN` or `LLM` | Student work against an Exercise |
| `JOURNAL` | `Submission(UserOwnedEntity)` | `LLM` | AI-processed reflective writing |
| `SUBMISSION_FEEDBACK` | `Submission(UserOwnedEntity)` | `HUMAN` or `LLM` | Assessment tied to a submission via `subject_uid` |
| `ACTIVITY_REPORT` | `UserOwnedEntity` **directly** | `AUTOMATIC`, `LLM`, or `HUMAN` | Activity-level feedback (no file fields; covers a time window) |

`ACTIVITY_REPORT` does NOT inherit from `Submission` — no file fields. It responds to aggregate activity patterns over a time period, not to a specific artifact.

**Services split:**
- `core/services/submissions/` — `ActivityReportService`, `ReviewQueueService`, student work pipeline
- `core/services/feedback/` — `FeedbackService`, `ProgressFeedbackGenerator`, `ProgressScheduleService`

**See:** `/docs/architecture/FEEDBACK_ARCHITECTURE.md`

---

### 5. Organizational Domains (2) — How I ORGANIZE

#### Groups (ADR-040)

Groups mediate ALL teacher-student relationships. Teacher creates group → adds students → assigns exercises to the group.

| Aspect | Description |
|--------|-------------|
| **Purpose** | Teacher-student class management |
| **UID Format** | `group_{slug}_{random}` |
| **Access** | TEACHER role required for creation |

**Key relationships:**
```cypher
(teacher:User)-[:OWNS]->(group:Group)
(student:User)-[:MEMBER_OF {joined_at, role}]->(group:Group)
(exercise:Exercise)-[:FOR_GROUP]->(group:Group)
(submission:Submission)-[:FULFILLS_EXERCISE]->(exercise:Exercise)
```

**See:** `/docs/decisions/ADR-040-teacher-assignment-workflow.md`

#### MOC (Map of Content)

MOC is NOT a separate entity — it IS an Entity (KU) with `ORGANIZES` relationships. An Entity "is" a MOC when it has outgoing `ORGANIZES` relationships (emergent identity). Managed by `KuOrganizationService` (sub-service of `KuService`).

| Path | Topology | Purpose | Pedagogy |
|------|----------|---------|----------|
| **LS** | Linear | Structured curriculum | Teacher-directed |
| **MOC** | Graph | Free exploration | Learner-directed |

```cypher
// Create organization
(parent:Entity)-[:ORGANIZES {order: int}]->(child:Entity)

// Check if Entity is a MOC
MATCH (e:Entity {uid: $uid})
OPTIONAL MATCH (e)-[:ORGANIZES]->(child)
RETURN count(child) > 0 AS is_moc
```

**See:** `/docs/domains/moc.md`

---

### 6. LifePath (1) — The Destination

LifePath is Domain #14 — the destination toward which everything flows. Inherits `UserOwnedEntity(Entity)`.

| Aspect | Description |
|--------|-------------|
| **Purpose** | Answer "Am I living my life path?" |
| **Key Insight** | Bridges VISION (words) with ACTIONS (behavior) |
| **Measurement** | 5-dimension alignment score (0.0-1.0) |

**5-Dimension Alignment:**

| Dimension | Weight |
|-----------|--------|
| Knowledge | 25% |
| Activity | 25% |
| Goal | 20% |
| Principle | 15% |
| Momentum | 15% |

**Key relationships:**
```
(User)-[:ULTIMATE_PATH]->(Lp)          # User's designated life path
(Entity)-[:SERVES_LIFE_PATH]->(Lp)     # Entity contributes to life path
```

**Service structure:**
```
LifePathService (facade)
├── .vision       → LifePathVisionService      (capture, analyze, recommend)
├── .core         → LifePathCoreService        (designation CRUD)
├── .alignment    → LifePathAlignmentService   (calculate alignment)
└── .intelligence → LifePathIntelligenceService (recommendations)
```

**See:** `/docs/domains/lifepath.md`

---

## Cross-Cutting Systems

| System | Purpose | Status |
|--------|---------|--------|
| **UserContext** | ~240 fields of cross-domain state, built by one MEGA-QUERY | Active |
| **Search** | Unified search across all domains | Active |
| **Calendar** | Aggregates Tasks, Events, Habits, Goals | Active |
| **Askesis** | Life context synthesis + LLM integration | Active |
| **Messaging** | Notifications, alerts | Planned |

**Analytics** is a meta-service (statistical aggregation across domains), not a cross-cutting system. See `/docs/architecture/ANALYTICS_ARCHITECTURE.md`.

---

## Activity DSL

The Activity DSL enables natural language parsing into all 14 domains:

```
- [ ] Complete project report    @context(task)      @when(2025-12-01) @priority(1)
- [ ] Morning meditation         @context(habit)     @repeat(daily) @duration(20m)
- [ ] Launch MVP                 @context(goal)      @when(2025-Q1)
- [ ] Team standup               @context(event)     @when(2025-11-28T09:00)
- [ ] Practice non-attachment    @context(principle) @energy(spiritual)
- [ ] Choose tech stack          @context(choice)    @link(goal:mvp-launch)
- [ ] AWS hosting $150           @context(finance)   @category(skuel)
- [ ] Python async/await         @context(ku)        @energy(focus)
- [ ] Complete async exercises   @context(ls)        @ku(ku:python/async)
- [ ] Master async programming   @context(lp)        @link(goal:python-expert)
- [ ] Embody wisdom and service  @context(lifepath)  @link(principle:service)
```

**Processing pipeline:**
```
Natural Text
    → LLMDSLBridgeService.transform()        # GPT-4o-mini adds @context tags
    → ActivityDSLParser.parse_journal()       # ParsedJournal (domain buckets)
    → ActivityEntityConverter.convert()       # Domain-typed create requests
    → ActivityExtractorService.extract_and_create()  # SKUEL entities + graph relationships
```

**See:** `/docs/dsl/DSL_SPECIFICATION.md`

---

## Graph Architecture

### Key Relationship Patterns

```cypher
// User ownership
(user:User)-[:OWNS]->(entity:Entity)

// Activity domain connections
(task:Task)-[:APPLIES_KNOWLEDGE]->(ku:Curriculum)
(task:Task)-[:FULFILLS_GOAL]->(goal:Goal)
(task:Task)-[:DEPENDS_ON]->(task:Task)
(habit:Habit)-[:REINFORCES_KNOWLEDGE]->(ku:Curriculum)
(habit:Habit)-[:SUPPORTS_GOAL]->(goal:Goal)
(goal:Goal)-[:GUIDED_BY_PRINCIPLE]->(principle:Principle)
(goal:Goal)-[:SUBGOAL_OF]->(goal:Goal)

// Curriculum
(ku:Curriculum)-[:REQUIRES_KNOWLEDGE]->(ku:Curriculum)
(ku:Curriculum)-[:ENABLES_KNOWLEDGE]->(ku:Curriculum)
(lp:LearningPath)-[:HAS_NARROWER]->(ls:LearningStep)
(ls:LearningStep)-[:REQUIRES_PREREQUISITE]->(ku:Curriculum)

// MOC organization
(entity:Entity)-[:ORGANIZES {order: int}]->(entity:Entity)

// Groups + exercises (ADR-040)
(teacher:User)-[:OWNS]->(group:Group)
(student:User)-[:MEMBER_OF {joined_at, role}]->(group:Group)
(exercise:Exercise)-[:FOR_GROUP]->(group:Group)
(submission:Submission)-[:FULFILLS_EXERCISE]->(exercise:Exercise)

// Sharing
(user:User)-[:SHARES_WITH {role, shared_at}]->(entity:Entity)
(entity:Entity)-[:SHARED_WITH_GROUP]->(group:Group)

// Life path
(user:User)-[:ULTIMATE_PATH]->(lp:LearningPath)
(entity:Entity)-[:SERVES_LIFE_PATH]->(lp:LearningPath)
```

Full taxonomy: 70+ typed relationship names in `RelationshipName` enum (`core/models/relationship_names.py`).

**See:** `/docs/architecture/RELATIONSHIPS_ARCHITECTURE.md`

---

## Core Design Principles

| Principle | Meaning |
|-----------|---------|
| **One Path Forward** | Single clear way to accomplish tasks — old patterns deleted, not deprecated |
| **Protocol-Based DI** | Two-tier strategy: facade services (9) use concrete class types in routes; thin/ISP services use protocol types; all backends depend on protocol interfaces |
| **Three-Tier Types** | Pydantic at edges (validation), DTOs for transfer, frozen dataclasses at core |
| **Result[T]** | `Result[T]` throughout services; `@boundary_handler` converts to HTTP at routes |
| **Fail-Fast** | All required dependencies raise at startup — no graceful degradation |
| **Async for I/O** | Database/service layer async; data conversion and models are sync |
| **Graph-Native** | All auth, sessions, relationships in Neo4j — no external services |

**Why Protocols?** Services depend on abstractions, not implementations. Zero circular imports, easy mocking in tests, MyPy validates at development time.

**Why Neo4j?** Knowledge is inherently graph-structured. Relationships are first-class citizens. Optimal for deep traversal (prerequisites, life-path alignment, cross-domain intelligence).

**Why frozen domain models?** Immutable business entities can't be accidentally modified. Clean separation: external validation (Pydantic), data transfer (DTOs), core logic (frozen dataclasses).

---

## See Also

| Document | What it covers |
|----------|---------------|
| [UNIFIED_USER_ARCHITECTURE.md](UNIFIED_USER_ARCHITECTURE.md) | User model, auth, roles, UserContext (~240 fields) |
| [FEEDBACK_ARCHITECTURE.md](FEEDBACK_ARCHITECTURE.md) | ActivityReport, SubmissionFeedback, all feedback types |
| [RELATIONSHIPS_ARCHITECTURE.md](RELATIONSHIPS_ARCHITECTURE.md) | UnifiedRelationshipService, relationship taxonomy |
| [CURRICULUM_GROUPING_PATTERNS.md](CURRICULUM_GROUPING_PATTERNS.md) | KU/LS/LP/MOC patterns |
| [ANALYTICS_ARCHITECTURE.md](ANALYTICS_ARCHITECTURE.md) | Analytics meta-service |
| [SEARCH_ARCHITECTURE.md](SEARCH_ARCHITECTURE.md) | Unified search across all domains |
| [/docs/patterns/protocol_architecture.md](../patterns/protocol_architecture.md) | Protocol-based dependency injection |
| [/docs/patterns/three_tier_type_system.md](../patterns/three_tier_type_system.md) | Type system details |
| [/docs/patterns/ERROR_HANDLING.md](../patterns/ERROR_HANDLING.md) | Result[T] pattern |
| [/docs/dsl/DSL_SPECIFICATION.md](../dsl/DSL_SPECIFICATION.md) | Activity DSL specification |
| [/docs/domains/](../domains/) | Individual domain documentation |
