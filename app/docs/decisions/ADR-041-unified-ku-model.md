# ADR-041: Unified Ku Model

**Status:** Accepted
**Date:** 2026-02-14
**Deciders:** Mike, Claude

## Context

SKUEL originally had 14 separate domain model packages (`core/models/task/`, `core/models/goal/`, etc.), each with three-tier type systems (Pydantic → DTO → frozen dataclass). This resulted in:

- ~18,000 lines of nearly-identical model code across 14 packages
- Inconsistent field naming across domains
- Multiple status enums (`ActivityStatus`, `GoalStatus`) with overlapping values
- Each domain requiring its own backend factory in `universal_backend.py`

## Decision

**Everything is a Ku.** All 14 domain types are stored as unified `Ku` nodes in Neo4j, discriminated by `KuType`. One model (`Ku`), one DTO (`KuDTO`), one status enum (`KuStatus`).
**Update (2026-02-23):** KuDTO deleted. All services now use per-domain DTOs (TaskDTO, GoalDTO, etc.).

### Phase 1-6: Model Unification (2026-02-10 to 2026-02-13)

Migrated all 14 domains to use the unified `Ku` model:
- Deleted `core/models/task/`, `core/models/goal/`, `core/models/habit/` (request models kept)
- Deleted `core/models/event/`, `core/models/choice/`, `core/models/principle/`
- Deleted `core/models/lifepath/`
- Deleted three-tier LS, LP, KU models
- **~18,000 lines of model code removed**

Pydantic request models (`*_request.py`) remain in their domain packages for API validation.

### Phase 7: Enum Consolidation (2026-02-14)

Unified status enums:
- `ActivityStatus` (11 values) → `KuStatus` (14 values)
- `GoalStatus` (7 values) → `KuStatus` (14 values)
- Key value mappings:
  - `ActivityStatus.IN_PROGRESS` ("in_progress") → `KuStatus.ACTIVE` ("active")
  - `GoalStatus.ACHIEVED` ("achieved") → `KuStatus.COMPLETED` ("completed")
  - `GoalStatus.PLANNED` ("planned") → `KuStatus.DRAFT` ("draft")
  - `ActivityStatus.RECURRING` → deleted (recurrence is a field, not a status)
- `CompletionStatus` moved from `activity_enums.py` to `ku_enums.py` (habit completion tracking)
- `ActivityType` stays in `activity_enums.py` (calendar/timeline classification, not status)

## Consequences

### Positive

- **Single source of truth**: One model, one status enum, one backend per domain
- **Type safety**: `KuType` discriminator + `KuStatus` with type-aware validation (`valid_statuses()`, `can_transition_to()`)
- **No silent bugs**: Status values are consistent — `KuStatus.ACTIVE` is always `"active"`, not sometimes `"in_progress"`
- **~18k lines removed**: Massive reduction in maintenance surface

### Negative

- Request models still live in domain packages (acceptable — they define domain-specific validation)
- Some services still have domain-specific status logic (e.g., goals use DRAFT→ACTIVE→COMPLETED, tasks use DRAFT→SCHEDULED→ACTIVE→COMPLETED)

### Neutral

- No data migration needed — no activity domain data existed in Neo4j at time of migration
- Learning/knowledge tracking system (`KnowledgeStatus.IN_PROGRESS`) is unaffected — different enum, different system

### Phase 8: Domain-First Model Hierarchy (2026-02-22)

The "Everything is a Ku" architecture was evolved to a domain-first model hierarchy while preserving the unified Neo4j storage:

**Phase 0: Neo4j Multi-Label + Backend Infrastructure**
- Added domain-specific Neo4j labels: every entity gets `:Entity` (universal) + domain label (`:Task`, `:Goal`, etc.)
- `NeoLabel` enum gained 16 domain labels with `from_entity_type()` mapper
- Backend `base_label=NeoLabel.ENTITY` for CREATE: `(n:Ku:Entity:Task)` triple labels
- User relationships standardized to `:OWNS` (was `:HAS_KU`)
- MEGA-QUERY fixed: now uses domain labels + OWNS relationships

**Phase 1: Model Class Renames**
- 17 class renames: `KuBase` → `Entity`, `TaskKu` → `Task`, `GoalKu` → `Goal`, etc.
- 17 file renames via git mv: `ku_task.py` → `task.py`, etc.
- 2 enum renames: `KuType` → `EntityType`, `KuStatus` → `EntityStatus` (still in `ku_enums.py`)
- NOT renamed: `ku_enums.py` file, `Ku` union type, `ku_type` DB field (KuDTO was later deleted in Phase 5b, 2026-02-23)
- 278 Python files changed, zero new mypy errors

**Phase 2: UserOwnedEntity Intermediate Class**
- New `UserOwnedEntity(Entity)` with `user_uid`, `priority` fields
- Entity slimmed: `user_uid`/`priority` removed as fields, added as properties returning None (backward compat for Ku union type)
- 8 models re-parented: Task, Goal, Habit, Event, Choice, Principle, Submission, LifePath
- Curriculum and Resource stay as direct Entity children
- `ActivityEntity` type alias added

**Phase 3-4: Per-Domain DTOs**
Replaced 138-field KuDTO God Object with per-domain DTOs mirroring the model hierarchy:
```
EntityDTO (~18 fields)
├── UserOwnedDTO(EntityDTO) +3 → TaskDTO, GoalDTO, HabitDTO, etc.
├── CurriculumDTO(EntityDTO) → LearningStepDTO, LearningPathDTO, ExerciseDTO
└── ResourceDTO(EntityDTO)
```

**Phase 5: Service Layer Migration**
- 57 service files migrated from KuDTO to per-domain DTOs
- KuDTO retained for cross-domain services (later deleted in Phase 5b, 2026-02-23)
- 7 type: ignore suppressions for pre-existing cross-domain field accesses

**Impact:**
- Model hierarchy now matches domain categories (Entity → UserOwnedEntity → Task)
- DTOs reduced from 138 fields to 30-50 fields each
- Neo4j queries use domain labels instead of property filtering
- Services use domain-specific types instead of God Object DTO

## Key Files

| Component | Location |
|-----------|----------|
| Ku model | `core/models/ku/ku.py` |
| KuDTO | ~~`core/models/ku/ku_dto.py`~~ (deleted 2026-02-23) |
| EntityType (was KuType) | `core/models/enums/ku_enums.py` |
| EntityStatus (was KuStatus) | `core/models/enums/ku_enums.py` |
| CompletionStatus | `core/models/enums/ku_enums.py` |
| Priority | `core/models/enums/activity_enums.py` |
| ActivityType | `core/models/enums/activity_enums.py` |
| Per-domain DTOs | `core/models/ku/{domain}_dto.py` (15 files) |
| Entity base | `core/models/ku/entity.py` |
| UserOwnedEntity | `core/models/ku/user_owned_entity.py` |
| EntityDTO base | `core/models/ku/entity_dto.py` |
| UserOwnedDTO | `core/models/ku/user_owned_dto.py` |
| NeoLabel | `adapters/persistence/neo4j/neo_labels.py` |

## Related ADRs

- ADR-035: Tier Selection Guidelines
- ADR-037: Infrastructure Field Filtering
