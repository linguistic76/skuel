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
# domain_backends.py pattern — uses self.execute_query() (inherited from UniversalNeo4jBackend)
async def link_task_to_knowledge(
    self, task_uid: str, knowledge_uid: str,
    knowledge_score_required: float = 0.8,
    is_learning_opportunity: bool = False,
) -> Result[bool]:
    query = """
    MATCH (t:Task {uid: $task_uid})
    MATCH (k:Entity {uid: $knowledge_uid})
    MERGE (t)-[r:REQUIRES_KNOWLEDGE]->(k)
    SET r.knowledge_score_required = $knowledge_score_required,
        r.is_learning_opportunity = $is_learning_opportunity
    RETURN r
    """
    params = {
        "task_uid": task_uid,
        "knowledge_uid": knowledge_uid,
        "knowledge_score_required": knowledge_score_required,
        "is_learning_opportunity": is_learning_opportunity,
    }
    result = await self.execute_query(query, params)
    if result.is_error:
        return Result.fail(result)
    return Result.ok(True)
```

**Trade-offs**:
- MERGE is idempotent — safe to call multiple times
- SET overwrites relationship properties on each call
- Use `ON CREATE SET` if you only want to set props on first creation

**Real-world usage**: All domain backend `link_*` methods in `domain_backends.py`. Also standardized across hierarchy (`_hierarchy_mixin.py`), lateral relationships (`LateralRelationshipBackend`), badges (`EARNED_BADGE`), LP/PS construction (`HAS_STEP`, `CONTAINS_KNOWLEDGE`). **Rule:** Use MERGE (not CREATE) whenever both endpoints already exist — prevents duplicate edges on retry.

---

## Pattern 1b: WHERE Guard — Atomic Status Transition Enforcement

**Problem**: A mutation should only execute if the entity is in a valid source state. Pre-fetching then writing is a race condition; two concurrent requests can both read PROCESSING and both write COMPLETED.

**Context**: `SubmissionsBackend.create_report_node()` and `approve_and_get_linked_kus()` — teacher review actions that set submission status atomically.

**Solution**:
```cypher
// TeacherReviewService → SubmissionsBackend.create_report_node()
MATCH (submission:Entity {uid: $submission_uid})
WHERE submission.status IN $allowed_from_statuses   // Cypher-level guard
OPTIONAL MATCH (student:User)-[:OWNS]->(submission)
SET submission.status = $submission_status, ...
CREATE (fb:Entity { ... })
...
RETURN submission.uid as uid, submission.status as status, ...

// If WHERE filters out the node → no rows returned → service returns validation error
```

**Python (service passes allowed source statuses)**:
```python
# TeacherReviewService.submit_report() — PROCESSING → COMPLETED
allowed_from = [EntityStatus.PROCESSING.value]
result = await self.submissions_backend.create_report_node({
    ...,
    "allowed_from_statuses": allowed_from,
    "submission_status": EntityStatus.COMPLETED.value,
})
if not records:
    return Result.fail(Errors.validation(
        message=f"Submission is not in a reviewable status (expected {allowed_from})",
        field="status",
    ))
```

**Trade-offs**:
- Atomic — no gap between status check and mutation (race-safe)
- Zero extra queries — guard is part of the existing MATCH
- Empty results are ambiguous (not found vs guard rejected) — resolve by checking existence separately first (e.g., `_verify_teacher_access`)

**Real-world usage**: `SubmissionsBackend.create_report_node()` (submit_report, request_revision), `SubmissionsBackend.approve_and_get_linked_kus()` (approve_report). Guards enforce: PROCESSING→COMPLETED, COMPLETED→REVISION_REQUESTED, REVISION_REQUESTED→COMPLETED.

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
| JSON properties | Nested data in Neo4j | `to_neo4j_node()` / `parse_neo4j_json()` | N/A (Python layer) |

---

## Pattern 8: JSON Property Handling (Neo4j Limitation)

**Problem**: Neo4j properties cannot store nested structures (dicts, lists of dicts). These must be stored as JSON strings and parsed on read.

**Context**: `InsightStore` storing `related_entities` (list), `supporting_data` (dict); `ContentEnrichmentService` reading `key_topics` (list) from raw Cypher results.

**The Standard Path (UniversalNeo4jBackend)**:
```python
# WRITE: Both create() and update() auto-serialize via to_neo4j_node()
# Services pass native Python types — NO json.dumps() needed
await self.backend.update(uid, {
    "metadata": {"key": "val"},        # dict → json.dumps() by mapper
    "form_schema": [{"type": "text"}], # list of dicts → json.dumps() by mapper
    "priority": Priority.HIGH,         # enum → .value by mapper
})

# READ: from_neo4j_node() auto-deserializes using type hints
entity = from_neo4j_node(record["n"], Task)  # JSON strings → dicts/lists based on type hints
```

**Custom Cypher Path** (services that bypass UniversalNeo4jBackend):
```python
from core.utils.neo4j_mapper import parse_neo4j_json, deserialize_json_fields

# Single value — handles str, native types, None, and parse failures
topics = parse_neo4j_json(record["key_topics"], default=[])
metadata = parse_neo4j_json(record["metadata"], default={})

# Multiple fields in a dict — modifies in place
insight_data = dict(node)
deserialize_json_fields(insight_data, "related_entities", "recommended_actions", "supporting_data")
```

**Key rule**: Services deal with native Python types. JSON serialization/deserialization is an adapter concern handled by the Neo4j mapper layer.

---

## Pattern 9: Ownership Queries — OWNS Relationship vs `user_uid` Property

**Problem:** Finding who owns a shared/curriculum entity when writing Cypher. Not all
entity types have a `user_uid` node property — only `UserOwnedEntity` subtypes do.

**The distinction:**

| Entity hierarchy | `user_uid` property in Neo4j | How to find owner in Cypher |
|-----------------|----------------------------|-----------------------------|
| `UserOwnedEntity` (Task, Goal, Habit, Event, Choice, Principle, Submission, ExerciseReport, RevisedExercise, ...) | ✅ Present — stored as node property | `WHERE n.user_uid = $uid` OR `(User)-[:OWNS]->(n)` |
| `Curriculum` (Exercise, PathStep, LearningPath) | ❌ Missing — `Entity.user_uid` property returns `None` | `(User)-[:OWNS]->(n)` only |
| `Entity` base (Ku, Resource) | ❌ Missing | `(User)-[:OWNS]->(n)` only |

**Key rule:** `Exercise` extends `Curriculum(Entity)`, not `UserOwnedEntity`.
The Python `Entity.user_uid` property returns `None` for non-user-owned types.
Neo4j nodes for curriculum entities carry no `user_uid` property.
**Teacher identity for exercises is ONLY available via the OWNS relationship.**

**Wrong (silently returns NULL for Exercise):**
```cypher
MATCH (exercise:Entity {uid: $exercise_uid})
RETURN exercise.user_uid as teacher_uid  -- always NULL for Exercise
```

**Correct:**
```cypher
MATCH (exercise:Entity {uid: $exercise_uid})
OPTIONAL MATCH (teacher:User)-[:OWNS]->(exercise)
RETURN teacher.uid as teacher_uid  -- works for all entity types
```

**COALESCE for hybrid queries** (supports both curriculum and user-owned types in one query):
```cypher
-- SubmissionsBackend.get_exercise_context() — works for Exercise AND RevisedExercise
MATCH (exercise:Entity {uid: $exercise_uid})
WHERE exercise.entity_type IN ['exercise', 'revised_exercise']
OPTIONAL MATCH (teacher:User)-[:OWNS]->(exercise)
RETURN COALESCE(teacher.uid, exercise.user_uid) as teacher_uid
-- Exercise: OWNS relationship → teacher.uid ✓
-- RevisedExercise: both OWNS + stored user_uid agree ✓
-- YAML-ingested exercise, no owner: both NULL → auto-share skipped ✓
```

**When `teacher_uid` can be NULL:** Exercises ingested via YAML with no authenticated
teacher context have no OWNS relationship and no `user_uid`. The service layer must
guard against `None` before calling downstream methods that require a teacher UID.

**Real-world usage:** `SubmissionsBackend.get_exercise_context()`,
`ExerciseBackend.get_exercises_with_submission_counts()` (`MATCH (user)-[:OWNS]->(exercise)`),
`TeacherReviewService.get_review_queue()` (OWNS-based: `(student)-[:OWNS]->(submission)
WHERE student.uid <> teacher_uid` — catches all student submissions including
YAML-ingested ones). No SHARES_WITH relationship is created between teacher and
submission (per ADR-040). Access is role-gated at route level, not relationship-gated.

---

## Key Rules

1. **Always use parameters** (`$uid`, never string interpolation) — prevents injection
2. **OPTIONAL MATCH** for nullable relationships — avoids returning no rows
3. **collect(DISTINCT ...)** when multiple paths could reach the same node
4. **coalesce(prop, default)** for nullable relationship/node properties
5. **UNWIND** for batch operations — one query for N entities
6. **No APOC in domain services** (SKUEL001) — pure Cypher only
7. **No inline Cypher in services** — domain-specific Cypher belongs in domain backends (`domain_backends.py`). Services call `self.backend.method_name()`, never `self.backend.execute_query(cypher, params)`.
8. **No json.dumps() in services** — `backend.update()` and `backend.create()` auto-serialize complex types via `to_neo4j_node()`. For custom Cypher reads, use `parse_neo4j_json()` / `deserialize_json_fields()`.
9. **Validate interpolated identifiers** — Neo4j Cypher cannot parameterize relationship types or labels, so f-string interpolation is unavoidable for those. Use `_validate_rel_name()` and `_ALLOWED_ORDER_BY` from `_backend_helpers.py` (rejects non-`[A-Z0-9_]` relationship names, whitelists ORDER BY fields), `NeoLabel` enum typing for labels. Never accept raw user strings for these positions.

## Where Does Cypher Live?

| Cypher Type | Location | Example |
|-------------|----------|---------|
| Generic CRUD | `UniversalNeo4jBackend` (via mixins) | `create()`, `get()`, `update()`, `delete()` |
| Domain-specific relationships | Domain backend in `domain_backends.py` | `SubmissionsBackend.link_to_exercise()`, `ChoicesBackend.get_principle_adherence_data()` |
| Atomic multi-entity creation | Domain backend in `domain_backends.py` | `SubmissionsBackend.create_report_and_revised_exercise()` — single Cypher creates ExerciseReport + RevisedExercise + all relationships |
| Lesson-specific Cypher | 5 Lesson mixins (`_organizes_mixin.py`, `_learning_state_mixin.py`, `_semantic_mixin.py`, `_knowledge_context_mixin.py`, `_adaptive_mixin.py`) | `_LearningStateMixin.mark_mastered()`, `_OrganizesMixin.organize()` |
| Cross-domain aggregation | Service files (exception — uses `QueryExecutor`) | `user_context_queries.py` MEGA-QUERY |
| Vector index calls | `neo4j_vector_search_service.py` (infrastructure, FULL tier only) | `db.index.vector.queryNodes()` |
| Fulltext index creation | `neo4j_schema_manager.py` (bootstrap, always) | `sync_fulltext_indexes()` — 15 domains |
| Query generation | `query_optimizer.py`, `query_template_registry.py` | Builds Cypher by design |
| Generic hierarchy | `_HierarchyMixin` (shared by 6 Activity backends) | `get_children_raw()`, `create_hierarchy_relationship()` |
| JSON property utilities | `core/utils/neo4j_mapper.py` | `parse_neo4j_json()`, `deserialize_json_fields()` |

**19 domain backends** in `domain_backends.py`: TasksBackend, GoalsBackend, HabitsBackend, EventsBackend, PrinciplesBackend, ChoicesBackend, LessonBackend, KuBackend, PsBackend, LpBackend, ExerciseBackend, RevisedExerciseBackend, SubmissionsBackend, FormTemplateBackend, FormSubmissionBackend, ActivityReportBackend, LateralRelationshipBackend, GroupBackend, NotificationBackend.

**See Also**: [SKILL.md](SKILL.md) for foundational concepts and RelationshipName enum reference.
