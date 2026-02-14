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

## Key Files

| Component | Location |
|-----------|----------|
| Ku model | `core/models/ku/ku.py` |
| KuDTO | `core/models/ku/ku_dto.py` |
| KuType | `core/models/enums/ku_enums.py` |
| KuStatus | `core/models/enums/ku_enums.py` |
| CompletionStatus | `core/models/enums/ku_enums.py` |
| Priority | `core/models/enums/activity_enums.py` |
| ActivityType | `core/models/enums/activity_enums.py` |

## Related ADRs

- ADR-035: Tier Selection Guidelines
- ADR-037: Infrastructure Field Filtering
