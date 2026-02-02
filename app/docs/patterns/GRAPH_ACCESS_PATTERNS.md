---
title: Graph Access Patterns Guide
updated: 2025-11-27
category: patterns
related_skills:
- pytest
- neo4j-cypher-patterns
related_docs: []
---

# Graph Access Patterns Guide

**Version**: 1.0
**Date**: October 8, 2025
**Status**: Official Architecture Guide

---
## Related Skills

For implementation guidance, see:
- [@neo4j-cypher-patterns](../../.claude/skills/neo4j-cypher-patterns/SKILL.md)
- [@pytest](../../.claude/skills/pytest/SKILL.md)


## Overview

SKUEL uses **two complementary graph access patterns** for optimal performance and functionality:

1. **Pattern 1: Graph-Aware Models** - Relationship UIDs stored in domain models
2. **Pattern 2: Graph-Native Queries** - Cypher traversal via GraphIntelligenceService

**Both patterns are essential and should be used together based on the use case.**

---

## Quick Decision Tree

```
┌─────────────────────────────────────┐
│   Need to access relationships?    │
└──────────────┬──────────────────────┘
               │
               ▼
    ┌──────────────────────┐
    │  Is it direct/       │ YES → Pattern 1 (UIDs)
    │  single-hop?         │       Fast, instant, type-safe
    └──────┬───────────────┘
           │ NO
           ▼
    ┌──────────────────────┐
    │  Need multi-hop      │ YES → Pattern 2 (Queries)
    │  or cross-domain?    │       Deep traversal, analytics
    └──────┬───────────────┘
           │ NO
           ▼
    ┌──────────────────────┐
    │  For validation      │ YES → Pattern 1 (UIDs)
    │  or business logic?  │       Pre-save checks, instant
    └──────┬───────────────┘
           │ NO
           ▼
    ┌──────────────────────┐
    │  For analytics or    │ YES → Pattern 2 (Queries)
    │  intelligence?       │       Complex analysis
    └──────────────────────┘
```

---

## Pattern 1: Graph-Aware Models

### What It Is

Domain models store relationship UIDs as **immutable fields**:

```python
@dataclass(frozen=True)
class Task:
    """Task domain model with graph-aware relationships."""

    uid: str
    title: str

    # Graph-aware relationship fields
    parent_uid: Optional[str] = None
    subtask_uids: tuple[str, ...] = ()
    prerequisite_task_uids: tuple[str, ...] = ()
    applies_knowledge_uids: tuple[str, ...] = ()
    fulfills_goal_uid: Optional[str] = None
    reinforces_habit_uid: Optional[str] = None
```

### When to Use

✅ **Use Pattern 1 when you need**:

1. **Direct relationship checks** (is there a parent?)
2. **Fast validation** (pre-save, permission checks)
3. **Business logic** (model methods without DB access)
4. **Simple queries** (`find_by(parent_uid=x)`)
5. **Type safety** (IDE autocomplete, mypy validation)
6. **UI display** (showing direct connections)

### Advantages

| Benefit | Description |
|---------|-------------|
| **⚡ Performance** | O(1) access - no DB query needed |
| **🔒 Type Safety** | Strongly typed with `Optional[str]` and `tuple[str, ...]` |
| **✅ Validation** | Pre-save checks without DB round-trip |
| **🧠 Business Logic** | Model methods can check relationships instantly |
| **🎯 Simplicity** | Straightforward code, easy to understand |

### Code Examples

#### Example 1: Instant Relationship Checks

```python
# No DB query needed - instant check
def can_start_task(task: Task) -> bool:
    """Check if task has no prerequisites."""
    return len(task.prerequisite_task_uids) == 0

# Instant check for business logic
if task.is_learning_task():  # Uses applies_knowledge_uids internally
    print("This is a learning task")

# Instant parent check
if task.parent_uid:
    print(f"This is a subtask of {task.parent_uid}")
```

#### Example 2: Simple Queries

```python
# Single query - find all subtasks
subtasks = await backend.find_by(parent_uid=parent_task_uid)

# Single query - find tasks for a goal
goal_tasks = await backend.find_by(fulfills_goal_uid=goal_uid)

# Single query with multiple filters
learning_tasks = await backend.find_by(
    status=ActivityStatus.IN_PROGRESS,
    # Note: Can't filter by "has knowledge" directly - need custom query
)
```

#### Example 3: Pre-Save Validation

```python
async def create_task(self, task_request: TaskCreateRequest) -> Result[Task]:
    """Create task with instant validation."""

    # Pattern 1: Instant validation (no DB query)
    if len(task_request.prerequisite_task_uids) > 20:
        return Result.fail("Too many prerequisites (max 20)")

    if task_request.parent_uid and len(task_request.subtask_uids) > 0:
        return Result.fail("Task cannot be both parent and subtask")

    # Create task
    task = Task(**task_request.dict())
    result = await self.backend.create(task)
    return result
```

#### Example 4: Business Logic Methods

```python
@dataclass(frozen=True)
class Task:
    parent_uid: Optional[str] = None
    subtask_uids: tuple[str, ...] = ()
    applies_knowledge_uids: tuple[str, ...] = ()
    prerequisite_task_uids: tuple[str, ...] = ()

    def is_standalone(self) -> bool:
        """Check if task has no parent or children (instant)."""
        return self.parent_uid is None and len(self.subtask_uids) == 0

    def has_prerequisites(self) -> bool:
        """Check if task has prerequisites (instant)."""
        return len(self.prerequisite_task_uids) > 0

    def is_learning_task(self) -> bool:
        """Check if task applies knowledge (instant)."""
        return len(self.applies_knowledge_uids) > 0

    def subtask_count(self) -> int:
        """Get subtask count (instant)."""
        return len(self.subtask_uids)
```

---

## Pattern 2: Graph-Native Queries

### What It Is

Complex graph queries using **GraphIntelligenceService** and **SemanticCypherBuilder**:

```python
# Multi-hop dependency query
query = task.build_dependency_query(depth=3)
dependencies = await graph_service.execute_graph_query(query)

# Cross-domain impact analysis
context = await graph_service.get_context(
    node_uid=task.uid,
    intent=QueryIntent.HIERARCHICAL,
    depth=2
)
```

### When to Use

✅ **Use Pattern 2 when you need**:

1. **Multi-hop traversal** (prerequisites of prerequisites...)
2. **Cross-domain analysis** (Task → Knowledge → Goal chains)
3. **Hidden connections** (inferred relationships, patterns)
4. **Analytics** (impact scores, relationship strength)
5. **Intelligence features** (Askesis context, recommendations)
6. **Semantic queries** (REQUIRES_THEORETICAL_UNDERSTANDING)

### Advantages

| Benefit | Description |
|---------|-------------|
| **🌐 Deep Traversal** | Multi-hop relationships (N levels deep) |
| **🔗 Cross-Domain** | Traverse Task → Knowledge → Goal seamlessly |
| **🔍 Discovery** | Find hidden connections and patterns |
| **📊 Analytics** | Compute impact scores, relationship strength |
| **🧠 Intelligence** | Rich context for AI/ML features |
| **🎯 Semantic** | Type-aware relationship traversal |

### Code Examples

#### Example 1: Multi-Hop Dependencies

```python
async def get_full_dependency_tree(self, task_uid: str) -> Result[dict]:
    """Get complete dependency tree (3 levels deep)."""

    task = await self.get_task(task_uid)

    # Pattern 2: Deep traversal query
    query = task.build_dependency_query(depth=3)
    result = await self.graph_intelligence.execute_graph_query(query)

    # Returns:
    # - Direct prerequisites (task.prerequisite_task_uids)
    # - Prerequisites of prerequisites (2-hop)
    # - Prerequisites of prerequisites of prerequisites (3-hop)
    # - Cross-domain: prerequisite knowledge
    # - Cross-domain: knowledge prerequisites (multi-hop)

    return Result.ok({
        'direct_prerequisites': list(task.prerequisite_task_uids),  # Pattern 1
        'dependency_tree': result.nodes,  # Pattern 2
        'total_depth': result.max_depth,
        'cross_domain_deps': result.cross_domain_relationships
    })
```

#### Example 2: Completion Impact Analysis

```python
async def analyze_completion_impact(self, task_uid: str) -> Result[dict]:
    """Analyze what happens when task completes."""

    task = await self.get_task(task_uid)

    # Pattern 2: Cross-domain impact analysis
    query = task.build_completion_impact_query()
    impact = await self.graph_intelligence.execute_graph_query(query)

    # Returns:
    # - Goals updated (from task.fulfills_goal_uid) - Pattern 1
    # - Goals affected via knowledge (cross-domain) - Pattern 2
    # - Tasks triggered (from task.completion_triggers_tasks) - Pattern 1
    # - Tasks enabled (reverse lookup) - Pattern 2
    # - Knowledge unlocked (from task.completion_unlocks_knowledge) - Pattern 1
    # - Knowledge chains affected (multi-hop) - Pattern 2
    # - Habits reinforced (from task.reinforces_habit_uid) - Pattern 1
    # - Habit streaks impacted (analytics) - Pattern 2

    return Result.ok({
        'immediate_impact': {
            'goals': [task.fulfills_goal_uid] if task.fulfills_goal_uid else [],
            'tasks': list(task.completion_triggers_tasks),
            'knowledge': list(task.completion_unlocks_knowledge),
        },
        'ripple_effects': impact.downstream_impacts,
        'cross_domain_effects': impact.cross_domain_impacts,
        'impact_score': impact.calculate_impact_score()
    })
```

#### Example 3: Knowledge Context for Askesis

```python
async def get_task_context_for_askesis(
    self,
    task_uid: str,
    include_deep_context: bool = True
) -> Result[dict]:
    """Get rich context for Askesis chatbot."""

    # Pattern 1: Get task with direct relationships (single query)
    task = await self.get_task(task_uid)

    context = {
        'task': task.to_dict(),
        'direct_relationships': {
            'applies_knowledge': list(task.applies_knowledge_uids),
            'prerequisites': list(task.prerequisite_task_uids),
            'parent': task.parent_uid,
            'goal': task.fulfills_goal_uid,
        }
    }

    if not include_deep_context:
        return Result.ok(context)

    # Pattern 2: Get deep context based on task characteristics

    # Determine query intent from model (Pattern 1 → Pattern 2)
    intent = task.get_suggested_query_intent()

    # Multi-hop graph analysis
    graph_context = await self.graph_intelligence.get_context(
        node_uid=task.uid,
        intent=intent,
        depth=2
    )

    context.update({
        'graph_context': {
            'total_relationships': graph_context.total_relationships,
            'hidden_connections': graph_context.inferred_relationships,
            'cross_domain_links': graph_context.cross_domain_relationships,
            'knowledge_gaps': graph_context.identify_knowledge_gaps(),
            'learning_opportunities': graph_context.find_learning_opportunities(),
            'impact_score': graph_context.calculate_impact_score()
        }
    })

    return Result.ok(context)
```

#### Example 4: Cross-Domain Analytics

```python
async def analyze_learning_path(self, user_uid: str) -> Result[dict]:
    """Analyze user's learning path with cross-domain insights."""

    # Pattern 1: Get user's active tasks (simple query)
    tasks = await self.backend.find_by(
        user_uid=user_uid,
        status=ActivityStatus.IN_PROGRESS
    )

    analytics = {
        'total_tasks': len(tasks),
        'with_knowledge': sum(1 for t in tasks if t.applies_knowledge_uids),  # Pattern 1
        'learning_tasks': sum(1 for t in tasks if t.is_learning_task()),  # Pattern 1
    }

    # Pattern 2: Deep cross-domain analysis for each learning task
    learning_insights = []
    for task in [t for t in tasks if t.is_learning_task()]:
        # Cross-domain query: Task → Knowledge → Goal → Learning Path
        context = await self.graph_intelligence.get_context(
            node_uid=task.uid,
            intent=QueryIntent.RELATIONSHIP,
            depth=3
        )

        learning_insights.append({
            'task_uid': task.uid,
            'direct_knowledge': len(task.applies_knowledge_uids),  # Pattern 1
            'inferred_knowledge': len(context.inferred_relationships),  # Pattern 2
            'knowledge_depth': context.calculate_knowledge_depth(),  # Pattern 2
            'learning_path_progress': context.get_learning_path_progress(),  # Pattern 2
            'recommended_next_steps': context.recommend_next_steps(),  # Pattern 2
        })

    analytics['learning_insights'] = learning_insights
    return Result.ok(analytics)
```

---

## Using Both Patterns Together

The patterns are **complementary** - use them together for optimal results.

### Example 1: Task Creation with Smart Validation

```python
async def create_task_with_validation(
    self,
    task_request: TaskCreateRequest
) -> Result[Task]:
    """Create task using both patterns for comprehensive validation."""

    # ========================================
    # Pattern 1: Quick instant validations
    # ========================================

    # Instant check - no DB query
    if len(task_request.prerequisite_task_uids) > 20:
        return Result.fail("Too many direct prerequisites (max 20)")

    # Instant check - no DB query
    if task_request.parent_uid and len(task_request.subtask_uids) > 0:
        return Result.fail("Task cannot be both parent and subtask")

    # Instant type check - no DB query
    if len(task_request.applies_knowledge_uids) == 0 and task_request.knowledge_mastery_check:
        return Result.fail("Mastery check requires applied knowledge")

    # ========================================
    # Pattern 2: Deep graph validations
    # ========================================

    # Only do deep validation if task has knowledge requirements
    if task_request.prerequisite_knowledge_uids:
        # Multi-hop check: Are knowledge prerequisites available?
        for ku_uid in task_request.prerequisite_knowledge_uids:
            context = await self.graph_intelligence.get_context(
                node_uid=ku_uid,
                intent=QueryIntent.PREREQUISITE,
                depth=2
            )

            # Check entire prerequisite chain
            if not context.all_prerequisites_available():
                missing = context.get_missing_prerequisites()
                return Result.fail(
                    f"Knowledge {ku_uid} has unmet prerequisites: {missing}"
                )

    # Cross-domain validation: Check if goal is achievable
    if task_request.fulfills_goal_uid:
        goal_context = await self.graph_intelligence.get_context(
            node_uid=task_request.fulfills_goal_uid,
            intent=QueryIntent.HIERARCHICAL,
            depth=2
        )

        if not goal_context.is_active():
            return Result.fail("Cannot create task for inactive goal")

    # ========================================
    # Create task
    # ========================================

    task = Task(**task_request.dict())
    result = await self.backend.create(task)

    return result
```

### Example 2: Smart Query Intent Selection

```python
@dataclass(frozen=True)
class Task:
    """Task uses Pattern 1 fields to determine Pattern 2 strategy."""

    prerequisite_task_uids: tuple[str, ...] = ()
    applies_knowledge_uids: tuple[str, ...] = ()
    completion_unlocks_knowledge: tuple[str, ...] = ()

    def get_suggested_query_intent(self) -> QueryIntent:
        """
        Pattern 1 → Pattern 2 bridge.

        Use model's relationship fields (Pattern 1) to determine
        the best graph query strategy (Pattern 2).
        """
        # Check direct relationships (instant, no DB)
        if len(self.prerequisite_task_uids) > 0:
            return QueryIntent.PREREQUISITE

        if len(self.completion_unlocks_knowledge) > 0:
            return QueryIntent.HIERARCHICAL

        if len(self.applies_knowledge_uids) > 0:
            return QueryIntent.PRACTICE

        return QueryIntent.RELATIONSHIP

# Usage in service
async def get_smart_task_context(self, task_uid: str) -> Result[dict]:
    """Use Pattern 1 to optimize Pattern 2 query."""

    # Pattern 1: Get task (single query)
    task = await self.get_task(task_uid)

    # Pattern 1 → Pattern 2: Use model to choose query strategy
    intent = task.get_suggested_query_intent()

    # Pattern 2: Execute optimized graph query
    context = await self.graph_intelligence.get_context(
        node_uid=task.uid,
        intent=intent,  # Optimized based on model
        depth=2
    )

    return Result.ok(context)
```

### Example 3: Progressive Complexity

```python
async def get_task_dependencies(
    self,
    task_uid: str,
    depth: str = 'shallow'  # 'shallow', 'medium', 'deep'
) -> Result[dict]:
    """Progressive complexity based on user needs."""

    # Pattern 1: Always start with direct relationships (instant)
    task = await self.get_task(task_uid)

    result = {
        'direct_prerequisites': list(task.prerequisite_task_uids),
        'prerequisite_count': len(task.prerequisite_task_uids),
    }

    # Shallow: Just direct relationships (Pattern 1 only)
    if depth == 'shallow':
        return Result.ok(result)

    # Medium: 2-hop dependencies (Pattern 2, limited depth)
    if depth == 'medium':
        query = task.build_dependency_query(depth=2)
        deps = await self.graph_intelligence.execute_graph_query(query)
        result['dependency_tree'] = deps
        return Result.ok(result)

    # Deep: Full analysis (Pattern 2, deep + analytics)
    if depth == 'deep':
        query = task.build_dependency_query(depth=4)
        deps = await self.graph_intelligence.execute_graph_query(query)

        # Add analytics (Pattern 2 only)
        result.update({
            'dependency_tree': deps,
            'critical_path': deps.find_critical_path(),
            'estimated_time': deps.calculate_total_time(),
            'blocking_tasks': deps.find_blocking_tasks(),
            'knowledge_gaps': deps.identify_knowledge_gaps(),
        })
        return Result.ok(result)
```

---

## Pattern Selection Matrix

| Use Case | Pattern | Why |
|----------|---------|-----|
| Check if task has parent | **P1** | Instant check, no DB query |
| Find all subtasks | **P1** | Simple query, single hop |
| Validate prerequisites before save | **P1** | Fast pre-save check |
| Display task card with direct links | **P1** | UI needs direct connections only |
| Model business logic method | **P1** | Model can decide without DB |
| Get full dependency tree | **P2** | Multi-hop traversal needed |
| Analyze completion impact | **P2** | Cross-domain effects |
| Find hidden knowledge connections | **P2** | Inferred relationships |
| Askesis chatbot context | **P2** | Rich, deep context needed |
| Learning path analytics | **P2** | Cross-domain analytics |
| Relationship strength scoring | **P2** | Graph-wide analysis |
| Check if task is learning task | **P1** | Model method, instant |
| Get practice opportunities | **P2** | Semantic graph query |
| Task creation validation (quick) | **P1** | Pre-save, instant |
| Task creation validation (deep) | **P2** | Multi-hop prerequisite check |
| Dashboard task counts | **P1** | Simple aggregations |
| Dashboard impact analysis | **P2** | Deep analytics |

---

## Code Review Checklist

When reviewing code that accesses relationships, ask:

### Pattern 1 Usage ✅

- [ ] Is this a direct relationship check?
- [ ] Does the model already have the UID field?
- [ ] Would a DB query be unnecessary overhead?
- [ ] Is this for validation or business logic?
- [ ] Is type safety important here?

**If YES to most** → Pattern 1 is correct

### Pattern 2 Usage ✅

- [ ] Does this need multi-hop traversal?
- [ ] Is this cross-domain analysis?
- [ ] Are hidden connections needed?
- [ ] Is this for analytics or intelligence?
- [ ] Does this need semantic relationships?

**If YES to most** → Pattern 2 is correct

### Anti-Patterns ❌

- [ ] ❌ Using graph query for single-hop check (use Pattern 1)
- [ ] ❌ Doing DB query when model already has UID (use Pattern 1)
- [ ] ❌ Trying to traverse N-hops with only UIDs (use Pattern 2)
- [ ] ❌ Missing deep validation for critical operations (use Pattern 2)
- [ ] ❌ Not using model fields to optimize query intent (combine patterns)

---

## Pattern Annotations (Code Convention)

### Docstring Pattern Badges

Use **pattern badges** in docstrings to document which pattern(s) a method uses:

| Badge | Meaning | When to Use |
|-------|---------|-------------|
| `[P1]` | Pattern 1 only | Method uses only relationship UIDs |
| `[P2]` | Pattern 2 only | Method uses only graph queries |
| `[P1 + P2]` | Both patterns | Method uses both patterns together |

### Annotation Format

**Pattern 1 Methods**:
```python
async def check_prerequisites(self, task: Task) -> bool:
    """
    [P1] Check if task prerequisites are met.

    Pattern 1 (Graph-Aware Models): Instant check using relationship UIDs.

    For deep prerequisite analysis, use Pattern 2:
        query = task.build_dependency_query(depth=3)
        full_deps = await graph_service.execute_graph_query(query)
    """
    return len(task.prerequisite_task_uids) == 0
```

**Pattern 2 Methods**:
```python
async def analyze_dependencies(self, task_uid: str) -> Result[dict]:
    """
    [P2] Analyze full dependency tree.

    Pattern 2 (Graph-Native Queries): Multi-hop traversal via GraphIntelligenceService.

    Uses task.build_dependency_query() for APOC-optimized graph traversal.
    For direct prerequisite checks, use Pattern 1: task.prerequisite_task_uids

    Args:
        task_uid: Task identifier
        depth: Traversal depth (default 3)

    Returns:
        Complete dependency tree with cross-domain connections
    """
    query = task.build_dependency_query(depth=3)
    return await self.graph_intelligence.execute_graph_query(query)
```

**Combined Pattern Methods**:
```python
async def create_task_validated(self, request: TaskCreateRequest) -> Result[Task]:
    """
    [P1 + P2] Create task with comprehensive validation.

    **Pattern Integration**: Uses BOTH patterns for optimal validation.

    Pattern 1: Quick instant validations (pre-save, no DB)
    Pattern 2: Deep multi-hop prerequisite chain validation

    Args:
        request: Task creation request

    Returns:
        Created task or validation error

    Example:
        # Pattern 1: Instant checks
        if len(request.prerequisite_task_uids) > 20:
            return Result.fail("Too many prerequisites")

        # Pattern 2: Deep validation
        context = await graph_intelligence.get_context(...)
        if not context.all_prerequisites_met():
            return Result.fail("Prerequisite chain incomplete")
    """
    # Pattern 1 validation
    if len(request.prerequisite_task_uids) > 20:
        return Result.fail("Too many prerequisites")

    # Pattern 2 validation
    context = await self.graph_intelligence.get_context(...)
```

### Domain Model Annotations

Add pattern badges to **domain model docstrings** to document which pattern the model supports:

```python
@dataclass(frozen=True)
class Task:
    """
    Task domain model with graph-aware relationships.

    ## Graph Access Patterns

    This model implements BOTH patterns:

    **Pattern 1 (Graph-Aware Models)**: Direct relationship UIDs
    - Fields: parent_uid, subtask_uids, prerequisite_task_uids
    - Methods: is_learning_task(), has_prerequisites() [marked with [P1]]
    - Use for: Instant checks, validation, simple queries

    **Pattern 2 (Graph-Native Queries)**: Graph intelligence
    - Methods: build_dependency_query(), build_completion_impact_query() [marked with [P2]]
    - Use for: Multi-hop traversal, cross-domain analysis, Askesis context

    **Example - Using Both Patterns Together**:
    ```python
    # Pattern 1: Quick validation
    if task.has_prerequisites():  # Instant
        print(f"Has {len(task.prerequisite_task_uids)} prerequisites")

    # Pattern 2: Deep analysis
    if task.is_learning_task():  # Pattern 1 informs Pattern 2
        query = task.build_knowledge_context_query(depth=2)
        context = await graph_service.execute_graph_query(query)
    ```
    """
    uid: str
    title: str
    parent_uid: Optional[str] = None  # Pattern 1 field
    prerequisite_task_uids: tuple[str, ...] = ()  # Pattern 1 field
```

### Code Review Pattern Badges

When reviewing pull requests, use pattern badges in review comments:

```markdown
**[P1]** This should use model UIDs instead of a graph query:
- Current: `context = await graph_intelligence.get_context(task.uid, depth=1)`
- Suggested: `has_parent = task.parent_uid is not None`

**[P2]** This needs multi-hop traversal, not just UIDs:
- Current: `for prereq_uid in task.prerequisite_task_uids: ...` (N+1 queries)
- Suggested: `query = task.build_dependency_query(depth=3)` (single query)

**[P1 + P2]** Good pattern integration! Quick check followed by deep analysis.
```

### Example: Fully Annotated Service Method

```python
class TasksService:
    async def get_task_with_context(
        self,
        uid: str,
        depth: int = 2
    ) -> Result[tuple[Task, 'GraphContext']]:
        """
        [P1 + P2] Get task with full graph context.

        **Pattern Integration**: Uses BOTH patterns for optimal intelligence.

        Pattern 1: Task model's get_suggested_query_intent() chooses strategy
        Pattern 2: Executes deep graph traversal via GraphIntelligenceService

        This achieves 8-10x performance improvement over sequential queries.

        Args:
            uid: Task UID
            depth: Maximum graph traversal depth (default 2)

        Returns:
            Result containing tuple of (Task, GraphContext)

        Example:
            # Pattern 1 informs Pattern 2
            task, context = await service.get_task_with_context("task.123", depth=3)

            # Pattern 1: Check direct relationships
            if task.has_prerequisites():
                print(f"Direct prerequisites: {task.prerequisite_task_uids}")

            # Pattern 2: Analyze deep context
            print(f"Total graph context: {context.total_relationships} relationships")
        """
        # Pattern 1: Get task with direct relationships
        task_result = await self.get_task(uid)
        if task_result.is_error:
            return task_result

        task = task_result.value

        # Pattern 1 → Pattern 2: Use model to choose query intent
        intent = task.get_suggested_query_intent()

        # Pattern 2: Execute optimized graph query
        graph_context_result = await self.graph_intel.query_with_intent(
            node_uid=uid,
            intent=intent,
            depth=depth
        )

        return Result.ok((task, graph_context_result.value))
```

---

## Performance Considerations

### Pattern 1 Performance

✅ **Optimal for**:
- Instant checks (O(1) - no DB query)
- Simple queries (1 DB query, single table)
- High-frequency operations (API responses, UI updates)
- Validation (pre-save, no round-trip)

❌ **Not suitable for**:
- Multi-hop traversal (would need N queries)
- Cross-domain analysis (need joins/traversal)
- Hidden connection discovery (UIDs don't show inferred links)

### Pattern 2 Performance

✅ **Optimal for**:
- Complex graph queries (single optimized query vs N queries)
- Cross-domain analysis (single traversal vs multiple joins)
- Analytics (aggregate across graph efficiently)
- Rare but important operations (detailed analysis, AI features)

❌ **Not suitable for**:
- High-frequency checks (DB query overhead)
- Simple direct relationships (unnecessary complexity)
- Pre-save validation (adds latency)

### Optimization Strategy

**Hot Path** (high frequency):
```python
# Use Pattern 1 - instant, no DB overhead
if task.has_prerequisites():  # Instant
    return "Task blocked"
```

**Cold Path** (low frequency, high value):
```python
# Use Pattern 2 - comprehensive but slower
context = await graph_intelligence.get_context(task.uid, depth=3)
return context.full_analysis()
```

---

## Migration Guide

### From Pattern 1 to Pattern 2

If you find yourself doing multiple Pattern 1 queries in a loop, consider Pattern 2:

**❌ Anti-pattern** (N+1 queries):
```python
# Bad: Multiple DB queries
for prereq_uid in task.prerequisite_task_uids:
    prereq_task = await self.get_task(prereq_uid)
    for prereq_prereq_uid in prereq_task.prerequisite_task_uids:
        prereq_prereq = await self.get_task(prereq_prereq_uid)
        # ... keeps going
```

**✅ Better** (single graph query):
```python
# Good: Single graph query
query = task.build_dependency_query(depth=3)
deps = await self.graph_intelligence.execute_graph_query(query)
# Returns entire tree in one query
```

### From Pattern 2 to Pattern 1

If you find yourself doing complex queries for simple checks, use Pattern 1:

**❌ Anti-pattern** (unnecessary graph query):
```python
# Bad: Complex query for simple check
context = await graph_intelligence.get_context(task.uid, depth=1)
has_parent = len(context.parents) > 0
```

**✅ Better** (instant check):
```python
# Good: Instant model check
has_parent = task.parent_uid is not None
```

---

## FAQ

### Q: When should I add a new UID field vs. using queries?

**A:** Add UID field (Pattern 1) if:
- Relationship is **direct and frequently accessed**
- You need **instant validation** or business logic
- It's a **1:1 or 1:many direct relationship**

Use queries only (Pattern 2) if:
- Relationship is **inferred or computed**
- Only needed for **analytics/intelligence**
- Traversal is **complex or semantic**

### Q: Can I mix both patterns in the same method?

**A:** Yes! This is encouraged. Use Pattern 1 for quick checks, then Pattern 2 for deep analysis when needed.

```python
# Pattern 1: Quick check
if not task.has_prerequisites():
    return Result.ok("Can start immediately")

# Pattern 2: Deep analysis if needed
if task.is_milestone_task():
    impact = await self.analyze_completion_impact(task.uid)
    return Result.ok(impact)
```

### Q: How do I decide query depth for Pattern 2?

**A:** Use business rules:

- **Depth 1**: Immediate neighbors only
- **Depth 2**: Neighbors + their neighbors (most common)
- **Depth 3**: Three hops (comprehensive analysis)
- **Depth 4+**: Rare, for full graph analysis

**Default to depth=2** unless you have a specific reason for more or less.

### Q: What if a relationship doesn't exist in the model?

**A:** Check if it should:
- If it's **direct and frequently used** → Add to model (Pattern 1)
- If it's **inferred or rare** → Use queries only (Pattern 2)
- If it's **cross-domain** → Definitely Pattern 2

### Q: How do I test Pattern 2 code?

**A:** Mock the GraphIntelligenceService:

```python
@pytest.fixture
def mock_graph_intelligence():
    mock = Mock(spec=GraphIntelligenceService)
    mock.get_context.return_value = create_mock_graph_context(...)
    return mock

async def test_analyze_impact(mock_graph_intelligence):
    service = TasksService(backend=mock_backend, graph_intelligence=mock_graph_intelligence)
    result = await service.analyze_completion_impact("task_uid")

    mock_graph_intelligence.get_context.assert_called_once_with(
        node_uid="task_uid",
        intent=QueryIntent.HIERARCHICAL,
        depth=2
    )
```

---

## Related Documentation

- **Architecture**: `/docs/100_PERCENT_DYNAMIC_ARCHITECTURE.md`
- **Query Infrastructure**: `/core/models/query/README.md`
- **Graph Intelligence**: `/core/services/graph_intelligence_service.py`
- **Domain Models**: `/core/models/*/README.md`
- **CLAUDE.md**: Section on "Query Infrastructure"

---

## Changelog

### v1.0 - October 8, 2025
- Initial documentation
- Decision tree and pattern selection matrix
- Code examples for both patterns
- Performance considerations
- Migration guide

---

**Remember**: Both patterns are essential. Use Pattern 1 for speed and simplicity, Pattern 2 for depth and intelligence. Together, they provide optimal graph access functionality.
