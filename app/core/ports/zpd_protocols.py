"""
ZPD Protocols
=============

Protocol interfaces for the Zone of Proximal Development subsystem.

- ZPDBackendOperations: Persistence layer — Cypher queries against Neo4j.
- ZPDOperations: Service layer — business logic consumed by Askesis + UserContext.

See: core/services/zpd/zpd_service.py — service implementation
See: adapters/persistence/neo4j/zpd_backend.py — backend implementation
See: docs/roadmap/zpd-service-architecture.md — design rationale
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypedDict, runtime_checkable

from core.models.type_hints import UserUID

if TYPE_CHECKING:
    from core.models.zpd.zpd_assessment import ZoneEvidence, ZPDAssessment
    from core.services.user.unified_user_context import UserContext
    from core.utils.result_simplified import Result


class PrereqCount(TypedDict):
    """Per-proximal-KU prerequisite count summary.

    Emitted by the zone-data Cypher's prerequisite aggregation step:
    for each KU in the proximal zone, the total number of prerequisites
    and how many of them the user has already engaged. Drives the
    readiness score (``met / total``).
    """

    ku_uid: str
    total: int
    met: int


class SubmissionScore(TypedDict):
    """Per-KU best submission score from completed exercise submissions.

    Emitted by the zone-data and targeted-engagement Cyphers' submission
    aggregation step. ``best_score`` is the max across all
    completed/approved submissions for the KU's applying exercises;
    ``count`` is the number of submissions in that aggregate. KUs with no
    submissions do not appear in the list.
    """

    ku_uid: str
    best_score: float
    count: int


@runtime_checkable
class ZPDBackendOperations(Protocol):
    """Persistence protocol for ZPD graph queries.

    Implemented by: adapters/persistence/neo4j/zpd_backend.py
    Consumed by: ZPDService
    """

    async def get_ku_count(self) -> int:
        """Count total KUs in the curriculum graph."""
        ...

    async def get_targeted_ku_engagement(
        self, user_uid: UserUID, ku_uids: list[str]
    ) -> Result[tuple[list[str], list[str], list[str], list[SubmissionScore]]]:
        """Fetch engagement data for specific KU UIDs only.

        Lightweight alternative to get_zone_data() for query-time ZPD.

        Returns:
            Result containing a tuple of:
                - task_engaged: KU UIDs engaged via tasks
                - habit_engaged: KU UIDs engaged via habits
                - entry_engaged: KU UIDs engaged via user entries (ADR-069)
                - submission_data: Submission scores per KU
        """
        ...

    async def get_zone_data(
        self, user_uid: UserUID
    ) -> Result[
        tuple[
            list[str],
            list[str],
            list[str],
            list[PrereqCount],
            list[str],
            list[str],
            list[str],
            list[str],
            list[SubmissionScore],
        ]
    ]:
        """Execute the zone traversal query and return parsed results.

        Returns:
            Result containing a tuple of:
                - current_zone: KU UIDs the user has engaged
                - proximal_zone: Adjacent KU UIDs not yet engaged
                - engaged_paths: Learning Path UIDs the user is on
                - prereq_data: Raw prerequisite counts per proximal KU
                - blocking_gaps: Prerequisite KU UIDs not yet met
                - task_engaged: KU UIDs engaged via tasks
                - habit_engaged: KU UIDs engaged via habits
                - entry_engaged: KU UIDs engaged via user entries (ADR-069)
                - submission_data: Submission scores per KU
        """
        ...


@runtime_checkable
class ZPDOperations(Protocol):
    """Pedagogical gravity well protocol for Zone of Proximal Development.

    ZPDService implements this protocol. It is stateless — every call
    traverses the live Neo4j curriculum graph. No ZPD state is stored.

    When an optional UserContext is passed, ZPD enriches the assessment
    with life path alignment, zone evidence, and recommended actions.

    Consumed by:
    - UserContextBuilder.build_rich() — capstone computation
    - UserContextIntelligence.get_optimal_next_path_steps()
    - AskesisService.analyze_user_state() — ZPDAssessment in state snapshot
    """

    async def assess_zone(
        self, user_uid: UserUID, context: UserContext | None = None
    ) -> Result[ZPDAssessment]:
        """Compute the user's full ZPD from the curriculum graph.

        2-hop traversal: current zone → proximal zone → readiness scores.
        Returns an empty ZPDAssessment (not an error) when the curriculum
        graph has fewer than 3 KUs.

        When context is provided, enriches the assessment with:
        - life_path_alignment and life_path_uid
        - zone_evidence (compound mastery tracking)
        - recommended_actions (concrete next steps)
        - submission_scores (from exercise submissions)

        Args:
            user_uid: User's unique identifier (e.g. "user_alice")
            context: Optional UserContext for life path + evidence enrichment.

        Returns:
            Result[ZPDAssessment]: Full ZPD snapshot including current zone,
                proximal zone, readiness scores, blocking gaps, behavioral
                readiness, and (when context provided) life path integration.
        """
        ...

    async def get_proximal_ku_uids(self, user_uid: UserUID) -> Result[list[str]]:
        """Get only the proximal zone KU UIDs for lightweight callers.

        Convenience wrapper over assess_zone() that extracts just the
        proximal_zone list. Use when only the candidate KU list is needed
        and the full ZPDAssessment is not required.

        Args:
            user_uid: User's unique identifier

        Returns:
            Result[list[str]]: ku_uids in the user's proximal zone,
                ordered by readiness score descending.
        """
        ...

    async def get_readiness_score(self, user_uid: UserUID, ku_uid: str) -> Result[float]:
        """Get the readiness score for a specific KU.

        Calls assess_zone() and extracts the score for the given KU.
        Returns 0.0 for KUs not in the proximal zone.

        Args:
            user_uid: User's unique identifier
            ku_uid: Knowledge Unit to score

        Returns:
            Result[float]: Readiness score 0.0-1.0. 1.0 means all
                prerequisites are met; 0.0 means none are.
        """
        ...

    async def assess_ku_readiness(
        self, user_uid: UserUID, ku_uids: list[str]
    ) -> Result[dict[str, ZoneEvidence]]:
        """Get targeted ZPD evidence for specific KUs.

        Lightweight alternative to assess_zone() — queries engagement data
        for just the specified KUs. Returns ZoneEvidence per KU. Same data
        shape as zone_evidence in ZPDAssessment, narrower query.

        Used by the Socratic pipeline to assess readiness for KUs mentioned
        in a question without computing the full ZPD assessment.

        Args:
            user_uid: User's unique identifier
            ku_uids: KU UIDs to assess

        Returns:
            Result[dict[str, ZoneEvidence]]: Per-KU engagement evidence.
                KUs with no engagement get a default ZoneEvidence (all zeros).
        """
        ...


@runtime_checkable
class ZPDSnapshotOperations(Protocol):
    """Persistence protocol for ZPD assessment snapshot writes.

    Implemented by ``adapters.persistence.neo4j.zpd_snapshot_backend.ZPDSnapshotBackend``.
    Consumed by ``ZPDEventHandler`` to persist ZPD assessment snapshots when
    user events fire (submission, mastery, etc.).

    Narrow by design — the event handler only writes snapshots; reads happen
    elsewhere via ZPDOperations.
    """

    async def save_snapshot(
        self, user_uid: UserUID, assessment: ZPDAssessment, trigger_event: str
    ) -> Result[None]:
        """Keep one ZPD history record per user, refreshed with the latest assessment.

        Stores only summary fields (current/proximal/confirmed counts,
        behavioral readiness, life path alignment) plus a snapshot counter
        — no full assessment serialization. The trigger event label
        identifies what fired the snapshot.

        Returns Result.ok(None) on success; Result.fail(Errors.database(...))
        on Neo4j failure.
        """
        ...
