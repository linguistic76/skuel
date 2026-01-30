

# Lateral Relationships - Core Graph Modeling

**Date:** 2026-01-31
**Status:** Core Architecture - Fundamental to SKUEL
**Philosophy:** "Lateral relationships are as fundamental as hierarchical ones"

---

## Executive Summary

SKUEL's graph model now includes **explicit lateral relationships** as a core architectural component, not a feature add-on. This establishes relationships between entities at the same or related hierarchical levels (siblings, cousins, dependencies, semantic connections).

**Why Core, Not Add-On:**
- Graph databases excel at relationships - we must model them properly
- Hierarchies alone can't capture complex entity semantics
- Performance optimization via explicit relationships
- Enables powerful graph algorithms and recommendations
- Foundation for advanced features (blocking chains, alternative paths, semantic discovery)

---

## The Problem: Hierarchies Are Insufficient

### What Hierarchies Give Us

```cypher
(Career Goals)
  ├── (Learn Python)
  ├── (Build Portfolio)
  └── (Get Job Offer)
```

**Tree structure tells us:**
- ✅ Parent-child relationships
- ✅ Grouping and nesting
- ✅ Order within level

**Tree structure CANNOT tell us:**
- ❌ "Learn Python" must complete before "Build Portfolio"
- ❌ "Build Portfolio" and "Get Certification" are alternative approaches
- ❌ "Learn Python" and "Practice Algorithms" complement each other
- ❌ Which goals are in similar domains but different branches

---

## The Solution: Explicit Lateral Relationships

### Enhanced Graph Model

```cypher
// Hierarchical relationships (existing)
(Career Goals)-[:SUBGOAL]->(Learn Python)
(Career Goals)-[:SUBGOAL]->(Build Portfolio)

// Lateral relationships (NEW - core)
(Learn Python)-[:BLOCKS {reason: "Need skills first"}]->(Build Portfolio)
(Build Portfolio)-[:ALTERNATIVE_TO {criteria: "credibility"}]->(Get Certification)
(Learn Python)-[:COMPLEMENTARY_TO {synergy: 0.85}]->(Practice Algorithms)
```

**Now the graph knows:**
- ✅ Blocking dependencies between siblings
- ✅ Alternative paths to achieve outcomes
- ✅ Synergistic combinations
- ✅ Semantic connections across branches

---

## Architecture Overview

### Three-Layer Design

```
┌─────────────────────────────────────────────────────────┐
│  Domain Services (Goals, Tasks, Habits, etc.)          │
│  - create_blocking_relationship()                      │
│  - create_alternative_relationship()                   │
│  - get_sibling_goals()                                 │
│  - Domain-specific validation                          │
└────────────────┬────────────────────────────────────────┘
                 │ delegates to
┌────────────────▼────────────────────────────────────────┐
│  Core Lateral Relationship Service                     │
│  - create_lateral_relationship()                       │
│  - delete_lateral_relationship()                       │
│  - get_lateral_relationships()                         │
│  - get_siblings(), get_cousins()                       │
│  - Validation, cycle detection, inverse creation       │
└────────────────┬────────────────────────────────────────┘
                 │ uses
┌────────────────▼────────────────────────────────────────┐
│  Graph Database (Neo4j)                                │
│  - Lateral relationship types (BLOCKS, SIBLING, etc.)  │
│  - Rich relationship metadata                          │
│  - Graph traversal algorithms                          │
└─────────────────────────────────────────────────────────┘
```

### Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| **LateralRelationType** | `/core/models/enums/` | Enum of all lateral relationship types |
| **LateralRelationshipService** | `/core/services/lateral_relationships/` | Domain-agnostic core service |
| **GoalsLateralService** | `/core/services/goals/` | Domain-specific wrapper (example) |
| **API Routes** | `/adapters/inbound/lateral_api.py` | HTTP endpoints for lateral operations |
| **UI Components** | `/ui/patterns/lateral_*.py` | Visualization components |

---

## Relationship Type Categories

### 1. Structural Relationships

**Derived from hierarchy, made explicit for performance:**

| Type | Example | Bidirectional |
|------|---------|---------------|
| **SIBLING** | Two goals under same parent | Yes (symmetric) |
| **COUSIN** | Two goals, different parents, shared grandparent | Yes (symmetric) |
| **AUNT_UNCLE** | Parent's sibling | No (has NIECE_NEPHEW inverse) |

**Use case:** Fast sibling queries without tree traversal.

### 2. Dependency Relationships

**Ordering and blocking constraints:**

| Type | Example | Bidirectional |
|------|---------|---------------|
| **BLOCKS** | Task A must complete before sibling Task B | No (has BLOCKED_BY inverse) |
| **PREREQUISITE_FOR** | KU A required for KU B | No (has REQUIRES_PREREQUISITE inverse) |
| **ENABLES** | Completing A unlocks B | No (has ENABLED_BY inverse) |

**Use case:** Blocking chains, prerequisite trees, unlock sequences.

### 3. Semantic Relationships

**Domain meaning beyond structure:**

| Type | Example | Bidirectional |
|------|---------|---------------|
| **RELATED_TO** | Two principles that reinforce each other | Yes (symmetric) |
| **SIMILAR_TO** | Two learning paths covering similar content | Yes (symmetric) |
| **COMPLEMENTARY_TO** | Meditation habit + Exercise habit | Yes (symmetric) |
| **CONFLICTS_WITH** | Mutually exclusive choices | Yes (symmetric) |

**Use case:** Recommendations, cross-domain discovery, conflict detection.

### 4. Associative Relationships

**Recommendations and alternatives:**

| Type | Example | Bidirectional |
|------|---------|---------------|
| **ALTERNATIVE_TO** | Career path A vs Career path B | Yes (symmetric) |
| **RECOMMENDED_WITH** | Users who completed A also completed B | Yes (symmetric) |
| **STACKS_WITH** | Do habit A after habit B (chaining) | Directional |

**Use case:** Habit stacking, choice alternatives, collaborative filtering.

---

## Core Service API

### Create Lateral Relationship

```python
from core.services.lateral_relationships import LateralRelationshipService
from core.models.enums.lateral_relationship_types import LateralRelationType

lateral_service = LateralRelationshipService(driver)

result = await lateral_service.create_lateral_relationship(
    source_uid="goal_python_basics",
    target_uid="goal_django_app",
    relationship_type=LateralRelationType.BLOCKS,
    metadata={
        "reason": "Must learn Python before building Django app",
        "severity": "required",
        "created_by": user_uid
    },
    validate=True,  # Perform constraint validation
    auto_inverse=True  # Auto-create BLOCKED_BY inverse relationship
)
```

**Validation Performed:**
- ✅ Both entities exist
- ✅ Same parent constraint (for SIBLING, BLOCKS)
- ✅ Same depth constraint (for COUSIN, ALTERNATIVE_TO)
- ✅ No circular dependencies (for BLOCKS, PREREQUISITE_FOR)
- ✅ No duplicate relationships

**Auto-Inverse Creation:**
For asymmetric relationships (BLOCKS, ENABLES, etc.), the service automatically creates the inverse relationship:
```cypher
// Creating this:
(A)-[:BLOCKS]->(B)

// Automatically creates:
(B)-[:BLOCKED_BY]->(A)
```

### Query Lateral Relationships

```python
# Get all lateral relationships for an entity
result = await lateral_service.get_lateral_relationships(
    entity_uid="goal_advanced_python",
    relationship_types=[
        LateralRelationType.BLOCKS,
        LateralRelationType.RELATED_TO
    ],
    direction="incoming",  # or "outgoing" or "both"
    include_metadata=True
)

# Returns:
[
    {
        "type": "BLOCKS",
        "target_uid": "goal_python_basics",
        "target_title": "Learn Python Basics",
        "metadata": {"reason": "...", "severity": "required"},
        "direction": "incoming"
    },
    ...
]
```

### Get Siblings (Derived)

```python
# Get siblings derived from hierarchy
result = await lateral_service.get_siblings(
    entity_uid="goal_learn_python",
    include_explicit_only=False  # Derive from SUBGOAL relationships
)

# Returns all goals sharing the same parent
```

### Get Cousins (Derived)

```python
# Get first cousins (same depth, shared grandparent)
result = await lateral_service.get_cousins(
    entity_uid="goal_learn_python",
    degree=1  # 1st cousins
)

# Returns goals at same depth via different parent branch
```

---

## Domain-Specific Services

Each domain creates a wrapper service for domain-specific convenience methods.

### Example: Goals Lateral Service

```python
# core/services/goals/goals_lateral_service.py
class GoalsLateralService:
    def __init__(self, driver, goals_service):
        self.lateral_service = LateralRelationshipService(driver)
        self.goals_service = goals_service

    async def create_blocking_relationship(
        self,
        blocker_uid: str,
        blocked_uid: str,
        reason: str,
        severity: str = "required",
        user_uid: str | None = None
    ) -> Result[bool]:
        """Domain-specific wrapper with ownership validation."""
        # Verify user owns both goals
        for goal_uid in [blocker_uid, blocked_uid]:
            ownership = await self.goals_service.verify_ownership(
                goal_uid, user_uid
            )
            if ownership.is_error:
                return ownership

        # Delegate to core service
        return await self.lateral_service.create_lateral_relationship(
            source_uid=blocker_uid,
            target_uid=blocked_uid,
            relationship_type=LateralRelationType.BLOCKS,
            metadata={"reason": reason, "severity": severity},
            validate=True,
            auto_inverse=True
        )
```

**Benefits:**
- ✅ Domain-specific validation (ownership, status checks)
- ✅ Convenient wrapper methods (no need to import enums)
- ✅ Business rules enforcement
- ✅ Consistent API across domains

---

## Query Patterns

### Find Blocking Chain

```cypher
// Find all goals blocking target goal (transitively)
MATCH path = (blocker)-[:BLOCKS*1..5]->(target {uid: $target_uid})
RETURN
    [node in nodes(path) | {
        uid: node.uid,
        title: node.title
    }] as blocking_chain,
    length(path) as chain_length
ORDER BY chain_length DESC
```

### Find Alternatives for Decision

```cypher
// Find all alternative choices
MATCH (choice {uid: $choice_uid})-[:ALTERNATIVE_TO]-(alternative)
RETURN
    alternative.uid as alternative_uid,
    alternative.title as alternative_title,
    alternative.description as description
```

### Recommend Based on Siblings

```cypher
// Find what siblings of completed goals typically lead to
MATCH (completed {uid: $completed_goal_uid})-[:SIBLING]-(sibling)-[:ENABLES]->(next)
WHERE NOT (completed)-[:ENABLES]->(next)
RETURN
    next.uid as recommended_uid,
    next.title as recommended_title,
    count(sibling) as evidence_count
ORDER BY evidence_count DESC
LIMIT 5
```

### Find Complementary Habits

```cypher
// Find habits that complement current habit
MATCH (habit {uid: $habit_uid})-[:COMPLEMENTARY_TO {synergy_score > 0.7}]-(complementary)
WHERE NOT (user)-[:PERFORMS_HABIT]->(complementary)
RETURN
    complementary.uid as habit_uid,
    complementary.title as habit_title,
    complementary.description as description
ORDER BY complementary.synergy_score DESC
```

---

## UI Visualization Strategies

### 1. Blocking Chain Diagram

**Use case:** Show prerequisite sequence for a goal

```
┌──────────────┐
│ Learn Python │ (blocking)
└──────┬───────┘
       │ BLOCKS
       ▼
┌──────────────┐
│ Build Django │ (blocked)
│     App      │
└──────────────┘
```

**Component:** `/ui/patterns/blocking_chain.py`

### 2. Alternative Options Grid

**Use case:** Compare mutually exclusive choices

```
┌─────────────────┬─────────────────┐
│  Career Path A  │  Career Path B  │
├─────────────────┼─────────────────┤
│ Medicine        │ Engineering     │
│ - 8 yr training │ - 4 yr training │
│ - Direct impact │ - Broad scope   │
└─────────────────┴─────────────────┘
    ALTERNATIVE_TO
```

**Component:** `/ui/patterns/alternatives_grid.py`

### 3. Sibling Relationship Map

**Use case:** Visualize how sibling goals relate

```
        ┌─────────────┐
        │ Parent Goal │
        └──────┬──────┘
               │
    ┌──────────┼──────────┐
    │          │          │
┌───▼───┐  ┌───▼───┐  ┌───▼───┐
│ Goal A│  │ Goal B│  │ Goal C│
└───────┘  └───┬───┘  └───────┘
               │
               │ BLOCKS
               ▼
          (Goal B must complete before C)
```

**Component:** `/ui/patterns/sibling_graph.py`

### 4. Complementary Suggestions

**Use case:** Recommend synergistic habits/goals

```
Your current habit: Meditation 🧘
Complementary habits:
  • Exercise 🏃 (synergy: 0.85)
  • Journaling 📓 (synergy: 0.78)
  • Yoga 🧘 (synergy: 0.92)
```

**Component:** `/ui/patterns/complementary_recommendations.py`

---

## Performance Considerations

### When to Use Explicit vs. Derived

| Scenario | Approach | Reason |
|----------|----------|--------|
| Query siblings once | Derive from hierarchy | No overhead |
| Query siblings 100x/day | Create explicit SIBLING | Faster lookup |
| Blocking relationship | Always explicit | Semantic meaning |
| Semantic similarity | Always explicit | Can't derive |
| First-time cousin query | Derive from hierarchy | Avoid premature optimization |
| Frequent cousin recommendations | Create explicit COUSIN | Performance gain |

**Rule of Thumb:** Start with derived queries. Add explicit relationships when:
1. Query is performance-critical (profiling proves it)
2. Relationship has semantic meaning beyond structure
3. Enables domain features (habit stacking, alternatives)

### Indexing Strategy

```cypher
// Create index for fast lateral relationship lookup
CREATE INDEX lateral_rel_source FOR ()-[r:BLOCKS]-() ON (r.source_uid)
CREATE INDEX lateral_rel_target FOR ()-[r:BLOCKS]-() ON (r.target_uid)

// Create indexes for all lateral relationship types
// (Handled automatically by relationship type enum)
```

---

## Integration with Existing Features

### UnifiedRelationshipService

**Keep both services:**
- `UnifiedRelationshipService` - Hierarchical relationships (SUBGOAL, parent/child)
- `LateralRelationshipService` - Lateral relationships (BLOCKS, SIBLING, COUSIN)

**Clear separation:**
```python
# Hierarchical relationships
await unified_rel_service.create_subgoal_relationship(parent, child)

# Lateral relationships
await lateral_service.create_lateral_relationship(
    sibling_a, sibling_b, LateralRelationType.BLOCKS
)
```

### UserContext Integration

Add lateral relationship fields to `UserContext`:

```python
@dataclass(frozen=True)
class UserContext:
    # ... existing fields ...

    # Lateral relationship counts
    blocking_goal_count: int = 0
    blocked_goal_count: int = 0
    alternative_choice_count: int = 0
    complementary_habit_pairs: int = 0

    # Rich lateral data (if rich context)
    blocking_chains: list[dict[str, Any]] = field(default_factory=list)
    goal_alternatives: list[dict[str, Any]] = field(default_factory=list)
```

### Intelligence Services

Leverage lateral relationships for smarter recommendations:

```python
# GoalsIntelligenceService
async def recommend_next_goals(self, user_uid: str) -> Result[list[Goal]]:
    """Use COMPLEMENTARY_TO and ENABLES to find synergistic goals."""
    # Find completed goals
    # Find what they ENABLE
    # Find COMPLEMENTARY_TO relationships
    # Score and rank recommendations
```

---

## Migration Strategy

### Phase 1: Core Infrastructure (COMPLETE)

- [x] Create `LateralRelationType` enum
- [x] Implement `LateralRelationshipService`
- [x] Create `GoalsLateralService` (example)
- [x] Write comprehensive documentation

### Phase 2: Domain Services (Next)

- [ ] Create lateral services for all domains:
  - [ ] `TasksLateralService`
  - [ ] `HabitsLateralService`
  - [ ] `KuLateralService`
  - [ ] `LsLateralService`
  - [ ] `LpLateralService`
  - [ ] `EventsLateralService`
  - [ ] `ChoicesLateralService`
  - [ ] `PrinciplesLateralService`

### Phase 3: API & UI (Next)

- [ ] Create API routes (`/api/lateral/*`)
- [ ] Build UI components for visualization
- [ ] Add lateral relationship management to entity detail pages

### Phase 4: Intelligence Features (Future)

- [ ] Blocking chain analyzer
- [ ] Alternative path recommender
- [ ] Complementary entity suggester
- [ ] Semantic similarity engine

### Phase 5: Advanced Features (Future)

- [ ] Graph algorithm integration (PageRank, centrality)
- [ ] Automated relationship discovery (ML-based)
- [ ] Cross-domain lateral relationships
- [ ] Temporal lateral relationships (changing over time)

---

## Examples

### Example 1: Goal Blocking Chain

```python
# User creates goals
career_goals_uid = await goals_service.create_goal(
    user_uid, "Advance Career", domain="career"
)
learn_python_uid = await goals_service.create_subgoal(
    career_goals_uid, "Learn Python Basics"
)
build_portfolio_uid = await goals_service.create_subgoal(
    career_goals_uid, "Build Portfolio"
)
get_job_uid = await goals_service.create_subgoal(
    career_goals_uid, "Get Job Offer"
)

# Create blocking relationships (siblings)
await goals_lateral_service.create_blocking_relationship(
    blocker_uid=learn_python_uid,
    blocked_uid=build_portfolio_uid,
    reason="Need Python skills to build projects",
    severity="required"
)

await goals_lateral_service.create_blocking_relationship(
    blocker_uid=build_portfolio_uid,
    blocked_uid=get_job_uid,
    reason="Portfolio demonstrates skills to employers",
    severity="recommended"
)

# Query blocking chain
blocking_chain = await goals_lateral_service.get_blocking_goals(get_job_uid)
# Returns: [Learn Python Basics] -> [Build Portfolio] -> [Get Job Offer]
```

### Example 2: Alternative Career Paths

```python
# User exploring career options
medicine_path_uid = await goals_service.create_goal(
    user_uid, "Become Doctor", domain="career"
)
engineering_path_uid = await goals_service.create_goal(
    user_uid, "Become Engineer", domain="career"
)

# Mark as alternatives
await goals_lateral_service.create_alternative_relationship(
    goal_a_uid=medicine_path_uid,
    goal_b_uid=engineering_path_uid,
    comparison_criteria="Long-term career path",
    tradeoffs=[
        "Medicine: 8-year training, direct patient impact, structured career",
        "Engineering: 4-year training, broad application, flexible career"
    ]
)

# Query alternatives
alternatives = await goals_lateral_service.get_alternative_goals(medicine_path_uid)
# UI shows side-by-side comparison with tradeoffs
```

### Example 3: Complementary Habits

```python
# User building morning routine
meditation_uid = await habits_service.create_habit(
    user_uid, "Morning Meditation", frequency="daily"
)
exercise_uid = await habits_service.create_habit(
    user_uid, "Morning Exercise", frequency="daily"
)

# Mark as complementary
await habits_lateral_service.create_complementary_relationship(
    habit_a_uid=meditation_uid,
    habit_b_uid=exercise_uid,
    synergy_description="Mindfulness + physical activity = optimal morning",
    synergy_score=0.88
)

# Intelligence service uses this for recommendations
recommendations = await habits_intelligence.recommend_complementary_habits(
    current_habits=[meditation_uid]
)
# Suggests: "Add Morning Exercise (synergy: 0.88) to enhance your routine"
```

---

## Conclusion

Lateral relationships are **fundamental** to SKUEL's graph model because:

1. **Semantic Richness:** Captures meaning beyond tree structure
2. **Performance:** Explicit relationships enable fast queries
3. **Intelligence:** Foundation for smart recommendations
4. **Flexibility:** Supports evolving domain features
5. **Graph-Native:** Leverages Neo4j's core strengths

This is not a feature - it's **core architecture** that all domains can build upon.

**Status:** Phase 1 (Core Infrastructure) COMPLETE ✅

**Next Steps:** Implement domain services for all 8 hierarchical domains.
