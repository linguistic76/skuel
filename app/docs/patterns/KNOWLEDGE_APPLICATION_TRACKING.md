---
title: Knowledge Application Tracking
updated: '2026-06-02'
category: patterns
related_skills:
- activity-domains
- learning-loop
- neo4j-cypher-patterns
related_docs:
- architecture/knowledge_substance_philosophy.md
- patterns/UNIFIED_RELATIONSHIP_SERVICE.md
---
# Knowledge Application Tracking

**Core Principle:** "When a learner applies knowledge to do real work, that is the
graph edge that makes SKUEL a *semantic* knowledge graph — not a denormalized field."

Knowledge application is the link between the **Curriculum** layer (what a learner
*knows* — Ku entities) and the **Action** layer (what a learner *does* — Activities).
It is the empirical proof that knowledge is *lived*, which is the foundation of the
[Knowledge Substance Philosophy](../architecture/knowledge_substance_philosophy.md).

It is the single most important cross-layer signal in the app, and it is **graph-native**.

---

## The edge IS the tracking

Knowledge application is stored as a relationship, never as a property on a node:

```
(Task)-[:APPLIES_KNOWLEDGE]->(Ku)
```

There is **no `applies_knowledge_uids` field on the frozen `Task` model**. It was
removed in the ADR-035 / ADR-065 graph-native migration, deliberately and permanently
(One Path Forward — do not reintroduce it). A denormalized list on a node is the
*least* graph-native representation of "knowledge is applied": it duplicates the edge,
drifts out of sync, and hides the relationship from graph traversals (ZPD, shared-neighbour
recommendations, substance scoring) that depend on it being a real edge.

`RelationshipName.APPLIES_KNOWLEDGE` is the canonical edge type. The relationship-registry
method key is `"knowledge"` (see `TASK_QUERY_SPECS` in
`core/services/tasks/task_relationships.py`).

> **`applies_knowledge_uids` *is* still a request/response field**
> (`TaskCreateRequest`, `TaskUpdateRequest`, `TaskResponse`). That is correct: it is the
> wire shape the API accepts and emits. The service layer translates that list into edges
> on the way in, and reads edges back on the way out. The field lives at the *boundary*,
> the edge lives at the *core*.

---

## Write path — both create AND update maintain the edge

| Operation | Site | Behaviour |
|-----------|------|-----------|
| **Create** | `tasks_core_service.create_task` / `tasks_scheduling_service` | Each `request.applies_knowledge_uids` entry becomes an `APPLIES_KNOWLEDGE` edge via `create_relationships_batch`. |
| **Update** | `TasksService.update_task` (facade) | `applies_knowledge_uids` is **popped out of the property `updates` dict** and re-synced as edges (delete-all-then-recreate). An empty list clears all knowledge edges. |

The update handling is symmetric to `reinforces_habit_uid` and is **required**: the
backend `update()` does an unfiltered `SET n += $updates`, so any relationship-typed key
left in the dict would (a) write a junk denormalized property onto the node and (b)
silently skip the edge. Relationship-typed keys must always be routed to edge mutation.

---

## Read path

Never read a node property — fetch the edge:

```python
# Container (parallel fetch of all task relationships)
rels = await TaskRelationships.fetch(task_uid, tasks_service.relationships)
if rels.applies_knowledge_uids:
    ...

# Or a single relationship key
result = await tasks_service.relationships.get_related_uids("knowledge", EntityUID(task_uid))

# Or the typed backend call
result = await backend.get_related_uids(task_uid, RelationshipName.APPLIES_KNOWLEDGE, direction="outgoing")
```

---

## Consumers (why this matters)

- **Insight generation** — `InsightGenerationService._analyze_knowledge_application_patterns`
  partitions completed tasks into the knowledge-applying cohort and emits a
  `PatternType.KNOWLEDGE_APPLICATION` pattern (→ `InsightCategory.LEARNING` insight) when
  that cohort is >10% more efficient. This is the "applied knowledge compounds" signal.
- **ZPD** — `ZPDBackend` traverses `APPLIES_KNOWLEDGE` edges to position the learner.
- **Learning relevance** — `tasks_learning_service.get_learning_relevant_tasks` scores
  tasks by the knowledge they apply.
- **Knowledge substance** — applied knowledge is one of the weighted contributions to a
  Ku's substance score.

Because every consumer reads the edge, the edge is the **single source of truth**. Add a
new consumer by traversing the edge — never by adding a field.

---

## Extending to other Activity domains

The same edge type and the same write/read discipline apply to every Activity domain that
can apply knowledge (Goal, Habit, Event, Choice, Principle). The YAML ingestion field is
`connections.applies_knowledge` (substance weight 0.05). Wire any new domain by:

1. Writing `APPLIES_KNOWLEDGE` edges on create (and re-syncing on update).
2. Reading via that domain's `*Relationships` container or `get_related_uids("knowledge", uid)`.

**See:** `core/services/tasks/task_relationships.py`,
`core/services/insight/_pattern_analysis_mixin.py`,
[Knowledge Substance Philosophy](../architecture/knowledge_substance_philosophy.md),
`@activity-domains`, `@learning-loop`.
