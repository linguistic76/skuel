---
title: Domain Relationships Pattern (Graph-Native Architecture)
updated: 2026-01-19
category: patterns
related_skills:
- neo4j-cypher-patterns
related_docs:
- /docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md
- /docs/patterns/BACKEND_OPERATIONS_ISP.md
- /docs/patterns/TESTING_PATTERNS.md
- /docs/decisions/ADR-029
---

# Domain Relationships Pattern (Graph-Native Architecture)

**Last Updated:** 2026-01-19
**Status:** ✅ Active Pattern - Used Across ALL Activity & Curriculum Domains
**One Path Forward:** UnifiedRelationshipService for ALL Activity Domain relationship queries (ADR-029)
**Applies To:** Tasks, Goals, Events, Habits, LearningSteps, Choices, Principles, LearningPaths, KnowledgeUnit (9 domains)
**Special:** KnowledgeUnit uses hybrid pattern (simple UIDs + optional rich semantic context)

**January 19, 2026 Update:** Added bidirectional relationships across all 6 Activity Domains. Tasks +3 fields (events, choices, life path). Goals +2 fields (milestones, life path). Events +6 fields (attendees, goals, life path, choices, principles). Habits corrected to 5 fields (goals, knowledge, life path, choices). Choices +6 fields (tasks, life path, habits, events). Principles +5 fields (choices, tasks, life path, events).

**January 8, 2026 Update:** GraphNative services removed from Tasks/Goals (ADR-029). UnifiedRelationshipService is now THE single path for all Activity Domain relationship queries.

**January 2026 Update:** Added documentation for auto-created user relationships and cascade deletion requirements. See section "Auto-Created User Relationships".

**December 2025 Update:** Activity Domains (6) now use `UnifiedRelationshipService` with domain configs instead of separate relationship services per domain. See `/docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md`.
## Related Skills

For implementation guidance, see:
- [@neo4j-cypher-patterns](../../.claude/skills/neo4j-cypher-patterns/SKILL.md)


## One Path Forward (ADR-029)

**January 8, 2026:** Tasks and Goals GraphNative services deleted (1,435 lines).

**Architecture Alignment:**
- **UnifiedRelationshipService** is THE single service for Activity Domain relationships
- All 6 Activity Domains (Tasks, Goals, Habits, Events, Choices, Principles) now use identical architecture
- GraphNative services were intermediate refactoring artifacts - now removed

**Decision Tree for Relationship Queries:**
```
Need relationship data?
├─ Activity Domains → service.relationships.get_related_uids("knowledge", uid)
│  └─ Via UnifiedRelationshipService (THE path)
│
├─ Curriculum Domains → service.relationships.get_prerequisites(uid)
│  └─ Via direct driver pattern (domain-specific services)
│
└─ Cross-domain context → service.relationships.get_cross_domain_context_typed(uid)
   └─ Via UnifiedRelationshipService with path-aware entities
```

**Result:** Zero alternative paths - one clear way to access relationship data per domain type.

**See:** [ADR-029](../decisions/ADR-029-graphnative-service-removal.md) for complete removal rationale.

---

## 🎯 Pattern Overview

**The Problem:**
Relationship list fields (like `subtask_uids`, `prerequisite_knowledge_uids`) were removed from domain models during graph-native migration. These relationships now live as Neo4j edges, not serialized lists.

**The Solution:**
Each domain has a `{Domain}Relationships` helper class that fetches all relationship data in parallel from the graph.

**Pattern Name:** Domain Relationships Fetch Pattern

---

## 📋 Domains Using This Pattern

### Activity Domains (6) - via UnifiedRelationshipService

As of December 2025, the 6 Activity Domains use `UnifiedRelationshipService` with domain-specific configs:

| Domain | Relationship Class | Relationship Count | Config |
|--------|-------------------|-------------------|---------|
| **Tasks** | `TaskRelationships` | 12 relationships | `TASKS_CONFIG` |
| **Goals** | `GoalRelationships` | 11 relationships | `GOALS_CONFIG` |
| **Habits** | `HabitRelationships` | 5 relationships | `HABITS_CONFIG` |
| **Events** | `EventRelationships` | 9 relationships | `EVENTS_CONFIG` |
| **Choices** | `ChoiceRelationships` | 10 relationships | `CHOICES_CONFIG` |
| **Principles** | `PrincipleRelationships` | 9 relationships | `PRINCIPLES_CONFIG` |

**See:** `/docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md` for the unified service pattern.

### Curriculum Domains (3) + MOC - Direct Driver Pattern

| Domain | Category | Relationship Class | Relationship Count | Service |
|--------|----------|-------------------|-------------------|---------|
| **LearningSteps** | Curriculum | `LsRelationships` | 5 relationships | `LsRelationshipService` |
| **LearningPaths** | Curriculum | `LpRelationships` | 5 relationships | `LpRelationshipService` |
| **KnowledgeUnit** | Curriculum | `KuRelationships` *(hybrid)* | 9 relationships | `KuGraphService` |
| **MOC** | Content/Org | `MocRelationships` | - | `MocRelationshipService` |

**Note:** MOC is architecturally a Content/Organization domain but uses the same direct driver pattern for navigation across curriculum content.

---

## 🔗 Auto-Created User Relationships (January 2026)

**Core Principle:** "No orphaned entities - every user entity has an ownership relationship"

When you create an Activity Domain entity with a `user_uid`, the backend **automatically creates** a user-entity relationship:

```
(User)-[:HAS_TASK]->(Task)
(User)-[:HAS_GOAL]->(Goal)
(User)-[:HAS_EVENT]->(Event)
(User)-[:HAS_HABIT]->(Habit)
(User)-[:HAS_CHOICE]->(Choice)
(User)-[:HAS_PRINCIPLE]->(Principle)
```

### Why This Matters

1. **Data Integrity**: No orphaned entities in the graph
2. **Ownership Verification**: `verify_ownership()` checks this relationship
3. **User Queries**: `get_user_entities()` traverses these relationships
4. **Deletion Requires cascade=True**: See [Cascade Deletion Pattern](/docs/patterns/BACKEND_OPERATIONS_ISP.md#cascade-deletion-pattern)

### The Flow

```python
# 1. Create entity with user_uid
task = Task(uid="task_001", user_uid="user.mike", title="Learn Python", ...)
await backend.create(task)

# Backend automatically executes:
# CREATE (t:Task {...properties...})
# MATCH (u:User {uid: "user.mike"}), (t:Task {uid: "task_001"})
# CREATE (u)-[:HAS_TASK]->(t)

# 2. Delete requires cascade=True (relationship exists)
await backend.delete("task_001", cascade=True)  # ✅ Works
await backend.delete("task_001")                # ❌ Fails - has relationships
```

### Curriculum & MOC Domains (No User Ownership)

Curriculum domains (KU, LS, LP) and MOC (Content/Organization) do **NOT** have user ownership relationships:

```python
# Shared content - no ownership relationship created
ku = KnowledgeUnit(uid="ku.python-basics", title="Python Basics", ...)
await backend.create(ku)  # No HAS_KU relationship

# Can delete without cascade
await backend.delete("ku.python-basics")  # ✅ Works (if no other relationships)
```

### Configuration

The ownership relationship is defined in `DomainRelationshipConfig` (in `core.models.relationship_registry`):

```python
# Activity Domains (user-owned)
TASKS_CONFIG = DomainRelationshipConfig(
    domain=Domain.TASKS,
    ownership_relationship=RelationshipName.HAS_TASK,  # Auto-created
    ...
)

# Curriculum Domains (shared content)
KU_CONFIG = DomainRelationshipConfig(
    domain=Domain.KNOWLEDGE,
    ownership_relationship=None,  # No auto-created relationship
    is_shared_content=True,
    ...
)
```

---

## ⚠️ What Changed (Graph-Native Migration)

### Removed: List Relationship Fields

These fields **DO NOT EXIST** anymore and will cause `AttributeError`:

```python
# ❌ WRONG - AttributeError!
task.subtask_uids                    # Tasks
task.applies_knowledge_uids          # Tasks
goal.sub_goal_uids                   # Goals
goal.supporting_habit_uids           # Goals
event.practices_knowledge_uids       # Events
event.executes_task_uids             # Events
habit.reinforces_goal_uids           # Habits
```

### Kept: Single UID References

These fields **STILL EXIST** as node properties:

```python
# ✅ AVAILABLE - Direct property access
task.fulfills_goal_uid: str | None
task.reinforces_habit_uid: str | None
task.parent_uid: str | None
event.reinforces_habit_uid: str | None
goal.parent_goal_uid: str | None
```

---

## 🚀 Quick Start: The Pattern

### Basic Usage (Any Domain)

```python
from core.models.{domain}.{domain}_relationships import {Domain}Relationships

async def analyze_{domain}_complexity(
    self,
    {domain}_uid: str
) -> Result[float]:
    """Calculate complexity based on relationships."""

    # 1. Get the entity
    entity_result = await self.get_{domain}({domain}_uid)
    if entity_result.is_error:
        return entity_result
    entity = entity_result.value

    # 2. Fetch ALL relationships in parallel
    rels = await {Domain}Relationships.fetch(
        entity.uid,
        self.relationships  # Domain-specific relationship service
    )

    # 3. Use relationship data
    complexity = 0.3  # Base complexity

    # Each domain has different relationship fields
    if rels.{domain_specific_relationships}:
        complexity += len(rels.{domain_specific_relationships}) * 0.1

    return Result.ok(complexity)
```

### Examples Across Domains

#### Example 1: Tasks

```python
from core.models.task.task_relationships import TaskRelationships

async def analyze_task(task_uid: str, tasks_service):
    # Fetch all 9 task relationships
    rels = await TaskRelationships.fetch(task_uid, tasks_service.relationships)

    # Access relationship data
    print(f"Subtasks: {len(rels.subtask_uids)}")
    print(f"Knowledge: {len(rels.applies_knowledge_uids)}")
    print(f"Prerequisites: {len(rels.prerequisite_task_uids)}")
```

#### Example 2: Goals

```python
from core.models.goal.goal_relationships import GoalRelationships

async def analyze_goal(goal_uid: str, goals_service):
    # Fetch all 9 goal relationships
    rels = await GoalRelationships.fetch(goal_uid, goals_service.relationships)

    # Access relationship data
    print(f"Sub-goals: {len(rels.sub_goal_uids)}")
    print(f"Supporting habits: {len(rels.supporting_habit_uids)}")
    print(f"Required knowledge: {len(rels.required_knowledge_uids)}")
```

#### Example 3: Events

```python
from core.models.event.event_relationships import EventRelationships

async def analyze_event(event_uid: str, events_service):
    # Fetch all 3 event relationships
    rels = await EventRelationships.fetch(event_uid, events_service.relationships)

    # Access relationship data
    print(f"Practices knowledge: {len(rels.practices_knowledge_uids)}")
    print(f"Executes tasks: {len(rels.executes_task_uids)}")
```

---

## 🏗️ Pattern Structure

### Every Domain Follows This Structure

```python
# File: core/models/{domain}/{domain}_relationships.py

from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.services.{domain}.{domain}_relationship_service import {Domain}RelationshipService

@dataclass(frozen=True)
class {Domain}Relationships:
    """
    Container for all {domain} relationship data (fetched from Neo4j graph).

    Usage:
        rels = await {Domain}Relationships.fetch(entity.uid, service.relationships)
    """

    # Domain-specific relationship fields
    {specific_relationship}_uids: list[str] = field(default_factory=list)
    {another_relationship}_uids: list[str] = field(default_factory=list)

    @classmethod
    async def fetch(
        cls,
        {domain}_uid: str,
        service: {Domain}RelationshipService
    ) -> {Domain}Relationships:
        """Fetch all relationships in parallel."""
        results = await asyncio.gather(
            service.get_{domain}_{relationship1}({domain}_uid),
            service.get_{domain}_{relationship2}({domain}_uid),
            # ... all relationship queries
        )

        return cls(
            {relationship1}_uids=results[0].value if results[0].is_ok else [],
            {relationship2}_uids=results[1].value if results[1].is_ok else [],
            # ... all relationships
        )

    @classmethod
    def empty(cls) -> {Domain}Relationships:
        """Create empty relationships (for testing)."""
        return cls()
```

---

## 📊 Relationship Fields By Domain

### Tasks (12 relationships)
```python
rels.subtask_uids                    # Child tasks
rels.applies_knowledge_uids          # Knowledge applied
rels.aligned_principle_uids          # Principles followed
rels.prerequisite_knowledge_uids     # Required knowledge
rels.prerequisite_task_uids          # Prerequisite tasks
rels.enables_task_uids               # Tasks this unlocks
rels.completion_triggers_tasks       # Tasks triggered on completion
rels.completion_unlocks_knowledge    # Knowledge unlocked
rels.inferred_knowledge_uids         # AI-inferred knowledge
rels.executed_in_event_uids          # Events that executed this task
rels.implements_choice_uids          # Choices this task implements
rels.serves_life_path_uids           # Life path alignment
```

### Goals (11 relationships)
```python
rels.aligned_learning_path_uids      # Learning paths
rels.requires_completion_of_paths    # Path prerequisites
rels.required_knowledge_uids         # Knowledge needed
rels.sub_goal_uids                   # Child goals
rels.supporting_habit_uids           # Supporting habits
rels.essential_habit_uids            # Essential habits
rels.critical_habit_uids             # Critical habits
rels.optional_habit_uids             # Optional habits
rels.guiding_principle_uids          # Guiding principles
rels.milestone_uids                  # Milestone nodes (Phase 2: graph-native)
rels.serves_life_path_uids           # Life path alignment
```

### Events (9 relationships)
```python
rels.practices_knowledge_uids        # Knowledge practiced
rels.executes_task_uids              # Tasks executed
rels.conflicts_with_uids             # Conflicting events
rels.attendee_uids                   # Event attendees
rels.supports_goal_uids              # Goals supported
rels.serves_life_path_uids           # Life path alignment
rels.triggered_choice_uids           # Choices triggered by this event
rels.scheduled_by_choice_uids        # Choices that scheduled this event
rels.demonstrated_principle_uids     # Principles demonstrated at this event
```

### Habits (5 relationships)
```python
rels.linked_goal_uids                # Goals supported
rels.knowledge_reinforcement_uids    # Knowledge reinforced
rels.serves_life_path_uids           # Life path alignment
rels.informed_choice_uids            # Choices informed by this habit
rels.impacting_choice_uids           # Choices that impacted this habit
```

### LearningSteps (5 relationships)
```python
rels.knowledge_unit_uids             # Knowledge units
rels.prerequisite_step_uids          # Prerequisite steps
rels.next_step_uids                  # Next steps
rels.alternative_step_uids           # Alternative paths
rels.milestone_step_uids             # Milestone steps
```

### Choices (10 relationships)
```python
rels.informed_by_knowledge_uids      # Knowledge informing choice
rels.opens_learning_path_uids        # Learning paths opened
rels.required_knowledge_uids         # Knowledge required for decision
rels.aligned_principle_uids          # Principles aligned with choice
rels.implementing_task_uids          # Tasks implementing this choice
rels.serves_life_path_uids           # Life path alignment
rels.impacted_habit_uids             # Habits impacted by this choice
rels.informing_habit_uids            # Habits that informed this choice
rels.scheduled_event_uids            # Events scheduled by this choice
rels.triggering_event_uids           # Events that triggered this choice
```

### Principles (9 relationships)
```python
rels.grounded_knowledge_uids         # Knowledge grounding principle
rels.guided_goal_uids                # Goals guided by principle
rels.inspired_habit_uids             # Habits inspired by principle
rels.related_principle_uids          # Related principles
rels.guided_choice_uids              # Choices guided by principle
rels.guided_task_uids                # Tasks aligned with principle
rels.serves_life_path_uids           # Life path alignment
rels.demonstrating_event_uids        # Events demonstrating this principle
rels.practice_event_uids             # Events for practicing this principle
```

### LearningPaths (5 relationships)
```python
rels.prerequisite_uids               # Prerequisite knowledge units
rels.milestone_event_uids            # Milestone events
rels.aligned_goal_uids               # Aligned goals
rels.embodied_principle_uids         # Embodied principles
rels.step_uids                       # Learning steps in path
```

### KnowledgeUnit (14 relationships - GRAPH-NATIVE + Substance Tracking)

**CRITICAL: KU has a unique hybrid design with two orthogonal concerns:**

#### 1. GRAPH-NATIVE Relationships (Fetched from Graph)
Stored as Neo4j edges, queried on-demand via `KuRelationships.fetch()`:

**Curriculum relationships (KU ↔ KU):**
- `rels.prerequisite_uids` - Required prerequisite knowledge
- `rels.enables_uids` - Knowledge this unlocks
- `rels.related_uids` - Semantically related knowledge
- `rels.broader_uids` - Broader concepts (parent)
- `rels.narrower_uids` - Narrower concepts (children)

**Curriculum relationships (KU ↔ LS/LP):**
- `rels.in_learning_steps_uids` - Learning steps that teach this KU
- `rels.in_learning_paths_uids` - Learning paths covering this KU (2-hop via LS)

**Cross-domain Activity applications (Phase 2 - January 2026):**
- `rels.applied_in_task_uids` - Tasks applying this knowledge
- `rels.required_by_goal_uids` - Goals requiring this knowledge
- `rels.practiced_in_event_uids` - Events practicing this knowledge
- `rels.reinforced_by_habit_uids` - Habits reinforcing this knowledge
- `rels.informs_choice_uids` - Choices informed by this knowledge
- `rels.grounds_principle_uids` - Principles grounded in this knowledge

**Fetch methods:**
```python
# Bulk fetch all relationships:
rels = await KuRelationships.fetch(ku_uid, neo4j_adapter, user_uid)

# Individual queries (Phase 2):
tasks = await ku_service.find_tasks_applying_knowledge(ku_uid, user_uid)
goals = await ku_service.find_goals_requiring_knowledge(ku_uid, user_uid)
events = await ku_service.find_events_applying_knowledge(ku_uid, user_uid)
habits = await ku_service.find_habits_reinforcing_knowledge(ku_uid, user_uid)
choices = await ku_service.find_choices_informed_by_knowledge(ku_uid, user_uid)
principles = await ku_service.find_principles_embodying_knowledge(ku_uid, user_uid)
```

#### 2. Substance Tracking Properties (Stored on KU Node)
These are **NOT GRAPH-NATIVE** - stored as KU properties for performance:

- `ku.times_applied_in_tasks` - Application count (for substance score)
- `ku.times_practiced_in_events` - Practice count (for substance score)
- `ku.times_built_into_habits` - Habit integration count (for substance score)
- `ku.journal_reflections_count` - Reflection count (for substance score)
- `ku.last_applied` - Most recent application timestamp
- `ku.last_practiced` - Most recent practice timestamp

**Why stored as properties:**
- Used in spaced repetition algorithms (30-day half-life temporal decay)
- Substance score calculation (0.0-1.0 scale)
- Performance optimization (no relationship count queries)

**Access via:**
```python
# Substance score (uses stored properties):
score = ku.calculate_substance_score()

# Individual metrics:
application_count = ku.times_applied_in_tasks
practice_count = ku.times_practiced_in_events
```

**Architecture Note:** This hybrid design is **intentional and correct** - relationships are fetched on-demand, but substance metrics are pre-computed aggregates for performance.

---

## 🤔 Decision Tree: When to Use

### Question 1: Are you accessing relationship LISTS?

**Examples:**
- List of subtasks
- List of knowledge units applied
- List of supporting habits
- List of sub-goals

**YES** → Use `{Domain}Relationships.fetch()`
**NO** → Use direct property access (single UIDs, booleans, strings)

---

### Question 2: Do you have service access?

#### ✅ YES - Use Relationships.fetch()

```python
async def process_entity(self, entity_uid: str):
    # You have self.relationships or service.relationships
    rels = await {Domain}Relationships.fetch(
        entity_uid,
        self.relationships
    )

    # Use relationship data
    if rels.{specific_relationships}:
        # Process relationships
        pass
```

#### ❌ NO - Use Proxy Attributes

**Available proxies across domains:**

| Proxy Field | Indicates | Works For |
|-------------|-----------|-----------|
| `knowledge_mastery_check` | Learning task | Tasks |
| `source_learning_step_uid` | Curriculum task | Tasks, Events |
| `parent_uid` | Hierarchical structure | Tasks |
| `parent_goal_uid` | Goal hierarchy | Goals |
| `fulfills_goal_uid` | Goal-linked | Tasks |
| `reinforces_habit_uid` | Habit-linked | Tasks, Events |

---

## 📊 Performance

### Parallel Fetching

**Single Entity:**
- Fetches N relationships in parallel (not sequential)
- ~70% faster than sequential queries

**Batch Processing:**
```python
# Fetch relationships for 100 entities
all_rels = await asyncio.gather(*[
    {Domain}Relationships.fetch(entity.uid, service.relationships)
    for entity in entities
])
# 100 * N queries all in parallel!
```

**Performance Metrics:**
- Tasks: 9 parallel queries per task
- Goals: 9 parallel queries per goal
- Events: 3 parallel queries per event
- Batch of 100 tasks: 900 queries in parallel = ~60% improvement

---

## 🧪 Testing Pattern

### Mock Relationships

```python
from core.models.{domain}.{domain}_relationships import {Domain}Relationships

def test_analysis():
    """Test with mock relationships."""

    # Create mock relationships
    mock_rels = {Domain}Relationships(
        {relationship1}_uids=["uid1", "uid2"],
        {relationship2}_uids=["uid3"],
        # All other fields default to empty lists
    )

    # Test your logic
    result = analyze_entity(entity, mock_rels)
    assert result > 0
```

### Empty Relationships

```python
def test_new_entity():
    """Test entity with no relationships."""

    rels = {Domain}Relationships.empty()

    assert rels.{relationship1}_uids == []
    assert rels.{relationship2}_uids == []
```

---

## ⚠️ Common Mistakes

### Mistake 1: Accessing Removed Fields

```python
# ❌ WRONG - AttributeError!
if task.applies_knowledge_uids:
    pass

if goal.sub_goal_uids:
    pass

# ✅ CORRECT - Fetch relationships
rels = await TaskRelationships.fetch(task.uid, service.relationships)
if rels.applies_knowledge_uids:
    pass

rels = await GoalRelationships.fetch(goal.uid, service.relationships)
if rels.sub_goal_uids:
    pass
```

### Mistake 2: Sequential Fetching

```python
# ❌ SLOW - Sequential
for entity in entities:
    rels = await {Domain}Relationships.fetch(entity.uid, service.relationships)
    # Process...

# ✅ FAST - Parallel
all_rels = await asyncio.gather(*[
    {Domain}Relationships.fetch(entity.uid, service.relationships)
    for entity in entities
])
rels_map = {e.uid: r for e, r in zip(entities, all_rels)}
```

---

## 🔧 Implementing for New Domains

When adding a new domain, follow this checklist:

1. **Create relationship file:** `core/models/{domain}/{domain}_relationships.py`
2. **Define relationship dataclass:** `{Domain}Relationships`
3. **List all relationship fields:** As `list[str]` with `field(default_factory=list)`
4. **Implement `fetch()` classmethod:** Query all relationships in parallel
5. **Implement `empty()` classmethod:** Return empty instance
6. **Add helper methods:** Like `has_any_relationships()`, `total_count()`, etc.
7. **Update DTO docstring:** Warn about removed fields
8. **Create relationship service:** `{domain}_relationship_service.py`

**Template available at:** `/core/models/task/task_relationships.py` (most complete example)

---

## 📚 Related Documentation

**Per-Domain Guides:**
- Tasks: `/core/models/task/task_relationships.py`
- Goals: `/core/models/goal/goal_relationships.py`
- Events: `/core/models/event/event_relationships.py`
- Habits: `/core/models/habit/habit_relationships.py`
- LearningSteps: `/core/models/ls/ls_relationships.py`
- Choices: `/core/models/choice/choice_relationships.py`
- Principles: `/core/models/principle/principle_relationships.py`
- LearningPaths: `/core/models/lp/lp_relationships.py`
- KnowledgeUnit: `/core/models/ku/ku_relationships.py` *(hybrid pattern with semantic support)*
- KnowledgeUnit Design: `/docs/design/KU_RELATIONSHIPS_DESIGN.md` *(design rationale)*

**Architecture:**
- Graph-Native Migration: `/docs/migrations/PHASE_3B_REFACTORING_PLAN.md`
- CLAUDE.md: Section on Graph-Native Comment Standard

---

## 🆘 Quick Reference

### When You Get AttributeError

```python
# Error: '{Domain}' object has no attribute '{relationship}_uids'

# Fix:
from core.models.{domain}.{domain}_relationships import {Domain}Relationships

rels = await {Domain}Relationships.fetch({domain}.uid, service.relationships)
uids = rels.{relationship}_uids  # ✅ Works!
```

### When You Need Performance

```python
# Use asyncio.gather for batch operations
all_rels = await asyncio.gather(*[
    {Domain}Relationships.fetch(e.uid, service.relationships)
    for e in entities
])
```

### When You're Testing

```python
# Use .empty() for new entities
rels = {Domain}Relationships.empty()

# Use constructor for mocks
rels = {Domain}Relationships(
    {relationship1}_uids=["test_uid"],
    # All others default to []
)
```
