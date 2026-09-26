"""
UserEntry Report Query Mixin
=============================

Cross-joins to EntryReport and learning-loop chain queries.
Covers pending entries, unsubmitted exercises, report summaries,
and learning-loop chain reads.

Consolidated from the legacy ``_SubmissionReportQueryMixin`` into a single
standalone mixin (ADR-054).

Requires on concrete class:
    driver, label, logger, execute_query (from _SearchMixin)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.persistence.neo4j.query.cypher.learning_loop_fragments import (
    build_review_standing_subquery,
)
from core.models.enums.entity_enums import EntityType
from core.models.relationship_names import RelationshipName
from core.models.type_hints import Neo4jProperties, UserUID
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from core.models.enums.neo_labels import NeoLabel

_USER_ENTRY = EntityType.USER_ENTRY.value


class _UserEntryReportQueryMixin:
    """Report-relationship cross-joins and learning-loop chain reads for ``UserEntry``.

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
    # REPORT RELATIONSHIP QUERIES
    # ========================================================================

    async def get_pending_submissions_raw(
        self,
        user_uid: UserUID,
        submission_types: list[str],
        pipelines: list[str] | None = None,
    ) -> Result[list[Neo4jProperties]]:
        """Get entries without a REPORT_FOR relationship.

        When ``pipelines`` is non-empty, narrows further to entries whose
        ``pipeline`` property is in the given values (``$pipelines IS NULL``
        is the no-filter case, evaluated server-side).
        """
        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(submission:Entity)
        WHERE submission.entity_type IN $submission_types
          AND ($pipelines IS NULL OR submission.pipeline IN $pipelines)
          AND NOT ()-[:{RelationshipName.REPORT_FOR.value}]->(submission)
        RETURN submission.uid AS uid
        ORDER BY submission.created_at DESC
        LIMIT 20
        """
        return await self.execute_query(
            query,
            {
                "user_uid": user_uid,
                "submission_types": submission_types,
                "pipelines": pipelines if pipelines else None,
            },
        )

    async def get_pending_entries_raw(
        self, user_uid: UserUID, pipelines: list[str] | None = None
    ) -> Result[list[Neo4jProperties]]:
        """Entries without an incoming ``REPORT_FOR`` relationship."""
        return await self.get_pending_submissions_raw(
            user_uid=user_uid,
            submission_types=[_USER_ENTRY],
            pipelines=pipelines,
        )

    async def get_unsubmitted_exercises_raw(
        self, user_uid: UserUID, limit: int
    ) -> Result[list[Neo4jProperties]]:
        """Get exercises assigned via group with no entry yet."""
        query = f"""
        MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.MEMBER_OF.value}]->(group:Group)
        MATCH (exercise:Entity {{entity_type: 'exercise', scope: 'assigned'}})-[:{RelationshipName.SHARED_WITH_GROUP.value}]->(group)
        WHERE NOT (:Entity {{user_uid: $user_uid}})-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(exercise)
        RETURN exercise.uid AS uid,
               exercise.title AS title,
               exercise.due_date AS due_date
        ORDER BY exercise.due_date ASC
        LIMIT $limit
        """
        return await self.execute_query(query, {"user_uid": user_uid, "limit": limit})

    async def get_report_summary_raw(
        self, user_uid: UserUID, submission_types: list[str]
    ) -> Result[list[Neo4jProperties]]:
        """Get report completion counts for a user's entries."""
        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(submission:Entity)
        WHERE submission.entity_type IN $submission_types
        OPTIONAL MATCH (fb:Entity)-[:{RelationshipName.REPORT_FOR.value}]->(submission)
        WITH submission, count(fb) AS report_count
        RETURN
            count(submission) AS total_submissions,
            count(CASE WHEN report_count > 0 THEN 1 END) AS with_report,
            count(CASE WHEN report_count = 0 THEN 1 END) AS without_report,
            sum(report_count) AS total_reports
        """
        return await self.execute_query(
            query, {"user_uid": user_uid, "submission_types": submission_types}
        )

    async def get_entry_report_summary_raw(
        self, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Aggregate report completion counts across user's entries."""
        return await self.get_report_summary_raw(
            user_uid=user_uid,
            submission_types=[_USER_ENTRY],
        )

    async def get_learning_loop_chain_raw(self, exercise_uid: str) -> Result[list[Neo4jProperties]]:
        """Traverse full learning loop chain from an exercise."""
        query = f"""
        MATCH (ex:Entity {{uid: $exercise_uid}})
        WHERE ex.entity_type IN ['exercise', 'revised_exercise']
        OPTIONAL MATCH (sub:Entity:UserEntry)-[:{RelationshipName.FULFILLS_EXERCISE.value}|{RelationshipName.FULFILLS_REVISED_EXERCISE.value}]->(ex)
        OPTIONAL MATCH (fb:Entity)-[:{RelationshipName.REPORT_FOR.value}]->(sub)
          WHERE fb.entity_type = 'entry_report'
        OPTIONAL MATCH (re:Entity)-[:{RelationshipName.RESPONDS_TO_REPORT.value}]->(fb)
          WHERE re.entity_type = 'revised_exercise'
        RETURN ex {{.uid, .title, .entity_type, .status, .created_at}} AS exercise,
               collect(DISTINCT sub {{.uid, .title, .status, .created_at, .user_uid}}) AS submissions,
               collect(DISTINCT fb {{.uid, .title, .processor_type, .created_at}}) AS feedback,
               collect(DISTINCT re {{.uid, .title, .revision_number, .created_at}}) AS revised_exercises
        """
        return await self.execute_query(query, {"exercise_uid": exercise_uid})

    async def get_exchange_thread_raw(
        self, exercise_uid: str, student_uid: str, viewer_uid: str | None = None
    ) -> Result[list[Neo4jProperties]]:
        """One (student, root exercise) exchange — the whole chain in one read.

        Collects every artifact of the exchange thread (feedback-loop UX arc
        C5): the student's entries whose turn-in snapshot names the root
        exercise (``turn_in_exercise_uid`` — the key every turn-in carries,
        whether it was filed against the exercise or against a revision of
        it), each with its ``FULFILLS_EXERCISE`` edge revision and, for a
        revision response, the RevisedExercise it answers; the reports
        written on those entries; and the revision requests that respond to
        those reports. Revisions are scoped through the chain's own reports,
        so another student's revision of the same exercise never appears.

        The exercise node is optional: an exchange outlives its exercise
        (Submit & Share arc R12). ``exercise`` is NULL once it is deleted,
        ``exercise_removed`` says so, and ``snapshot_title`` carries the
        title the newest entry snapshotted at submission.

        ``viewer_uid`` is the teacher-mode scope (NULL = the student reading
        their own exchange): each entry must itself be ``SUBMITTED_TO_GROUP``
        an active group the viewer owns — the Model B entry-level gate
        (``get_entry_detail_for_teacher``). Merely sharing *some* group with
        a multi-class student must not expose work the student directed only
        to another teacher's classroom; reports and revisions hang off the
        entries, so gating the entries gates the whole chain.

        Received feedback is identified by its outcome: a report is part of
        the exchange only when ``assessment_outcome`` is set (every teacher or
        AI feedback writer sets one). A journal reflection carries none — it
        is the student's own artifact, not part of the teacher↔student
        exchange — and the ``visibility`` property decides nothing here
        (ADR-088).

        Every ``created_at`` is emitted through ``toString()`` so the caller
        always receives ISO-8601 strings — entry timestamps are stored as ISO
        strings by the mapper while report timestamps are native datetimes,
        and a mixed-type emission would push the sort problem to every reader.

        Returns a single row: ``exercise`` (NULL when no live Exercise
        carries the uid), ``exercise_removed``, ``snapshot_title``,
        ``entries``, ``reports``, ``revisions``.
        """
        query = f"""
        OPTIONAL MATCH (ex:Entity:Exercise {{uid: $exercise_uid}})
        OPTIONAL MATCH (:User {{uid: $student_uid}})-[:{RelationshipName.OWNS.value}]->(e:Entity:UserEntry)
        WHERE e.turn_in_exercise_uid = $exercise_uid
          AND ($viewer_uid IS NULL OR EXISTS {{
            MATCH (e)-[:{RelationshipName.SUBMITTED_TO_GROUP.value}]->(:Group {{is_active: true}})
                  <-[:{RelationshipName.OWNS.value}]-(:User {{uid: $viewer_uid}})
          }})
        OPTIONAL MATCH (e)-[f:{RelationshipName.FULFILLS_EXERCISE.value}]->(:Entity:Exercise)
        OPTIONAL MATCH (e)-[:{RelationshipName.FULFILLS_REVISED_EXERCISE.value}]->(rex:Entity:RevisedExercise)
        WITH ex, e, f, rex
        ORDER BY toString(e.created_at) DESC, e.uid
        WITH ex,
             collect(DISTINCT e {{.uid, .title, .status, created_at: toString(e.created_at),
                                  revision: f.revision, via_revised_uid: rex.uid}}) AS entry_rows,
             collect(DISTINCT e) AS entry_nodes,
             head([t IN collect(e.turn_in_exercise_title) WHERE t IS NOT NULL]) AS snapshot_title
        OPTIONAL MATCH (report:Entity {{entity_type: 'entry_report'}})-[:{RelationshipName.REPORT_FOR.value}]->(entry)
        WHERE entry IN entry_nodes
          AND report.assessment_outcome IS NOT NULL
        WITH ex, entry_rows, snapshot_title,
             collect(DISTINCT report {{.uid, .title, .content, .processed_content, .processor_type,
                                       .report_file_path, created_at: toString(report.created_at),
                                       entry_uid: entry.uid}}) AS report_rows,
             collect(DISTINCT report) AS report_nodes
        OPTIONAL MATCH (rev:Entity:RevisedExercise)-[:{RelationshipName.RESPONDS_TO_REPORT.value}]->(rep)
        WHERE rep IN report_nodes
        RETURN ex {{.uid, .title, .status, .entity_type}} AS exercise,
               ex IS NULL AS exercise_removed,
               snapshot_title,
               entry_rows AS entries,
               report_rows AS reports,
               collect(DISTINCT rev {{.uid, .title, .instructions, .revision_number,
                                      created_at: toString(rev.created_at),
                                      report_uid: rep.uid}}) AS revisions
        """
        return await self.execute_query(
            query,
            {
                "exercise_uid": exercise_uid,
                "student_uid": student_uid,
                "viewer_uid": viewer_uid,
            },
        )

    async def get_student_exchange_summaries_raw(
        self, student_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Every exchange the student is in, one summary row each — one read.

        The GradeBook page's single query (feedback-loop UX arc 2 C1): per
        root exercise the student has turn-ins against — grouped on the
        turn-in snapshot ``turn_in_exercise_uid``, the key every turn-in
        carries whether it was filed against the exercise or against a
        revision of it — the latest entry, the latest report on that entry,
        and lineage counts. The exercise node is optional: an exchange
        outlives its exercise (Submit & Share arc R12) — ``exercise_removed``
        is true once it is deleted and ``exercise_title`` then reads the
        newest entry's snapshot. A second column carries the received
        reports OUTSIDE any exchange (a report on an entry with no snapshot,
        or on no entry at all) so the page's "Other feedback" group needs no
        second query.

        Latest-entry pick is ``created_at`` (tie: uid) rather than the review
        queue's revision-first collapse — the edge revision dies with the
        exercise, and the snapshot key must rank a deleted exercise's
        entries the same way as a live one's. The latest entry's derived
        review standing (``build_review_standing_subquery`` — the badges' one
        derivation) and whether it carries any share link yet ride on the
        row as ``latest_entry_revised_after_feedback`` /
        ``latest_entry_shared``: the "Share your revised work" nudge (R2).

        Received feedback is identified by its outcome everywhere in this
        read: only reports with ``assessment_outcome`` set count (a journal
        reflection carries none and is not received feedback; the
        ``visibility`` property decides nothing — ADR-088). Every
        ``created_at`` is emitted through ``toString()`` — entry stamps are
        ISO strings, report stamps native datetimes; emission normalizes so
        the service can treat naive values as UTC (the exchange-thread
        convention).

        Returns a single row: ``exercise_summaries`` (unordered — the
        service sorts by latest activity), ``other_feedback`` (newest first).
        """
        review_standing = build_review_standing_subquery("latest_entry")
        query = f"""
        MATCH (student:User {{uid: $student_uid}})
        CALL (student) {{
            MATCH (student)-[:{RelationshipName.OWNS.value}]->(e:Entity:UserEntry)
            WHERE e.turn_in_exercise_uid IS NOT NULL
            OPTIONAL MATCH (r:Entity {{entity_type: $report_type}})-[:{RelationshipName.REPORT_FOR.value}]->(e)
                WHERE r.assessment_outcome IS NOT NULL
            WITH e, r ORDER BY r.created_at DESC
            WITH e, collect(r {{.uid, .processor_type, created_at: toString(r.created_at)}}) AS entry_reports
            WITH e, entry_reports, size(entry_reports) AS n_reports
            ORDER BY toString(e.created_at) DESC, e.uid
            WITH e.turn_in_exercise_uid AS exercise_uid,
                 count(e) AS entry_count,
                 sum(n_reports) AS report_count,
                 collect({{uid: e.uid, status: e.status, created_at: toString(e.created_at),
                          snapshot_title: e.turn_in_exercise_title,
                          reports: entry_reports}})[0] AS latest
            MATCH (latest_entry:Entity:UserEntry {{uid: latest.uid}})
            {review_standing}
            WITH exercise_uid, entry_count, report_count, latest, revised_after_feedback,
                 (EXISTS {{ (latest_entry)<-[:{RelationshipName.SHARES_WITH.value}]-(:User) }}
                  OR EXISTS {{ (latest_entry)-[:{RelationshipName.SHARED_WITH_GROUP.value}]->(:Group) }}
                 ) AS latest_entry_shared
            OPTIONAL MATCH (ex:Entity:Exercise {{uid: exercise_uid}})
            RETURN collect({{
                exercise_uid: exercise_uid,
                exercise_title: coalesce(ex.title, latest.snapshot_title),
                exercise_removed: ex IS NULL,
                latest_entry_uid: latest.uid,
                latest_entry_status: latest.status,
                latest_entry_created_at: latest.created_at,
                latest_report: head(latest.reports),
                entry_count: entry_count,
                report_count: report_count,
                latest_entry_revised_after_feedback: revised_after_feedback,
                latest_entry_shared: latest_entry_shared
            }}) AS exercise_summaries
        }}
        CALL (student) {{
            MATCH (student)-[:{RelationshipName.OWNS.value}]->(r:Entity {{entity_type: $report_type}})
            WHERE r.assessment_outcome IS NOT NULL
            OPTIONAL MATCH (r)-[:{RelationshipName.REPORT_FOR.value}]->(e:Entity:UserEntry)
            WITH r, e
            WHERE e IS NULL OR e.turn_in_exercise_uid IS NULL
            WITH r ORDER BY r.created_at DESC
            RETURN collect(r {{.uid, .title, .processor_type, created_at: toString(r.created_at)}}) AS other_feedback
        }}
        RETURN exercise_summaries, other_feedback
        """
        return await self.execute_query(
            query,
            {
                "student_uid": student_uid,
                "report_type": EntityType.ENTRY_REPORT.value,
            },
        )

    async def get_entry_review_standing_raw(self, entry_uid: str) -> Result[list[Neo4jProperties]]:
        """One entry's derived review standing — the recipient card's badges (R2).

        The badges' one derivation (``build_review_standing_subquery``) over
        the entry alone: ``reviewed_by`` and ``revised_after_feedback``. No
        owner arm — the caller's audience read decided who may see the
        entry; this read only says what standing it has. No row for a uid
        that names no UserEntry.
        """
        review_standing = build_review_standing_subquery("entry")
        query = f"""
        MATCH (entry:Entity:UserEntry {{uid: $entry_uid}})
        {review_standing}
        RETURN reviewed_by, revised_after_feedback
        """
        return await self.execute_query(query, {"entry_uid": entry_uid})

    async def get_submission_chain_raw(self, submission_uid: str) -> Result[list[Neo4jProperties]]:
        """Traverse learning loop chain from a specific entry.

        The ``exercise`` projection is keyed by the entry's turn-in snapshot:
        the live Exercise node when one still carries the snapshotted uid,
        else the snapshot itself with ``removed: true`` (the exchange
        outlives its exercise — Submit & Share arc R12); NULL for an entry
        that is not a turn-in.
        """
        query = f"""
        MATCH (sub:Entity:UserEntry {{uid: $submission_uid}})
        OPTIONAL MATCH (ex:Entity:Exercise {{uid: sub.turn_in_exercise_uid}})
        OPTIONAL MATCH (fb:Entity)-[:{RelationshipName.REPORT_FOR.value}]->(sub)
          WHERE fb.entity_type = 'entry_report'
        OPTIONAL MATCH (re:Entity)-[:{RelationshipName.RESPONDS_TO_REPORT.value}]->(fb)
          WHERE re.entity_type = 'revised_exercise'
        RETURN sub {{.uid, .title, .status, .created_at, .user_uid}} AS submission,
               CASE
                 WHEN ex IS NOT NULL THEN ex {{.uid, .title, .entity_type, .status, removed: false}}
                 WHEN sub.turn_in_exercise_uid IS NOT NULL THEN {{
                   uid: sub.turn_in_exercise_uid, title: sub.turn_in_exercise_title,
                   entity_type: $exercise_type, status: NULL, removed: true}}
                 ELSE NULL
               END AS exercise,
               collect(DISTINCT fb {{.uid, .title, .processor_type, .created_at}}) AS feedback,
               collect(DISTINCT re {{.uid, .title, .revision_number, .student_uid, .created_at}}) AS revised_exercises
        """
        return await self.execute_query(
            query,
            {"submission_uid": submission_uid, "exercise_type": EntityType.EXERCISE.value},
        )

    async def get_entry_chain_raw(self, entry_uid: str) -> Result[list[Neo4jProperties]]:
        """Loop chain rooted at a specific entry."""
        return await self.get_submission_chain_raw(submission_uid=entry_uid)

    async def get_admin_uid(self) -> Result[list[Neo4jProperties]]:
        """Get the UID of the oldest human admin user.

        The role lives in the `role` property (the User dataclass field name);
        `user_role` was a legacy property no current write path produces.

        Service accounts (`@skuel.local` emails: user_system, the legacy
        vault-watcher) carry role=admin but must never win this pick — the
        caller treats the result as the default TEACHER for curriculum
        content, and a default group owned by user_system is a review queue
        nobody can ever log into.
        """
        query = """
        MATCH (admin:User)
        WHERE admin.role = 'admin'
          AND NOT coalesce(admin.email, '') ENDS WITH '@skuel.local'
        RETURN admin.uid AS admin_uid
        ORDER BY admin.created_at ASC
        LIMIT 1
        """
        return await self.execute_query(query, {})
