---
title: Embedding Infrastructure Alignment - Activity & Curriculum Domains
date: 2026-02-01
status: complete
category: migration
---

# Embedding Infrastructure Alignment (2026-02-01)

## Problem

Tasks and Goals domains were failing with:
```
TaskDTO.__init__() got an unexpected keyword argument 'embedding'
GoalDTO.__init__() got an unexpected keyword argument 'embedding'
```

**Root cause:** Neo4j nodes contain infrastructure fields (`embedding`, `embedding_version`, `embedding_model`, `embedding_updated_at`) that DTOs don't define.

## Architectural Decision (ADR-037)

**Embeddings are search infrastructure, not domain data.**

- Stored in Neo4j for vector search
- 1536-dimensional vectors not needed in application memory
- Automatically filtered out when converting to DTOs
- Consistent across all domains using `dto_from_dict`

## Domains Aligned

### Activity Domains (6/6) ✅

All use `dto_from_dict` with automatic filtering:

| Domain | Status | DTO File |
|--------|--------|----------|
| **Tasks** | ✅ Aligned | `core/models/task/task_dto.py` |
| **Goals** | ✅ Aligned | `core/models/goal/goal_dto.py` |
| **Habits** | ✅ Aligned | `core/models/habit/habit_dto.py` |
| **Events** | ✅ Aligned | `core/models/event/event_dto.py` |
| **Choices** | ✅ Migrated | `core/models/choice/choice_dto.py` |
| **Principles** | ✅ Aligned | `core/models/principle/principle_dto.py` |

**ChoiceDTO Special Case:**
- Previously used manual field filtering (60+ lines)
- Migrated to generic `dto_from_dict` for consistency
- Removed manual `known_fields` whitelist

### Curriculum Domains (1/3) ✅

| Domain | Status | Notes |
|--------|--------|-------|
| **KU** | ✅ Aligned | Migrated to `dto_from_dict` |
| **LS** | ⏭️ Different Pattern | Uses custom converters, no `from_dict` |
| **LP** | ⏭️ Different Pattern | Uses custom converters, no `from_dict` |

**LS/LP:** Use `ls_create_request_to_dto()` and `lp_create_request_to_dto()` converters instead of `from_dict`. Not affected by this issue.

## Changes Made

### 1. Generic Filtering in `dto_from_dict`

**File:** `core/models/dto_helpers.py` (line 591)

```python
# Filter out fields that don't exist in the dataclass
if is_dataclass(cls):
    valid_field_names = {f.name for f in dataclass_fields(cls)}
    filtered_data = {k: v for k, v in data.items() if k in valid_field_names}
    return cls(**filtered_data)
```

**Infrastructure fields automatically filtered:**
- `embedding` - 1536-dimensional vector
- `embedding_version` - Model version
- `embedding_model` - Model name
- `embedding_updated_at` - Generation timestamp

### 2. ChoiceDTO Migration

**Before (manual filtering):**
```python
# 60+ lines of manual field filtering
known_fields = {
    "uid", "title", "description", ...  # 30+ fields
}
filtered_data = {k: v for k, v in data.items() if k in known_fields}
return cls(**filtered_data)
```

**After (generic):**
```python
return dto_from_dict(
    cls, data,
    enum_fields={},
    datetime_fields=["decision_deadline", "created_at", ...],
    list_fields=["decision_criteria", "constraints", ...],
    dict_fields=["metadata"],
)
```

### 3. KuDTO Migration *(Note: KuDTO deleted 2026-02-23, replaced by CurriculumDTO)*

**Before (manual):**
```python
parse_datetime_fields(data, ["created_at", "updated_at"])
parse_enum_field(data, "domain", Domain)
ensure_list_fields(data, ["tags", "semantic_links"])
for old_field in ["prerequisites", "enables", "related_to"]:
    data.pop(old_field, None)
return cls(**data)  # ❌ Would fail with embedding field
```

**After (generic with filtering):**
```python
return dto_from_dict(
    cls, data,
    enum_fields={"domain": Domain},
    datetime_fields=["created_at", "updated_at"],
    list_fields=["tags", "semantic_links"],
    deprecated_fields=["prerequisites", "enables", "related_to"],
)  # ✅ Automatically filters embedding
```

### 4. Documentation Updates

**New Documentation:**
- `/docs/decisions/ADR-037-embedding-infrastructure-separation.md` - Architectural decision
- `/docs/migrations/EMBEDDING_INFRASTRUCTURE_ALIGNMENT_2026-02-01.md` - This file

**Updated Documentation:**
- `CLAUDE.md` - Added infrastructure field filtering note
- `/docs/patterns/three_tier_type_system.md` - Added embedding filtering section
- `core/models/dto_helpers.py` - Added detailed architectural comment
- `core/models/task/task_dto.py` - Updated docstring
- `core/models/goal/goal_dto.py` - Updated docstring
- `core/models/choice/choice_dto.py` - Updated docstring
- `core/models/ku/ku_dto.py` - Updated docstring

### 5. Test Coverage

**New Test:** `tests/unit/test_dto_from_dict_embedding_filter.py`

Tests that verify:
- ✅ TaskDTO filters embedding field
- ✅ GoalDTO filters embedding field
- ✅ All valid fields preserved
- ✅ Unknown fields silently filtered

## Verification

Run tests to verify:
```bash
# Specific test
uv run pytest tests/unit/test_dto_from_dict_embedding_filter.py -v

# All DTO tests
uv run pytest tests/unit/ -k "dto" -v

# Full test suite
uv run pytest
```

## Impact

### Code Reduction
- **Before:** Manual filtering in ChoiceDTO (60+ lines)
- **After:** Generic filtering in `dto_from_dict` (15 lines)
- **Saved:** ~60 lines of redundant code

### Consistency
- All Activity domains use identical pattern
- No special cases or domain-specific filtering
- Future domains automatically get filtering

### Type Safety
- Only dataclass-defined fields passed to `__init__`
- No runtime errors from unknown fields
- MyPy can verify field access

## Migration Status

✅ **COMPLETE** - All affected domains aligned

**Breakdown:**
- Activity Domains: 6/6 ✅
- Curriculum Domains: 1/3 ✅ (2 use different pattern)
- Total Aligned: 7/9 domains

## Related

- **ADR-037:** Embedding Infrastructure Separation
- **Three-Tier Type System:** `/docs/patterns/three_tier_type_system.md`
- **DTO Helpers:** `/core/models/dto_helpers.py`
- **Embedding Worker:** `/core/services/background/embedding_worker.py`

## Rollout

✅ **Completed 2026-02-01**

1. ✅ Implemented generic filtering in `dto_from_dict`
2. ✅ Migrated ChoiceDTO from manual to generic filtering
3. ✅ Migrated KuDTO to use generic filtering
4. ✅ Updated all docstrings
5. ✅ Created ADR-037
6. ✅ Added test coverage
7. ✅ Updated documentation
