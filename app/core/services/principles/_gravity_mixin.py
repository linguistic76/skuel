"""
Gravity Mixin — PrinciplesService
===================================

The gravitational pull Principles exerts — links to goals, habits, knowledge,
choices. Principles attract connections without always being visible.

Part of principles_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import Any, ClassVar

from core.services.mixins.link_edge_guard import (
    CHOICE_FAR_END,
    GOAL_FAR_END,
    HABIT_FAR_END,
    KNOWLEDGE_FAR_END,
    PRINCIPLE_FAR_END,
    LinkFarEnd,
)
from core.utils.result_simplified import Errors, Result


class _GravityMixin:
    """
    Cross-domain link methods for PrinciplesService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by PrinciplesService.__init__
    relationships: Any
    logger: Any

    # Maps a public link_type to its PRINCIPLES_CONFIG relationship method key.
    # Single source for both create_principle_link (write) and get_principle_links
    # (read) so the two can never drift to different keys. Each value must be a real
    # method_key in PRINCIPLES_CONFIG — guarded by tests/test_cross_domain_link_keys.py.
    _LINK_TYPE_MAP: ClassVar[dict[str, str]] = {
        "goal": "guided_goals",
        "habit": "inspired_habits",
        "knowledge": "knowledge",
        "principle": "supporting_principles",
        "choice": "guided_choices",
    }

    # What each link_type links to — the kind the far end must be, and the name a
    # refusal answers with. Keyed like ``_LINK_TYPE_MAP``; the pairing is guarded by
    # tests/unit/test_cross_domain_link_keys.py.
    _LINK_FAR_ENDS: ClassVar[dict[str, LinkFarEnd]] = {
        "goal": GOAL_FAR_END,
        "habit": HABIT_FAR_END,
        "knowledge": KNOWLEDGE_FAR_END,
        "principle": PRINCIPLE_FAR_END,
        "choice": CHOICE_FAR_END,
    }

    async def link_principle_to_knowledge(
        self, principle_uid: str, knowledge_uid: str, relevance: str = "fundamental"
    ) -> Result[bool]:
        """Link principle to the Ku it is grounded in (``GROUNDED_IN_KNOWLEDGE``)."""
        return await self.relationships.create_relationship(
            "knowledge",
            principle_uid,
            knowledge_uid,
            {"relevance": relevance},
            far_end=KNOWLEDGE_FAR_END,
        )

    # ========================================================================
    # PRINCIPLE LINKS — Neo4j relationships via UnifiedRelationshipService
    # ========================================================================

    async def create_principle_link(
        self,
        principle_uid: str,
        target_uid: str,
        link_type: str,
    ) -> Result[dict[str, Any]]:
        """
        Link a principle to a goal, habit, Ku, choice or another principle.

        ``link_type`` selects both the relationship (``_LINK_TYPE_MAP``) and what the
        target must be (``_LINK_FAR_ENDS``): the target is admitted by
        ``UnifiedRelationshipService`` — it exists, is of that kind, and is the
        principle's owner's or shared content. A target that is none of those is
        refused as not found.

        Returns:
            Result with the created link info
        """
        config_key = self._LINK_TYPE_MAP.get(link_type)
        far_end = self._LINK_FAR_ENDS.get(link_type)
        if config_key is None or far_end is None:
            return Result.fail(
                Errors.validation(
                    message=(
                        f"Unknown link_type: {link_type}. Valid: {', '.join(self._LINK_TYPE_MAP)}"
                    ),
                    field="link_type",
                )
            )

        result = await self.relationships.create_relationship(
            config_key, principle_uid, target_uid, far_end=far_end
        )
        if result.is_error:
            return Result.fail(result)

        self.logger.info(
            "Created %s link from principle %s to %s", link_type, principle_uid, target_uid
        )
        return Result.ok(
            {
                "principle_uid": principle_uid,
                "target_uid": target_uid,
                "link_type": link_type,
            }
        )

    async def get_principle_links(
        self,
        principle_uid: str,
        link_type: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get links for a principle (relationships to goals, habits, knowledge, principles).

        Queries via UnifiedRelationshipService cross-domain context and filters
        by link_type if provided.

        Args:
            principle_uid: Principle UID
            link_type: Optional filter (goal/habit/knowledge/principle/choice)

        Returns:
            Result with list of link dicts containing target info
        """
        if link_type:
            config_key = self._LINK_TYPE_MAP.get(link_type)
            if not config_key:
                return Result.fail(
                    Errors.validation(
                        message=(
                            f"Unknown link_type: {link_type}. "
                            f"Valid: {', '.join(self._LINK_TYPE_MAP)}"
                        ),
                        field="link_type",
                    )
                )
            uids_result = await self.relationships.get_related_uids(config_key, principle_uid)
            if uids_result.is_error:
                return Result.fail(uids_result)
            return Result.ok(
                [{"target_uid": uid, "link_type": link_type} for uid in uids_result.value]
            )

        # No filter — get all link types
        all_links: list[dict[str, Any]] = []
        for lt, config_key in self._LINK_TYPE_MAP.items():
            uids_result = await self.relationships.get_related_uids(config_key, principle_uid)
            if uids_result.is_error:
                continue  # Skip failed queries, return what we can
            all_links.extend({"target_uid": uid, "link_type": lt} for uid in uids_result.value)

        return Result.ok(all_links)
