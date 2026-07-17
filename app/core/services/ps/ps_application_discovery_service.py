"""
Path Step Application Discovery Service - Reverse Relationship Queries
=======================================================================

Answers "where is this path step applied/required/reinforced?" by querying
reverse relationships from activity domains back to path steps.

Generic method `find_activities_connected_to_knowledge()` handles all 6 activity
domains. Thin wrappers preserve the existing API for callers.

2 curriculum methods (Learning Steps, Learning Paths) remain separate as they
don't follow the same user-owned activity pattern.

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from typing import Any

from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName
from core.models.type_hints import UserUID
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result


class PsApplicationDiscoveryService:
    """
    Reverse relationship queries for path step application discovery.

    These methods answer "where is this path step being used?" by traversing
    graph relationships from activity domains back to path steps.
    """

    def __init__(self, repo: Any = None) -> None:
        """
        Initialize with backend.

        Args:
            repo: Backend for path step operations
        """
        if not repo:
            raise ValueError("KU repository is required")

        self.repo = repo
        self.logger = get_logger("skuel.services.ps.application_discovery")

    async def _verify_ku_exists(self, ku_uid: str) -> Result[None]:
        """Verify path step exists, returning NotFound error if not."""
        ku_result = await self.repo.get(ku_uid)
        if not ku_result.is_ok or not ku_result.value:
            return Result.fail(Errors.not_found(f"Path step {ku_uid} not found"))
        return Result.ok(None)

    # ========================================================================
    # GENERIC ACTIVITY DISCOVERY
    # ========================================================================

    @with_error_handling(
        "find_activities_connected_to_knowledge", error_type="database", uid_param="ku_uid"
    )
    async def find_activities_connected_to_knowledge(
        self,
        ku_uid: str,
        user_uid: UserUID,
        node_label: NeoLabel,
        relationship_types: list[str],
        filters: dict[str, Any] | None = None,
        order_by: str = "created_at",
        limit: int = 10,
        reverse_direction: bool = False,
    ) -> Result[list[str]]:
        """
        Find activity entities connected to a path step via graph relationships.

        Generic method that replaces 6 structurally identical per-domain methods.

        Args:
            ku_uid: Path step UID
            user_uid: User UID to filter activities
            node_label: Neo4j node label (e.g., "Task", "Goal", "Habit")
            relationship_types: Relationship types to traverse (e.g., ["APPLIES_KNOWLEDGE"])
            filters: Optional domain-specific conditions as {cypher_fragment: params_dict}
                     e.g., {"n.status = $status_filter": {"status_filter": "active"}}
            order_by: Property to order results by (default "created_at")
            limit: Maximum results to return (default 10)
            reverse_direction: If True, use (n)<-[:REL]-(ku) instead of (n)-[:REL]->(ku)

        Returns:
            Result containing list of entity UIDs
        """
        verify = await self._verify_ku_exists(ku_uid)
        if verify.is_error:
            return Result.fail(verify)

        self.logger.debug(
            f"Finding {node_label} entities connected to path step {ku_uid} "
            f"via {'|'.join(relationship_types)} (user={user_uid})"
        )

        results = await self.repo.find_connected_activities(
            ku_uid=ku_uid,
            user_uid=user_uid,
            node_label=node_label,
            rel_types=relationship_types,
            filters=filters,
            order_by=order_by,
            limit=limit,
            reverse_direction=reverse_direction,
        )

        if results.is_error:
            return Result.fail(results)

        entity_uids = [record["entity_uid"] for record in results.value if record.get("entity_uid")]

        self.logger.debug(
            f"Found {len(entity_uids)} {node_label} entities connected to path step {ku_uid}"
        )
        return Result.ok(entity_uids)

    # ========================================================================
    # ACTIVITY DOMAIN WRAPPERS (delegate to generic method)
    # ========================================================================

    async def find_events_applying_knowledge(
        self, ku_uid: str, user_uid: UserUID, upcoming_only: bool = True
    ) -> Result[list[str]]:
        """Find events that apply or reinforce this path step."""
        filters: dict[str, Any] | None = None
        if upcoming_only:
            filters = {"n.start_time >= datetime()": {}}
        return await self.find_activities_connected_to_knowledge(
            ku_uid=ku_uid,
            user_uid=user_uid,
            node_label=NeoLabel.EVENT,
            relationship_types=[
                RelationshipName.APPLIES_KNOWLEDGE.value,
                RelationshipName.REINFORCES_KNOWLEDGE.value,
            ],
            filters=filters,
            order_by="start_time",
        )

    async def find_habits_reinforcing_knowledge(
        self, ku_uid: str, user_uid: UserUID, only_active: bool = True
    ) -> Result[list[str]]:
        """Find habits that reinforce this path step."""
        filters: dict[str, Any] | None = None
        if only_active:
            filters = {"n.status = $status_val": {"status_val": "active"}}
        return await self.find_activities_connected_to_knowledge(
            ku_uid=ku_uid,
            user_uid=user_uid,
            node_label=NeoLabel.HABIT,
            relationship_types=[RelationshipName.REINFORCES_KNOWLEDGE.value],
            filters=filters,
            order_by="created_at",
        )

    async def find_tasks_applying_knowledge(
        self, ku_uid: str, user_uid: UserUID, status_filter: str | None = None
    ) -> Result[list[str]]:
        """Find tasks that apply this path step."""
        filters: dict[str, Any] | None = None
        if status_filter:
            filters = {"n.status = $status_val": {"status_val": status_filter}}
        return await self.find_activities_connected_to_knowledge(
            ku_uid=ku_uid,
            user_uid=user_uid,
            node_label=NeoLabel.TASK,
            relationship_types=[RelationshipName.APPLIES_KNOWLEDGE.value],
            filters=filters,
            order_by="due_date",
        )

    async def find_goals_requiring_knowledge(
        self, ku_uid: str, user_uid: UserUID, status_filter: str | None = None
    ) -> Result[list[str]]:
        """Find goals that require this path step."""
        filters: dict[str, Any] | None = None
        if status_filter:
            filters = {"n.status = $status_val": {"status_val": status_filter}}
        return await self.find_activities_connected_to_knowledge(
            ku_uid=ku_uid,
            user_uid=user_uid,
            node_label=NeoLabel.GOAL,
            relationship_types=[RelationshipName.REQUIRES_KNOWLEDGE.value],
            filters=filters,
            order_by="target_date",
        )

    async def find_choices_informed_by_knowledge(
        self, ku_uid: str, user_uid: UserUID, pending_only: bool = False
    ) -> Result[list[str]]:
        """Find choices informed by this path step."""
        filters: dict[str, Any] | None = None
        if pending_only:
            filters = {"n.status IN ['pending', 'active']": {}}
        return await self.find_activities_connected_to_knowledge(
            ku_uid=ku_uid,
            user_uid=user_uid,
            node_label=NeoLabel.CHOICE,
            relationship_types=[RelationshipName.INFORMS_CHOICE.value],
            filters=filters,
            order_by="created_at",
            reverse_direction=True,
        )

    async def find_principles_embodying_knowledge(
        self, ku_uid: str, user_uid: UserUID, only_active: bool = True
    ) -> Result[list[str]]:
        """Find principles that embody/reinforce this path step."""
        filters: dict[str, Any] | None = None
        if only_active:
            filters = {"n.is_active = true": {}}
        return await self.find_activities_connected_to_knowledge(
            ku_uid=ku_uid,
            user_uid=user_uid,
            node_label=NeoLabel.PRINCIPLE,
            relationship_types=[RelationshipName.REINFORCES_KNOWLEDGE.value],
            filters=filters,
            order_by="strength",
        )

    # ========================================================================
    # CURRICULUM DISCOVERY (non-activity, no user_uid)
    # ========================================================================

    @with_error_handling("find_path_steps_containing", error_type="database", uid_param="ku_uid")
    async def find_path_steps_containing(self, ku_uid: str, limit: int = 10) -> Result[list[str]]:
        """
        Find path steps that contain/teach this path step.

        Graph Pattern: (Ls)-[:CONTAINS_KNOWLEDGE]->(Ku)
        """
        verify = await self._verify_ku_exists(ku_uid)
        if verify.is_error:
            return Result.fail(verify)

        self.logger.debug(f"Finding path steps containing path step {ku_uid} (limit={limit})")

        results = await self.repo.find_path_steps_containing_ku(ku_uid, limit)

        if results.is_error:
            return Result.fail(results)

        step_uids = [record["step_uid"] for record in results.value if record.get("step_uid")]

        self.logger.debug(f"Found {len(step_uids)} path steps containing path step {ku_uid}")
        return Result.ok(step_uids)

    @with_error_handling("find_learning_paths_teaching", error_type="database", uid_param="ku_uid")
    async def find_learning_paths_teaching(self, ku_uid: str, limit: int = 10) -> Result[list[str]]:
        """
        Find learning paths that teach this path step (via path steps).

        Graph Pattern: (Lp)-[:HAS_STEP]->(Ls)-[:CONTAINS_KNOWLEDGE]->(Ku)
        """
        verify = await self._verify_ku_exists(ku_uid)
        if verify.is_error:
            return Result.fail(verify)

        self.logger.debug(f"Finding learning paths teaching path step {ku_uid} (limit={limit})")

        results = await self.repo.find_learning_paths_teaching_ku(ku_uid, limit)

        if results.is_error:
            return Result.fail(results)

        path_uids = [record["path_uid"] for record in results.value if record.get("path_uid")]

        self.logger.debug(f"Found {len(path_uids)} learning paths teaching path step {ku_uid}")
        return Result.ok(path_uids)
