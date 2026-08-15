# Model Architecture
*Last updated: 2026-03-03*

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
    entity_type: EntityType = EntityType.TASK  # Honest leaf default; __post_init__ rejects a mismatch (G6)

# Tier 2 — Transfer (core/models/task/task_dto.py)
class TaskDTO(UserOwnedDTO):
    # Mutable mirror of Task fields for serialization
```

---

## Class Hierarchy

### Domain Models (Frozen Dataclasses)

```
Entity (~19 fields: uid, title, entity_type, status, visibility, tags, domain,
│       description, content, source, source_file, parent_entity_uid,
│       embedding, created_at, updated_at, ...)
│
├── UserOwnedEntity (+user_uid, +priority, overrides visibility → PRIVATE)
│   │
│   ├── Task ─────────── entity_type=TASK (leaf default, mismatch rejected)
│   ├── Goal ─────────── + goal_type, timeframe, measurement_type, target_date, milestones
│   ├── Habit ────────── + polarity, habit_category, habit_difficulty, frequency, streak
│   ├── Event ────────── + event_type, location, start_time, end_time, duration
│   ├── Choice ───────── + choice_type, options, decision_context, outcome
│   ├── Principle ────── + principle_category, principle_source, strength, current_alignment
│   │
│   ├── UserEntry ────── + pipeline, modality, file_path, file_size, file_type, processed_content (entity_type=USER_ENTRY — leaf default, mismatch rejected)
│   ├── EntryReport ── + processed_content, subject_uid, assessment_outcome, report_file_path, report_generated_at (entity_type=ENTRY_REPORT — leaf default, mismatch rejected)
│   ├── ActivityReport ─── (entity_type=ACTIVITY_REPORT — leaf default, mismatch rejected; NO file fields)
│   │
│   └── LifePath ─────── + alignment_level, vision_statement, alignment_score
│
├── Curriculum (+complexity, learning_level, sel_category, quality_score, +21 fields)
│   ├── Ku ───────────── entity_type=KU (leaf default, mismatch rejected; atomic knowledge unit)
│   ├── PathStep ─── + step_difficulty, order, lp_uid
│   ├── LearningPath ─── + path_type, step_count, total_duration
│   └── Exercise ─────── + scope, expected_modality (FILE_UPLOAD or STRUCTURED_FORM)
│
└── Resource ──────────── + source_url, author, resource_type, year, medium
```

Every leaf model declares its `entity_type` as an honest field default and `__post_init__()` **raises `ValueError` on a mismatch** — a wrong persisted type fails loudly instead of being silently corrected (G6, Arc C 2026-07-03). The write-path guard is on Tier 2: `EntityDTO.entity_type` is REQUIRED (kw_only, no default); only leaf DTOs default. The entity_type drives:
- **Status validation:** `EntityType.TASK.valid_statuses()` → which statuses a Task can have
- **Default status:** `EntityType.HABIT.default_status()` → `ACTIVE` (not DRAFT)
- **Neo4j labels:** `NeoLabel.from_entity_type(EntityType.TASK)` → `:Entity:Task`

### DTO Hierarchy

DTOs mirror the domain model hierarchy with mutable fields:

```
EntityDTO (~18 fields)
├── UserOwnedDTO (+user_uid, visibility, priority)
│   ├── TaskDTO, GoalDTO, HabitDTO, EventDTO, ChoiceDTO, PrincipleDTO
│   ├── ActivityReportDTO                      (no file fields — activity patterns)
│   ├── UserEntryDTO
│   └── LifePathDTO
├── CurriculumDTO (+complexity, learning_level, ...)
│   ├── KuDTO, PathStepDTO, LearningPathDTO, ExerciseDTO
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
| `exercises/` | Exercise, RevisedExercise + DTOs + requests | Curriculum | Exercise and revision models |
| `pathways/` | PathStep, LearningPath + DTOs, Mastery, LpPosition, LearningProgress | Curriculum | LP/PS pathway models (PathStep IS the curriculum content entity) |
| `lesson_content/` | CurriculumContent, ContentChunk, ContentMetadata | Curriculum | PathStep body storage + RAG chunking |
| `ku/` | Ku + KuDTO | Curriculum | Atomic knowledge units |
| `resource/` | Resource + ResourceDTO | Shared | Curated content (books, talks) |
| `user_entry/` | UserEntry + DTOs | User Entry | + report_schedule.py |
| `report/` | ActivityReport + ActivityReportDTO, EntryReport + EntryReportDTO | Report | ActivityReport: no file fields; EntryReport: tied to submission via subject_uid |
| `life_path/` | LifePath + LifePathDTO | Destination | |
| `group/` | Group + request | Organizational | Teacher-student classes (ADR-040) |
| `finance/` | Finance + FinanceDTO + requests | Finance | + Invoice, FinanceIntelligence |
| `user/` | User + UserDTO + requests | Cross-cutting | + UserLearningIntelligence, ConversationSession |
| `askesis/` | Askesis + AskesisDTO + requests | Cross-cutting | AI tutor state |
| `notification/` | Notification | Infrastructure | In-app notifications |

### Root-Level Files

| File | Purpose |
|------|---------|
| `entity.py` | Base frozen dataclass — all 25 EntityType models extend this |
| `user_owned_entity.py` | Intermediate class adding user_uid, priority |
| `entity_dto.py` | Base DTO mirroring Entity fields |
| `user_owned_dto.py` | Intermediate DTO adding visibility, priority |
| `entity_types.py` | `ENTITY_TYPE_CLASS_MAP` dispatcher + `ActivityEntity`, `CurriculumEntity`, `SubmissionEntity` aliases |
| `entity_requests.py` | Base Pydantic requests (EntityCreateRequest, EntityUpdateRequest) |
| `entity_converters.py` | Entity → response dict conversion |
| `validation_rules.py` | Shared Pydantic validators (date, string, range, domain-specific) |
| `search_request.py` | Canonical search request (~50 fields, all search strategies) |
| `relationship_registry.py` | Single source of truth for all relationship definitions |
| `relationship_names.py` | `RelationshipName` enum for Neo4j relationship types |
| `dto_helpers.py` | DTO conversion utilities (domain_to_dto, dto_from_dict, dict_from_dto) |
| `request_base.py` | Base Pydantic request class with common mixins |
| `type_hints.py` | `Neo4jProperties`, `FilterParams`, `RelationshipMetadata` type aliases |

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
| `analytics/` | 4 | Analytics request models |

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

# Type aliases for services that handle subsets
ActivityEntity = Task | Goal | Habit | Event | Choice | Principle
CurriculumEntity = Ku | PathStep | LearningPath | Exercise  # Ku is the atomic leaf
SubmissionEntity = UserEntry
```

**Note:** `Ku` is a leaf domain class (`Ku(Curriculum)`), not a union type alias. The old union `Ku = Task | Goal | ...` was dissolved when `core/models/ku/` was created as a dedicated directory for atomic knowledge units (February 2026).

Cross-domain deserialization uses the dispatcher:
```python
entity_class = ENTITY_TYPE_CLASS_MAP[dto.entity_type]
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

## Intelligence Architecture

Intelligence logic lives in `*IntelligenceService` classes (extending `BaseAnalyticsService`), not in model files. These services use graph queries and shared utilities directly. Domain-specific enums live in `core/models/enums/`.

The one exception is `core/models/finance/finance_intelligence.py` which defines `FinancialHealthScore` and related enums used by `cross_domain_analytics_service.py`.

**See:** [ADR-048 Adaptive Learning Loop](/docs/decisions/ADR-048-adaptive-learning-loop.md) for the architecture of learning from outcomes.

---

## See Also

- [Enum Architecture](ENUM_ARCHITECTURE.md) — Enum landscape, enum-to-model wiring, dynamic patterns
- [Three-Tier Type System](/docs/patterns/three_tier_type_system.md) — Pattern details and rationale
- [Domain Patterns Catalog](/docs/patterns/DOMAIN_PATTERNS_CATALOG.md) — Per-domain examples
- [Entity Type Architecture](ENTITY_TYPE_ARCHITECTURE.md) — Entity types and relationships
- Source: `core/models/` (194 files, 30 packages)
