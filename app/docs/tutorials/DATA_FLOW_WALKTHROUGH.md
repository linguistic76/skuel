---
updated: 2026-11-08
---

# Data Flow Walkthrough: One Task, Created and Read Back

This page follows one real request from the client to the graph and back. Each stop names a
symbol you can search for. `/tests/integration/routes/test_data_flow_walkthrough_doc.py` sends the
request below to the running app and fails if a stop, the stored node or the response no longer
matches this page.

## The request

```http
POST /api/tasks/create
Content-Type: application/json
```

```json
{
  "title": "Review Python decorators",
  "description": "Study decorators before the advanced class",
  "priority": "high",
  "duration_minutes": 60,
  "applies_knowledge_uids": ["ku.python.decorators"],
  "prerequisite_knowledge_uids": ["ku.python.functions"]
}
```

The body names no `due_date` because a past date answers 400, and any date written here would
become a past date. A task with no date is due the day it is created.

Both Kus must already exist and be published: each list becomes edges to them.

`TASKS_CONFIG` in `/adapters/inbound/tasks_routes.py` declares this door, with
`create_schema=TaskCreateRequest` and `request_create_method="create_task"`. `CRUDRouteFactory`
builds the handler from that config, so `tasks_api.py` holds no route for it.

## The create path

Smaller helpers run between these stops. The table names the ones that decide something.

| # | Stop | Where | What it does |
|---|------|-------|--------------|
| 1 | `csrf_protected` | `/adapters/inbound/csrf.py` | Refuses a missing or wrong token: 403 |
| 2 | `instrument_with_boundary_handler` | `/adapters/inbound/boundary.py` | Counts the request and turns what the handler returns into a response |
| 3 | `CRUDRouteFactory._register_create_route` | `/adapters/inbound/route_factories/crud_route_factory.py` | The generated `create` handler |
| 4 | `check_required_role` | `/adapters/inbound/route_factories/route_helpers.py` | Tasks name no role, so this passes |
| 5 | `require_authenticated_user` | `/adapters/inbound/auth/session.py` | Reads the caller from the session: 401 without one, before the body is read |
| 6 | `parse_body` | `/adapters/inbound/form_helpers.py` | Reads JSON or a form by `Content-Type` and validates it as a `TaskCreateRequest`: 400 on failure |
| 7 | `TasksService.create_task` | `/core/services/tasks_service.py` | The facade, which delegates |
| 8 | `TasksCoreService.create_task` | `/core/services/tasks/tasks_core_service.py` | The request door, the one create that holds the request's link lists |
| 9 | `Task.from_request` | `/core/models/task/task.py` | Builds the frozen `Task` and generates its uid |
| 10 | `TasksCoreService._create_with_links` | `/core/services/tasks/tasks_core_service.py` | The one create path: persist, write every edge, then announce |
| 11 | `Task.with_creation_due_date` | `/core/models/task/task.py` | A task with no date becomes due today |
| 12 | `_CrudMixin.create` | `/adapters/persistence/neo4j/_crud_mixin.py` | Writes the node and its `OWNS` edge in one statement, and fails if the owner does not exist |
| 13 | `to_neo4j_node` | `/adapters/persistence/neo4j/neo4j_mapper.py` | `Task` to properties: enums to values, dates to ISO strings, dicts to JSON |
| 14 | `from_neo4j_node` | `/adapters/persistence/neo4j/neo4j_mapper.py` | Stored properties back to the `Task` the request answers with |
| 15 | `TasksCoreService._write_link_edges` | `/core/services/tasks/tasks_core_service.py` | Gathers the edges the request and the entity ask for |
| 16 | `keep_permitted_link_edges` | `/core/services/mixins/link_edge_guard.py` | Keeps the edges this owner may write |
| 17 | `_RelationshipCrudMixin.create_relationships_batch` | `/adapters/persistence/neo4j/_relationship_crud_mixin.py` | Writes the kept edges, all or none |
| 18 | `TasksCoreService._publish_created` | `/core/services/tasks/tasks_core_service.py` | Publishes `TaskCreated` and the embedding request, now that every edge exists |
| 19 | `TasksCoreService.publish_knowledge_applied` | `/core/services/tasks/tasks_core_service.py` | Announces the knowledge edges actually written, never the ones requested |
| 20 | `result_to_response` | `/adapters/inbound/boundary.py` | Turns the `Result` into a status: 201 |
| 21 | `jsonable_content` | `/adapters/inbound/boundary.py` | Turns the `Task` into JSON types and leaves out its embedding fields |

## What the graph holds

One node, labelled `:Entity:Task`, with 20 properties. Angle brackets stand for what a run fills in.

```json
{
  "uid": "<generated>",
  "title": "Review Python decorators",
  "entity_type": "task",
  "domain": "knowledge",
  "summary": "",
  "description": "Study decorators before the advanced class",
  "word_count": 0,
  "status": "draft",
  "visibility": "private",
  "tags": [],
  "created_at": "<now>",
  "updated_at": "<now>",
  "user_uid": "<caller>",
  "priority": "high",
  "due_date": "<today>",
  "duration_minutes": 60,
  "goal_progress_contribution": 0.0,
  "knowledge_mastery_check": false,
  "habit_streak_maintainer": false,
  "completion_updates_goal": true
}
```

A field with no value is not stored, and no property holds knowledge: the Kus a task applies
are its edges. In the FULL tier a background worker adds the embedding properties after the
response (`EMBEDDING_OWNED_PROPERTIES`) and announces the vector; `TaskGroundingService` then
links the published Kus it matches as `APPLIES_KNOWLEDGE {inferred: true, confidence,
grounded_at}` edges and stamps the node (`grounded_text_hash`). In CORE neither runs, so a task
carries only the knowledge its owner links.

The caller and the request's two lists become edges:

```text
(:User {uid: <caller>})-[:OWNS]->(task)
(task)-[:APPLIES_KNOWLEDGE]->(:Entity:Ku {uid: "ku.python.decorators"})
(task)-[:REQUIRES_KNOWLEDGE]->(:Entity:Ku {uid: "ku.python.functions"})
```

**A refused link still answers 201.** `keep_permitted_link_edges` drops a far end that does not
exist, belongs to another user, is the wrong kind or is an unpublished Ku, and logs why. An unknown
Ku writes no edge, and a valid Ku in the same list keeps its own.

`parent_uid`, `reinforces_habit_uid` and `contributes_to_goal_uids` ride on the `Task` as input to
those edge writes and never reach the node. See
[edge carriers](../architecture/CROSS_DOMAIN_UID_PATTERNS.md).

## The response

The body is every field of `Task` except the three embedding fields, nulls included: 40 keys.
Abridged:

```json
{
  "uid": "<generated>",
  "title": "Review Python decorators",
  "entity_type": "task",
  "status": "draft",
  "user_uid": "<caller>",
  "priority": "high",
  "due_date": "<today>",
  "scheduled_date": null,
  "parent_uid": null,
  "contributes_to_goal_uids": []
}
```

`applies_knowledge_uids` is not a key, because the `Task` holds no copy of the request's lists. A
service that needs them reads the graph with
`TaskRelationships.fetch(uid, tasks_service.relationships)`. Its `applies_knowledge_uids` holds
the owner's links and the ones grounding inferred alike; only the edge's `inferred` flag tells
them apart, and only an inferred one is removed at `POST /api/tasks/grounding/remove`.

## The read path

`GET /api/tasks/get?uid=<uid>` answers 200 with the same keys and values. It enters through the same
`csrf_protected` (a GET passes) and `instrument_with_boundary_handler`.

Once the FULL tier's worker has embedded a task, the `Task` the read builds carries the vector in
`embedding`, with `embedding_model` and `embedding_updated_at`: AI ranking reads them off the model.
The response does not. `jsonable_content` leaves those three keys out of every `Entity` in any JSON
response, so they are absent, never null, and an embedded task answers with the same 40 keys as one
that is not.

| # | Stop | Where | What it does |
|---|------|-------|--------------|
| 1 | `CRUDRouteFactory._register_get_route` | `/adapters/inbound/route_factories/crud_route_factory.py` | The generated `get` handler |
| 2 | `require_authenticated_user` | `/adapters/inbound/auth/session.py` | 401 without a session |
| 3 | `CrudOperationsMixin.get_for_user` | `/core/services/mixins/crud_operations_mixin.py` | The owner-scoped read |
| 4 | `CrudOperationsMixin.verify_ownership` | `/core/services/mixins/crud_operations_mixin.py` | Another user's task answers the same 404 as a missing uid |
| 5 | `_CrudMixin.get` | `/adapters/persistence/neo4j/_crud_mixin.py` | Reads the node by uid |
| 6 | `from_neo4j_node` | `/adapters/persistence/neo4j/neo4j_mapper.py` | Stored properties to a `Task` |
| 7 | `result_to_response` | `/adapters/inbound/boundary.py` | 200 |
| 8 | `jsonable_content` | `/adapters/inbound/boundary.py` | `Task` to JSON types, without the embedding fields |

## Where DTOs live

`TaskDTO` is on neither path. A request becomes a frozen `Task` directly and the mapper turns that
into a node, which is the intended design. DTOs live in the generators:
`GoalTaskGenerator.generate_tasks_for_goal` builds each task it suggests as a `TaskDTO` and
answers the tasks it created `to_dto()`. No service rewrites an entity through a DTO. A field whose
new value comes from its current one is planned from the node under its lock and written alone
(`rewrite_under_lock`): `PrinciplesService.create_principle_expression` (`_EmbodimentMixin`)
appends an expression that way.

## Where to read next

- [Three-Tier Type System](../patterns/three_tier_type_system.md): why the tiers exist
- [Route Factories](../patterns/ROUTE_FACTORIES.md): how `CRUDRouteFactory` builds the handlers
- [Model to Adapter](../patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md): how the mapper serializes each type
