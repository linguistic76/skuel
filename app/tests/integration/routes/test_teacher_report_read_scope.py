"""Owner-scoping for the teacher-gated *reads* of student feedback.

Three role-gated surfaces read a student's learning-loop feedback by a
caller-supplied UID and were scoped by ``@require_teacher`` alone — the role
gate answers "may you review at all", never "whose feedback". Their paired
*writes* are all narrower: ``submit_report`` / ``request_revision`` /
``approve_report`` run ``verify_teacher_has_group_access`` first, so only a
teacher sharing an active group with the student may author feedback. A read
audience wider than that write audience is the #887 blind spot: any TEACHER
could read one classroom's private feedback from another.

The three surfaces, and what each leaked:

- ``GET /api/reports/{report_uid}/download`` — handed back the raw ``.md``
  feedback file for *any* report UID (``download_report_file``).
- ``GET /teaching/review/{uid}/content`` — its scoped submission-detail read
  failed shut for an out-of-group teacher, but the feedback-history read on the
  same fragment ran unconditionally and rendered the report bodies anyway.
- ``GET /api/teaching/review/{uid}/panel`` — same unconditional history read
  behind a scoped detail read.

The audience pinned here is the one the *write* already uses: a teacher who
owns an active group the student belongs to (download) / that the submission is
``SHARED_WITH_GROUP`` (the review surfaces). Every actor is a TEACHER, so
``@require_teacher`` passes for all of them and the audience is the only
variable — a refusal below can never be the role gate in disguise.

Run against a real Neo4j container: the scoping resolves against persisted
``:OWNS`` / ``:MEMBER_OF`` / ``:SHARED_WITH_GROUP`` edges, which a mocked
backend would only assert were queried, not that they gate. Refusals are
404-equivalent (OWNERSHIP_VERIFICATION.md): the download yields a real 404, the
HTMX fragments yield the byte-identical markup a nonexistent UID yields, so a
denied read cannot be told from a missing one.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fasthtml.common import to_xml
from starlette.responses import FileResponse

from adapters.inbound.teaching_api import create_teaching_api_routes
from adapters.inbound.teaching_ui import create_teaching_ui_routes
from adapters.persistence.neo4j.backends.exercise_backends import EntryReportBackend
from adapters.persistence.neo4j.backends.user_entry_backend import UserEntryBackend
from core.models.enums import UserRole
from core.models.enums.neo_labels import NeoLabel
from core.models.report.entry_report import EntryReport
from core.models.user.user import User
from core.orchestrator.teacher_orchestrator import TeacherOrchestrator
from core.services.report.entry_report_service import EntryReportService
from core.services.report.teacher_review_service import TeacherReviewService
from core.utils.result_simplified import Errors, Result

STUDENT = "user_trs_student"
IN_TEACHER = "user_trs_in_teacher"  # owns the group the submission is shared with
OUT_TEACHER = "user_trs_out_teacher"  # a TEACHER, but of a different classroom
GROUP_UID = "group_trs_in"
OTHER_GROUP_UID = "group_trs_out"

SUB_UID = "ue_trs_submission"
REPORT_UID = "er_trs_report"
SECRET_FEEDBACK = "TRS_SECRET_FEEDBACK_BODY_9f1c"

CONTENT_PATH = "/teaching/review/{uid}/content"
PANEL_PATH = "/api/teaching/review/{uid}/panel"
DOWNLOAD_PATH = "/api/reports/{report_uid}/download"

ROLES = {
    STUDENT: UserRole.MEMBER,
    IN_TEACHER: UserRole.TEACHER,
    OUT_TEACHER: UserRole.TEACHER,
}


def _user_service() -> Any:
    """Real ``User`` records so ``@require_teacher`` runs its hierarchy check."""

    async def get_user(user_uid: str) -> Result[User]:
        role = ROLES.get(user_uid)
        if role is None:
            return Result.fail(Errors.not_found(resource="User", identifier=user_uid))
        return Result.ok(User(uid=user_uid, title=user_uid, role=role))

    return SimpleNamespace(get_user=get_user)


def _make_request(user_uid: str) -> Any:
    """Minimal session-backed request stub for the auth guards."""
    return SimpleNamespace(
        method="GET",
        session={"user_uid": user_uid},
        url=SimpleNamespace(path="/"),
        query_params={},
        cookies={},
        headers={},
    )


def _collector() -> tuple[Any, dict[str, Any]]:
    """A stand-in app/rt pair that records path → registered handler."""
    registered: dict[str, Any] = {}

    def rt(path: str, *_a: Any, **_kw: Any) -> Any:
        def decorator(fn: Any) -> Any:
            registered[path] = fn
            return fn

        return decorator

    app = SimpleNamespace(get=rt, post=rt, route=rt)
    return (app, rt), registered


@pytest.fixture
def review_service(neo4j_driver) -> TeacherReviewService:
    """Real service over a real user_entry backend.

    Only ``user_entry_backend`` is exercised by the reads under test
    (``get_submission_detail``, ``get_report_file_path``); the other
    collaborators are never touched, so ``None`` is honest here.
    """
    user_entry_backend = UserEntryBackend(driver=neo4j_driver)
    return TeacherReviewService(
        user_entry_backend=user_entry_backend,
        report_backend=None,  # type: ignore[arg-type]
        exercise_backend=None,  # type: ignore[arg-type]
        group_backend=None,  # type: ignore[arg-type]
        ku_interaction_service=None,  # type: ignore[arg-type]
        report_mastery_service=None,  # type: ignore[arg-type]
        event_bus=None,  # type: ignore[arg-type]
    )


@pytest.fixture
def entry_report_service(neo4j_driver) -> EntryReportService:
    backend = EntryReportBackend(
        driver=neo4j_driver,
        label=NeoLabel.ENTRY_REPORT,
        entity_class=EntryReport,
        base_label=NeoLabel.ENTITY,
    )
    return EntryReportService(llm_caller=None, backend=backend)


@pytest.fixture
def ui_handlers(review_service, entry_report_service) -> dict[str, Any]:
    (app, rt), registered = _collector()
    orchestrator = TeacherOrchestrator(review_service)
    create_teaching_ui_routes(
        app,
        rt,
        orchestrator,
        user_service=_user_service(),
        entry_report_service=entry_report_service,
    )
    return registered


@pytest.fixture
def api_handlers(review_service, entry_report_service) -> dict[str, Any]:
    (app, rt), registered = _collector()
    create_teaching_api_routes(
        app,
        rt,
        review_service,
        user_service=_user_service(),
        exercises_service=SimpleNamespace(),
        entry_report_service=entry_report_service,
    )
    return registered


@pytest.fixture
def report_file() -> Any:
    """A real .md file on disk so the in-group download returns a FileResponse."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as fh:
        fh.write(f"# Feedback\n\n{SECRET_FEEDBACK}\n")
        path = fh.name
    yield path
    Path(path).unlink(missing_ok=True)


@pytest.fixture
async def seeded(clean_neo4j, neo4j_driver, report_file) -> str:
    """Seed the two-classroom graph and return the report's file path.

    In-group teacher owns the active group the student belongs to and the
    submission is shared with; out-of-group teacher owns a different group.
    """
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MERGE (student:User {uid: $student})
            MERGE (inT:User {uid: $in_teacher})
            MERGE (outT:User {uid: $out_teacher})
            MERGE (g:Group {uid: $group}) SET g.is_active = true
            MERGE (g2:Group {uid: $other_group}) SET g2.is_active = true
            MERGE (inT)-[:OWNS]->(g)
            MERGE (outT)-[:OWNS]->(g2)
            MERGE (student)-[:MEMBER_OF]->(g)
            CREATE (sub:Entity:UserEntry {
                uid: $sub, entity_type: 'user_entry', title: 'Student submission',
                content: 'submission body', processed_content: '', status: 'submitted',
                pipeline: 'teacher_review', created_at: datetime(), updated_at: datetime()
            })
            MERGE (student)-[:OWNS]->(sub)
            MERGE (sub)-[:SHARED_WITH_GROUP]->(g)
            CREATE (rep:Entity:EntryReport {
                uid: $report, entity_type: 'entry_report', title: 'Teacher feedback',
                description: '', status: 'completed', processed_content: $secret,
                report_file_path: $file_path, processor_type: 'human',
                user_uid: $student, created_at: datetime(), updated_at: datetime()
            })
            MERGE (rep)-[:REPORT_FOR]->(sub)
            MERGE (student)-[:OWNS]->(rep)
            """,
            student=STUDENT,
            in_teacher=IN_TEACHER,
            out_teacher=OUT_TEACHER,
            group=GROUP_UID,
            other_group=OTHER_GROUP_UID,
            sub=SUB_UID,
            report=REPORT_UID,
            secret=SECRET_FEEDBACK,
            file_path=report_file,
        )
    return report_file


# ============================================================================
# Fix A — GET /api/reports/{report_uid}/download
# ============================================================================


class TestReportDownloadScope:
    """The report .md download is owner-scoped, not merely teacher-gated."""

    async def test_in_group_teacher_downloads_the_file(self, api_handlers, seeded) -> None:
        handler = api_handlers[DOWNLOAD_PATH]
        response = await handler(_make_request(IN_TEACHER), report_uid=REPORT_UID)
        assert isinstance(response, FileResponse), (
            "the authoring classroom's teacher must still get the feedback file"
        )
        assert str(response.path) == seeded

    async def test_out_of_group_teacher_gets_404(self, api_handlers, seeded) -> None:
        handler = api_handlers[DOWNLOAD_PATH]
        response = await handler(_make_request(OUT_TEACHER), report_uid=REPORT_UID)
        # A denied read must not reach the client as a 200 success (it may be
        # cached); it is a real 404, identical to a nonexistent report.
        assert not isinstance(response, FileResponse)
        assert getattr(response, "status_code", None) == 404

    async def test_missing_report_is_404_too(self, api_handlers, seeded) -> None:
        """The refusal is indistinguishable from a genuinely missing report."""
        handler = api_handlers[DOWNLOAD_PATH]
        response = await handler(_make_request(IN_TEACHER), report_uid="er_does_not_exist")
        assert getattr(response, "status_code", None) == 404


# ============================================================================
# Fix B — GET /teaching/review/{uid}/content  (HTMX fragment)
# ============================================================================


class TestReviewFragmentScope:
    """The review-detail fragment reads feedback history only after the scoped
    submission-detail read establishes access."""

    async def test_in_group_teacher_sees_feedback(self, ui_handlers, seeded) -> None:
        handler = ui_handlers[CONTENT_PATH]
        markup = to_xml(await handler(_make_request(IN_TEACHER), uid=SUB_UID))
        assert SECRET_FEEDBACK in markup, (
            "the reviewing teacher must still see the submission's feedback history"
        )

    async def test_out_of_group_teacher_sees_nothing(self, ui_handlers, seeded) -> None:
        handler = ui_handlers[CONTENT_PATH]
        markup = to_xml(await handler(_make_request(OUT_TEACHER), uid=SUB_UID))
        assert SECRET_FEEDBACK not in markup, (
            "a teacher outside the classroom must not read the feedback history"
        )
        assert "Submission not found" in markup


# ============================================================================
# Fix C — GET /api/teaching/review/{uid}/panel  (HTMX fragment)
# ============================================================================


class TestReviewPanelScope:
    """The inline review panel gates its feedback-history read the same way."""

    async def test_in_group_teacher_sees_feedback(self, api_handlers, seeded) -> None:
        handler = api_handlers[PANEL_PATH]
        markup = to_xml(await handler(_make_request(IN_TEACHER), uid=SUB_UID))
        assert SECRET_FEEDBACK in markup

    async def test_out_of_group_teacher_sees_nothing(self, api_handlers, seeded) -> None:
        handler = api_handlers[PANEL_PATH]
        markup = to_xml(await handler(_make_request(OUT_TEACHER), uid=SUB_UID))
        assert SECRET_FEEDBACK not in markup
