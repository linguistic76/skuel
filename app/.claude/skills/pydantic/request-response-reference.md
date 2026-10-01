# Request & Response Model Reference

Patterns for API request/response models in SKUEL.

## Request Model Types

### CreateRequest - Create Bodies

For creating new entities:

```python
# core/models/task/task_request.py (abridged)
from pydantic import Field
from core.models.request_base import CreateRequestBase

class TaskCreateRequest(CreateRequestBase):
    """External API request for creating a task."""

    # Required fields (no default)
    title: str = Field(min_length=1, max_length=200, description="Task title")

    # Optional fields (with defaults)
    description: str | None = Field(
        default=None, max_length=2000, description="Detailed description"
    )
    due_date: date | None = Field(default=None)
    duration_minutes: int | None = Field(default=None, ge=5, le=480)

    # Enum fields with descriptions
    priority: Priority = Field(default=Priority.MEDIUM, description="Task priority")
    status: EntityStatus = Field(default=EntityStatus.DRAFT, description="Initial status")
```

Two doors bind it: the CRUD factory's `POST /api/tasks/create` reads it with `parse_body`
(JSON or form, by Content-Type), and the UI's `POST /tasks/create` with `parse_form_body`.

### UpdateRequest - Partial Updates

For partial updates (all fields optional):

```python
class TaskUpdateRequest(UpdateRequestBase):
    """Bound by the CRUD factory's /api/tasks/update?uid= route."""

    # ALL fields optional for partial update
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    due_date: date | None = None
    priority: Priority | None = None
    actual_minutes: int | None = Field(default=None, ge=0)

    def to_intent(self) -> TaskUpdateIntent:
        """Build the typed TaskUpdateIntent (ADR-066) from explicitly-set fields.

        Fields absent from `model_fields_set` stay `UNSET` (untouched); fields the
        client sent — including an explicit `None` — are carried through. Enum values
        are lowered to their `.value` to match the persistence boundary.
        """
        set_fields = self.model_fields_set

        def when_set[T](name: str, value: T) -> T | Unset:
            return value if name in set_fields else UNSET

        return TaskUpdateIntent(
            title=when_set("title", self.title),
            description=when_set("description", self.description),
            priority=when_set(
                "priority", self.priority.value if self.priority is not None else None
            ),
            # one when_set(...) per updatable field
        )
```

**Usage (ADR-066 — the service contract takes the typed intent, never a dict):**

```python
# Client sends a partial update
request = TaskUpdateRequest(priority=Priority.HIGH)

# Build the typed intent — only the set fields are non-UNSET
intent = request.to_intent()  # TaskUpdateIntent(priority="high")

await tasks_service.update_task(uid, intent)
```

> The generic `CRUDRouteFactory` calls `request.to_intent()` for you when the request is
> `SupportsToIntent` (every Activity Domain `*UpdateRequest` is); any other update model
> falls back to a `RawChanges` patch from `model_dump(exclude_unset=True)`. See
> [ADR-066](/docs/decisions/ADR-066-typed-update-intents.md).

### Status Changes

A status change is not a request model. `create_activity_field_api_routes` registers
`POST /api/{domain}/{uid}/status`, which reads `form["status"]`; the service validates the
transition inside the status-guarded write (ADR-087). `TaskStatusUpdateRequest` exists in
`task_request.py` but no route binds it.

### Query Parameters - GET

A handful of query params go through the silent/strict helpers in
`adapters/inbound/route_factories/route_helpers.py` (`parse_int_query_param`,
`parse_date_param_strict`, …). A form with many checkbox/enum/optional-string facets builds
its model with a `from_form_params()` classmethod — see
[Methods on Request Models](#methods-on-request-models). `FilterRequestBase`
(`core/models/request_base.py`) is the base for such models.

## Response Models

### Routes Return Domain Models

An API route returns `Result[Task]` — the frozen domain model — and `@boundary_handler`
serializes it (`jsonable_content` in `adapters/inbound/boundary.py`, via Pydantic's
`to_jsonable_python`). There is no per-entity Pydantic response layer to convert through:
`TaskResponse` / `TaskListResponse` exist in `task_request.py` but no route builds them.

A Pydantic response model earns its place when the payload is not an entity — the search
envelope below.

### Search Response with Facets

```python
# core/models/search_request.py (abridged)
class FacetCount(BaseModel):
    """Count of results per facet value - for UI filter badges."""

    facet_type: str = Field(..., description="Type of facet (sel_category, learning_level, etc.)")
    facet_value: str = Field(..., description="Value of facet (self_awareness, beginner, etc.)")
    count: int = Field(..., ge=0, description="Number of results with this facet")
    display_name: str | None = Field(default=None, description="Human-readable display name")


class SearchResponse(BaseModel):
    """Search results with facet counts"""

    # Results (polymorphic - can be ku, task, event, etc.)
    results: list[dict[str, Any]] = Field(default_factory=list)

    # Rows in THIS page — search is top-N: one page-only query, no match-set
    # count. Never read `total` as "how many matched".
    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1)
    offset: int = Field(..., ge=0)

    # Query info
    query_text: str | None = None
    domain: str | None = None

    # Facet counts for filtering UI
    facet_counts: dict[str, list[FacetCount]] = Field(default_factory=dict)

    # Performance
    search_time_ms: float | None = None

    def has_results(self) -> bool:
        return len(self.results) > 0
```

`SearchRouter` builds it (`core/orchestrator/search_router.py`).

## ConfigDict Reference

### Common Configurations

```python
from pydantic import ConfigDict

# The bases carry the shared config — core/models/request_base.py
class RequestBase(BaseModel):
    model_config = ConfigDict()  # Pydantic V2 defaults: enums stay enum members


class ResponseBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # build from dataclass attributes


# A model that rejects unknown fields — core/models/transcription/transcription.py
class TranscriptionCreateRequest(BaseModel):
    audio_file_path: str = Field(..., description="Path to audio file")
    language: str = Field(default="en", description="Language code for transcription")

    model_config = {"extra": "forbid"}
```

### ConfigDict Options Table

| Option | Pydantic default | Use Case |
|--------|------------------|----------|
| `use_enum_values=True` | False | Store `.value` strings instead of enum members |
| `from_attributes=True` | False | Create from ORM/dataclass attributes |
| `validate_assignment=True` | False | Validate on attribute assignment |
| `extra="forbid"` | "ignore" | Reject extra fields |
| `str_strip_whitespace=True` | False | Auto-strip all strings |
| `json_schema_extra` | None | OpenAPI examples |

## Literal Types

Enums are the default for a fixed vocabulary — they carry behavior (`get_color()`, sort
order) and are reused across models. A `Literal` is for a one-off constraint:

```python
# core/models/search_request.py — built by from_form_params()
connected_direction: Literal["outgoing", "incoming", "both"] = Field(default="outgoing")
```

Either works on a model read through `parse_body` / `parse_json_body` / `parse_form_body`,
the only way a route binds a request model: the helper hands Pydantic the raw value, and a bad one
is a 400. Never declare the model as a handler parameter (`body: Model`) — FastHTML coerces
each value by calling its annotation before Pydantic sees it, and `Literal(...)` /
`Priority("bad")` raise outside the model, a 500.

### When to Use Literal vs Enum

| Use Literal | Use Enum |
|-------------|----------|
| One-off constraint | Reused across models |
| No behavior needed | Methods (`get_color`, sort order) |

## Methods on Request Models

Add helper methods for complex transformations:

```python
# core/models/search_request.py (abridged)
class SearchRequest(BaseModel):
    """Search request with graph-aware filters"""

    query_text: str | None = None
    status: EntityStatus | None = None
    ready_to_learn: bool = False
    supports_goals: bool = False

    @classmethod
    def from_form_params(
        cls,
        *,
        query: str = "",
        user_uid: UserUID | None = None,
        status: str | None = None,
        ready_to_learn: str | None = None,
        supports_goals: str | None = None,
        # ... one keyword per form field
    ) -> SearchRequest:
        """Build from raw HTML form strings — handles all coercion.

        Encapsulates: empty string → None, checkbox "true" → bool,
        string → enum parsing, extended_facets assembly.
        Routes stay thin — all normalization lives on the model.
        """

    def to_property_filters(self) -> dict[str, Any]:
        """Convert facets to property filters"""

    def to_relationship_filters(self) -> RelationshipFilters:
        """Capture active relationship flags as a frozen intent (NOT Cypher).

        A request model must not author Cypher (SKUEL021 / ADR-044). It hands
        the active-flag *intent* down; the flag→Cypher mapping lives below the
        boundary in adapters/.../relationship_filter_fragments.py.
        """

    def has_relationship_filters(self) -> bool:
        """Check if any graph-aware filters are active"""

    def get_search_strategy(self) -> str:
        """Determine optimal search strategy"""
```

**Two construction paths:**
- `from_form_params()` — for HTML form routes (raw strings need coercion). A value it
  rejects raises `ValidationError`, which `/search/results` catches and renders with
  `render_search_error` (served as 200).
- Regular constructor — for API/programmatic use (already-typed values)

## model_dump() Patterns

### Basic Serialization

```python
request = TaskCreateRequest(title="Test", priority=Priority.HIGH)

# All fields
data = request.model_dump()
# {'title': 'Test', 'priority': <Priority.HIGH: 'high'>, 'description': None, ...}

# Exclude None values
data = request.model_dump(exclude_none=True)

# Only the fields the client set — a partial update
data = request.model_dump(exclude_unset=True)
# {'title': 'Test', 'priority': <Priority.HIGH: 'high'>}

# Serialize enums to values
data = request.model_dump(mode="json")
# {'title': 'Test', 'priority': 'high', ...}
```

### Selective Field Export

```python
# Include specific fields
data = request.model_dump(include={"title", "priority"})

# Exclude fields
data = request.model_dump(exclude={"description"})
```

## FastHTML Integration

### Form to Request Model

A form posts a browser encoding; `parse_form_body` turns empty strings into `None`, splits
`list[T]` fields, validates, and returns a `Result`. Never construct the model from the raw
form yourself: `TaskCreateRequest(**form)` *raises* on bad input, so the request ends in a
boundary's safety net (a 500 from `@boundary_handler`) instead of the form back with a
banner.

```python
# adapters/inbound/tasks_ui.py
@rt("/tasks/create", methods=["POST"])
@csrf_protected
async def task_create_submit(request: Request) -> FT | RedirectResponse:
    """Validate the form, create the task, redirect to its detail page."""
    user_uid = require_authenticated_user(request)

    parsed = await parse_form_body(request, TaskCreateRequest)
    if parsed.is_error:
        # UI route: re-render the form with a banner (served as 200)
        err = parsed.expect_error()
        content = Div(
            PageHeader("New Task"),
            render_error_banner(err.display_message),
            TaskCreateForm(),
            cls="space-y-6",
        )
        return render_activity_sidebar_page(content, active="tasks", request=request)

    result = await tasks_service.core.create_task(parsed.value, user_uid)
    if result.is_error:
        ...  # the same page, with the service's display_message

    return RedirectResponse(f"/tasks/detail?uid={result.value.uid}", status_code=303)
```

### Query Params to a Model

```python
# adapters/inbound/search_routes.py (abridged)
try:
    search_request = SearchRequest.from_form_params(
        query=query,
        user_uid=user_uid,
        status=status,
        ready_to_learn=ready_to_learn,
    )
except ValueError as e:  # a Pydantic ValidationError is a ValueError
    logger.error(f"Invalid filter value: {e}")
    return render_search_error("Invalid filter selection. Please try again.", "warning")
```
