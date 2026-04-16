"""
Submission Relationship Service
================================

Creates graph relationships for Submission entity nodes.

In the graph, Submissions are Entities (entity_type=submission/journal). This service
creates the relationships that connect a Submission to its context:

Relationships Created:
1. FOLLOWS -> Previous Submission of same type (temporal continuity)
2. RELATED_TO -> Submissions with shared topics (thematic connections)
3. SUPPORTS_GOAL -> Goals mentioned in submission content (goal progress tracking)
"""

from typing import TYPE_CHECKING, Any

from core.models.entity_types import SubmissionEntity
from core.models.type_hints import UserUID
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports import BackendOperations


class SubmissionsRelationshipService:
    """Service for creating graph relationships on Entity nodes."""

    def __init__(self, backend: "BackendOperations[Any]") -> None:
        """
        Initialize Ku relationship service.

        Args:
            backend: BackendOperations for database access (REQUIRED)
        """
        self.backend = backend
        self.logger = get_logger("skuel.services.ku_relationship")

    # ========================================================================
    # RELATIONSHIP CREATION
    # ========================================================================

    async def create_submission_relationships(
        self,
        entity: SubmissionEntity,
        themes: list[str] | None = None,
        active_goals: list[dict[str, str]] | None = None,
    ) -> Result[dict[str, int]]:
        """
        Create graph relationships for a submission entity.

        Args:
            entity: The newly created/updated submission entity
            themes: Optional list of themes for thematic relationships
            active_goals: Optional list of active goals for goal-support relationships

        Returns:
            Result containing counts of relationships created
        """
        relationships_created = {"temporal": 0, "thematic": 0, "goal_support": 0}

        try:
            # 1. Temporal Relationship: FOLLOWS (previous submission of same type)
            temporal_result = await self._create_temporal_relationship(
                entity.uid,
                entity.user_uid,
                entity.entity_type.value,
            )
            relationships_created["temporal"] = temporal_result

            # 2. Thematic Relationships: RELATED_TO (shared topics)
            if themes:
                thematic_result = await self._create_thematic_relationships(
                    entity.uid,
                    entity.user_uid,
                    themes,
                )
                relationships_created["thematic"] = thematic_result

            # 3. Goal Support Relationships: SUPPORTS_GOAL
            processed_content = getattr(entity, "processed_content", None)
            if active_goals and processed_content:
                goal_result = await self._create_goal_relationships(
                    entity.uid, processed_content, active_goals
                )
                relationships_created["goal_support"] = goal_result

            self.logger.info(
                f"Created submission relationships: {relationships_created['temporal']} temporal, "
                f"{relationships_created['thematic']} thematic, {relationships_created['goal_support']} goal_support"
            )

            return Result.ok(relationships_created)

        except NEO4J_EXCEPTIONS as e:
            return Result.fail(
                Errors.database(
                    operation="create_submission_relationships",
                    message=f"Failed to create relationships: {e!s}",
                )
            )

    # ========================================================================
    # TEMPORAL RELATIONSHIPS
    # ========================================================================

    async def _create_temporal_relationship(
        self, submission_uid: str, user_uid: UserUID | None, entity_type: str
    ) -> int:
        """
        Create FOLLOWS relationship to most recent previous submission of same type.

        Args:
            submission_uid: UID of the new submission
            user_uid: User identifier (None for curriculum)
            entity_type: Entity type for filtering

        Returns:
            Count of relationships created (0 or 1)
        """
        if not user_uid:
            return 0  # CURRICULUM entities don't have temporal chains per user

        result = await self.backend.create_temporal_relationship(  # type: ignore[attr-defined]
            submission_uid, user_uid, entity_type
        )
        if result.is_error:
            return 0
        records = result.value or []
        return records[0]["count"] if records else 0

    # ========================================================================
    # THEMATIC RELATIONSHIPS
    # ========================================================================

    async def _create_thematic_relationships(
        self,
        submission_uid: str,
        user_uid: UserUID | None,
        themes: list[str],
    ) -> int:
        """
        Create RELATED_TO relationships for submissions sharing topics.

        Args:
            submission_uid: UID of the new submission
            user_uid: User identifier
            themes: List of themes to match

        Returns:
            Count of relationships created
        """
        if not themes or not user_uid:
            return 0

        result = await self.backend.create_thematic_relationships(  # type: ignore[attr-defined]
            submission_uid, user_uid, themes, ", ".join(themes[:3])
        )
        if result.is_error:
            return 0
        records = result.value or []
        return records[0]["count"] if records else 0

    # ========================================================================
    # GOAL RELATIONSHIPS
    # ========================================================================

    async def _create_goal_relationships(
        self,
        submission_uid: str,
        processed_content: str,
        active_goals: list[dict[str, str]],
    ) -> int:
        """
        Create SUPPORTS_GOAL relationships for mentioned goals.

        Args:
            submission_uid: UID of the submission
            processed_content: Processed submission content
            active_goals: List of active goals from context

        Returns:
            Count of relationships created
        """
        content_lower = processed_content.lower()
        mentioned_goal_uids = []

        for goal in active_goals:
            goal_title_lower = goal["title"].lower()
            if goal_title_lower in content_lower:
                mentioned_goal_uids.append(goal["uid"])

        if not mentioned_goal_uids:
            return 0

        result = await self.backend.create_goal_support_relationships(  # type: ignore[attr-defined]
            submission_uid, mentioned_goal_uids
        )
        return result.value if result.is_ok else 0

    # ========================================================================
    # RELATIONSHIP QUERIES
    # ========================================================================

    async def get_related_submissions(self, submission_uid: str) -> Result[list[str]]:
        """
        Get UIDs of submissions related to this one.

        Graph relationship: (submission)-[:RELATED_TO]->(submission)

        Args:
            submission_uid: UID of the submission entity

        Returns:
            Result containing list of related submission UIDs
        """
        result = await self.backend.get_related_submission_uids(submission_uid)  # type: ignore[attr-defined]
        if result.is_error:
            return Result.fail(result)

        return Result.ok([r["uid"] for r in (result.value or []) if r["uid"]])

    async def get_supported_goals(self, submission_uid: str) -> Result[list[str]]:
        """
        Get UIDs of goals supported by this submission.

        Graph relationship: (submission)-[:SUPPORTS_GOAL]->(goal)

        Args:
            submission_uid: UID of the submission

        Returns:
            Result containing list of supported goal UIDs
        """
        result = await self.backend.get_supported_goal_uids(submission_uid)  # type: ignore[attr-defined]
        if result.is_error:
            return Result.fail(result)

        return Result.ok([r["uid"] for r in (result.value or []) if r["uid"]])

    async def get_submission_summary(self, submission_uid: str) -> Result[dict[str, int]]:
        """
        Get comprehensive relationship summary for a submission entity.

        Returns counts for all relationship types (RELATED_TO, SUPPORTS_GOAL, FOLLOWS).

        Args:
            submission_uid: UID of the submission entity

        Returns:
            Result containing dict with relationship counts
        """
        result = await self.backend.get_submission_relationship_summary(submission_uid)  # type: ignore[attr-defined]
        if result.is_error:
            return Result.fail(result)

        records = result.value or []
        if not records:
            return Result.ok(
                {
                    "related_ku_count": 0,
                    "supported_goal_count": 0,
                    "follows_count": 0,
                }
            )

        record = records[0]
        return Result.ok(
            {
                "related_ku_count": record["related_count"],
                "supported_goal_count": record["goal_count"],
                "follows_count": record["follows_count"],
            }
        )
