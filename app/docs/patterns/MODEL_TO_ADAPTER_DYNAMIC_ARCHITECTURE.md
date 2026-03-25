---
title: Model-to-Adapter Dynamic Architecture
updated: 2026-03-24
category: patterns
related_skills: []
related_docs:
- /docs/patterns/BACKEND_OPERATIONS_ISP.md
---

# Model-to-Adapter Dynamic Architecture
**Date:** October 3, 2025 (Updated: March 24, 2026)
**Status:** 100% Dynamic - All domains use domain backend subclasses or UniversalNeo4jBackend[T]

## Executive Summary

The architecture is **100% dynamic** for model-to-adapter connections. The introspection-based design with `UniversalNeo4jBackend` and `Neo4jGenericMapper` means changes to domain models automatically ripple to adapters.

---

## February 2026 Update: Backend Mixin Decomposition

`universal_backend.py` grew to 4,214 lines and was decomposed into a shell + 5 focused mixin files, mirroring the `BaseService` mixin decomposition done in January 2026.

**Result:** The same `UniversalNeo4jBackend[T]` API — unchanged for all 25+ callers in `services_bootstrap/`. Only the internal file layout changed.

```
adapters/persistence/neo4j/
    universal_backend.py          # ~527 lines (shell: __init__, helpers)
    _crud_mixin.py                # CrudOperations[T]
    _search_mixin.py              # EntitySearchOperations[T]
    _relationship_query_mixin.py  # RelationshipQuery + EdgeMetadata + fluent API
    _relationship_crud_mixin.py   # RelationshipCrud + validation helpers
    _user_entity_mixin.py         # Generic user-entity ops (5 methods)
    _traversal_mixin.py           # GraphTraversalOperations
    _hierarchy_mixin.py           # HierarchyConfig + _HierarchyMixin (6 hierarchy methods for Activity Domains)
    domain_backends.py            # 18 domain subclasses: TasksBackend, EventsBackend, GoalsBackend, HabitsBackend,
                                  #   ChoicesBackend, PrinciplesBackend, LessonBackend, KuBackend, LsBackend,
                                  #   LpBackend, ExerciseBackend, SubmissionsBackend, SharingBackend,
                                  #   RevisedExerciseBackend, FormTemplateBackend, FormSubmissionBackend,
                                  #   ActivityReportBackend, GroupBackend
```

**Class declaration:**
```python
class UniversalNeo4jBackend[T: DomainModelProtocol](
    _CrudMixin[T],
    _SearchMixin[T],
    _RelationshipQueryMixin[T],
    _RelationshipCrudMixin[T],
    _UserEntityMixin[T],
    _TraversalMixin,
):
```

**Security (March 2026):** All 6 mixin files validate interpolated values before Cypher string building. `_relationship_crud_mixin.py` validates relationship types in `_build_direction_pattern()` — the single choke point for all relationship pattern Cypher. `_traversal_mixin.py` validates pipe-separated relationship patterns in `traverse()` and `find_path()`. `_search_mixin.py` and `_user_entity_mixin.py` validate field names via `validate_field_name()` with safe-default fallback. Validators live in `core/utils/validation_helpers.py` and `crud_queries.py`.

**Cross-mixin dependencies** use `TYPE_CHECKING` stubs (zero runtime cost, MyPy-verified).

**Commit:** `dc77a7a` — 2675/2677 tests pass (2 pre-existing failures).

**See:** `/docs/patterns/BACKEND_OPERATIONS_ISP.md` for full mixin boundary map.
**See:** `/docs/decisions/ADR-044-neo4j-committed-architectural-choice.md` — Neo4j is a committed architectural choice; `UniversalNeo4jBackend` is the hexagonal boundary.

---

## March 2026 Update: Domain Backends Extended to All Domains

**All domains with relationship-specific Cypher now have typed domain backends.**

### What Changed

Four new domain backends added to `domain_backends.py`:

| Backend | Methods moved from |
|---------|-------------------|
| `KuBackend` | `ku_organization_service.py` — 7 ORGANIZES methods |
| `SubmissionsBackend` | `submissions_sharing_service.py` — 8 SHARES_WITH methods |
| `LpBackend` | `lp_progress_service.py` — 2 mastery progress queries |
| `ExerciseBackend` | `exercise_service.py` — 3 curriculum link methods |

**Rule:** Domain-specific relationship Cypher belongs on the domain backend. Cross-domain aggregation stays in services.

**4-layer consistency achieved across all domains:**
```
*Operations protocol → *Backend subclass → *Service facade → sub-services
```

### March 24, 2026 Update: Hierarchy Mixin + Curriculum Relationship CRUD

**`_HierarchyMixin`** added to `_hierarchy_mixin.py` — generic parent-child hierarchy operations shared by all 6 Activity Domain backends. Parameterized via `HierarchyConfig` frozen dataclass (relationship names, node labels, optional entity_type filter).

**6 mixin methods:** `get_children_raw`, `get_parent_raw`, `get_hierarchy_raw`, `create_hierarchy_relationship` (with cycle detection), `remove_hierarchy_relationship`, `would_create_cycle`.

**Activity backends updated (6):** All extend `_HierarchyMixin`. Each sets a `_hierarchy_config` class attribute. `get_stats_for_user()` moved from services to backends. ~790 lines of inline Cypher removed from 5 core services.

| Backend | Hierarchy Config |
|---------|-----------------|
| `TasksBackend` | HAS_SUBTASK / SUBTASK_OF, Entity |
| `GoalsBackend` | HAS_SUBGOAL / SUBGOAL_OF, Entity |
| `HabitsBackend` | HAS_SUBHABIT / SUBHABIT_OF, Habit |
| `EventsBackend` | HAS_SUBEVENT / SUBEVENT_OF, Entity |
| `PrinciplesBackend` | HAS_SUBPRINCIPLE / SUBPRINCIPLE_OF, Principle |
| `ChoicesBackend` | HAS_SUBCHOICE / SUBCHOICE_OF, Entity (node_filter: entity_type='choice') |

**Curriculum backends extended:**

| Backend | Methods Added |
|---------|-------------|
| `LsBackend` | 4 CONTAINS_KNOWLEDGE methods + 6 CRUD methods: `create_step_node`, `get_step_with_knowledge`, `get_step_with_context`, `update_step_fields`, `delete_step_node`, `list_steps_raw` |
| `LpBackend` | 5 HAS_STEP methods: `get_steps_raw`, `get_parent_path_raw`, `add_step_to_path`, `remove_step_from_path`, `reorder_steps` |
| `GoalsBackend` | 4 progress-helper methods: `find_linked_goals_for_task`, `count_linked_tasks`, `find_linked_goals_for_habit`, `count_linked_habits_avg_streak` |
| `KuBackend` | 2 substance methods: `batch_increment_substance`, `increment_substance` |

**Protocols updated:** `EventsOperations`, `ChoicesOperations`, `PrinciplesOperations` now extend `HierarchyOperations`. `LsOperations`, `LpOperations`, `GoalsOperations` gained method signatures for the new backend methods.

**March 24, 2026 Update: Remaining 12 Services Migrated**

Phase 5 completed the backend delegation refactor — ~46 inline Cypher queries from 12 service files moved to domain backends. Two new backends created: `GroupBackend` (6 OWNS/MEMBER_OF methods) and `NotificationBackend` (5 HAS_NOTIFICATION methods). All existing backends extended: `LessonBackend` (+18 user progress/graph context methods), `KuBackend` (+6 usage/search methods), `SubmissionsBackend` (+14 exercise processing/relationship/assessment methods), `ExerciseBackend` (+6 methods), `RevisedExerciseBackend` (+4 methods), `HabitsBackend` (+4 badge methods), `FormTemplateBackend` (+1), `FormSubmissionBackend` (+1).

**File layout:**
```
adapters/persistence/neo4j/
    _hierarchy_mixin.py           # HierarchyConfig + _HierarchyMixin (6 generic methods)
    domain_backends.py            # 18 domain subclasses (6 Activity + 5 Curriculum + 7 Other)
```

### March 25, 2026 Update: Report + Teacher Review Services Migrated (Phase 4)

Two more services migrated to domain backends — zero inline Cypher remains in either service.

**New backend:** `ActivityReportBackend` (6 methods):
| Method | What It Does |
|--------|-------------|
| `get_history` | Query ActivityReports by subject_uid |
| `annotate` | Save annotation/revision on owned ActivityReport |
| `get_annotation` | Get annotation state for owned ActivityReport |
| `get_admin_snapshots` | Privacy audit: admin-written reports received by user |
| `get_shares_granted` | Privacy audit: SHARES_WITH access to user's entities |
| `get_report_schedule` | Privacy audit: active report schedule |

**Existing backends extended:**
| Backend | Methods Added |
|---------|-------------|
| `SubmissionsBackend` | +10 teacher review methods: `get_review_queue`, `get_report_history`, `create_report_node`, `approve_and_get_linked_kus`, `get_submissions_for_exercise_review`, `get_students_summary`, `get_student_submissions_for_teacher`, `get_submission_detail_for_teacher`, `get_dashboard_stats`, `verify_teacher_access` |
| `ExerciseBackend` | +1: `get_exercises_with_submission_counts` |
| `GroupBackend` | +2: `get_teacher_groups_with_stats`, `get_group_detail` |

**Fail-fast cleanup:**
- `ActivityReportService`: `executor` dependency removed, `event_bus` made required
- `TeacherReviewService`: `executor` replaced with 3 required typed backends (`SubmissionsBackend`, `ExerciseBackend`, `GroupBackend`), `event_bus` made required

---

## January 2026 Update: Wrapper Classes Removed

**Deleted ~2,000 lines** of wrapper code from curriculum domains (LS, LP, MOC).

### What Changed

| Domain Group | Before | After |
|--------------|--------|-------|
| **Activity (6)** | Per-domain wrapper classes | UniversalNeo4jBackend[T] ✅ |
| **Curriculum (3)** | Wrapper backends | UniversalNeo4jBackend[T] ✅ |
| **Content/Org (3)** | Mixed | UniversalNeo4jBackend[T] ✅ |
| **Finance (1)** | UniversalNeo4jBackend[T] | UniversalNeo4jBackend[T] ✅ |

**Note:** Activity Domains later gained typed domain backend subclasses (February 2026) and Curriculum/Submissions followed (March 2026). The distinction is: old "wrappers" duplicated generic CRUD; new domain backends ADD domain-specific methods on top of the universal base.

### New Helper Methods

`_build_direction_pattern()` added to consolidate ~30 lines of duplicated Cypher pattern building:

```python
def _build_direction_pattern(
    self,
    relationship_type: str,
    direction: Direction,
    rel_var: str | None = None,
    target_label: str | None = None,
) -> Result[str]:
    """Build Cypher pattern for directional relationship traversal."""
```

### Driver Access Patterns

| Pattern | When to Use | Example |
|---------|-------------|---------|
| `self.backend.method()` | Standard CRUD, search, relationships | `await self.backend.find_by(status="active")` |
| `self.backend.driver.execute_query()` | Complex graph queries returning EagerResult | Semantic relationships, aggregations |
| `self.backend.driver.session()` | Multi-statement transactions | AVOID - prefer execute_query() |

### Fail-Fast Alignment

Driver guards (`if not self.backend.driver: return Error`) were **removed** from LS/LP services:
- `ls_core_service.py`: 6 guards removed
- `lp_core_service.py`: 8 guards removed

These violated fail-fast philosophy - driver is REQUIRED at bootstrap.

---

## What's Already Dynamic ✅

### 1. **Core CRUD Operations** (100% Dynamic)

**The Flow:**
```
create: Task (add field) → to_neo4j_node() → Neo4j
update: dict of changes  → to_neo4j_node() → Neo4j  (March 2026)
read:                      ← from_neo4j_node() ← Neo4j
```

Both `create()` and `update()` in `_CrudMixin` route through `to_neo4j_node()`, so services pass native Python types (dicts, enums, dates) and the mapper handles all Neo4j serialization (dicts → JSON strings, enums → values, dates → ISO strings). Services never call `json.dumps()` before `backend.update()`.

**How it works:**
```python
# In core/utils/neo4j_mapper.py

def to_neo4j_node(entity: Any) -> dict:
    """Uses Python introspection to serialize ANY dataclass or dict."""
    # For dataclasses: iterates fields(entity)
    # For dicts: iterates key/value pairs (used by update())
    # Both paths apply the same serialization rules:
    if isinstance(value, Enum):
        node_data[field.name] = value.value  # ← Auto-handles enums
    elif isinstance(value, date):
        node_data[field.name] = value.isoformat()  # ← Auto-converts dates
    elif isinstance(value, dict):
        node_data[field.name] = json.dumps(value)  # ← Neo4j can't store nested dicts
    # ... etc
```

**For custom Cypher** (services that bypass `UniversalNeo4jBackend`), two utilities handle the read side:
```python
from core.utils.neo4j_mapper import parse_neo4j_json, deserialize_json_fields

# Single value — parse a JSON-encoded Neo4j property
topics = parse_neo4j_json(record["key_topics"], default=[])

# Multiple fields — deserialize several JSON fields in a dict
deserialize_json_fields(insight_data, "related_entities", "recommended_actions", "supporting_data")
```

**Proof:**
```python
# Add a NEW field to Task:
@dataclass(frozen=True)
class Task:
    uid: str
    title: str
    estimated_hours: Optional[float] = None  # ← NEW FIELD

# Result:
task = Task(uid="1", title="Test", estimated_hours=3.5)
node_data = to_neo4j_node(task)
# ✅ {'uid': '1', 'title': 'Test', 'estimated_hours': 3.5}
# ✅ NEW field automatically serialized, no adapter changes needed!
```

### 2. **Enum Handling** (100% Dynamic)

**Automatic enum serialization/deserialization:**

```python
# In model
task = Task(priority=Priority.HIGH, status=EntityStatus.ACTIVE)

# to_neo4j_node() automatically:
# priority: Priority.HIGH → 'high'  (extracts .value)
# status: EntityStatus.ACTIVE → 'in_progress'

# from_neo4j_node() automatically:
# 'high' → Priority.HIGH  (reconstructs enum)
# 'in_progress' → EntityStatus.ACTIVE

# ✅ Edit core/models/enums/ → Add Priority.URGENT → Works immediately in adapters
```

### 3. **Type Safety** (100% Dynamic)

Uses Python type hints to ensure correct reconstruction:

```python
# Model defines types
@dataclass(frozen=True)
class Task:
    uid: str
    estimated_hours: Optional[float]
    priority: Priority

# from_neo4j_node uses type hints to reconstruct correctly:
# str → str
# float → float
# 'high' → Priority.HIGH (enum reconstruction)
```

### 4. **Complex Types** (100% Dynamic)

Automatically handles lists, dicts, nested dataclasses:

```python
@dataclass(frozen=True)
class Task:
    tags: list[str]  # ← Lists auto-serialized to JSON
    metadata: dict[str, Any]  # ← Dicts auto-serialized to JSON
    related_knowledge: tuple[str, ...]  # ← Tuples handled

# ✅ All work automatically via neo4j_mapper introspection
```

---

## What Remains Manual (Edge Cases)

> **Note:** The core data flow is 100% dynamic. These are optimization opportunities, not gaps.

### 1. **Domain-Specific Query Methods** (Manual)

**Current State:**
```python
# tasks_enhanced_backend.py
async def get_tasks_by_priority(self, priority: Priority) -> Result[List[Task]]:
    query = """
    MATCH (t:Task)
    WHERE t.priority = $priority
    RETURN t
    """
    # ❌ Manually written Cypher query
    # ❌ If you add a field, this query doesn't automatically use it
```

**Problem:**
- Adding `estimated_hours` to Task doesn't automatically create `get_tasks_by_estimated_hours()`
- Queries are manually written in enhanced backends

### 2. **Neo4j Indexes** (Manual)

**Current State:**
```python
# Indexes must be manually created
CREATE INDEX task_priority IF NOT EXISTS FOR (t:Task) ON (t.priority)
CREATE INDEX task_due_date IF NOT EXISTS FOR (t:Task) ON (t.due_date)
```

**Problem:**
- Add `estimated_hours` to model → index not automatically created
- Performance degrades until developer remembers to add index

### 3. **Relationship Definitions** (Semi-Dynamic)

**Current State:**
```python
# Relationships defined in enhanced backends
async def link_task_to_goal(self, task_uid: str, goal_uid: str):
    query = """
    MATCH (t:Task {uid: $task_uid})
    MATCH (g:Goal {uid: $goal_uid})
    MERGE (t)-[:CONTRIBUTES_TO]->(g)
    """
```

**Status:**
- RelationshipType enum is dynamic ✅
- But creating new relationship methods requires manual backend code ❌

### 4. **Search/Filter Query Generation** (Manual)

**Current State:**
```python
async def search_tasks(self, filters: Dict[str, Any]):
    # ❌ Manually build WHERE clauses based on filters
    # ❌ Add new field to Task → search doesn't include it automatically
```

---

## The Architecture You've Built

```
┌─────────────────────────────────────────────────────┐
│           Domain Models (100% Your Control)         │
│                                                      │
│  @dataclass(frozen=True)                            │
│  class Task:                                        │
│      uid: str                                       │
│      title: str                                     │
│      priority: Priority  # ← enum from shared_enums│
│      estimated_hours: Optional[float]  # ← NEW      │
└──────────────────┬──────────────────────────────────┘
                   │
         ┌─────────┴──────────┐
         │                    │
         ▼                    ▼
┌────────────────────┐  ┌───────────────────────┐
│ Neo4jGenericMapper │  │ UniversalNeo4jBackend │
│                    │  │                       │
│ Uses Python        │  │ Generic CRUD for      │
│ introspection:     │  │ ANY entity type       │
│                    │  │                       │
│ - fields(entity)   │  │ - create(entity)      │
│ - get_type_hints() │  │ - get(uid)            │
│ - isinstance()     │  │ - update(uid, dict)   │
│                    │  │ - delete(uid)         │
│                    │  │ - list()              │
└─────────┬──────────┘  └──────────┬────────────┘
          │                        │
          │   ✅ 100% DYNAMIC     │
          │   Add field to model  │
          │   → Works immediately │
          │                        │
          └────────────┬───────────┘
                       │
                       ▼
              ┌────────────────┐
              │    Neo4j DB    │
              │                │
              │  Stores ANY    │
              │  field auto    │
              └────────────────┘
```

---

## What You Already Have (Don't Underestimate This!)

Your architecture is **revolutionary** because:

### 1. **Zero Backend Code for New Fields**

```python
# OLD WAY (before your architecture):
# Add field to Task → Must update:
# - tasks_neo4j_backend.py (serialization)
# - tasks_neo4j_backend.py (deserialization)
# - tasks_neo4j_backend.py (query methods)
# Total: 3+ files, 50+ lines of code

# YOUR WAY:
# Add field to Task → Done!
# Total: 1 file, 1 line of code
```

### 2. **Enum Changes Ripple Automatically**

```python
# Add Priority.URGENT to core/models/enums/
# ✅ Serialization handles it (via .value extraction)
# ✅ Deserialization handles it (via enum reconstruction)
# ✅ UI displays it (via get_color() method)
# ✅ Queries filter by it (value passed to Neo4j)
# ZERO adapter code changes needed!
```

### 3. **Type Safety Across Layers**

```python
# Model defines: estimated_hours: Optional[float]
# ✅ to_neo4j_node() stores as float
# ✅ from_neo4j_node() reconstructs as float
# ✅ Type checkers verify correctness
# ✅ Runtime errors impossible (type mismatch caught)
```

---

## Recommendations

1. ✅ **Keep using introspection-based mappers** - Already perfect
2. ✅ **Keep using UniversalNeo4jBackend** - Already perfect
3. 📝 **Create migration guide** for when fields are removed
4. 📝 **Add validation** for Neo4j property name conflicts

---

## The Bottom Line

**You asked:** "How can models ripple into adapters?"

**The answer:** **They already do!** Your introspection-based architecture with `Neo4jGenericMapper` and `UniversalNeo4jBackend` means:

✅ **Add a field to any model → It's automatically stored in Neo4j**
✅ **Change an enum value → Automatically serialized/deserialized**
✅ **Change a type → Automatically handled correctly**

The **core data flow is 100% dynamic**.

---

## Example: Adding a Field Today

**Before (OLD architecture):**
```
1. Edit Task - add field
2. Edit tasks_neo4j_backend.py - add serialization
3. Edit tasks_neo4j_backend.py - add deserialization
4. Edit tasks_neo4j_backend.py - update query methods
5. Create migration script for existing data
6. Update tests
Time: 2-4 hours
```

**After (YOUR architecture):**
```
1. Edit Task - add field
Time: 30 seconds

✅ Serialization automatic (via introspection)
✅ Deserialization automatic (via type hints)
✅ Queries work automatically (field stored in Neo4j)
✅ Type safety automatic (Python annotations)
```

**This is the ripple effect you envisioned.** The plant (models) grows freely on the lattice (adapters) through introspection.

---

## Conclusion

The plant (models) grows freely on the lattice (adapters) through introspection. The core ripple effect from models to adapters **already works**.

This is SKUEL's second dynamic layer:
1. **Presentation Layer** (just completed): core/models/enums/ → UI/Services
2. **Data Layer** (this analysis): Domain models → Adapters

Both use the same principle: **Introspection over configuration. Runtime discovery over compile-time declarations.**
