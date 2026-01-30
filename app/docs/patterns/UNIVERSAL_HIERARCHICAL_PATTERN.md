# Universal Hierarchical Pattern
**Status:** Implemented (2026-01-30)
**Scope:** All Domains (Activity, Curriculum, Infrastructure)
**Principle:** "All hierarchy is graph relationships, never UID encoding"

---

## Table of Contents

1. [Core Principle](#core-principle)
2. [Pattern Overview](#pattern-overview)
3. [Implementation by Domain](#implementation-by-domain)
4. [Benefits](#benefits)
5. [Migration Guide](#migration-guide)
6. [Examples](#examples)
7. [Related Documentation](#related-documentation)

---

## Core Principle

**"All hierarchy is graph relationships, never UID encoding"**

SKUEL uses ONE consistent pattern for hierarchy across all domains:

1. **Flat UIDs** - Identity independent of location (`task_abc123`, `ku_meditation_xyz789`)
2. **Graph relationships** - Hierarchy via edges with metadata (`HAS_SUBTASK`, `ORGANIZES`)
3. **Display hierarchy** - Generated from graph traversal, not UID parsing
4. **DAG support** - Multiple parents possible (Directed Acyclic Graph, not tree)

---

## Pattern Overview

### Before: Inconsistent Patterns (Pre-2026-01-30)

```python
# Activity Domains - Flat UIDs + Relationships ✅
task_abc123 → (task)-[:HAS_SUBTASK]->(task)

# KU - Hierarchical UIDs ❌
ku.yoga.meditation.basics → Parent encoded in UID string
```

**Problems:**
- Two different mental models
- KU reorganization broke UIDs
- No multiple parents for KUs
- String parsing needed for hierarchy

### After: Universal Pattern (2026-01-30)

```python
# ALL Domains - Flat UIDs + Relationships ✅
task_abc123         → (task)-[:HAS_SUBTASK]->(task)
ku_meditation_xyz   → (ku)-[:ORGANIZES]->(ku)
goal_project_def    → (goal)-[:HAS_SUBGOAL]->(goal)
habit_routine_ghi   → (habit)-[:HAS_SUBHABIT]->(habit)
```

**Benefits:**
- One mental model everywhere
- Reorganization never changes UIDs
- Multiple parents possible
- Consistent query patterns

---

## Implementation by Domain

### Activity Domains

**Domains:** Tasks, Goals, Habits, Events, Choices, Principles

**UID Format:**
```
{type}_{slug}_{random}
```

**Examples:**
```
task_implement-auth_a1b2c3d4
goal_complete-project_x7y8z9w0
habit_daily-exercise_def45678
```

**Parent-Child Relationships:**

| Domain | Relationship | Properties | Bidirectional |
|--------|-------------|------------|---------------|
| **Task** | `HAS_SUBTASK` / `SUBTASK_OF` | `progress_weight`, `order` | ✅ |
| **Goal** | `HAS_SUBGOAL` / `SUBGOAL_OF` | `progress_weight`, `order` | ✅ |
| **Habit** | `HAS_SUBHABIT` / `SUBHABIT_OF` | `progress_weight`, `order` | ✅ |

**Service Methods:**

```python
# Tasks (same pattern for Goals, Habits)
await tasks_service.get_subtasks(parent_uid, depth=1)
await tasks_service.get_parent_tasks(task_uid)
await tasks_service.get_task_hierarchy(task_uid)
await tasks_service.add_subtask(parent_uid, child_uid, progress_weight, order)
await tasks_service.remove_subtask(parent_uid, child_uid)
```

**Cypher Pattern:**

```cypher
// Create parent-child relationship
MATCH (parent:Task {uid: $parent_uid})
MATCH (child:Task {uid: $child_uid})
MERGE (parent)-[r:HAS_SUBTASK]->(child)
SET r.progress_weight = 0.5,
    r.order = 1,
    r.created_at = datetime()

// Bidirectional for efficient queries
MERGE (child)-[:SUBTASK_OF]->(parent)
```

---

### Curriculum Domains

#### KU (Knowledge Units)

**UID Format:**
```
ku_{slug}_{random}
```

**Examples:**
```
ku_meditation-basics_a1b2c3d4
ku_python-functions_x7y8z9w0
ku_machine-learning-101_def45678
```

**Organization Relationship:**

```cypher
// ORGANIZES - MOC Pattern
(parent:Ku)-[:ORGANIZES {order, importance}]->(child:Ku)
```

**Properties:**
- `order` (int) - Display order (0 = first)
- `importance` (string) - "core", "normal", "supplemental"
- `created_at` (datetime)
- `updated_at` (datetime)

**Service Methods:**

```python
# KU Hierarchical Methods (added 2026-01-30)
await ku_service.get_subkus(parent_uid, depth=1)
await ku_service.get_parent_kus(ku_uid)           # Multiple parents possible!
await ku_service.get_ku_hierarchy(ku_uid)
await ku_service.organize_ku(parent_uid, child_uid, order, importance)
await ku_service.unorganize_ku(parent_uid, child_uid)
```

**MOC Pattern:**

A KU "is" a MOC when it has outgoing ORGANIZES relationships. MOC is NOT a separate entity type.

```cypher
// Yoga Fundamentals MOC organizing 3 KUs
(ku_yoga_fundamentals:Ku)
  -[:ORGANIZES {order: 1, importance: "core"}]->
  (ku_meditation:Ku)

(ku_yoga_fundamentals:Ku)
  -[:ORGANIZES {order: 2, importance: "core"}]->
  (ku_breathing:Ku)

(ku_yoga_fundamentals:Ku)
  -[:ORGANIZES {order: 3, importance: "supplemental"}]->
  (ku_history:Ku)
```

**Multiple Parents (DAG):**

```cypher
// Machine Learning in 3 different MOCs
(ku_ai_fundamentals:Ku)-[:ORGANIZES]->(ku_machine_learning:Ku)
(ku_data_science:Ku)-[:ORGANIZES]->(ku_machine_learning:Ku)
(ku_python_advanced:Ku)-[:ORGANIZES]->(ku_machine_learning:Ku)

// Same KU, three different organizational contexts!
```

---

#### LS (Learning Steps)

**UID Format:**
```
ls:{random12}
```

**Examples:**
```
ls:a1b2c3d4e5f6
ls:x7y8z9w0v1u2
```

**Relationships:**

| Type | Pattern | Purpose |
|------|---------|---------|
| **Step Sequence** | `(lp)-[:HAS_STEP {order}]->(ls)` | LP contains steps |
| **Prerequisites** | `(ls)-[:REQUIRES_STEP]->(ls)` | Step dependencies |
| **Knowledge** | `(ls)-[:CONTAINS_KNOWLEDGE {type}]->(ku)` | Knowledge references |

**Knowledge Storage (Migrated 2026-01-30):**

**Before (Properties):**
```python
# OLD - Properties
class LS:
    primary_knowledge_uids: tuple[str, ...] = ()
    supporting_knowledge_uids: tuple[str, ...] = ()
```

**After (Relationships):**
```cypher
// NEW - Graph relationships
(ls:Ls)-[:CONTAINS_KNOWLEDGE {type: "primary"}]->(ku:Ku)
(ls:Ls)-[:CONTAINS_KNOWLEDGE {type: "supporting"}]->(ku:Ku)
```

**Service Methods:**

```python
# LS Knowledge Methods (pending implementation)
await ls_service.add_knowledge_relationship(ls_uid, ku_uid, type="primary")
await ls_service.get_contained_knowledge(ls_uid, type="primary")
```

---

#### LP (Learning Paths)

**UID Format:**
```
lp:{random}
```

**Examples:**
```
lp:abc123xyz789
lp:def456ghi012
```

**Relationships:**

```cypher
// Learning Path contains steps
(lp:Lp)-[:HAS_STEP {order: 1, sequence: 1}]->(ls:Ls)
(lp:Lp)-[:HAS_STEP {order: 2, sequence: 2}]->(ls:Ls)
```

---

## Benefits

### 1. Consistent Mental Model

**Before (Competing Designs):**
- "How do I create hierarchy? Tasks use relationships, KUs use UID encoding... which do I use?"
- Developer confusion switching between domains
- Two patterns to learn and maintain

**After (Unified):**
- "All hierarchy is relationships - same pattern everywhere"
- One mental model across all domains
- Predictable, learnable, transferable

---

### 2. Reorganization Safety

**Before:**
```python
# Moving KU changed UID (BREAKING!)
# Old: ku.yoga.meditation
# New: ku.wellness.meditation
# All references must update! Risk of breaking links!
```

**After:**
```python
# Moving updates edge only (SAFE!)
await ku_service.unorganize_ku(old_parent_uid, ku_uid)
await ku_service.organize_ku(new_parent_uid, ku_uid, order=1)
# UID unchanged: ku_meditation_xyz789
# All references intact!
```

---

### 3. Multiple Parents (DAG Support)

**Before:**
- Tasks: Multiple parents ✅
- Goals: Multiple parents ✅
- KUs: Single parent only ❌ (tree structure forced by UID encoding)

**After:**
- All entities: Multiple parents ✅ (DAG everywhere)

**Example:**
```cypher
// Machine Learning KU in 3 MOCs simultaneously
(ku_ai:Ku)-[:ORGANIZES]->(ku_ml:Ku)
(ku_data_science:Ku)-[:ORGANIZES]->(ku_ml:Ku)
(ku_python:Ku)-[:ORGANIZES]->(ku_ml:Ku)

// Query all parents
MATCH (parent:Ku)-[:ORGANIZES]->(ku:Ku {uid: "ku_ml_abc"})
RETURN parent
// Returns: AI Fundamentals, Data Science, Python Advanced
```

---

### 4. Relationship Metadata

**Before:**
- Tasks: Metadata on edges ✅ (progress_weight, order)
- KUs: No metadata ❌ (hierarchy in UID string)

**After:**
- All domains: Rich metadata on edges ✅

```cypher
[:ORGANIZES {
    order: 1,                    // Display order
    importance: "core",          // Priority level
    created_at: datetime(),      // When organized
    updated_at: datetime(),      // Last reorganization
    user_notes: "Focus here"     // Custom annotations
}]
```

---

### 5. Query Consistency

**Before:**
```python
# Different patterns per domain
subtasks = await get_related(task_uid, HAS_SUBTASK)  # Graph query
parent = get_parent_uid(ku_uid)  # String parsing!
```

**After:**
```python
# Same pattern everywhere
children = await service.get_related(
    entity_uid,
    relationship_type,  # HAS_SUBTASK, ORGANIZES, etc.
    direction="outgoing"
)
```

---

### 6. Cycle Prevention

**Built-in for all domains:**

```python
# Automatic cycle detection in organize_ku()
await ku_service.organize_ku(parent="ku_a", child="ku_b")  # OK
await ku_service.organize_ku(parent="ku_b", child="ku_c")  # OK
await ku_service.organize_ku(parent="ku_c", child="ku_a")  # ERROR: Cycle detected!

# Cypher check before creating relationship
MATCH path = (child)-[:ORGANIZES*]->(parent)
WHERE child.uid = $child_uid AND parent.uid = $parent_uid
RETURN length(path)
// If path exists → cycle would be created → reject
```

---

## Migration Guide

### Step 1: Check Current State

```bash
# Run analysis
poetry run python scripts/migrations/analyze_ku_uids.py

# Expected output:
# - Flat UIDs (underscore): X KUs
# - Hierarchical UIDs: Y KUs (if any need migration)
```

### Step 2: Backup Database

```bash
# Critical: Backup before any migration
neo4j-admin dump --database=neo4j --to=/backups/pre-universal-hierarchical.dump
```

### Step 3: Dry Run

```bash
# See what would change
poetry run python scripts/migrations/flatten_ku_uids.py --dry-run
```

### Step 4: Execute (if needed)

```bash
# Only if hierarchical KUs exist
poetry run python scripts/migrations/flatten_ku_uids.py --execute
```

### Step 5: Verify

```bash
# Check results
poetry run python scripts/migrations/analyze_ku_uids.py
# Should show: 0 hierarchical UIDs
```

---

## Examples

### Creating Hierarchical Structure

**Tasks:**
```python
# Create parent task
parent = await tasks_service.create(
    title="Implement Auth System",
    description="Full authentication implementation",
    user_uid="user_mike"
)
# Result: task_implement-auth-system_a1b2c3d4

# Create subtasks
jwt_task = await tasks_service.create(
    title="Setup JWT",
    user_uid="user_mike"
)
login_task = await tasks_service.create(
    title="Login Endpoint",
    user_uid="user_mike"
)

# Create hierarchy
await tasks_service.add_subtask(
    parent_uid=parent.uid,
    child_uid=jwt_task.uid,
    progress_weight=0.5,
    order=1
)
await tasks_service.add_subtask(
    parent_uid=parent.uid,
    child_uid=login_task.uid,
    progress_weight=0.5,
    order=2
)
```

**KUs:**
```python
# Create MOC (Map of Content)
moc = await ku_service.create(
    title="Yoga Fundamentals",
    body="Comprehensive guide to yoga practice",
    tags=["yoga", "wellness"]
)
# Result: ku_yoga-fundamentals_abc123

# Create child KUs
meditation = await ku_service.create(
    title="Meditation Basics",
    body="Introduction to meditation",
    parent_uid=moc.uid,  # Auto-creates ORGANIZES
    order=1,
    importance="core"
)

breathing = await ku_service.create(
    title="Breathing Techniques",
    body="Pranayama fundamentals",
    parent_uid=moc.uid,
    order=2,
    importance="core"
)

history = await ku_service.create(
    title="History of Yoga",
    body="Origins and evolution",
    parent_uid=moc.uid,
    order=3,
    importance="supplemental"
)
```

---

### Querying Hierarchy

**Get Children:**
```python
# Get all subtasks (1 level deep)
result = await tasks_service.get_subtasks(parent_uid, depth=1)

# Get all sub-KUs (2 levels deep)
result = await ku_service.get_subkus(moc_uid, depth=2)
```

**Get Parents:**
```python
# Get parent tasks
result = await tasks_service.get_parent_tasks(task_uid)

# Get parent KUs (can have multiple!)
result = await ku_service.get_parent_kus(ku_uid)
# Returns: All MOCs organizing this KU
```

**Get Full Hierarchy:**
```python
# Get complete context
result = await ku_service.get_ku_hierarchy(ku_uid)

# Returns:
{
    "ancestors": [
        {"uid": "ku_yoga_abc", "title": "Yoga Fundamentals", "level": 1},
        {"uid": "ku_wellness_def", "title": "Wellness", "level": 2}
    ],
    "siblings": [
        {"uid": "ku_breathing_ghi", "title": "Breathing Techniques"}
    ],
    "children": [
        {"uid": "ku_mindfulness_jkl", "title": "Mindfulness"}
    ],
    "depth": 2
}
```

---

### Reorganizing

**Move Entity:**
```python
# Remove from old parent
await ku_service.unorganize_ku(
    parent_uid="ku_yoga_abc",
    child_uid="ku_meditation_xyz"
)

# Add to new parent
await ku_service.organize_ku(
    parent_uid="ku_wellness_def",
    child_uid="ku_meditation_xyz",
    order=1,
    importance="core"
)

# UID unchanged! All references intact!
```

**Multiple Parents:**
```python
# Add same KU to multiple MOCs
await ku_service.organize_ku("ku_ai_abc", "ku_ml_xyz", order=1)
await ku_service.organize_ku("ku_data_science_def", "ku_ml_xyz", order=2)
await ku_service.organize_ku("ku_python_ghi", "ku_ml_xyz", order=3)

# Machine Learning appears in 3 different contexts
```

---

### Cypher Queries

**Find All Descendants:**
```cypher
// Get all KUs under a MOC (any depth)
MATCH (moc:Ku {uid: "ku_yoga_abc"})-[:ORGANIZES*]->(descendant:Ku)
RETURN descendant.uid, descendant.title
ORDER BY descendant.title
```

**Find All Ancestors:**
```cypher
// Get all MOCs containing a KU
MATCH (ancestor:Ku)-[:ORGANIZES*]->(ku:Ku {uid: "ku_meditation_xyz"})
RETURN ancestor.uid, ancestor.title, length(path) as depth
ORDER BY depth
```

**Check for Cycles:**
```cypher
// Verify no circular references exist
MATCH path = (ku:Ku)-[:ORGANIZES*]->(ku)
RETURN ku.uid, length(path) as cycle_length
// Should return empty (no cycles)
```

**Progress Aggregation (Tasks):**
```cypher
// Calculate parent task completion from subtasks
MATCH (parent:Task {uid: $parent_uid})-[r:HAS_SUBTASK]->(child:Task)
WITH parent,
     sum(CASE WHEN child.status = 'COMPLETED' THEN r.progress_weight ELSE 0 END) as completed_weight,
     sum(r.progress_weight) as total_weight
RETURN completed_weight / total_weight as progress_percentage
```

---

## Related Documentation

### Pattern Documentation
- `/docs/patterns/HIERARCHICAL_RELATIONSHIPS_PATTERN.md` - Activity domain implementation
- `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md` - KU, LS, LP patterns
- `/docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md` - Domain overview

### Decision Records
- `/docs/decisions/ADR-013-ku-uid-flat-identity.md` - KU flat identity decision

### Migration Documentation
- `/docs/migrations/UNIVERSAL_HIERARCHICAL_IMPLEMENTATION_2026-01-30.md` - Implementation plan
- `/docs/migrations/UNIVERSAL_HIERARCHICAL_COMPLETE_2026-01-30.md` - Completion report
- `/docs/migrations/HIERARCHICAL_RELATIONSHIPS_IMPLEMENTATION_COMPLETE_2026-01-30.md` - Activity domain completion

### Code References
- `/core/utils/uid_generator.py` - Flat UID generation
- `/core/models/relationship_names.py` - Relationship type definitions
- `/core/services/ku/ku_core_service.py` - KU hierarchical methods
- `/core/services/tasks/tasks_core_service.py` - Task hierarchical methods

---

## Summary

The Universal Hierarchical Pattern achieves:

✅ **Consistency** - One pattern across all domains
✅ **Flexibility** - Reorganize without breaking UIDs
✅ **DAG Support** - Multiple parents possible
✅ **Metadata** - Rich relationship properties
✅ **Safety** - Cycle prevention built-in
✅ **Simplicity** - One mental model to learn

**Core Principle:** "All hierarchy is graph relationships, never UID encoding"

This pattern extends SKUEL's graph-first philosophy to entity identity, ensuring that the structure of relationships matches the structure of data storage - consistent, flexible, and graph-native.
