"""
Interaction Service
===================

CRUD operations for Interaction entities — situated learning-loop events
that record the User Interaction Contract (who, what, where, result).

Responsibilities:
- Persist Interaction nodes to Neo4j
- Create graph context relationships (INTERACTION_DURING, INTERACTION_WITHIN, RECORDS)
- Transition result_status as the report pipeline progresses (ADR-051 Phase 2)
- Query interactions for a user (for ZPD and analytics — Phase 2)

Does NOT handle:
- ZPD integration (deferred to Phase 2)
- Askesis integration (deferred to Phase 2)
"""

from core.models.enums.interaction_enums import InteractionResult
from core.models.interaction.interaction import Interaction
from core.models.interaction.interaction_dto import InteractionDTO
from core.models.relationship_names import RelationshipName
from core.models.type_hints import Neo4jProperties
from core.ports.interaction_protocols import InteractionBackendOperations
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.services.interaction")


class InteractionService(BaseService[InteractionBackendOperations, Interaction]):
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
        backend: InteractionBackendOperations,
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
        relationships: list[tuple[str, str, str, Neo4jProperties | None]] = []

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
    # RESULT-STATUS TRANSITIONS (ADR-051 Phase 2)
    # =========================================================================

    @with_error_handling("record_result")
    async def record_result(self, entry_uid: str, new_status: InteractionResult) -> Result[bool]:
        """Transition the result_status of the Interaction recording a UserEntry.

        The lifecycle is forward-only — ``InteractionResult.allowed_from()``
        defines which current statuses the transition applies from, and the
        guard runs inside the Cypher so stale events can never demote a record.

        Returns ``Result.ok(True)`` when a record transitioned, ``ok(False)``
        for the two valid no-ops: no Interaction records this entry (e.g. a
        journal entry), or the guard rejected an out-of-order event.

        Backend: InteractionBackend.update_result_status_for_entry
        """
        allowed_from = new_status.allowed_from()
        if not allowed_from:
            return Result.fail(
                Errors.validation(
                    f"{new_status.value} is not a valid transition target",
                    field="new_status",
                )
            )

        update_result = await self.backend.update_result_status_for_entry(
            entry_uid=entry_uid,
            new_status=new_status,
            allowed_from=allowed_from,
        )
        if update_result.is_error:
            return Result.fail(update_result)

        transitioned = update_result.value > 0
        if transitioned:
            self.logger.info(
                f"Interaction result transitioned to {new_status.value} for entry {entry_uid}"
            )
        else:
            self.logger.debug(
                f"No interaction transition to {new_status.value} for entry {entry_uid} "
                f"(no record, or already past {new_status.value})"
            )
        return Result.ok(transitioned)

    # =========================================================================
