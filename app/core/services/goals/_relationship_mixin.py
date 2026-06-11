"""
Relationship Mixin — GoalsService
====================================

Cross-domain graph relationship creation and semantic connections.

Part of goals_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.type_hints import UserUID
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
    from core.models.goal.goal import Goal


class _RelationshipMixin:
    """
    Cross-domain graph relationship creation for GoalsService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by GoalsService.__init__
    relationships: Any
    logger: Any

    async def create_user_goal_relationship(
        self, user_uid: UserUID, goal_uid: str, role: str = "owner"
    ) -> Result[bool]:
        """Create User->Goal relationship in graph."""
        properties = {"role": role} if role != "owner" else None
        return await self.relationships.create_user_relationship(user_uid, goal_uid, properties)

    async def link_goal_to_habit(
        self,
        goal_uid: str,
        habit_uid: str,
        weight: float = 1.0,
        essentiality: str = "supporting",
    ) -> Result[bool]:
        """Link goal to supporting habit, tagged with its essentiality tier.

        Writes ``(Habit)-[:SUPPORTS_GOAL {weight, essentiality}]->(Goal)``. The
        ``essentiality`` property (``essential`` / ``critical`` / ``supporting`` /
        ``optional``) is THE single source for the GOAPS_CONFIG tier buckets
        (``essential_habits`` / ``critical_habits`` / ``optional_habits``, with the
        ``supporting`` and unset cases falling to the ``contributing_habits`` catch-all).
        It MUST match the read mappings' ``filter_property="essentiality"`` — storing the
        tier under any other key (the former ``contribution_type``) left every tier empty.
        """
        properties = {"weight": weight, "essentiality": essentiality}
        return await self.relationships.create_relationship(
            "supporting_habits", goal_uid, habit_uid, properties
        )

    async def unlink_goal_from_habit(self, uid: str, habit_uid: str) -> Result[bool]:
        """Unlink a habit from a goal. Delegates to UnifiedRelationshipService."""
        return await self.relationships.delete_relationship("supporting_habits", uid, habit_uid)

    async def link_goal_to_knowledge(
        self,
        goal_uid: str,
        knowledge_uid: str,
        proficiency_required: str = "intermediate",
        priority: int = 1,
    ) -> Result[bool]:
        """Link goal to required knowledge/skill (``REQUIRES_KNOWLEDGE``)."""
        return await self.relationships.create_relationship(
            "knowledge",
            goal_uid,
            knowledge_uid,
            {"proficiency_required": proficiency_required, "priority": priority},
        )

    async def link_goal_to_principle(
        self, goal_uid: str, principle_uid: str, alignment_strength: float = 1.0
    ) -> Result[bool]:
        """Link goal to guiding principle/value (``GUIDED_BY_PRINCIPLE``)."""
        return await self.relationships.create_relationship(
            "principles", goal_uid, principle_uid, {"alignment_strength": alignment_strength}
        )

    async def create_semantic_goal_relationship(
        self,
        goal_uid: str,
        knowledge_uid: str,
        semantic_type: SemanticRelationshipType,
        confidence: float = 0.9,
        notes: str | None = None,
    ) -> Result[dict[str, Any]]:
        """Create semantic relationship between goal and knowledge."""
        return await self.relationships.create_semantic_relationship(
            goal_uid, knowledge_uid, semantic_type, confidence, notes
        )

    async def find_goals_requiring_knowledge(
        self, knowledge_uid: str, min_confidence: float = 0.8
    ) -> Result[list[Goal]]:
        """Find goals that require specific knowledge."""
        return await self.relationships.find_by_semantic_filter(
            target_uid=knowledge_uid, min_confidence=min_confidence, direction="incoming"
        )
