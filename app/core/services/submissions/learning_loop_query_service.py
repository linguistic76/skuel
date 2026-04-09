"""
Learning Loop Query Service
============================

Read-only queries that traverse the five-phase learning loop graph:

    PathStep → Exercise → Submission → Interaction → Report → RevisedExercise

The read-side peer of ``LearningLoopEventHandlerService`` (which handles the
event-driven write side: iteration tracking, turnaround calibration, mastery
velocity).

New learning-loop reads land here — not on ``SubmissionsSearchService``, which
is for generic cross-type submission search (by date, mood, category, text).
Keeping these concerns apart prevents generic search from accreting Cypher
that traverses Interaction/Exercise/Report edges.
"""

from core.constants import QueryLimit
from core.models.entity_types import SubmissionEntity
from core.models.enums.entity_enums import EntityType
from core.models.relationship_names import RelationshipName
from core.models.type_hints import UserUID
from core.ports import BackendOperations
from core.ports.query_types import PathStepSubmissionRow
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger("skuel.services.submissions.learning_loop_query")


class LearningLoopQueryService:
    """Read-side queries for the five-phase learning loop.

    Thin Cypher wrapper — no BaseService/DomainConfig. Owns queries whose
    intent is the learning loop graph, not generic submission search.

    Current queries:
    - get_submissions_for_path_step: submissions + report status for a PS,
      discovered via Interaction edges.
    """

    def __init__(
        self,
        submissions_backend: BackendOperations[SubmissionEntity],
    ) -> None:
        """Initialize learning loop query service.

        Args:
            submissions_backend: Backend for submission storage (shared with
                SubmissionsSearchService — queries all target Entity nodes).
        """
        self.backend = submissions_backend
        self.logger = logger

    @with_error_handling("get_submissions_for_path_step")
    async def get_submissions_for_path_step(
        self,
        user_uid: UserUID,
        ps_uid: str,
        limit: int = QueryLimit.COMPREHENSIVE,
    ) -> Result[list[PathStepSubmissionRow]]:
        """Get a user's submissions that occurred during a specific PathStep.

        Discovers submissions via Interaction relationships:
            (user)-[:OWNS]->(sub)-[:RECORDS]<-(interaction)-[:INTERACTION_DURING]->(ps)

        Returns submissions enriched with exercise title and report status,
        used by the PathStep detail page's learning loop sections.

        Args:
            user_uid: Owner of the submissions to return.
            ps_uid: PathStep UID to scope the Interaction traversal to.
            limit: Max rows to return (default `QueryLimit.COMPREHENSIVE`). Bounds the
                result set so a learner with hundreds of submissions on one
                PathStep can't unbounded-load the detail page.
        """
        query = f"""
        MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(sub:Entity {{entity_type: $submission_type}})
        MATCH (i:Entity:Interaction)-[:{RelationshipName.RECORDS.value}]->(sub)
        MATCH (i)-[:{RelationshipName.INTERACTION_DURING.value}]->(ps:Entity {{uid: $ps_uid}})
        OPTIONAL MATCH (sub)-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(ex:Entity)
        OPTIONAL MATCH (report:Entity)-[:{RelationshipName.REPORT_FOR.value}]->(sub)
        RETURN sub.uid AS uid, sub.title AS title, sub.status AS status,
               sub.created_at AS created_at,
               ex.uid AS exercise_uid, ex.title AS exercise_title,
               report.uid AS report_uid,
               report.assessment_outcome AS report_outcome
        ORDER BY sub.created_at DESC
        LIMIT $limit
        """

        result = await self.backend.execute_query(
            query,
            {
                "user_uid": user_uid,
                "ps_uid": ps_uid,
                "submission_type": EntityType.EXERCISE_SUBMISSION.value,
                "limit": limit,
            },
        )
        if result.is_error:
            return Result.fail(result)

        return Result.ok(
            [
                PathStepSubmissionRow(
                    uid=record["uid"],
                    title=record.get("title"),
                    status=record.get("status"),
                    created_at=record.get("created_at"),
                    exercise_uid=record.get("exercise_uid"),
                    exercise_title=record.get("exercise_title"),
                    report_uid=record.get("report_uid"),
                    report_outcome=record.get("report_outcome"),
                )
                for record in result.value or []
            ]
        )
