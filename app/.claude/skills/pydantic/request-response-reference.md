# Request & Response Model Reference

Patterns for API request/response models in SKUEL.

## Request Model Types

### CreateRequest - POST Bodies

For creating new entities:

```python
from pydantic import Field
from core.models.request_base import CreateRequestBase

class TaskCreateRequest(CreateRequestBase):
    """POST /api/tasks - Create a new task"""

    # Required fields (no default)
    title: str = Field(min_length=1, max_length=200)

    # Optional fields (with defaults)
    description: str | None = Field(None, max_length=2000)
    due_date: date | None = None
    priority: Priority = Field(default=Priority.MEDIUM)
    tags: list[str] = Field(default_factory=list)

    # Enum fields with descriptions
    status: ActivityStatus = Field(
        default=ActivityStatus.PENDING,
        description="Initial task status"
    )
```

### UpdateRequest - PATCH Bodies

For partial updates (all fields optional):

```python
class TaskUpdateRequest(UpdateRequestBase):
    """PATCH /api/tasks/{uid} - Update task fields"""

    # ALL fields optional for partial update
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    due_date: date | None = None
    priority: Priority | None = None
    tags: list[str] | None = None

    def get_updates(self) -> dict[str, Any]:
        """Return only fields that were explicitly set"""
        return self.model_dump(exclude_unset=True)
```

**Usage:**

```python
# Client sends partial update
request = TaskUpdateRequest(priority=Priority.HIGH)

# Only update fields that were set
updates = request.get_updates()
# {'priority': Priority.HIGH}

await service.update(uid, updates)
```

### FilterRequest - GET Query Params

For list/search endpoints:

```python
class TaskFilterRequest(FilterRequestBase):
    """GET /api/tasks - Filter tasks"""

    # Enum filters
    status: ActivityStatus | None = None
    priority: Priority | None = None
    domain: Domain | None = None

    # Date range filters
    due_after: date | None = None
    due_before: date | None = None

    # Text search
    query: str | None = Field(None, min_length=1, max_length=200)

    # Pagination
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)

    # Sorting
    sort_by: Literal["created_at", "due_date", "priority"] = "created_at"
    sort_order: Literal["asc", "desc"] = "desc"

    def to_filters(self) -> dict[str, Any]:
        """Convert to backend filter dict"""
        filters = {}
        if self.status:
            filters["status"] = self.status.value
        if self.priority:
            filters["priority"] = self.priority.value
        if self.due_after:
            filters["due_date__gte"] = self.due_after
        if self.due_before:
            filters["due_date__lte"] = self.due_before
        return filters
```

### StatusUpdateRequest - State Changes

For status transitions:

```python
class TaskStatusUpdateRequest(RequestBase):
    """POST /api/tasks/{uid}/status - Change task status"""

    status: ActivityStatus = Field(description="New status")
    completion_date: date | None = Field(None, description="When completed")
    cancelled_reason: str | None = Field(None, max_length=500)

    @field_validator("completion_date")
    @classmethod
    def auto_set_completion(cls, v, info: ValidationInfo):
        if info.data.get("status") == ActivityStatus.COMPLETED and not v:
            return date.today()
        return v

    @field_validator("cancelled_reason")
    @classmethod
    def require_reason(cls, v, info: ValidationInfo):
        if info.data.get("status") == ActivityStatus.CANCELLED and not v:
            raise ValueError("Reason required for cancellation")
        return v
```

## Response Models

### Basic Response

```python
from core.models.request_base import ResponseBase

class TaskResponse(ResponseBase):
    """Response model for a single task"""

    # Identity
    uid: str

    # Core fields
    title: str
    description: str | None
    due_date: date | None
    priority: Priority
    status: ActivityStatus

    # Timestamps
    created_at: datetime
    updated_at: datetime

    # Computed fields (from domain model)
    is_overdue: bool
    is_recurring: bool
    days_until_due: int | None

    # Graph relationships (from separate query)
    subtask_uids: list[str] = Field(default_factory=list)
    related_goal_uids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
```

### The from_dto() Pattern

Create response models from DTOs with computed fields:

```python
class TaskResponse(ResponseBase):
    uid: str
    title: str
    is_overdue: bool  # Computed
    impact_score: float  # Computed

    @classmethod
    def from_dto(
        cls,
        dto: "TaskDTO",
        relationships: "TaskRelationships | None" = None
    ) -> "TaskResponse":
        """Create response from DTO with optional graph data"""
        from core.models.task.task import Task

        # Create domain model for business logic
        task = Task.from_dto(dto)

        return cls(
            uid=dto.uid,
            title=dto.title,
            status=dto.status,
            priority=dto.priority,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
            # Computed from domain model
            is_overdue=task.is_overdue(),
            impact_score=task.calculate_impact_score(),
            days_until_due=task.days_until_due(),
            # From graph relationships
            subtask_uids=list(relationships.subtask_uids) if relationships else [],
            related_goal_uids=list(relationships.goal_uids) if relationships else [],
        )
```

### List Response with Pagination

```python
class TaskListResponse(BaseModel):
    """Paginated list of tasks"""

    items: list[TaskResponse]
    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1)
    offset: int = Field(..., ge=0)

    def has_more(self) -> bool:
        return (self.offset + self.limit) < self.total

    def get_page_info(self) -> dict[str, int]:
        return {
            "current_page": (self.offset // self.limit) + 1,
            "total_pages": (self.total + self.limit - 1) // self.limit,
            "showing": len(self.items),
        }

    @classmethod
    def from_results(
        cls,
        dtos: list["TaskDTO"],
        total: int,
        limit: int,
        offset: int
    ) -> "TaskListResponse":
        return cls(
            items=[TaskResponse.from_dto(dto) for dto in dtos],
            total=total,
            limit=limit,
            offset=offset,
        )
```

### Search Response with Facets

```python
class FacetCount(BaseModel):
    """Single facet value with count"""
    value: str
    count: int
    label: str | None = None


class SearchResponse(BaseModel):
    """Search results with facet counts"""

    # Results
    results: list[dict[str, Any]] = Field(default_factory=list)
    total: int = Field(..., ge=0)

    # Pagination
    limit: int = Field(..., ge=1)
    offset: int = Field(..., ge=0)

    # Search context
    query_text: str | None = None
    domain: str | None = None

    # Facet counts for filtering UI
    facet_counts: dict[str, list[FacetCount]] = Field(default_factory=dict)

    # Applied filters (echo back what was searched)
    applied_filters: dict[str, Any] = Field(default_factory=dict)

    # Performance
    search_time_ms: float | None = None
    timestamp: datetime = Field(default_factory=datetime.now)

    def has_results(self) -> bool:
        return len(self.results) > 0

    def has_more_pages(self) -> bool:
        return (self.offset + self.limit) < self.total
```

## ConfigDict Reference

### Common Configurations

```python
from pydantic import ConfigDict

# Request models - keep enums as objects
class TaskCreateRequest(BaseModel):
    priority: Priority

    model_config = ConfigDict(
        use_enum_values=False,  # Keep Priority.HIGH, not "high"
    )


# Response models - serialize enums
class TaskResponse(BaseModel):
    priority: Priority

    model_config = ConfigDict(
        use_enum_values=True,   # Serialize as "high"
        from_attributes=True,   # Allow creation from ORM/dataclass
    )


# With JSON schema example
class GoalCreateRequest(BaseModel):
    title: str
    timeframe: GoalTimeframe

    model_config = ConfigDict(
        use_enum_values=False,
        json_schema_extra={
            "example": {
                "title": "Complete ML Course",
                "timeframe": "quarterly",
                "priority": "high",
            }
        }
    )
```

### ConfigDict Options Table

| Option | Default | Use Case |
|--------|---------|----------|
| `use_enum_values=False` | True | Keep enum objects for type safety |
| `use_enum_values=True` | True | Serialize enums to strings |
| `from_attributes=True` | False | Create from ORM/dataclass attributes |
| `validate_assignment=True` | False | Validate on attribute assignment |
| `extra="forbid"` | "ignore" | Reject extra fields |
| `str_strip_whitespace=True` | False | Auto-strip all strings |
| `json_schema_extra` | None | OpenAPI examples |

## Literal Types

For strict string validation without defining enums:

```python
from typing import Literal

# Define literal types
ProcessingStatus = Literal[
    "pending", "processing", "completed", "failed"
]
AudioFormat = Literal["mp3", "wav", "m4a", "webm", "ogg"]
Language = Literal["en", "es", "fr", "de", "zh", "ja"]

class TranscriptionRequest(BaseModel):
    audio_format: AudioFormat
    language: Language = "en"
    status: ProcessingStatus = "pending"
```

### When to Use Literal vs Enum

| Use Literal | Use Enum |
|-------------|----------|
| Simple string constraints | Need methods (get_color, etc.) |
| One-off validation | Reused across models |
| API contract only | Business logic attached |
| No behavior needed | Dynamic behavior (sort order) |

## Methods on Request Models

Add helper methods for complex transformations:

```python
class SearchRequest(BaseModel):
    """Search request with graph-aware filters"""

    query_text: str | None = None
    domain: Domain | None = None
    ready_to_learn: bool = False
    supports_goals: bool = False
    builds_on_mastered: bool = False

    def to_neo4j_filters(self) -> dict[str, Any]:
        """Convert facets to Neo4j property filters"""
        filters = {}
        if self.domain:
            filters["domain"] = self.domain.value
        return filters

    def to_graph_patterns(self) -> dict[str, str]:
        """Convert boolean filters to Cypher patterns"""
        patterns = {}
        if self.ready_to_learn:
            patterns["ready_to_learn"] = """
            NOT EXISTS {
                MATCH (ku)-[:REQUIRES_KNOWLEDGE]->(prereq:Curriculum)
                WHERE NOT EXISTS {
                    MATCH (user:User {uid: $user_uid})-[:MASTERED]->(prereq)
                }
            }
            """
        if self.supports_goals:
            patterns["supports_goals"] = """
            EXISTS {
                MATCH (ku)<-[:REQUIRES_KNOWLEDGE]-(goal:Goal)
                WHERE goal.status = 'active'
            }
            """
        return patterns

    def has_graph_filters(self) -> bool:
        """Check if any graph-aware filters are active"""
        return any([
            self.ready_to_learn,
            self.supports_goals,
            self.builds_on_mastered,
        ])

    def get_search_strategy(self) -> str:
        """Determine optimal search strategy"""
        if self.has_graph_filters():
            return "graph_aware"
        elif self.query_text:
            return "text_search"
        else:
            return "filter_only"
```

## model_dump() Patterns

### Basic Serialization

```python
request = TaskCreateRequest(title="Test", priority=Priority.HIGH)

# All fields
data = request.model_dump()
# {'title': 'Test', 'priority': <Priority.HIGH>, 'description': None, ...}

# Exclude None values
data = request.model_dump(exclude_none=True)
# {'title': 'Test', 'priority': <Priority.HIGH>}

# Only set fields (for PATCH)
data = request.model_dump(exclude_unset=True)
# {'title': 'Test', 'priority': <Priority.HIGH>}

# Serialize enums to values
data = request.model_dump(mode="json")
# {'title': 'Test', 'priority': 'high', ...}
```

### Selective Field Export

```python
# Include specific fields
data = request.model_dump(include={"title", "priority"})

# Exclude fields
data = request.model_dump(exclude={"created_at", "updated_at"})

# Nested exclusion
data = request.model_dump(exclude={"metadata": {"internal_id"}})
```

## FastHTML Integration

### Form to Request Model

```python
from fasthtml.common import Form, Input, Select

def task_form():
    return Form(
        Input(name="title", placeholder="Task title"),
        Select(
            *[Option(p.value, value=p.value) for p in Priority],
            name="priority"
        ),
        Input(name="due_date", type="date"),
        method="post",
        action="/api/tasks"
    )


@rt("/api/tasks", methods=["POST"])
async def create_task(request):
    form_data = await request.form()

    # Pydantic validates form data
    task_request = TaskCreateRequest(**form_data)

    return await service.create(task_request)
```

### Query Params to Filter Model

```python
@rt("/api/tasks")
async def list_tasks(request):
    # Extract query params
    params = dict(request.query_params)

    # Pydantic validates and provides defaults
    filters = TaskFilterRequest(**params)

    return await service.list(
        filters=filters.to_filters(),
        limit=filters.limit,
        offset=filters.offset,
    )
```
