# Hierarchical Methods Analysis - All Domains
**Date:** 2026-01-30
**Purpose:** Comprehensive analysis of what hierarchical methods need to be added to each domain
**Status:** Analysis Complete - Ready for Implementation

---

## Executive Summary

**Current State:**
- ✅ Tasks: Has 4 hierarchical methods (COMPLETE)
- ✅ KU: Has 5 hierarchical methods (COMPLETE - 2026-01-30)
- ✅ LS: Has 4 knowledge relationship methods (COMPLETE - 2026-01-30)
- ❌ Goals: Missing hierarchical methods
- ❌ Habits: Missing hierarchical methods
- ❌ Events: Missing hierarchical methods
- ❌ Choices: Missing hierarchical methods
- ❌ Principles: Missing hierarchical methods
- ❌ LP: Missing hierarchical methods

**Goal:** Add consistent hierarchical methods to ALL domains following Universal Hierarchical Pattern.

---

## Reference Implementation: TasksCoreService

### Methods in TasksCoreService

Located: `/core/services/tasks/tasks_core_service.py` (lines 556-800+)

**1. `get_subtasks(parent_uid, depth=1)` → `Result[list[Task]]`**
- Get all children of a parent
- Supports multi-level depth (1=direct, 99=all descendants)
- Returns ordered list

**2. `get_parent_task(subtask_uid)` → `Result[Task | None]`**
- Get immediate parent (single level up)
- Returns None if root-level

**3. `get_task_hierarchy(task_uid)` → `Result[dict]`**
- Comprehensive hierarchy context
- Returns: ancestors, current, siblings, children, depth
- Most powerful method for UI display

**4. `create_subtask_relationship(parent_uid, subtask_uid, progress_weight)` → `Result[bool]`**
- Create bidirectional relationship
- Includes cycle detection
- Creates both HAS_SUBTASK and SUBTASK_OF edges

**Total Lines:** ~250 lines of implementation

---

## Domain-by-Domain Analysis

### 1. Goals (HAS_SUBGOAL / SUBGOAL_OF)

**File:** `/core/services/goals/goals_core_service.py`

**Relationship Type:** `HAS_SUBGOAL` / `SUBGOAL_OF`

**Relationship Properties:**
- `progress_weight` (float) - Contribution to parent progress
- `order` (int) - Display order
- `created_at` (datetime)

**Methods Needed:**

```python
async def get_subgoals(parent_uid: str, depth: int = 1) -> Result[list[Goal]]
async def get_parent_goal(subgoal_uid: str) -> Result[Goal | None]
async def get_goal_hierarchy(goal_uid: str) -> Result[dict]
async def create_subgoal_relationship(
    parent_uid: str,
    subgoal_uid: str,
    progress_weight: float = 1.0
) -> Result[bool]
async def remove_subgoal_relationship(
    parent_uid: str,
    subgoal_uid: str
) -> Result[bool]
```

**Use Case:**
- Annual goal → Quarterly goals (4 subgoals)
- Quarterly goal → Monthly milestones
- Career goal → Skill acquisition goals

**Example:**
```python
# Goal: "Career Growth 2026"
#   ├─ Q1: Foundation (40% weight)
#   ├─ Q2: Projects (30% weight)
#   ├─ Q3: Certification (20% weight)
#   └─ Q4: Interview Prep (10% weight)

await goals_service.create_subgoal_relationship(
    parent_uid="goal_career-growth_abc123",
    subgoal_uid="goal_q1-foundation_xyz789",
    progress_weight=0.40
)
```

**Status:** ❌ Not implemented
**Estimated Lines:** 250
**Priority:** HIGH (common use case)

---

### 2. Habits (HAS_SUBHABIT / SUBHABIT_OF)

**File:** `/core/services/habits/habits_core_service.py`

**Relationship Type:** `HAS_SUBHABIT` / `SUBHABIT_OF`

**Relationship Properties:**
- `progress_weight` (float) - Contribution to parent progress
- `order` (int) - Display order in routine
- `created_at` (datetime)

**Methods Needed:**

```python
async def get_subhabits(parent_uid: str, depth: int = 1) -> Result[list[Habit]]
async def get_parent_habit(subhabit_uid: str) -> Result[Habit | None]
async def get_habit_hierarchy(habit_uid: str) -> Result[dict]
async def create_subhabit_relationship(
    parent_uid: str,
    subhabit_uid: str,
    progress_weight: float = 1.0,
    order: int = 0
) -> Result[bool]
async def remove_subhabit_relationship(
    parent_uid: str,
    subhabit_uid: str
) -> Result[bool]
```

**Use Case:**
- Morning routine → Individual habits
- Exercise routine → Warmup, workout, cooldown
- Meditation practice → Posture, breathing, awareness

**Example:**
```python
# Habit: "Morning Routine"
#   ├─ 1. Meditation (10 min)
#   ├─ 2. Exercise (20 min)
#   ├─ 3. Journaling (10 min)
#   └─ 4. Review Goals (5 min)

await habits_service.create_subhabit_relationship(
    parent_uid="habit_morning-routine_abc123",
    subhabit_uid="habit_meditation_xyz789",
    progress_weight=0.25,
    order=1
)
```

**Status:** ❌ Not implemented
**Estimated Lines:** 250
**Priority:** HIGH (routines are critical)

---

### 3. Events (HAS_SUBEVENT / SUBEVENT_OF)

**File:** `/core/services/events/events_core_service.py`

**Relationship Type:** `HAS_SUBEVENT` / `SUBEVENT_OF`

**Relationship Properties:**
- `order` (int) - Sequence in agenda
- `created_at` (datetime)
- Optional: `time_offset` (int) - Minutes from parent start

**Methods Needed:**

```python
async def get_subevents(parent_uid: str, depth: int = 1) -> Result[list[Event]]
async def get_parent_event(subevent_uid: str) -> Result[Event | None]
async def get_event_hierarchy(event_uid: str) -> Result[dict]
async def create_subevent_relationship(
    parent_uid: str,
    subevent_uid: str,
    order: int = 0,
    time_offset: int | None = None
) -> Result[bool]
async def remove_subevent_relationship(
    parent_uid: str,
    subevent_uid: str
) -> Result[bool]
```

**Use Case:**
- Conference → Sessions, workshops, breaks
- Workshop → Segments (intro, exercises, discussion, wrap-up)
- Meeting → Agenda items

**Example:**
```python
# Event: "Python Workshop"
#   ├─ 1. Introduction (15 min, offset=0)
#   ├─ 2. Hands-on Exercise (45 min, offset=15)
#   ├─ 3. Break (10 min, offset=60)
#   └─ 4. Q&A (20 min, offset=70)

await events_service.create_subevent_relationship(
    parent_uid="event_python-workshop_abc123",
    subevent_uid="event_intro_xyz789",
    order=1,
    time_offset=0
)
```

**Status:** ❌ Not implemented
**Estimated Lines:** 250
**Priority:** MEDIUM (useful for complex events)

---

### 4. Choices (HAS_SUBCHOICE / SUBCHOICE_OF)

**File:** `/core/services/choices/choices_core_service.py`

**Relationship Type:** `HAS_SUBCHOICE` / `SUBCHOICE_OF`

**Relationship Properties:**
- `order` (int) - Decision tree order
- `created_at` (datetime)
- Optional: `depends_on_outcome` (string) - Conditional branching

**Methods Needed:**

```python
async def get_subchoices(parent_uid: str, depth: int = 1) -> Result[list[Choice]]
async def get_parent_choice(subchoice_uid: str) -> Result[Choice | None]
async def get_choice_hierarchy(choice_uid: str) -> Result[dict]
async def create_subchoice_relationship(
    parent_uid: str,
    subchoice_uid: str,
    order: int = 0,
    depends_on_outcome: str | None = None
) -> Result[bool]
async def remove_subchoice_relationship(
    parent_uid: str,
    subchoice_uid: str
) -> Result[bool]
```

**Use Case:**
- Career decision → Follow-up decisions
- Life choice → Implementation choices
- Decision trees

**Example:**
```python
# Choice: "Career Path"
#   ├─ If Yes → "Which specialty?" (depends_on_outcome="yes")
#   │   ├─ Backend
#   │   ├─ Frontend
#   │   └─ Full-stack
#   └─ If No → "Alternative paths?" (depends_on_outcome="no")

await choices_service.create_subchoice_relationship(
    parent_uid="choice_career-path_abc123",
    subchoice_uid="choice_specialty_xyz789",
    order=1,
    depends_on_outcome="yes"
)
```

**Status:** ❌ Not implemented
**Estimated Lines:** 250
**Priority:** MEDIUM (decision trees valuable but less common)

---

### 5. Principles (HAS_SUBPRINCIPLE / SUBPRINCIPLE_OF)

**File:** `/core/services/principles/principles_core_service.py`

**Relationship Type:** `HAS_SUBPRINCIPLE` / `SUBPRINCIPLE_OF`

**Relationship Properties:**
- `order` (int) - Display order
- `importance` (string) - "core" | "supporting" | "derived"
- `created_at` (datetime)

**Methods Needed:**

```python
async def get_subprinciples(parent_uid: str, depth: int = 1) -> Result[list[Principle]]
async def get_parent_principle(subprinciple_uid: str) -> Result[Principle | None]
async def get_principle_hierarchy(principle_uid: str) -> Result[dict]
async def create_subprinciple_relationship(
    parent_uid: str,
    subprinciple_uid: str,
    order: int = 0,
    importance: str = "core"
) -> Result[bool]
async def remove_subprinciple_relationship(
    parent_uid: str,
    subprinciple_uid: str
) -> Result[bool]
```

**Use Case:**
- Core value → Supporting principles
- Life philosophy → Derived principles
- Principle frameworks

**Example:**
```python
# Principle: "Integrity"
#   ├─ 1. Honesty (core)
#   ├─ 2. Transparency (core)
#   ├─ 3. Consistency (supporting)
#   └─ 4. Accountability (derived)

await principles_service.create_subprinciple_relationship(
    parent_uid="principle_integrity_abc123",
    subprinciple_uid="principle_honesty_xyz789",
    order=1,
    importance="core"
)
```

**Status:** ❌ Not implemented
**Estimated Lines:** 250
**Priority:** MEDIUM (valuable for philosophy structure)

---

### 6. LP - Learning Paths (HAS_STEP / STEP_OF)

**File:** `/core/services/lp/lp_core_service.py`

**Relationship Type:** `HAS_STEP` / `STEP_OF`

**Relationship Properties:**
- `sequence` (int) - Step order in path
- `order` (int) - Display order
- `created_at` (datetime)

**Methods Needed:**

```python
async def get_steps(path_uid: str, depth: int = 1) -> Result[list[Ls]]
async def get_parent_path(step_uid: str) -> Result[Lp | None]
async def get_path_hierarchy(path_uid: str) -> Result[dict]
async def add_step_to_path(
    path_uid: str,
    step_uid: str,
    sequence: int,
    order: int = 0
) -> Result[bool]
async def remove_step_from_path(
    path_uid: str,
    step_uid: str
) -> Result[bool]
async def reorder_steps(
    path_uid: str,
    step_uids: list[str]
) -> Result[bool]
```

**Use Case:**
- Learning path → Learning steps (sequential)
- Course → Modules → Lessons
- Curriculum structure

**Example:**
```python
# LP: "Python Mastery"
#   ├─ Step 1: Python Basics
#   ├─ Step 2: Data Structures
#   ├─ Step 3: OOP Fundamentals
#   └─ Step 4: Advanced Topics

await lp_service.add_step_to_path(
    path_uid="lp:python-mastery",
    step_uid="ls:python-basics",
    sequence=1,
    order=1
)
```

**Status:** ❌ Not implemented (may have partial implementation)
**Estimated Lines:** 250
**Priority:** HIGH (core curriculum feature)

---

### 7. KU - Knowledge Units (ORGANIZES)

**File:** `/core/services/ku/ku_core_service.py`

**Relationship Type:** `ORGANIZES` (unidirectional - parent organizes child)

**Relationship Properties:**
- `order` (int) - Display order
- `importance` (string) - "core" | "supporting" | "reference"
- `created_at` (datetime)
- `updated_at` (datetime)

**Methods Already Implemented:** ✅
```python
async def organize_ku(parent_uid, child_uid, order, importance) -> Result[bool]
async def unorganize_ku(parent_uid, child_uid) -> Result[bool]
async def get_subkus(parent_uid, depth) -> Result[list[KnowledgeUnit]]
async def get_parent_kus(ku_uid) -> Result[list[KnowledgeUnit]]
async def get_ku_hierarchy(ku_uid) -> Result[dict]
```

**Status:** ✅ COMPLETE (2026-01-30)
**Lines:** 280
**Priority:** N/A (already done)

---

### 8. LS - Learning Steps (CONTAINS_KNOWLEDGE)

**File:** `/core/services/ls/ls_core_service.py`

**Relationship Type:** `CONTAINS_KNOWLEDGE`

**Relationship Properties:**
- `type` (string) - "primary" | "supporting"
- `created_at` (datetime)
- `updated_at` (datetime)

**Methods Already Implemented:** ✅
```python
async def add_knowledge_relationship(ls_uid, ku_uid, type) -> Result[bool]
async def get_contained_knowledge(ls_uid, type) -> Result[list[dict]]
async def remove_knowledge_relationship(ls_uid, ku_uid) -> Result[bool]
async def get_knowledge_summary(ls_uid) -> Result[dict]
```

**Status:** ✅ COMPLETE (2026-01-30)
**Lines:** 250
**Priority:** N/A (already done)

---

### 9. MOC - Map of Content (KU + ORGANIZES)

**Pattern:** MOC is not a separate entity - it's a KU with outgoing ORGANIZES relationships.

**Implementation:** Same as KU above (already complete)

**Status:** ✅ COMPLETE (emergent from KU implementation)
**Priority:** N/A (inherent in KU)

---

## Comparison Table

### All Domains - Hierarchical Methods

| Domain | Relationship | Parent Method | Child Method | Hierarchy Method | Create Method | Remove Method | Status |
|--------|-------------|---------------|--------------|------------------|---------------|---------------|--------|
| **Task** | `HAS_SUBTASK` | `get_subtasks()` | `get_parent_task()` | `get_task_hierarchy()` | `create_subtask_relationship()` | ✅ | ✅ DONE |
| **Goal** | `HAS_SUBGOAL` | `get_subgoals()` | `get_parent_goal()` | `get_goal_hierarchy()` | `create_subgoal_relationship()` | ✅ | ❌ TODO |
| **Habit** | `HAS_SUBHABIT` | `get_subhabits()` | `get_parent_habit()` | `get_habit_hierarchy()` | `create_subhabit_relationship()` | ✅ | ❌ TODO |
| **Event** | `HAS_SUBEVENT` | `get_subevents()` | `get_parent_event()` | `get_event_hierarchy()` | `create_subevent_relationship()` | ✅ | ❌ TODO |
| **Choice** | `HAS_SUBCHOICE` | `get_subchoices()` | `get_parent_choice()` | `get_choice_hierarchy()` | `create_subchoice_relationship()` | ✅ | ❌ TODO |
| **Principle** | `HAS_SUBPRINCIPLE` | `get_subprinciples()` | `get_parent_principle()` | `get_principle_hierarchy()` | `create_subprinciple_relationship()` | ✅ | ❌ TODO |
| **KU** | `ORGANIZES` | `get_subkus()` | `get_parent_kus()` | `get_ku_hierarchy()` | `organize_ku()` | `unorganize_ku()` | ✅ DONE |
| **LS** | `CONTAINS_KNOWLEDGE` | `get_contained_knowledge()` | N/A | `get_knowledge_summary()` | `add_knowledge_relationship()` | `remove_knowledge_relationship()` | ✅ DONE |
| **LP** | `HAS_STEP` | `get_steps()` | `get_parent_path()` | `get_path_hierarchy()` | `add_step_to_path()` | `remove_step_from_path()` | ❌ TODO |

---

## Code Pattern Template

### Generic Template (Activity Domains)

All activity domains (Goals, Habits, Events, Choices, Principles) follow this pattern:

```python
# ========================================================================
# HIERARCHICAL RELATIONSHIPS (2026-01-30 - Universal Hierarchical Pattern)
# ========================================================================

@with_error_handling("get_sub{entities}", error_type="database", uid_param="parent_uid")
async def get_sub{entities}(self, parent_uid: str, depth: int = 1) -> Result[list[{Entity}]]:
    """
    Get all sub-{entities} of a parent {entity}.

    Args:
        parent_uid: Parent {entity} UID
        depth: How many levels deep (1=direct children, 2=children+grandchildren, etc.)

    Returns:
        Result containing list of sub-{entities} ordered by created_at

    Example:
        # Get direct children
        sub{entities} = await service.get_sub{entities}("{entity}_abc123")

        # Get all descendants
        all = await service.get_sub{entities}("{entity}_abc123", depth=99)
    """
    query = f"""
    MATCH (parent:{EntityLabel} {{uid: $parent_uid}})
    MATCH (parent)-[:HAS_SUB{ENTITY_UPPER}*1..{depth}]->(sub{entity}:{EntityLabel})
    RETURN sub{entity}
    ORDER BY sub{entity}.created_at
    """

    result = await self.backend.driver.execute_query(query, parent_uid=parent_uid)

    if not result.records:
        return Result.ok([])

    # Convert to domain models
    {entities} = []
    for record in result.records:
        {entity}_data = dict(record["sub{entity}"])
        {entity} = self._to_domain_model({entity}_data, {Entity}DTO, {Entity})
        {entities}.append({entity})

    return Result.ok({entities})

@with_error_handling("get_parent_{entity}", error_type="database", uid_param="sub{entity}_uid")
async def get_parent_{entity}(self, sub{entity}_uid: str) -> Result[{Entity} | None]:
    """
    Get immediate parent of a sub-{entity} (if any).

    Args:
        sub{entity}_uid: Sub-{entity} UID

    Returns:
        Result containing parent {Entity} or None if root-level {entity}
    """
    query = """
    MATCH (sub{entity}:{EntityLabel} {uid: $sub{entity}_uid})
    MATCH (parent:{EntityLabel})-[:HAS_SUB{ENTITY_UPPER}]->(sub{entity})
    RETURN parent
    LIMIT 1
    """

    result = await self.backend.driver.execute_query(query, sub{entity}_uid=sub{entity}_uid)

    if not result.records:
        return Result.ok(None)

    parent_data = dict(result.records[0]["parent"])
    parent = self._to_domain_model(parent_data, {Entity}DTO, {Entity})
    return Result.ok(parent)

@with_error_handling("get_{entity}_hierarchy", error_type="database", uid_param="{entity}_uid")
async def get_{entity}_hierarchy(self, {entity}_uid: str) -> Result[dict[str, Any]]:
    """
    Get full hierarchy context: ancestors, siblings, children.

    Args:
        {entity}_uid: {Entity} UID to get context for

    Returns:
        Result containing hierarchy dict with keys:
        - ancestors: list[{Entity}] (root to immediate parent)
        - current: {Entity}
        - siblings: list[{Entity}] (other children of same parent)
        - children: list[{Entity}] (immediate children)
        - depth: int (how deep in hierarchy, 0=root)

    Example:
        hierarchy = await service.get_{entity}_hierarchy("{entity}_xyz789")
        # {
        #   "ancestors": [root_{entity}, parent_{entity}],
        #   "current": {entity}_xyz789,
        #   "siblings": [sibling1, sibling2],
        #   "children": [child1, child2],
        #   "depth": 2
        # }
    """
    # Get ancestors
    ancestors_query = """
    MATCH path = (root:{EntityLabel})-[:HAS_SUB{ENTITY_UPPER}*]->(current:{EntityLabel} {uid: ${entity}_uid})
    WHERE NOT EXISTS((root)<-[:HAS_SUB{ENTITY_UPPER}]-())
    RETURN nodes(path) as ancestors
    """

    # Get siblings
    siblings_query = """
    MATCH (current:{EntityLabel} {uid: ${entity}_uid})
    OPTIONAL MATCH (parent:{EntityLabel})-[:HAS_SUB{ENTITY_UPPER}]->(current)
    OPTIONAL MATCH (parent)-[:HAS_SUB{ENTITY_UPPER}]->(sibling:{EntityLabel})
    WHERE sibling.uid <> ${entity}_uid
    RETURN collect(sibling) as siblings
    """

    # Get children
    children_query = """
    MATCH (current:{EntityLabel} {uid: ${entity}_uid})
    OPTIONAL MATCH (current)-[:HAS_SUB{ENTITY_UPPER}]->(child:{EntityLabel})
    RETURN collect(child) as children
    """

    # Execute all queries
    current_result = await self.backend.get({entity}_uid)
    if current_result.is_error:
        return Result.fail(current_result)

    current_{entity} = self._to_domain_model(current_result.value, {Entity}DTO, {Entity})

    ancestors_result = await self.backend.driver.execute_query(
        ancestors_query, {entity}_uid={entity}_uid
    )
    siblings_result = await self.backend.driver.execute_query(
        siblings_query, {entity}_uid={entity}_uid
    )
    children_result = await self.backend.driver.execute_query(
        children_query, {entity}_uid={entity}_uid
    )

    # Process ancestors
    ancestors = []
    if ancestors_result.records and ancestors_result.records[0]["ancestors"]:
        for node in ancestors_result.records[0]["ancestors"][:-1]:  # Exclude current
            {entity}_data = dict(node)
            ancestors.append(self._to_domain_model({entity}_data, {Entity}DTO, {Entity}))

    # Process siblings
    siblings = []
    if siblings_result.records and siblings_result.records[0]["siblings"]:
        for node in siblings_result.records[0]["siblings"]:
            if node:  # Skip None values
                {entity}_data = dict(node)
                siblings.append(self._to_domain_model({entity}_data, {Entity}DTO, {Entity}))

    # Process children
    children = []
    if children_result.records and children_result.records[0]["children"]:
        for node in children_result.records[0]["children"]:
            if node:  # Skip None values
                {entity}_data = dict(node)
                children.append(self._to_domain_model({entity}_data, {Entity}DTO, {Entity}))

    return Result.ok(
        {
            "ancestors": ancestors,
            "current": current_{entity},
            "siblings": siblings,
            "children": children,
            "depth": len(ancestors),
        }
    )

async def create_sub{entity}_relationship(
    self, parent_uid: str, sub{entity}_uid: str, progress_weight: float = 1.0
) -> Result[bool]:
    """
    Create bidirectional parent-child relationship.

    Args:
        parent_uid: Parent {entity} UID
        sub{entity}_uid: Sub-{entity} UID
        progress_weight: How much this sub{entity} contributes to parent progress (default: 1.0)

    Returns:
        Result indicating success

    Note:
        Creates both HAS_SUB{ENTITY_UPPER} (parent→child) and SUB{ENTITY_UPPER}_OF (child→parent)
        for efficient bidirectional queries.
    """
    # Validate no cycle (can't make parent a child of its descendant)
    cycle_check = await self._would_create_cycle(parent_uid, sub{entity}_uid)
    if cycle_check:
        return Result.fail(
            Errors.validation(
                f"Cannot create sub{entity} relationship: would create cycle "
                f"({sub{entity}_uid} is ancestor of {parent_uid})"
            )
        )

    query = """
    MATCH (parent:{EntityLabel} {uid: $parent_uid})
    MATCH (sub{entity}:{EntityLabel} {uid: $sub{entity}_uid})

    CREATE (parent)-[:HAS_SUB{ENTITY_UPPER} {
        progress_weight: $progress_weight,
        created_at: datetime()
    }]->(sub{entity})

    CREATE (sub{entity})-[:SUB{ENTITY_UPPER}_OF {
        created_at: datetime()
    }]->(parent)

    RETURN true as success
    """

    result = await self.backend.driver.execute_query(
        query,
        parent_uid=parent_uid,
        sub{entity}_uid=sub{entity}_uid,
        progress_weight=progress_weight
    )

    success = len(result.records) > 0 and result.records[0].get("success", False)

    if success:
        self.logger.info(
            f"Created HAS_SUB{ENTITY_UPPER}: {parent_uid} -> {sub{entity}_uid} "
            f"(weight={progress_weight})"
        )

    return Result.ok(success)

async def remove_sub{entity}_relationship(
    self, parent_uid: str, sub{entity}_uid: str
) -> Result[bool]:
    """
    Remove sub{entity} relationship.

    Args:
        parent_uid: Parent {entity} UID
        sub{entity}_uid: Sub{entity} UID

    Returns:
        Result[bool] - True if removed successfully
    """
    query = """
    MATCH (parent:{EntityLabel} {uid: $parent_uid})
    MATCH (sub{entity}:{EntityLabel} {uid: $sub{entity}_uid})
    MATCH (parent)-[r1:HAS_SUB{ENTITY_UPPER}]->(sub{entity})
    MATCH (sub{entity})-[r2:SUB{ENTITY_UPPER}_OF]->(parent)
    DELETE r1, r2
    RETURN count(r1) as deleted
    """

    result = await self.backend.driver.execute_query(
        query,
        parent_uid=parent_uid,
        sub{entity}_uid=sub{entity}_uid
    )

    deleted = result.records[0]["deleted"] if result.records else 0
    success = deleted > 0

    if success:
        self.logger.info(f"Removed HAS_SUB{ENTITY_UPPER}: {parent_uid} -> {sub{entity}_uid}")
    else:
        self.logger.warning(
            f"No HAS_SUB{ENTITY_UPPER} relationship found: {parent_uid} -> {sub{entity}_uid}"
        )

    return Result.ok(success)

async def _would_create_cycle(self, parent_uid: str, child_uid: str) -> bool:
    """
    Check if adding child to parent would create a cycle.

    Returns:
        True if cycle would be created, False otherwise
    """
    query = """
    MATCH (child:{EntityLabel} {uid: $child_uid})
    MATCH (parent:{EntityLabel} {uid: $parent_uid})
    RETURN EXISTS((child)-[:HAS_SUB{ENTITY_UPPER}*]->(parent)) as would_cycle
    """

    result = await self.backend.driver.execute_query(
        query,
        parent_uid=parent_uid,
        child_uid=child_uid
    )

    if result.records:
        return result.records[0]["would_cycle"]

    return False
```

---

## Variable Substitutions per Domain

### Goals

```python
{entity} = "goal"
{Entity} = "Goal"
{ENTITY_UPPER} = "GOAL"
{EntityLabel} = "Goal"
{entities} = "goals"
```

### Habits

```python
{entity} = "habit"
{Entity} = "Habit"
{ENTITY_UPPER} = "HABIT"
{EntityLabel} = "Habit"
{entities} = "habits"
```

### Events

```python
{entity} = "event"
{Entity} = "Event"
{ENTITY_UPPER} = "EVENT"
{EntityLabel} = "Event"
{entities} = "events"
```

### Choices

```python
{entity} = "choice"
{Entity} = "Choice"
{ENTITY_UPPER} = "CHOICE"
{EntityLabel} = "Choice"
{entities} = "choices"
```

### Principles

```python
{entity} = "principle"
{Entity} = "Principle"
{ENTITY_UPPER} = "PRINCIPLE"
{EntityLabel} = "Principle"
{entities} = "principles"
```

---

## Implementation Estimates

### Per Domain Estimates

| Domain | Methods | Lines | Complexity | Estimated Time |
|--------|---------|-------|------------|----------------|
| Goals | 5 | 250 | Low (copy/paste + rename) | 30 min |
| Habits | 5 | 250 | Low (copy/paste + rename) | 30 min |
| Events | 5 | 250 | Low (copy/paste + rename) | 30 min |
| Choices | 5 | 250 | Medium (conditional logic) | 45 min |
| Principles | 5 | 250 | Low (copy/paste + rename) | 30 min |
| LP | 6 | 280 | Medium (sequence handling) | 45 min |

**Total:** ~3.5 hours of implementation

---

## Risks & Considerations

### 1. Neo4j Relationship Names

**Risk:** Relationship names must match exactly what's in the database.

**Mitigation:**
- Check existing relationships first
- Use `RelationshipName` enum where available
- Verify with database query before implementing

### 2. Domain Model Conversion

**Risk:** `_to_domain_model()` pattern may differ per service.

**Mitigation:**
- Check existing methods in each service
- Use consistent pattern from Tasks as reference
- Test conversion logic

### 3. Progress Weight Logic

**Risk:** Not all domains use progress_weight.

**Mitigation:**
- Goals, Habits, Tasks: Use progress_weight ✅
- Events: Use order + time_offset instead
- Choices: Use order + depends_on_outcome
- Principles: Use order + importance
- LP: Use sequence + order

### 4. Cycle Detection

**Risk:** Cycle detection query may need optimization.

**Mitigation:**
- Use same pattern as Tasks (proven to work)
- Add indexes on UID if needed
- Consider max depth limit

---

## Testing Strategy

### Unit Tests Needed (Per Domain)

```python
# test_{domain}_hierarchical.py

async def test_create_relationship():
    """Test creating parent-child relationship"""
    pass

async def test_get_children():
    """Test getting all children"""
    pass

async def test_get_children_with_depth():
    """Test multi-level depth"""
    pass

async def test_get_parent():
    """Test getting parent"""
    pass

async def test_get_hierarchy():
    """Test full hierarchy context"""
    pass

async def test_cycle_prevention():
    """Test that cycles are prevented"""
    pass

async def test_remove_relationship():
    """Test removing relationship"""
    pass

async def test_multiple_children():
    """Test parent with multiple children"""
    pass

async def test_orphan_entity():
    """Test entity with no parent (root)"""
    pass
```

**Total Tests per Domain:** 9 tests
**Total Tests Overall:** 54 tests (6 domains × 9 tests)

---

## Implementation Plan

### Phase 1: Activity Domains (HIGH PRIORITY)

**Order:** Goals → Habits → Events → Choices → Principles

**Reason:**
- Most commonly used
- Similar patterns (copy/paste friendly)
- High user value

**Duration:** 2.5 hours

---

### Phase 2: Curriculum Domains

**Order:** LP only (KU and LS already done)

**Duration:** 45 minutes

---

### Phase 3: Documentation

**Tasks:**
- Update UNIVERSAL_HIERARCHICAL_PATTERN.md with all domains
- Create migration completion document
- Update CLAUDE.md if needed

**Duration:** 30 minutes

---

### Phase 4: Testing (Optional but Recommended)

**Tasks:**
- Create unit tests for each domain
- Integration tests for cross-domain hierarchies

**Duration:** 3-4 hours

---

## Success Criteria

- [ ] Goals: 5 hierarchical methods added
- [ ] Habits: 5 hierarchical methods added
- [ ] Events: 5 hierarchical methods added
- [ ] Choices: 5 hierarchical methods added
- [ ] Principles: 5 hierarchical methods added
- [ ] LP: 6 step management methods added
- [ ] All methods follow Universal Hierarchical Pattern
- [ ] All methods include cycle detection
- [ ] All methods return Result[T]
- [ ] All methods have comprehensive docstrings
- [ ] All code passes linting (no SKUEL violations)
- [ ] Documentation updated

---

## Files to Modify

### Service Files (6)

1. `/core/services/goals/goals_core_service.py` - Add 5 methods
2. `/core/services/habits/habits_core_service.py` - Add 5 methods
3. `/core/services/events/events_core_service.py` - Add 5 methods
4. `/core/services/choices/choices_core_service.py` - Add 5 methods
5. `/core/services/principles/principles_core_service.py` - Add 5 methods
6. `/core/services/lp/lp_core_service.py` - Add 6 methods

### Documentation Files (3)

1. `/docs/patterns/UNIVERSAL_HIERARCHICAL_PATTERN.md` - Add all domains section
2. `/docs/migrations/ACTIVITY_HIERARCHICAL_METHODS_COMPLETE_2026-01-30.md` - New completion doc
3. `/CLAUDE.md` - Update if needed

---

## Next Steps

1. **Review this analysis** - Confirm approach is correct
2. **Start with Goals** - Easiest domain to validate pattern
3. **Iterate through domains** - Goals → Habits → Events → Choices → Principles → LP
4. **Update documentation** - Once all domains complete
5. **Create tests** - Optional but recommended

---

## Appendix: Example Implementation (Goals)

### Complete Goals Implementation

```python
# /core/services/goals/goals_core_service.py

# Add after existing methods, before end of class

    # ========================================================================
    # HIERARCHICAL RELATIONSHIPS (2026-01-30 - Universal Hierarchical Pattern)
    # ========================================================================

    @with_error_handling("get_subgoals", error_type="database", uid_param="parent_uid")
    async def get_subgoals(self, parent_uid: str, depth: int = 1) -> Result[list[Goal]]:
        """
        Get all subgoals of a parent goal.

        Args:
            parent_uid: Parent goal UID
            depth: How many levels deep (1=direct children, 2=children+grandchildren, etc.)

        Returns:
            Result containing list of subgoals ordered by created_at

        Example:
            # Get direct children (quarterly goals)
            subgoals = await service.get_subgoals("goal_annual-plan_abc123")

            # Get all descendants (quarterly + monthly)
            all = await service.get_subgoals("goal_annual-plan_abc123", depth=99)
        """
        query = f"""
        MATCH (parent:Goal {{uid: $parent_uid}})
        MATCH (parent)-[:HAS_SUBGOAL*1..{depth}]->(subgoal:Goal)
        RETURN subgoal
        ORDER BY subgoal.created_at
        """

        result = await self.backend.driver.execute_query(query, parent_uid=parent_uid)

        if not result.records:
            return Result.ok([])

        # Convert to Goal models
        goals = []
        for record in result.records:
            goal_data = dict(record["subgoal"])
            goal = self._to_domain_model(goal_data, GoalDTO, Goal)
            goals.append(goal)

        return Result.ok(goals)

    @with_error_handling("get_parent_goal", error_type="database", uid_param="subgoal_uid")
    async def get_parent_goal(self, subgoal_uid: str) -> Result[Goal | None]:
        """
        Get immediate parent of a subgoal (if any).

        Args:
            subgoal_uid: Subgoal UID

        Returns:
            Result containing parent Goal or None if root-level goal
        """
        query = """
        MATCH (subgoal:Goal {uid: $subgoal_uid})
        MATCH (parent:Goal)-[:HAS_SUBGOAL]->(subgoal)
        RETURN parent
        LIMIT 1
        """

        result = await self.backend.driver.execute_query(query, subgoal_uid=subgoal_uid)

        if not result.records:
            return Result.ok(None)

        parent_data = dict(result.records[0]["parent"])
        parent = self._to_domain_model(parent_data, GoalDTO, Goal)
        return Result.ok(parent)

    @with_error_handling("get_goal_hierarchy", error_type="database", uid_param="goal_uid")
    async def get_goal_hierarchy(self, goal_uid: str) -> Result[dict[str, Any]]:
        """
        Get full hierarchy context: ancestors, siblings, children.

        Args:
            goal_uid: Goal UID to get context for

        Returns:
            Result containing hierarchy dict with keys:
            - ancestors: list[Goal] (root to immediate parent)
            - current: Goal
            - siblings: list[Goal] (other children of same parent)
            - children: list[Goal] (immediate children)
            - depth: int (how deep in hierarchy, 0=root)

        Example:
            hierarchy = await service.get_goal_hierarchy("goal_q2-projects_xyz789")
            # {
            #   "ancestors": [annual_goal],
            #   "current": q2_projects_goal,
            #   "siblings": [q1_goal, q3_goal, q4_goal],
            #   "children": [project1_goal, project2_goal],
            #   "depth": 1
            # }
        """
        # Get ancestors
        ancestors_query = """
        MATCH path = (root:Goal)-[:HAS_SUBGOAL*]->(current:Goal {uid: $goal_uid})
        WHERE NOT EXISTS((root)<-[:HAS_SUBGOAL]-())
        RETURN nodes(path) as ancestors
        """

        # Get siblings
        siblings_query = """
        MATCH (current:Goal {uid: $goal_uid})
        OPTIONAL MATCH (parent:Goal)-[:HAS_SUBGOAL]->(current)
        OPTIONAL MATCH (parent)-[:HAS_SUBGOAL]->(sibling:Goal)
        WHERE sibling.uid <> $goal_uid
        RETURN collect(sibling) as siblings
        """

        # Get children
        children_query = """
        MATCH (current:Goal {uid: $goal_uid})
        OPTIONAL MATCH (current)-[:HAS_SUBGOAL]->(child:Goal)
        RETURN collect(child) as children
        """

        # Execute all queries
        current_result = await self.backend.get(goal_uid)
        if current_result.is_error:
            return Result.fail(current_result)

        current_goal = self._to_domain_model(current_result.value, GoalDTO, Goal)

        ancestors_result = await self.backend.driver.execute_query(
            ancestors_query, goal_uid=goal_uid
        )
        siblings_result = await self.backend.driver.execute_query(
            siblings_query, goal_uid=goal_uid
        )
        children_result = await self.backend.driver.execute_query(
            children_query, goal_uid=goal_uid
        )

        # Process ancestors
        ancestors = []
        if ancestors_result.records and ancestors_result.records[0]["ancestors"]:
            for node in ancestors_result.records[0]["ancestors"][:-1]:  # Exclude current
                goal_data = dict(node)
                ancestors.append(self._to_domain_model(goal_data, GoalDTO, Goal))

        # Process siblings
        siblings = []
        if siblings_result.records and siblings_result.records[0]["siblings"]:
            for node in siblings_result.records[0]["siblings"]:
                if node:  # Skip None values
                    goal_data = dict(node)
                    siblings.append(self._to_domain_model(goal_data, GoalDTO, Goal))

        # Process children
        children = []
        if children_result.records and children_result.records[0]["children"]:
            for node in children_result.records[0]["children"]:
                if node:  # Skip None values
                    goal_data = dict(node)
                    children.append(self._to_domain_model(goal_data, GoalDTO, Goal))

        return Result.ok(
            {
                "ancestors": ancestors,
                "current": current_goal,
                "siblings": siblings,
                "children": children,
                "depth": len(ancestors),
            }
        )

    async def create_subgoal_relationship(
        self, parent_uid: str, subgoal_uid: str, progress_weight: float = 1.0
    ) -> Result[bool]:
        """
        Create bidirectional parent-child relationship.

        Args:
            parent_uid: Parent goal UID
            subgoal_uid: Subgoal UID
            progress_weight: How much this subgoal contributes to parent progress (default: 1.0)

        Returns:
            Result indicating success

        Note:
            Creates both HAS_SUBGOAL (parent→child) and SUBGOAL_OF (child→parent)
            for efficient bidirectional queries.

        Example:
            # Create annual → quarterly relationship
            await service.create_subgoal_relationship(
                parent_uid="goal_career-2026_abc123",
                subgoal_uid="goal_q1-foundation_xyz789",
                progress_weight=0.40  # Q1 is 40% of annual goal
            )
        """
        # Validate no cycle (can't make parent a child of its descendant)
        cycle_check = await self._would_create_cycle(parent_uid, subgoal_uid)
        if cycle_check:
            return Result.fail(
                Errors.validation(
                    f"Cannot create subgoal relationship: would create cycle "
                    f"({subgoal_uid} is ancestor of {parent_uid})"
                )
            )

        query = """
        MATCH (parent:Goal {uid: $parent_uid})
        MATCH (subgoal:Goal {uid: $subgoal_uid})

        CREATE (parent)-[:HAS_SUBGOAL {
            progress_weight: $progress_weight,
            created_at: datetime()
        }]->(subgoal)

        CREATE (subgoal)-[:SUBGOAL_OF {
            created_at: datetime()
        }]->(parent)

        RETURN true as success
        """

        result = await self.backend.driver.execute_query(
            query,
            parent_uid=parent_uid,
            subgoal_uid=subgoal_uid,
            progress_weight=progress_weight
        )

        success = len(result.records) > 0 and result.records[0].get("success", False)

        if success:
            self.logger.info(
                f"Created HAS_SUBGOAL: {parent_uid} -> {subgoal_uid} "
                f"(weight={progress_weight})"
            )

        return Result.ok(success)

    async def remove_subgoal_relationship(
        self, parent_uid: str, subgoal_uid: str
    ) -> Result[bool]:
        """
        Remove subgoal relationship.

        Args:
            parent_uid: Parent goal UID
            subgoal_uid: Subgoal UID

        Returns:
            Result[bool] - True if removed successfully
        """
        query = """
        MATCH (parent:Goal {uid: $parent_uid})
        MATCH (subgoal:Goal {uid: $subgoal_uid})
        MATCH (parent)-[r1:HAS_SUBGOAL]->(subgoal)
        MATCH (subgoal)-[r2:SUBGOAL_OF]->(parent)
        DELETE r1, r2
        RETURN count(r1) as deleted
        """

        result = await self.backend.driver.execute_query(
            query,
            parent_uid=parent_uid,
            subgoal_uid=subgoal_uid
        )

        deleted = result.records[0]["deleted"] if result.records else 0
        success = deleted > 0

        if success:
            self.logger.info(f"Removed HAS_SUBGOAL: {parent_uid} -> {subgoal_uid}")
        else:
            self.logger.warning(
                f"No HAS_SUBGOAL relationship found: {parent_uid} -> {subgoal_uid}"
            )

        return Result.ok(success)

    async def _would_create_cycle(self, parent_uid: str, child_uid: str) -> bool:
        """
        Check if adding child to parent would create a cycle.

        Returns:
            True if cycle would be created, False otherwise
        """
        query = """
        MATCH (child:Goal {uid: $child_uid})
        MATCH (parent:Goal {uid: $parent_uid})
        RETURN EXISTS((child)-[:HAS_SUBGOAL*]->(parent)) as would_cycle
        """

        result = await self.backend.driver.execute_query(
            query,
            parent_uid=parent_uid,
            child_uid=child_uid
        )

        if result.records:
            return result.records[0]["would_cycle"]

        return False
```

---

**End of Analysis**

**Status:** Ready for implementation
**Next Step:** Begin with Goals domain (highest priority)
**Estimated Total Duration:** 3.5 hours implementation + 30 min docs = 4 hours
