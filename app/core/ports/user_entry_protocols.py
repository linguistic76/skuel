"""
UserEntry Protocols — ADR-054
==============================

Backend-level, ISP-split protocols for the unified ``UserEntry`` domain.
``UserEntry`` replaces ``Submission`` / ``ExerciseSubmission`` / ``JeInput`` /
``JeOutput`` as one type of user-authored artifact. Dispatch is driven by the
``Pipeline`` enum on the entry, not by ``entity_type`` branching.

Six ISP parents mirror the six backend mixins (renamed from
``_submission_*_mixin.py`` to ``_user_entry_*_mixin.py``):

    UserEntryCrudOperations         — content search + feedback-count joins
    UserEntryLifecycleOperations    — create-with-link, FULFILLS_EXERCISE,
                                      revision resolution
    UserEntryAssessmentOperations   — teacher review queue (SHARED_WITH_GROUP),
                                      assessments, teacher dashboards
    UserEntryReportQueryOperations  — learning-loop chain queries + report
                                      cross-joins
    UserEntryContentOperations      — processing context + exercise-instruction
                                      enrichment reads
    UserEntryOrganizesOperations    — ORGANIZES child reads (emergent MOC map);
                                      the narrow slice of the shared
                                      ``_OrganizesMixin`` this domain consumes

``UserEntryOperations`` aggregates the six parents and extends
``BackendOperations[UserEntry]`` — this is the protocol that
``UserEntryBackend`` satisfies and that ``UserEntryService.__init__`` consumes.

``UserEntryProcessingOperations`` is a separate, narrower contract for the
dispatcher service — it takes a ``UserEntry`` and runs its ``Pipeline``.

See: /docs/decisions/ADR-054-user-entry-unified-submissions.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from core.models.type_hints import Neo4jProperties, UserUID
from core.ports.base_protocols import BackendOperations
from core.ports.query_types import GroundingEntryRow, GroundingRemovalRow, OrganizerResult
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.user_entry.user_entry import UserEntry


# ============================================================================
# ISP parent 1 — CRUD / content search / feedback-count joins
# ============================================================================


@runtime_checkable
class UserEntryCrudOperations(Protocol):
    """Content search + feedback-count joins for ``UserEntry`` nodes.

    Implementation: ``_UserEntryCrudMixin`` (renamed from ``_SubmissionCrudMixin``).
    """

    async def upsert(self, entry: UserEntry) -> Result[UserEntry]:
        """Create-or-update a ``UserEntry`` keyed on its caller-supplied uid.

        MERGE-on-uid: re-syncing a deterministic-uid vault note updates the
        node in place (preserving ``created_at``) instead of duplicating it.
        """
        ...

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

    async def get_latest_entry_for_exercise(
        self, user_uid: UserUID, exercise_uid: str
    ) -> Result[Neo4jProperties | None]:
        """Newest turn-in's uid + content + revision for a user+exercise pair.

        The vault submit-signal branch diffs the living file against this
        row — the copies are the last-submitted state.
        """
        ...

    async def get_teacher_feedback_state(self, teacher_uid: str) -> Result[Neo4jProperties]:
        """Read feedback EMA state from ``User`` for turnaround calibration."""
        ...

    async def update_teacher_feedback_state(
        self, teacher_uid: str, properties: Neo4jProperties
    ) -> Result[bool]:
        """Write feedback EMA state to ``User``."""
        ...

    async def get_extracted_entities_for_entry(
        self, entry_uid: str
    ) -> Result[list[dict[str, Any]]]:
        """Extracted entity UIDs + EXTRACTED_FROM edge properties for a UserEntry.

        Returns dicts with keys: entity_uid, title, labels, source_line_hash,
        vault_id. Used by VaultReconciler for outbound ID injection (ADR-070)
        and by UserEntryProcessingService for extraction dedup guards (R3).
        """
        ...

    async def update_extracted_from_vault_id(
        self, entry_uid: str, entity_uid: str, vault_id: str
    ) -> Result[bool]:
        """Set vault_id on an existing EXTRACTED_FROM edge (ADR-070 ID injection)."""
        ...

    async def get_user_active_extraction_twins(
        self, user_uid: UserUID, labels: list[str]
    ) -> Result[list[dict[str, Any]]]:
        """The user's OWNED, non-terminal entities of the given domain labels.

        Returns dicts with keys: entity_uid, title, labels — ordered oldest-first.
        Input to extraction dedup Guard 4 (cross-entry, F4).
        """
        ...


# ============================================================================
# ISP parent 2 — lifecycle: create-with-link + revision resolution
# ============================================================================


@runtime_checkable
class UserEntryLifecycleOperations(Protocol):
    """FULFILLS_EXERCISE wiring + entry-owner / group-membership reads.

    Replaces ``_SubmissionLifecycleMixin``. ``create_with_exercise_link``
    carries the revision on the edge (``FULFILLS_EXERCISE {revision}``);
    no node field.

    Implementation: ``_UserEntryLifecycleMixin``.
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


# ============================================================================
# ISP parent 3 — assessment + teacher review queue
# ============================================================================


@runtime_checkable
class UserEntryAssessmentOperations(Protocol):
    """Assessment scoring + teacher-review workflow.

    The review queue is a pure graph pattern on ``SHARED_WITH_GROUP`` +
    ``pipeline = 'teacher_review'`` — no role gate at the Cypher level.
    Route-level role checks remain authoritative for access.

    Implementation: ``_UserEntryAssessmentMixin``.
    """

    # -------- review queue --------

    async def get_review_queue_by_groups(
        self,
        teacher_uid: str,
        status_filter: list[str] | None = None,
    ) -> Result[list[Neo4jProperties]]:
        """Teacher's pending review queue via ``SHARED_WITH_GROUP``.

        Pattern:

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
        """Read ``report_file_path`` for an ``EntryReport`` node."""
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

    async def get_entries_for_exercise_review(
        self, exercise_uid: str, teacher_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Entries against an exercise shared with the requesting teacher's groups."""
        ...

    async def get_students_summary(self, teacher_uid: str) -> Result[list[Neo4jProperties]]:
        """Students who have submitted, with submission counts."""
        ...

    async def get_student_entries_for_teacher(
        self, teacher_uid: str, student_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """All entries owned by a student, gated by shared active group.

        Empty when teacher and student do not share an active group — callers
        treat as a genuinely empty per-student history (no leak of unrelated
        students' submissions).
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
        """Full entry detail for teacher review, gated by SHARED_WITH_GROUP.

        Empty when the entry is not shared with any active group the teacher
        owns — service-layer callers map empty to ``Errors.not_found`` (404).
        """
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
    """Cross-joins to ``EntryReport`` + learning-loop chain reads.

    Implementation: ``_UserEntryReportQueryMixin``.
    """

    async def get_pending_entries_raw(
        self, user_uid: UserUID, pipelines: list[str] | None = None
    ) -> Result[list[Neo4jProperties]]:
        """Entries without an incoming ``REPORT_FOR`` relationship.

        ``pipelines`` optionally narrows to entries whose ``pipeline`` is in the
        given values (e.g. journal pipelines for the response surface).
        """
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

    The processing-context read returns active goals only — ADR-054 dismantled
    the rich-journal model, so the former recent-journal/topic/mood reads were
    removed.

    Implementation: ``_UserEntryContentMixin``.
    """

    async def get_journal_processing_context(
        self, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Single-query active-goal context bundle for the enrichment pipeline."""
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

    async def get_vault_notes_for_context(
        self,
        user_uid: UserUID,
        limit: int = 8,
    ) -> Result[list[Neo4jProperties]]:
        """Vault-synced personal notes (pipeline=journal, vault_file_path in metadata)."""
        ...

    async def get_entries_for_path_step(
        self,
        user_uid: UserUID,
        ps_uid: str,
        limit: int,
    ) -> Result[list[Neo4jProperties]]:
        """Entries for a path step via ``Interaction`` edges."""
        ...

    async def get_exercise_entries_for_user(
        self,
        user_uid: UserUID,
        limit: int,
    ) -> Result[list[Neo4jProperties]]:
        """A user's exercise submissions (FULFILLS_EXERCISE edge, pipeline-agnostic)."""
        ...

    async def get_knowledge_entries_with_grounding(
        self,
        user_uid: UserUID,
        limit: int,
    ) -> Result[list[Neo4jProperties]]:
        """Knowledge-pipeline entries + their APPLIES_KNOWLEDGE chips (confidence-ordered)."""
        ...


# ============================================================================
# ISP parent 6 — ORGANIZES child reads (emergent MOC map)
# ============================================================================


@runtime_checkable
class UserEntryOrganizesOperations(Protocol):
    """ORGANIZES-children reads for user entries that act as MOCs.

    MOC is emergent identity — any entity with outgoing ORGANIZES edges. The
    vault MOC ingestion (``moc: true`` body links) draws the edges; this slice
    only reads them so /gradebook/{uid} can render the map. Deliberately
    narrow: the write half of the shared mixin stays ingestion-owned
    (``refresh_moc_organizes``).

    Implementation: ``_OrganizesMixin`` (shared with ``PsBackend``).
    """

    async def get_organized_children(
        self, parent_uid: str, limit: int | None = None
    ) -> Result[list[OrganizerResult]]:
        """Direct ORGANIZES children of an entity, ordered by position."""
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
    UserEntryOrganizesOperations,
    Protocol,
):
    """Full backend operations protocol for the ``UserEntry`` domain.

    Base CRUD/search/relationships inherited from
    ``BackendOperations[UserEntry]``; domain methods from the six ISP parents.

    Consumer: ``UserEntryService.__init__`` —
    ``backend: UserEntryOperations``.
    Implementation: ``UserEntryBackend`` — composes
    ``UniversalNeo4jBackend[UserEntry]`` with the five renamed mixins plus the
    shared ``_OrganizesMixin``.
    """


# ============================================================================
# Processing dispatcher — separate, narrower contract
# ============================================================================


@runtime_checkable
class UserEntryProcessingOperations(Protocol):
    """Pipeline dispatcher for a ``UserEntry``.

    ``process`` reads ``entry.pipeline`` and routes to the matching handler
    (Deepgram transcription, LLM structuring, LLM summary, teacher review,
    or no-op). Implementation: ``UserEntryProcessingService``.
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


# ============================================================================
# Entry→Ku grounding — standalone backend contract (Entry-Enrichment PR 3)
# ============================================================================


@runtime_checkable
class EntryGroundingBackendOperations(Protocol):
    """Persistence contract for entry→Ku grounding.

    Candidate reads + eager edge writes for ``EntryGroundingService``: which
    knowledge-pipeline entries still need a grounding pass, the provenance-
    stamped ``APPLIES_KNOWLEDGE`` write, the per-entry grounded stamp, and the
    ownership-scoped removal that records the user's rejection.

    Implementation: ``EntryGroundingBackend``
    (``adapters/persistence/neo4j/entry_grounding_backend.py``).
    """

    async def get_pending_entries(
        self, user_uid: str | None = None, force: bool = False
    ) -> Result[list[GroundingEntryRow]]:
        """Knowledge entries with an embedding whose grounding stamp is missing or stale."""
        ...

    async def write_applies_knowledge(
        self, entry_uid: str, ku_uid: str, confidence: float
    ) -> Result[bool]:
        """MERGE the inferred edge with provenance; True iff a NEW edge was created."""
        ...

    async def stamp_grounded(self, entry_uid: str, text_hash: str, version: int) -> Result[None]:
        """Mark the entry's grounding pass complete for its current embedding text."""
        ...

    async def remove_grounded_edge(
        self, entry_uid: str, ku_uid: str, user_uid: UserUID
    ) -> Result[GroundingRemovalRow | None]:
        """Ownership-scoped edge delete + rejection record; None when nothing matched."""
        ...
