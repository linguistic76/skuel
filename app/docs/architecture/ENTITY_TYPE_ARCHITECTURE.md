---
title: SKUEL Architecture — 25 Entity Types + 5 Cross-Cutting Systems
updated: 2026-05-09
status: current
category: architecture
version: 8.1.0
related_skills: [activity-domains]
tags:
- architecture
- entity-types
related:
- ADR-040-teacher-exercise-workflow
- ADR-041-unified-ku-model
- ADR-047-entity-types-replace-domain-categories
- ADR-051-user-interaction-contract
- ADR-054-user-entry-unified-submissions
- ADR-055-architectural-lenses
---

# SKUEL Architecture

## Executive Summary

SKUEL is a **knowledge-centric productivity platform** where every operation connects to and enriches understanding. **Knowledge is the fertile soil from which all activity grows.**

This doc is **Model A at the fine grain** per ADR-055 — the 25 EntityTypes. For the coarse rollup into 7 subsystems (Object / Context / Meta), see [`SEVEN_SUBSYSTEMS.md`](SEVEN_SUBSYSTEMS.md). For the flow-of-information view (Curriculum → Action → Feedback), see [`THREE_LAYER_LENS.md`](THREE_LAYER_LENS.md). The 5 Cross-Cutting Systems below are infrastructure layers orthogonal to both lenses.

### 25 Entity Types + 5 Cross-Cutting Systems

| EntityType | What It Is | UID Format | Ownership |
|------------|-----------|-----------|-----------|
| Task | Work to be done | `task_{slug}_{random}` | User-owned |
| Goal | Outcome to achieve | `goal_{slug}_{random}` | User-owned |
| Habit | Behavior to build | `habit_{slug}_{random}` | User-owned |
| Event | Time commitment to keep | `event_{slug}_{random}` | User-owned |
| Choice | Decision to make | `choice_{slug}_{random}` | User-owned |
| Principle | Value to embody | `principle_{slug}_{random}` | User-owned |
| TaskTemplate | PS-owned template that spawns Task instances on engagement | `tt_{slug}_{random}` | Admin/teacher-created, shared |
| GoalTemplate | PS-owned template that spawns Goal instances on engagement | `gt_{slug}_{random}` | Admin/teacher-created, shared |
| HabitTemplate | PS-owned template that spawns Habit instances on engagement | `ht_{slug}_{random}` | Admin/teacher-created, shared |
| EventTemplate | PS-owned template that spawns Event instances on engagement | `et_{slug}_{random}` | Admin/teacher-created, shared |
| ChoiceTemplate | PS-owned template that spawns Choice instances on engagement | `ct_{slug}_{random}` | Admin/teacher-created, shared |
| PrincipleTemplate | PS-owned template that spawns Principle instances on engagement | `pt_{slug}_{random}` | Admin/teacher-created, shared |
| FormTemplate | General-purpose form definition | `ft_{slug}_{random}` | Admin-created, shared |
| FormSubmission | User response to a FormTemplate | `fs_{slug}_{random}` | User-owned |
| Ku | Atomic knowledge unit (concept, principle, substance) | `ku_{slug}_{random}` | Admin-created, shared |
| Resource | Curated content (books, talks, films) | N/A | Admin-created, shared |
| PathStep | THE curriculum content entity (composes Kus into learning content) | `ps:{namespace}:{slug}` | Admin-created, shared |
| LearningPath | An ordered sequence of PathSteps | `lp:{namespace}:{slug}` | Admin-created, shared |
| Exercise | Instruction template, assignment, or formal assessment | N/A | Admin-created, shared |
| RevisedExercise | Targeted revision after feedback | `re_{slug}_{random}` | Teacher-owned |
| UserEntry | Unified user-authored content — submissions, journals, uploads (ADR-054) | `ue_{slug}_{random}` | User-owned |
| Interaction | Situated learning-loop event (curriculum context at submission time) | `ia_{slug}_{random}` | User-owned |
| ActivityReport | Feedback about activity patterns over time | `ar_{random}` | User-owned |
| EntryReport | Report (teacher/AI assessment or LLM reflective response) tied to a specific UserEntry | `er_{random}` | User-owned |
| LifePath | The user's life direction | `lp_{random}` | User-owned |

**Not EntityTypes** (listed separately): Groups (`NonKuDomain.GROUP`, ADR-053 — teacher-student class management, `:Group` nodes). Finance (`NonKuDomain.FINANCE`, ADR-052 — Firefly III sidecar). MOC is emergent (any Entity with ORGANIZES edges, no dedicated EntityType).

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
|   +-- UserEntry(UserOwnedEntity) +file/processing/pipeline fields   USER_ENTRY (ADR-054)
|   +-- EntryReport(UserOwnedEntity) +6 report fields              ENTRY_REPORT
|   +-- RevisedExercise(UserOwnedEntity)                              REVISED_EXERCISE
+-- FormTemplate(Entity) — reusable form definition (shared, embeddable)
+-- {Activity}Template(Entity) — PS-owned spawn blueprints (Entity-direct, not UserOwned)
|   +-- TaskTemplate, GoalTemplate, HabitTemplate, EventTemplate, ChoiceTemplate, PrincipleTemplate
+-- Curriculum(Entity) +21 fields (base class only)
|   +-- PathStep(Curriculum), LearningPath, Exercise
+-- Ku(Entity) — atomic knowledge unit
+-- Resource(Entity) +7 fields
```

### DTO Hierarchy

```
EntityDTO (~18 fields)
+-- UserOwnedDTO(EntityDTO) +3 -> TaskDTO, GoalDTO, HabitDTO, EventDTO, ChoiceDTO, PrincipleDTO
+-- UserOwnedDTO -> ActivityReportDTO              (no file fields)
+-- UserOwnedDTO -> FormSubmissionDTO              (structured JSON, no file fields)
+-- UserOwnedDTO -> UserEntryDTO                   (file + processing + pipeline)
+-- UserOwnedDTO -> EntryReportDTO
+-- EntityDTO -> FormTemplateDTO                   (form_schema, instructions)
+-- EntityDTO -> TaskTemplateDTO, GoalTemplateDTO, HabitTemplateDTO, EventTemplateDTO, ChoiceTemplateDTO, PrincipleTemplateDTO   (PS-owned spawn blueprints, RelativeOffset timing)
+-- CurriculumDTO(EntityDTO) -> PathStepDTO, LearningPathDTO, ExerciseDTO
+-- KuDTO(EntityDTO)
+-- ResourceDTO(EntityDTO)
```

Cross-domain services use `ENTITY_TYPE_CLASS_MAP` for generic entity deserialization.

**Cross-domain UID fields** on model classes are either persisted structural anchors (written at creation, e.g., `source_path_step_uid`, `fulfills_goal_uid`) or enrichment links derived from graph edges at read time (e.g., `reinforces_habit_uid`, `supports_goal_uid`). **See:** `/docs/architecture/CROSS_DOMAIN_UID_PATTERNS.md`

### Neo4j Multi-Label

Every entity node gets two labels: `:Entity` (universal) + type-specific (`:Task`, `:Goal`, etc.).

**`NeoLabel` enum** (`/core/models/enums/neo_labels.py`):

| Labels |
|--------|
| `:Entity` (universal — all entity nodes) |
| `:Task`, `:Goal`, `:Habit`, `:Event`, `:Choice`, `:Principle` |
| `:TaskTemplate`, `:GoalTemplate`, `:HabitTemplate`, `:EventTemplate`, `:ChoiceTemplate`, `:PrincipleTemplate` |
| `:Curriculum`, `:Resource`, `:PathStep`, `:LearningPath` |
| `:FormTemplate`, `:FormSubmission` |
| `:UserEntry` |
| `:EntryReport` |
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
- `/core/models/enums/entity_enums.py` — `EntityType` (25 values), `EntityStatus` (14 values)

---

## Naming Convention

Naming discipline is load-bearing in a graph — it determines the readability of every Cypher query and the mental model of the ontology. Three constructs carry the weight, each with its own linguistic form.

| Construct | Linguistic form | Examples |
|-----------|-----------------|----------|
| **EntityType** | Noun, or adjective / past-participle + noun — a compound noun denoting a *kind of thing* | `Exercise`, `UserEntry`, `EntryReport`, `RevisedExercise`, `LearningPath`, `PathStep` |
| **Relationship (edge)** | Active verb phrase | `FULFILLS_EXERCISE`, `REVISES_EXERCISE`, `RESPONDS_TO_REPORT`, `ORGANIZES`, `USES_KU` |
| **Variant within an entity** | Enum field on that entity | `Pipeline` (on `UserEntry`), `ReportSource` + `AssessmentOutcome` (on `EntryReport`), `ExerciseScope` (on `Exercise`), `FeedbackCategory` (on `RevisedExercise.feedback_points`) |

### Two-part test for "does this justify a new EntityType?"

1. **Does the proposed name read as a noun / kind-of-thing?** If not, it belongs on an edge (verb) or an enum (variant) — not as a type.
2. **Does the semantic difference change the class hierarchy?** A new base class (`Curriculum` vs. `UserOwnedEntity`), a different ownership model (shared vs. teacher-owned vs. user-owned), or a different `ContentOrigin` tier. If the hierarchy is unchanged, prefer an enum field on the existing type.

Both conditions must hold to justify a new EntityType. Passing only test 1 means the name is fine but the concept collapses into an existing type with a new enum variant. Passing only test 2 cannot happen — a genuinely different hierarchy always has a distinct kind-of-thing name.

### Worked examples

**`UserEntry` — correctly a unified type (ADR-054).** The former `ExerciseSubmission` / `JeInput` / `JeOutput` types all passed test 1 (each was a noun compound) but *failed* test 2: same hierarchy (`UserOwnedEntity`), same ownership, same file/processing field set. The three collapsed into one `UserEntry` discriminated by `pipeline: Pipeline`. The variants (exercise submission, journal raw input, journal processed output) now live on an enum field, not on separate types.

**`EntryReport` — correctly one type with two enums.** There is no `RevisedEntryReport` class. Whether a report came from a teacher, an LLM, a hybrid workflow, or an automatic process is recorded on `report_source: ReportSource`; whether the outcome is approval, a revision request, or AI-evaluated is recorded on `assessment_outcome: AssessmentOutcome`. Each variant has a different *history* but the same *shape* — an enum, not a type.

**`RevisedExercise` — correctly a distinct type.** Passes both tests. *Test 1:* the name is a past-participle + noun — "a revised exercise" denoting a kind of thing, parallel to `FrozenDataclass`, `CompiledQuery`, `DerivedAttribute`. It is not the verb phrase "revising an exercise" (which would be process-language). *Test 2:* different base class (`UserOwnedEntity` vs. `Exercise`'s `Curriculum`), different ownership (teacher-owned vs. shared), different `ContentOrigin` tier (`USER_CREATED` vs. `CURRICULUM`), different targeting (individual `student_uid` vs. group or curriculum), and typed `FeedbackPoint[]` feedback instead of plain `instructions` text. The verb lives on the edge `(RevisedExercise)-[:REVISES_EXERCISE]->(Exercise)`, not in the type name.

**`FormSubmission` — a structural split despite similarity.** Superficially like a `UserEntry`, but `FormSubmission` carries structured JSON (`form_data`) instead of files and responds to a `FormTemplate` rather than an `Exercise`. Both passed test 1 (distinct noun compound) AND test 2 (different field set — no file/processing fields, different `RESPONDS_TO_FORM` edge topology). Separate types were correct.

### Applying the rule

Before proposing to rename, collapse, or split an EntityType, run both tests. Name drift suspicions (e.g., "this name looks like process-language") are answered by test 1 — if the name reads as a kind-of-thing, it is object-language, regardless of whether it contains a past participle. `RevisedExercise` is object-language and will not be renamed; this conversation has been had and settled.

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
| **Activity Template** | `is_activity_template()` | Is it one of the 6 PS-owned template types? |
| **Template → Instance** | `instance_type()` | Returns the spawned instance type (e.g. TASK_TEMPLATE → TASK); raises ValueError if not a template |
| **Instance → Template** | `template_type()` | Returns the template type (e.g. TASK → TASK_TEMPLATE); raises ValueError if not an activity |

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

### Ku, PathStep, LearningPath, Exercise — Curriculum

**The knowledge / applied-knowledge hierarchy:**

> PathStep IS knowledge. Exercise is APPLIED knowledge. This hierarchy is fundamental.

These four EntityTypes form a hierarchy, not a flat peer group:

| EntityType | Role | Hierarchy position |
|---|---|---|
| Ku | Atomic knowledge unit | Foundation — irreducible concept |
| PathStep | Composed knowledge | Built on Kus — the teachable unit |
| LearningPath | Organisational structure | Sequences PathSteps into a path |
| Exercise | Applied knowledge | Anchored below PathStep — instruction template |

PathStep and Exercise are **NOT peers**. Exercise is subordinate to PathStep via
`(PathStep)-[:HAS_EXERCISE]->(Exercise)` — the same structural relationship as sub-goal
under parent goal (`Goal.fulfills_goal_uid`). `Exercise.path_step_uid` is a
**hierarchy-membership property** (identifies which knowledge unit this instruction
template belongs to), not a scoring or enrichment field. Both the graph edge and the
property are written at creation time so both lookup directions are always available.

Exercise and RevisedExercise share `is_applied_knowledge() == True` in the EntityType
classification (`entity_enums.py`). LearningPath alone is `is_curriculum_structure()`.

All four are admin-created and publicly readable via `ContentScope.SHARED`. Ku extends
`Entity` directly (lightweight atomic unit); PathStep, LearningPath, and Exercise extend
`Curriculum(Entity)` to inherit substance tracking, learning metadata, and confidence fields.

### Resource — Curated External Content

Pointers to external content (books, talks, films) that Askesis can recommend. Resource extends `Entity` directly (+7 fields). Admin-created, publicly readable via `ContentScope.SHARED`. Resource is NOT curriculum — it does not participate in the `Exercise → UserEntry → EntryReport → RevisedExercise` loop (PathStep anchors Exercises, but Resource sits outside that chain entirely). Its `ContentOrigin` is `CURATED` (tier A), distinct from curriculum's `CURRICULUM` (tier B).

**Two paths to knowledge (Montessori-inspired):**
- **PS Path**: Structured, linear, teacher-directed (Ku -> PathStep -> LearningPath)
- **MOC Path**: Unstructured, graph, learner-directed (any Entity ORGANIZES others)

**Service architecture:**
```
KuService (facade) — 4 sub-services via create_curriculum_sub_services()
├── core: KuCoreService
├── search: KuSearchService
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

### Exercise Scope — Four Modes of Ownership and Assessment

Exercise is a single entity type serving four distinct pedagogical roles via `ExerciseScope`:

| Scope | Purpose | Key Fields | Mastery Signal |
|-------|---------|------------|----------------|
| `PERSONAL` | User's own AI feedback template (default) | `instructions`, `model`; `path_step_uid` optional anchor | Soft — AI-evaluated |
| `ASSIGNED` | Teacher assigns to a group | `group_uid` (required), `due_date` | Medium — teacher-approved |
| `ASSESSMENT` | Formal test/exam with scoring rubric | `scoring_rubric` (required), `pass_threshold` | Hard — objective score |
| `CURRICULUM` | Content-vault-authored shared exercise — owned by the curriculum, no user OWNS edge | Anchored via `exercise_uids:` in PathStep YAML; not creatable via API | Soft — AI-evaluated |

**ASSESSMENT scope** adds two fields to Exercise:
- `scoring_rubric`: List of criteria, each with `name`, `weight` (must sum to 1.0), and optional `description`
- `pass_threshold`: Minimum score (0.0-1.0) to pass; defaults to 0.7

**EntryReport** carries `assessment_score` (0.0-1.0) for ASSESSMENT-scope exercises — the numeric result evaluated against the rubric. This is the **objective measurement layer** that substance tracking and EntryReports don't otherwise provide.

**Design rationale:** A Test is an Exercise with `scope=ASSESSMENT` and a scoring rubric — not a separate entity type. The learning loop (`Exercise → UserEntry → EntryReport → RevisedExercise`) applies identically to all scopes. What differs is the evaluation mechanism (AI feedback vs teacher review vs rubric scoring) and the strength of the mastery signal.

### FormTemplate + FormSubmission — General-Purpose Forms

A general-purpose form system decoupled from the learning loop. Admin creates reusable form templates, embeds them in PathSteps via `EMBEDS_FORM` relationships, and users submit structured responses. Submissions flow through the existing sharing infrastructure (groups, direct sharing, admin).

| EntityType | Inherits | Description |
|------------|---------|-------------|
| `FORM_TEMPLATE` | `Entity` directly | Reusable form definition with `form_schema` (field specs) |
| `FORM_SUBMISSION` | `UserOwnedEntity` | User response storing structured JSON `form_data` |

FormTemplate extends `Entity` (NOT Curriculum — doesn't need 21 Curriculum fields). `ContentOrigin.CURATED`, publicly readable via `ContentScope.SHARED`. FormSubmission extends `UserOwnedEntity` (NOT UserEntry — no file fields). `ContentOrigin.USER_CREATED`, `is_derived()=True`.

**Graph relationships:**
```cypher
(ps:PathStep)-[:EMBEDS_FORM]->(ft:FormTemplate)
(fs:FormSubmission)-[:RESPONDS_TO_FORM]->(ft:FormTemplate)
(user:User)-[:OWNS]->(fs:FormSubmission)
```

**Data integrity:** Schema pinning (`template_schema_hash` on FormSubmission), atomic writes (`FormSubmissionBackend.create_with_relationships()`), canonical `processed_content` via `build_form_processed_content()`.

**Services:** `core/services/forms/form_template_service.py`, `core/services/forms/form_submission_service.py`, `core/services/forms/form_content.py`
**Protocols (two tiers):** `core/ports/form_protocols.py`
- Backend-level: `FormTemplateBackendOperations(BackendOperations["FormTemplate"])`, `FormSubmissionBackendOperations(BackendOperations["FormSubmission"])` — typed `self.backend` in services (import directly from `core.ports.form_protocols`)
- Route-level: `FormTemplateOperations`, `FormSubmissionOperations` — typed service in routes (re-exported from `core.ports`)

### UserEntry, Reports, ActivityReport — Content Processing

The educational loop: `PathStep -> Exercise -> UserEntry -> EntryReport -> RevisedExercise -> UserEntry -> ...`. Activity entity types are equal entry points via `ACTIVITY_REPORT`.

`UserEntry` (ADR-054) collapses the former `ExerciseSubmission`, `JeInput`, and `JeOutput` entity types into a single user-authored content type. Behavior is discriminated by two dimensions: a `Pipeline` field on the node (how the entry is processed) and a `ReportSource` field on derived reports (who or what produced the report).

| EntityType | Inherits | Pipeline / ReportSource | Description |
|------------|---------|------------------------|-------------|
| `USER_ENTRY` | `UserOwnedEntity` | `Pipeline` (`NONE`, `TEACHER_REVIEW`, `TRANSCRIBE`, `LLM_SUMMARY`, `TRANSCRIBE_AND_STRUCTURE`, `EXTRACT_ACTIVITIES`) | Unified user-authored content — exercise submissions, journal audio, uploads |
| `ENTRY_REPORT` | `UserOwnedEntity` | `ReportSource` (`HUMAN`, `LLM`) | Assessment tied to a `UserEntry` via `subject_uid` |
| `ACTIVITY_REPORT` | `UserOwnedEntity` **directly** | `ReportSource` (`AUTOMATIC`, `LLM`, `HUMAN`) | Activity-level feedback (no file fields; covers a time window) |

**Revision lives on the edge, not the node.** The `revision_number` field that used to sit on `ExerciseSubmission` now lives on `(UserEntry)-[:FULFILLS_EXERCISE {revision}]->(Exercise)`. Re-submitting the same exercise creates a new `UserEntry` node carrying its own `FULFILLS_EXERCISE {revision: N+1}` edge.

**Key structural note:** `EntryReport` has 6 report-specific fields (`report_generated_at`, `subject_uid`, `report_source`, `assessment_outcome`, `report_file_path`, `assessment_score`) but no file/processing fields. The report body lives on the inherited `Entity.content` field. `assessment_outcome` (`AssessmentOutcome` enum: APPROVED, NEEDS_REVISION, AI_EVALUATED) makes each report self-describing — the report records what decision was made, not just feedback text. `assessment_score` (0.0-1.0) carries the numeric result for ASSESSMENT-scope exercises. `report_source` (`ReportSource` enum) replaces the former `processor_type`.

`ACTIVITY_REPORT` also inherits `UserOwnedEntity` directly — no file fields. It responds to aggregate activity patterns over a time period, not to a specific artifact.

**Ingestion aliases:** `exercise_submission`, `submission`, `journal`, `je_input`, `je_output` still parse via `_ENTITY_TYPE_ALIASES` — all of them map to `EntityType.USER_ENTRY`, with `pipeline` inferred from the alias. Legacy YAMLs in `/home/mike/0bsidian/0vault/` continue ingesting without rewrites.

**Services:**
- `core/services/user_entry/` — `UserEntryService` (facade), `UserEntryProcessingService` (pipeline dispatch: Deepgram transcribe, LLM summarize, transcribe-and-structure, DSL activity extraction per ADR-069), `AssessmentService`, `ReviewQueueService`, relationship + exercise linking helpers.
- `core/services/report/` — `EntryReportService`, `ProgressReportGenerator`, `ProgressScheduleService`.

**See:** `/docs/architecture/REPORT_ARCHITECTURE.md`, [ADR-054](../decisions/ADR-054-user-entry-unified-submissions.md)

### Pipeline and ReportSource (supersede ProcessorType)

ProcessorType was a single enum doing two jobs: classifying how a submission was processed AND labeling who generated a report. ADR-054 splits those into two purpose-built enums.

| Enum | Applies to | Values | Purpose |
|------|-----------|--------|---------|
| `Pipeline` | `UserEntry` nodes | `NONE`, `TEACHER_REVIEW`, `TRANSCRIBE`, `LLM_SUMMARY`, `TRANSCRIBE_AND_STRUCTURE`, `EXTRACT_ACTIVITIES` | How a user entry is processed after creation. Drives `UserEntryProcessingService` dispatch. |
| `ReportSource` | `EntryReport`, `ActivityReport` | `HUMAN`, `LLM`, `HYBRID`, `AUTOMATIC` | Who or what produced the report. Stored as `report_source` on the report node. |

Both `Pipeline` and `ReportSource` live in `core/models/enums/pipeline.py`. `SubmissionModality` and `EnrichmentMode` live in `core/models/enums/user_entry_enums.py` (formerly `submissions_enums.py`) — both still load-bearing.

ProcessorType has been removed from the codebase. Legacy aliases ensure old serialized data continues to read: the ingestion alias map redirects legacy string values onto the new enums.

### RevisedExercise — Four-Phase Learning Loop

Teacher-created revision of an Exercise that addresses specific `EntryReport` gaps. Extends `UserOwnedEntity` (NOT Curriculum — needs `user_uid` but not 21 Curriculum fields). `ContentOrigin.USER_CREATED` — teacher-authored content targeted at a specific student.

| EntityType | Inherits | Description |
|------------|---------|-------------|
| `REVISED_EXERCISE` | `UserOwnedEntity` | Teacher's revised instructions targeting a specific student |

**Graph relationships:**
- `RESPONDS_TO_REPORT` → EntryReport (what report this addresses)
- `REVISES_EXERCISE` → Exercise (what exercise this revises)
- `FULFILLS_EXERCISE` ← UserEntry (student submits against this; `revision` stored on edge)

**Service:** `core/services/revised_exercises/revised_exercise_service.py`
**See:** `/docs/architecture/LEARNING_LOOP_ARCHITECTURE.md`

### Groups — Teacher-Student Organization

Groups mediate ALL teacher-student relationships. Teacher creates group -> adds students -> assigns exercises to the group.

**Key relationships:**
```cypher
(teacher:User)-[:OWNS]->(group:Group)
(student:User)-[:MEMBER_OF {joined_at, role}]->(group:Group)
(exercise:Exercise)-[:FOR_GROUP]->(group:Group)
(entry:UserEntry)-[:FULFILLS_EXERCISE {revision}]->(exercise:Exercise)
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

**Processing pipeline (staged — PLANNED tier; wiring retired with the journal pipeline, ADR-054):**
```
Natural Text
    -> LLMDSLBridgeService.transform()        # GPT-4o-mini adds @context tags
    -> ActivityDSLParser.parse_journal()       # ParsedJournal (domain buckets)
    -> activity_to_* converter functions       # Domain-typed create requests (link UIDs ride along)
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
(ps:PathStep)-[:USES_KU]->(ku:Ku)
(ku:Curriculum)-[:REQUIRES_KNOWLEDGE]->(ku:Curriculum)
(ku:Curriculum)-[:ENABLES_KNOWLEDGE]->(ku:Curriculum)
(lp:LearningPath)-[:HAS_NARROWER]->(ps:PathStep)
(ps:PathStep)-[:REQUIRES_PREREQUISITE]->(ku:Curriculum)

// MOC organization
(entity:Entity)-[:ORGANIZES {order: int}]->(entity:Entity)

// Groups + exercises (ADR-040 + ADR-054)
(teacher:User)-[:OWNS]->(group:Group)
(student:User)-[:MEMBER_OF {joined_at, role}]->(group:Group)
(exercise:Exercise)-[:FOR_GROUP]->(group:Group)
(entry:UserEntry)-[:FULFILLS_EXERCISE {revision}]->(exercise:Exercise)
(structured:UserEntry)-[:TRANSFORMS]->(source:UserEntry)  // journal pipeline

// Forms
(ps:PathStep)-[:EMBEDS_FORM]->(ft:FormTemplate)
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
| [REPORT_ARCHITECTURE.md](REPORT_ARCHITECTURE.md) | ActivityReport, EntryReport, all report types |
| [RELATIONSHIPS_ARCHITECTURE.md](RELATIONSHIPS_ARCHITECTURE.md) | UnifiedRelationshipService, relationship taxonomy |
| [CURRICULUM_GROUPING_PATTERNS.md](CURRICULUM_GROUPING_PATTERNS.md) | KU/PS/LP/MOC patterns |
| [ANALYTICS_ARCHITECTURE.md](ANALYTICS_ARCHITECTURE.md) | Analytics meta-service |
| [SEARCH_ARCHITECTURE.md](SEARCH_ARCHITECTURE.md) | Unified search across all entity types |
| [/docs/patterns/protocol_architecture.md](../patterns/protocol_architecture.md) | Protocol-based dependency injection |
| [/docs/patterns/three_tier_type_system.md](../patterns/three_tier_type_system.md) | Type system details |
| [/docs/patterns/ERROR_HANDLING.md](../patterns/ERROR_HANDLING.md) | Result[T] pattern |
| [/docs/dsl/DSL_SPECIFICATION.md](../dsl/DSL_SPECIFICATION.md) | Activity DSL specification |
| [/docs/domains/](../domains/) | Individual domain documentation |
