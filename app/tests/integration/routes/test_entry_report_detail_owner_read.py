"""``GET /entry-reports/detail`` is an owner read (ADR-088 §3).

An EntryReport belongs to the student it was written for (``user_uid``); the
teacher who wrote it is its ``author_uid`` and reads their own artifacts on
the teaching surfaces. Ownership is the only grant — a share edge and the
``visibility`` property admit nobody — so:

- the owner gets the page (a plain FT, status 200);
- the authoring teacher gets the rendered "Report not found" page at a real
  404, with a ``SHARES_WITH`` edge and ``visibility: 'shared'`` on the node
  (the shape the report writer produces), so the test proves neither is a
  grant;
- a stranger gets the same 404, and neither body carries the feedback text.

Run against a real Neo4j container: the owner predicate is a Cypher clause
composed by ``build_search_visibility_clause`` (ADR-085), so a mocked backend
would only prove that the route calls a method. The positive control (the
owner) guards against a predicate that refuses everyone.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from types import SimpleNamespace

import pytest
from fasthtml.common import FT, FtResponse, to_xml

from adapters.inbound.entry_reports_ui import create_entry_reports_ui_routes
from adapters.inbound.fasthtml_types import RouteDecorator
from adapters.persistence.neo4j.backends.exercise_backends import (
    EntryReportBackend,
    RevisedExerciseBackend,
)
from core.models.enums.neo_labels import NeoLabel
from core.models.exercises.revised_exercise import RevisedExercise
from core.models.report.entry_report import EntryReport
from core.orchestrator.user_entry_orchestrator import UserEntryOrchestrator
from core.services.report.entry_report_service import EntryReportService
from core.services.revised_exercises.revised_exercise_service import RevisedExerciseService

STUDENT = "user_erd_student"
TEACHER = "user_erd_teacher"
STRANGER = "user_erd_stranger"
ENTRY = "ue_erd_turn_in"
REPORT = "er_erd_feedback"
FEEDBACK_TEXT = "Your thesis is clear; tighten the second paragraph."

DETAIL_PATH = "/entry-reports/detail"

Handler = Callable[..., Awaitable[FT | FtResponse]]
"""The registered page handler: a served page (FT) or a rendered refusal."""


def _make_request(user_uid: str, uid: str) -> SimpleNamespace:
    """Session-backed request stub for ``require_authenticated_user`` + ``query_params``."""
    return SimpleNamespace(
        method="GET",
        session={"user_uid": user_uid},
        url=SimpleNamespace(path=DETAIL_PATH),
        query_params={"uid": uid},
        headers={},
        cookies={},
    )


def _collector() -> tuple[tuple[SimpleNamespace, RouteDecorator], dict[str, Handler]]:
    """A stand-in app/rt pair that records path → handler."""
    registered: dict[str, Handler] = {}

    def rt(path: str, methods: list[str] | None = None) -> Callable[[Handler], Handler]:
        def decorator(fn: Handler) -> Handler:
            registered[path] = fn
            return fn

        return decorator

    app = SimpleNamespace(get=rt, post=rt, route=rt)
    return (app, rt), registered


@pytest.fixture
def orchestrator(neo4j_driver) -> UserEntryOrchestrator:
    """The real report read over the real backends — only Neo4j is a container."""
    report_backend = EntryReportBackend(
        driver=neo4j_driver,
        label=NeoLabel.ENTRY_REPORT,
        entity_class=EntryReport,
        base_label=NeoLabel.ENTITY,
    )
    revised_backend = RevisedExerciseBackend(
        driver=neo4j_driver,
        label=NeoLabel.REVISED_EXERCISE,
        entity_class=RevisedExercise,
        base_label=NeoLabel.ENTITY,
    )
    return UserEntryOrchestrator(
        user_entry_service=None,  # type: ignore[arg-type]
        exercises_service=None,  # type: ignore[arg-type]
        teacher_review_service=None,  # type: ignore[arg-type]
        user_service=None,  # type: ignore[arg-type]
        activity_report_service=None,  # type: ignore[arg-type]
        revised_exercise_service=RevisedExerciseService(backend=revised_backend),
        entry_report_service=EntryReportService(llm_caller=None, backend=report_backend),
        report_relationship_service=None,  # type: ignore[arg-type]
    )


@pytest.fixture
def handler(orchestrator: UserEntryOrchestrator) -> Handler:
    (app, rt), registered = _collector()
    create_entry_reports_ui_routes(app, rt, orchestrator)
    return registered[DETAIL_PATH]


@pytest.fixture
async def seeded(clean_neo4j, neo4j_driver) -> None:
    """One teacher report on the student's turn-in, in the shape the writer produces.

    ``create_report_node`` stamps ``user_uid`` = the student, ``author_uid`` =
    the teacher, ``visibility: 'shared'``, an ``OWNS`` edge from the student,
    ``REPORT_FOR`` to the entry, and the student's own ``SHARES_WITH`` on the
    report. The teacher holds NO edge to it — as in production.
    """
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MERGE (s:User {uid: $student})
            MERGE (t:User {uid: $teacher})
            MERGE (x:User {uid: $stranger})
            CREATE (e:Entity:UserEntry {
                uid: $entry, entity_type: 'user_entry', title: 'Turn-in',
                status: 'completed', pipeline: 'teacher_review',
                created_at: '2026-09-01T10:00:00.000000'
            })
            CREATE (r:Entity:EntryReport {
                uid: $report, entity_type: 'entry_report', title: 'Feedback on Turn-in',
                user_uid: $student, author_uid: $teacher, status: 'completed',
                visibility: 'shared', processor_type: 'human',
                assessment_outcome: 'approved', processed_content: $feedback,
                created_at: datetime('2026-09-01T12:00:00Z'),
                updated_at: datetime('2026-09-01T12:00:00Z')
            })
            MERGE (s)-[:OWNS]->(e)
            MERGE (s)-[:OWNS]->(r)
            MERGE (r)-[:REPORT_FOR]->(e)
            MERGE (s)-[:SHARES_WITH {shared_at: datetime(), role: 'student'}]->(r)
            """,
            student=STUDENT,
            teacher=TEACHER,
            stranger=STRANGER,
            entry=ENTRY,
            report=REPORT,
            feedback=FEEDBACK_TEXT,
        )


async def _open(handler: Handler, user_uid: str, uid: str = REPORT) -> tuple[int, str]:
    """Render the detail page as the given user → (status, markup)."""
    response = await handler(request=_make_request(user_uid, uid))
    if isinstance(response, FtResponse):
        return response.status_code, to_xml(response.content)
    return 200, to_xml(response)


@pytest.mark.integration
class TestEntryReportDetailOwnerRead:
    async def test_owner_opens_the_report(self, handler, seeded) -> None:
        status, html = await _open(handler, STUDENT)
        assert status == 200
        assert FEEDBACK_TEXT in html
        assert "Report not found" not in html

    async def test_authoring_teacher_gets_404(self, handler, seeded) -> None:
        """A share edge + ``visibility: 'shared'`` grant nothing: the teacher who wrote
        the report is not its owner and gets the rendered not-found at a real 404."""
        status, html = await _open(handler, TEACHER)
        assert status == 404
        assert "Report not found" in html
        assert FEEDBACK_TEXT not in html

    async def test_stranger_gets_404(self, handler, seeded) -> None:
        status, html = await _open(handler, STRANGER)
        assert status == 404
        assert FEEDBACK_TEXT not in html

    async def test_missing_uid_is_the_same_404(self, handler, seeded) -> None:
        """Absent and not-owned are one outcome — no existence leak."""
        status, html = await _open(handler, STUDENT, uid="er_erd_does_not_exist")
        assert status == 404
        assert "Report not found" in html
