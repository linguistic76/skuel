# mypy: disable-error-code="var-annotated"
"""
Test Error Boundary Pattern
============================

Tests the "Results internally, exceptions at boundaries" pattern.
Validates boundary_handler decorator, result_to_response conversion,
and safe_backend_operation decorator.
"""

import json

import pytest
from starlette.responses import JSONResponse

from adapters.inbound.boundary import (
    boundary_handler,
    result_to_exception,
    result_to_response,
    ui_boundary_handler,
)
from core.utils.error_boundary import (
    exception_to_result,
    safe_backend_operation,
)
from core.utils.result_simplified import ErrorCategory, Errors, Result


def extract_response(response: JSONResponse) -> tuple[dict, int]:
    """Helper to extract body and status from JSONResponse for testing."""
    body = json.loads(response.body)
    return body, response.status_code


# ============================================================================
# Test result_to_response (Core Boundary Conversion)
# ============================================================================


def test_result_to_response_success():
    """Test converting successful Result to HTTP response."""
    result = Result.ok({"name": "Test Task", "priority": "high"})

    response = result_to_response(result)
    body, status = extract_response(response)

    assert status == 200
    assert body == {"name": "Test Task", "priority": "high"}


def test_result_to_response_success_custom_status():
    """Test converting successful Result with custom status code."""
    result = Result.ok({"uid": "task-123", "title": "New Task"})

    response = result_to_response(result, success_status=201)
    body, status = extract_response(response)

    assert status == 201
    assert body["uid"] == "task-123"


def test_result_to_response_validation_error():
    """Test converting validation error to 400 response."""
    result = Result.fail(
        Errors.validation(message="Priority is required", field="priority", value=None)
    )

    response = result_to_response(result)
    body, status = extract_response(response)

    assert status == 400
    assert body["category"] == "validation"
    assert "priority" in body["message"].lower()


def test_result_to_response_not_found():
    """Test converting not found error to 404 response."""
    result = Result.fail(Errors.not_found(resource="Task", identifier="task-nonexistent"))

    response = result_to_response(result)
    body, status = extract_response(response)

    assert status == 404
    assert body["category"] == "not_found"
    # Client sees user_message, not developer message with identifier
    assert "task" in body["message"].lower()
    # No details, stack_trace, or source_location leaked to client
    assert "details" not in body
    assert "stack_trace" not in body
    assert "source_location" not in body


def test_result_to_response_business_error():
    """Test converting business rule violation to 422 response."""
    result = Result.fail(
        Errors.business(rule="unique_title", message="Task with this title already exists")
    )

    response = result_to_response(result)
    body, status = extract_response(response)

    assert status == 422
    assert body["category"] == "business"
    assert "already exists" in body["message"]


def test_result_to_response_database_error():
    """Test converting database error to 503 response."""
    result = Result.fail(Errors.database(operation="create_task", message="Connection timeout"))

    response = result_to_response(result)
    body, status = extract_response(response)

    assert status == 503
    assert body["category"] == "database"


def test_result_to_response_integration_error():
    """Test converting integration error to 502 response."""
    result = Result.fail(Errors.integration(service="OpenAI", message="API rate limit exceeded"))

    response = result_to_response(result)
    body, status = extract_response(response)

    assert status == 502
    assert body["category"] == "integration"


def test_result_to_response_system_error():
    """Test converting system error to 500 response."""
    result = Result.fail(Errors.system(message="Unexpected error occurred"))

    response = result_to_response(result)
    body, status = extract_response(response)

    assert status == 500
    assert body["category"] == "system"


# ============================================================================
# Test result_to_response domain-model serialization (regression)
# ============================================================================
# POST /api/{domain}/create 500'd after a successful create because the frozen
# domain dataclass went straight into Starlette's JSONResponse (json.dumps
# can't serialize dataclasses, enums, datetimes, or MappingProxyType). These
# tests use the REAL Task model — dict-only mocks are what hid the bug.


def test_result_to_response_frozen_dataclass_entity():
    """A created domain entity must serialize to JSON (the create-route path)."""
    from datetime import date

    from core.models.enums.entity_enums import EntityStatus, EntityType
    from core.models.task.task import Task

    task = Task(
        uid="task:abc123def456",
        title="Boundary serialization",
        user_uid="user_test",
        due_date=date(2026, 6, 15),
        knowledge_confidence_scores={"ku_x": 0.5},  # wrapped in MappingProxyType
    )
    result = Result.ok(task)

    response = result_to_response(result, success_status=201)
    body, status = extract_response(response)

    assert status == 201
    assert body["uid"] == "task:abc123def456"
    assert body["title"] == "Boundary serialization"
    assert body["entity_type"] == EntityType.TASK.value
    assert body["status"] == EntityStatus.DRAFT.value
    assert body["due_date"] == "2026-06-15"
    assert body["knowledge_confidence_scores"] == {"ku_x": 0.5}
    # datetime fields serialize as ISO strings
    assert isinstance(body["created_at"], str)


def test_result_to_response_list_of_entities():
    """A list of domain entities must serialize to JSON (the list-route path)."""
    from core.models.task.task import Task

    tasks = [
        Task(uid="task:aaa111", title="First", user_uid="user_test"),
        Task(uid="task:bbb222", title="Second", user_uid="user_test"),
    ]
    response = result_to_response(Result.ok(tasks))
    body, status = extract_response(response)

    assert status == 200
    assert [t["uid"] for t in body] == ["task:aaa111", "task:bbb222"]


@pytest.mark.asyncio
async def test_boundary_handler_unserializable_value_returns_500():
    """A genuinely unserializable value still hits the safety-net, not a crash."""

    class NotSerializable:
        pass

    @boundary_handler()
    async def handler():
        return Result.ok(NotSerializable())

    response = await handler()
    body, status = extract_response(response)

    assert status == 500
    assert body == {"error": "An internal error occurred"}


# ============================================================================
# Test result_to_exception (Alternative Boundary Conversion)
# ============================================================================


def test_result_to_exception_success():
    """Test unwrapping successful Result."""
    result = Result.ok({"task": "Complete tests"})

    value = result_to_exception(result)

    assert value == {"task": "Complete tests"}


def test_result_to_exception_error():
    """Test Result error raises RuntimeError."""
    result = Result.fail(Errors.not_found("Task", "task-123"))

    with pytest.raises(RuntimeError) as exc_info:
        result_to_exception(result)

    assert "not_found" in str(exc_info.value)
    assert "task-123" in str(exc_info.value).lower()


# ============================================================================
# Test @boundary_handler Decorator
# ============================================================================


@pytest.mark.asyncio
async def test_boundary_handler_success():
    """Test boundary_handler converts successful Result to response."""

    @boundary_handler()
    async def mock_route():
        return Result.ok({"message": "Success"})

    response = await mock_route()
    body, status = extract_response(response)

    assert status == 200
    assert body["message"] == "Success"


@pytest.mark.asyncio
async def test_boundary_handler_success_custom_status():
    """Test boundary_handler with custom success status."""

    @boundary_handler(success_status=201)
    async def mock_create_route():
        return Result.ok({"uid": "new-task"})

    response = await mock_create_route()
    body, status = extract_response(response)

    assert status == 201
    assert body["uid"] == "new-task"


@pytest.mark.asyncio
async def test_boundary_handler_validation_error():
    """Test boundary_handler converts validation error to 400."""

    @boundary_handler()
    async def mock_route():
        return Result.fail(
            Errors.validation(
                message="Invalid priority value", field="priority", value="super-duper-high"
            )
        )

    response = await mock_route()
    body, status = extract_response(response)

    assert status == 400
    assert body["category"] == "validation"
    assert "priority" in body["message"].lower()


@pytest.mark.asyncio
async def test_boundary_handler_not_found_error():
    """Test boundary_handler converts not found to 404."""

    @boundary_handler()
    async def mock_route():
        return Result.fail(Errors.not_found("Task", "task-missing"))

    response = await mock_route()
    body, status = extract_response(response)

    assert status == 404
    assert body["category"] == "not_found"


@pytest.mark.asyncio
async def test_boundary_handler_business_error():
    """Test boundary_handler converts business error to 422."""

    @boundary_handler()
    async def mock_route():
        return Result.fail(
            Errors.business(rule="deadline_constraint", message="Deadline must be in the future")
        )

    response = await mock_route()
    body, status = extract_response(response)

    assert status == 422
    assert body["category"] == "business"


@pytest.mark.asyncio
async def test_boundary_handler_database_error():
    """Test boundary_handler converts database error to 503."""

    @boundary_handler()
    async def mock_route():
        return Result.fail(Errors.database(operation="query_tasks", message="Connection lost"))

    response = await mock_route()
    body, status = extract_response(response)

    assert status == 503
    assert body["category"] == "database"


@pytest.mark.asyncio
async def test_boundary_handler_unexpected_exception():
    """Test boundary_handler catches unexpected exceptions."""

    @boundary_handler()
    async def mock_route_with_exception():
        raise ValueError("Something went wrong")

    response = await mock_route_with_exception()
    body, status = extract_response(response)

    assert status == 500
    assert "error" in body
    # Generic message — exception details never sent to clients
    assert body["error"] == "An internal error occurred"


@pytest.mark.asyncio
async def test_boundary_handler_non_result_passthrough():
    """Test boundary_handler passes through non-Result returns."""

    @boundary_handler()
    async def mock_route_direct_response():
        return {"direct": "response"}, 200

    result = await mock_route_direct_response()

    # Should pass through unchanged
    assert result == ({"direct": "response"}, 200)


# ============================================================================
# Test @safe_backend_operation Decorator
# ============================================================================


@pytest.mark.asyncio
async def test_safe_backend_operation_success():
    """Test safe_backend_operation wraps successful operation."""

    @safe_backend_operation("create_task")
    async def mock_backend_create(task_data):
        return {"uid": "task-123", **task_data}

    result = await mock_backend_create({"title": "Test Task"})

    assert result.is_ok
    assert result.value["uid"] == "task-123"
    assert result.value["title"] == "Test Task"


@pytest.mark.asyncio
async def test_safe_backend_operation_returns_result():
    """Test safe_backend_operation handles functions already returning Result."""

    @safe_backend_operation("get_task")
    async def mock_backend_get(uid: str):
        if uid == "task-exists":
            return Result.ok({"uid": uid, "title": "Existing Task"})
        return Result.fail(Errors.not_found("Task", uid))

    # Success case
    result = await mock_backend_get("task-exists")
    assert result.is_ok
    assert result.value["title"] == "Existing Task"

    # Error case
    result = await mock_backend_get("task-missing")
    assert result.is_error
    assert result.error.category == ErrorCategory.NOT_FOUND


@pytest.mark.asyncio
async def test_safe_backend_operation_catches_not_found():
    """Test safe_backend_operation converts Neo4j 'not found' to DATABASE."""
    from neo4j.exceptions import Neo4jError

    @safe_backend_operation("get_task")
    async def mock_backend_get(uid: str):
        raise Neo4jError(f"Task {uid} not found")

    result = await mock_backend_get(uid="task-missing")

    assert result.is_error
    assert result.error.category == ErrorCategory.DATABASE


@pytest.mark.asyncio
async def test_safe_backend_operation_catches_duplicate():
    """Test safe_backend_operation converts Neo4j duplicate to DATABASE."""
    from neo4j.exceptions import Neo4jError

    @safe_backend_operation("create_task")
    async def mock_backend_create(task_data):
        raise Neo4jError("Task with this title already exists")

    result = await mock_backend_create({"title": "Duplicate Task"})

    assert result.is_error
    assert result.error.category == ErrorCategory.DATABASE


@pytest.mark.asyncio
async def test_safe_backend_operation_catches_connection_error():
    """Test safe_backend_operation converts Neo4j errors as DATABASE category."""
    from neo4j.exceptions import ServiceUnavailable

    @safe_backend_operation("query_tasks")
    async def mock_backend_query():
        raise ServiceUnavailable("Connection timeout to database")

    result = await mock_backend_query()

    assert result.is_error
    assert result.error.category == ErrorCategory.DATABASE


@pytest.mark.asyncio
async def test_safe_backend_operation_catches_generic_exception_as_system():
    """Test safe_backend_operation converts non-Neo4j exceptions as SYSTEM category."""

    @safe_backend_operation("query_tasks")
    async def mock_backend_query():
        raise Exception("Connection timeout to database")

    result = await mock_backend_query()

    assert result.is_error
    assert result.error.category == ErrorCategory.SYSTEM


@pytest.mark.asyncio
async def test_safe_backend_operation_catches_generic_error():
    """Test safe_backend_operation converts generic exceptions."""

    @safe_backend_operation("process_task")
    async def mock_backend_process():
        raise ValueError("Unexpected processing error")

    result = await mock_backend_process()

    assert result.is_error
    # safe_backend_operation wraps all exceptions - may categorize as DATABASE or SYSTEM
    assert result.error.category in [ErrorCategory.SYSTEM, ErrorCategory.DATABASE]


@pytest.mark.asyncio
async def test_safe_backend_operation_with_async_function():
    """Test safe_backend_operation works with async functions.

    Note: @safe_backend_operation is designed for async backend operations.
    For sync functions, manually wrap the result in Result.ok/fail.
    """

    @safe_backend_operation("validate_task")
    async def mock_async_validate(task_data):
        if not task_data.get("title"):
            raise ValueError("Title is required")
        return task_data

    # Success case - async function properly decorated
    result = await mock_async_validate({"title": "Test Task"})
    assert result.is_ok
    assert result.value["title"] == "Test Task"

    # Error case - exceptions converted to Result.fail
    result = await mock_async_validate({})
    assert result.is_error
    assert result.error.category in [ErrorCategory.DATABASE, ErrorCategory.SYSTEM]


# ============================================================================
# Test @exception_to_result Decorator
# ============================================================================


@pytest.mark.asyncio
async def test_exception_to_result_success():
    """Test exception_to_result wraps successful operation."""

    @exception_to_result
    async def mock_service_method():
        return Result.ok({"data": "success"})

    result = await mock_service_method()

    assert result.is_ok
    assert result.value["data"] == "success"


@pytest.mark.asyncio
async def test_exception_to_result_wraps_non_result():
    """Test exception_to_result wraps non-Result returns."""

    @exception_to_result
    async def mock_service_method():
        return {"raw": "data"}

    result = await mock_service_method()

    assert result.is_ok
    assert result.value == {"raw": "data"}


# ============================================================================
# Integration Test - Full Flow
# ============================================================================


class MockTaskBackend:
    """Mock backend for integration testing."""

    def __init__(self):
        self.tasks = {}

    @safe_backend_operation("create_task")
    async def create(self, task_data: dict) -> Result[dict]:
        if task_data["uid"] in self.tasks:
            raise Exception("Task already exists")

        self.tasks[task_data["uid"]] = task_data
        return Result.ok(task_data)

    @safe_backend_operation("get_task")
    async def get(self, uid: str) -> Result[dict | None]:
        if uid not in self.tasks:
            return Result.ok(None)
        return Result.ok(self.tasks[uid])


class MockTaskService:
    """Mock service for integration testing."""

    def __init__(self, backend: MockTaskBackend):
        self.backend = backend

    async def create_task(self, task_data: dict) -> Result[dict]:
        """Create task - returns Result internally."""
        # Validation
        if not task_data.get("title"):
            return Result.fail(Errors.validation(message="Title is required", field="title"))

        # Check uniqueness
        existing = await self.backend.get(task_data["uid"])
        if existing.is_ok and existing.value:
            return Result.fail(
                Errors.business(
                    rule="unique_uid", message=f"Task {task_data['uid']} already exists"
                )
            )

        # Create task
        return await self.backend.create(task_data)

    async def get_task(self, uid: str) -> Result[dict]:
        """Get task - returns Result internally."""
        result = await self.backend.get(uid)

        if result.is_error:
            return Result.fail(result)

        if not result.value:
            return Result.fail(Errors.not_found("Task", uid))

        return Result.ok(result.value)


@pytest.mark.asyncio
async def test_full_flow_success():
    """Test complete flow: Route -> Service -> Backend -> Response."""
    backend = MockTaskBackend()
    service = MockTaskService(backend)

    @boundary_handler(success_status=201)
    async def create_task_route(task_data: dict):
        return await service.create_task(task_data)

    # Create task
    task_data = {"uid": "task-123", "title": "Test Task"}
    response = await create_task_route(task_data)
    body, status = extract_response(response)

    assert status == 201
    assert body["uid"] == "task-123"
    assert body["title"] == "Test Task"


@pytest.mark.asyncio
async def test_full_flow_validation_error():
    """Test complete flow with validation error."""
    backend = MockTaskBackend()
    service = MockTaskService(backend)

    @boundary_handler()
    async def create_task_route(task_data: dict):
        return await service.create_task(task_data)

    # Missing title
    response = await create_task_route({"uid": "task-123"})
    body, status = extract_response(response)

    assert status == 400
    assert body["category"] == "validation"
    assert "title" in body["message"].lower()


@pytest.mark.asyncio
async def test_full_flow_not_found():
    """Test complete flow with not found error."""
    backend = MockTaskBackend()
    service = MockTaskService(backend)

    @boundary_handler()
    async def get_task_route(uid: str):
        return await service.get_task(uid)

    # Get non-existent task
    response = await get_task_route("task-missing")
    body, status = extract_response(response)

    assert status == 404
    assert body["category"] == "not_found"


@pytest.mark.asyncio
async def test_full_flow_business_error():
    """Test complete flow with business rule violation."""
    backend = MockTaskBackend()
    service = MockTaskService(backend)

    @boundary_handler(success_status=201)
    async def create_task_route(task_data: dict):
        return await service.create_task(task_data)

    # Create task twice
    task_data = {"uid": "task-123", "title": "Test Task"}
    await create_task_route(task_data)

    response = await create_task_route(task_data)
    body, status = extract_response(response)

    assert status == 422
    assert body["category"] == "business"


@pytest.mark.asyncio
async def test_full_flow_round_trip():
    """Test complete round trip: Create -> Get -> Success."""
    backend = MockTaskBackend()
    service = MockTaskService(backend)

    @boundary_handler(success_status=201)
    async def create_task_route(task_data: dict):
        return await service.create_task(task_data)

    @boundary_handler()
    async def get_task_route(uid: str):
        return await service.get_task(uid)

    # Create task
    task_data = {"uid": "task-123", "title": "Test Task", "priority": "high"}
    create_response = await create_task_route(task_data)
    _create_body, create_status = extract_response(create_response)
    assert create_status == 201

    # Retrieve task
    get_response = await get_task_route("task-123")
    get_body, get_status = extract_response(get_response)
    assert get_status == 200
    assert get_body["title"] == "Test Task"
    assert get_body["priority"] == "high"


# ============================================================================
# Test Error Context Preservation
# ============================================================================


def test_error_context_client_safe_in_response():
    """Test that client response strips internal details (security hardening)."""
    error = Errors.validation(
        message="Invalid priority value", field="priority", value="super-high"
    )
    result = Result.fail(error)

    response = result_to_response(result)
    body, status = extract_response(response)

    assert status == 400
    assert body["category"] == "validation"
    # Client sees user_message (which for validation defaults to developer message)
    assert "invalid priority" in body["message"].lower()
    # Internal details stripped from client response
    assert "details" not in body
    assert "stack_trace" not in body
    assert "source_location" not in body


@pytest.mark.asyncio
async def test_boundary_handler_strips_internal_details():
    """Test boundary_handler strips internal details from client response (security hardening)."""

    @boundary_handler()
    async def mock_route():
        return Result.fail(Errors.not_found(resource="Task", identifier="task-123"))

    response = await mock_route()
    body, status = extract_response(response)

    assert status == 404
    assert body["category"] == "not_found"
    # Client gets user_message, not internal details
    assert "task" in body["message"].lower()
    assert "details" not in body
    assert "stack_trace" not in body
    assert "source_location" not in body


# ============================================================================
# Test @ui_boundary_handler Decorator (UI/fragment routes)
# ============================================================================


class _FakeApp:
    def __init__(self, debug: bool) -> None:
        self.debug = debug


class _FakeSettings:
    def __init__(self, debug: bool) -> None:
        self.application = _FakeApp(debug)


@pytest.fixture
def debug_off(monkeypatch):
    """Settings stub — get_settings() needs real env config, unavailable in unit tests."""
    from adapters.inbound import boundary

    def fake_settings() -> _FakeSettings:
        return _FakeSettings(debug=False)

    monkeypatch.setattr(boundary, "get_settings", fake_settings)


@pytest.mark.asyncio
async def test_ui_boundary_handler_passthrough_on_success():
    """Successful handler output is returned untouched."""

    @ui_boundary_handler("Error loading widgets")
    async def mock_route():
        return "the-fragment"

    assert await mock_route() == "the-fragment"


@pytest.mark.asyncio
async def test_ui_boundary_handler_renders_banner_on_exception(debug_off):
    """Unexpected exceptions render an error banner instead of propagating."""
    from fasthtml.common import to_xml

    @ui_boundary_handler("Error loading widgets")
    async def mock_route():
        raise ValueError("boom")

    html = to_xml(await mock_route())
    assert "Error loading widgets" in html
    assert 'role="alert"' in html


@pytest.mark.asyncio
async def test_ui_boundary_handler_wraps_fragment_id(debug_off):
    """fragment_id wraps the banner so HTMX swaps still target the right element."""
    from fasthtml.common import to_xml

    @ui_boundary_handler("Error loading feedback", fragment_id="feedback-list")
    async def mock_route():
        raise RuntimeError("boom")

    html = to_xml(await mock_route())
    assert 'id="feedback-list"' in html
    assert "Error loading feedback" in html


@pytest.mark.asyncio
async def test_ui_boundary_handler_reraises_http_exception():
    """Auth guards keep their semantics: HTTPException is never swallowed."""
    from starlette.exceptions import HTTPException

    @ui_boundary_handler("Error loading widgets")
    async def mock_route():
        raise HTTPException(status_code=401)

    with pytest.raises(HTTPException):
        await mock_route()


def test_ui_boundary_handler_sync_handler(debug_off):
    """Sync handlers (page shells) get the same boundary without becoming async."""

    @ui_boundary_handler("Error loading page")
    def mock_route():
        raise ValueError("boom")

    from fasthtml.common import to_xml

    html = to_xml(mock_route())
    assert "Error loading page" in html


def test_ui_boundary_handler_sync_reraises_http_exception():
    """Sync path re-raises HTTPException too."""
    from starlette.exceptions import HTTPException

    @ui_boundary_handler("Error loading page")
    def mock_route():
        raise HTTPException(status_code=401)

    with pytest.raises(HTTPException):
        mock_route()


def test_ui_boundary_handler_details_hidden_by_default(monkeypatch):
    """Technical details render only when application.debug is on."""
    from fasthtml.common import to_xml

    from adapters.inbound import boundary

    @ui_boundary_handler("Error loading widgets")
    def mock_route():
        raise ValueError("secret internals")

    def fake_settings_off() -> _FakeSettings:
        return _FakeSettings(debug=False)

    def fake_settings_on() -> _FakeSettings:
        return _FakeSettings(debug=True)

    monkeypatch.setattr(boundary, "get_settings", fake_settings_off)
    assert "secret internals" not in to_xml(mock_route())

    monkeypatch.setattr(boundary, "get_settings", fake_settings_on)
    assert "secret internals" in to_xml(mock_route())


if __name__ == "__main__":
    # Run with: uv run pytest tests/test_error_boundary.py -v
    pytest.main([__file__, "-v"])
