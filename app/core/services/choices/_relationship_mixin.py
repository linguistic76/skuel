"""
Relationship Mixin — ChoicesService
=====================================

Cross-domain graph relationship creation and semantic connections.

Part of choices_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
    from core.models.choice.choice import Choice


class _RelationshipMixin:
    """
    Cross-domain graph relationship creation for ChoicesService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by ChoicesService.__init__
    relationships: Any

    async def link_choice_to_goal(
        self, choice_uid: str, goal_uid: str, contribution_score: float = 0.5
    ) -> Result[bool]:
        """Link choice to goal it supports/advances."""
        return await self.relationships.link_to_goal(
            choice_uid, goal_uid, contribution_score=contribution_score
        )

    async def link_choice_to_habit(
        self, choice_uid: str, habit_uid: str, reinforcement_strength: float = 0.5
    ) -> Result[bool]:
        """Link choice to habit it reinforces/weakens."""
        properties = {"reinforcement_strength": reinforcement_strength}
        return await self.relationships.create_relationship(
            "habits", choice_uid, habit_uid, properties
        )

    async def link_choice_to_principle(
        self, choice_uid: str, principle_uid: str, alignment_score: float = 0.5
    ) -> Result[bool]:
        """Link choice to principle it aligns with."""
        return await self.relationships.link_to_principle(
            choice_uid, principle_uid, alignment_score=alignment_score
        )

    async def create_semantic_choice_relationship(
        self,
        choice_uid: str,
        related_uid: str,
        semantic_type: SemanticRelationshipType,
        confidence: float = 0.9,
        notes: str | None = None,
    ) -> Result[dict[str, Any]]:
        """Create semantic relationship for choice (to principle, knowledge, or goal)."""
        return await self.relationships.create_semantic_relationship(
            choice_uid, related_uid, semantic_type, confidence, notes
        )

    async def find_choices_aligned_with_principle(
        self, principle_uid: str, min_confidence: float = 0.8
    ) -> Result[list[Choice]]:
        """Find choices aligned with specific principle."""
        return await self.relationships.find_by_semantic_filter(
            target_uid=principle_uid, min_confidence=min_confidence, direction="incoming"
        )
