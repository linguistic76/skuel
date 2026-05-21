"""
Interaction Service
===================

CRUD operations for Interaction entities — situated learning-loop events
that record the User Interaction Contract (who, what, where, result).

Responsibilities:
- Persist Interaction nodes to Neo4j
- Create graph context relationships (INTERACTION_DURING, INTERACTION_WITHIN, RECORDS)
- Query interactions for a user (for ZPD and analytics — Phase 2)

Does NOT handle:
- ZPD integration (deferred to Phase 2)
- Askesis integration (deferred to Phase 2)
- Updating result_status after report generation (deferred to Phase 2)
"""

from typing import TYPE_CHECKING

from core.models.enums.entity_enums import EntityType
from core.models.interaction.interaction import Interaction
from core.models.interaction.interaction_dto import InteractionDTO
from core.models.relationship_names import RelationshipName
from core.models.type_hints import UserUID
from core.ports import BackendOperations
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.backends.misc_backends import InteractionBackend

logger = get_logger("skuel.services.interaction")


class InteractionService(BaseService[BackendOperations[Interaction], Interaction]):
    """
    Service for Interaction entities (User Interaction Contract).

    Stores situated learning-loop events in Neo4j with their curriculum context:
    - (Interaction)-[:INTERACTION_DURING]->(PathStep)
    - (Interaction)-[:INTERACTION_WITHIN]->(LearningPath)
    - (Interaction)-[:RECORDS]->(UserEntry|...)

    Called by UserEntryService after a UserEntry is created (ADR-054),
    capturing the user's PathStep and LearningPath context at that moment.
    """

    _config = DomainConfig(
        dto_class=InteractionDTO,
        model_class=Interaction,
        entity_label="Entity",
        search_fields=("interaction_type", "target_uid"),
        search_order_by="created_at",
        user_ownership_relationship=RelationshipName.OWNS,
    )

    def __init__(
        self,
        backend: "InteractionBackend",
        event_bus=None,
    ) -> None:
        super().__init__(backend, "InteractionService")
        self.event_bus = event_bus
        self.logger = get_logger("skuel.services.interaction")  # type: ignore[assignment]

    # =========================================================================
    # CREATE
    # =========================================================================

    @with_error_handling("create_interaction")
    async def create_interaction(self, interaction: Interaction) -> Result[Interaction]:
        """
        Persist an Interaction node and its curriculum context relationships.

        Creates:
        - :Entity:Interaction node
        - [:INTERACTION_DURING]->(PathStep)   if context_path_step_uid is set
        - [:INTERACTION_WITHIN]->(LearningPath) if context_learning_path_uid is set
        - [:RECORDS]->(source entity)          if source_entity_uid is set

        Args:
            interaction: Fully constructed Interaction instance

        Returns:
            Result containing the created Interaction, or failure.
        """
        create_result = await self.backend.create(interaction)
        if create_result.is_error:
            return Result.fail(create_result)

        uid = interaction.uid
        relationships: list[tuple[str, str, str, None]] = []

        if interaction.context_path_step_uid:
            relationships.append(
                (
                    uid,
                    interaction.context_path_step_uid,
                    RelationshipName.INTERACTION_DURING.value,
                    None,
                )
            )

        if interaction.context_learning_path_uid:
            relationships.append(
                (
                    uid,
                    interaction.context_learning_path_uid,
                    RelationshipName.INTERACTION_WITHIN.value,
                    None,
                )
            )

        if interaction.source_entity_uid:
            relationships.append(
                (uid, interaction.source_entity_uid, RelationshipName.RECORDS.value, None)
            )

        if relationships:
            rel_result = await self.backend.create_relationships_batch(relationships)
            if rel_result.is_error:
                self.logger.warning(
                    f"Interaction {uid} created but context relationships failed: "
                    f"{rel_result.error}"
                )

        self.logger.info(
            f"Interaction created: {uid} "
            f"(type={interaction.interaction_type.value}, "
            f"target={interaction.target_uid}, "
            f"ps_context={interaction.context_path_step_uid})"
        )

        return create_result

    # =========================================================================
    # QUERY
    # =========================================================================

    @with_error_handling("list_interactions_for_user")
    async def list_interactions_for_user(
        self,
        user_uid: UserUID,
        limit: int = 50,
    ) -> Result[list[Interaction]]:
        """
        List recent Interactions for a user, newest first.

        Args:
            user_uid: User to query
            limit: Maximum number of interactions to return (default: 50)

        Returns:
            Result containing list of Interaction instances.
        """
        result = await self.backend.get_user_entities(
            user_uid=user_uid,
            filters={"entity_type": EntityType.INTERACTION.value},
            limit=limit,
            sort_by="created_at",
            sort_order="desc",
        )
        if result.is_error:
            return Result.fail(result)

        interactions = []
        for item in result.value or []:
            try:
                if isinstance(item, dict):
                    dto = InteractionDTO.from_dict(item)
                    interactions.append(Interaction.from_interaction_dto(dto))
                elif isinstance(item, Interaction):
                    interactions.append(item)
            except (KeyError, TypeError, ValueError):  # deserialization failures
                uid = item.get("uid") if isinstance(item, dict) else getattr(item, "uid", "?")
                self.logger.warning(f"Failed to deserialize interaction: {uid}")

        return Result.ok(interactions)
