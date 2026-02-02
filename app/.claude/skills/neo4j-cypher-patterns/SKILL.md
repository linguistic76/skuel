---
name: neo4j-cypher-patterns
description: Expert guide to Neo4j Cypher queries and SKUEL's graph patterns. Use when writing Cypher queries, optimizing graph traversals, understanding relationship types, analyzing query performance, or when the user mentions Cypher, Neo4j, graph queries, or asks about relationships between entities.
allowed-tools: Read, Grep, Glob
---

# Neo4j Cypher Patterns for SKUEL

## Quick Start

SKUEL uses Neo4j as its graph database with a 14-domain architecture. All domains flow toward LifePath (the destination).

### Entity Labels (Neo4j Node Labels)

| Domain | Label | UID Format | Example |
|--------|-------|------------|---------|
| Tasks | `Task` | `task:{uuid}` | `task:550e8400-e29b-41d4-a716-446655440000` |
| Goals | `Goal` | `goal:{uuid}` | `goal:123e4567-e89b-12d3-a456-426614174000` |
| Habits | `Habit` | `habit:{uuid}` | `habit:...` |
| Events | `Event` | `event:{uuid}` | `event:...` |
| Choices | `Choice` | `choice:{uuid}` | `choice:...` |
| Principles | `Principle` | `principle:{uuid}` | `principle:...` |
| Knowledge Units | `Ku` | `ku.{filename}` | `ku.python-basics` |
| Learning Steps | `Ls` | `ls.{name}` | `ls.intro-to-python` |
| Learning Paths | `Lp` | `lp.{name}` | `lp.become-python-developer` |
| Maps of Content | `Moc` | `moc.{name}` | `moc.programming-languages` |
| Users | `User` | `user:{uuid}` | `user:...` |
| Finance | `Expense` | `expense:{uuid}` | `expense:...` |

### Core Relationships (Most Common)

```cypher
// Ownership - User owns entities
(user:User)-[:HAS_TASK]->(task:Task)
(user:User)-[:HAS_GOAL]->(goal:Goal)
(user:User)-[:HAS_HABIT]->(habit:Habit)

// Knowledge application
(task:Task)-[:APPLIES_KNOWLEDGE]->(ku:Ku)
(goal:Goal)-[:REQUIRES_KNOWLEDGE]->(ku:Ku)
(habit:Habit)-[:REINFORCES_KNOWLEDGE]->(ku:Ku)

// Goal hierarchy
(task:Task)-[:FULFILLS_GOAL]->(goal:Goal)
(habit:Habit)-[:SUPPORTS_GOAL]->(goal:Goal)
(goal:Goal)-[:SUBGOAL_OF]->(parent:Goal)

// Knowledge structure
(ku:Ku)-[:REQUIRES_KNOWLEDGE]->(prereq:Ku)
(ku:Ku)-[:ENABLES]->(enabled:Ku)
(ku:Ku)-[:RELATED_TO]->(related:Ku)

// Principles guidance
(goal:Goal)-[:GUIDED_BY_PRINCIPLE]->(principle:Principle)
(choice:Choice)-[:ALIGNED_WITH_PRINCIPLE]->(principle:Principle)
```

## Query Patterns

### Pattern 1: Get User's Entities

```cypher
// Get all active tasks for a user
MATCH (u:User {uid: $user_uid})-[:HAS_TASK]->(t:Task)
WHERE t.status IN ['pending', 'in_progress']
RETURN t
ORDER BY t.priority DESC, t.due_date ASC
```

### Pattern 2: Entity with Graph Context

```cypher
// Get task with its full neighborhood
MATCH (t:Task {uid: $uid})
OPTIONAL MATCH (t)-[:APPLIES_KNOWLEDGE]->(ku:Ku)
OPTIONAL MATCH (t)-[:FULFILLS_GOAL]->(g:Goal)
OPTIONAL MATCH (t)-[:DEPENDS_ON]->(dep:Task)
RETURN t,
       collect(DISTINCT ku) as applied_knowledge,
       collect(DISTINCT g) as goals,
       collect(DISTINCT dep) as dependencies
```

### Pattern 3: Relationship Traversal

```cypher
// Find all knowledge required for a goal (including transitive)
MATCH (g:Goal {uid: $goal_uid})
MATCH path = (g)-[:REQUIRES_KNOWLEDGE*1..3]->(ku:Ku)
RETURN DISTINCT ku
ORDER BY length(path)
```

### Pattern 4: Graph-Aware Search

```cypher
// Search tasks with relationship filter
MATCH (t:Task)
WHERE t.title CONTAINS $query OR t.description CONTAINS $query
OPTIONAL MATCH (t)-[:APPLIES_KNOWLEDGE]->(ku:Ku)
WITH t, collect(ku) as knowledge
WHERE size(knowledge) > 0  // Only tasks that apply knowledge
RETURN t, knowledge
```

### Pattern 5: User Learning Progress

```cypher
// Get user's mastery state for knowledge units
MATCH (u:User {uid: $user_uid})-[r:MASTERED|IN_PROGRESS|VIEWED]->(ku:Ku)
RETURN ku.uid,
       type(r) as status,
       r.mastery_score as score,
       r.mastered_at as mastered_at
```

## Query Builders (SKUEL Infrastructure)

SKUEL has three query builders with clear responsibilities:

| Builder | Location | Use Case |
|---------|----------|----------|
| **CypherGenerator** | `core/models/query/cypher/` | Pure Cypher, semantic traversal (modular package) |
| **ApocQueryBuilder** | `core/models/query/query_models.py` | Batch ops, schema-aware merges |
| **UnifiedQueryBuilder** | `core/models/query/` | Generic CRUD (used by backends) |

### Two-Layer Architecture

```
Layer 1: Backend (Generic CRUD)
├── UniversalNeo4jBackend uses UnifiedQueryBuilder
└── Powers ALL 12+ domains with generic operations

Layer 2: Services (Semantic Queries)
├── Domain services use CypherGenerator
└── Specialized queries for business logic
```

## Filter Operators

All query builders support these operators:

| Operator | Usage | Cypher Output |
|----------|-------|---------------|
| `eq` (default) | `priority='high'` | `n.priority = 'high'` |
| `gt` | `due_date__gt=date` | `n.due_date > $date` |
| `lt` | `hours__lt=5.0` | `n.hours < 5.0` |
| `gte` | `due_date__gte=date` | `n.due_date >= $date` |
| `lte` | `score__lte=8` | `n.score <= 8` |
| `contains` | `title__contains='urgent'` | `n.title CONTAINS 'urgent'` |
| `in` | `priority__in=['high', 'urgent']` | `n.priority IN ['high', 'urgent']` |

## Intent-Based Traversal

Each domain has a suggested `QueryIntent` that optimizes graph queries:

| Domain | Intent | Focus Relationships |
|--------|--------|---------------------|
| Tasks | `PRACTICE` | EXECUTES_TASK, REQUIRES_KNOWLEDGE, DEPENDS_ON |
| Goals | `GOAL_ACHIEVEMENT` | FULFILLS_GOAL, SUPPORTS_GOAL, SUBGOAL_OF |
| Principles | `PRINCIPLE_EMBODIMENT` | GUIDED_BY_PRINCIPLE, INSPIRES_HABIT |
| Habits | `PRACTICE` | REINFORCES_KNOWLEDGE, SUPPORTS_GOAL |
| Choices | `PRINCIPLE_ALIGNMENT` | ALIGNED_WITH_PRINCIPLE, INFORMED_BY_KNOWLEDGE |
| Events | `SCHEDULED_ACTION` | EXECUTES_TASK, PRACTICES_KNOWLEDGE |

## Best Practices

### 1. Always Use Parameters

```cypher
// GOOD - parameterized
MATCH (t:Task {uid: $uid})

// BAD - string interpolation (SQL injection risk)
MATCH (t:Task {uid: '${uid}'})
```

### 2. Use OPTIONAL MATCH for Nullable Relationships

```cypher
// GOOD - returns task even without knowledge
MATCH (t:Task {uid: $uid})
OPTIONAL MATCH (t)-[:APPLIES_KNOWLEDGE]->(ku:Ku)

// RISKY - returns nothing if no knowledge relationship
MATCH (t:Task {uid: $uid})-[:APPLIES_KNOWLEDGE]->(ku:Ku)
```

### 3. Use COLLECT to Prevent Cartesian Products

```cypher
// GOOD - one row per task
MATCH (t:Task {uid: $uid})
OPTIONAL MATCH (t)-[:APPLIES_KNOWLEDGE]->(ku:Ku)
OPTIONAL MATCH (t)-[:FULFILLS_GOAL]->(g:Goal)
RETURN t, collect(DISTINCT ku) as knowledge, collect(DISTINCT g) as goals

// BAD - cartesian product of knowledge × goals
MATCH (t:Task {uid: $uid})
OPTIONAL MATCH (t)-[:APPLIES_KNOWLEDGE]->(ku:Ku)
OPTIONAL MATCH (t)-[:FULFILLS_GOAL]->(g:Goal)
RETURN t, ku, g
```

### 4. Use RelationshipName Enum

```python
from core.models.relationship_names import RelationshipName

# GOOD - type-safe, IDE autocomplete
rel = RelationshipName.REQUIRES_KNOWLEDGE
query = f"MATCH (a)-[:{rel.value}]->(b)"

# BAD - typo-prone, no compile-time check
query = "MATCH (a)-[:REQURES_KNOWLEDGE]->(b)"  # typo!
```

### 5. Check Ownership for Multi-Tenant Security

```cypher
// GOOD - ownership verified
MATCH (u:User {uid: $user_uid})-[:HAS_TASK]->(t:Task {uid: $task_uid})
RETURN t

// BAD - no ownership check (security risk)
MATCH (t:Task {uid: $task_uid})
RETURN t
```

## Additional Resources

- [reference.md](reference.md) - Complete relationship type catalog (80+ types)
- [examples.md](examples.md) - Full query examples for each domain

## Related Skills

- **[skuel-search-architecture](../skuel-search-architecture/SKILL.md)** - Unified search using Cypher patterns
- **[python](../python/SKILL.md)** - Python services executing Cypher queries

## Deep Dive Resources

**Architecture:**
- [NEO4J_DATABASE_ARCHITECTURE.md](/docs/architecture/NEO4J_DATABASE_ARCHITECTURE.md) - Graph database architecture
- [LATERAL_RELATIONSHIPS_CORE.md](/docs/architecture/LATERAL_RELATIONSHIPS_CORE.md) - Lateral relationship patterns
- [ADR-037](/docs/decisions/ADR-037-lateral-relationships-visualization-phase5.md) - Lateral relationships visualization

**Patterns:**
- [query_architecture.md](/docs/patterns/query_architecture.md) - Query architecture patterns

**Code:**
- `/core/models/relationship_names.py` - RelationshipName enum (source of truth for all 80+ relationship types)

---

## Foundation

This skill has no prerequisites. It is a foundational pattern.

## See Also

- `/docs/patterns/query_architecture.md` - Query architecture documentation
- `/docs/architecture/NEO4J_DATABASE_ARCHITECTURE.md` - Database architecture
- `/core/models/relationship_names.py` - RelationshipName enum (source of truth)
