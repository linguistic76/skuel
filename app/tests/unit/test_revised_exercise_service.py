"""Tests for RevisedExerciseService's reads.

Verifies that list_for_student scopes results to the requesting teacher when
teacher_uid is provided. The service writes nothing: a revision is sent from
the review page (``TeacherReviewService.request_revision``).
"""

from unittest.mock import AsyncMock

import pytest

from core.services.revised_exercises.revised_exercise_service import RevisedExerciseService
from core.utils.result_simplified import Result


@pytest.fixture
def mock_backend():
    backend = AsyncMock()
    backend.list_for_student = AsyncMock()
    return backend


@pytest.fixture
def service(mock_backend):
    return RevisedExerciseService(backend=mock_backend)


class TestListForStudentScoping:
    """Test that list_for_student scopes by teacher when provided."""

    @pytest.mark.asyncio
    async def test_unscoped_query_without_teacher_uid(self, service, mock_backend):
        """Without teacher_uid, delegates to backend.list_for_student without teacher."""
        mock_backend.list_for_student.return_value = Result.ok([])

        await service.list_for_student("user_student")

        mock_backend.list_for_student.assert_called_once_with("user_student", None)

    @pytest.mark.asyncio
    async def test_scoped_query_with_teacher_uid(self, service, mock_backend):
        """With teacher_uid, delegates to backend.list_for_student with teacher scoping."""
        mock_backend.list_for_student.return_value = Result.ok([])

        await service.list_for_student("user_student", teacher_uid="user_teacher")

        mock_backend.list_for_student.assert_called_once_with("user_student", "user_teacher")


class TestTheReadSurfaceIsTheOnlySurface:
    """A revision is written only by the review page's door (ADR-091 N2). The
    service's ``BaseService`` base still carries generic writers, so every
    consumer holds the read-only protocol instead of the concrete class."""

    _WRITERS = frozenset(
        {
            "create",
            "update",
            "delete",
            "update_for_user",
            "delete_for_user",
            "add_relationship",
            "add_prerequisite",
        }
    )

    def test_the_protocol_names_no_writer(self) -> None:
        from core.ports.curriculum_protocols import RevisedExerciseOperations

        members = {name for name in vars(RevisedExerciseOperations) if not name.startswith("_")}
        assert members == {"get", "get_by_report_uid", "list_for_student", "get_revision_chain"}
        assert not members & self._WRITERS

    @pytest.mark.parametrize(
        "consumer",
        [
            "adapters.inbound.revised_exercises_api:create_revised_exercises_api_routes",
            "core.orchestrator.user_entry_orchestrator:UserEntryOrchestrator.__init__",
        ],
    )
    def test_every_consumer_takes_the_protocol(self, consumer: str) -> None:
        import importlib
        import inspect
        from annotationlib import Format

        module_name, qualname = consumer.split(":")
        target: object = importlib.import_module(module_name)
        for part in qualname.split("."):
            target = getattr(target, part)
        assert callable(target)
        signature = inspect.signature(target, annotation_format=Format.FORWARDREF)
        annotation = signature.parameters["revised_exercise_service"].annotation
        assert "RevisedExerciseOperations" in str(annotation), annotation
