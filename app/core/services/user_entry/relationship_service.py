"""
UserEntry Relationship Service — ADR-054 Commit 6a
===================================================

Creates graph relationships for ``UserEntry`` nodes. Ported from
``SubmissionsRelationshipService`` unchanged — the underlying edge wiring
(``FOLLOWS``, ``RELATED_TO``, ``SUPPORTS_GOAL``) is label-agnostic and
works identically against ``:Entity`` regardless of subtype.

Relationships created:
    1. FOLLOWS       → previous user entry of same type (temporal)
    2. RELATED_TO    → user entries with shared topics (thematic)
    3. SUPPORTS_GOAL → goals mentioned in processed content (goal progress)
"""

from core.models.type_hints import UserUID
from core.models.user_entry.user_entry import UserEntry
from core.ports.user_entry_protocols import UserEntryOperations
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.neo4j_mapper import coerce_int
from core.utils.result_simplified import Errors, Result


class UserEntryRelationshipService:
    """Create graph relationships on ``UserEntry`` nodes."""

    def __init__(self, backend: UserEntryOperations) -> None:
        self.backend = backend
        self.logger = get_logger("skuel.services.user_entry.relationship")

    async def create_submission_relationships(
        self,
        entity: UserEntry,
        themes: list[str] | None = None,
        active_goals: list[dict[str, str]] | None = None,
    ) -> Result[dict[str, int]]:
        """Create graph relationships for a user entry.

        Kept method name ``create_submission_relationships`` so callers
        inside the intelligence + zpd wiring stay source-compatible.
        """
        relationships_created = {"temporal": 0, "thematic": 0, "goal_support": 0}

        try:
            temporal_result = await self._create_temporal_relationship(
                entity.uid,
                entity.user_uid,
                entity.entity_type.value,
            )
            relationships_created["temporal"] = temporal_result

            if themes:
                thematic_result = await self._create_thematic_relationships(
                    entity.uid,
                    entity.user_uid,
                    themes,
                )
                relationships_created["thematic"] = thematic_result

            processed_content = getattr(entity, "processed_content", None)
            if active_goals and processed_content:
                goal_result = await self._create_goal_relationships(
                    entity.uid, processed_content, active_goals
                )
                relationships_created["goal_support"] = goal_result

            self.logger.info(
                f"Created user_entry relationships: {relationships_created['temporal']} temporal, "
                f"{relationships_created['thematic']} thematic, "
                f"{relationships_created['goal_support']} goal_support"
            )

            return Result.ok(relationships_created)

        except NEO4J_EXCEPTIONS as e:
            return Result.fail(
                Errors.database(
                    operation="create_user_entry_relationships",
                    message=f"Failed to create relationships: {e!s}",
                )
            )

    async def _create_temporal_relationship(
        self, entry_uid: str, user_uid: UserUID | None, entity_type: str
    ) -> int:
        if not user_uid:
            return 0

        result = await self.backend.create_temporal_relationship(entry_uid, user_uid, entity_type)
        if result.is_error:
            return 0
        records = result.value or []
        return coerce_int(records[0]["count"]) if records else 0

    async def _create_thematic_relationships(
        self,
        entry_uid: str,
        user_uid: UserUID | None,
        themes: list[str],
    ) -> int:
        if not themes or not user_uid:
            return 0

        result = await self.backend.create_thematic_relationships(
            entry_uid, user_uid, themes, ", ".join(themes[:3])
        )
        if result.is_error:
            return 0
        records = result.value or []
        return coerce_int(records[0]["count"]) if records else 0

    async def _create_goal_relationships(
        self,
        entry_uid: str,
        processed_content: str,
        active_goals: list[dict[str, str]],
    ) -> int:
        content_lower = processed_content.lower()
        mentioned_goal_uids = []

        for goal in active_goals:
            goal_title_lower = goal["title"].lower()
            if goal_title_lower in content_lower:
                mentioned_goal_uids.append(goal["uid"])

        if not mentioned_goal_uids:
            return 0

        result = await self.backend.create_goal_support_relationships(
            entry_uid, mentioned_goal_uids
        )
        return result.value if result.is_ok else 0

    async def get_related_submissions(self, entry_uid: str) -> Result[list[str]]:
        """Return UIDs of user entries related via ``RELATED_TO``.

        Method name preserved for source compatibility with the
        intelligence layer.
        """
        result = await self.backend.get_related_entry_uids(entry_uid)
        if result.is_error:
            return Result.fail(result)

        return Result.ok([str(r["uid"]) for r in (result.value or []) if r["uid"]])

    async def get_supported_goals(self, entry_uid: str) -> Result[list[str]]:
        """Return UIDs of goals supported via ``SUPPORTS_GOAL``."""
        result = await self.backend.get_supported_goal_uids(entry_uid)
        if result.is_error:
            return Result.fail(result)

        return Result.ok([str(r["uid"]) for r in (result.value or []) if r["uid"]])

    async def get_submission_summary(self, entry_uid: str) -> Result[dict[str, int]]:
        """Return comprehensive relationship counts for a user entry."""
        result = await self.backend.get_entry_relationship_summary(entry_uid)
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
                "related_ku_count": coerce_int(record["related_count"]),
                "supported_goal_count": coerce_int(record["goal_count"]),
                "follows_count": coerce_int(record["follows_count"]),
            }
        )
