# Neo4j Cypher Patterns - Common Patterns

> **Real query patterns used in SKUEL's production services**

---

## Pattern 1: MERGE + SET — Idempotent Relationship Creation

**Problem**: Creating a relationship that may already exist, with metadata you want to update.

**Context**: Domain backends linking entities (task→knowledge, habit→goal, event→knowledge).

**Solution**:
```cypher
// TasksBackend.link_task_to_knowledge()
MATCH (t:Task {uid: $task_uid})
MATCH (k:Entity {uid: $knowledge_uid})
MERGE (t)-[r:REQUIRES_KNOWLEDGE]->(k)
SET r.knowledge_score_required = $knowledge_score_required,
    r.is_learning_opportunity = $is_learning_opportunity
RETURN r

// GoalsBackend.link_task_to_goal()
MATCH (t:Task {uid: $task_uid})
MATCH (g:Goal {uid: $goal_uid})
MERGE (t)-[r:CONTRIBUTES_TO_GOAL]->(g)
SET r.contribution_percentage = $contribution_percentage
RETURN r
```

**Python (via backend)**:
```python
# domain_backends.py pattern
async def link_task_to_knowledge(
    self, task_uid: str, knowledge_uid: str, **props
) -> Result[bool]:
    result = await self.driver.execute_query(
        """
        MATCH (t:Task {uid: $task_uid})
        MATCH (k:Entity {uid: $knowledge_uid})
        MERGE (t)-[r:REQUIRES_KNOWLEDGE]->(k)
        SET r += $props
        RETURN true AS success
        """,
        task_uid=task_uid, knowledge_uid=knowledge_uid, props=props
    )
    return Result.ok(bool(result.records))
```

**Trade-offs**:
- MERGE is idempotent — safe to call multiple times
- SET overwrites relationship properties on each call
- Use `ON CREATE SET` if you only want to set props on first creation

**Real-world usage**: All domain backend `link_*` methods in `domain_backends.py`

---

## Pattern 2: UNWIND — Batch Operations (Avoid N+1)

**Problem**: Creating or checking relationships for multiple entities in one round-trip.

**Context**: Batch linking events to multiple knowledge units; checking relationship existence across entity lists.

**Solution**:
```cypher
// EventsBackend.link_event_to_knowledge() — batch link one event to many KUs
MATCH (e:Event {uid: $event_uid})
UNWIND $knowledge_uids AS ku_uid
MATCH (k:Entity {uid: ku_uid})
MERGE (e)-[r:REINFORCES_KNOWLEDGE]->(k)
RETURN count(r) AS relationship_count

// UnifiedRelationshipService — batch check existence
UNWIND $entity_uids AS entity_uid
MATCH (e:Task {uid: entity_uid})
OPTIONAL MATCH (e)-[r]->(related)
WHERE type(r) = $relationship_type
RETURN entity_uid, count(related) > 0 AS has_relationship

// Batch count related entities
UNWIND $entity_uids AS entity_uid
MATCH (e:Goal {uid: entity_uid})
OPTIONAL MATCH (e)-[r]->(related)
WHERE type(r) = $relationship_type
RETURN entity_uid, count(related) AS count
```

**Trade-offs**:
- Single round-trip for N entities — eliminates N+1 query pattern
- UNWIND on an empty list returns no rows — always handle the empty case
- OPTIONAL MATCH inside UNWIND prevents failures when entities have no relationships

**Real-world usage**: `UnifiedRelationshipService.batch_has_relationship()`, `EventsBackend.link_event_to_knowledge()`

---

## Pattern 3: COLLECT + CASE — Categorized Collection

**Problem**: Collecting entity UIDs categorized by status or condition in a single query (rather than multiple queries per category).

**Context**: UserContext MEGA-QUERY collecting task UIDs by status, overdue status, etc.

**Solution**:
```cypher
// user_context_queries.py — MEGA-QUERY segment
MATCH (user:User {uid: $user_uid})
OPTIONAL MATCH (user)-[:OWNS]->(task:Task)

WITH user,
     collect(CASE WHEN task.status IN ['draft', 'scheduled', 'active', 'blocked']
                  THEN task.uid END) AS active_task_uids,
     collect(CASE WHEN task.status = 'completed'
                  THEN task.uid END) AS completed_task_uids,
     collect(CASE WHEN task.due_date IS NOT NULL
                       AND date(task.due_date) < date($today)
                  THEN task.uid END) AS overdue_task_uids,
     collect(task) AS all_task_nodes

// Enrich with subtasks via UNWIND
UNWIND CASE WHEN size(all_task_nodes) > 0 THEN all_task_nodes ELSE [null] END AS task
OPTIONAL MATCH (task)-[:HAS_SUBTASK]->(subtask:Task)
WHERE task IS NOT NULL AND task.status IN ['draft', 'scheduled', 'active', 'blocked']
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, task,
     collect(DISTINCT {uid: subtask.uid, title: subtask.title, status: subtask.status})
     AS task_subtasks
```

**Trade-offs**:
- One query, three categorized lists — avoids three separate queries
- `CASE WHEN` inside `collect()` inserts `null` for non-matching rows — Neo4j 5 filters these automatically, but always verify
- `UNWIND CASE` pattern handles empty lists gracefully

**Real-world usage**: `user_context_queries.py` MEGA-QUERY (Tasks, Goals, Habits, Events segments)

---

## Pattern 4: WHERE NOT EXISTS — Negative Matching

**Problem**: Find entities that do NOT have a certain relationship (e.g., root nodes in a hierarchy).

**Context**: Finding root MOC organizers (Ku nodes that organize others but are not themselves organized).

**Solution**:
```cypher
// KuBackend.list_root_organizers()
MATCH (root:Entity)-[:ORGANIZES]->(:Entity)
WHERE NOT EXISTS((:Entity)-[:ORGANIZES]->(root))
WITH DISTINCT root
OPTIONAL MATCH (root)-[:ORGANIZES]->(child:Entity)
RETURN root.uid AS uid, root.title AS title, count(child) AS child_count
ORDER BY root.title
LIMIT $limit

// ExerciseBackend — type-gated linking with WHERE guard
MATCH (exercise:Entity {uid: $exercise_uid, entity_type: 'exercise'})
MATCH (curriculum:Entity {uid: $curriculum_uid})
WHERE curriculum.entity_type IN ['ku', 'resource']
MERGE (exercise)-[r:REQUIRES_KNOWLEDGE]->(curriculum)
ON CREATE SET r.created_at = datetime()
RETURN true AS success
```

**Trade-offs**:
- `NOT EXISTS` is clean and readable; use `WHERE NOT (a)-[:REL]->(b)` as alternative syntax
- Two-step `WHERE NOT EXISTS` + `OPTIONAL MATCH` avoids cartesian products
- `ON CREATE SET` adds metadata only on first creation (unlike `SET` which always runs)

**Real-world usage**: `KuBackend.list_root_organizers()`, `ExerciseBackend.link_to_curriculum()`

---

## Pattern 5: Multi-Relationship Type Matching

**Problem**: A relationship can be one of several types — match all of them in one pattern.

**Context**: Learning paths that include KUs via different relationship types; user mastery tracked via multiple status relationships.

**Solution**:
```cypher
// LpBackend.get_paths_containing_ku() — match either relationship type
MATCH (lp:Entity {entity_type: 'learning_path'})
      -[:INCLUDES_KU|REQUIRES_KNOWLEDGE]->
      (ku:Entity {uid: $ku_uid})
RETURN DISTINCT lp.uid AS lp_uid

// LpBackend.get_ku_mastery_progress() — two-pass calculation
MATCH (lp:Entity {uid: $lp_uid})-[:INCLUDES_KU|REQUIRES_KNOWLEDGE]->(ku:Entity)
WITH count(DISTINCT ku) AS total_kus
MATCH (lp:Entity {uid: $lp_uid})-[:INCLUDES_KU|REQUIRES_KNOWLEDGE]->(ku:Entity)
MATCH (user:User {uid: $user_uid})-[:MASTERED]->(ku)
WITH total_kus, count(DISTINCT ku) AS mastered_kus
RETURN total_kus, mastered_kus

// user_context_queries.py — user progress via multiple relationship types
OPTIONAL MATCH (user)-[mastered:MASTERED|IN_PROGRESS]->(ku:Entity)
WITH user, ...,
     collect({
         uid: ku.uid,
         score: coalesce(
             mastered.mastery_score,
             CASE WHEN type(mastered) = 'MASTERED' THEN 1.0 ELSE 0.5 END
         ),
         mastered_at: mastered.mastered_at,
     }) AS knowledge_mastery_data
```

**Trade-offs**:
- `[:TYPE_A|TYPE_B]` syntax is clean and efficient
- `type(r)` function lets you branch on which relationship type matched
- `DISTINCT` is essential when multiple paths can lead to the same node

**Real-world usage**: `LpBackend`, `user_context_queries.py` knowledge mastery segments

---

## Pattern 6: OPTIONAL MATCH — Non-Failing Relationship Queries

**Problem**: An entity may or may not have relationships — return the entity regardless.

**Context**: Everywhere. Tasks may have no goals. Habits may reinforce no knowledge.

**Solution**:
```cypher
// Get task with full neighborhood — always returns the task
MATCH (t:Task {uid: $uid})
OPTIONAL MATCH (t)-[:APPLIES_KNOWLEDGE]->(ku:Ku)
OPTIONAL MATCH (t)-[:FULFILLS_GOAL]->(g:Goal)
OPTIONAL MATCH (t)-[:DEPENDS_ON]->(dep:Task)
RETURN t,
       collect(DISTINCT ku) AS applied_knowledge,
       collect(DISTINCT g) AS goals,
       collect(DISTINCT dep) AS dependencies

// KuBackend.is_organizer() — check existence without failing
MATCH (ku:Entity {uid: $ku_uid})
OPTIONAL MATCH (ku)-[:ORGANIZES]->(child:Entity)
RETURN ku IS NOT NULL AS ku_exists, count(child) > 0 AS is_organizer
```

**Trade-offs**:
- `OPTIONAL MATCH` returns `null` for missing relationships — the entity row is still returned
- Combine with `collect()` to get empty list instead of `null`
- `DISTINCT` in collect prevents duplicates when multiple paths reach the same node (Cartesian products)

**Real-world usage**: All graph context queries, domain backends, `KuBackend.is_organizer()`

---

## Pattern 7: Relationship Metadata Extraction

**Problem**: Relationship properties contain important metadata (order, confidence, contribution_percentage).

**Context**: ORGANIZES relationships have `order` for hierarchy position; REQUIRES_KNOWLEDGE has `confidence`.

**Solution**:
```cypher
// KuBackend.get_organized_children() — extract both node and relationship properties
MATCH (parent:Entity {uid: $parent_uid})-[r:ORGANIZES]->(child:Entity)
RETURN child.uid AS uid,
       child.title AS title,
       child.entity_type AS entity_type,
       r.order AS order,
       r.importance AS importance
ORDER BY r.order ASC
LIMIT $limit

// ExerciseBackend.get_required_knowledge() — multiple node properties
MATCH (exercise:Entity {uid: $exercise_uid, entity_type: 'exercise'})
      -[:REQUIRES_KNOWLEDGE]->
      (curriculum:Entity)
RETURN curriculum.uid AS uid,
       curriculum.title AS title,
       curriculum.entity_type AS entity_type,
       curriculum.complexity AS complexity,
       curriculum.learning_level AS learning_level
ORDER BY curriculum.title

// Filter by relationship property
OPTIONAL MATCH (task)-[dep_rel:DEPENDS_ON]->(dependency:Task)
WHERE task IS NOT NULL
  AND coalesce(dep_rel.confidence, 1.0) >= $min_confidence
```

**Trade-offs**:
- Always alias extracted properties (`r.order AS order`) for clean result records
- `coalesce()` provides defaults for nullable relationship properties — prevents null comparison failures
- Filtering on relationship properties (`WHERE r.confidence >= x`) happens after matching — index can't help here

**Real-world usage**: `KuBackend.get_organized_children()`, `ExerciseBackend.get_required_knowledge()`, MEGA-QUERY dependency segment

---

## Pattern Comparison

| Pattern | Use Case | Key Clause | Performance |
|---------|----------|-----------|-------------|
| MERGE + SET | Idempotent link creation | `MERGE ... SET` | Fast (uses index on uid) |
| UNWIND | Batch N entities in 1 query | `UNWIND $list AS item` | Eliminates N+1 |
| COLLECT + CASE | Categorized aggregation | `collect(CASE WHEN ...)` | Fast (single pass) |
| WHERE NOT EXISTS | Negative matching (roots) | `WHERE NOT EXISTS(...)` | Can be slow — add limit |
| Multi-type | Match any of several rels | `[:A\|B\|C]` | Fast (multiple rel indexes) |
| OPTIONAL MATCH | Nullable relationships | `OPTIONAL MATCH` | No cost for missing rels |
| Relationship props | Metadata filtering | `WHERE r.prop >= x` | Post-match filter — no index |

---

## Key Rules

1. **Always use parameters** (`$uid`, never string interpolation) — prevents injection
2. **OPTIONAL MATCH** for nullable relationships — avoids returning no rows
3. **collect(DISTINCT ...)** when multiple paths could reach the same node
4. **coalesce(prop, default)** for nullable relationship/node properties
5. **UNWIND** for batch operations — one query for N entities
6. **No APOC in domain services** (SKUEL001) — pure Cypher only

**See Also**: [SKILL.md](SKILL.md) for foundational concepts and RelationshipName enum reference.
