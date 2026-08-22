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

    async def link_principle_to_knowledge(
        self, principle_uid: str, knowledge_uid: str, relevance: str = "fundamental"
    ) -> Result[bool]:
        """Link principle to knowledge it's grounded in (``GROUNDED_IN_KNOWLEDGE``)."""
        return await self.relationships.create_relationship(
            "knowledge", principle_uid, knowledge_uid, {"relevance": relevance}
        )

    # ========================================================================
    # PRINCIPLE LINKS — Neo4j relationships via UnifiedRelationshipService
    # ========================================================================

    async def create_principle_link(
        self,
        dto: Any,
    ) -> Result[dict[str, Any]]:
        """
        Create a link between a principle and another entity.

        Maps link_type to the appropriate relationship config key in PRINCIPLES_CONFIG
        and delegates to UnifiedRelationshipService.

        Args:
            dto: Dict with principle_uid, target_uid, link_type (goal/habit/knowledge/principle),
                 and optional properties

        Returns:
            Result with the created link info
        """
        principle_uid = (
            dto.get("principle_uid")
            if isinstance(dto, dict)
            else getattr(dto, "principle_uid", None)
        )
        target_uid = (
            dto.get("target_uid") if isinstance(dto, dict) else getattr(dto, "target_uid", None)
        )
        link_type = (
            dto.get("link_type") if isinstance(dto, dict) else getattr(dto, "link_type", None)
        )

        if not principle_uid or not target_uid or not link_type:
            return Result.fail(
                Errors.validation(
                    message="principle_uid, target_uid, and link_type are required",
                    field="link_type",
                )
            )

        # Map link_type to PRINCIPLES_CONFIG relationship config key
        config_key = self._LINK_TYPE_MAP.get(link_type)
        if not config_key:
            return Result.fail(
                Errors.validation(
                    message=(
                        f"Unknown link_type: {link_type}. Valid: {', '.join(self._LINK_TYPE_MAP)}"
                    ),
                    field="link_type",
                )
            )

        properties = (
            dto.get("properties") if isinstance(dto, dict) else getattr(dto, "properties", None)
        )
        result = await self.relationships.create_relationship(
            config_key, principle_uid, target_uid, properties
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
