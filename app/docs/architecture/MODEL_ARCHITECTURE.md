# Model Architecture
*Last updated: 2026-02-23*

> **Core Principle:** "Pydantic at the edges, pure Python at the core"

`core/models/` contains ~194 files across 30 packages implementing SKUEL's three-tier type system. Every domain entity flows through the same pattern: Pydantic validates at API boundaries, DTOs transfer data between layers, and frozen dataclasses enforce immutability at the core.

---

## Three-Tier Type System

| Tier | Type | Mutability | Purpose | Example |
|------|------|------------|---------|---------|
| **External** | Pydantic BaseModel | N/A | API boundary validation | `TaskCreateRequest` |
| **Transfer** | Mutable dataclass | Mutable | Data movement, serialization | `TaskDTO` |
| **Core** | Frozen dataclass | Immutable | Business logic, domain rules | `Task` |

**Data flow:**

```
HTTP Request
    → Pydantic validates (Tier 1)
        → Service creates frozen dataclass (Tier 3)
            → Backend serializes via DTO (Tier 2)
                → Neo4j storage

Neo4j read
    → Backend deserializes to DTO (Tier 2)
        → Service converts to frozen dataclass (Tier 3)
            → Route serializes to response
```

**Concrete example (Task):**

```python
# Tier 1 — API boundary (core/models/task/task_request.py)
class TaskCreateRequest(BaseModel):
    title: str                    # Pydantic validates non-empty
    priority: Priority | None     # Enum auto-validated

# Tier 3 — Core domain (core/models/task/task.py)
@dataclass(frozen=True)
class Task(UserOwnedEntity):
    ku_type: EntityType = EntityType.TASK  # Forced in __post_init__

# Tier 2 — Transfer (core/models/task/task_dto.py)
class TaskDTO(UserOwnedDTO):
    # Mutable mirror of Task fields for serialization
```

---

## Class Hierarchy

### Domain Models (Frozen Dataclasses)

```
Entity (~19 fields: uid, title, ku_type, status, visibility, tags, domain,
│       description, content, source, source_file, parent_ku_uid,
│       embedding, created_at, updated_at, ...)
│
├── UserOwnedEntity (+user_uid, +priority, overrides visibility → PRIVATE)
│   │
│   ├── Task ─────────── forces ku_type=TASK
│   ├── Goal ─────────── + goal_type, timeframe, measurement_type, target_date, milestones
│   ├── Habit ────────── + polarity, habit_category, habit_difficulty, frequency, streak
│   ├── Event ────────── + event_type, location, start_time, end_time, duration
│   ├── Choice ───────── + choice_type, options, decision_context, outcome
│   ├── Principle ────── + principle_category, principle_source, strength, current_alignment
│   │
│   ├── Submission ───── + processor_type, file_path, file_type, processed_content
│   │   ├── Journal        (forces ku_type=JOURNAL)
│   │   ├── AiReport       (forces ku_type=AI_REPORT)
│   │   └── Feedback       (forces ku_type=FEEDBACK_REPORT, +subject_uid)
│   │
│   └── LifePath ─────── + alignment_level, vision_statement, alignment_score
│
├── Curriculum (+complexity, learning_level, sel_category, quality_score, +21 fields)
│   ├── LearningStep ─── + step_difficulty, order, lp_uid
│   ├── LearningPath ─── + path_type, step_count, total_duration
│   └── Exercise ─────── + scope (PERSONAL or ASSIGNED)
│
└── Resource ──────────── + source_url, author, resource_type, year, medium
```

Every model forces its `ku_type` in `__post_init__()`. This drives:
- **Status validation:** `EntityType.TASK.valid_statuses()` → which statuses a Task can have
- **Default status:** `EntityType.HABIT.default_status()` → `ACTIVE` (not DRAFT)
- **Neo4j labels:** `NeoLabel.from_entity_type(EntityType.TASK)` → `:Entity:Task`

### DTO Hierarchy

DTOs mirror the domain model hierarchy with mutable fields:

```
EntityDTO (~18 fields)
├── UserOwnedDTO (+user_uid, visibility, priority)
│   ├── TaskDTO, GoalDTO, HabitDTO, EventDTO, ChoiceDTO, PrincipleDTO
│   ├── SubmissionDTO → JournalDTO, AiReportDTO, FeedbackDTO
│   └── LifePathDTO
├── CurriculumDTO (+complexity, learning_level, ...)
│   ├── LearningStepDTO, LearningPathDTO, ExerciseDTO
└── ResourceDTO (+source_url, author, ...)
```

Conversion: `to_dict()` calls `.value` on enums. `from_dict()` uses `dto_from_dict()` with enum class mappings.

---

## Directory Layout

### Per-Domain Pattern

Each domain follows a consistent file structure:

```
core/models/{domain}/
├── {domain}.py              # Frozen dataclass (Tier 3)
├── {domain}_dto.py          # Mutable DTO (Tier 2)
├── {domain}_request.py      # Pydantic request (Tier 1)
├── {domain}_intelligence.py # Intelligence/analytics models (optional)
└── __init__.py              # Re-exports
```

### Domain Directories

| Directory | Models | Category | Notes |
|-----------|--------|----------|-------|
| `task/` | Task + TaskDTO + requests | Activity | + TaskIntelligence |
| `goal/` | Goal + GoalDTO + requests | Activity | + Milestone sub-model |
| `habit/` | Habit + HabitDTO + requests | Activity | + HabitCompletion sub-entity, HabitIntelligence |
| `event/` | Event + EventDTO + requests | Activity | + calendar_models.py |
| `choice/` | Choice + ChoiceDTO | Activity | + ChoiceOption sub-model |
| `principle/` | Principle + PrincipleDTO + requests | Activity | + Reflection sub-entity, PrincipleIntelligence |
| `curriculum/` | Curriculum, LS, LP, Exercise + DTOs | Curriculum | + KU content/metadata/chunks, 14 files |
| `resource/` | Resource + ResourceDTO | Shared | Curated content (books, talks) |
| `reports/` | Submission, Journal, AiReport, Feedback + DTOs | Reports | + submission_requests.py, ku_schedule.py |
| `life_path/` | LifePath + LifePathDTO | Destination | |
| `group/` | Group + request | Organizational | Teacher-student classes (ADR-040) |
| `finance/` | Finance + FinanceDTO + requests | Finance | + Invoice, FinanceIntelligence |
| `user/` | User + UserDTO + requests | Cross-cutting | + UserLearningIntelligence, ConversationSession |
| `askesis/` | Askesis + AskesisDTO + requests | Cross-cutting | AI tutor state |
| `notification/` | Notification | Infrastructure | In-app notifications |

### Root-Level Files

| File | Purpose |
|------|---------|
| `entity.py` | Base frozen dataclass — all 16 EntityType models extend this |
| `user_owned_entity.py` | Intermediate class adding user_uid, priority |
| `entity_dto.py` | Base DTO mirroring Entity fields |
| `user_owned_dto.py` | Intermediate DTO adding visibility, priority |
| `entity_types.py` | `Ku` union type + `ENTITY_TYPE_CLASS_MAP` dispatcher |
| `entity_requests.py` | Base Pydantic requests (EntityCreateRequest, EntityUpdateRequest) |
| `entity_converters.py` | Entity → response dict conversion |
| `activity_requests.py` | Choice/Principle create requests |
| `validation_rules.py` | Shared Pydantic validators (date, string, range, domain-specific) |
| `search_request.py` | Canonical search request (~50 fields, all search strategies) |
| `relationship_registry.py` | Single source of truth for all relationship definitions |
| `relationship_names.py` | `RelationshipName` enum for Neo4j relationship types |
| `dto_helpers.py` | DTO conversion utilities (dto_from_dict, dict_from_dto, model_from_dto) |
| `request_base.py` | Base Pydantic request class with common mixins |
| `activity_dto_mixin.py` | Shared DTO conversion logic for activity domains |

### Infrastructure Packages

| Package | Files | Purpose |
|---------|-------|---------|
| `enums/` | 17 | All enum definitions ([ENUM_ARCHITECTURE.md](ENUM_ARCHITECTURE.md)) |
| `query/` | 19 | Query builders, Cypher generators, search models |
| `search/` | 5 | Search filters, scoring, query parsing, search router |
| `protocols/` | 4 | DomainModelProtocol, conversion protocols |
| `shared/` | 1 | DualTrackResult[L] generic assessment model |
| `auth/` | 3 | Session, auth events, password reset tokens |
| `progress/` | 1 | UserProgress tracking |
| `vectors/` | 1 | EmbeddingVector container |
| `semantic/` | 2 | Edge metadata, search metrics |
| `insight/` | 1 | PersistedInsight (Neo4j-stored insights) |
| `transcription/` | 1 | Transcription model |
| `mixins/` | 1 | Status checking utilities |
| `analytics/` | 2 | Analytics request models |

---

## Entity Type Dispatcher

`entity_types.py` provides the dispatcher that maps `EntityType` enum → concrete class:

```python
ENTITY_TYPE_CLASS_MAP: dict[EntityType, type[Entity]] = {
    EntityType.TASK: Task,
    EntityType.GOAL: Goal,
    EntityType.HABIT: Habit,
    # ... all 16 mappings
}

# Union type for type annotations
Ku = Task | Goal | Habit | Event | Choice | Principle | Curriculum | ...

# Narrower aliases for services that handle subsets
ActivityEntity = Task | Goal | Habit | Event | Choice | Principle
CurriculumEntity = Curriculum | LearningStep | LearningPath | Exercise
SubmissionEntity = Submission | Journal | AiReport | Feedback
```

Cross-domain deserialization uses the dispatcher:
```python
entity_class = ENTITY_TYPE_CLASS_MAP[dto.ku_type]
entity = entity_class.from_dto(dto)
```

---

## Sub-Entity Models

Some domains have nested models that aren't top-level entities:

| Sub-Entity | Parent Domain | File | Neo4j Label | Purpose |
|------------|--------------|------|-------------|---------|
| HabitCompletion | Habit | `habit/completion.py` | `:HabitCompletion` | Daily completion tracking |
| Milestone | Goal | `goal/milestone.py` | *(embedded)* | Goal sub-tasks with progress |
| ChoiceOption | Choice | `choice/choice_option.py` | *(embedded)* | Options in a decision |
| Reflection | Principle | `principle/reflection.py` | `:PrincipleReflection` | Principle reflection entries |

Sub-entities with Neo4j labels (HabitCompletion, Reflection) have their own DTOs and are stored as separate nodes connected via relationships.

---

## Intelligence Models

Per-domain `*_intelligence.py` files contain persistent learning state and analytics types used by intelligence services:

| Domain | Intelligence Models | Purpose |
|--------|-------------------|---------|
| Task | TaskIntelligence, TaskCompletionContext | Energy levels, procrastination triggers |
| Habit | HabitIntelligence, HabitCompletionContext | Failure reasons, completion context |
| Principle | PrincipleIntelligence | Alignment tracking, reflection analysis |
| Curriculum | KuMastery, KuRecommendation, LearningPreference | Mastery tracking, content recommendation |
| Finance | FinanceIntelligence | Budget tracking, spending analysis |
| User | UserLearningIntelligence | Cross-domain learning state |

These models are consumed by `BaseAnalyticsService` subclasses — they never touch Neo4j directly.

---

## See Also

- [Enum Architecture](ENUM_ARCHITECTURE.md) — Enum landscape, enum-to-model wiring, dynamic patterns
- [Three-Tier Type System](/docs/patterns/three_tier_type_system.md) — Pattern details and rationale
- [Domain Patterns Catalog](/docs/patterns/DOMAIN_PATTERNS_CATALOG.md) — Per-domain examples
- [14-Domain Architecture](FOURTEEN_DOMAIN_ARCHITECTURE.md) — Domain categories and relationships
- Source: `core/models/` (194 files, 30 packages)
