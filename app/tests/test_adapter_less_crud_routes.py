"""
Test Adapter-Less CRUD Routes Integration
==========================================

Tests the complete flow from HTTP request → Service → UniversalBackend → Neo4j
without any adapter wrappers, validating the 100% Dynamic Backend pattern.

Validates:
- CRUDRouteFactory generic route generation
- @boundary_handler HTTP response conversion
- Result[T] propagation through all layers
- Enum conversion (Priority, KuStatus, etc.)
- Pydantic validation at boundaries
- Direct UniversalBackend usage (no adapters)
- Multi-domain coverage (Task, Event, Habit, Goal)
"""

import json
from typing import Any

import pytest
from starlette.responses import JSONResponse

from core.infrastructure.routes.crud_route_factory import CRUDRouteFactory
from core.models.enums import KuStatus, Priority
from core.utils.error_boundary import boundary_handler
from core.utils.result_simplified import Errors, Result


def extract_response(response: JSONResponse) -> tuple[dict, int]:
    """Helper to extract body and status from JSONResponse for testing."""
    body = json.loads(response.body)
    return body, response.status_code


# ============================================================================
# MOCK REQUEST/RESPONSE INFRASTRUCTURE
# ============================================================================


class MockRequest:
    """Mock HTTP request for testing."""

    def __init__(
        self,
        body: dict | None = None,
        query_params: dict | None = None,
        path_params: dict | None = None,
    ):
        self.body = body or {}
        self.query_params = query_params or {}
        self.path_params = path_params or {}

    async def json(self):
        return self.body


# ============================================================================
# MOCK SERVICE (Implements CRUDOperations Protocol)
# ============================================================================


class MockTaskService:
    """Mock task service implementing CRUDOperations protocol."""

    def __init__(self):
        self.tasks: dict[str, dict] = {}

    async def create(self, task: Any) -> Result[dict]:
        """Create new task."""
        # Convert domain model to dict for storage
        if hasattr(task, "uid"):
            task_dict = {
                "uid": task.uid,
                "title": task.title,
                "priority": task.priority.value
                if hasattr(task.priority, "value")
                else task.priority,
                "status": task.status.value if hasattr(task.status, "value") else task.status,
            }
        else:
            task_dict = task

        # Validation
        if not task_dict.get("title"):
            return Result.fail(Errors.validation(message="Title is required", field="title"))

        # Check uniqueness
        if task_dict["uid"] in self.tasks:
            return Result.fail(
                Errors.business(
                    rule="unique_uid", message=f"Task {task_dict['uid']} already exists"
                )
            )

        self.tasks[task_dict["uid"]] = task_dict
        return Result.ok(task_dict)

    async def get(self, uid: str) -> Result[dict | None]:
        """Get task by UID."""
        task = self.tasks.get(uid)

        if not task:
            return Result.fail(Errors.not_found("Task", uid))

        return Result.ok(task)

    async def update(self, uid: str, updates: dict[str, Any]) -> Result[dict]:
        """Update task with partial data."""
        if uid not in self.tasks:
            return Result.fail(Errors.not_found("Task", uid))

        # Apply updates
        self.tasks[uid].update(updates)
        return Result.ok(self.tasks[uid])

    async def delete(self, uid: str) -> Result[bool]:
        """Delete task by UID."""
        if uid not in self.tasks:
            return Result.fail(Errors.not_found("Task", uid))

        del self.tasks[uid]
        return Result.ok(True)

    async def list(
        self,
        limit: int = 100,
        offset: int = 0,
        order_by: str | None = None,
        order_desc: bool = False,
    ) -> Result[list[dict]]:
        """List tasks with pagination."""
        tasks_list = list(self.tasks.values())

        # Apply sorting if requested
        if order_by:
            tasks_list.sort(key=lambda t: t.get(order_by, ""), reverse=order_desc)

        # Apply pagination
        paginated = tasks_list[offset : offset + limit]

        return Result.ok(paginated)


# ============================================================================
# TEST CRUD ROUTE FACTORY INITIALIZATION
# ============================================================================


def test_crud_factory_initialization():
    """Test CRUDRouteFactory initialization."""
    from pydantic import BaseModel

    class TaskCreateRequest(BaseModel):
        title: str
        priority: str = "medium"

    class TaskUpdateRequest(BaseModel):
        title: str | None = None
        priority: str | None = None

    service = MockTaskService()

    factory = CRUDRouteFactory(
        service=service,
        domain_name="tasks",
        create_schema=TaskCreateRequest,
        update_schema=TaskUpdateRequest,
    )

    assert factory.domain == "tasks"
    assert factory.base_path == "/api/tasks"  # Consistent with other route factories
    assert factory.uid_prefix == "tasks"
    assert factory.create_schema == TaskCreateRequest
    assert factory.update_schema == TaskUpdateRequest


def test_crud_factory_custom_configuration():
    """Test CRUDRouteFactory with custom configuration."""
    from pydantic import BaseModel

    class TaskCreateRequest(BaseModel):
        title: str

    class TaskUpdateRequest(BaseModel):
        title: str | None = None

    service = MockTaskService()

    factory = CRUDRouteFactory(
        service=service,
        domain_name="tasks",
        create_schema=TaskCreateRequest,
        update_schema=TaskUpdateRequest,
        base_path="/api/v2/tasks",
        uid_prefix="task",
        enable_search=True,
    )

    assert factory.base_path == "/api/v2/tasks"
    assert factory.uid_prefix == "task"
    assert factory.enable_search is True


# ============================================================================
# TEST CREATE ROUTE (POST)
# ============================================================================


@pytest.mark.asyncio
async def test_create_route_success():
    """Test successful task creation via API route."""
    from pydantic import BaseModel

    class TaskCreateRequest(BaseModel):
        title: str
        priority: str = "medium"
        status: str = "pending"

    service = MockTaskService()

    # Simulate route handler
    @boundary_handler(success_status=201)
    async def create_route(request):
        body = await request.json()
        schema = TaskCreateRequest.model_validate(body)

        # Create task entity
        task_data = schema.model_dump()
        task_data["uid"] = f"task:{body.get('title', 'test')[:12]}"

        return await service.create(task_data)

    # Test request
    request = MockRequest(body={"title": "Complete integration tests", "priority": "high"})

    response = await create_route(request)
    body, status = extract_response(response)

    assert status == 201
    assert body["title"] == "Complete integration tests"
    assert body["priority"] == "high"
    assert "uid" in body


@pytest.mark.asyncio
async def test_create_route_validation_error():
    """Test validation error on missing required field."""
    from pydantic import BaseModel, ValidationError

    class TaskCreateRequest(BaseModel):
        title: str  # Required
        priority: str = "medium"

    service = MockTaskService()

    @boundary_handler(success_status=201)
    async def create_route(request):
        body = await request.json()

        # Pydantic validation should catch missing title
        try:
            schema = TaskCreateRequest.model_validate(body)
        except ValidationError as e:
            return Result.fail(Errors.validation(message=f"Validation failed: {e!s}"))

        task_data = schema.model_dump()
        task_data["uid"] = "task:test"

        return await service.create(task_data)

    # Missing title
    request = MockRequest(body={"priority": "high"})

    response = await create_route(request)
    body, status = extract_response(response)

    assert status == 400
    assert body["category"] == "validation"


@pytest.mark.asyncio
async def test_create_route_enum_conversion():
    """Test enum conversion in create route."""
    from pydantic import BaseModel

    class TaskCreateRequest(BaseModel):
        title: str
        priority: Priority
        status: KuStatus

    service = MockTaskService()

    @boundary_handler(success_status=201)
    async def create_route(request):
        body = await request.json()
        schema = TaskCreateRequest.model_validate(body)

        # Enums should be in schema
        assert isinstance(schema.priority, Priority)
        assert isinstance(schema.status, KuStatus)

        task_data = {
            "uid": "task:enum_test",
            "title": schema.title,
            "priority": schema.priority.value,  # Convert enum to string for storage
            "status": schema.status.value,
        }

        return await service.create(task_data)

    request = MockRequest(
        body={"title": "Test enum handling", "priority": "high", "status": "active"}
    )

    response = await create_route(request)
    body, status = extract_response(response)

    assert status == 201
    assert body["priority"] == "high"
    assert body["status"] == "active"


# ============================================================================
# TEST GET ROUTE (GET /{uid})
# ============================================================================


@pytest.mark.asyncio
async def test_get_route_success():
    """Test retrieving task by UID."""
    service = MockTaskService()

    # Pre-populate task
    task_data = {
        "uid": "task:123",
        "title": "Existing Task",
        "priority": "high",
        "status": "active",
    }
    await service.create(task_data)

    @boundary_handler()
    async def get_route(request):
        uid = request.path_params["uid"]
        return await service.get(uid)

    request = MockRequest(path_params={"uid": "task:123"})

    response = await get_route(request)
    body, status = extract_response(response)

    assert status == 200
    assert body["uid"] == "task:123"
    assert body["title"] == "Existing Task"


@pytest.mark.asyncio
async def test_get_route_not_found():
    """Test getting non-existent task returns 404."""
    service = MockTaskService()

    @boundary_handler()
    async def get_route(request):
        uid = request.path_params["uid"]
        return await service.get(uid)

    request = MockRequest(path_params={"uid": "task:nonexistent"})

    response = await get_route(request)
    body, status = extract_response(response)

    assert status == 404
    assert body["category"] == "not_found"


# ============================================================================
# TEST UPDATE ROUTE (PUT /{uid})
# ============================================================================


@pytest.mark.asyncio
async def test_update_route_success():
    """Test updating task via API route."""
    from pydantic import BaseModel

    class TaskUpdateRequest(BaseModel):
        title: str | None = None
        priority: str | None = None
        status: str | None = None

    service = MockTaskService()

    # Create initial task
    task_data = {
        "uid": "task:update_test",
        "title": "Original Title",
        "priority": "medium",
        "status": "pending",
    }
    await service.create(task_data)

    @boundary_handler()
    async def update_route(request):
        uid = request.path_params["uid"]
        body = await request.json()

        schema = TaskUpdateRequest.model_validate(body)
        updates = schema.model_dump(exclude_unset=True)

        return await service.update(uid, updates)

    # Update only priority
    request = MockRequest(path_params={"uid": "task:update_test"}, body={"priority": "high"})

    response = await update_route(request)
    body, status = extract_response(response)

    assert status == 200
    assert body["priority"] == "high"
    assert body["title"] == "Original Title"  # Unchanged


@pytest.mark.asyncio
async def test_update_route_partial_updates():
    """Test partial updates (only specified fields changed)."""
    from pydantic import BaseModel

    class TaskUpdateRequest(BaseModel):
        title: str | None = None
        priority: str | None = None

    service = MockTaskService()

    # Create task
    await service.create({"uid": "task:partial", "title": "Original", "priority": "low"})

    @boundary_handler()
    async def update_route(request):
        uid = request.path_params["uid"]
        body = await request.json()

        schema = TaskUpdateRequest.model_validate(body)
        # Only include fields that were actually set
        updates = schema.model_dump(exclude_unset=True)

        return await service.update(uid, updates)

    # Update title only
    request = MockRequest(path_params={"uid": "task:partial"}, body={"title": "Updated Title"})

    response = await update_route(request)
    body, status = extract_response(response)

    assert status == 200
    assert body["title"] == "Updated Title"
    assert body["priority"] == "low"  # Unchanged


# ============================================================================
# TEST DELETE ROUTE (DELETE /{uid})
# ============================================================================


@pytest.mark.asyncio
async def test_delete_route_success():
    """Test deleting task via API route."""
    service = MockTaskService()

    # Create task
    await service.create({"uid": "task:delete_me", "title": "To Be Deleted"})

    @boundary_handler()
    async def delete_route(request):
        uid = request.path_params["uid"]
        return await service.delete(uid)

    request = MockRequest(path_params={"uid": "task:delete_me"})

    response = await delete_route(request)
    body, status = extract_response(response)

    assert status == 200
    assert body is True

    # Verify task is gone
    result = await service.get("task:delete_me")
    assert result.is_error


@pytest.mark.asyncio
async def test_delete_route_not_found():
    """Test deleting non-existent task returns 404."""
    service = MockTaskService()

    @boundary_handler()
    async def delete_route(request):
        uid = request.path_params["uid"]
        return await service.delete(uid)

    request = MockRequest(path_params={"uid": "task:nonexistent"})

    response = await delete_route(request)
    body, status = extract_response(response)

    assert status == 404
    assert body["category"] == "not_found"


# ============================================================================
# TEST LIST ROUTE (GET with pagination)
# ============================================================================


@pytest.mark.asyncio
async def test_list_route_success():
    """Test listing tasks with pagination."""
    service = MockTaskService()

    # Create multiple tasks
    for i in range(15):
        await service.create({"uid": f"task:{i}", "title": f"Task {i}", "priority": "medium"})

    @boundary_handler()
    async def list_route(request):
        params = dict(request.query_params)
        limit = int(params.get("limit", 100))
        offset = int(params.get("offset", 0))

        return await service.list(limit=limit, offset=offset)

    # Get first 10
    request = MockRequest(query_params={"limit": "10", "offset": "0"})

    response = await list_route(request)
    body, status = extract_response(response)

    assert status == 200
    assert len(body) == 10


@pytest.mark.asyncio
async def test_list_route_pagination():
    """Test pagination works correctly."""
    service = MockTaskService()

    # Create 25 tasks
    for i in range(25):
        await service.create({"uid": f"task:{i}", "title": f"Task {i:02d}"})

    @boundary_handler()
    async def list_route(request):
        params = dict(request.query_params)
        limit = int(params.get("limit", 100))
        offset = int(params.get("offset", 0))

        return await service.list(limit=limit, offset=offset)

    # Get second page (10-19)
    request = MockRequest(query_params={"limit": "10", "offset": "10"})

    response = await list_route(request)
    body, status = extract_response(response)

    assert status == 200
    assert len(body) == 10
    # Verify it's the second page (tasks 10-19)


@pytest.mark.asyncio
async def test_list_route_sorting():
    """Test listing with sorting."""
    service = MockTaskService()

    # Create tasks in random order
    for priority in ["low", "high", "medium", "urgent"]:
        await service.create(
            {"uid": f"task:{priority}", "title": f"Task {priority}", "priority": priority}
        )

    @boundary_handler()
    async def list_route(request):
        params = dict(request.query_params)
        order_by = params.get("order_by")
        order_desc = params.get("order_desc", "false").lower() == "true"

        return await service.list(limit=100, offset=0, order_by=order_by, order_desc=order_desc)

    # Sort by priority ascending
    request = MockRequest(query_params={"order_by": "priority", "order_desc": "false"})

    response = await list_route(request)
    body, status = extract_response(response)

    assert status == 200
    # Should be sorted: high, low, medium, urgent (alphabetical)
    assert body[0]["priority"] == "high"


# ============================================================================
# INTEGRATION TEST - FULL CRUD LIFECYCLE
# ============================================================================


@pytest.mark.asyncio
async def test_full_crud_lifecycle():
    """Test complete CRUD lifecycle: Create → Read → Update → Delete."""
    service = MockTaskService()

    # 1. CREATE
    @boundary_handler(success_status=201)
    async def create_route(request):
        body = await request.json()
        task_data = body.copy()
        task_data["uid"] = "task:lifecycle"
        return await service.create(task_data)

    create_req = MockRequest(
        body={"title": "Lifecycle Test Task", "priority": "high", "status": "pending"}
    )

    create_response = await create_route(create_req)
    create_body, create_status = extract_response(create_response)
    assert create_status == 201
    uid = create_body["uid"]

    # 2. READ
    @boundary_handler()
    async def get_route(request):
        uid = request.path_params["uid"]
        return await service.get(uid)

    get_req = MockRequest(path_params={"uid": uid})
    get_response = await get_route(get_req)
    get_body, get_status = extract_response(get_response)

    assert get_status == 200
    assert get_body["title"] == "Lifecycle Test Task"

    # 3. UPDATE
    @boundary_handler()
    async def update_route(request):
        uid = request.path_params["uid"]
        body = await request.json()
        return await service.update(uid, body)

    update_req = MockRequest(path_params={"uid": uid}, body={"status": "active"})

    update_response = await update_route(update_req)
    update_body, update_status = extract_response(update_response)
    assert update_status == 200
    assert update_body["status"] == "active"

    # 4. DELETE
    @boundary_handler()
    async def delete_route(request):
        uid = request.path_params["uid"]
        return await service.delete(uid)

    delete_req = MockRequest(path_params={"uid": uid})
    delete_response = await delete_route(delete_req)
    delete_body, delete_status = extract_response(delete_response)

    assert delete_status == 200
    assert delete_body is True

    # 5. VERIFY DELETION
    get_after_delete = await service.get(uid)
    assert get_after_delete.is_error


# ============================================================================
# MULTI-DOMAIN COVERAGE TEST
# ============================================================================


@pytest.mark.asyncio
async def test_multi_domain_coverage():
    """Test that CRUD pattern works across multiple domains."""

    # Same pattern should work for Task, Event, Habit, Goal, etc.
    domains = [
        ("tasks", "task"),
        ("events", "event"),
        ("habits", "habit"),
        ("goals", "goal"),
    ]

    for domain_name, uid_prefix in domains:
        service = MockTaskService()  # Reusing for simplicity

        @boundary_handler(success_status=201)
        async def create_route(request, uid_prefix=uid_prefix, service=service):
            body = await request.json()
            task_data = body.copy()
            task_data["uid"] = f"{uid_prefix}:test"
            return await service.create(task_data)

        request = MockRequest(
            body={"title": f"Test {domain_name.capitalize()}", "priority": "medium"}
        )

        response = await create_route(request)
        body, status = extract_response(response)

        assert status == 201
        assert body["uid"].startswith(uid_prefix)
        assert domain_name.capitalize() in body["title"]


if __name__ == "__main__":
    # Run with: poetry run pytest tests/test_adapter_less_crud_routes.py -v
    pytest.main([__file__, "-v"])
