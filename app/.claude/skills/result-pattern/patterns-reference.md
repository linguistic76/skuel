# Result[T] Patterns Reference

Comprehensive code examples for SKUEL's Result[T] error handling pattern.

## Service Method Patterns

### Complete CRUD Service Example

```python
from core.utils.result_simplified import Result
from core.utils.errors_simplified import Errors

class TasksCoreService(BaseService[BackendOperations[Task], Task]):

    async def create_task(
        self, request: TaskCreateRequest, user_uid: str
    ) -> Result[Task]:
        """Create a task with full validation."""
        # 1. Input validation
        if not user_uid:
            return Result.fail(
                Errors.validation("user_uid is required", field="user_uid")
            )

        if not request.title or len(request.title.strip()) == 0:
            return Result.fail(
                Errors.validation("Title cannot be empty", field="title")
            )

        # 2. Business rule validation
        existing = await self.backend.find_by(
            title=request.title, user_uid=user_uid
        )
        if existing.is_ok and existing.value:
            return Result.fail(
                Errors.business(
                    rule="task_title_unique",
                    message=f"Task '{request.title}' already exists",
                    title=request.title
                )
            )

        # 3. Create entity
        task = Task(
            uid=generate_uid("task"),
            title=request.title,
            description=request.description,
            priority=request.priority,
            created_by=user_uid,
        )

        # 4. Persist
        result = await self.backend.create(task)
        if result.is_error:
            return result  # Propagate database error

        return Result.ok(task)

    async def get_task(self, uid: str, user_uid: str) -> Result[Task]:
        """Get task with ownership verification."""
        # Ownership check returns entity or NOT_FOUND
        return await self.verify_ownership(uid, user_uid)

    async def update_task(
        self, uid: str, updates: dict, user_uid: str
    ) -> Result[Task]:
        """Update task with ownership check."""
        # 1. Verify ownership
        ownership = await self.verify_ownership(uid, user_uid)
        if ownership.is_error:
            return ownership

        task = ownership.value

        # 2. Apply updates
        updated = task.with_updates(updates)

        # 3. Persist
        result = await self.backend.update(uid, updated.to_dict())
        if result.is_error:
            return result

        return Result.ok(updated)

    async def delete_task(self, uid: str, user_uid: str) -> Result[bool]:
        """Delete task with ownership check."""
        ownership = await self.verify_ownership(uid, user_uid)
        if ownership.is_error:
            return ownership

        return await self.backend.delete(uid)
```

### Search Service Example

```python
class TasksSearchService(BaseService[BackendOperations[Task], Task]):

    async def search(
        self, query: str, user_uid: str, limit: int = 20
    ) -> Result[list[Task]]:
        """Search tasks by text query."""
        if not query or len(query.strip()) < 2:
            return Result.fail(
                Errors.validation(
                    "Search query must be at least 2 characters",
                    field="query"
                )
            )

        result = await self.backend.text_search(
            query=query,
            fields=["title", "description"],
            user_uid=user_uid,
            limit=limit
        )

        if result.is_error:
            return result

        return Result.ok(result.value)

    async def get_by_status(
        self, status: ActivityStatus, user_uid: str
    ) -> Result[list[Task]]:
        """Get tasks by status."""
        result = await self.backend.find_by(
            status=status.value,
            user_uid=user_uid
        )

        if result.is_error:
            return result

        return Result.ok(result.value or [])

    async def intelligent_search(
        self, query: str, user_uid: str
    ) -> Result[tuple[list[Task], ParsedQuery]]:
        """NLP-based search with automatic filter extraction."""
        # Parse query for keywords
        parsed = self._parse_query(query)

        # Build filters from parsed keywords
        filters = {}
        if parsed.priority:
            filters["priority"] = parsed.priority.value
        if parsed.status:
            filters["status"] = parsed.status.value

        # Execute search
        result = await self.backend.find_by(
            **filters,
            text_query=parsed.text_query,
            user_uid=user_uid
        )

        if result.is_error:
            return result

        return Result.ok((result.value or [], parsed))
```

### Intelligence Service Example

```python
class TasksIntelligenceService:

    async def get_recommendations(
        self, user_uid: str
    ) -> Result[list[TaskRecommendation]]:
        """Get AI-powered task recommendations."""
        # 1. Get user's current tasks
        tasks_result = await self.tasks_service.get_user_tasks(user_uid)
        if tasks_result.is_error:
            return tasks_result

        # 2. Get user context
        context_result = await self.context_service.build(user_uid)
        if context_result.is_error:
            return context_result

        # 3. Call LLM for recommendations
        try:
            llm_result = await self.llm_service.generate_recommendations(
                tasks=tasks_result.value,
                context=context_result.value
            )
        except Exception as e:
            return Result.fail(
                Errors.integration(
                    service="OpenAI",
                    message=f"Failed to generate recommendations: {e}"
                )
            )

        return Result.ok(llm_result)
```

---

## Route Handler Patterns

### Standard CRUD Routes

```python
from core.utils.error_boundary import boundary_handler

def create_task_routes(_app, rt, services):

    @rt("/api/tasks")
    @boundary_handler(success_status=201)
    async def create_task(request):
        user_uid = require_authenticated_user(request)
        data = await request.json()
        request_obj = TaskCreateRequest(**data)
        return await services.tasks.create_task(request_obj, user_uid)

    @rt("/api/tasks/{uid}")
    @boundary_handler()
    async def get_task(request, uid: str):
        user_uid = require_authenticated_user(request)
        return await services.tasks.get_task(uid, user_uid)

    @rt("/api/tasks/{uid}", methods=["PUT"])
    @boundary_handler()
    async def update_task(request, uid: str):
        user_uid = require_authenticated_user(request)
        updates = await request.json()
        return await services.tasks.update_task(uid, updates, user_uid)

    @rt("/api/tasks/{uid}", methods=["DELETE"])
    @boundary_handler()
    async def delete_task(request, uid: str):
        user_uid = require_authenticated_user(request)
        return await services.tasks.delete_task(uid, user_uid)
```

### Search Routes

```python
@rt("/api/tasks/search")
@boundary_handler()
async def search_tasks(request):
    user_uid = require_authenticated_user(request)
    query = request.query_params.get("q", "")
    limit = int(request.query_params.get("limit", "20"))
    return await services.tasks.search.search(query, user_uid, limit)
```

### Bulk Operation Routes

```python
@rt("/api/tasks/bulk-delete", methods=["POST"])
@boundary_handler()
async def bulk_delete_tasks(request):
    user_uid = require_authenticated_user(request)
    data = await request.json()
    uids = data.get("uids", [])

    if not uids:
        return Result.fail(
            Errors.validation("No task UIDs provided", field="uids")
        )

    return await services.tasks.batch_delete(uids, user_uid)
```

---

## Errors Factory - All Six Categories

### VALIDATION (400)

```python
# Single field - format issue
Result.fail(Errors.validation(
    message="Invalid email format",
    field="email",
    value="not-an-email",
    user_message="Please enter a valid email address"
))

# Single field - required
Result.fail(Errors.validation(
    message="Title is required",
    field="title"
))

# Single field - length constraint
Result.fail(Errors.validation(
    message="Title must be between 3 and 200 characters",
    field="title",
    value="ab"
))
```

### NOT_FOUND (404)

```python
# Resource not found
Result.fail(Errors.not_found(
    resource="Task",
    identifier="task-12345"
))

# With additional context
Result.fail(Errors.not_found(
    resource="User",
    identifier=email,
    lookup_method="email"
))
```

### BUSINESS (422)

```python
# Uniqueness constraint (multi-entity)
Result.fail(Errors.business(
    rule="journal_uniqueness",
    message="Journal with this title already exists on this date",
    title=title,
    date=date
))

# State transition violation
Result.fail(Errors.business(
    rule="task_completion",
    message="Cannot complete task with incomplete dependencies",
    task_uid=uid,
    pending_dependencies=pending
))

# Permission violation
Result.fail(Errors.business(
    rule="curriculum_edit_permission",
    message="Only TEACHER role can edit curriculum content",
    required_role="TEACHER",
    user_role=user.role.value
))

# Capacity constraint
Result.fail(Errors.business(
    rule="daily_task_limit",
    message="Maximum 50 tasks per day reached",
    current_count=50,
    limit=50
))
```

### DATABASE (503)

```python
# Connection failure
Result.fail(Errors.database(
    operation="create_user",
    message="Connection to Neo4j timed out after 30s"
))

# Query execution error
Result.fail(Errors.database(
    operation="find_tasks",
    message="Query execution failed",
    query="MATCH (t:Task) WHERE t.user_uid = $uid RETURN t",
    error_code="Neo.ClientError.Statement.SyntaxError"
))

# Constraint violation (from DB)
Result.fail(Errors.database(
    operation="create_user",
    message="Unique constraint violation on email",
    constraint="user_email_unique"
))
```

### INTEGRATION (502)

```python
# API rate limit
Result.fail(Errors.integration(
    service="OpenAI",
    message="Rate limit exceeded, retry after 60 seconds",
    status_code=429,
    retry_after=60
))

# Service unavailable
Result.fail(Errors.integration(
    service="Deepgram",
    message="Transcription service temporarily unavailable",
    status_code=503
))

# Timeout
Result.fail(Errors.integration(
    service="ElevenLabs",
    message="TTS request timed out after 30 seconds",
    timeout=30
))

# Invalid response
Result.fail(Errors.integration(
    service="GitHub",
    message="Unexpected response format from API",
    expected="JSON array",
    received="null"
))
```

### SYSTEM (500)

```python
# Unexpected exception
try:
    # ... operation
except Exception as e:
    return Result.fail(Errors.system(
        message="Unexpected error during task processing",
        exception=e  # Captures stack trace
    ))

# Configuration error
Result.fail(Errors.system(
    message="Required environment variable OPENAI_API_KEY not set"
))

# Internal invariant violation
Result.fail(Errors.system(
    message="Internal error: task state inconsistent",
    expected_state="PENDING",
    actual_state=task.status
))
```

---

## Functional Composition Examples

### Chaining Operations

```python
async def get_task_with_relationships(
    self, uid: str, user_uid: str
) -> Result[TaskWithContext]:
    # Chain multiple Result-returning operations
    task_result = await self.get_task(uid, user_uid)

    if task_result.is_error:
        return task_result

    task = task_result.value

    # Get related entities
    deps_result = await self.get_dependencies(uid)
    if deps_result.is_error:
        # Continue with empty deps rather than fail
        deps = []
    else:
        deps = deps_result.value

    goals_result = await self.get_related_goals(uid)
    goals = goals_result.or_else([])  # Default to empty list

    return Result.ok(TaskWithContext(
        task=task,
        dependencies=deps,
        related_goals=goals
    ))
```

### Using .map() and .and_then()

```python
# .map() for value transformation (returns plain value)
user_result = await get_user(uid)
email_result = user_result.map(lambda u: u.email)

# .and_then() for chaining Result operations
async def process_task(uid: str) -> Result[ProcessedTask]:
    return (
        await Result.ok(uid)
        .aflat_map(self.get_task)           # Result[Task]
        .aflat_map(self.validate_task)       # Result[Task]
        .aflat_map(self.process_task)        # Result[ProcessedTask]
    )
```

### Error Transformation

```python
# Add context to errors as they propagate
result = await backend.create(entity)
result = result.map_error(lambda e: ErrorContext(
    category=e.category,
    message=e.message,
    code=e.code,
    severity=e.severity,
    details={**e.details, "operation": "create_task", "user_uid": user_uid}
))
```

---

## Testing Patterns

### Unit Test - Success Case

```python
import pytest
from unittest.mock import AsyncMock

@pytest.fixture
def mock_backend():
    return AsyncMock()

@pytest.fixture
def service(mock_backend):
    return TasksCoreService(backend=mock_backend)

async def test_create_task_success(service, mock_backend):
    # Arrange
    request = TaskCreateRequest(title="Test Task")
    user_uid = "user-123"
    mock_backend.find_by.return_value = Result.ok([])  # No existing
    mock_backend.create.return_value = Result.ok(True)

    # Act
    result = await service.create_task(request, user_uid)

    # Assert
    assert result.is_ok
    assert result.value.title == "Test Task"
    mock_backend.create.assert_called_once()
```

### Unit Test - Validation Error

```python
async def test_create_task_empty_title(service):
    request = TaskCreateRequest(title="")
    user_uid = "user-123"

    result = await service.create_task(request, user_uid)

    assert result.is_error
    assert result.error.category == ErrorCategory.VALIDATION
    assert "title" in result.error.details.get("field", "")
```

### Unit Test - Business Rule Violation

```python
async def test_create_task_duplicate_title(service, mock_backend):
    request = TaskCreateRequest(title="Existing Task")
    user_uid = "user-123"
    mock_backend.find_by.return_value = Result.ok([
        Task(uid="task-1", title="Existing Task")
    ])

    result = await service.create_task(request, user_uid)

    assert result.is_error
    assert result.error.category == ErrorCategory.BUSINESS
    assert result.error.code == "task_title_unique"
```

### Unit Test - Database Error Propagation

```python
async def test_create_task_database_error(service, mock_backend):
    request = TaskCreateRequest(title="Test Task")
    user_uid = "user-123"
    mock_backend.find_by.return_value = Result.ok([])
    mock_backend.create.return_value = Result.fail(
        Errors.database("create", "Connection timeout")
    )

    result = await service.create_task(request, user_uid)

    assert result.is_error
    assert result.error.category == ErrorCategory.DATABASE
```

### Integration Test

```python
async def test_task_lifecycle(services, test_user):
    # Create
    create_result = await services.tasks.create_task(
        TaskCreateRequest(title="Integration Test"),
        test_user.uid
    )
    assert create_result.is_ok
    task = create_result.value

    # Read
    get_result = await services.tasks.get_task(task.uid, test_user.uid)
    assert get_result.is_ok
    assert get_result.value.title == "Integration Test"

    # Update
    update_result = await services.tasks.update_task(
        task.uid,
        {"title": "Updated Title"},
        test_user.uid
    )
    assert update_result.is_ok

    # Delete
    delete_result = await services.tasks.delete_task(task.uid, test_user.uid)
    assert delete_result.is_ok

    # Verify deleted
    verify_result = await services.tasks.get_task(task.uid, test_user.uid)
    assert verify_result.is_error
    assert verify_result.error.category == ErrorCategory.NOT_FOUND
```

---

## Backend Decorator Pattern

### @safe_backend_operation

```python
from core.utils.safe_operations import safe_backend_operation

class UniversalNeo4jBackend(Generic[T]):

    @safe_backend_operation("create")
    async def create(self, entity: T) -> Result[T]:
        """Exceptions automatically wrapped in Result.fail()"""
        query = "CREATE (n:$label $props) RETURN n"
        records = await self.execute_query(query, props=entity.to_dict())

        if not records:
            return Result.fail(
                Errors.database("create", "No record returned from CREATE")
            )

        return Result.ok(self._from_record(records[0]))

    @safe_backend_operation("get")
    async def get(self, uid: str) -> Result[T | None]:
        query = "MATCH (n:$label {uid: $uid}) RETURN n"
        records = await self.execute_query(query, uid=uid)

        if not records:
            return Result.ok(None)

        return Result.ok(self._from_record(records[0]))
```

The decorator catches any exceptions and converts them to `Result.fail(Errors.database(...))`.
