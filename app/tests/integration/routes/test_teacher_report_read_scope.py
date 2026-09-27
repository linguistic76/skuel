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
``SUBMITTED_TO_GROUP`` (the review surfaces). Every actor is a TEACHER, so
``@require_teacher`` passes for all of them and the audience is the only
variable — a refusal below can never be the role gate in disguise.

Run against a real Neo4j container: the scoping resolves against persisted
``:OWNS`` / ``:MEMBER_OF`` / ``:SUBMITTED_TO_GROUP`` edges, which a mocked
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
STUDENT_WORK = "TRS_STUDENT_WORK_BODY_4b2e"
SNAPSHOT_TITLE = "Snapshot Exercise"
NEWER_UID = "ue_trs_newer_copy"
STUDENT_NAME = "Tess Student"

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
            MERGE (student:User {uid: $student}) SET student.display_name = $student_name
            MERGE (inT:User {uid: $in_teacher})
            MERGE (outT:User {uid: $out_teacher})
            MERGE (g:Group {uid: $group}) SET g.is_active = true
            MERGE (g2:Group {uid: $other_group}) SET g2.is_active = true
            MERGE (inT)-[:OWNS]->(g)
            MERGE (outT)-[:OWNS]->(g2)
            MERGE (student)-[:MEMBER_OF]->(g)
            CREATE (sub:Entity:UserEntry {
                uid: $sub, entity_type: 'user_entry', title: 'Student submission',
                content: $work, processed_content: '', status: 'submitted',
                pipeline: 'teacher_review', turn_in_exercise_uid: 'ex_trs_snapshot',
                turn_in_exercise_title: $snapshot_title, turn_in_revision: 3,
                created_at: datetime(), updated_at: datetime()
            })
            MERGE (student)-[:OWNS]->(sub)
            MERGE (sub)-[:SUBMITTED_TO_GROUP]->(g)
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
            work=STUDENT_WORK,
            snapshot_title=SNAPSHOT_TITLE,
            student_name=STUDENT_NAME,
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


# ============================================================================
# The review body — the student's work, its version, and history copies
# ============================================================================


@pytest.fixture
async def seeded_newer_copy(seeded, neo4j_driver) -> None:
    """A newer copy in the submission's lineage, visible to the same teacher."""
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MATCH (student:User {uid: $student}), (g:Group {uid: $group})
            CREATE (newer:Entity:UserEntry {
                uid: $newer, entity_type: 'user_entry', title: 'Newer copy',
                content: 'the newer words', status: 'submitted',
                pipeline: 'teacher_review', turn_in_exercise_uid: 'ex_trs_snapshot',
                turn_in_exercise_title: $snapshot_title, turn_in_revision: 4,
                created_at: datetime() + duration('PT5S'), updated_at: datetime()
            })
            MERGE (student)-[:OWNS]->(newer)
            MERGE (newer)-[:SUBMITTED_TO_GROUP]->(g)
            """,
            student=STUDENT,
            group=GROUP_UID,
            newer=NEWER_UID,
            snapshot_title=SNAPSHOT_TITLE,
        )


@pytest.mark.parametrize(("path", "surface"), [(CONTENT_PATH, "ui"), (PANEL_PATH, "api")])
class TestReviewShowsTheStudentsWork:
    """Both teacher surfaces show the work itself and its version — to the
    teacher it was submitted to, and to no one else."""

    def _handler(self, ui_handlers, api_handlers, path: str, surface: str) -> Any:
        return (ui_handlers if surface == "ui" else api_handlers)[path]

    async def test_the_teacher_reads_the_work_and_its_version(
        self, ui_handlers, api_handlers, seeded, path, surface
    ) -> None:
        handler = self._handler(ui_handlers, api_handlers, path, surface)
        markup = to_xml(await handler(_make_request(IN_TEACHER), uid=SUB_UID))
        assert STUDENT_WORK in markup
        assert f"by {STUDENT_NAME} · Exercise: {SNAPSHOT_TITLE} · v3" in markup
        assert 'name="instructions"' in markup

    async def test_another_classroom_reads_none_of_it(
        self, ui_handlers, api_handlers, seeded, path, surface
    ) -> None:
        handler = self._handler(ui_handlers, api_handlers, path, surface)
        markup = to_xml(await handler(_make_request(OUT_TEACHER), uid=SUB_UID))
        assert STUDENT_WORK not in markup
        assert SNAPSHOT_TITLE not in markup

    async def test_a_superseded_copy_is_history(
        self, ui_handlers, api_handlers, seeded_newer_copy, path, surface
    ) -> None:
        handler = self._handler(ui_handlers, api_handlers, path, surface)
        older = to_xml(await handler(_make_request(IN_TEACHER), uid=SUB_UID))
        assert STUDENT_WORK in older, "the history copy still shows its work"
        assert "this copy is history" in older
        assert f"/api/teaching/review/{SUB_UID}/revision" not in older
        assert f"/api/teaching/review/{SUB_UID}/report" not in older

        newer = to_xml(await handler(_make_request(IN_TEACHER), uid=NEWER_UID))
        assert f"/api/teaching/review/{NEWER_UID}/revision" in newer


# ============================================================================
# The writes hold the supersession rule themselves (decided by the write)
# ============================================================================


def _report_backend(neo4j_driver) -> EntryReportBackend:
    return EntryReportBackend(
        driver=neo4j_driver,
        label=NeoLabel.ENTRY_REPORT,
        entity_class=EntryReport,
        base_label=NeoLabel.ENTITY,
    )


def _report_params(submission_uid: str, report_uid: str, **extra: object) -> dict[str, object]:
    return {
        "report_uid": submission_uid,
        "report_entity_uid": report_uid,
        "author_uid": IN_TEACHER,
        "feedback": "write-guard feedback",
        "report_file_path": None,
        "title_prefix": "Feedback on",
        "entity_type": "entry_report",
        "submission_status": "completed",
        "completed_status": "completed",
        "processor_type": "human",
        "assessment_outcome": "approved",
        "allowed_from_statuses": ["submitted", "active"],
        "now": "2026-09-27T10:00:00",
        **extra,
    }


class TestTheWritesRefuseHistory:
    """Bypassing the service's read, each write statement still refuses a copy
    superseded for the reviewing teacher — the rule is decided by the write."""

    async def test_a_teacher_report_on_history_writes_nothing(
        self, seeded_newer_copy, neo4j_driver
    ) -> None:
        backend = _report_backend(neo4j_driver)
        refused = await backend.create_report_node(
            _report_params(SUB_UID, "er_trs_guard_old", reviewing_teacher_uid=IN_TEACHER)
        )
        assert refused.is_ok and refused.value == []

        landed = await backend.create_report_node(
            _report_params(NEWER_UID, "er_trs_guard_new", reviewing_teacher_uid=IN_TEACHER)
        )
        assert landed.is_ok and len(landed.value) == 1

    async def test_an_ai_report_is_not_gated(self, seeded_newer_copy, neo4j_driver) -> None:
        """No reviewing teacher, no supersession gate — the AI path is unchanged."""
        backend = _report_backend(neo4j_driver)
        result = await backend.create_report_node(
            _report_params(
                SUB_UID,
                "er_trs_guard_ai",
                author_uid=None,
                processor_type="llm",
                submission_status=None,
                allowed_from_statuses=None,
            )
        )
        assert result.is_ok and len(result.value) == 1

    async def test_a_revision_on_history_writes_nothing(
        self, seeded_newer_copy, neo4j_driver
    ) -> None:
        from core.models.enums import EntityType
        from core.models.exercises.revised_exercise import RevisedExercise

        backend = _report_backend(neo4j_driver)
        re_entity = RevisedExercise(
            uid="re_trs_guard",
            entity_type=EntityType.REVISED_EXERCISE,
            title="",
            user_uid=IN_TEACHER,
            original_exercise_uid="ex_trs_snapshot",
            report_uid="er_trs_guard_rev",
            instructions="revise",
        )
        result = await backend.create_report_and_revised_exercise(
            _report_params(
                SUB_UID,
                "er_trs_guard_rev",
                submission_status="revision_requested",
                assessment_outcome="needs_revision",
                reviewing_teacher_uid=IN_TEACHER,
                re_uid="re_trs_guard",
                original_exercise_uid="ex_trs_snapshot",
            ),
            re_entity,
        )
        assert result.is_ok and result.value == []

    async def test_approve_on_history_writes_nothing(self, seeded_newer_copy, neo4j_driver) -> None:
        backend = UserEntryBackend(driver=neo4j_driver)
        refused = await backend.approve_and_get_linked_kus(
            SUB_UID, "2026-09-27T10:00:00", "completed", ["submitted"], IN_TEACHER
        )
        assert refused.is_ok and refused.value == []
        landed = await backend.approve_and_get_linked_kus(
            NEWER_UID, "2026-09-27T10:00:00", "completed", ["submitted"], IN_TEACHER
        )
        assert landed.is_ok and len(landed.value) == 1
