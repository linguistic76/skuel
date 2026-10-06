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

from core.models.enums.principle_enums import PrincipleLinkType
from core.models.type_hints import Neo4jProperties
from core.services.mixins.link_edge_guard import (
    CHOICE_FAR_END,
    GOAL_FAR_END,
    HABIT_FAR_END,
    KNOWLEDGE_FAR_END,
    PRINCIPLE_FAR_END,
    LinkFarEnd,
)
from core.utils.result_simplified import Result


class _GravityMixin:
    """
    Cross-domain link methods for PrinciplesService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by PrinciplesService.__init__
    relationships: Any
    logger: Any

    # The PRINCIPLES_CONFIG relationship method key each link type writes and reads
    # through. One map for create_principle_link (write) and get_principle_links
    # (read), so the two cannot drift to different keys. Each value is a method_key in
    # PRINCIPLES_CONFIG — guarded by tests/unit/test_cross_domain_link_keys.py.
    _LINK_TYPE_MAP: ClassVar[dict[PrincipleLinkType, str]] = {
        PrincipleLinkType.GOAL: "supported_goals",
        PrincipleLinkType.HABIT: "inspired_habits",
        PrincipleLinkType.KNOWLEDGE: "knowledge",
        PrincipleLinkType.PRINCIPLE: "supporting_principles",
        PrincipleLinkType.CHOICE: "informed_choices",
    }

    # The properties a link type's edge is written with. Partial by design: a link
    # type with no entry writes no properties. A principle supports a goal with the
    # importance level a habit's support carries, at the habit doors' default.
    _LINK_PROPERTIES: ClassVar[dict[PrincipleLinkType, Neo4jProperties]] = {
        PrincipleLinkType.GOAL: {"weight": 1.0, "essentiality": "supporting"},
    }

    # What each link type links to — the kind the far end must be, and the name a
    # refusal answers with. Total over PrincipleLinkType, as _LINK_TYPE_MAP is; the
    # same test guards both.
    _LINK_FAR_ENDS: ClassVar[dict[PrincipleLinkType, LinkFarEnd]] = {
        PrincipleLinkType.GOAL: GOAL_FAR_END,
        PrincipleLinkType.HABIT: HABIT_FAR_END,
        PrincipleLinkType.KNOWLEDGE: KNOWLEDGE_FAR_END,
        PrincipleLinkType.PRINCIPLE: PRINCIPLE_FAR_END,
        PrincipleLinkType.CHOICE: CHOICE_FAR_END,
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
        link_type: PrincipleLinkType,
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
        result = await self.relationships.create_relationship(
            self._LINK_TYPE_MAP[link_type],
            principle_uid,
            target_uid,
            self._LINK_PROPERTIES.get(link_type),
            far_end=self._LINK_FAR_ENDS[link_type],
        )
        if result.is_error:
            return Result.fail(result)

        self.logger.info(
            "Created %s link from principle %s to %s", link_type.value, principle_uid, target_uid
        )
        return Result.ok(
            {
                "principle_uid": principle_uid,
                "target_uid": target_uid,
                "link_type": link_type.value,
            }
        )

    async def get_principle_links(
        self,
        principle_uid: str,
        link_type: PrincipleLinkType | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get a principle's links to goals, habits, Kus, choices and principles.

        Args:
            principle_uid: Principle UID
            link_type: One link type, or ``None`` for all of them

        Returns:
            Result with one ``{"target_uid", "link_type"}`` dict per link
        """
        if link_type is not None:
            uids_result = await self.relationships.get_related_uids(
                self._LINK_TYPE_MAP[link_type], principle_uid
            )
            if uids_result.is_error:
                return Result.fail(uids_result)
            return Result.ok(
                [{"target_uid": uid, "link_type": link_type.value} for uid in uids_result.value]
            )

        # No filter — get all link types
        all_links: list[dict[str, Any]] = []
        for each_type, config_key in self._LINK_TYPE_MAP.items():
            uids_result = await self.relationships.get_related_uids(config_key, principle_uid)
            if uids_result.is_error:
                continue  # Skip failed queries, return what we can
            all_links.extend(
                {"target_uid": uid, "link_type": each_type.value} for uid in uids_result.value
            )

        return Result.ok(all_links)
