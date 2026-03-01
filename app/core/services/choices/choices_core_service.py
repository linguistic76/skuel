"""
Choices Core Service - CRUD Operations
=======================================

Handles basic CRUD operations for choices.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.events import publish_event
from core.events.choice_events import (
    ChoiceCreated,
    ChoiceDeleted,
    ChoiceOutcomeRecorded,
    ChoiceUpdated,
)
from core.models.choice.choice import Choice
from core.models.choice.choice_dto import ChoiceDTO
from core.models.choice.choice_option import ChoiceOption
from core.models.enums.choice_enums import ChoiceType
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.relationship_names import RelationshipName
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.utils.decorators import with_error_handling
from core.utils.embedding_text_builder import build_embedding_text
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import make_attribute_sort_key

if TYPE_CHECKING:
    from core.models.choice.choice_request import (
        ChoiceCreateRequest,
        ChoiceEvaluationRequest,
    )
    from core.models.entity_requests import EntityUpdateRequest
    from core.ports.domain_protocols import ChoicesOperations


class ChoicesCoreService(BaseService["ChoicesOperations", Choice]):
    """
    Core CRUD operations for choices.

    Responsibilities:
    - Create, read, update, DETACH DELETE choices
    - List and filter choices
    - Count choices with filters


    Source Tag: "choices_core_service_explicit"
    - Format: "choices_core_service_explicit" for user-created relationships
    - Format: "choices_core_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from choices_core metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (uses pure Cypher)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    def __init__(
        self, backend: ChoicesOperations, event_bus=None, relationship_service=None
    ) -> None:
        """
        Initialize choices core service.

        Args:
            backend: Protocol-based backend for choice operations
            event_bus: Event bus for publishing domain events (optional)
            relationship_service: Optional relationship service for creating choice relationships

        Note:
            Context invalidation now happens via event-driven architecture.
            Created choices trigger ChoiceCreated events which invalidate context.
        """
        super().__init__(backend, "choices")
        self.event_bus = event_bus
        self.relationship_service = relationship_service
        self.logger = get_logger("skuel.services.choices.core")

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Choice entities (filters by entity_type)."""
        return "Entity"

    # ========================================================================
    # EMBEDDING HELPERS (Async Background Generation - January 2026)
    # ========================================================================

    # ========================================================================
    # DOMAIN-SPECIFIC CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================

    _config = create_activity_domain_config(
        dto_class=ChoiceDTO,
        model_class=Choice,
        domain_name="choices",
        date_field="decision_deadline",
        completed_statuses=(EntityStatus.COMPLETED.value,),
    )
    # ========================================================================
    # DOMAIN-SPECIFIC VALIDATION HOOKS
    # ========================================================================

    def _validate_create(self, choice: Choice) -> Result[None] | None:
        """
        Validate choice creation with business rules.

        Business Rules:
        1. Choice must have at least 2 options to be meaningful
        2. Binary choices must have exactly 2 options
        3. Strategic choices require detailed description (50+ characters)

        Args:
            choice: Choice domain model being created

        Returns:
            None if valid, Result.fail() with validation error if invalid
        """
        from core.utils.result_simplified import Errors

        if not isinstance(choice, Choice):
            return None

        # Business Rule 1: Minimum options
        if not choice.options or len(choice.options) < 2:
            return Result.fail(
                Errors.validation(
                    message="Choice must have at least 2 options to be meaningful",
                    field="options",
                    value=len(choice.options) if choice.options else 0,
                )
            )

        # Business Rule 2: Binary choice option count
        if choice.choice_type == ChoiceType.BINARY and len(choice.options) != 2:
            return Result.fail(
                Errors.validation(
                    message="Binary choices must have exactly 2 options",
                    field="options",
                    value=len(choice.options),
                )
            )

        # Business Rule 3: Strategic choices need detail
        if choice.choice_type == ChoiceType.STRATEGIC and (
            not choice.description or len(choice.description.strip()) < 50
        ):
            return Result.fail(
                Errors.validation(
                    message="Strategic choices require detailed description (50+ characters) "
                    "to ensure thoughtful decision-making",
                    field="description",
                    value=choice.description,
                )
            )

        return None  # All validations passed

    def _validate_update(self, current: Choice, updates: dict[str, Any]) -> Result[None] | None:
        """
        Validate choice updates with business rules.

        Business Rules:
        1. Decision immutability: Cannot modify critical fields in DECIDED or EVALUATED states
           (decisions are historical records - can only add notes or update metadata)
        2. Option count: If updating options, must maintain minimum of 2

        Args:
            current: Current choice state
            updates: Dictionary of proposed changes

        Returns:
            None if valid, Result.fail() with validation error if invalid
        """
        from core.utils.result_simplified import Errors

        # Business Rule 1: Decision immutability for critical fields
        # Once a choice is decided/evaluated, it's a historical decision point
        # Allow updates to notes/metadata, but not to the decision itself
        if current.status in [EntityStatus.ACTIVE, EntityStatus.COMPLETED]:
            # Critical fields that cannot be changed after decision
            critical_fields = {"options", "choice_type", "status", "selected_option"}
            changed_critical = set(updates.keys()) & critical_fields

            if changed_critical:
                return Result.fail(
                    Errors.validation(
                        message=f"Cannot modify {', '.join(changed_critical)} in {current.status.value} state. "
                        f"Decisions are historical records. Create a new choice to reconsider.",
                        field="status",
                        value=current.status.value,
                    )
                )

        # Business Rule 2: Option count validation
        if "options" in updates and (not updates["options"] or len(updates["options"]) < 2):
            return Result.fail(
                Errors.validation(
                    message="Choice must maintain at least 2 options to be meaningful",
                    field="options",
                    value=len(updates["options"]) if updates["options"] else 0,
                )
            )

        return None  # All validations passed

    async def create_choice(
        self, choice_request: ChoiceCreateRequest, user_uid: str
    ) -> Result[Choice]:
        """
        Create a basic choice.

        Args:
            choice_request: Choice creation request
            user_uid: User UID (REQUIRED - fail-fast philosophy)

        Returns:
            Result containing created Choice
        """
        # Validate user_uid (uses BaseService helper)
        validation = self._validate_required_user_uid(user_uid, "choice creation")
        if validation:
            return validation

        # Create DTO from request using entity factory method
        dto = ChoiceDTO.create_choice(
            user_uid=user_uid,
            title=choice_request.title,
            description=choice_request.description,
            priority=choice_request.priority,
            domain=choice_request.domain,
            decision_deadline=choice_request.decision_deadline,
        )

        # Create choice in backend (use generic create, not domain-specific create_choice)
        create_result = await self.backend.create(dto)
        if create_result.is_error:
            return create_result

        # Backend returns domain model directly, no conversion needed
        choice = create_result.value

        # Create knowledge relationships if provided
        if choice_request.informed_by_knowledge_uids and self.relationship_service:
            rel_result = await self.relationship_service.create_choice_relationships(
                choice_uid=choice.uid,
                informed_by_knowledge_uids=choice_request.informed_by_knowledge_uids,
            )
            if rel_result.is_error:
                self.logger.warning(
                    f"Failed to create knowledge relationships for choice {choice.uid}: {rel_result.error}"
                )

        # Publish ChoiceCreated event (event-driven architecture)
        event = ChoiceCreated(
            choice_uid=choice.uid,
            user_uid=choice.user_uid,
            choice_description=choice.description or choice.title,
            domain=choice.domain.value,
            urgency=choice.priority or "medium",
            occurred_at=datetime.now(),
        )
        await publish_event(self.event_bus, event, self.logger)

        # Publish batch knowledge event for substance tracking (O(1) vs O(n))
        if choice_request.informed_by_knowledge_uids:
            from core.events.ku_events import KnowledgeBulkInformedChoice

            knowledge_event = KnowledgeBulkInformedChoice(
                knowledge_uids=tuple(choice_request.informed_by_knowledge_uids),
                choice_uid=choice.uid,
                user_uid=choice.user_uid,
                occurred_at=datetime.now(),
                choice_title=choice.title,
            )
            await publish_event(self.event_bus, knowledge_event, self.logger)

        # Publish embedding request event for async background generation
        # Background worker will process embeddings in batches (zero latency impact on user)
        embedding_text = build_embedding_text(EntityType.CHOICE, choice)
        if embedding_text:
            from core.events import ChoiceEmbeddingRequested

            now = datetime.now()
            embedding_event = ChoiceEmbeddingRequested(
                entity_uid=choice.uid,
                entity_type="choice",
                embedding_text=embedding_text,
                user_uid=choice.user_uid,
                requested_at=now,
                occurred_at=now,
            )
            await publish_event(self.event_bus, embedding_event, self.logger)

        return Result.ok(choice)

    async def get_choice(self, choice_uid: str) -> Result[Choice]:
        """
        Get a specific choice by UID.

        Uses BaseService.get() which delegates to BackendOperations.get().
        Not found is returned as Result.fail(Errors.not_found(...)).

        Args:
            choice_uid: UID of the choice

        Returns:
            Result[Choice] - success contains Choice, not found is an error
        """
        return await self.get(choice_uid)

    async def get_user_choices(self, user_uid: str) -> Result[list[Choice]]:
        """
        Get all choices for a user.

        Args:
            user_uid: UID of the user

        Returns:
            Result containing list of Choices
        """
        result = await self.backend.find_by(user_uid=user_uid)
        if result.is_error:
            return result

        choices = self._to_domain_models(result.value, ChoiceDTO, Choice)
        return Result.ok(choices)

    @with_error_handling("get_choices_for_goal", error_type="database", uid_param="goal_uid")
    async def get_choices_for_goal(self, goal_uid: str) -> Result[list[Choice]]:
        """
        Get all choices motivated by a specific goal.

        Graph-native query: (goal)-[:MOTIVATED_BY_GOAL]->(choice)

        Args:
            goal_uid: Goal UID

        Returns:
            Result containing list of Choices motivated by this goal
        """
        # Query graph for choices motivated by this goal
        uids_result = await self.backend.get_related_uids(
            uid=goal_uid,
            relationship_type=RelationshipName.MOTIVATED_BY_GOAL,
            direction="outgoing",
            limit=100,
        )

        if uids_result.is_error:
            return Result.fail(uids_result.expect_error())

        choice_uids = uids_result.value

        if not choice_uids:
            return Result.ok([])

        # Fetch full choice entities
        choices = []
        for choice_uid in choice_uids:
            choice_result = await self.get_choice(choice_uid)
            if choice_result.is_ok:
                choices.append(choice_result.value)

        self.logger.debug(f"Found {len(choices)} choices for goal {goal_uid}")
        return Result.ok(choices)

    async def update_choice(
        self, choice_uid: str, choice_update: EntityUpdateRequest
    ) -> Result[Choice]:
        """
        Update a choice.

        Args:
            choice_uid: UID of the choice,
            choice_update: Updated choice data

        Returns:
            Result containing updated Choice
        """
        # Get existing choice
        existing_result = await self.get_choice(choice_uid)
        if existing_result.is_error:
            return Result.fail(existing_result.expect_error())

        existing = existing_result.value
        if not existing:
            return Result.fail(Errors.not_found(resource="Choice", identifier=choice_uid))
        assert isinstance(existing, Choice)

        # Create updated DTO
        dto = existing.to_dto()

        # Apply updates
        if choice_update.title is not None:
            dto.title = choice_update.title
        if choice_update.description is not None:
            dto.description = choice_update.description
        if choice_update.priority is not None:
            dto.priority = choice_update.priority
        if choice_update.decision_deadline is not None:
            dto.decision_deadline = choice_update.decision_deadline

        # Track updated fields
        updated_fields = {}
        if choice_update.title is not None:
            updated_fields["title"] = choice_update.title
        if choice_update.description is not None:
            updated_fields["description"] = choice_update.description
        if choice_update.priority is not None:
            updated_fields["priority"] = choice_update.priority
        if choice_update.decision_deadline is not None:
            updated_fields["deadline"] = choice_update.decision_deadline

        # Update in backend
        update_result = await self.backend.update(choice_uid, dto.to_dict())
        if update_result.is_error:
            return Result.fail(update_result)

        choice = self._to_domain_model(update_result.value, ChoiceDTO, Choice)

        # Publish ChoiceUpdated event (event-driven architecture)
        if updated_fields:
            event = ChoiceUpdated(
                choice_uid=choice.uid,
                user_uid=choice.user_uid,
                updated_fields=updated_fields,
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, event, self.logger)

        return Result.ok(choice)

    async def delete_choice(self, choice_uid: str) -> Result[bool]:
        """
        DETACH DELETE a choice.

        Args:
            choice_uid: UID of the choice

        Returns:
            Result indicating success
        """
        # Get choice before deletion (for event)
        choice_result = await self.get_choice(choice_uid)
        choice_description = None
        user_uid = "unknown"
        if choice_result.is_ok:
            choice = choice_result.value
            if choice:
                choice_description = choice.description or choice.title
                user_uid = choice.user_uid

        result = await self.backend.delete(choice_uid, cascade=True)
        if result.is_error:
            return result

        # Publish ChoiceDeleted event (event-driven architecture)
        event = ChoiceDeleted(
            choice_uid=choice_uid,
            user_uid=user_uid,
            choice_description=choice_description or choice_uid,
            occurred_at=datetime.now(),
        )
        await publish_event(self.event_bus, event, self.logger)

        return Result.ok(True)

    async def evaluate_choice_outcome(
        self, choice_uid: str, evaluation: ChoiceEvaluationRequest
    ) -> Result[Choice]:
        """
        Record the outcome evaluation for a choice.

        Publishes ChoiceOutcomeRecorded event for analytics and learning.

        Args:
            choice_uid: UID of the choice
            evaluation: Outcome evaluation data

        Returns:
            Result containing updated Choice
        """
        # Get existing choice
        existing_result = await self.get_choice(choice_uid)
        if existing_result.is_error:
            return Result.fail(existing_result.expect_error())

        existing = existing_result.value
        if not existing:
            return Result.fail(Errors.not_found(resource="Choice", identifier=choice_uid))
        assert isinstance(existing, Choice)

        # Create updated DTO with outcome data
        dto = existing.to_dto()
        dto.actual_outcome = evaluation.actual_outcome
        dto.satisfaction_score = evaluation.satisfaction_score
        dto.lessons_learned = evaluation.lessons_learned

        # Update in backend
        update_result = await self.backend.update(choice_uid, dto.to_dict())
        if update_result.is_error:
            return Result.fail(update_result)

        choice = self._to_domain_model(update_result.value, ChoiceDTO, Choice)
        assert isinstance(choice, Choice)

        # Calculate outcome quality score
        outcome_quality = choice.get_decision_quality_score() or 0.5

        # Publish ChoiceOutcomeRecorded event (event-driven architecture)
        event = ChoiceOutcomeRecorded(
            choice_uid=choice.uid,
            user_uid=choice.user_uid,
            outcome_quality=outcome_quality,
            lessons_learned=evaluation.actual_outcome if evaluation.lessons_learned else None,
            occurred_at=datetime.now(),
        )
        await publish_event(self.event_bus, event, self.logger)

        return Result.ok(choice)

    async def make_decision(
        self,
        choice_uid: str,
        selected_option_uid: str,
        decision_rationale: str | None = None,
        confidence: float = 0.5,
    ) -> Result[Choice]:
        """
        Record a decision for a choice (selects an option).

        Publishes ChoiceMade event when decision is finalized.

        Args:
            choice_uid: UID of the choice
            selected_option_uid: UID of the option that was selected
            decision_rationale: Optional rationale for the decision
            confidence: Confidence level in the decision (0.0-1.0)

        Returns:
            Result containing updated Choice
        """
        # Update choice with selected option directly via backend
        updates = {
            "selected_option_uid": selected_option_uid,
            "decision_rationale": decision_rationale,
            "decided_at": datetime.now().isoformat(),
            "status": EntityStatus.ACTIVE.value,
        }

        result = await self.backend.update(choice_uid, updates)
        if result.is_error:
            return result

        choice = self._to_domain_model(result.value, ChoiceDTO, Choice)

        # Publish ChoiceMade event
        from core.events import ChoiceMade

        event = ChoiceMade(
            choice_uid=choice.uid,
            user_uid=choice.user_uid,
            selected_option=selected_option_uid,
            confidence=confidence,
            occurred_at=datetime.now(),
            metadata={"rationale": decision_rationale} if decision_rationale else None,
        )
        await publish_event(self.event_bus, event, self.logger)

        return Result.ok(choice)

    async def find_choices(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str | None = None,
        order_desc: bool = False,
    ) -> Result[list[Choice]]:
        """
        Find choices with filters and pagination.

        Args:
            filters: Filter dictionary,
            limit: Maximum number of results,
            offset: Number of results to skip,
            order_by: Field to order by,
            order_desc: Order descending if True

        Returns:
            Result containing list of Choices
        """
        # Protocol-compliant backend call (filters and limit only)
        # Backend returns more results than needed to allow service-layer pagination
        backend_limit = limit + offset if offset > 0 else limit
        result = await self.backend.find_by(**(filters or {}), limit=backend_limit)

        if result.is_error:
            return result

        # Convert to domain models
        choices = self._to_domain_models(result.value, ChoiceDTO, Choice)

        # Service-layer filtering: sorting
        if order_by:
            reverse = order_desc
            try:
                sort_key = make_attribute_sort_key(order_by)
                choices = sorted(choices, key=sort_key, reverse=reverse)
            except (AttributeError, TypeError):
                # If order_by field doesn't exist or can't be compared, skip sorting
                pass

        # Service-layer filtering: pagination (offset)
        if offset > 0:
            choices = choices[offset:]

        # Apply final limit
        choices = choices[:limit]

        return Result.ok(choices)

    async def count_choices(self, filters: dict[str, Any] | None = None) -> Result[int]:
        """
        Count choices matching filters.

        Args:
            filters: Filter dictionary

        Returns:
            Result containing count
        """
        return await self.backend.count(**(filters or {}))

    # get_user_items_in_range() is now inherited from BaseService
    # Configured via class attributes: _date_field, _completed_statuses, _dto_class, _model_class
    # CONSOLIDATED (November 27, 2025) - Removed 45 lines of duplicate code

    # ========================================================================
    # OPTION MANAGEMENT
    # ========================================================================

    async def add_option(
        self,
        choice_uid: str,
        title: str,
        description: str,
        feasibility_score: float = 0.5,
        risk_level: float = 0.5,
        potential_impact: float = 0.5,
        resource_requirement: float = 0.5,
        estimated_duration: int | None = None,
        dependencies: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> Result[Choice]:
        """
        Add a new option to an existing choice.

        Business Rules:
        1. Cannot add options to DECIDED or EVALUATED choices (immutability)
        2. Binary choices can only have exactly 2 options

        Args:
            choice_uid: UID of the choice
            title: Option title
            description: Option description
            feasibility_score: Feasibility score (0-1, default 0.5)
            risk_level: Risk level (0-1, default 0.5)
            potential_impact: Potential impact (0-1, default 0.5)
            resource_requirement: Resource requirement (0-1, default 0.5)
            estimated_duration: Estimated duration in minutes
            dependencies: List of dependency UIDs
            tags: List of tags

        Returns:
            Result containing updated Choice with new option
        """
        from core.utils.uid_generator import UIDGenerator

        # Get existing choice
        existing_result = await self.get_choice(choice_uid)
        if existing_result.is_error:
            return Result.fail(existing_result.expect_error())

        existing = existing_result.value
        if not existing or not isinstance(existing, Choice):
            return Result.fail(Errors.not_found(resource="Choice", identifier=choice_uid))

        # Business Rule: Cannot modify decided/evaluated choices
        if existing.status in [EntityStatus.ACTIVE, EntityStatus.COMPLETED]:
            return Result.fail(
                Errors.validation(
                    message=f"Cannot add options to {existing.status.value} choice. "
                    "Decisions are historical records.",
                    field="status",
                    value=existing.status.value,
                )
            )

        # Business Rule: Binary choices can only have 2 options
        if existing.choice_type == ChoiceType.BINARY and len(existing.options) >= 2:
            return Result.fail(
                Errors.validation(
                    message="Binary choices can only have exactly 2 options",
                    field="choice_type",
                    value=existing.choice_type.value,
                )
            )

        # Create new option
        option_uid = UIDGenerator.generate_random_uid("option")
        new_option = ChoiceOption(
            uid=option_uid,
            title=title,
            description=description,
            feasibility_score=feasibility_score,
            risk_level=risk_level,
            potential_impact=potential_impact,
            resource_requirement=resource_requirement,
            estimated_duration=estimated_duration,
            dependencies=tuple(dependencies) if dependencies else (),
            tags=tuple(tags) if tags else (),
        )

        # Add option to existing options
        updated_options = list(existing.options)
        updated_options.append(new_option)

        # Update choice with new options
        dto = existing.to_dto()
        # ChoiceDTO stores ChoiceOption frozen dataclasses directly
        dto.options = list(updated_options)

        # Update in backend
        update_result = await self.backend.update(choice_uid, dto.to_dict())
        if update_result.is_error:
            return Result.fail(update_result.expect_error())

        choice = self._to_domain_model(update_result.value, ChoiceDTO, Choice)

        # Publish ChoiceUpdated event
        event = ChoiceUpdated(
            choice_uid=choice.uid,
            user_uid=choice.user_uid,
            updated_fields={"options": f"Added option: {title}"},
            occurred_at=datetime.now(),
        )
        await publish_event(self.event_bus, event, self.logger)

        self.logger.info(f"Added option '{title}' to choice {choice_uid}")
        return Result.ok(choice)

    async def update_option(
        self,
        choice_uid: str,
        option_uid: str,
        title: str | None = None,
        description: str | None = None,
        feasibility_score: float | None = None,
        risk_level: float | None = None,
        potential_impact: float | None = None,
        resource_requirement: float | None = None,
        estimated_duration: int | None = None,
        dependencies: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> Result[Choice]:
        """
        Update an existing option in a choice.

        Business Rules:
        1. Cannot update options in DECIDED or EVALUATED choices (immutability)
        2. Option must exist in the choice

        Args:
            choice_uid: UID of the choice
            option_uid: UID of the option to update
            title: New option title (optional)
            description: New option description (optional)
            feasibility_score: New feasibility score (optional)
            risk_level: New risk level (optional)
            potential_impact: New potential impact (optional)
            resource_requirement: New resource requirement (optional)
            estimated_duration: New estimated duration (optional)
            dependencies: New dependencies list (optional)
            tags: New tags list (optional)

        Returns:
            Result containing updated Choice
        """

        # Get existing choice
        existing_result = await self.get_choice(choice_uid)
        if existing_result.is_error:
            return Result.fail(existing_result.expect_error())

        existing = existing_result.value
        if not existing or not isinstance(existing, Choice):
            return Result.fail(Errors.not_found(resource="Choice", identifier=choice_uid))

        # Business Rule: Cannot modify decided/evaluated choices
        if existing.status in [EntityStatus.ACTIVE, EntityStatus.COMPLETED]:
            return Result.fail(
                Errors.validation(
                    message=f"Cannot update options in {existing.status.value} choice. "
                    "Decisions are historical records.",
                    field="status",
                    value=existing.status.value,
                )
            )

        # Find the option to update
        option_found = False
        updated_options = []

        for opt in existing.options:
            if opt.uid == option_uid:
                option_found = True
                # Create updated option with new values (immutable pattern)
                updated_option = ChoiceOption(
                    uid=opt.uid,
                    title=title if title is not None else opt.title,
                    description=description if description is not None else opt.description,
                    feasibility_score=(
                        feasibility_score
                        if feasibility_score is not None
                        else opt.feasibility_score
                    ),
                    risk_level=risk_level if risk_level is not None else opt.risk_level,
                    potential_impact=(
                        potential_impact if potential_impact is not None else opt.potential_impact
                    ),
                    resource_requirement=(
                        resource_requirement
                        if resource_requirement is not None
                        else opt.resource_requirement
                    ),
                    estimated_duration=(
                        estimated_duration
                        if estimated_duration is not None
                        else opt.estimated_duration
                    ),
                    dependencies=tuple(dependencies)
                    if dependencies is not None
                    else opt.dependencies,
                    tags=tuple(tags) if tags is not None else opt.tags,
                )
                updated_options.append(updated_option)
            else:
                updated_options.append(opt)

        if not option_found:
            return Result.fail(
                Errors.not_found(
                    resource="ChoiceOption",
                    identifier=option_uid,
                )
            )

        # Update choice with modified options
        dto = existing.to_dto()
        # ChoiceDTO stores ChoiceOption frozen dataclasses directly
        dto.options = list(updated_options)

        # Update in backend
        update_result = await self.backend.update(choice_uid, dto.to_dict())
        if update_result.is_error:
            return Result.fail(update_result.expect_error())

        choice = self._to_domain_model(update_result.value, ChoiceDTO, Choice)

        # Publish ChoiceUpdated event
        event = ChoiceUpdated(
            choice_uid=choice.uid,
            user_uid=choice.user_uid,
            updated_fields={"options": f"Updated option: {option_uid}"},
            occurred_at=datetime.now(),
        )
        await publish_event(self.event_bus, event, self.logger)

        self.logger.info(f"Updated option {option_uid} in choice {choice_uid}")
        return Result.ok(choice)

    async def remove_option(
        self,
        choice_uid: str,
        option_uid: str,
    ) -> Result[Choice]:
        """
        Remove an option from a choice.

        Business Rules:
        1. Cannot remove options from DECIDED or EVALUATED choices (immutability)
        2. Cannot remove options if it would leave less than 2 options
        3. Cannot remove the selected option (if choice is decided)
        4. Option must exist in the choice

        Args:
            choice_uid: UID of the choice
            option_uid: UID of the option to remove

        Returns:
            Result containing updated Choice
        """
        # Get existing choice
        existing_result = await self.get_choice(choice_uid)
        if existing_result.is_error:
            return Result.fail(existing_result.expect_error())

        existing = existing_result.value
        if not existing or not isinstance(existing, Choice):
            return Result.fail(Errors.not_found(resource="Choice", identifier=choice_uid))

        # Business Rule: Cannot modify decided/evaluated choices
        if existing.status in [EntityStatus.ACTIVE, EntityStatus.COMPLETED]:
            return Result.fail(
                Errors.validation(
                    message=f"Cannot remove options from {existing.status.value} choice. "
                    "Decisions are historical records.",
                    field="status",
                    value=existing.status.value,
                )
            )

        # Business Rule: Cannot remove selected option
        if existing.selected_option_uid == option_uid:
            return Result.fail(
                Errors.validation(
                    message="Cannot remove the selected option",
                    field="selected_option_uid",
                    value=option_uid,
                )
            )

        # Find and remove the option
        option_found = False
        updated_options = []

        for opt in existing.options:
            if opt.uid == option_uid:
                option_found = True
                # Don't add to updated_options (remove it)
            else:
                updated_options.append(opt)

        if not option_found:
            return Result.fail(
                Errors.not_found(
                    resource="ChoiceOption",
                    identifier=option_uid,
                )
            )

        # Business Rule: Must maintain at least 2 options
        if len(updated_options) < 2:
            return Result.fail(
                Errors.validation(
                    message="Choice must have at least 2 options. Cannot remove.",
                    field="options",
                    value=len(updated_options),
                )
            )

        # Update choice with remaining options
        dto = existing.to_dto()
        # ChoiceDTO stores ChoiceOption frozen dataclasses directly
        dto.options = list(updated_options)

        # Update in backend
        update_result = await self.backend.update(choice_uid, dto.to_dict())
        if update_result.is_error:
            return Result.fail(update_result.expect_error())

        choice = self._to_domain_model(update_result.value, ChoiceDTO, Choice)

        # Publish ChoiceUpdated event
        event = ChoiceUpdated(
            choice_uid=choice.uid,
            user_uid=choice.user_uid,
            updated_fields={"options": f"Removed option: {option_uid}"},
            occurred_at=datetime.now(),
        )
        await publish_event(self.event_bus, event, self.logger)

        self.logger.info(f"Removed option {option_uid} from choice {choice_uid}")
        return Result.ok(choice)

    # ========================================================================
    # HIERARCHICAL RELATIONSHIPS (2026-01-30 - Universal Hierarchical Pattern)
    # ========================================================================

    @with_error_handling("get_subchoices", error_type="database", uid_param="parent_uid")
    async def get_subchoices(self, parent_uid: str, depth: int = 1) -> Result[list[Choice]]:
        """
        Get all subchoices of a parent choice.

        Args:
            parent_uid: Parent choice UID
            depth: How many levels deep (1=direct children, 2=children+grandchildren, etc.)

        Returns:
            Result containing list of subchoices ordered by created_at

        Example:
            # Get direct children
            subchoices = await service.get_subchoices("choice_abc123")

            # Get all descendants
            all_subchoices = await service.get_subchoices("choice_abc123", depth=99)
        """
        query = f"""
        MATCH (parent:Entity {{uid: $parent_uid, ku_type: 'choice'}})
        MATCH (parent)-[:HAS_SUBCHOICE*1..{depth}]->(subchoice:Entity {{ku_type: 'choice'}})
        RETURN subchoice
        ORDER BY subchoice.created_at
        """

        result = await self.backend.execute_query(query, {"parent_uid": parent_uid})

        if result.is_error:
            return Result.fail(result.expect_error())
        if not result.value:
            return Result.ok([])

        # Convert to Choice models
        choices = []
        for record in result.value:
            choice_data = record["subchoice"]
            choice = self._to_domain_model(choice_data, ChoiceDTO, Choice)
            choices.append(choice)

        return Result.ok(choices)

    @with_error_handling("get_parent_choice", error_type="database", uid_param="subchoice_uid")
    async def get_parent_choice(self, subchoice_uid: str) -> Result[Choice | None]:
        """
        Get immediate parent of a subchoice (if any).

        Args:
            subchoice_uid: Subchoice UID

        Returns:
            Result containing parent Choice or None if root-level choice
        """
        query = """
        MATCH (subchoice:Entity {uid: $subchoice_uid, ku_type: 'choice'})
        MATCH (parent:Entity {ku_type: 'choice'})-[:HAS_SUBCHOICE]->(subchoice)
        RETURN parent
        LIMIT 1
        """

        result = await self.backend.execute_query(query, {"subchoice_uid": subchoice_uid})

        if result.is_error:
            return Result.fail(result.expect_error())
        if not result.value:
            return Result.ok(None)

        parent_data = result.value[0]["parent"]
        parent = self._to_domain_model(parent_data, ChoiceDTO, Choice)
        return Result.ok(parent)

    @with_error_handling("get_choice_hierarchy", error_type="database", uid_param="choice_uid")
    async def get_choice_hierarchy(self, choice_uid: str) -> Result[dict[str, Any]]:
        """
        Get full hierarchy context: ancestors, siblings, children.

        Args:
            choice_uid: Choice UID to get context for

        Returns:
            Result containing hierarchy dict with keys:
            - ancestors: list[Choice] (root to immediate parent)
            - current: Choice
            - siblings: list[Choice] (other children of same parent)
            - children: list[Choice] (immediate children)
            - depth: int (how deep in hierarchy, 0=root)

        Example:
            hierarchy = await service.get_choice_hierarchy("choice_xyz789")
            # {
            # "ancestors": [root_choice, parent_choice],
            # "current": choice_xyz789,
            # "siblings": [sibling1, sibling2],
            # "children": [child1, child2],
            # "depth": 2
            # }
        """
        # Get ancestors
        ancestors_query = """
        MATCH path = (root:Entity {ku_type: 'choice'})-[:HAS_SUBCHOICE*]->(current:Entity {uid: $choice_uid, ku_type: 'choice'})
        WHERE NOT EXISTS((root)<-[:HAS_SUBCHOICE]-())
        RETURN nodes(path) as ancestors
        """

        # Get siblings
        siblings_query = """
        MATCH (current:Entity {uid: $choice_uid, ku_type: 'choice'})
        OPTIONAL MATCH (parent:Entity {ku_type: 'choice'})-[:HAS_SUBCHOICE]->(current)
        OPTIONAL MATCH (parent)-[:HAS_SUBCHOICE]->(sibling:Entity {ku_type: 'choice'})
        WHERE sibling.uid <> $choice_uid
        RETURN collect(sibling) as siblings
        """

        # Get children
        children_query = """
        MATCH (current:Entity {uid: $choice_uid, ku_type: 'choice'})
        OPTIONAL MATCH (current)-[:HAS_SUBCHOICE]->(child:Entity {ku_type: 'choice'})
        RETURN collect(child) as children
        """

        # Execute all queries
        current_result = await self.backend.get(choice_uid)
        if current_result.is_error:
            return Result.fail(current_result)

        current_choice = self._to_domain_model(current_result.value, ChoiceDTO, Choice)

        ancestors_result = await self.backend.execute_query(
            ancestors_query, {"choice_uid": choice_uid}
        )
        siblings_result = await self.backend.execute_query(
            siblings_query, {"choice_uid": choice_uid}
        )
        children_result = await self.backend.execute_query(
            children_query, {"choice_uid": choice_uid}
        )

        # Process ancestors
        ancestors = []
        if (
            not ancestors_result.is_error
            and ancestors_result.value
            and ancestors_result.value[0]["ancestors"]
        ):
            for node in ancestors_result.value[0]["ancestors"][:-1]:  # Exclude current
                choice_data = node
                ancestors.append(self._to_domain_model(choice_data, ChoiceDTO, Choice))

        # Process siblings
        siblings = []
        if (
            not siblings_result.is_error
            and siblings_result.value
            and siblings_result.value[0]["siblings"]
        ):
            for node in siblings_result.value[0]["siblings"]:
                if node:  # Skip None values
                    choice_data = node
                    siblings.append(self._to_domain_model(choice_data, ChoiceDTO, Choice))

        # Process children
        children = []
        if (
            not children_result.is_error
            and children_result.value
            and children_result.value[0]["children"]
        ):
            for node in children_result.value[0]["children"]:
                if node:  # Skip None values
                    choice_data = node
                    children.append(self._to_domain_model(choice_data, ChoiceDTO, Choice))

        return Result.ok(
            {
                "ancestors": ancestors,
                "current": current_choice,
                "siblings": siblings,
                "children": children,
                "depth": len(ancestors),
            }
        )

    @with_error_handling("create_subchoice_relationship", error_type="database")
    async def create_subchoice_relationship(
        self,
        parent_uid: str,
        subchoice_uid: str,
        order: int = 0,
        depends_on_outcome: str | None = None,
    ) -> Result[bool]:
        """
        Create bidirectional parent-child relationship.

        Args:
            parent_uid: Parent choice UID
            subchoice_uid: Subchoice UID
            order: Display order for subchoices (default: 0)
            depends_on_outcome: Outcome value that triggers this subchoice (optional)

        Returns:
            Result indicating success

        Note:
            Creates both HAS_SUBCHOICE (parent→child) and SUBCHOICE_OF (child→parent)
            for efficient bidirectional queries. Supports conditional decision trees via
            depends_on_outcome property.
        """
        # Validate no cycle (can't make parent a child of its descendant)
        cycle_check = await self._would_create_cycle(parent_uid, subchoice_uid)
        if cycle_check:
            return Result.fail(
                Errors.validation(
                    f"Cannot create subchoice relationship: would create cycle "
                    f"({subchoice_uid} is ancestor of {parent_uid})"
                )
            )

        # Build relationship properties
        rel_props = {"order": order}
        if depends_on_outcome is not None:
            rel_props["depends_on_outcome"] = depends_on_outcome

        # Build property assignments for Cypher
        prop_assignments = ", ".join([f"{k}: ${k}" for k in rel_props])

        query = f"""
        MATCH (parent:Entity {{uid: $parent_uid, ku_type: 'choice'}})
        MATCH (subchoice:Entity {{uid: $subchoice_uid, ku_type: 'choice'}})

        CREATE (parent)-[:HAS_SUBCHOICE {{
            {prop_assignments},
            created_at: datetime()
        }}]->(subchoice)

        CREATE (subchoice)-[:SUBCHOICE_OF {{
            created_at: datetime()
        }}]->(parent)

        RETURN true as success
        """

        params = {"parent_uid": parent_uid, "subchoice_uid": subchoice_uid, **rel_props}
        result = await self.backend.execute_query(query, params)

        if result.is_error:
            return Result.fail(
                Errors.database(
                    operation="create", message="Failed to create subchoice relationship"
                )
            )
        if result.value:
            self.logger.info(
                f"Created subchoice relationship: {parent_uid} -> {subchoice_uid} (order: {order})"
            )
            return Result.ok(True)

        return Result.fail(
            Errors.database(operation="create", message="Failed to create subchoice relationship")
        )

    @with_error_handling("remove_subchoice_relationship", error_type="database")
    async def remove_subchoice_relationship(
        self, parent_uid: str, subchoice_uid: str
    ) -> Result[bool]:
        """
        Remove bidirectional parent-child relationship.

        Args:
            parent_uid: Parent choice UID
            subchoice_uid: Subchoice UID

        Returns:
            Result containing True if relationships were deleted
        """
        query = """
        MATCH (parent:Entity {uid: $parent_uid, ku_type: 'choice'})-[r1:HAS_SUBCHOICE]->(subchoice:Entity {uid: $subchoice_uid, ku_type: 'choice'})
        MATCH (subchoice)-[r2:SUBCHOICE_OF]->(parent)
        DELETE r1, r2
        RETURN count(r1) + count(r2) as deleted_count
        """

        result = await self.backend.execute_query(
            query, {"parent_uid": parent_uid, "subchoice_uid": subchoice_uid}
        )

        if not result.is_error and result.value:
            deleted = result.value[0]["deleted_count"]
            if deleted > 0:
                self.logger.info(f"Removed subchoice relationship: {parent_uid} -> {subchoice_uid}")
                return Result.ok(True)

        return Result.ok(False)

    async def _would_create_cycle(self, parent_uid: str, child_uid: str) -> bool:
        """Check if adding parent->child relationship would create a cycle."""
        query = """
        MATCH (child:Entity {uid: $child_uid, ku_type: 'choice'})
        MATCH path = (child)-[:HAS_SUBCHOICE*]->(parent:Entity {uid: $parent_uid, ku_type: 'choice'})
        RETURN count(path) > 0 as would_create_cycle
        """

        result = await self.backend.execute_query(
            query, {"parent_uid": parent_uid, "child_uid": child_uid}
        )

        if result.is_error:
            return False
        if result.value:
            return result.value[0]["would_create_cycle"]

        return False
