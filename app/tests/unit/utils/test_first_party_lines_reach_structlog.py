"""The lines the boundaries, the Neo4j adapter, the planning base and ZPD log reach structlog.

Each test reads a module's line back through ``capture_with_call_sites``. A line written by a
stdlib ``logging.getLogger`` logger never reaches that capture, so a module's test fails while the
module logs through one. The fields a line carries (its traceback, its ``extra`` context) are read
from the captured dict, the dict the configured renderers print.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fasthtml.common import FT
from structlog.typing import EventDict

from adapters.inbound import boundary
from adapters.inbound.boundary import (
    boundary_handler,
    instrument_with_boundary_handler,
    ui_boundary_handler,
)
from adapters.persistence.neo4j_adapter import Neo4jSessionContext
from core.constants import ZPDWeights
from core.events.knowledge_substance_events import KnowledgeAppliedInTask
from core.models.type_hints import UserUID
from core.services.base_planning_service import BasePlanningService
from core.services.zpd.zpd_service import ZPDService
from core.utils.error_boundary import safe_event_handler
from core.utils.logging import get_logger
from core.utils.result_simplified import ErrorContext, Errors, Result
from tests.helpers.log_capture import capture_with_call_sites, lines_from
from tests.helpers.settings_stub import settings_stub

BOUNDARY = "adapters/inbound/boundary.py"
NEO4J_ADAPTER = "adapters/persistence/neo4j_adapter.py"
PLANNING = "core/services/base_planning_service.py"
ZPD = "core/services/zpd/zpd_service.py"
ERROR_BOUNDARY = "core/utils/error_boundary.py"
RESULT = "core/utils/result_simplified.py"
THIS_FILE = "tests/unit/utils/test_first_party_lines_reach_structlog.py"


def _last_traceback_line(line: EventDict) -> str:
    return str(line["exception"]).splitlines()[-1]


# --------------------------------------------------------------------------- the HTTP boundary


async def test_the_api_catch_all_logs_its_traceback() -> None:
    @boundary_handler()
    async def route() -> Result[None]:
        raise KeyError("forced")

    with capture_with_call_sites() as logs:
        response = await route()

    assert response.status_code == 500
    [line] = lines_from(logs, BOUNDARY)
    assert (line["log_level"], line["event"]) == ("error", "Unexpected error in route: 'forced'")
    assert _last_traceback_line(line) == "KeyError: 'forced'"


async def test_a_ui_route_failure_logs_its_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(boundary, "get_settings", settings_stub(debug=False))

    @ui_boundary_handler("Error loading widgets", fragment_id="widgets")
    async def fragment() -> FT:
        raise RuntimeError("no widgets")

    with capture_with_call_sites() as logs:
        await fragment()

    [line] = lines_from(logs, BOUNDARY)
    assert line["event"] == "Error loading widgets in fragment: no widgets"
    assert _last_traceback_line(line) == "RuntimeError: no widgets"


async def test_the_instrumented_boundary_logs_a_failed_request() -> None:
    @instrument_with_boundary_handler(None, "/api/widgets")
    async def route(request: Any) -> Result[None]:  # boundary: a stand-in request
        raise KeyError("forced")

    with capture_with_call_sites() as logs, pytest.raises(KeyError):
        await route(SimpleNamespace(method="GET"))

    [line] = lines_from(logs, BOUNDARY)
    assert line["event"] == "Request failed: GET /api/widgets"
    assert line["extra"] == {"endpoint": "/api/widgets", "method": "GET"}
    assert _last_traceback_line(line) == "KeyError: 'forced'"


# --------------------------------------------------------------------------- persistence


async def test_a_neo4j_session_closed_by_an_exception_is_logged() -> None:
    context = Neo4jSessionContext(driver=None)

    with capture_with_call_sites() as logs:
        await context.__aexit__(RuntimeError, RuntimeError("lost"), None)

    assert [line["event"] for line in lines_from(logs, NEO4J_ADAPTER)] == [
        "Neo4j session context exit with exception: lost"
    ]


class _FailingBackend:
    async def get_many(self, uids: list[str]) -> Result[list[Any]]:  # boundary: no entity type
        return Result.fail(Errors.database(operation="get_many", message="unreachable"))


class _WidgetPlanning(BasePlanningService[Any, Any]):  # boundary: a stand-in domain
    _domain_name = "Widgets"


async def test_a_planning_service_logs_a_failed_fetch() -> None:
    planning = _WidgetPlanning(backend=_FailingBackend())

    with capture_with_call_sites() as logs:
        assert await planning._get_entities_by_uids(["widget_1"]) == []

    [line] = lines_from(logs, PLANNING)
    assert line["log_level"] == "warning"
    assert line["event"].startswith("Failed to fetch Widgets by UIDs: ")


async def test_zpd_formats_its_positional_arguments() -> None:
    backend = AsyncMock()
    backend.get_ku_count = AsyncMock(return_value=1)
    service = ZPDService(backend=backend)

    with capture_with_call_sites() as logs:
        result = await service.assess_zone(UserUID("user_0123456789abcdef"))

    assert result.is_ok
    assert [line["event"] for line in lines_from(logs, ZPD)] == [
        f"ZPD skipped: curriculum graph has 1 KUs (minimum {ZPDWeights.MIN_KU_THRESHOLD} required)"
    ]


# --------------------------------------------------------------------------- the Result helpers


class _Handler:
    @safe_event_handler("knowledge.applied_in_task")
    async def handle(self, event: KnowledgeAppliedInTask) -> None:
        raise LookupError("no step")


async def test_an_event_handler_failure_logs_its_event_and_traceback() -> None:
    event = KnowledgeAppliedInTask(
        knowledge_uid="ku.ns.slug",
        task_uid="task_0123456789abcdef",
        user_uid=UserUID("user_0123456789abcdef"),
        task_title="Read the chapter",
    )

    with capture_with_call_sites() as logs:
        await _Handler().handle(event)

    [line] = lines_from(logs, ERROR_BOUNDARY)
    assert line["event"] == "Event handler failed: knowledge.applied_in_task"
    assert line["extra"] == {
        "event_name": "knowledge.applied_in_task",
        "error_type": "LookupError",
        "error_message": "no step",
        "handler": "handle",
        "event_data": {name: str(value) for name, value in vars(event).items()},
    }
    assert _last_traceback_line(line) == "LookupError: no step"


@pytest.mark.parametrize(
    ("error", "level"),
    [
        (Errors.validation("Bad week", field="week"), "info"),
        (Errors.integration("calendar", "Timed out"), "warning"),
        (Errors.database(operation="metrics", message="Unreachable"), "error"),
        (Errors.system("Layer exploded"), "critical"),
    ],
)
def test_log_if_error_logs_the_error_context_at_its_severity(
    error: ErrorContext, level: str
) -> None:
    with capture_with_call_sites() as logs:
        Result.fail(error).log_if_error("Habits metrics unavailable")

    [line] = lines_from(logs, RESULT)
    assert line["log_level"] == level
    assert line["event"] == f"Habits metrics unavailable: {error}"
    assert line["extra"] == {"error_context": error.to_dict()}
    assert "stack_trace" in line["extra"]["error_context"]


# --------------------------------------------------------------------------- the controls


def test_control_a_line_is_read_back_from_its_own_file_only() -> None:
    with capture_with_call_sites() as logs:
        get_logger("skuel.tests.log_capture").warning("from the test")

    assert [line["event"] for line in lines_from(logs, THIS_FILE)] == ["from the test"]
    assert lines_from(logs, BOUNDARY) == []


def test_control_a_module_path_matches_whole_path_parts() -> None:
    entries: list[EventDict] = [{"pathname": "/repo/app/core/utils/error_boundary.py"}]

    assert lines_from(entries, ERROR_BOUNDARY) == entries
    assert lines_from(entries, BOUNDARY) == []
    assert lines_from(entries, "boundary.py") == []
