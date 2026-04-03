---
title: SKUEL Architecture — 22 Entity Types + 5 Cross-Cutting Systems
updated: 2026-04-02
status: current
category: architecture
version: 7.0.0
tags:
- architecture
- entity-types
related:
- ADR-040-teacher-exercise-workflow
- ADR-041-unified-ku-model
- ADR-047-entity-types-replace-domain-categories
- ADR-051-user-interaction-contract
---

# SKUEL Architecture

## Executive Summary

SKUEL is a **knowledge-centric productivity platform** where every operation connects to and enriches understanding. **Knowledge is the fertile soil from which all activity grows.**

### 22 Entity Types + 5 Cross-Cutting Systems

| EntityType | What It Is | Ownership |
|------------|-----------|-----------|
| Task | Work to be done | User-owned |
| Goal | Outcome to achieve | User-owned |
| Habit | Behavior to build | User-owned |
| Event | Time commitment to keep | User-owned |
| Choice | Decision to make | User-owned |
| Principle | Value to embody | User-owned |
| Ku | Atomic knowledge unit (concept, principle, substance) | Admin-created, shared |
| Resource | Curated content (books, talks, films) | Admin-created, shared |
| PathStep | THE curriculum content entity (composes Kus into learning content) | Admin-created, shared |
| LearningPath | An ordered sequence of PathSteps | Admin-created, shared |
| Exercise | Instruction template, assignment, or formal assessment | Admin-created, shared |
| FormTemplate | Reusable form definition | Admin-created, shared |
| FormSubmission | User response to a FormTemplate | User-owned |
| ExerciseSubmission | Student-uploaded work against an exercise | User-owned |
| Interaction | Situated learning-loop event (curriculum context at submission time) | User-owned |
| JeInput | Journal entry input (voice/text) | User-owned |
| JeOutput | Journal entry output (LLM-transformed) | User-owned |
| ExerciseReport | Assessment tied to a specific submission | User-owned |
| ActivityReport | Feedback about activity patterns over time | User-owned |
| RevisedExercise | Targeted revision after feedback | Teacher-owned |
| LifePath | The user's life direction | User-owned |
| Groups | Teacher-student class management | Teacher-owned |

**Cross-Cutting Systems (5)**: UserContext, Search, Calendar, Askesis, Messaging (planned)

**Core Philosophy**: "Everything flows toward the life path."

---

## Architecture Layers

```
External World (HTTP/Files)
        |
+--------------------------------------------------------+
|                    INBOUND LAYER                        |
|  FastHTML Routes -> Pydantic -> @boundary_handler       |
|  Location: /adapters/inbound/                           |
|  Pattern: DomainRouteConfig -> API + UI route factories |
+--------------------------------------------------------+
        | Services container
+--------------------------------------------------------+
|                    SERVICE LAYER                        |
|  Business Logic with Protocol Dependencies             |
|  Location: /core/services/                             |
|  Returns: Result[T] for all operations                 |
+--------------------------------------------------------+
        | Protocol interfaces
+--------------------------------------------------------+
|                    DOMAIN LAYER                         |
|  Frozen Domain Models (Dataclasses)                    |
|  Location: /core/models/                               |
|  Pattern: Three-Tier (Pydantic -> DTO -> Domain)       |
+--------------------------------------------------------+
        | Backend protocols
+--------------------------------------------------------+
|                    PERSISTENCE LAYER                    |
|  UniversalNeo4jBackend + Domain Backends               |
|  Location: /adapters/persistence/neo4j/                |
|  Storage: Neo4j Graph Database                         |
+--------------------------------------------------------+
```

**Routing flow:** Bootstrap builds `Services` container -> route factories receive services -> API/UI handlers call service methods -> `@boundary_handler` converts `Result[T]` to HTTP responses. Routes know services; services know protocols; backends know the database. Zero concrete cross-layer dependencies.

**`UniversalNeo4jBackend` is the hexagonal boundary.** Neo4j-specific code (Cypher strings, `AsyncDriver` calls, label conventions) lives at and below this boundary. Service mixins above it use graph vocabulary (`depth`, `traverse`, `graph_enrichment_patterns`) because SKUEL's domain model is inherently a graph — this is intentional, not leaky. Neo4j is a committed architectural choice, not a swappable adapter. See: [ADR-044](../decisions/ADR-044-neo4j-committed-architectural-choice.md).

**Key files:**
- `services_bootstrap/` — wires all backends + services
- `core/ports/` — all protocol interfaces (10 files)
- `adapters/persistence/neo4j/universal_backend.py` — generic backend (6-mixin shell, ~527 lines)

---

## Domain Model Architecture

### Model Hierarchy

```
Entity (~18 fields: uid, entity_type, title, description, status, tags, ...)
+-- UserOwnedEntity(Entity) +3 fields (user_uid, visibility, priority)
|   +-- Task, Goal, Habit, Event, Choice, Principle
|   +-- LifePath
|   +-- ActivityReport                           (no file fields)
|   +-- FormSubmission(UserOwnedEntity)          FORM_SUBMISSION (structured JSON)
|   +-- Submission(UserOwnedEntity) +14 file/processing/modality fields
|   |   +-- ExerciseSubmission(Submission)        EXERCISE_SUBMISSION
|   +-- ExerciseReport(UserOwnedEntity) +6 report fields (NOT Submission)    EXERCISE_REPORT
|   +-- JeInput(UserOwnedEntity)                  JE_INPUT (standalone journal domain)
|   +-- JeOutput(UserOwnedEntity)                 JE_OUTPUT (standalone journal domain)
|   +-- RevisedExercise(UserOwnedEntity)          REVISED_EXERCISE
+-- FormTemplate(Entity) — reusable form definition (shared, embeddable)
+-- Curriculum(Entity) +21 fields (base class only)
|   +-- Lesson(Curriculum), PathStep, LearningPath, Exercise
+-- Ku(Entity) — atomic knowledge unit
+-- Resource(Entity) +7 fields
```

### DTO Hierarchy

```
EntityDTO (~18 fields)
+-- UserOwnedDTO(EntityDTO) +3 -> TaskDTO, GoalDTO, HabitDTO, EventDTO, ChoiceDTO, PrincipleDTO
+-- UserOwnedDTO -> ActivityReportDTO              (no file fields)
+-- UserOwnedDTO -> FormSubmissionDTO              (structured JSON, no file fields)
+-- UserOwnedDTO -> SubmissionDTO -> ExerciseSubmissionDTO
+-- UserOwnedDTO -> ExerciseReportDTO  (NOT SubmissionDTO)
+-- UserOwnedDTO -> JeInputDTO, JeOutputDTO        (standalone journal domain)
+-- EntityDTO -> FormTemplateDTO                   (form_schema, instructions)
+-- CurriculumDTO(EntityDTO) -> LessonDTO, PathStepDTO, LearningPathDTO, ExerciseDTO
+-- KuDTO(EntityDTO)
+-- ResourceDTO(EntityDTO)
```

Cross-domain services use `ENTITY_TYPE_CLASS_MAP` for generic entity deserialization.

### Neo4j Multi-Label

Every entity node gets two labels: `:Entity` (universal) + type-specific (`:Task`, `:Goal`, etc.).

**`NeoLabel` enum** (`/core/models/enums/neo_labels.py`):

| Labels |
|--------|
| `:Entity` (universal — all entity nodes) |
| `:Task`, `:Goal`, `:Habit`, `:Event`, `:Choice`, `:Principle` |
| `:Curriculum`, `:Resource`, `:PathStep`, `:LearningPath` |
| `:FormTemplate`, `:FormSubmission` |
| `:Submission`, `:ExerciseSubmission` |
| `:ExerciseReport` |
| `:JeInput`, `:JeOutput` |
| `:ActivityReport` |
| `:Exercise` |
| `:LifePath` |

User relationships use `:OWNS`. Entity creation always produces dual labels:

```cypher
CREATE (n:Entity:Task {uid: $uid, ...})
CREATE (n:Entity:Goal {uid: $uid, ...})
```

**Key files:**
- `/core/models/entity.py` — `Entity` + `UserOwnedEntity` base classes
- `/core/models/enums/entity_enums.py` — `EntityType` (21 values), `EntityStatus`

---

## Entity Types and Behavioral Traits

Each entity type is a peer — no hierarchy of categories. Behavioral traits (not category membership) determine how an entity is handled.

### Behavioral Traits

| Trait | Method | What It Determines |
|-------|--------|--------------------|
| **Ownership** | `requires_user_uid()` | User-owned vs shared (admin-created) |
| **Content Origin** | `content_origin()` | Where content comes from (4 tiers: Curated, Curriculum, User-Created, Report) |
| **Processable** | `is_processable()` | Goes through a processing pipeline |
| **Derived** | `is_derived()` | Has parent in derivation chain |
| **Activity** | `is_activity()` | Shares Activity infrastructure (factory, facade, sub-services) |

These methods exist on `EntityType` in `entity_enums.py`. They are the architecture.

**See:** [ADR-047](../decisions/ADR-047-entity-types-replace-domain-categories.md)

### The Activity Entity Types (6)

Task, Goal, Habit, Event, Choice, and Principle genuinely share infrastructure — `create_common_sub_services()` factory, facade pattern, `create_activity_domain_route_config()`, `UserOwnedEntity` base class with identical access patterns. This grouping reflects shared code, not an imposed label.

Events additionally has integration sub-services (`EventsHabitIntegrationService`, `EventsLearningService`) that bridge it with other Activity types. The `ActivityType` enum (12 types) gives Events polymorphic calendar coverage. The **Calendar** cross-cutting system aggregates Events, Tasks, Habits, and Goals into a unified timeline — Calendar is the scheduling system, Events are the things being scheduled.

**Service pattern** (all 6):

```
{Domain}Service (Facade)
+-- .core          -> {Domain}CoreService        (CRUD + status transitions)
+-- .search        -> {Domain}SearchService      (Discovery)
+-- .relationships -> UnifiedRelationshipService ({DOMAIN}_CONFIG)
+-- .intelligence  -> {Domain}IntelligenceService (Analytics — NO AI)
```

Common sub-services created via `create_common_sub_services()` factory (`core/services/activity_domain_config.py`). Domain-specific sub-services (e.g., `PlanningService`, `SchedulingService`) added after.

**Access model**: `ContentScope.USER_OWNED` — user creates, only owner sees via `(User)-[:OWNS]->(Entity)`.

### Finance — Admin-Only Bookkeeping

Standalone facade with 4 sub-services (Core, Budget, Reporting, Invoice). No intelligence service, no relationship configuration. All Finance routes require ADMIN role. Does NOT use `BaseService` or `BaseAnalyticsService`.

### Lesson, Ku, PathStep, LearningPath, Exercise — Curriculum

Educational foundation. Lesson extends `Curriculum(Entity)`. Ku extends `Entity` directly (lightweight atomic unit). All admin-created, publicly readable via `ContentScope.SHARED`.

### Resource — Curated External Content

Pointers to external content (books, talks, films) that Askesis can recommend. Resource extends `Entity` directly (+7 fields). Admin-created, publicly readable via `ContentScope.SHARED`. Resource is NOT curriculum — it does not participate in the `Lesson → Exercise → Submission → Report → RevisedExercise` loop. Its `ContentOrigin` is `CURATED` (tier A), distinct from curriculum's `CURRICULUM` (tier B).

**Two paths to knowledge (Montessori-inspired):**
- **PS Path**: Structured, linear, teacher-directed (Lesson -> PS -> LP)
- **MOC Path**: Unstructured, graph, learner-directed (any Entity ORGANIZES others)

**Service architecture:**
```
KuService (facade) — 4 sub-services via create_curriculum_sub_services()
├── core: KuCoreService
├── search_service: KuSearchService
├── relationships: UnifiedRelationshipService
└── intelligence: KuIntelligenceService

PsService (facade) — 4 sub-services via create_curriculum_sub_services()
├── core: PsCoreService
├── search: PsSearchService
├── relationships: UnifiedRelationshipService
└── intelligence: PsIntelligenceService

LpService (facade) — 5 sub-services via create_lp_sub_services()
├── core: LpCoreService
├── search: LpSearchService
├── relationships: UnifiedRelationshipService
├── intelligence: LpIntelligenceService
└── progress: LpProgressService
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

### Exercise Scope — Three Modes of Assessment

Exercise is a single entity type serving three distinct pedagogical roles via `ExerciseScope`:

| Scope | Purpose | Key Fields | Mastery Signal |
|-------|---------|------------|----------------|
| `PERSONAL` | User's own AI feedback template (default) | `instructions`, `model` | Soft — AI-evaluated |
| `ASSIGNED` | Teacher assigns to a group | `group_uid` (required), `due_date` | Medium — teacher-approved |
| `ASSESSMENT` | Formal test/exam with scoring rubric | `scoring_rubric` (required), `pass_threshold` | Hard — objective score |

**ASSESSMENT scope** adds two fields to Exercise:
- `scoring_rubric`: List of criteria, each with `name`, `weight` (must sum to 1.0), and optional `description`
- `pass_threshold`: Minimum score (0.0-1.0) to pass; defaults to 0.7

**ExerciseReport** carries `assessment_score` (0.0-1.0) for ASSESSMENT-scope exercises — the numeric result evaluated against the rubric. This is the **objective measurement layer** that substance tracking and ExerciseReports don't otherwise provide.

**Design rationale:** A Test is an Exercise with `scope=ASSESSMENT` and a scoring rubric — not a separate entity type. The learning loop (`Exercise → Submission → Report → RevisedExercise`) applies identically to all three scopes. What differs is the evaluation mechanism (AI feedback vs teacher review vs rubric scoring) and the strength of the mastery signal.

### FormTemplate + FormSubmission — General-Purpose Forms

A general-purpose form system decoupled from the learning loop. Admin creates reusable form templates, embeds them in Lessons via `EMBEDS_FORM` relationships, and users submit structured responses. Submissions flow through the existing sharing infrastructure (groups, direct sharing, admin).

| EntityType | Inherits | Description |
|------------|---------|-------------|
| `FORM_TEMPLATE` | `Entity` directly | Reusable form definition with `form_schema` (field specs) |
| `FORM_SUBMISSION` | `UserOwnedEntity` | User response storing structured JSON `form_data` |

FormTemplate extends `Entity` (NOT Curriculum — doesn't need 21 Curriculum fields). `ContentOrigin.CURATED`, publicly readable via `ContentScope.SHARED`. FormSubmission extends `UserOwnedEntity` (NOT Submission — no file fields). `ContentOrigin.USER_CREATED`, `is_derived()=True`.

**Graph relationships:**
```cypher
(lesson:Lesson)-[:EMBEDS_FORM]->(ft:FormTemplate)
(fs:FormSubmission)-[:RESPONDS_TO_FORM]->(ft:FormTemplate)
(user:User)-[:OWNS]->(fs:FormSubmission)
```

**Data integrity:** Schema pinning (`template_schema_hash` on FormSubmission), atomic writes (`FormSubmissionBackend.create_with_relationships()`), canonical `processed_content` via `build_form_processed_content()`.

**Services:** `core/services/forms/form_template_service.py`, `core/services/forms/form_submission_service.py`, `core/services/forms/form_content.py`
**Protocols (two tiers):** `core/ports/form_protocols.py`
- Backend-level: `FormTemplateBackendOperations(BackendOperations["FormTemplate"])`, `FormSubmissionBackendOperations(BackendOperations["FormSubmission"])` — typed `self.backend` in services (import directly from `core.ports.form_protocols`)
- Route-level: `FormTemplateOperations`, `FormSubmissionOperations` — typed service in routes (re-exported from `core.ports`)

### Submissions, Reports, ActivityReport — Content Processing

The educational loop: `Lesson -> Exercise -> ExerciseSubmission -> ExerciseReport -> RevisedExercise -> ...`. Activity entity types are equal entry points via `ACTIVITY_REPORT`.

| EntityType | Inherits | ProcessorType | Description |
|------------|---------|---------------|-------------|
| `EXERCISE_SUBMISSION` | `Submission(UserOwnedEntity)` | `HUMAN` or `LLM` | Student work against an Exercise |
| `EXERCISE_REPORT` | `ExerciseReport(UserOwnedEntity)` | `HUMAN` or `LLM` | Assessment tied to a submission via `subject_uid` |
| `ACTIVITY_REPORT` | `UserOwnedEntity` **directly** | `AUTOMATIC`, `LLM`, or `HUMAN` | Activity-level feedback (no file fields; covers a time window) |

**Key structural note:** `ExerciseReport` extends `UserOwnedEntity` directly — NOT `Submission`. It has 7 report-specific fields (`report_content`, `report_generated_at`, `subject_uid`, `processor_type`, `assessment_outcome`, `report_file_path`, `assessment_score`) but no file/processing fields. `assessment_outcome` (`AssessmentOutcome` enum: APPROVED, NEEDS_REVISION, AI_EVALUATED) makes each report self-describing — the report records what decision was made, not just feedback text. `assessment_score` (0.0-1.0) carries the numeric result for ASSESSMENT-scope exercises.

`ACTIVITY_REPORT` also inherits `UserOwnedEntity` directly — no file fields. It responds to aggregate activity patterns over a time period, not to a specific artifact.

**Removed aliases:** `SUBMISSION` → `EXERCISE_SUBMISSION`, `JOURNAL` → `JOURNAL_SUBMISSION`, `SUBMISSION_REPORT` → `EXERCISE_REPORT` (removed from enum; old string values still parsed via `from_string()`).

**Services split:**
- `core/services/submissions/` — `ActivityReportService`, `ReviewQueueService`, student work pipeline
- `core/services/report/` — `ExerciseReportService`, `ProgressReportGenerator`, `ProgressScheduleService`

### JeInput + JeOutput — Standalone Journal Domain

Journal is a **standalone domain**, NOT under submissions/reports. Two entity types: `JeInput` (user's raw journal entry) and `JeOutput` (LLM-transformed output).

| EntityType | Inherits | Description |
|------------|---------|-------------|
| `JE_INPUT` | `UserOwnedEntity` directly | Journal entry input (voice/text), UID prefix `ji_` |
| `JE_OUTPUT` | `UserOwnedEntity` directly | Journal entry output (LLM-transformed), UID prefix `jo_` |

Both extend `UserOwnedEntity` directly (NOT `Submission` or `ExerciseReport`). `JeOutput` has `ContentOrigin.USER_CREATED` (not REPORT). Relationship: `(JeOutput)-[:TRANSFORMS]->(JeInput)`.

**Pipeline:** JE_INPUT(audio) → Deepgram → JE_INPUT(text) → LLM → JE_OUTPUT

**Models:** `core/models/journal/`
**Services:** `JournalInputService` (CRUD + file upload), `JournalOutputService` (LLM processing) in `core/services/journal/`

**See:** `/docs/architecture/REPORT_ARCHITECTURE.md`

### RevisedExercise — Five-Phase Learning Loop

Teacher-created revision of an Exercise that addresses specific `ExerciseReport` gaps. Extends `UserOwnedEntity` (NOT Curriculum — needs `user_uid` but not 21 Curriculum fields). `ContentOrigin.USER_CREATED` — teacher-authored content targeted at a specific student.

| EntityType | Inherits | Description |
|------------|---------|-------------|
| `REVISED_EXERCISE` | `UserOwnedEntity` | Teacher's revised instructions targeting a specific student |

**Graph relationships:**
- `RESPONDS_TO_REPORT` → ExerciseReport (what report this addresses)
- `REVISES_EXERCISE` → Exercise (what exercise this revises)
- `FULFILLS_EXERCISE` ← Submission (student submits against this)

**Service:** `core/services/revised_exercises/revised_exercise_service.py`
**See:** `/docs/architecture/LEARNING_LOOP_ARCHITECTURE.md`

### Groups — Teacher-Student Organization

Groups mediate ALL teacher-student relationships. Teacher creates group -> adds students -> assigns exercises to the group.

**Key relationships:**
```cypher
(teacher:User)-[:OWNS]->(group:Group)
(student:User)-[:MEMBER_OF {joined_at, role}]->(group:Group)
(exercise:Exercise)-[:FOR_GROUP]->(group:Group)
(submission:Submission)-[:FULFILLS_EXERCISE]->(exercise:Exercise)
```

**See:** `/docs/decisions/ADR-040-teacher-exercise-workflow.md`

### MOC (Map of Content) — Emergent Organization

MOC is NOT a separate entity — it IS an Entity with `ORGANIZES` relationships. An Entity "is" a MOC when it has outgoing `ORGANIZES` relationships (emergent identity). Managed by `KuOrganizationService` (sub-service of `KuService`).

```cypher
(parent:Entity)-[:ORGANIZES {order: int}]->(child:Entity)
```

**See:** `/docs/domains/moc.md`

### LifePath — The Destination

The destination toward which everything flows. Inherits `UserOwnedEntity(Entity)`.

**Philosophy:** Bridges VISION (declared intent) with ACTIONS (behavior).

**5-Dimension Alignment (0.0-1.0):**

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

**See:** `/docs/domains/lifepath.md`

---

## Cross-Cutting Systems

| System | Purpose | Status |
|--------|---------|--------|
| **UserContext** | ~240 fields of cross-domain state, built by one MEGA-QUERY | Active |
| **Search** | Unified search across all entity types | Active |
| **Calendar** | Aggregates Tasks, Events, Habits, Goals | Active |
| **Askesis** | Life context synthesis + LLM integration | Active |
| **Messaging** | Notifications, alerts | Planned |

**Analytics** is a meta-service (statistical aggregation across entity types), not a cross-cutting system. See `/docs/architecture/ANALYTICS_ARCHITECTURE.md`.

---

## Activity DSL

The Activity DSL enables natural language parsing into entity types:

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
    -> LLMDSLBridgeService.transform()        # GPT-4o-mini adds @context tags
    -> ActivityDSLParser.parse_journal()       # ParsedJournal (domain buckets)
    -> ActivityEntityConverter.convert()       # Domain-typed create requests
    -> ActivityExtractorService.extract_and_create()  # SKUEL entities + graph relationships
```

**See:** `/docs/dsl/DSL_SPECIFICATION.md`

---

## Graph Architecture

### Key Relationship Patterns

```cypher
// User ownership
(user:User)-[:OWNS]->(entity:Entity)

// Activity connections to knowledge
(task:Task)-[:APPLIES_KNOWLEDGE]->(ku:Curriculum)
(task:Task)-[:FULFILLS_GOAL]->(goal:Goal)
(task:Task)-[:DEPENDS_ON]->(task:Task)
(habit:Habit)-[:REINFORCES_KNOWLEDGE]->(ku:Curriculum)
(habit:Habit)-[:SUPPORTS_GOAL]->(goal:Goal)
(goal:Goal)-[:GUIDED_BY_PRINCIPLE]->(principle:Principle)
(goal:Goal)-[:SUBGOAL_OF]->(goal:Goal)

// Curriculum
(lesson:Lesson)-[:USES_KU]->(ku:Ku)
(ku:Curriculum)-[:REQUIRES_KNOWLEDGE]->(ku:Curriculum)
(ku:Curriculum)-[:ENABLES_KNOWLEDGE]->(ku:Curriculum)
(lp:LearningPath)-[:HAS_NARROWER]->(ps:PathStep)
(ps:PathStep)-[:REQUIRES_PREREQUISITE]->(ku:Curriculum)

// MOC organization
(entity:Entity)-[:ORGANIZES {order: int}]->(entity:Entity)

// Groups + exercises (ADR-040)
(teacher:User)-[:OWNS]->(group:Group)
(student:User)-[:MEMBER_OF {joined_at, role}]->(group:Group)
(exercise:Exercise)-[:FOR_GROUP]->(group:Group)
(submission:Submission)-[:FULFILLS_EXERCISE]->(exercise:Exercise)

// Forms
(lesson:Lesson)-[:EMBEDS_FORM]->(ft:FormTemplate)
(fs:FormSubmission)-[:RESPONDS_TO_FORM]->(ft:FormTemplate)

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
| [REPORT_ARCHITECTURE.md](REPORT_ARCHITECTURE.md) | ActivityReport, ExerciseReport, all report types |
| [RELATIONSHIPS_ARCHITECTURE.md](RELATIONSHIPS_ARCHITECTURE.md) | UnifiedRelationshipService, relationship taxonomy |
| [CURRICULUM_GROUPING_PATTERNS.md](CURRICULUM_GROUPING_PATTERNS.md) | KU/PS/LP/MOC patterns |
| [ANALYTICS_ARCHITECTURE.md](ANALYTICS_ARCHITECTURE.md) | Analytics meta-service |
| [SEARCH_ARCHITECTURE.md](SEARCH_ARCHITECTURE.md) | Unified search across all entity types |
| [/docs/patterns/protocol_architecture.md](../patterns/protocol_architecture.md) | Protocol-based dependency injection |
| [/docs/patterns/three_tier_type_system.md](../patterns/three_tier_type_system.md) | Type system details |
| [/docs/patterns/ERROR_HANDLING.md](../patterns/ERROR_HANDLING.md) | Result[T] pattern |
| [/docs/dsl/DSL_SPECIFICATION.md](../dsl/DSL_SPECIFICATION.md) | Activity DSL specification |
| [/docs/domains/](../domains/) | Individual domain documentation |
