"""
UserEntry Protocols — ADR-054
==============================

Backend-level, ISP-split protocols for the unified ``UserEntry`` domain.
``UserEntry`` replaces ``Submission`` / ``ExerciseSubmission`` / ``JeInput`` /
``JeOutput`` as one type of user-authored artifact. Dispatch is driven by the
``Pipeline`` enum on the entry, not by ``entity_type`` branching.

Five ISP parents mirror the five backend mixins (renamed in Step 4 from
``_submission_*_mixin.py`` to ``_user_entry_*_mixin.py``):

    UserEntryCrudOperations         — content search + feedback-count joins
    UserEntryLifecycleOperations    — create-with-link, FULFILLS_EXERCISE,
                                      temporal/thematic relationships
    UserEntryAssessmentOperations   — teacher review queue (SHARED_WITH_GROUP),
                                      assessments, teacher dashboards
    UserEntryReportQueryOperations  — learning-loop chain queries + report
                                      cross-joins
    UserEntryContentOperations      — processing context + exercise-instruction
                                      enrichment reads

``UserEntryOperations`` aggregates the five parents and extends
``BackendOperations[UserEntry]`` — this is the protocol that
``UserEntryBackend`` satisfies (added in Step 4) and that
``UserEntryService.__init__`` consumes (added in Step 5).

``UserEntryProcessingOperations`` is a separate, narrower contract for the
dispatcher service — it takes a ``UserEntry`` and runs its ``Pipeline``.

Additive for Step 3: nothing consumes these protocols yet. The legacy
``submission_protocols.py`` and ``journal_protocols.py`` remain in place
through Step 13 and are removed in the final cleanup step.

See: /home/mike/.claude/plans/woolly-weaving-hejlsberg.md
See: /docs/decisions/ADR-054-user-entry-unified-submissions.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from core.models.type_hints import Neo4jProperties, UserUID
from core.ports.base_protocols import BackendOperations
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.user_entry.user_entry import UserEntry


# ============================================================================
# ISP parent 1 — CRUD / content search / feedback-count joins
# ============================================================================


@runtime_checkable
class UserEntryCrudOperations(Protocol):
    """Content search + feedback-count joins for ``UserEntry`` nodes.

    Implementation: ``_UserEntryCrudMixin`` (Step 4 rename of
    ``_SubmissionCrudMixin``).
    """

    async def search_entry_content(
        self,
        user_uid: UserUID,
        query_text: str,
        limit: int = 50,
    ) -> Result[list[Neo4jProperties]]:
        """Case-insensitive substring search across ``processed_content``."""
        ...

    async def get_entries_with_feedback_count(
        self,
        user_uid: UserUID,
        limit: int = 50,
    ) -> Result[list[Neo4jProperties]]:
        """List user entries enriched with teacher feedback counts."""
        ...

    async def count_entries_for_exercise(self, user_uid: UserUID, exercise_uid: str) -> Result[int]:
        """Count entries a user has submitted against an exercise (full loop)."""
        ...

    async def get_first_entry_for_exercise(
        self, user_uid: UserUID, exercise_uid: str
    ) -> Result[Neo4jProperties | None]:
        """Earliest entry's uid + created_at for a user+exercise pair."""
        ...

    async def get_exercise_for_entry(self, entry_uid: str) -> Result[str | None]:
        """Exercise UID linked via ``FULFILLS_EXERCISE``, if any."""
        ...

    async def get_teacher_feedback_state(self, teacher_uid: str) -> Result[Neo4jProperties]:
        """Read feedback EMA state from ``User`` for turnaround calibration."""
        ...

    async def update_teacher_feedback_state(
        self, teacher_uid: str, properties: Neo4jProperties
    ) -> Result[bool]:
        """Write feedback EMA state to ``User``."""
        ...


# ============================================================================
# ISP parent 2 — lifecycle: create-with-link + relationship wiring
# ============================================================================


@runtime_checkable
class UserEntryLifecycleOperations(Protocol):
    """FULFILLS_EXERCISE + temporal/thematic relationship wiring.

    Replaces ``_SubmissionLifecycleMixin``. ``create_with_exercise_link``
    carries the revision on the edge (``FULFILLS_EXERCISE {revision}``);
    no node field.

    Implementation: ``_UserEntryLifecycleMixin`` (Step 4).
    """

    async def get_exercise_context(self, exercise_uid: str) -> Result[list[Neo4jProperties]]:
        """Exercise scope, teacher, group info for entry creation."""
        ...

    async def get_entry_owner(self, entry_uid: str) -> Result[list[Neo4jProperties]]:
        """Student UID who owns an entry."""
        ...

    async def verify_student_group_membership(
        self, entry_uid: str, group_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Check student owns entry AND is member of group."""
        ...

    async def create_with_exercise_link(
        self,
        entry: UserEntry,
        exercise_uid: str,
        revision: int,
    ) -> Result[UserEntry]:
        """Atomically create a ``UserEntry`` and link it to an exercise.

        Writes ``(:UserEntry)-[:FULFILLS_EXERCISE {revision}]->(:Exercise)``.
        For a ``RevisedExercise`` target, additionally writes
        ``FULFILLS_REVISED_EXERCISE`` to the revision node while anchoring
        ``FULFILLS_EXERCISE`` on the root ``Exercise``.
        """
        ...

    async def create_temporal_relationship(
        self, entry_uid: str, user_uid: UserUID, entity_type: str
    ) -> Result[list[Neo4jProperties]]:
        """Create FOLLOWS relationship to the most recent previous entry of the same type."""
        ...

    async def create_thematic_relationships(
        self,
        entry_uid: str,
        user_uid: UserUID,
        themes: list[str],
        shared_topics_str: str,
    ) -> Result[list[Neo4jProperties]]:
        """Create RELATED_TO relationships for entries sharing topics."""
        ...

    async def get_related_entry_uids(self, entry_uid: str) -> Result[list[Neo4jProperties]]:
        """UIDs of entries related via RELATED_TO."""
        ...

    async def get_supported_goal_uids(self, entry_uid: str) -> Result[list[Neo4jProperties]]:
        """UIDs of goals supported via SUPPORTS_GOAL."""
        ...

    async def get_entry_relationship_summary(self, entry_uid: str) -> Result[list[Neo4jProperties]]:
        """Per-entry relationship counts (related, goals, follows)."""
        ...


# ============================================================================
# ISP parent 3 — assessment + teacher review queue
# ============================================================================


@runtime_checkable
class UserEntryAssessmentOperations(Protocol):
    """Assessment scoring + teacher-review workflow.

    The review queue is a pure graph pattern on ``SHARED_WITH_GROUP`` +
    ``pipeline = 'teacher_review'`` — no role gate at the Cypher level.
    Route-level role checks remain authoritative for access.

    Implementation: ``_UserEntryAssessmentMixin`` (Step 4).
    """

    # -------- review queue (NEW — Step 4 rewrites the Cypher) --------

    async def get_review_queue(
        self,
        teacher_uid: str,
        status_filter: str | None = None,
        entity_type_filter: str | None = None,
    ) -> Result[list[Neo4jProperties]]:
        """Teacher's pending review queue (all student entries via OWNS).

        Distinct from ``get_review_queue_by_groups`` — this is the
        ``exercise_submission`` admin-oversight view (no group-sharing
        gate), defaulting to ``submitted+active`` when no status filter is
        given.
        """
        ...

    async def get_review_queue_by_groups(
        self,
        teacher_uid: str,
        status_filter: list[str] | None = None,
    ) -> Result[list[Neo4jProperties]]:
        """Teacher's pending review queue via ``SHARED_WITH_GROUP``.

        Pattern (Step 4 Cypher):

            MATCH (teacher:User {user_uid: $teacher_uid})-[:OWNS]->(g:Group)
            MATCH (entry:Entity:UserEntry)-[:SHARED_WITH_GROUP]->(g)
            WHERE entry.pipeline = 'teacher_review'
              AND entry.status IN $status_filter
            OPTIONAL MATCH (entry)-[r:FULFILLS_EXERCISE]->(ex:Exercise)
            OPTIONAL MATCH (student:User)-[:OWNS]->(entry)
            RETURN entry, student.user_uid AS student_uid,
                   student.display_name AS student_name,
                   ex.uid AS exercise_uid, ex.title AS exercise_title,
                   r.revision AS revision, g.uid AS group_uid
        """
        ...

    # -------- assessment relationships --------

    async def verify_teacher_authority(
        self, teacher_uid: str, subject_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Verify teacher-student share an active group."""
        ...

    async def create_assessment_relationship(
        self, assessment_uid: str, subject_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Create ``ASSESSMENT_OF`` from assessment report to student."""
        ...

    async def auto_share_assessment_with_student(
        self, subject_uid: str, assessment_uid: str, now: str
    ) -> Result[list[Neo4jProperties]]:
        """Auto-share assessment report with student via ``SHARES_WITH``."""
        ...

    async def get_assessments_for_student_raw(
        self, student_uid: str, limit: int
    ) -> Result[list[Neo4jProperties]]:
        """Assessment report nodes for a student via ``ASSESSMENT_OF``."""
        ...

    # -------- teacher review workflow --------

    async def get_report_file_path(self, report_uid: str) -> Result[str | None]:
        """Read ``report_file_path`` for an ``ExerciseReport`` node."""
        ...

    async def approve_and_get_linked_kus(
        self,
        report_uid: str,
        now: str,
        status: str,
        allowed_from_statuses: list[str],
    ) -> Result[list[Neo4jProperties]]:
        """Approve entry, return linked KU UIDs + mastery_impact."""
        ...

    async def get_submissions_for_exercise_review(
        self, exercise_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """All entries against an exercise (teacher review view).

        Submission-flavored sibling of ``get_entries_for_exercise_review``;
        retained for the ``exercise_submission`` admin-oversight path that
        ``TeacherReviewService.get_submissions_for_exercise`` calls.
        """
        ...

    async def get_entries_for_exercise_review(
        self, exercise_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """All entries against an exercise (teacher review view)."""
        ...

    async def get_students_summary(self, teacher_uid: str) -> Result[list[Neo4jProperties]]:
        """Students who have submitted, with submission counts."""
        ...

    async def get_student_submissions_for_teacher(
        self, _teacher_uid: str, student_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """All entries owned by a student (admin oversight view).

        Submission-flavored sibling of ``get_student_entries_for_teacher``;
        retained for the ``TeacherReviewService.get_student_submissions``
        admin-oversight surface.
        """
        ...

    async def get_student_entries_for_teacher(
        self, teacher_uid: str, student_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """All entries owned by a student (admin oversight view)."""
        ...

    async def get_submission_detail_for_teacher(
        self, submission_uid: str, teacher_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Full entry detail for teacher review (admin oversight view).

        Submission-flavored sibling of ``get_entry_detail_for_teacher``;
        retained for the ``TeacherReviewService.get_submission_detail``
        admin-oversight surface.
        """
        ...

    async def update_entry_score(
        self, entry_uid: str, score: float
    ) -> Result[list[Neo4jProperties]]:
        """Update the score on an entry explicitly."""
        ...

    async def get_entry_detail_for_teacher(
        self, entry_uid: str, teacher_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Full entry detail for teacher review (admin oversight view)."""
        ...

    async def get_dashboard_stats(self, teacher_uid: str) -> Result[list[Neo4jProperties]]:
        """At-a-glance stats for the teacher dashboard."""
        ...

    async def verify_teacher_has_group_access(
        self, entry_uid: str, teacher_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Verify teacher and the entry's owner share an active group."""
        ...


# ============================================================================
# ISP parent 4 — report relationship queries + learning-loop chain
# ============================================================================


@runtime_checkable
class UserEntryReportQueryOperations(Protocol):
    """Cross-joins to ``ExerciseReport`` + learning-loop chain reads.

    Implementation: ``_UserEntryReportQueryMixin`` (Step 4).
    """

    async def get_pending_entries_raw(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Entries without an incoming ``REPORT_FOR`` relationship."""
        ...

    async def get_unsubmitted_exercises_raw(
        self, user_uid: UserUID, limit: int
    ) -> Result[list[Neo4jProperties]]:
        """Group-assigned exercises with no entry yet from this user."""
        ...

    async def get_entry_report_summary_raw(
        self, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Aggregate report completion counts across user's entries.

        Named distinctly from the inherited ``get_report_summary_raw``
        (which takes ``submission_types``) to avoid an LSP conflict.
        """
        ...

    async def get_learning_loop_chain_raw(self, exercise_uid: str) -> Result[list[Neo4jProperties]]:
        """Full loop chain from an exercise (entries + reports + revisions)."""
        ...

    async def get_entry_chain_raw(self, entry_uid: str) -> Result[list[Neo4jProperties]]:
        """Loop chain rooted at a specific entry."""
        ...

    async def get_admin_uid(self) -> Result[list[Neo4jProperties]]:
        """Oldest admin user — fallback teacher for YAML-ingested exercises."""
        ...


# ============================================================================
# ISP parent 5 — processing context + exercise-instruction enrichment
# ============================================================================


@runtime_checkable
class UserEntryContentOperations(Protocol):
    """Processing context + exercise-instruction enrichment reads.

    Journal-flavored methods now operate on ``UserEntry`` with
    ``pipeline IN ('transcribe_and_structure', ...)`` rather than on a
    distinct ``JeInput``/``JeOutput`` label.

    Implementation: ``_UserEntryContentMixin`` (Step 4).
    """

    async def get_journal_processing_context(
        self, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Single-query context bundle for the journal enrichment pipeline."""
        ...

    async def get_recent_journal_entries(
        self, user_uid: UserUID, cutoff_datetime: str
    ) -> Result[list[Neo4jProperties]]:
        """Recent journal-flavored entries."""
        ...

    async def get_active_goals_for_user(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Active goals for a user (enrichment context)."""
        ...

    async def get_recent_journal_topics(
        self, user_uid: UserUID, cutoff_datetime: str
    ) -> Result[list[Neo4jProperties]]:
        """``key_topics`` from recent journal entries for aggregation."""
        ...

    async def load_exercise_instructions(self, uid: str) -> Result[list[Neo4jProperties]]:
        """Load formatting instructions from an ``Exercise`` node."""
        ...

    async def create_exercise_instruction_set(
        self, uid: str, name: str, instructions: str
    ) -> Result[list[Neo4jProperties]]:
        """Create a new ``Exercise`` instruction-set node."""
        ...

    async def list_exercise_instruction_sets(
        self,
    ) -> Result[list[Neo4jProperties]]:
        """List all available exercise instruction sets."""
        ...

    async def get_entries_for_path_step(
        self,
        user_uid: UserUID,
        ps_uid: str,
        limit: int,
    ) -> Result[list[Neo4jProperties]]:
        """Entries for a path step via ``Interaction`` edges."""
        ...

    async def create_goal_support_relationships(
        self, entry_uid: str, goal_uids: list[str]
    ) -> Result[int]:
        """Batch-create ``SUPPORTS_GOAL`` from an entry to goals."""
        ...


# ============================================================================
# Composed backend protocol — THE contract ``UserEntryBackend`` satisfies
# ============================================================================


@runtime_checkable
class UserEntryOperations(  # Protocol MRO — intentional
    BackendOperations["UserEntry"],
    UserEntryCrudOperations,
    UserEntryLifecycleOperations,
    UserEntryAssessmentOperations,
    UserEntryReportQueryOperations,
    UserEntryContentOperations,
    Protocol,
):
    """Full backend operations protocol for the ``UserEntry`` domain.

    Base CRUD/search/relationships inherited from
    ``BackendOperations[UserEntry]``; domain methods from the five ISP parents.

    Consumer: ``UserEntryService.__init__`` (Step 5) —
    ``backend: UserEntryOperations``.
    Implementation: ``UserEntryBackend`` (Step 4) — composes
    ``UniversalNeo4jBackend[UserEntry]`` with the five renamed mixins.
    """


# ============================================================================
# Processing dispatcher — separate, narrower contract
# ============================================================================


@runtime_checkable
class UserEntryProcessingOperations(Protocol):
    """Pipeline dispatcher for a ``UserEntry``.

    ``process`` reads ``entry.pipeline`` and routes to the matching handler
    (Deepgram transcription, LLM structuring, LLM summary, teacher review,
    or no-op). Implementation: ``UserEntryProcessingService`` (Step 5).
    """

    async def process(
        self,
        entry: UserEntry,
        instructions: dict[str, Any] | None = None,
    ) -> Result[UserEntry]:
        """Run the entry's declared pipeline; return the updated entry."""
        ...

    async def reprocess(
        self,
        entry_uid: str,
        new_instructions: dict[str, Any] | None = None,
    ) -> Result[UserEntry]:
        """Re-run the entry's pipeline, optionally with new instructions."""
        ...
