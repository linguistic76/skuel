# Universal Hierarchical Architecture Analysis
**Date:** 2026-01-30
**Status:** Analysis Complete - Awaiting User Decisions

## Executive Summary

SKUEL currently has **competing designs** for hierarchy across domains:

- ✅ **Activity Domains (Tasks, Goals, Habits):** Flat UIDs + Graph Relationships (CORRECT)
- ❌ **KU (Knowledge Units):** Hierarchical UIDs (dot-encoded parent paths) - CONFLICTS with ADR-013
- ✅ **MOC (Map of Content):** Flat KUs + ORGANIZES relationships (CORRECT - already aligned!)
- ⚠️ **LS (Learning Steps):** Flat UIDs but properties for knowledge (partial)
- ✅ **LP (Learning Paths):** Flat UIDs + HAS_STEP relationships (CORRECT)

**The Problem:** KU uses hierarchical UIDs (`ku.yoga.meditation.basics`) while Activity domains use flat UIDs (`task_abc123`) with graph relationships for hierarchy. This violates the "One Path Forward" philosophy.

**The Solution:** Extend the Activity domain pattern to ALL domains - flat UIDs everywhere, hierarchy via relationships only.

---

## Current State Analysis

### What We Just Implemented (Activity Domains) ✅

**Pattern:** "Flat Identity, Rich Structure"

**Implementation (2026-01-30):**
```cypher
# Storage - Flat UIDs
CREATE (parent:Task {uid: "task_abc123", title: "Implement Auth"})
CREATE (child1:Task {uid: "task_xyz789", title: "Setup JWT"})
CREATE (child2:Task {uid: "task_def456", title: "Login Endpoint"})

# Hierarchy - Graph Relationships
CREATE (parent)-[:HAS_SUBTASK {progress_weight: 0.5, order: 1}]->(child1)
CREATE (parent)-[:HAS_SUBTASK {progress_weight: 0.5, order: 2}]->(child2)
CREATE (child1)-[:SUBTASK_OF]->(parent)  # Bidirectional
CREATE (child2)-[:SUBTASK_OF]->(parent)
```

**Benefits:**
- ✅ Multiple parents possible (DAG not tree)
- ✅ Reorganize without changing UIDs
- ✅ Relationship metadata (progress_weight, order)
- ✅ Cycle prevention
- ✅ Auto-completion propagation

**Service Methods Added:**
```python
# TasksCoreService (and Goals, Habits)
async def get_subtasks(parent_uid: str, depth: int = 1) -> Result[list[Task]]
async def get_parent_tasks(task_uid: str) -> Result[list[Task]]
async def get_task_hierarchy(task_uid: str) -> Result[dict]
async def add_subtask(parent_uid: str, child_uid: str, ...) -> Result[bool]
async def remove_subtask(parent_uid: str, child_uid: str) -> Result[bool]
```

**Files:**
- ✅ `/core/models/relationship_names.py` - HAS_SUBTASK, SUBTASK_OF, HAS_SUBGOAL, HAS_SUBHABIT
- ✅ `/core/services/tasks/tasks_core_service.py` - Hierarchical methods
- ✅ `/docs/patterns/HIERARCHICAL_RELATIONSHIPS_PATTERN.md` - Pattern documentation

---

### Current KU Implementation (Hierarchical UIDs) ❌

**Problem: KU violates ADR-013's own decision!**

**ADR-013 states:** "KU UIDs are FLAT: `ku.{filename}` - Identity is independent of location"

**Reality in code:**
```python
# /core/utils/uid_generator.py:68-110
def generate_knowledge_uid(
    title: str,
    parent_uid: str | None = None,  # ❌ Parent encoded in UID!
    domain_uid: str | None = None   # ❌ Domain encoded in UID!
) -> str:
    parts = [cls.KNOWLEDGE_PREFIX]  # "ku"

    if domain_uid:
        domain_part = domain_uid.replace("dom.", "")
        parts.append(domain_part)  # ❌ Adds domain to UID

    if parent_uid:
        parent_parts = parent_uid.split(".")[1:]  # ❌ Parses parent hierarchy
        parts.extend(parent_parts)  # ❌ Adds parent path to UID

    parts.append(slug)
    return ".".join(parts)  # ❌ Result: "ku.yoga.meditation.basics"
```

**Result:**
```python
# Creating a KU under parent "ku.yoga" with title "Meditation Basics"
uid = generate_knowledge_uid(
    title="Meditation Basics",
    parent_uid="ku.yoga",
    domain_uid="dom.wellness"
)
# Result: "ku.yoga.meditation-basics"  ← HIERARCHICAL!
```

**Parsing Methods Needed:**
```python
# These exist because UIDs are hierarchical
UIDGenerator.extract_parts(uid)  # Parse UID string
UIDGenerator.get_parent_uid(uid)  # Extract parent from UID
UIDGenerator.get_domain_from_uid(uid)  # Extract domain from UID
```

**Problems:**
1. ❌ UID encodes parent path → reorganizing changes UID → breaks references
2. ❌ Cannot have multiple parents (tree structure forced)
3. ❌ Requires string parsing to extract hierarchy
4. ❌ Contradicts ADR-013's stated decision
5. ❌ Inconsistent with Activity domains (flat UIDs)

---

### MOC Implementation (Already Correct!) ✅

**Pattern:** KU + ORGANIZES relationship

```cypher
# MOC is NOT a separate entity - it's a KU with ORGANIZES relationships
CREATE (moc:Curriculum {uid: "ku.yoga-fundamentals", title: "Yoga Fundamentals"})
CREATE (ku1:Curriculum {uid: "ku.meditation", title: "Meditation"})
CREATE (ku2:Curriculum {uid: "ku.breathing", title: "Breathing Techniques"})

# A KU "is" a MOC when it has ORGANIZES relationships
CREATE (moc)-[:ORGANIZES {order: 1}]->(ku1)
CREATE (moc)-[:ORGANIZES {order: 2}]->(ku2)
```

**Key Insight:** MOC already uses the target pattern! 🎉
- Flat UIDs: `ku.meditation` (not `ku.yoga.meditation`)
- Hierarchy via ORGANIZES relationships
- Multiple parents possible: `(ku.ai)-[:ORGANIZES]->(ku.ml)` AND `(ku.data-science)-[:ORGANIZES]->(ku.ml)`

**This is the model we want for ALL KU hierarchy!**

---

### LS Implementation (Partial) ⚠️

**UID Pattern:** CORRECT ✅
```python
# Flat UIDs with random suffix
uid = f"ls:{uuid.uuid4().hex[:12]}"
# Example: "ls:a1b2c3d4e5f6"
```

**Hierarchy Pattern:** CORRECT ✅
```cypher
(lp)-[:HAS_STEP {order: 1}]->(ls)
(ls)-[:REQUIRES_STEP]->(ls)  # Prerequisites
```

**Knowledge Storage:** INCORRECT ❌
```python
# /core/models/ls/ls.py:99-100
class LS:
    primary_knowledge_uids: tuple[str, ...] = ()  # ❌ Should be relationships!
    supporting_knowledge_uids: tuple[str, ...] = ()  # ❌ Should be relationships!
```

**Should be:**
```cypher
(ls)-[:CONTAINS_KNOWLEDGE {type: "primary"}]->(ku)
(ls)-[:CONTAINS_KNOWLEDGE {type: "supporting"}]->(ku)
```

---

## Architecture Comparison Matrix

| Domain | UID Format | Hierarchy Method | Multiple Parents? | Reorganize Safe? | Aligned? |
|--------|-----------|------------------|-------------------|------------------|----------|
| **Task** | `task_abc123` (flat) | `HAS_SUBTASK` edge | ✅ Yes (DAG) | ✅ Yes | ✅ CORRECT |
| **Goal** | `goal_xyz789` (flat) | `HAS_SUBGOAL` edge | ✅ Yes (DAG) | ✅ Yes | ✅ CORRECT |
| **Habit** | `habit_def456` (flat) | `HAS_SUBHABIT` edge | ✅ Yes (DAG) | ✅ Yes | ✅ CORRECT |
| **KU** | `ku.yoga.meditation` (hierarchical) | Encoded in UID | ❌ No (tree) | ❌ UID changes | ❌ **WRONG** |
| **LS** | `ls:abc123` (flat) | `HAS_STEP` edge | ✅ Yes | ✅ Yes | ⚠️ (properties) |
| **LP** | `lp:xyz789` (flat) | `HAS_STEP` edge | ✅ Yes | ✅ Yes | ✅ CORRECT |
| **MOC** | `ku.name` (flat) | `ORGANIZES` edge | ✅ Yes (DAG) | ✅ Yes | ✅ CORRECT |

**Summary:** 5 out of 7 patterns correct. Only KU is fundamentally wrong.

---

## Target Architecture: Universal Pattern

### Core Principle

**"All hierarchy is graph relationships, never UID encoding"**

1. **Flat UIDs** - Identity stable across reorganization
2. **Graph relationships** - Hierarchy flexible via edges
3. **Dots only for display** - Breadcrumbs generated, not stored
4. **One mental model** - Same pattern everywhere

### Universal Relationship Patterns

**Parent-Child Composition (Decomposition):**
```cypher
# Activity Domains
(task)-[:HAS_SUBTASK {progress_weight, order}]->(task)
(goal)-[:HAS_SUBGOAL {progress_weight, order}]->(goal)
(habit)-[:HAS_SUBHABIT {progress_weight, order}]->(habit)

# Curriculum Domains
(ku)-[:ORGANIZES {order}]->(ku)  # MOC pattern - already exists!
(ls)-[:HAS_SUBSTEP {order}]->(ls)  # NEW: LS decomposition
```

**Prerequisites (Sequential Dependencies - orthogonal to parent-child):**
```cypher
(task)-[:REQUIRES_TASK]->(task)
(goal)-[:REQUIRES_GOAL]->(goal)  # NEW
(habit)-[:REQUIRES_HABIT]->(habit)  # NEW
(ku)-[:REQUIRES_KNOWLEDGE]->(ku)  # Already exists
(ls)-[:REQUIRES_STEP]->(ls)  # Already exists
```

**Content Containment:**
```cypher
# Move from properties to relationships
(ls)-[:CONTAINS_KNOWLEDGE {type: "primary"}]->(ku)
(ls)-[:CONTAINS_KNOWLEDGE {type: "supporting"}]->(ku)
```

---

## Critical Decisions Required

### Decision 1: KU UID Format

**Question:** How should KU UIDs be structured?

**Current:** `ku.yoga.meditation.basics` (hierarchical - parent path encoded)

**Option A: Full Underscore Alignment (Activity Pattern)**
```
Current: ku.yoga.meditation.basics
Target:  ku_meditation-basics_a1b2c3d4

Benefits:
- Consistent separator across ALL domains (task_, goal_, ku_)
- Clear signal: no hierarchy in UID
- Random suffix prevents collisions

Costs:
- Large database migration
- UID format changes visible to users
- Breaks existing references
```

**Option B: Flat Dot Names (Keep Dots, Remove Hierarchy)**
```
Current: ku.yoga.meditation.basics (hierarchical path)
Target:  ku.meditation-basics (flat name)

Benefits:
- Smaller UID change
- Dots remain for "readability"
- MOC already uses this pattern

Costs:
- Dots might look hierarchical (confusion)
- Inconsistent with Activity domains (underscore)
```

**Option C: Hybrid (Domain-Appropriate Separators)**
```
Activity: task_abc123, goal_xyz789 (underscore)
Curriculum: ku.meditation, ls:step123 (dots/colons)

Benefits:
- Domain identity via separator
- Less migration for curriculum

Costs:
- Two patterns (violates "One Path Forward")
- Cognitive overhead
```

**Recommendation:** Need user preference. I recommend **Option A** for true unification.

---

### Decision 2: Dot Notation Semantics

**Question:** If KU keeps dots, what do they mean?

**Option A: Dots = Display Only (Never in UIDs)**
```
Storage: ku_meditation_a1b2
Display: "Yoga → Meditation → Basics" (breadcrumb from graph)
Dots only appear in UI, never in database
```

**Option B: Dots = Name Separator (Not Hierarchy)**
```
Storage: ku.meditation-basics (flat name with dot prefix)
Hierarchy: (ku.yoga)-[:ORGANIZES]->(ku.meditation-basics)
Display: "Yoga → Meditation → Basics" (from ORGANIZES edges)
```

**Recommendation:** Option A aligns with "syntax reflects structure" principle.

---

### Decision 3: Migration Strategy

**Question:** When to migrate existing KU UIDs?

**Option A: Immediate (Breaking Change)**
- Migrate all KU UIDs now (hierarchical → flat)
- Downtime required
- Clean break
- Full consistency achieved

**Option B: Gradual (Hybrid Period)**
- New KUs use flat UIDs
- Old KUs keep hierarchical UIDs
- Migrate over time
- Temporary inconsistency

**Option C: Defer**
- Document hierarchical KU UIDs as intentional
- Update ADR-013 to match reality
- Focus on Activity domain consistency only

**Recommendation:** **Option A** if true unification desired. Option B if risk mitigation needed.

---

### Decision 4: LS Knowledge Storage

**Question:** Move LS knowledge from properties to relationships?

**Current:**
```python
class LS:
    primary_knowledge_uids: tuple[str, ...] = ()
    supporting_knowledge_uids: tuple[str, ...] = ()
```

**Target:**
```cypher
(ls)-[:CONTAINS_KNOWLEDGE {type: "primary"}]->(ku)
(ls)-[:CONTAINS_KNOWLEDGE {type: "supporting"}]->(ku)
```

**Benefits:**
- ✅ Consistent with graph-first philosophy
- ✅ Query via graph traversal (not UID list parsing)
- ✅ Supports metadata on relationships

**Costs:**
- ⚠️ Migration needed for existing LS nodes
- ⚠️ Query pattern changes

**Recommendation:** **YES** - this aligns with universal pattern.

---

## Implementation Roadmap

### Phase 1: Decision Making (CURRENT)
- [ ] User chooses KU UID format (Option A/B/C)
- [ ] User chooses dot semantics (if keeping dots)
- [ ] User chooses migration strategy (immediate/gradual/defer)
- [ ] User confirms LS knowledge migration (yes/no)

### Phase 2: KU UID Flattening

**Files to Modify:**

1. **`/core/utils/uid_generator.py`**
   - Remove hierarchical logic from `generate_knowledge_uid()`
   - Delete parsing methods: `extract_parts()`, `get_parent_uid()`, `get_domain_from_uid()`
   - Implement chosen format (underscore or flat dot)

2. **`/core/services/ku/ku_core_service.py`**
   - Remove `parent_uid` and `domain_uid` parameters from create flow
   - Add organization relationship creation
   - Add hierarchical methods (like Tasks)

3. **Database Migration Script** (new file)
   - Identify hierarchical KU UIDs
   - Flatten to chosen format
   - Preserve all relationships
   - Handle collisions

### Phase 3: KU Hierarchical Methods

**Add to `KuCoreService` (mirroring TasksCoreService):**
```python
async def get_subkus(parent_uid: str, depth: int = 1) -> Result[list[Ku]]
async def get_parent_kus(ku_uid: str) -> Result[list[Ku]]
async def get_ku_hierarchy(ku_uid: str) -> Result[dict]
async def organize_ku(parent_uid: str, child_uid: str, order: int = 0) -> Result[bool]
async def unorganize_ku(parent_uid: str, child_uid: str) -> Result[bool]
```

### Phase 4: LS Knowledge Relationship Migration

**Changes:**

1. **Model** (`/core/models/ls/ls.py`)
   - Remove `primary_knowledge_uids` and `supporting_knowledge_uids` properties
   - Document relationship pattern

2. **Service** (`/core/services/ls/ls_core_service.py`)
   - Add relationship methods:
     ```python
     async def add_knowledge_relationship(ls_uid: str, ku_uid: str, type: str) -> Result[bool]
     async def get_contained_knowledge(ls_uid: str, type: str = None) -> Result[list[Ku]]
     ```

3. **Database Migration**
   - Read existing UID properties
   - Create `CONTAINS_KNOWLEDGE` relationships
   - Remove properties from nodes

### Phase 5: Documentation Updates

**Files to Update:**
1. `/docs/decisions/ADR-013-ku-uid-flat-identity.md` - Update implementation to match reality
2. `/docs/patterns/HIERARCHICAL_RELATIONSHIPS_PATTERN.md` - Add curriculum domains
3. `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md` - Update KU hierarchy section
4. `/CLAUDE.md` - Update UID format documentation

**New Documentation:**
5. `/docs/patterns/UNIVERSAL_HIERARCHICAL_PATTERN.md` - Comprehensive pattern guide
6. `/docs/migrations/KU_FLATTENING_MIGRATION_2026-01-30.md` - Migration guide

---

## Benefits of Universal Pattern

### 1. Consistent Mental Model
**Before:** "Tasks use relationships, KUs use UID encoding - which pattern do I use?"
**After:** "All hierarchy is relationships - one pattern everywhere"

### 2. Flexible Reorganization
**Before:**
- Move KU: Change UID → Update all references → Risk breaking
- Move Task: Update relationship edge → UID unchanged → Safe

**After:**
- Move anything: Update relationship edge → UID unchanged → Safe

### 3. Multiple Parents (DAG)
**Before:**
- Tasks: Can have multiple parents (shared subtask) ✅
- KUs: Cannot have multiple parents (tree only) ❌

**After:**
```cypher
# Machine Learning KU in multiple MOCs
(ku.ai-fundamentals)-[:ORGANIZES]->(ku.machine-learning)
(ku.data-science)-[:ORGANIZES]->(ku.machine-learning)
(ku.python-advanced)-[:ORGANIZES]->(ku.machine-learning)
```

### 4. Relationship Metadata
**Before:**
- Tasks: Progress weighting on edges ✅
- KUs: No metadata (hierarchy in UID string) ❌

**After:**
```cypher
(ku.moc)-[:ORGANIZES {
    order: 1,
    importance: "core",
    last_reviewed: datetime(),
    user_notes: "Focus on this first"
}]->(ku.child)
```

### 5. Query Consistency
**Before:**
```python
# Tasks (graph query)
subtasks = await get_related(task_uid, RelationshipName.HAS_SUBTASK)

# KUs (string parsing)
parent_uid = get_parent_uid(ku_uid)  # Parse "ku.yoga.meditation" → "ku.yoga"
```

**After:**
```python
# Everything (graph query)
children = await get_related(entity_uid, relationship_type, direction="outgoing")
```

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| KU UID migration breaks references | Medium | High | Backup database, test migration script |
| LS property removal breaks queries | Low | Medium | Update all queries first, test thoroughly |
| User confusion during transition | Medium | Low | Clear documentation, gradual rollout |
| Performance impact from new queries | Low | Medium | Index ORGANIZES relationships |
| Collision in flattened UIDs | Low | High | Add random suffix, collision detection |

---

## Success Criteria

- [ ] All domains use flat UIDs (no hierarchy encoding)
- [ ] All hierarchy via graph relationships (HAS_SUBTASK, ORGANIZES, etc.)
- [ ] Consistent query patterns across domains
- [ ] Multiple parents possible for all entities (DAG support)
- [ ] Reorganization never changes UIDs
- [ ] No UID string parsing methods remain
- [ ] One mental model documented for all hierarchy
- [ ] All tests passing
- [ ] ADR-013 updated to match implementation

---

## Next Steps

**User decisions needed:**

1. **KU UID Format:** Option A (underscore), B (flat dots), or C (hybrid)?
2. **Dot Semantics:** Display only or name separator?
3. **Migration Timing:** Immediate, gradual, or defer?
4. **LS Knowledge:** Migrate to relationships? (Recommend: YES)

Once decisions are made, we can proceed with implementation phases.

---

## Appendix: Code Examples

### Before (Current KU - Hierarchical)
```python
# UID generation encodes parent
uid = UIDGenerator.generate_knowledge_uid(
    title="Meditation Basics",
    parent_uid="ku.yoga",
    domain_uid="dom.wellness"
)
# Result: "ku.yoga.meditation-basics"

# Reorganizing requires UID change
# If moved to different parent, UID becomes "ku.mindfulness.meditation-basics"
# All references must update!
```

### After (Target KU - Flat + Relationships)
```python
# UID generation - flat, stable
uid = UIDGenerator.generate_knowledge_uid(title="Meditation Basics")
# Result: "ku_meditation-basics_a1b2c3d4"

# Hierarchy via relationship
await ku_service.organize_ku(
    parent_uid="ku_yoga_x7y8z9w0",
    child_uid="ku_meditation-basics_a1b2c3d4",
    order=1
)
# Creates: (parent)-[:ORGANIZES {order: 1}]->(child)

# Reorganizing updates edge only
await ku_service.unorganize_ku(old_parent, child)
await ku_service.organize_ku(new_parent, child)
# UID unchanged! All references intact!
```

### LS Knowledge Migration

**Before:**
```python
# Properties store UID lists
ls = LS(
    uid="ls:abc123",
    primary_knowledge_uids=("ku.python", "ku.functions"),
    supporting_knowledge_uids=("ku.variables",)
)

# Query requires property parsing
primary_kus = await ku_service.get_batch(ls.primary_knowledge_uids)
```

**After:**
```cypher
# Relationships store connections
CREATE (ls:Ls {uid: "ls:abc123"})
CREATE (ls)-[:CONTAINS_KNOWLEDGE {type: "primary"}]->(ku1:Curriculum {uid: "ku.python"})
CREATE (ls)-[:CONTAINS_KNOWLEDGE {type: "primary"}]->(ku2:Curriculum {uid: "ku.functions"})
CREATE (ls)-[:CONTAINS_KNOWLEDGE {type: "supporting"}]->(ku3:Curriculum {uid: "ku.variables"})
```

```python
# Query via graph traversal
primary_kus = await ls_service.get_contained_knowledge(
    ls_uid="ls:abc123",
    type="primary"
)
```
