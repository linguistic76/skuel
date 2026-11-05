---
updated: 2026-11-05
---

# Data Flow Walkthrough: Following a Task Creation Request

## Purpose

This tutorial follows a **single HTTP request** through SKUEL's entire data flow pipeline, showing exactly how data transforms through each tier of the three-tier type system.

**Goal**: Make the data flow crystal clear by following actual code execution.

---

## The Journey: Creating a Task

We'll trace this HTTP request from the user's client to Neo4j and back:

```http
POST /api/tasks/create
Content-Type: application/json

{
  "title": "Review Python decorators",
  "description": "Study decorators before the advanced class",
  "due_date": "2026-02-05",
  "priority": "high",
  "duration_minutes": 60,
  "applies_knowledge_uids": ["ku.python-decorators"],
  "prerequisite_knowledge_uids": ["ku.python-functions"]
}
```

---

## Stage 1: HTTP Boundary (Tier 1 - Pydantic)

**Location**: `/adapters/inbound/tasks_api.py`

### 1.1 Route Registration

```python
# CRUDRouteFactory automatically registers this route
crud_factory = CRUDRouteFactory(
    service=tasks_service,
    domain_name="tasks",
    create_schema=TaskCreateRequest,  # ← Pydantic model for validation
    uid_prefix="task",
    scope=ContentScope.USER_OWNED,
)

# This creates: POST /api/tasks/create
crud_factory.register_routes(rt)
```

### 1.2 Request Parsing via `parse_body()`

```python
# parse_body() handles:
# 1. Reads the body by its Content-Type — JSON from an API client, url-encoded or
#    multipart from an HTMX form (the CRUD factory's doors serve both callers)
# 2. Validates against TaskCreateRequest schema via Pydantic
# 3. Returns Result.fail() with validation error on failure
# 4. Returns Result.ok(model) on success

from adapters.inbound.form_helpers import parse_body

@rt("/api/tasks/create", methods=["POST"])
@boundary_handler(success_status=201)
async def create_task(request: Request) -> Result[Task]:
    user_uid = require_authenticated_user(request)
    parsed = await parse_body(request, TaskCreateRequest)
    if parsed.is_error:
        return parsed  # type: ignore[return-value]
    return await tasks_service.create_task(parsed.value, user_uid)
```

### 1.3 Pydantic Validation (Tier 1)

**File**: `/core/models/task/task_request.py:36-89`

```python
class TaskCreateRequest(CreateRequestBase):
    """External API request for creating a task."""

    title: str = Field(min_length=1, max_length=200, description="Task title")
    description: str | None = Field(None, max_length=2000, description="Detailed description")

    # Scheduling
    due_date: date | None = Field(None, description="Due date")
    duration_minutes: int | None = Field(None, ge=5, le=480, description="Estimated duration")

    # Priority and status
    priority: Priority = Field(default=Priority.MEDIUM, description="Task priority")
    status: EntityStatus = Field(default=EntityStatus.DRAFT, description="Initial status")

    # Learning Integration
    applies_knowledge_uids: list[str] = Field(
        default_factory=list, description="Knowledge being applied"
    )
    prerequisite_knowledge_uids: list[str] = Field(
        default_factory=list, description="Required knowledge"
    )

    # Pydantic field validators
    _validate_dates = validate_future_date("due_date", "scheduled_date")
    _validate_recurrence_end = validate_recurrence_end_after_start(
        "recurrence_end_date", "due_date"
    )
```

**What Pydantic checks:**
- ✅ `title` is a string between 1-200 chars
- ✅ `due_date` is a valid date format
- ✅ `priority` is one of the allowed Priority enum values
- ✅ `duration_minutes` is between 5-480
- ✅ `applies_knowledge_uids` is a list of strings
- ✅ Custom validators ensure due_date is in the future

**If validation fails**: Pydantic returns `400 Bad Request` with field-level errors **before** any service code runs.

**Result after Stage 1**:
```python
# Validated Pydantic object
body: TaskCreateRequest = TaskCreateRequest(
    title="Review Python decorators",
    description="Study decorators before the advanced class",
    due_date=date(2026, 2, 5),
    priority=Priority.HIGH,  # Enum parsed from "high"
    duration_minutes=60,
    applies_knowledge_uids=["ku.python-decorators"],
    prerequisite_knowledge_uids=["ku.python-functions"],
    status=EntityStatus.DRAFT,  # Default value
)
```

---

## Stage 2: Service Layer (Tier 1 → Tier 2)

**Location**: `/core/services/tasks/tasks_core_service.py`

### 2.1 Service Method Entry

```python
async def create_task(
    self,
    request: TaskCreateRequest,  # ← Tier 1 (Pydantic)
    user_uid: UserUID,
) -> Result[TaskDTO]:  # ← Returns Tier 2 (DTO)
    """
    Create a new task.

    Flow:
    1. Convert Pydantic request → DTO (Tier 1 → Tier 2)
    2. Persist DTO to Neo4j
    3. Create graph relationships
    4. Return DTO
    """
```

### 2.2 Conversion: Pydantic → DTO (Tier 1 → Tier 2)

**File**: `/core/models/task/task.py` — `Task.from_request` (the block below shows the retired `task_converters.py` shape; see the note after it)

```python
def task_create_request_to_dto(
    request: TaskCreateRequest,  # ← Tier 1 (Pydantic)
    user_uid: UserUID,
) -> TaskDTO:  # ← Tier 2 (DTO)
    """Convert Pydantic request to mutable DTO."""

    return TaskDTO.create(
        user_uid=user_uid,
        title=request.title,
        description=request.description,
        due_date=request.due_date,
        priority=request.priority,
        status=request.status,
        duration_minutes=request.duration_minutes,
        project=request.project,
        tags=request.tags or [],
        # NOT stored as properties — see the note below this block
        reinforces_habit_uid=request.reinforces_habit_uid,
        # Metadata fields
        goal_progress_contribution=request.goal_progress_contribution,
        knowledge_mastery_check=request.knowledge_mastery_check,
        habit_streak_maintainer=request.habit_streak_maintainer,
    )
```

> ⚠ **Illustrative, and behind the code.** Since #966 `create_task` builds a frozen
> `Task` via `Task.from_request` and persists the ENTITY, not a DTO dict. And
> `reinforces_habit_uid` is *not* a node property in either shape: it is in
> `RELATIONSHIP_SKIP_FIELDS`, and `TasksCoreService.create` writes
> `(Task)-[:REINFORCES_HABIT]->(Habit)` from it. `parent_uid` is the same shape
> (HAS_SUBTASK), and so is `contributes_to_goal_uids` (one CONTRIBUTES_TO_GOAL edge
> per goal). See `docs/architecture/CROSS_DOMAIN_UID_PATTERNS.md § edge carrier`.

**Why convert to DTO?**
1. **Mutability**: DTOs can be modified during service operations
2. **UID generation**: `TaskDTO.create()` generates unique `task.{uuid}` UID
3. **Timestamps**: Sets `created_at` and `updated_at` to current time
4. **Graph relationships**: Relationship UIDs (like `applies_knowledge_uids`) are handled separately as graph edges

**Result after Stage 2.2**:
```python
# Mutable DTO with generated UID and timestamps
task_dto: TaskDTO = TaskDTO(
    uid="task_a1b2c3d4e5f67890",  # Generated
    user_uid="user_5f2c8e1a9b3d7046",
    title="Review Python decorators",
    description="Study decorators before the advanced class",
    due_date=date(2026, 2, 5),
    priority=Priority.HIGH,
    status=EntityStatus.DRAFT,
    duration_minutes=60,
    tags=[],
    # Edge carriers (never persisted)
    reinforces_habit_uid=None,
    # Timestamps
    created_at=datetime(2026, 1, 29, 10, 30, 0),  # Now
    updated_at=datetime(2026, 1, 29, 10, 30, 0),  # Now
    # Metadata
    goal_progress_contribution=0.0,
    knowledge_mastery_check=False,
    metadata={},
)
```

### 2.3 Create Graph Relationships (GRAPH-NATIVE)

```python
# Relationship UIDs are NOT stored in the DTO
# They're stored as Neo4j edges

# Create APPLIES_KNOWLEDGE relationships
for ku_uid in request.applies_knowledge_uids:
    await self.relationships.add_task_knowledge(
        task_uid=task_dto.uid,
        knowledge_uid=ku_uid,
        relationship_type="APPLIES_KNOWLEDGE",
    )

# Create REQUIRES_KNOWLEDGE relationships
for ku_uid in request.prerequisite_knowledge_uids:
    await self.relationships.add_task_prerequisite_knowledge(
        task_uid=task_dto.uid,
        knowledge_uid=ku_uid,
    )
```

**Graph structure created**:
```cypher
# Task node
CREATE (task:Task {
    uid: "task_a1b2c3d4e5f67890",
    title: "Review Python decorators",
    user_uid: "user_5f2c8e1a9b3d7046",
    priority: "high",
    status: "draft",
    due_date: "2026-02-05",
    duration_minutes: 60,
    created_at: "2026-01-29T10:30:00",
    updated_at: "2026-01-29T10:30:00"
})

# Ownership edge
CREATE (user:User {uid: "user_5f2c8e1a9b3d7046"})-[:OWNS]->(task)

# Knowledge application edges
CREATE (task)-[:APPLIES_KNOWLEDGE]->(ku1:KU {uid: "ku.python-decorators"})
CREATE (task)-[:REQUIRES_KNOWLEDGE]->(ku2:KU {uid: "ku.python-functions"})
```

---

## Stage 3: Persistence Layer (Tier 2 → Neo4j)

**Location**: `/adapters/persistence/neo4j/universal_backend.py`

### 3.1 DTO → Neo4j Properties

```python
async def create(self, entity: TaskDTO) -> Result[TaskDTO]:
    """
    Persist DTO to Neo4j.

    Flow:
    1. Convert DTO to dict (to_dict method)
    2. Generate Cypher CREATE query
    3. Execute query
    4. Return persisted DTO
    """

    # Convert DTO to dictionary
    props = entity.to_dict()
    # {
    #     "uid": "task_a1b2c3d4e5f67890",
    #     "user_uid": "user_5f2c8e1a9b3d7046",
    #     "title": "Review Python decorators",
    #     "priority": "high",  # Enum converted to string
    #     "status": "draft",   # Enum converted to string
    #     "due_date": "2026-02-05",  # Date converted to ISO string
    #     "created_at": "2026-01-29T10:30:00",  # Datetime converted to ISO string
    #     ...
    # }

    # Generate and execute Cypher
    query = """
    CREATE (n:Task $props)
    RETURN n
    """
    result = await self.driver.execute_query(query, props=props)

    return Result.ok(entity)
```

### 3.2 DTO Serialization Helper

**File**: `/core/models/task/task_dto.py:229-238`

```python
def to_dict(self) -> dict:
    """Convert DTO to dictionary for database operations."""
    from core.models.dto_helpers import dto_to_dict

    return dto_to_dict(
        self,
        enum_fields=["status", "priority", "recurrence_pattern"],  # Convert enums to strings
        date_fields=["due_date", "scheduled_date", "completion_date"],  # Convert dates to ISO
        datetime_fields=["created_at", "updated_at"],  # Convert datetimes to ISO
    )
```

**Neo4j node created**:
```cypher
(:Task {
    uid: "task_a1b2c3d4e5f67890",
    user_uid: "user_5f2c8e1a9b3d7046",
    title: "Review Python decorators",
    description: "Study decorators before the advanced class",
    due_date: "2026-02-05",
    priority: "high",
    status: "draft",
    duration_minutes: 60,
    created_at: "2026-01-29T10:30:00.000000",
    updated_at: "2026-01-29T10:30:00.000000",
    goal_progress_contribution: 0.0,
    knowledge_mastery_check: false
})
```

---

## Stage 4: Read Path (Neo4j → Tier 2 → Tier 3 → JSON)

When the client requests the task: `GET /api/tasks/get?uid=task_a1b2c3d4e5f67890`

### 4.1 Neo4j → DTO (Tier 2)

```python
async def get(self, uid: str) -> Result[TaskDTO]:
    """Fetch task from Neo4j."""

    # Execute Cypher query
    query = """
    MATCH (n:Task {uid: $uid})
    RETURN n
    """
    result = await self.driver.execute_query(query, uid=uid)

    # Convert Neo4j record to dict
    record = result.records[0]
    node_dict = dict(record["n"])
    # {
    #     "uid": "task_a1b2c3d4e5f67890",
    #     "user_uid": "user_5f2c8e1a9b3d7046",
    #     "title": "Review Python decorators",
    #     "priority": "high",  # String from Neo4j
    #     "status": "draft",   # String from Neo4j
    #     "due_date": "2026-02-05",  # ISO string from Neo4j
    #     "created_at": "2026-01-29T10:30:00.000000",  # ISO string from Neo4j
    #     ...
    # }

    # Convert dict → DTO
    task_dto = TaskDTO.from_dict(node_dict)
    return Result.ok(task_dto)
```

### 4.2 DTO Deserialization Helper

**File**: `/core/models/task/task_dto.py:159`

```python
@classmethod
def from_dict(cls, data: dict) -> TaskDTO:
    """Create DTO from dictionary (Neo4j record)."""
    from core.models.dto_helpers import dto_from_dict

    return dto_from_dict(
        cls,
        data,
        enum_fields={  # Convert strings → enums
            "status": EntityStatus,
            "priority": Priority,
            "recurrence_pattern": RecurrencePattern,
        },
        date_fields=["due_date", "scheduled_date", "completion_date"],  # ISO → date
        datetime_fields=["created_at", "updated_at"],  # ISO → datetime
        list_fields=["tags", "knowledge_patterns_detected"],  # Ensure lists
        dict_fields=["knowledge_confidence_scores", "metadata"],  # Ensure dicts
    )
```

**Result**: Reconstituted DTO with correct Python types.

### 4.3 DTO → Domain Model (Tier 2 → Tier 3)

**File**: `/core/models/task/task.py` — `Task.from_dto`

```python
@classmethod
def from_dto(cls, dto: EntityDTO | TaskDTO) -> Task:
    """Create Task from an EntityDTO or TaskDTO."""
    return cls._from_dto(dto)
```

The domain model (Tier 3) is immutable (a frozen dataclass), carries the business logic
methods, and holds no relationship lists: those are graph edges.

```python
# Business logic examples
task.is_overdue()  # → False
task.get_days_remaining()  # → days until due_date, None if it has none
task.learning_alignment_score()  # → 0.0 (no source path step, no mastery check)
```

### 4.4 Relationships Are Read Separately (GRAPH-NATIVE)

The `Task` holds no relationship lists. A service that needs them reads the graph:

```python
rels: TaskRelationships = await TaskRelationships.fetch(
    task.uid,
    tasks_service.relationships,
)

# TaskRelationships dataclass holds the relationship UIDs
# rels.applies_knowledge_uids = ["ku.python-decorators"]
# rels.prerequisite_knowledge_uids = ["ku.python-functions"]
# rels.subtask_uids = []
# rels.enables_task_uids = []
```

### 4.5 Domain → JSON

**File**: `/adapters/inbound/boundary.py`

There is no per-entity response model. A route returns `Result[Task]`, and `@boundary_handler`
converts it: `result_to_response` puts the value through `jsonable_content`, which turns the
frozen dataclass, its enums and its dates into plain JSON types.

### 4.6 HTTP Response

The body is every field of the `Task`, abridged here:

```json
{
  "uid": "task_a1b2c3d4e5f67890",
  "title": "Review Python decorators",
  "entity_type": "task",
  "description": "Study decorators before the advanced class",
  "status": "draft",
  "visibility": "private",
  "created_at": "2026-01-29T10:30:00",
  "updated_at": "2026-01-29T10:30:00",
  "user_uid": "user_5f2c8e1a9b3d7046",
  "priority": "high",
  "due_date": "2026-02-05",
  "duration_minutes": 60,
  "completion_updates_goal": true
}
```

`applies_knowledge_uids` is not in the body: the request's list became edges.

---

## Visual Summary: Complete Data Flow

```
USER CLIENT
     │
     │ POST /api/tasks/create + JSON
     ▼
┌────────────────────────────────────────────┐
│ TIER 1: Pydantic Request Model             │
│ (External boundary - validation)           │
│                                            │
│ TaskCreateRequest                          │
│ - Validates JSON structure                 │
│ - Validates types and constraints          │
│ - Returns 400 on failure                   │
└────────────────┬───────────────────────────┘
                 │ Validated data
                 ▼
┌────────────────────────────────────────────┐
│ TIER 2: DTO (Data Transfer Object)         │
│ (Mutable - service layer operations)       │
│                                            │
│ TaskDTO                                    │
│ - Generate UID                             │
│ - Set timestamps                           │
│ - Mutable for updates                      │
│ - Properties only (no relationships)       │
└────────────────┬───────────────────────────┘
                 │ DTO + Relationships
                 ▼
┌────────────────────────────────────────────┐
│ NEO4J DATABASE                             │
│ (Graph storage)                            │
│                                            │
│ Task Node (properties)                     │
│ + OWNS edge (User → Task)                  │
│ + APPLIES_KNOWLEDGE edges (Task → KU)      │
│ + REQUIRES_KNOWLEDGE edges (Task → KU)     │
└────────────────┬───────────────────────────┘
                 │
                 │ Read request
                 ▼
┌────────────────────────────────────────────┐
│ TIER 2: DTO (Reconstituted)                │
│ (From Neo4j properties)                    │
│                                            │
│ TaskDTO.from_dict(neo4j_record)            │
│ - Convert strings → enums                  │
│ - Convert ISO strings → dates/datetimes    │
└────────────────┬───────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────┐
│ TIER 3: Domain Model (Immutable)           │
│ (Business logic - frozen dataclass)        │
│                                            │
│ Task.from_dto(dto)                         │
│ - Immutable (frozen=True)                  │
│ - Business logic methods                   │
│ - is_overdue(), get_days_remaining(), etc. │
└────────────────┬───────────────────────────┘
                 │ Result[Task]
                 ▼
┌────────────────────────────────────────────┐
│ HTTP BOUNDARY: @boundary_handler           │
│ (External boundary - serialization)        │
│                                            │
│ jsonable_content(task)                     │
│ - Every field of the Task, JSON-safe       │
│ - No relationship lists: those are edges   │
└────────────────┬───────────────────────────┘
                 │ JSON response
                 ▼
       USER CLIENT (receives JSON)
```

---

## Key Insights

### Why Three Tiers?

1. **Tier 1 (Pydantic)** - External boundary protection
   - Validates ALL external input before it reaches business logic
   - Prevents 500 errors from malformed data
   - Auto-generates 400 responses with field-level errors
   - Self-documenting API contracts

2. **Tier 2 (DTO)** - Service layer flexibility
   - Mutable for service operations (status updates, field modifications)
   - Clean serialization to/from database
   - No business logic - pure data transfer
   - Relationship UIDs handled separately (graph-native)

3. **Tier 3 (Domain)** - Business logic safety
   - Immutable (frozen dataclass) prevents accidental mutations
   - Business logic methods (is_overdue, get_days_remaining, etc.)
   - Type-safe via `DomainModelProtocol`
   - Used by intelligence services for calculations

### Where Relationships Live

**GRAPH-NATIVE DESIGN**: Relationship lists (like `applies_knowledge_uids`) are NOT stored in DTOs or Domain models.

**Storage**: Neo4j edges only
- `(task:Task)-[:APPLIES_KNOWLEDGE]->(ku:KU)`
- `(task:Task)-[:REQUIRES_KNOWLEDGE]->(ku:KU)`

**Access**: Via `TaskRelationships.fetch()`
```python
rels = await TaskRelationships.fetch(task_uid, relationships_service)
knowledge_uids = rels.applies_knowledge_uids  # Fetched from graph
```

**Why separate?**
- Reduces DTO bloat (no large UID lists in every DTO)
- Graph queries are more efficient for relationships
- Allows dynamic relationship queries without DTO changes

### When Conversions Happen

| Stage | From | To | Purpose |
|-------|------|-----|---------|
| Create | Pydantic Request | DTO | Prepare for persistence |
| Persist | DTO | Neo4j dict | Store in database |
| Read | Neo4j dict | DTO | Reconstitute from storage |
| Business Logic | DTO | Domain Model | Use business logic methods |
| Response | Domain Model | JSON (`jsonable_content`) | Return to client |

---

## Common Questions

### Q: Why not go directly from Pydantic to Domain?

**A**: Service layer needs mutability.

**Example**: Task status update
```python
# Get task from database → DTO (mutable)
task_dto = await backend.get(uid)

# Update a field (requires mutability)
task_dto.title = "Review decorators"
task_dto.updated_at = datetime.now()

# Persist changes — pass native Python types, backend auto-serializes
# (a status change is not this write: it goes through update_with_status_guard, ADR-087)
await backend.update(uid, {"title": "Review decorators", "metadata": {"reason": "renamed"}})
# ↑ The dict is auto-serialized via to_neo4j_node() in _CrudMixin.update()
#   dicts → JSON strings, enums → values, dates → ISO strings
#   Services never call json.dumps() before backend.update().
```

If we used frozen domain models directly, we'd have to create a new instance for every field change.

### Q: When should I skip Tier 3?

**A**: When there's minimal business logic.

**Examples of simplified domains** (skip Tier 3):
- **Finance**: Admin-only bookkeeping, simple CRUD → uses DTO directly
- **Journals**: Content storage, minimal logic → uses DTO directly

**Keep Tier 3 when**:
- Complex business logic methods needed
- Immutability is semantically important
- Protocol-based generic code requires `DomainModelProtocol`

### Q: Why does a response carry no `applies_knowledge_uids`?

**A**: The list belongs to the request. The service writes it as edges and the `Task` holds
no copy, so the JSON has none. A service that needs the UIDs reads the graph:

```python
rels = await TaskRelationships.fetch(uid, tasks_service.relationships)
rels.applies_knowledge_uids  # ← from the graph
```

---

## Next Steps

- Read [Three-Tier Type System](../patterns/three_tier_type_system.md) for architectural rationale
- See [API Validation Patterns](../patterns/API_VALIDATION_PATTERNS.md) for Pydantic patterns
- Explore [Graph-Native Design](../patterns/GRAPH_NATIVE_PLACEHOLDERS.md) for relationship handling

---

**TL;DR**:
- **Tier 1 (Pydantic)**: Validates at API boundaries (400 on failure)
- **Tier 2 (DTO)**: Mutable for service operations, serializes to Neo4j
- **Tier 3 (Domain)**: Immutable business logic, type-safe protocols
- **Relationships**: Stored as Neo4j edges, fetched separately via `*Relationships.fetch()`
