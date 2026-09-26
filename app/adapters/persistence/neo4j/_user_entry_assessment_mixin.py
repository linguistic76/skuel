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

from core.models.enums.entity_enums import EntityStatus
from core.models.enums.pipeline import Pipeline
from core.models.relationship_names import RelationshipName
from core.models.type_hints import Neo4jProperties
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from core.models.enums.neo_labels import NeoLabel


# A feedback request awaiting review — the queue's default and its badge twin.
_PENDING_STATUSES = [EntityStatus.SUBMITTED.value, EntityStatus.ACTIVE.value]

_OWNS = RelationshipName.OWNS.value
_SUBMITTED_TO_GROUP = RelationshipName.SUBMITTED_TO_GROUP.value
_FULFILLS_EXERCISE = RelationshipName.FULFILLS_EXERCISE.value

# THE supersede rule for pending feedback requests — one predicate, read by the
# review queue, its dashboard badge twin and the students summary, so the three
# can never disagree on what awaits review.
#
# A copy is superseded by a newer sibling the SAME teacher can see (a
# ``teacher_review`` entry of the same student, submitted to one of this
# teacher's ACTIVE owned groups), in either of two lineages:
#
#   * the exercise lineage — the same turn-in snapshot ``turn_in_exercise_uid``
#     (the key that outlives the exercise, Submit & Share arc R12), newer by the
#     ``FULFILLS_EXERCISE`` edge revision where the edge still exists, else by
#     ``created_at``;
#   * the note lineage — frozen copies filed from the same vault note
#     (``submitted_from_uid``, R9), newer by ``created_at``.
#
# Whatever the newer copy's status (a reviewed rev 2 retires a pending rev 1).
# Siblings the teacher cannot see never supersede: a PRIVATE ``llm_summary``
# entry, a copy sent only to another teacher's group, one locked in a group this
# teacher deactivated. An entry in neither lineage always passes through.
#
# The caller binds, in a WITH before the predicate: ``teacher``, ``student``
# (the entry's owner), ``copy_uid``, ``copy_lineage`` (the entry's
# ``turn_in_exercise_uid``), ``copy_note`` (its ``submitted_from_uid``),
# ``copy_revision`` (its edge revision, 0 without one) and ``copy_created_at``.
_SUPERSEDED_COPY = f"""EXISTS {{
    MATCH (student)-[:{_OWNS}]->(newer:Entity:UserEntry)
    WHERE newer.uid <> copy_uid
      AND newer.pipeline = $pipeline
      AND (newer)-[:{_SUBMITTED_TO_GROUP}]->(:Group {{is_active: true}})<-[:{_OWNS}]-(teacher)
      AND ((copy_lineage IS NOT NULL
            AND newer.turn_in_exercise_uid = copy_lineage
            AND (coalesce(head([(newer)-[nr:{_FULFILLS_EXERCISE}]->(:Entity:Exercise) | nr.revision]), 0)
                   > copy_revision
                 OR (coalesce(head([(newer)-[nr:{_FULFILLS_EXERCISE}]->(:Entity:Exercise) | nr.revision]), 0)
                       = copy_revision
                     AND newer.created_at > copy_created_at)))
           OR (copy_note IS NOT NULL
               AND newer.submitted_from_uid = copy_note
               AND newer.created_at > copy_created_at))
}}"""


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
        """Verify teacher-student share an active group."""
        query = """
        MATCH (teacher:User {uid: $teacher_uid})-[:OWNS]->(g:Group)
              <-[:MEMBER_OF]-(student:User {uid: $subject_uid})
        WHERE g.is_active = true
        RETURN g.uid AS group_uid LIMIT 1
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
        """Teacher's pending review queue via ``SUBMITTED_TO_GROUP``.

        Returns entries submitted to the teacher's ACTIVE groups whose pipeline
        is ``teacher_review`` — the same visibility the detail read
        (``get_entry_detail_for_teacher``) and the review writes
        (``verify_teacher_has_group_access``) enforce, so the queue never
        lists work the teacher cannot open or act on. Empty when the teacher
        owns no groups, or when no ``UserEntry`` has been
        ``SUBMITTED_TO_GROUP`` an owned group — so we do not leak the
        existence of unrelated students' submissions. A share
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
        whatever the newer copy's status. The rule is ``_SUPERSEDED_COPY``,
        shared with the dashboard badge and the students summary.
        ``exercise_uid`` / ``exercise_title`` read the live exercise, falling
        back to the snapshot once it is deleted.
        """
        statuses = status_filter or _PENDING_STATUSES
        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})-[:{RelationshipName.OWNS.value}]->(g:Group)
        MATCH (entry:Entity:UserEntry)-[:{RelationshipName.SUBMITTED_TO_GROUP.value}]->(g)
        WHERE g.is_active = true
          AND entry.pipeline = $pipeline
          AND entry.status IN $statuses
          AND ($student_uid IS NULL OR EXISTS {{
              MATCH (:User {{uid: $student_uid}})-[:{RelationshipName.OWNS.value}]->(entry)
          }})
        OPTIONAL MATCH (entry)-[r:{RelationshipName.FULFILLS_EXERCISE.value}]->(:Entity:Exercise)
        OPTIONAL MATCH (ex:Entity:Exercise {{uid: entry.turn_in_exercise_uid}})
        OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(entry)
        WITH teacher, entry, r, ex, student, g,
             entry.uid AS copy_uid,
             entry.turn_in_exercise_uid AS copy_lineage,
             entry.submitted_from_uid AS copy_note,
             coalesce(r.revision, 0) AS copy_revision,
             entry.created_at AS copy_created_at
        WHERE NOT {_SUPERSEDED_COPY}
        OPTIONAL MATCH (report:Entity {{entity_type: 'entry_report'}})-[:{RelationshipName.REPORT_FOR.value}]->(entry)
        WITH entry, r, ex, student, g, count(DISTINCT report) AS feedback_count
        RETURN entry.uid AS entry_uid,
               entry.title AS title,
               entry.status AS status,
               entry.entity_type AS entity_type,
               entry.original_filename AS original_filename,
               entry.created_at AS submitted_at,
               student.uid AS student_uid,
               student.name AS student_name,
               coalesce(ex.uid, entry.turn_in_exercise_uid) AS exercise_uid,
               coalesce(ex.title, entry.turn_in_exercise_title) AS exercise_title,
               ex.due_date AS due_date,
               coalesce(r.revision, entry.turn_in_revision) AS revision,
               g.uid AS group_uid,
               feedback_count
        ORDER BY entry.created_at DESC
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
        """Get the report_file_path for an EntryReport, gated by teacher group access.

        Anchors on the report, walks ``REPORT_FOR`` to the reviewed submission
        and its owning student, and requires the teacher to share an active
        group with that student (a student-level authority; the review write
        gate, ``verify_teacher_has_group_access``, is narrower — the entry's
        own feedback request). Returns ``None`` both
        when no such report exists and when the teacher is outside the student's
        classroom, so a denied download is indistinguishable from a missing one
        and cannot enumerate other classrooms' reports.
        """
        query = f"""
        MATCH (r:Entity {{uid: $report_uid, entity_type: 'entry_report'}})
              -[:{RelationshipName.REPORT_FOR.value}]->(sub:Entity)
        MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(sub)
        MATCH (teacher:User {{uid: $teacher_uid}})-[:{RelationshipName.OWNS.value}]->(g:Group)
              <-[:{RelationshipName.MEMBER_OF.value}]-(student)
        WHERE g.is_active = true
          AND student.uid <> $teacher_uid
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
    ) -> Result[list[Neo4jProperties]]:
        """Approve entry: set status and return linked KU UIDs for mastery."""
        query = f"""
        MATCH (ku:Entity {{uid: $report_uid}})
        WHERE ku.status IN $allowed_from_statuses
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
            },
        )

    async def get_entries_for_exercise_review(
        self, exercise_uid: str, teacher_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Entries against an exercise that are submitted to the requesting teacher's groups.

        Scoped to teacher-review turn-ins ``SUBMITTED_TO_GROUP`` an active
        group the teacher owns — a teacher supplying another teacher's
        exercise UID gets an empty result rather than that classroom's work,
        and a deactivated group's work no longer lists (ADR-088 §3).
        """
        query = f"""
        MATCH (s:Entity:UserEntry)-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(e:Entity:Exercise {{uid: $exercise_uid}})
        WHERE s.pipeline = $pipeline
          AND EXISTS {{ (s)-[:{RelationshipName.SUBMITTED_TO_GROUP.value}]->(:Group {{is_active: true}})<-[:{RelationshipName.OWNS.value}]-(:User {{uid: $teacher_uid}}) }}
        OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(s)
        OPTIONAL MATCH (fb:Entity {{entity_type: 'entry_report'}})-[:{RelationshipName.REPORT_FOR.value}]->(s)
        WITH s, student, count(fb) AS feedback_count
        RETURN s.uid AS uid, s.title AS title,
               s.original_filename AS original_filename, s.status AS status,
               s.created_at AS created_at, student.uid AS student_uid,
               student.name AS student_name, feedback_count,
               s.turn_in_revision AS revision
        ORDER BY s.created_at DESC
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
        """Students who have submitted work to an active group the teacher owns, with entry counts.

        ``submission_count`` is every submission, ``reviewed_count`` the
        completed ones, and ``pending_count`` the rest that are not superseded
        — the queue's one supersede rule (``_SUPERSEDED_COPY``), so a copy
        replaced by a newer one from the same exercise or the same vault note
        is history, not work awaiting review.
        """
        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})
        MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(ku:Entity:UserEntry)
        WHERE student.uid <> $teacher_uid
          AND ku.pipeline = $pipeline
          AND EXISTS {{ (ku)-[:{RelationshipName.SUBMITTED_TO_GROUP.value}]->(:Group {{is_active: true}})<-[:{RelationshipName.OWNS.value}]-(teacher) }}
        OPTIONAL MATCH (ku)-[r:{RelationshipName.FULFILLS_EXERCISE.value}]->(:Entity:Exercise)
        WITH teacher, student, ku,
             ku.uid AS copy_uid,
             ku.turn_in_exercise_uid AS copy_lineage,
             ku.submitted_from_uid AS copy_note,
             coalesce(max(r.revision), 0) AS copy_revision,
             ku.created_at AS copy_created_at
        WITH student, ku,
             ku.status = $completed AS reviewed,
             {_SUPERSEDED_COPY} AS superseded
        WITH student,
             count(DISTINCT ku) AS submission_count,
             count(DISTINCT CASE WHEN reviewed THEN ku.uid END) AS reviewed_count,
             count(DISTINCT CASE WHEN NOT reviewed AND NOT superseded THEN ku.uid END) AS pending_count
        RETURN student.uid AS student_uid,
               student.name AS student_name,
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
        """A student's teacher-review entries that are submitted to the teacher's groups.

        Gate: each entry must itself be ``SUBMITTED_TO_GROUP`` an active group the
        requesting teacher owns — not merely prove that teacher and student share
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
        MATCH (student:User {{uid: $student_uid}})-[:{RelationshipName.OWNS.value}]->(ku:Entity:UserEntry)
        WHERE ku.pipeline = $pipeline
          AND EXISTS {{
            (ku)-[:{RelationshipName.SUBMITTED_TO_GROUP.value}]->(g:Group {{is_active: true}})
                <-[:{RelationshipName.OWNS.value}]-(:User {{uid: $teacher_uid}})
          }}
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
        ORDER BY ku.created_at DESC
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
        """Full entry detail for teacher review, gated by SUBMITTED_TO_GROUP.

        Model B gate: the entry must be ``SUBMITTED_TO_GROUP`` an active group
        the teacher owns. Empty result when the entry asks none of the
        teacher's groups for feedback — service-layer callers (``get_submission_detail``)
        map empty to ``Errors.not_found`` (404) so a teacher outside the
        student's group cannot distinguish "entry does not exist" from
        "entry exists but belongs to another teacher's student".
        """
        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})-[:{RelationshipName.OWNS.value}]->(g:Group)
        WHERE g.is_active = true
        MATCH (s:Entity:UserEntry {{uid: $entry_uid}})
              -[:{RelationshipName.SUBMITTED_TO_GROUP.value}]->(g)
        WHERE s.pipeline = $pipeline
        OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(s)
        OPTIONAL MATCH (ex:Entity:Exercise {{uid: s.turn_in_exercise_uid}})
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
               student.name AS student_name,
               coalesce(ex.uid, s.turn_in_exercise_uid) AS exercise_uid,
               coalesce(ex.title, s.turn_in_exercise_title) AS exercise_title,
               s.turn_in_revision AS revision,
               ex.instructions AS exercise_instructions
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
        across entries ``SUBMITTED_TO_GROUP`` an active group the teacher owns.
        ``total_exercises`` + ``total_groups`` are scoped via direct ``OWNS``
        from the teacher (already correct pre-fix).

        ``pending_count`` is the review queue's badge twin and reads the
        queue's one supersede rule (``_SUPERSEDED_COPY``): a pending copy
        superseded by a newer one from the same exercise or the same vault
        note is not pending work, so the badge and the queue length agree.
        """
        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})
        OPTIONAL MATCH (teacher)-[:{RelationshipName.OWNS.value}]->(g:Group)
        OPTIONAL MATCH (sub:Entity:UserEntry)
                      -[:{RelationshipName.SUBMITTED_TO_GROUP.value}]->(g)
          WHERE sub.pipeline = $pipeline AND g.is_active = true
        OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(sub)
        WHERE student.uid <> $teacher_uid
        OPTIONAL MATCH (teacher)-[:{RelationshipName.OWNS.value}]->(ex:Entity:Exercise)
        WITH teacher, g, sub, student, ex,
             sub.uid AS copy_uid,
             sub.turn_in_exercise_uid AS copy_lineage,
             sub.submitted_from_uid AS copy_note,
             coalesce(head([(sub)-[sr:{RelationshipName.FULFILLS_EXERCISE.value}]->(:Entity:Exercise) | sr.revision]), 0) AS copy_revision,
             sub.created_at AS copy_created_at
        RETURN
          count(DISTINCT CASE
              WHEN sub.status IN $pending_statuses
               AND EXISTS {{
                  (sub)-[:{RelationshipName.SUBMITTED_TO_GROUP.value}]->(:Group {{is_active: true}})
                       <-[:{RelationshipName.OWNS.value}]-(teacher)
               }}
               AND NOT {_SUPERSEDED_COPY}
              THEN sub.uid END) AS pending_count,
          count(DISTINCT student) AS total_students,
          count(DISTINCT ex) AS total_exercises,
          count(DISTINCT g) AS total_groups
        """
        return await self.execute_query(
            query,
            {
                "teacher_uid": teacher_uid,
                "pipeline": Pipeline.TEACHER_REVIEW.value,
                "pending_statuses": _PENDING_STATUSES,
            },
        )

    async def verify_teacher_has_group_access(
        self, submission_uid: str, teacher_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Verify the entry asks this teacher for feedback — the review-write gate.

        The same authority the queue and the detail read carry (ADR-088 §2):
        the entry itself must be ``SUBMITTED_TO_GROUP`` an active group the
        teacher ``OWNS``. Sharing a classroom with the *owner* is deliberately
        not enough — a multi-class student who sent the entry to one teacher's
        group has not put it in another teacher's hands, so that other teacher
        can neither open it nor write on it. A teacher never reviews their own
        entry. Returns empty when the entry asks none of the teacher's active
        groups — callers map empty to 404 (not found) so we do not leak the
        existence of unrelated students' submissions.
        """
        query = f"""
        MATCH (submission:Entity {{uid: $submission_uid}})
        MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(submission)
        MATCH (teacher:User {{uid: $teacher_uid}})-[:{RelationshipName.OWNS.value}]->(g:Group)
              <-[:{RelationshipName.SUBMITTED_TO_GROUP.value}]-(submission)
        WHERE g.is_active = true
          AND student.uid <> $teacher_uid
        RETURN true AS has_access LIMIT 1
        """
        return await self.execute_query(
            query, {"submission_uid": submission_uid, "teacher_uid": teacher_uid}
        )
