"""
UserEntry Assessment + Teacher Review Mixin
============================================

Assessment scoring + teacher-review queue and reporting.
Covers teacher authority verification, assessment queries,
review queue queries, report creation, and teacher dashboards.

Consolidated from the legacy ``_SubmissionAssessmentMixin`` into a single
standalone mixin (ADR-054).

Requires on concrete class:
    driver, label, logger, execute_query (from _SearchMixin)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.persistence.neo4j.query.cypher.learning_loop_fragments import (
    SUPERSEDED_COPY,
    asks_teacher,
    feedback_requests_subquery,
    in_classroom,
    superseded_copy_bindings,
)
from core.models.enums.entity_enums import REVIEWABLE_ENTRY_STATUSES, EntityStatus
from core.models.enums.pipeline import Pipeline
from core.models.relationship_names import RelationshipName
from core.models.type_hints import Neo4jProperties
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from core.models.enums.neo_labels import NeoLabel


# A feedback request awaiting review — the queue's default and its badge twin.
_PENDING_STATUSES = [status.value for status in REVIEWABLE_ENTRY_STATUSES]


class _UserEntryAssessmentMixin:
    """Assessment scoring + teacher-review workflow operations for ``UserEntry``.

    See ``UserEntryBackend`` in ``backends/user_entry_backend.py`` for the
    composed class.
    """

    if TYPE_CHECKING:
        driver: AsyncDriver
        label: NeoLabel

        async def execute_query(
            self, query: str, params: dict[str, Any] | None = None
        ) -> Result[list[dict[str, Any]]]: ...

    # ========================================================================
    # ASSESSMENT OPERATIONS
    # ========================================================================

    async def verify_teacher_authority(
        self, teacher_uid: str, subject_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Verify the student is in the teacher's classroom (``in_classroom``) — the student-level gate.

        Gates the student page, its knowledge tab and the students list. A
        feedback request filed with the teacher directly does not satisfy it
        (ADR-088 §9). One row when it holds, none otherwise.
        """
        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})
        MATCH (student:User {{uid: $subject_uid}})
        WHERE {in_classroom("teacher", "student")}
        RETURN true AS has_authority
        """
        return await self.execute_query(
            query, {"teacher_uid": teacher_uid, "subject_uid": subject_uid}
        )

    async def verify_teacher_exchange_authority(
        self, teacher_uid: str, subject_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Verify the teacher may open the student's exchange threads — classroom, or a direct request.

        The student is in the teacher's classroom (``in_classroom``), or filed
        a feedback request with the teacher directly (``SUBMITTED_TO_TEACHER``,
        ADR-088 §9). The thread itself is scoped to the entries that ask the
        teacher (``asks_teacher``), so this admits no entry of the student's
        the teacher was not asked about. One row when it holds, none otherwise.
        """
        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})
        MATCH (student:User {{uid: $subject_uid}})
        WHERE student.uid <> teacher.uid
          AND ({in_classroom("teacher", "student")}
               OR EXISTS {{
                   MATCH (student)-[:{RelationshipName.OWNS.value}]->(:Entity:UserEntry)
                         -[:{RelationshipName.SUBMITTED_TO_TEACHER.value}]->(teacher)
               }})
        RETURN true AS has_authority
        """
        return await self.execute_query(
            query, {"teacher_uid": teacher_uid, "subject_uid": subject_uid}
        )

    # ========================================================================
    # TEACHER REVIEW OPERATIONS
    # ========================================================================

    async def get_review_queue_by_groups(
        self,
        teacher_uid: str,
        status_filter: list[str] | None = None,
        student_uid: str | None = None,
    ) -> Result[list[Neo4jProperties]]:
        """Teacher's pending review queue — every feedback request sent to this teacher.

        One row per entry: an entry submitted to several of this teacher's
        groups (a ``teachers`` request files to every class the student is in
        without an exercise, or with one to each of its assigned classes the
        student is in) is one feedback request to this teacher, listed once.

        Returns the ``teacher_review`` entries that ask this teacher
        (``feedback_requests_subquery``: ``SUBMITTED_TO_GROUP`` one of the
        teacher's ACTIVE groups, or ``SUBMITTED_TO_TEACHER`` the teacher —
        ADR-088 §2, §9) — the same visibility the detail read
        (``get_entry_detail_for_teacher``) and the review writes
        (``verify_entry_asks_teacher``) enforce, so the queue never
        lists work the teacher cannot open or act on. Empty when nothing asks
        this teacher, so we do not leak the existence of unrelated students'
        submissions. A share
        (``SHARED_WITH_GROUP``) never queues: it lets members see the work
        and asks nobody for feedback (ADR-088 §2).

        ``student_uid`` narrows the queue to entries that student owns. This
        is THE needs-review rule for per-student surfaces too: the student
        page's Needs Review section reads through this same query, so the
        queue and the student page can never disagree on what awaits review
        (one collapse rule, two surfaces — feedback-loop UX arc C2).

        Superseded copies never queue: a pending entry with a newer sibling
        this teacher can see — in its exercise lineage (the turn-in snapshot)
        or its note lineage (frozen copies of one vault note) — is history,
        whatever the newer copy's status. The rule is ``SUPERSEDED_COPY``,
        shared with the dashboard badge and the students summary.
        ``exercise_uid`` / ``exercise_title`` read the live exercise, falling
        back to the snapshot once it is deleted.
        """
        statuses = status_filter or _PENDING_STATUSES
        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})
        // One row per entry, however many of this teacher's groups it asks.
        {feedback_requests_subquery("teacher", "entry")}
        WITH teacher, entry
        WHERE entry.pipeline = $pipeline
          AND entry.status IN $statuses
          AND ($student_uid IS NULL OR EXISTS {{
              MATCH (:User {{uid: $student_uid}})-[:{RelationshipName.OWNS.value}]->(entry)
          }})
        OPTIONAL MATCH (entry)-[r:{RelationshipName.FULFILLS_EXERCISE.value}]->(:Entity:Exercise)
        OPTIONAL MATCH (ex:Entity:Exercise {{uid: entry.turn_in_exercise_uid}})
        OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(entry)
        WITH teacher, entry, r, ex, student,
             entry.uid AS copy_uid,
             entry.turn_in_exercise_uid AS copy_lineage,
             entry.submitted_from_uid AS copy_note,
             coalesce(r.revision, 0) AS copy_revision,
             entry.created_at AS copy_created_at
        WHERE NOT {SUPERSEDED_COPY}
        OPTIONAL MATCH (report:Entity {{entity_type: 'entry_report'}})-[:{RelationshipName.REPORT_FOR.value}]->(entry)
        WITH entry, r, ex, student, count(DISTINCT report) AS feedback_count
        RETURN entry.uid AS entry_uid,
               entry.title AS title,
               entry.status AS status,
               entry.entity_type AS entity_type,
               entry.original_filename AS original_filename,
               entry.created_at AS submitted_at,
               student.uid AS student_uid,
               coalesce(student.display_name, student.title, student.uid) AS student_name,
               coalesce(ex.uid, entry.turn_in_exercise_uid) AS exercise_uid,
               coalesce(ex.title, entry.turn_in_exercise_title) AS exercise_title,
               ex.due_date AS due_date,
               coalesce(r.revision, entry.turn_in_revision) AS revision,
               feedback_count
        ORDER BY datetime(entry.created_at) DESC
        """
        return await self.execute_query(
            query,
            {
                "teacher_uid": teacher_uid,
                "pipeline": Pipeline.TEACHER_REVIEW.value,
                "statuses": statuses,
                "student_uid": student_uid,
            },
        )

    async def get_report_file_path(self, report_uid: str, teacher_uid: str) -> Result[str | None]:
        """Get the report_file_path for an EntryReport, gated by the teacher's access to the reviewed entry.

        Anchors on the report, walks ``REPORT_FOR`` to the reviewed submission
        and its owning student, and admits the teacher when the student is in
        the teacher's classroom (``in_classroom``, a student-level authority)
        or when the reviewed entry asks this teacher for feedback
        (``asks_teacher`` — so a teacher reached by a direct request,
        ADR-088 §9, downloads the reports on the entries sent to them, and no
        other). Returns ``None`` both when no such report exists and when the
        teacher has neither, so a denied download is indistinguishable from a
        missing one and cannot enumerate other classrooms' reports.
        """
        query = f"""
        MATCH (r:Entity {{uid: $report_uid, entity_type: 'entry_report'}})
              -[:{RelationshipName.REPORT_FOR.value}]->(sub:Entity)
        MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(sub)
        MATCH (teacher:User {{uid: $teacher_uid}})
        WHERE student.uid <> $teacher_uid
          AND ({in_classroom("teacher", "student")} OR {asks_teacher("sub", "teacher")})
        RETURN r.report_file_path as file_path
        LIMIT 1
        """
        result = await self.execute_query(
            query, {"report_uid": report_uid, "teacher_uid": teacher_uid}
        )
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok(None)
        return Result.ok(result.value[0].get("file_path"))

    async def approve_and_get_linked_kus(
        self,
        report_uid: str,
        now: str,
        status: str,
        allowed_from_statuses: list[str],
        teacher_uid: str,
    ) -> Result[list[Neo4jProperties]]:
        """Approve entry: set status and return linked KU UIDs for mastery.

        The status guard and the supersession guard (``SUPERSEDED_COPY`` for the
        approving teacher) are decided by this write: a copy with a newer version
        the teacher can see is never approved, whatever an earlier read saw.
        """
        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})
        MATCH (ku:Entity {{uid: $report_uid}})
        WHERE ku.status IN $allowed_from_statuses
        OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(ku)
        WITH teacher, student, ku, {superseded_copy_bindings("ku")}
        WHERE NOT {SUPERSEDED_COPY}
        SET ku.status = $status,
            ku.updated_at = datetime($now)
        WITH ku
        OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(ku)
        OPTIONAL MATCH (ku)-[:{RelationshipName.APPLIES_KNOWLEDGE.value}]->(curriculum:Entity:Ku)
        OPTIONAL MATCH (ku)-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(exercise:Entity)
        RETURN ku.uid as uid,
               ku.status as status,
               student.uid as student_uid,
               collect(curriculum.uid) as linked_ku_uids,
               exercise.mastery_impact as mastery_impact
        """
        return await self.execute_query(
            query,
            {
                "report_uid": report_uid,
                "now": now,
                "status": status,
                "allowed_from_statuses": allowed_from_statuses,
                "teacher_uid": teacher_uid,
                "pipeline": Pipeline.TEACHER_REVIEW.value,
            },
        )

    async def get_entries_for_exercise_review(
        self, exercise_uid: str, teacher_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Entries against an exercise that ask the requesting teacher for feedback.

        Scoped to teacher-review turn-ins that ask this teacher (``asks_teacher``:
        an active group the teacher owns, or the teacher directly) — a teacher
        supplying another teacher's exercise UID gets an empty result rather
        than that classroom's work, and a deactivated group's work no longer
        lists (ADR-088 §3).
        """
        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})
        MATCH (s:Entity:UserEntry)-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(e:Entity:Exercise {{uid: $exercise_uid}})
        WHERE s.pipeline = $pipeline
          AND {asks_teacher("s", "teacher")}
        OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(s)
        OPTIONAL MATCH (fb:Entity {{entity_type: 'entry_report'}})-[:{RelationshipName.REPORT_FOR.value}]->(s)
        WITH s, student, count(fb) AS feedback_count
        RETURN s.uid AS uid, s.title AS title,
               s.original_filename AS original_filename, s.status AS status,
               s.created_at AS created_at, student.uid AS student_uid,
               coalesce(student.display_name, student.title, student.uid) AS student_name, feedback_count,
               s.turn_in_revision AS revision
        ORDER BY datetime(s.created_at) DESC
        """
        return await self.execute_query(
            query,
            {
                "exercise_uid": exercise_uid,
                "teacher_uid": teacher_uid,
                "pipeline": Pipeline.TEACHER_REVIEW.value,
            },
        )

    async def get_students_summary(self, teacher_uid: str) -> Result[list[Neo4jProperties]]:
        """The teacher's classroom students whose work asks the teacher for feedback, with entry counts.

        A student is listed only from the teacher's classroom (``in_classroom``
        — the gate the student page opens by), so every row links to a page
        that opens: a learner who reached this teacher by a direct request
        alone (``SUBMITTED_TO_TEACHER``, ADR-088 §9) is not listed — the
        teacher works their requests from the review queue. A listed student's
        counts read every request to this teacher
        (``feedback_requests_subquery``), as the student page does.

        ``submission_count`` is every submission, ``reviewed_count`` the
        completed ones, and ``pending_count`` the rest that are not superseded
        — the queue's one supersede rule (``SUPERSEDED_COPY``), so a copy
        replaced by a newer one from the same exercise or the same vault note
        is history, not work awaiting review.
        """
        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})
        {feedback_requests_subquery("teacher", "ku")}
        MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(ku)
        WHERE student.uid <> $teacher_uid
          AND ku.pipeline = $pipeline
          AND {in_classroom("teacher", "student")}
        OPTIONAL MATCH (ku)-[r:{RelationshipName.FULFILLS_EXERCISE.value}]->(:Entity:Exercise)
        WITH teacher, student, ku,
             ku.uid AS copy_uid,
             ku.turn_in_exercise_uid AS copy_lineage,
             ku.submitted_from_uid AS copy_note,
             coalesce(max(r.revision), 0) AS copy_revision,
             ku.created_at AS copy_created_at
        WITH student, ku,
             ku.status = $completed AS reviewed,
             {SUPERSEDED_COPY} AS superseded
        WITH student,
             count(DISTINCT ku) AS submission_count,
             count(DISTINCT CASE WHEN reviewed THEN ku.uid END) AS reviewed_count,
             count(DISTINCT CASE WHEN NOT reviewed AND NOT superseded THEN ku.uid END) AS pending_count
        RETURN student.uid AS student_uid,
               coalesce(student.display_name, student.title, student.uid) AS student_name,
               submission_count,
               reviewed_count,
               pending_count
        ORDER BY pending_count DESC, submission_count DESC
        """
        return await self.execute_query(
            query,
            {
                "teacher_uid": teacher_uid,
                "pipeline": Pipeline.TEACHER_REVIEW.value,
                "completed": EntityStatus.COMPLETED.value,
            },
        )

    async def get_student_entries_for_teacher(
        self, teacher_uid: str, student_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """A student's teacher-review entries that ask the teacher for feedback.

        Gate: each entry must itself ask the requesting teacher (``asks_teacher``:
        an active group the teacher owns, or the teacher directly) — not merely
        prove that teacher and student share
        *some* group. This stops a teacher who shares one group with a multi-class
        student from reading entries the student only sent to another teacher's
        group. Empty result when nothing the student owns is submitted to this
        teacher's groups — indistinguishable from a genuinely empty history, so the
        existence of other classrooms' submissions is not leaked. (Mirrors the
        entry-level gate used by ``get_entry_detail_for_teacher``; ``EXISTS`` avoids
        inflating ``feedback_count`` when an entry is submitted to several of the
        teacher's groups.)
        """
        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})
        MATCH (student:User {{uid: $student_uid}})-[:{RelationshipName.OWNS.value}]->(ku:Entity:UserEntry)
        WHERE ku.pipeline = $pipeline
          AND {asks_teacher("ku", "teacher")}
        OPTIONAL MATCH (fb:Entity {{entity_type: 'entry_report'}})-[:{RelationshipName.REPORT_FOR.value}]->(ku)
        OPTIONAL MATCH (ex:Entity:Exercise {{uid: ku.turn_in_exercise_uid}})
        WITH ku, count(fb) AS feedback_count, ex
        RETURN ku.uid AS uid, ku.title AS title,
               ku.original_filename AS original_filename, ku.status AS status,
               ku.created_at AS created_at,
               feedback_count,
               coalesce(ex.uid, ku.turn_in_exercise_uid) AS exercise_uid,
               coalesce(ex.title, ku.turn_in_exercise_title) AS exercise_title,
               ku.turn_in_revision AS revision
        ORDER BY datetime(ku.created_at) DESC
        """
        return await self.execute_query(
            query,
            {
                "teacher_uid": teacher_uid,
                "student_uid": student_uid,
                "pipeline": Pipeline.TEACHER_REVIEW.value,
            },
        )

    async def update_entry_score(
        self, entry_uid: str, score: float
    ) -> Result[list[Neo4jProperties]]:
        """Update the score on an entry explicitly."""
        query = """
        MATCH (sub:Entity:UserEntry {uid: $entry_uid})
        SET sub.score = $score
        RETURN sub.uid as uid, sub.score as score
        """
        return await self.execute_query(query, {"entry_uid": entry_uid, "score": score})

    async def get_entry_detail_for_teacher(
        self, entry_uid: str, teacher_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Full entry detail for teacher review, gated by the entry's feedback request.

        Model B gate: the entry must ask this teacher (``asks_teacher``:
        ``SUBMITTED_TO_GROUP`` an active group the teacher owns, or
        ``SUBMITTED_TO_TEACHER`` the teacher). One row, or none — the gate is an existence test, so
        an entry submitted to several of the teacher's groups is still one
        detail. ``superseded`` applies the queue's collapse rule
        (``SUPERSEDED_COPY``): a copy with a newer sibling this teacher can see
        is history, which the review page offers no action on. Empty result
        when the entry asks none of the
        teacher's groups for feedback — service-layer callers (``get_submission_detail``)
        map empty to ``Errors.not_found`` (404) so a teacher outside the
        student's group cannot distinguish "entry does not exist" from
        "entry exists but belongs to another teacher's student".
        """
        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})
        MATCH (s:Entity:UserEntry {{uid: $entry_uid}})
        WHERE s.pipeline = $pipeline
          AND {asks_teacher("s", "teacher")}
        OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(s)
        OPTIONAL MATCH (ex:Entity:Exercise {{uid: s.turn_in_exercise_uid}})
        OPTIONAL MATCH (s)-[r:{RelationshipName.FULFILLS_EXERCISE.value}]->(:Entity:Exercise)
        WITH teacher, s, student, ex,
             s.uid AS copy_uid,
             s.turn_in_exercise_uid AS copy_lineage,
             s.submitted_from_uid AS copy_note,
             coalesce(r.revision, 0) AS copy_revision,
             s.created_at AS copy_created_at
        RETURN s.uid AS uid,
               s.title AS title,
               s.content AS content,
               s.processed_content AS processed_content,
               s.file_path AS file_path,
               s.original_filename AS original_filename,
               s.entity_type AS entity_type,
               s.status AS status,
               s.created_at AS created_at,
               student.uid AS student_uid,
               coalesce(student.display_name, student.title, student.uid) AS student_name,
               coalesce(ex.uid, s.turn_in_exercise_uid) AS exercise_uid,
               coalesce(ex.title, s.turn_in_exercise_title) AS exercise_title,
               s.turn_in_revision AS revision,
               ex.instructions AS exercise_instructions,
               {SUPERSEDED_COPY} AS superseded
        """
        return await self.execute_query(
            query,
            {
                "entry_uid": entry_uid,
                "teacher_uid": teacher_uid,
                "pipeline": Pipeline.TEACHER_REVIEW.value,
            },
        )

    async def get_dashboard_stats(self, teacher_uid: str) -> Result[list[Neo4jProperties]]:
        """At-a-glance stats for the teacher dashboard, scoped to the teacher's classroom.

        ``pending_count`` + ``total_students`` are Model-B-scoped: counted only
        across the entries that ask this teacher for feedback
        (``feedback_requests_subquery`` — an active owned group, or the teacher
        directly). ``total_students`` counts the requesters in the teacher's
        classroom only (``in_classroom``) — the students list's own rule.
        ``total_exercises`` counts the exercises the teacher teaches — named
        their teacher (``REVIEWED_BY``, ADR-091 S3) or owned — and
        ``total_groups`` the groups they own.

        ``pending_count`` is the review queue's badge twin and reads the
        queue's one supersede rule (``SUPERSEDED_COPY``): a pending copy
        superseded by a newer one from the same exercise or the same vault
        note is not pending work, so the badge and the queue length agree.
        """
        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})
        // Aggregating subquery: one row even when nothing asks this teacher.
        CALL (teacher) {{
            {feedback_requests_subquery("teacher", "sub")}
            WITH teacher, sub
            WHERE sub.pipeline = $pipeline
            OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(sub)
            WHERE student.uid <> $teacher_uid
            WITH teacher, sub, student, {superseded_copy_bindings("sub")}
            RETURN
              count(DISTINCT CASE
                  WHEN sub.status IN $pending_statuses AND NOT {SUPERSEDED_COPY}
                  THEN sub.uid END) AS pending_count,
              count(DISTINCT CASE WHEN {in_classroom("teacher", "student")}
                                  THEN student END) AS total_students
        }}
        RETURN
          pending_count,
          total_students,
          COUNT {{
              MATCH (ex:Entity:Exercise)-[:{RelationshipName.REVIEWED_BY.value}]->(teacher)
              RETURN ex
            UNION
              MATCH (teacher)-[:{RelationshipName.OWNS.value}]->(ex:Entity:Exercise)
              RETURN ex
          }} AS total_exercises,
          COUNT {{ (teacher)-[:{RelationshipName.OWNS.value}]->(:Group) }} AS total_groups
        """
        return await self.execute_query(
            query,
            {
                "teacher_uid": teacher_uid,
                "pipeline": Pipeline.TEACHER_REVIEW.value,
                "pending_statuses": _PENDING_STATUSES,
            },
        )

    async def verify_entry_asks_teacher(
        self, submission_uid: str, teacher_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Verify the entry asks this teacher for feedback — the review-write gate.

        The same authority the queue and the detail read carry (ADR-088 §2,
        §9): the entry itself must ask this teacher (``asks_teacher`` —
        ``SUBMITTED_TO_GROUP`` an active group the teacher ``OWNS``, or
        ``SUBMITTED_TO_TEACHER`` the teacher). Sharing a classroom with the *owner* is deliberately
        not enough — a multi-class student who sent the entry to one teacher's
        group has not put it in another teacher's hands, so that other teacher
        can neither open it nor write on it. A teacher never reviews their own
        entry. Returns empty when the entry asks none of the teacher's active
        groups and does not name the teacher — callers map empty to 404 (not
        found) so we do not leak the existence of unrelated students' submissions.
        """
        query = f"""
        MATCH (submission:Entity {{uid: $submission_uid}})
        MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(submission)
        MATCH (teacher:User {{uid: $teacher_uid}})
        WHERE student.uid <> $teacher_uid
          AND {asks_teacher("submission", "teacher")}
        RETURN true AS has_access LIMIT 1
        """
        return await self.execute_query(
            query, {"submission_uid": submission_uid, "teacher_uid": teacher_uid}
        )
