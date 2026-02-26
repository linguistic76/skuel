---
title: Graph Access Patterns Guide
updated: 2026-02-18
category: patterns
related_skills:
- pytest
- neo4j-cypher-patterns
related_docs: []
---

# Graph Access Patterns Guide

**Version**: 2.0
**Date**: February 18, 2026
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

**Architectural Principle (February 2026):** Domain models express *intent* (what kind of query is appropriate), infrastructure builds *queries* (how to execute it). Models never generate Cypher strings — that knowledge lives in `core.models.query.graph_traversal` and the persistence adapter.

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
class Ku:
    """Unified domain model with graph-aware relationships."""

    uid: str
    title: str

    # Graph-aware relationship fields
    parent_uid: str | None = None
    fulfills_goal_uid: str | None = None
    reinforces_habit_uid: str | None = None
    source_learning_step_uid: str | None = None
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
| **Performance** | O(1) access - no DB query needed |
| **Type Safety** | Strongly typed with `str \| None` and `tuple[str, ...]` |
| **Validation** | Pre-save checks without DB round-trip |
| **Business Logic** | Model methods can check relationships instantly |
| **Simplicity** | Straightforward code, easy to understand |

### Code Examples

#### Example 1: Instant Relationship Checks

```python
# No DB query needed - instant check
def can_start(ku: Ku) -> bool:
    """Check if entity has no unfulfilled goal dependency."""
    return ku.fulfills_goal_uid is None or ku.is_completed

# Instant parent check
if ku.parent_uid:
    print(f"This is a child of {ku.parent_uid}")
```

#### Example 2: Simple Queries

```python
# Single query - find all subtasks
subtasks = await backend.find_by(parent_uid=parent_uid)

# Single query - find entities for a goal
goal_entities = await backend.find_by(fulfills_goal_uid=goal_uid)
```

#### Example 3: Pre-Save Validation

```python
async def create_task(self, task_request: TaskCreateRequest) -> Result[Ku]:
    """Create task with instant validation."""

    # Pattern 1: Instant validation (no DB query)
    if task_request.parent_uid and task_request.fulfills_goal_uid:
        return Result.fail(Errors.validation(
            "Cannot set both parent and goal", field="parent_uid"
        ))

    # Create entity
    result = await self.backend.create(ku)
    return result
```

#### Example 4: Business Logic Methods

```python
@dataclass(frozen=True)
class Ku:
    parent_uid: str | None = None
    fulfills_goal_uid: str | None = None
    source_learning_step_uid: str | None = None

    @property
    def is_from_learning_step(self) -> bool:
        """Check if this entity originated from a learning step."""
        return self.source_learning_step_uid is not None

    @property
    def parent_goal_uid(self) -> str | None:
        """Alias for fulfills_goal_uid."""
        return self.fulfills_goal_uid
```

---

## Pattern 2: Graph-Native Queries

### What It Is

Complex graph queries using **GraphIntelligenceService** and **GraphContextOrchestrator**, where domain models express *intent* and infrastructure builds Cypher:

```python
# Model expresses intent (domain logic)
intent = ku.get_suggested_query_intent()

# Infrastructure builds and executes query (persistence logic)
context = await graph_intelligence.query_with_intent(
    domain=Domain.TASKS,
    node_uid=ku.uid,
    intent=intent,
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
| **Deep Traversal** | Multi-hop relationships (N levels deep) |
| **Cross-Domain** | Traverse Task → Knowledge → Goal seamlessly |
| **Discovery** | Find hidden connections and patterns |
| **Analytics** | Compute impact scores, relationship strength |
| **Intelligence** | Rich context for AI/ML features |
| **Semantic** | Type-aware relationship traversal |

### Architectural Separation

Domain models **express intent**, infrastructure **builds queries**:

| Responsibility | Location | Example |
|---------------|----------|---------|
| Suggest query intent | `Ku.get_suggested_query_intent()` | Returns `QueryIntent.PREREQUISITE` |
| Build Cypher query | `graph_traversal.build_graph_context_query()` | Generates Cypher string |
| Execute query | `GraphIntelligenceService.query_with_intent()` | Runs against Neo4j |
| Orchestrate flow | `GraphContextOrchestrator.get_with_context()` | Combines all steps |

This separation means domain models have zero Cypher dependencies — if the persistence layer changed from Neo4j to PostgreSQL, the domain models wouldn't need to change.

### Code Examples

#### Example 1: Multi-Hop Dependencies

```python
async def get_full_dependency_tree(self, task_uid: str) -> Result[dict]:
    """Get complete dependency tree (3 levels deep)."""

    task_result = await self.backend.get(task_uid)
    if task_result.is_error:
        return task_result

    task = task_result.value

    # Pattern 2: Deep traversal via infrastructure
    context_result = await self.graph_intelligence.query_with_intent(
        domain=Domain.TASKS,
        node_uid=task.uid,
        intent=QueryIntent.PREREQUISITE,
        depth=3
    )

    if context_result.is_error:
        return context_result

    context = context_result.value
    return Result.ok({
        'dependency_tree': context.nodes,
        'total_depth': context.max_depth,
        'cross_domain_deps': context.cross_domain_relationships
    })
```

#### Example 2: Completion Impact Analysis

```python
async def analyze_completion_impact(self, task_uid: str) -> Result[dict]:
    """Analyze what happens when task completes."""

    task_result = await self.backend.get(task_uid)
    if task_result.is_error:
        return task_result

    task = task_result.value

    # Pattern 2: Cross-domain impact via graph intelligence
    impact_result = await self.graph_intelligence.query_with_intent(
        domain=Domain.TASKS,
        node_uid=task.uid,
        intent=QueryIntent.HIERARCHICAL,
        depth=2
    )

    if impact_result.is_error:
        return impact_result

    impact = impact_result.value
    return Result.ok({
        'immediate_impact': {
            'goals': [task.fulfills_goal_uid] if task.fulfills_goal_uid else [],
        },
        'ripple_effects': impact.downstream_impacts,
        'cross_domain_effects': impact.cross_domain_impacts,
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
    task_result = await self.backend.get(task_uid)
    if task_result.is_error:
        return task_result

    task = task_result.value

    context = {
        'task': task.to_dto().to_dict(),
        'direct_relationships': {
            'parent': task.parent_uid,
            'goal': task.fulfills_goal_uid,
        }
    }

    if not include_deep_context:
        return Result.ok(context)

    # Pattern 2: Model expresses intent, infrastructure builds query
    intent = task.get_suggested_query_intent()

    graph_context_result = await self.graph_intelligence.query_with_intent(
        domain=Domain.TASKS,
        node_uid=task.uid,
        intent=intent,
        depth=2
    )

    if graph_context_result.is_error:
        return graph_context_result

    graph_context = graph_context_result.value
    context.update({
        'graph_context': {
            'total_relationships': graph_context.total_relationships,
            'cross_domain_links': graph_context.cross_domain_relationships,
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
        status=EntityStatus.ACTIVE
    )

    analytics = {
        'total_tasks': len(tasks),
        'learning_tasks': sum(1 for t in tasks if t.source_learning_step_uid),
    }

    # Pattern 2: Deep cross-domain analysis via infrastructure
    learning_insights = []
    for task in [t for t in tasks if t.source_learning_step_uid]:
        context_result = await self.graph_intelligence.query_with_intent(
            domain=Domain.TASKS,
            node_uid=task.uid,
            intent=QueryIntent.RELATIONSHIP,
            depth=3
        )

        if context_result.is_ok:
            context = context_result.value
            learning_insights.append({
                'task_uid': task.uid,
                'knowledge_depth': context.total_nodes,
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
) -> Result[Ku]:
    """Create task using both patterns for comprehensive validation."""

    # ========================================
    # Pattern 1: Quick instant validations
    # ========================================

    # Instant check - no DB query
    if task_request.parent_uid and task_request.fulfills_goal_uid:
        return Result.fail(Errors.validation(
            "Cannot set both parent and goal", field="parent_uid"
        ))

    # ========================================
    # Pattern 2: Deep graph validations
    # ========================================

    # Only do deep validation if task has knowledge requirements
    if task_request.source_learning_step_uid:
        context_result = await self.graph_intelligence.query_with_intent(
            domain=Domain.CURRICULUM,
            node_uid=task_request.source_learning_step_uid,
            intent=QueryIntent.PREREQUISITE,
            depth=2
        )

        if context_result.is_ok and not context_result.value.all_prerequisites_available():
            return Result.fail(
                Errors.business("prerequisites_unmet", "Learning step has unmet prerequisites")
            )

    # ========================================
    # Create task
    # ========================================
    result = await self.backend.create(ku)
    return result
```

### Example 2: Smart Query Intent Selection

```python
@dataclass(frozen=True)
class Ku:
    """Domain model uses its own state to suggest query intent."""

    def get_suggested_query_intent(self) -> QueryIntent:
        """
        Pattern 1 → Pattern 2 bridge.

        Use model's characteristics (Pattern 1) to determine
        the best graph query strategy (Pattern 2).

        The model expresses WHAT kind of query is appropriate.
        Infrastructure decides HOW to build it.
        """
        if self.is_foundational():
            return QueryIntent.HIERARCHICAL
        elif self.is_terminal():
            return QueryIntent.PREREQUISITE
        elif self.is_connected():
            return QueryIntent.RELATIONSHIP
        elif self.is_basic():
            return QueryIntent.PRACTICE
        else:
            return QueryIntent.EXPLORATORY

# Usage in service
async def get_smart_context(self, uid: str) -> Result[dict]:
    """Use Pattern 1 to optimize Pattern 2 query."""

    # Pattern 1: Get entity (single query)
    entity_result = await self.backend.get(uid)
    if entity_result.is_error:
        return entity_result
    entity = entity_result.value

    # Pattern 1 → Pattern 2: Model suggests intent, infrastructure builds query
    intent = entity.get_suggested_query_intent()

    # Pattern 2: Execute via infrastructure
    context_result = await self.graph_intelligence.query_with_intent(
        domain=self.domain,
        node_uid=entity.uid,
        intent=intent,
        depth=2
    )

    return context_result
```

### Example 3: Progressive Complexity

```python
async def get_dependencies(
    self,
    uid: str,
    depth: str = 'shallow'  # 'shallow', 'medium', 'deep'
) -> Result[dict]:
    """Progressive complexity based on user needs."""

    # Pattern 1: Always start with direct relationships (instant)
    entity_result = await self.backend.get(uid)
    if entity_result.is_error:
        return entity_result
    entity = entity_result.value

    result = {
        'parent': entity.parent_uid,
        'goal': entity.fulfills_goal_uid,
    }

    # Shallow: Just direct relationships (Pattern 1 only)
    if depth == 'shallow':
        return Result.ok(result)

    # Medium/Deep: Graph traversal via infrastructure (Pattern 2)
    traversal_depth = 2 if depth == 'medium' else 4
    context_result = await self.graph_intelligence.query_with_intent(
        domain=self.domain,
        node_uid=uid,
        intent=QueryIntent.PREREQUISITE,
        depth=traversal_depth
    )

    if context_result.is_ok:
        result['dependency_tree'] = context_result.value.nodes

    return Result.ok(result)
```

---

## Pattern Selection Matrix

| Use Case | Pattern | Why |
|----------|---------|-----|
| Check if entity has parent | **P1** | Instant check, no DB query |
| Find all children | **P1** | Simple query, single hop |
| Validate relationships before save | **P1** | Fast pre-save check |
| Display card with direct links | **P1** | UI needs direct connections only |
| Model business logic method | **P1** | Model can decide without DB |
| Get full dependency tree | **P2** | Multi-hop traversal needed |
| Analyze completion impact | **P2** | Cross-domain effects |
| Find hidden knowledge connections | **P2** | Inferred relationships |
| Askesis chatbot context | **P2** | Rich, deep context needed |
| Learning path analytics | **P2** | Cross-domain analytics |
| Relationship strength scoring | **P2** | Graph-wide analysis |
| Get practice opportunities | **P2** | Semantic graph query |
| Task creation validation (quick) | **P1** | Pre-save, instant |
| Task creation validation (deep) | **P2** | Multi-hop prerequisite check |
| Dashboard entity counts | **P1** | Simple aggregations |
| Dashboard impact analysis | **P2** | Deep analytics |

---

## Code Review Checklist

When reviewing code that accesses relationships, ask:

### Pattern 1 Usage

- [ ] Is this a direct relationship check?
- [ ] Does the model already have the UID field?
- [ ] Would a DB query be unnecessary overhead?
- [ ] Is this for validation or business logic?
- [ ] Is type safety important here?

**If YES to most** → Pattern 1 is correct

### Pattern 2 Usage

- [ ] Does this need multi-hop traversal?
- [ ] Is this cross-domain analysis?
- [ ] Are hidden connections needed?
- [ ] Is this for analytics or intelligence?
- [ ] Does this need semantic relationships?
- [ ] Does the model express intent, with infrastructure building the query?

**If YES to most** → Pattern 2 is correct

### Anti-Patterns

- [ ] Using graph query for single-hop check (use Pattern 1)
- [ ] Doing DB query when model already has UID (use Pattern 1)
- [ ] Trying to traverse N-hops with only UIDs (use Pattern 2)
- [ ] Missing deep validation for critical operations (use Pattern 2)
- [ ] Not using model fields to optimize query intent (combine patterns)
- [ ] Domain model generating Cypher strings (move to infrastructure)

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
async def check_prerequisites(self, ku: Ku) -> bool:
    """
    [P1] Check if entity has a learning step source.

    Pattern 1 (Graph-Aware Models): Instant check using relationship UIDs.
    For deep prerequisite analysis, use Pattern 2 via GraphIntelligenceService.
    """
    return ku.source_learning_step_uid is not None
```

**Pattern 2 Methods**:
```python
async def analyze_dependencies(self, uid: str, depth: int = 3) -> Result[dict]:
    """
    [P2] Analyze full dependency tree.

    Pattern 2 (Graph-Native Queries): Multi-hop traversal via GraphIntelligenceService.
    Model expresses intent, infrastructure builds Cypher.
    For direct relationship checks, use Pattern 1 model fields.
    """
    context_result = await self.graph_intelligence.query_with_intent(
        domain=self.domain,
        node_uid=uid,
        intent=QueryIntent.PREREQUISITE,
        depth=depth
    )
    return context_result
```

**Combined Pattern Methods**:
```python
async def create_with_validation(self, request: TaskCreateRequest) -> Result[Ku]:
    """
    [P1 + P2] Create entity with comprehensive validation.

    Pattern 1: Quick instant validations (pre-save, no DB)
    Pattern 2: Deep multi-hop prerequisite chain validation via infrastructure
    """
    # Pattern 1 validation
    if request.parent_uid:
        ...  # Instant check

    # Pattern 2 validation
    context = await self.graph_intelligence.query_with_intent(...)
```

### Domain Model Annotations

Domain models express **intent**, not queries:

```python
@dataclass(frozen=True)
class Ku:
    """
    Unified domain model with graph-aware relationships.

    ## Graph Access Patterns

    **Pattern 1 (Graph-Aware Models)**: Direct relationship UIDs
    - Fields: parent_uid, fulfills_goal_uid, source_learning_step_uid
    - Use for: Instant checks, validation, simple queries

    **Pattern 2 (Graph-Native Queries)**: Graph intelligence via services
    - Method: get_suggested_query_intent() — expresses WHAT kind of query
    - Infrastructure builds HOW (Cypher generation in graph_traversal module)
    - Use for: Multi-hop traversal, cross-domain analysis, Askesis context
    """
    uid: str
    title: str
    parent_uid: str | None = None         # Pattern 1 field
    fulfills_goal_uid: str | None = None   # Pattern 1 field
```

### Code Review Pattern Badges

When reviewing pull requests, use pattern badges in review comments:

```markdown
**[P1]** This should use model UIDs instead of a graph query:
- Current: `context = await graph_intelligence.query_with_intent(uid, depth=1)`
- Suggested: `has_parent = ku.parent_uid is not None`

**[P2]** This needs multi-hop traversal, not just UIDs:
- Current: Looping through UIDs with N+1 queries
- Suggested: `await graph_intelligence.query_with_intent(node_uid=uid, intent=QueryIntent.PREREQUISITE, depth=3)`

**[P1 + P2]** Good pattern integration! Quick check followed by deep analysis.
```

### Example: Fully Annotated Service Method

```python
class TasksService:
    async def get_task_with_context(
        self,
        uid: str,
        depth: int = 2
    ) -> Result[tuple[Ku, GraphContext]]:
        """
        [P1 + P2] Get task with full graph context.

        Pattern 1: Ku model's get_suggested_query_intent() chooses strategy
        Pattern 2: Executes deep graph traversal via GraphIntelligenceService

        This achieves 8-10x performance improvement over sequential queries.
        """
        # Pattern 1: Get entity with direct relationships
        entity_result = await self.backend.get(uid)
        if entity_result.is_error:
            return entity_result

        entity = entity_result.value

        # Pattern 1 → Pattern 2: Model expresses intent
        intent = entity.get_suggested_query_intent()

        # Pattern 2: Infrastructure builds and executes query
        graph_context_result = await self.graph_intel.query_with_intent(
            domain=Domain.TASKS,
            node_uid=uid,
            intent=intent,
            depth=depth
        )

        if graph_context_result.is_error:
            return graph_context_result

        return Result.ok((entity, graph_context_result.value))
```

---

## Performance Considerations

### Pattern 1 Performance

**Optimal for**:
- Instant checks (O(1) - no DB query)
- Simple queries (1 DB query, single table)
- High-frequency operations (API responses, UI updates)
- Validation (pre-save, no round-trip)

**Not suitable for**:
- Multi-hop traversal (would need N queries)
- Cross-domain analysis (need joins/traversal)
- Hidden connection discovery (UIDs don't show inferred links)

### Pattern 2 Performance

**Optimal for**:
- Complex graph queries (single optimized query vs N queries)
- Cross-domain analysis (single traversal vs multiple joins)
- Analytics (aggregate across graph efficiently)
- Rare but important operations (detailed analysis, AI features)

**Not suitable for**:
- High-frequency checks (DB query overhead)
- Simple direct relationships (unnecessary complexity)
- Pre-save validation (adds latency)

### Optimization Strategy

**Hot Path** (high frequency):
```python
# Use Pattern 1 - instant, no DB overhead
if ku.parent_uid is not None:
    return "Entity has parent"
```

**Cold Path** (low frequency, high value):
```python
# Use Pattern 2 - comprehensive but slower
context = await graph_intelligence.query_with_intent(
    domain=Domain.TASKS, node_uid=uid,
    intent=QueryIntent.RELATIONSHIP, depth=3
)
return context
```

---

## Migration Guide

### From Pattern 1 to Pattern 2

If you find yourself doing multiple Pattern 1 queries in a loop, consider Pattern 2:

**Anti-pattern** (N+1 queries):
```python
# Bad: Multiple DB queries in a loop
for uid in entity.related_uids:
    related = await self.backend.get(uid)
    for nested_uid in related.related_uids:
        nested = await self.backend.get(nested_uid)
```

**Better** (single graph query):
```python
# Good: Single graph query via infrastructure
context = await self.graph_intelligence.query_with_intent(
    domain=self.domain,
    node_uid=entity.uid,
    intent=QueryIntent.PREREQUISITE,
    depth=3
)
# Returns entire tree in one query
```

### From Pattern 2 to Pattern 1

If you find yourself doing complex queries for simple checks, use Pattern 1:

**Anti-pattern** (unnecessary graph query):
```python
# Bad: Complex query for simple check
context = await graph_intelligence.query_with_intent(
    domain=Domain.TASKS, node_uid=uid, intent=QueryIntent.HIERARCHICAL, depth=1
)
has_parent = len(context.parents) > 0
```

**Better** (instant check):
```python
# Good: Instant model check
has_parent = ku.parent_uid is not None
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
if ku.parent_uid is None:
    return Result.ok("Can start immediately")

# Pattern 2: Deep analysis if needed
context = await self.graph_intelligence.query_with_intent(
    domain=self.domain, node_uid=ku.uid,
    intent=ku.get_suggested_query_intent(), depth=2
)
return Result.ok(context)
```

### Q: How do I decide query depth for Pattern 2?

**A:** Use business rules:

- **Depth 1**: Immediate neighbors only
- **Depth 2**: Neighbors + their neighbors (most common)
- **Depth 3**: Three hops (comprehensive analysis)
- **Depth 4+**: Rare, for full graph analysis

**Default to depth=2** unless you have a specific reason for more or less.

### Q: Should domain models build Cypher queries?

**A:** No. Domain models express *intent* via `get_suggested_query_intent()` which returns a `QueryIntent` enum. Infrastructure (`graph_traversal.build_graph_context_query()`, `GraphIntelligenceService`) translates intent into Cypher. This keeps the core free of persistence technology dependencies.

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
    mock = AsyncMock(spec=GraphIntelligenceService)
    mock.query_with_intent.return_value = Result.ok(create_mock_graph_context(...))
    return mock

async def test_analyze_impact(mock_graph_intelligence):
    service = TasksService(backend=mock_backend, graph_intelligence=mock_graph_intelligence)
    result = await service.analyze_completion_impact("task_uid")

    mock_graph_intelligence.query_with_intent.assert_called_once_with(
        domain=Domain.TASKS,
        node_uid="task_uid",
        intent=QueryIntent.HIERARCHICAL,
        depth=2
    )
```

---

## Related Documentation

- **Query Infrastructure**: `/core/models/query/graph_traversal.py` (Pure Cypher query builder)
- **Graph Intelligence**: `/core/services/intelligence/graph_context_orchestrator.py`
- **Domain Models**: `/core/models/ku/ku.py` (Unified Ku model)
- **CLAUDE.md**: Section on "Search & Query Architecture"

---

## Changelog

### v2.0 - February 18, 2026
- Updated Pattern 2 to reflect architectural separation: models express intent, infrastructure builds queries
- Removed all references to `entity.build_*_query()` methods (deleted from domain models)
- Updated code examples to use `GraphIntelligenceService.query_with_intent()` directly
- Added "Architectural Separation" table explaining responsibility boundaries
- Added anti-pattern: "Domain model generating Cypher strings"
- Added FAQ: "Should domain models build Cypher queries?"
- Updated from old Task/Habit/Goal model references to unified Ku model

### v1.0 - October 8, 2025
- Initial documentation
- Decision tree and pattern selection matrix
- Code examples for both patterns
- Performance considerations
- Migration guide
