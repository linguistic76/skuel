# Neo4j Cypher Patterns - Common Patterns

> **Real query patterns used in SKUEL's production services**

---

## Pattern 1: MERGE + SET — Idempotent Relationship Creation

**Problem**: Creating a relationship that may already exist, with metadata you want to update.

**Context**: Backends linking entities — hierarchy, lateral relationships, badges, LP/PS construction.

**Solution**:
```cypher
// _hierarchy_mixin.py — parent-child relationship
MATCH (p:Entity {uid: $parent_uid})
MATCH (c:Entity {uid: $child_uid})
MERGE (p)-[r:HAS_SUBTASK]->(c)
SET r.created_at = datetime()
RETURN r

// LateralRelationshipBackend — cross-domain edges
MATCH (a:Entity {uid: $source_uid})
MATCH (b:Entity {uid: $target_uid})
MERGE (a)-[r:RELATED_TO]->(b)
SET r.confidence = $confidence,
    r.created_at = datetime()
RETURN r
```

**Trade-offs**:
- MERGE is idempotent — safe to call multiple times
- SET overwrites relationship properties on each call
- Use `ON CREATE SET` if you only want to set props on first creation

**Real-world usage**: Standardized across hierarchy (`_hierarchy_mixin.py`), lateral relationships (`LateralRelationshipBackend`), badges (`EARNED_BADGE`), LP/PS construction (`HAS_STEP`, `USES_KU`, `CONTAINS_KNOWLEDGE`). Cross-domain relationship creation (task→knowledge, goal→habit, etc.) is handled by `UnifiedRelationshipService`, not domain backends. **Rule:** Use MERGE (not CREATE) whenever both endpoints already exist — prevents duplicate edges on retry.

---

## Pattern 1b: WHERE Guard — Atomic Status Transition Enforcement

**Problem**: A mutation should only execute if the entity is in a valid source state. Pre-fetching then writing is a race condition; two concurrent requests can both read PROCESSING and both write COMPLETED.

**Context**: `EntryReportBackend.create_report_node()` and `UserEntryBackend.approve_and_get_linked_kus()` — teacher review actions that set submission status atomically.

**Solution**:
```cypher
// TeacherReviewService → EntryReportBackend.create_report_node()
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
result = await self.report_backend.create_report_node({
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
- Empty results are ambiguous (not found vs guard rejected) — resolve by checking existence separately first (e.g., `_verify_teacher_has_group_access`)

**Real-world usage**: `EntryReportBackend.create_report_node()` (submit_report, request_revision), `UserEntryBackend.approve_and_get_linked_kus()` (approve_report). Guards enforce: PROCESSING→COMPLETED, COMPLETED→REVISION_REQUESTED, REVISION_REQUESTED→COMPLETED.

---

## Pattern 2: UNWIND — Batch Operations (Avoid N+1)

**Problem**: Creating or checking relationships for multiple entities in one round-trip.

**Context**: Batch-creating registry-validated relationships (e.g. Event→Ku APPLIES_KNOWLEDGE via `link_event_to_knowledge` on the Events service); checking relationship existence across entity lists.

**Solution**:
```cypher
// BatchCypherBuilder.build_relationship_create_query("APPLIES_KNOWLEDGE") —
// the one batch relationship writer (rel type is literal; :Entity endpoint
// labels guard against :Content shadow-uid double-binding)
UNWIND $rels AS rel
MATCH (a:Entity {uid: rel.from_uid})
MATCH (b:Entity {uid: rel.to_uid})
MERGE (a)-[r:APPLIES_KNOWLEDGE]->(b)
SET r += rel.properties
RETURN count(r) as created_count

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

**Real-world usage**: `UnifiedRelationshipService.batch_has_relationship()`, `BatchCypherBuilder.build_relationship_create_query()` (backs `create_relationships_batch` on the universal backend — how the Events service's `link_event_to_knowledge` facade writes APPLIES_KNOWLEDGE)

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
                       AND date(left(toString(task.due_date), 10)) < date($today)
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

**Real-world usage**: `KuBackend.list_root_organizers()`, `ExerciseBackend.link_to_curriculum()`, `ExerciseBackend.link_to_path_step()`

---

## Pattern 5: Multi-Relationship Type Matching

**Problem**: A relationship can be one of several types — match all of them in one pattern.

**Context**: Learning paths that include KUs via different relationship types; user mastery tracked via multiple status relationships.

**Solution**:
```cypher
// LpBackend.get_paths_containing_ku() — a path reaches a Ku two ways: directly,
// via its ingestible REQUIRES_KNOWLEDGE prerequisites, or (the normal case)
// through the PathSteps that actually compose Kus. There is NO LearningPath→Ku
// containment edge — this query used to match INCLUDES_KU, which nothing writes.
MATCH (lp:Entity {entity_type: 'learning_path'})-[:REQUIRES_KNOWLEDGE]->(ku:Entity {uid: $ku_uid})
RETURN DISTINCT lp.uid AS lp_uid
UNION
MATCH (lp:Entity {entity_type: 'learning_path'})
      -[:HAS_STEP]->(:Entity)-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]->
      (ku:Entity {uid: $ku_uid})
RETURN DISTINCT lp.uid AS lp_uid

// LpBackend.get_ku_mastery_progress() — collect both routes, then test mastery
// with a predicate. A mandatory MATCH on MASTERED would return zero rows for a
// user who has mastered nothing, which the service reads as "path has no Kus".
MATCH (lp:Entity {uid: $lp_uid})
OPTIONAL MATCH (lp)-[:REQUIRES_KNOWLEDGE]->(direct_ku:Entity)
WITH lp, collect(DISTINCT direct_ku) AS direct_kus
OPTIONAL MATCH (lp)-[:HAS_STEP]->(:Entity)-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]->(step_ku:Entity)
WITH direct_kus, collect(DISTINCT step_ku) AS step_kus
WITH direct_kus + step_kus AS candidate_kus
UNWIND (CASE WHEN size(candidate_kus) = 0 THEN [null] ELSE candidate_kus END) AS ku
WITH [k IN collect(DISTINCT ku) WHERE k IS NOT NULL] AS lp_kus
RETURN size(lp_kus) AS total_kus,
       size([k IN lp_kus WHERE EXISTS { (:User {uid: $user_uid})-[:MASTERED]->(k) }]) AS mastered_kus

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
from core.utils.neo4j_props import parse_neo4j_json, deserialize_json_fields

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
| `UserOwnedEntity` (Task, Goal, Habit, Event, Choice, Principle, Submission, EntryReport, RevisedExercise, ...) | ✅ Present — stored as node property | `WHERE n.user_uid = $uid` OR `(User)-[:OWNS]->(n)` |
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
// UserEntryBackend.get_exercise_context() — works for Exercise AND RevisedExercise
MATCH (exercise:Entity {uid: $exercise_uid})
WHERE exercise.entity_type IN ['exercise', 'revised_exercise']
OPTIONAL MATCH (teacher:User)-[:OWNS]->(exercise)
RETURN COALESCE(teacher.uid, exercise.user_uid) as teacher_uid
// Exercise: OWNS relationship → teacher.uid ✓
// RevisedExercise: both OWNS + stored user_uid agree ✓
// YAML-ingested exercise, no owner: both NULL → auto-share skipped ✓
```

**When `teacher_uid` can be NULL:** Exercises ingested via YAML with no authenticated
teacher context have no OWNS relationship and no `user_uid`. The service layer must
guard against `None` before calling downstream methods that require a teacher UID.

**Real-world usage:** `UserEntryBackend.get_exercise_context()`,
`ExerciseBackend.get_exercises_with_submission_counts()` (`MATCH (user)-[:OWNS]->(exercise)`),
`TeacherReviewService.get_review_queue()` (OWNS-based: `(student)-[:OWNS]->(submission)
WHERE student.uid <> teacher_uid` — catches all student submissions including
YAML-ingested ones). No SHARES_WITH relationship is created between teacher and
submission (per ADR-040). Access is role-gated at route level, not relationship-gated.

---

## Pattern 10: Temporal Property Coercion (string-stored dates vs `date()`/`datetime()`)

**Problem:** SKUEL stores temporal fields as **ISO strings** (DTOs serialize `datetime`/`date` via `.isoformat()`). Neo4j evaluates `string >= date(...)` / `string >= datetime(...)` as **`null`** — not an error, so the predicate silently fails and the row is dropped (or a `CASE` falls through). Whole features quietly return nothing.

**The discriminator — the WRITER decides the stored type:**

| Write path | Stored type | A direct `field OP date()/datetime()` is… |
|---|---|---|
| DTO `.isoformat()` (domain entities: `due_date`, `event_date`, `created_at`, `expires_at`, `next_due_at`, `last_completed`, …) | **STRING** | **broken** (string vs temporal → null) |
| Cypher `SET n.x = datetime()` / `datetime($param)` (sessions, tokens, `updated_at`, `achieved_at`, `mastered_at`) | **native ZONED DATETIME** | fine |

Before "fixing" a comparison, **grep the write path**: `.isoformat()` → string (coerce); `= datetime(` / `datetime($` → native (leave). Some columns are **mixed** (e.g. `created_at`: mostly strings + a few native datetimes from legacy writes) — coercion handles both.

**The fix — coerce the stored side:**
```cypher
// datetime-typed field (has a time component): use datetime()
WHERE datetime(n.created_at) >= datetime($window_start)
WHERE datetime(s.next_due_at) <= datetime()

// date field (due_date, event_date, ...): take the YYYY-MM-DD prefix. A bare
// date(n.due_date) works for a clean date-only string but THROWS if a writer
// mis-stored a datetime there — which blanks the whole range (#766). left(...,10)
// tolerates every shape (date-only string, datetime string, date/datetime type).
WHERE date(left(toString(n.due_date), 10)) >= date($start_date)
```

🔑 **`date()` CANNOT parse a datetime string** (Neo4j 2025.12: `Cannot parse '2026-06-05T02:24:..+00:00' as a Date`) — and a throw inside a range `WHERE` or a mega-query `CASE` takes the **whole** query down, so the user silently loses every row, not just the malformed one (#766). The `left(toString(x), 10)` prefix above is the defensive default for any date field. For a **datetime**-typed field compared against a *date*, `date(datetime(...))` (parse-then-extract) is equivalent:
```cypher
// last_completed is a datetime string; we want "before today"
CASE WHEN date(datetime(h.last_completed)) < date() THEN 0 ELSE 1 END
```

**Coercion safety cheat-sheet:**
- `datetime(x)` — parses date-only **and** datetime ISO strings; **no-op** on a native datetime. **Universally safe.**
- `date(x)` — parses date-only strings and native temporals; **ERRORS on a datetime string**. Safe only for date-typed fields.
- So when unsure, `datetime(...)` (or `date(datetime(...))` if you need a date) is the safe choice.

**Two valid styles, but pick one and be consistent on BOTH sides:** either coerce the stored field as above, OR (Key Rule #17) build the comparison bound as a matching ISO **string** and compare string-vs-string. Mixing a string field with a temporal bound (or vice-versa) is the bug.

**Verify against real Neo4j** — `string >= datetime()` returning `null` cannot be caught by a mocked backend; a unit test with stubbed rows passes while production returns empty. Seed both a string and a native value, assert the row is matched, and prove the test fails before the coercion (`datetime(string) >= datetime($w) → true`, `string >= datetime($w) → null`).

**Real-world:** PRs #199 (date fields), #202 (`created_at` mixed column), #203 (`next_due_at`/`last_generated_at`/`expires_at`/`completed_at`/`last_completed`). Guards: `tests/integration/test_date_range_string_coercion.py`, `test_created_at_window_coercion.py`, `test_timestamp_field_coercion_residual.py`.

### 10b: The same trap through `find_by` — where you never write Cypher at all

Everything above assumes you are *writing* a query, so you can see the operands. The
easiest way to hit this trap is through `find_by`, where you write only Python:

```python
# Looks like a plain Python filter. It is a Cypher range predicate.
await backend.find_by(habit_uid=uid, completed_at__gte=window_start, completed_at__lte=window_end)
```

`convert_value_for_neo4j` (`query/cypher/_helpers.py`) turns a `date`/`datetime` bound into
an **ISO string** on the way to the driver. So this is `string OP stored_field`, and Key
Rule #17 applies with nothing on screen to remind you: rows whose field is a *native*
temporal are dropped — silently, from a call that reads like it filters in Python.

`find_by` cannot coerce the stored side (it emits `field OP $param`, no room for
`datetime(...)`), so there are only three honest options:

| Situation | Do this |
|---|---|
| The column is string-only **by writer enumeration** | Keep the kwargs filter; name the writer in a comment, because the *next* writer is what breaks it |
| The column is or may be mixed | Fetch **without** a temporal predicate and filter in Python — the mapper has already normalised both forms to `datetime`, so the comparison is type-tolerant by construction |
| You need the predicate in the database (volume) | Give the backend a real method with `date(left(toString(x), 10))` — Pattern 10 proper |

Dropping the predicate means dropping the row cap with it: page (`sort_by="uid"` — a plain
string on every row, so the ordering that makes paging deterministic cannot itself be
skewed by the split), never a bare `limit`, or you have swapped a silent type bug for a
silent truncation bug.

⚠️ The same applies to `sort_by` on a temporal column: mixed types sort by **type before
value**, so a cap truncates one type band rather than the oldest rows.

**Real-world:** PR #1140. Guard: `tests/integration/test_habit_completion_temporal_split.py`
seeds two completions on the same instant differing only in storage type and asserts the
bounded `find_by` returns one — pinning the mechanism, so if Neo4j's cross-type comparison
ever changes, the test says so.

---

## Key Rules

1. **Always use parameters** (`$uid`, never string interpolation) — prevents injection
2. **OPTIONAL MATCH** for nullable relationships — avoids returning no rows
3. **collect(DISTINCT ...)** when multiple paths could reach the same node
4. **coalesce(prop, default)** for nullable relationship/node properties
5. **UNWIND** for batch operations — one query for N entities
6. **No APOC in domain services** (SKUEL001) — pure Cypher only
7. **No inline Cypher in domain services** — domain-specific Cypher belongs in domain backends (`adapters/persistence/neo4j/backends/`). Services call `self.backend.method_name()`, never `self.backend.execute_query(cypher, params)`. Two service-layer exceptions: `user_context_queries.py` (MEGA-QUERY) and `CrossDomainQueryService` (targeted cross-domain reads) — both use `QueryExecutor` directly for explicitly cross-domain Cypher spanning 2+ domain labels.
8. **No json.dumps() in services** — `backend.update()` and `backend.create()` auto-serialize complex types via `to_neo4j_node()`. For custom Cypher reads, use `parse_neo4j_json()` / `deserialize_json_fields()`.
9. **Validate interpolated identifiers** — Neo4j Cypher cannot parameterize relationship types or labels, so f-string interpolation is unavoidable for those. All 5 query builder modules (`crud_queries.py`, `domain_queries.py`, `relationship_queries.py`, `semantic_queries.py`, `intelligence_queries.py`) import `validate_label()` and `validate_identifier()` from `_helpers.py` and call them before every f-string interpolation of labels, field names, relationship types, and property keys. Backend mixins additionally use `_validate_rel_name()` and `_ALLOWED_ORDER_BY` from `_backend_helpers.py`. Never accept raw user strings for these positions.
10. **Parameterize `entity_type` filters via the enum** — `entity_type` is a node *property*, so it CAN (and must) be a `$param`. Bind `EntityType.USER_ENTRY.value` (etc.) instead of inlining `'user_entry'`. Inline literals violate SKUEL014 and silently rot if an enum value ever changes. Pattern: `MATCH (u:Entity {entity_type: $entry_type})` + `params={"entry_type": EntityType.USER_ENTRY.value}`.
11. **Bound traversal queries with `LIMIT $limit`** — any query that returns a per-user collection (submissions for a PathStep, reports for a submission, etc.) must accept a `limit` parameter and apply `LIMIT $limit`. Default to a `QueryLimit.*` constant. Unbounded `MATCH ... RETURN ... ORDER BY ...` is a latent DoS as user data grows.
12. **Defensive `.get()` on record columns + `result.value or []`** — when projecting Neo4j records into TypedDicts/dicts, use `record.get("col")` for every column except the genuinely required ones, and guard the comprehension with `for r in result.value or []`. A `KeyError` mid-comprehension is much harder to debug than a `None` field downstream.
13. **Clamp caller-supplied `limit` at the service boundary** — parameterizing via `$limit` protects the query plan, but it does not protect the driver from a caller passing `limit=10_000_000`. Clamp with `limit = max(1, min(limit, QueryLimit.MAXIMUM))` as the first statement in any public service method that accepts `limit`. The `$limit` binding in the Cypher is the floor, not the ceiling.
14. **Whitelist `entity_type` at the service boundary** — a service named `SomethingSearchService` that accepts an `entity_type: EntityType | None` override is a cross-domain bleed waiting to happen. The backend label is `:Entity`, so passing `EntityType.TASK` to a submission query silently scopes to Tasks and returns them as "submissions." Resolve via a private method that validates against a `ClassVar[frozenset[EntityType]]` of allowed types and raises `ValueError` on mismatch — `@with_error_handling` surfaces it as a validation `Result`. Pattern: see `SubmissionsSearchService._resolve_submission_type()` + `_ALLOWED_SUBMISSION_TYPES`.
15. **Reject `start_date > end_date` upfront** — an inverted date range produces an impossible `created_at__gte=X AND created_at__lt=Y` Cypher predicate that silently returns `[]`. Callers see "no results" and assume the database is empty. Return `Errors.validation(...)` before hitting the backend so the caller bug surfaces immediately.
16. **Sanitize text-search inputs before CONTAINS** — `toLower(s.processed_content) CONTAINS toLower($query)` with `query=""` is caught by `if not query:`, but `"   "` and `"a"` sail through and scan every row. Strip and require `len(query.strip()) >= 2` before building the Cypher. Short-circuit to `Result.ok([])` when below threshold.
17. **Match ISO-string date bounds to the storage invariant** — SKUEL stores `created_at` as naive-local via `datetime.now().isoformat()` with no tz suffix. Date-boundary queries must build bounds the same way: `datetime.combine(target_date, time.min).isoformat()`. Mixing a naive stored value with a tz-aware bound string (`"...+00:00"` or `"...Z"`) is silently broken at day boundaries — string comparison sorts `"2026-04-05T00:00:00"` differently from `"2026-04-05T00:00:00+00:00"`. Document the invariant at the top of any service that builds ISO-string bounds; if the storage format ever changes, every boundary construction must move in lockstep.
18. **Coerce string-stored temporals before comparing to `date()`/`datetime()`** — the flip side of #17: when a query compares a stored temporal against a Cypher temporal value (not another string), `string OP date()/datetime()` evaluates to `null` and the row is silently dropped. Wrap the stored field: `datetime(n.created_at) >= datetime($w)`. `datetime()` is universally safe (parses both string shapes, no-op on natives); `date()` ERRORS on a datetime string, so use `date(datetime(field))` for a datetime field compared to a date. The WRITER decides the type — DTO `.isoformat()` → string (coerce); Cypher `= datetime()` → native (leave). **See Pattern 10.**
18b. **`find_by(field__gte=<datetime>)` is a Cypher range predicate, not a Python filter** — the bound is stringified by `convert_value_for_neo4j`, so Key Rule #17 applies to a call with no Cypher in sight. `find_by` cannot coerce the stored side; on a possibly-mixed column, fetch unbounded (paged, `sort_by="uid"`) and window in Python. **See Pattern 10b.**

## Where Does Cypher Live?

| Cypher Type | Location | Example |
|-------------|----------|---------|
| Generic CRUD | `UniversalNeo4jBackend` (via mixins) | `create()`, `get()`, `update()`, `delete()` |
| Domain-specific relationships | Domain backend in `backends/` | `RevisedExerciseBackend.link_to_exercise()` |
| Atomic multi-entity creation | Domain backend in `backends/` | `EntryReportBackend.create_report_and_revised_exercise()` — single Cypher creates EntryReport + RevisedExercise + all relationships |
| PS-specific Cypher | 5 PsBackend mixins (`_organizes_mixin.py`, `_learning_state_mixin.py`, `_semantic_mixin.py`, `_knowledge_context_mixin.py`, `_adaptive_mixin.py`) | `_LearningStateMixin.mark_mastered()`, `_OrganizesMixin.organize()` |
| Cross-domain aggregation | Service files (exception — uses `QueryExecutor`) | `user_context_queries.py` MEGA-QUERY, `CrossDomainQueryService` (9 targeted reads → frozen typed dataclasses) |
| Vector index calls | `VectorSearchBackend` in `vector_search_backend.py` (infrastructure, FULL tier only) | `db.index.vector.queryNodes()` |
| Fulltext index creation | `neo4j_schema_manager.py` (bootstrap, always) | `sync_fulltext_indexes()` — 14 domains, names from `NeoLabel.fulltext_index_name()` |
| Fulltext index calls | `VectorSearchBackend` in `vector_search_backend.py` (publication-gated, like its vector twin) | `db.index.fulltext.queryNodes()` |
| Query generation | `query_optimizer.py`, `query_template_registry.py` | Builds Cypher by design |
| Generic hierarchy | `_HierarchyMixin` (shared by 6 Activity backends) | `get_children_raw()`, `create_hierarchy_relationship()` |
| JSON property utilities | `core/utils/neo4j_props.py` | `parse_neo4j_json()`, `deserialize_json_fields()` |

**31 domain backends** live in `adapters/persistence/neo4j/backends/` (9 cluster files). Import directly from the cluster file:

| Cluster file | Backends |
|---|---|
| `backends/activity_backends.py` | HabitsBackend, GoalsBackend, TasksBackend, EventsBackend, ChoicesBackend, PrinciplesBackend |
| `backends/curriculum_backends.py` | KuBackend, PsBackend, LpBackend |
| `backends/exercise_backends.py` | ExerciseBackend, RevisedExerciseBackend, EntryReportBackend |
| `backends/user_entry_backend.py` | UserEntryBackend (shell over 5 `_user_entry_*_mixin` files) |
| `backends/sharing_backend.py` | SharingBackend |
| `backends/forms_backends.py` | FormTemplateBackend, FormSubmissionBackend |
| `backends/templates_backends.py` | TaskTemplateBackend, GoalTemplateBackend, HabitTemplateBackend, EventTemplateBackend, ChoiceTemplateBackend, PrincipleTemplateBackend |
| `backends/collab_backends.py` | GroupBackend, LateralRelationshipBackend, NotificationBackend, ReviewQueueBackend |
| `backends/misc_backends.py` | ActivityReportBackend, ResourceBackend, InteractionBackend, ReportScheduleBackend, ActivityReportGeneratorBackend |

Always import directly from the cluster file, e.g. `from adapters.persistence.neo4j.backends.activity_backends import TasksBackend`.

**See Also**: [SKILL.md](SKILL.md) for foundational concepts and RelationshipName enum reference.
