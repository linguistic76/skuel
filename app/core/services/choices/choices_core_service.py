"""
Choices Core Service - CRUD Operations
=======================================

Handles basic CRUD operations for choices.

Version: 1.0.0
- v1.0.0: Initial implementation extracted from EnhancedChoicesService (October 13, 2025)
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar

from core.events import publish_event
from core.events.choice_events import (
    ChoiceCreated,
    ChoiceDeleted,
    ChoiceOutcomeRecorded,
    ChoiceUpdated,
)
from core.models.choice.choice import Choice, ChoiceStatus, ChoiceType
from core.models.choice.choice_dto import ChoiceDTO
from core.models.choice.choice_request import ChoiceUpdateRequest
from core.models.relationship_names import RelationshipName
from core.services.base_service import BaseService
from core.services.protocols.domain_protocols import ChoicesOperations
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import make_attribute_sort_key

if TYPE_CHECKING:
    from core.models.choice.choice_request import (
        ChoiceCreateRequest,
        ChoiceEvaluationRequest,
    )


class ChoicesCoreService(BaseService[ChoicesOperations, Choice]):
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
    - No APOC calls (Phase 5 eliminated those)
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
        """Return the graph label for Choice entities."""
        return "Choice"

    # ========================================================================
    # DOMAIN-SPECIFIC CONFIGURATION (Class Attributes)
    # ========================================================================
    # CONSOLIDATED (November 27, 2025): These class attributes configure
    # the unified get_user_items_in_range() method in BaseService.

    _date_field: str = "decided_at"  # Choices filter by decision date
    _completed_statuses: ClassVar[list[str]] = [ChoiceStatus.ARCHIVED.value]
    _dto_class = ChoiceDTO
    _model_class = Choice

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
        if current.status in [ChoiceStatus.DECIDED, ChoiceStatus.EVALUATED]:
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

        # Create DTO from request
        dto = ChoiceDTO.create(
            user_uid=user_uid,
            title=choice_request.title,
            description=choice_request.description,
            priority=choice_request.priority,
            domain=choice_request.domain,
            deadline=choice_request.decision_deadline,
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
            urgency=choice.priority.value,
            occurred_at=datetime.now(),
        )
        await publish_event(self.event_bus, event, self.logger)

        # Publish batch knowledge event for substance tracking (O(1) vs O(n))
        if choice_request.informed_by_knowledge_uids:
            from core.events.knowledge_events import KnowledgeBulkInformedChoice

            knowledge_event = KnowledgeBulkInformedChoice(
                knowledge_uids=tuple(choice_request.informed_by_knowledge_uids),
                choice_uid=choice.uid,
                user_uid=choice.user_uid,
                occurred_at=datetime.now(),
                choice_title=choice.title,
            )
            await publish_event(self.event_bus, knowledge_event, self.logger)

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
        self, choice_uid: str, choice_update: ChoiceUpdateRequest
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
        update_result = await self.backend.update_choice(choice_uid, dto.to_dict())
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

        result = await self.backend.delete_choice(choice_uid)
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

        # Create updated DTO with outcome data
        dto = existing.to_dto()
        dto.actual_outcome = evaluation.actual_outcome
        dto.satisfaction_score = evaluation.satisfaction_score
        dto.lessons_learned = evaluation.lessons_learned

        # Update in backend
        update_result = await self.backend.update_choice(choice_uid, dto.to_dict())
        if update_result.is_error:
            return Result.fail(update_result)

        choice = self._to_domain_model(update_result.value, ChoiceDTO, Choice)

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
        # Update choice with selected option
        updates = {
            "selected_option_uid": selected_option_uid,
            "decision_rationale": decision_rationale,
            "decided_at": datetime.now(),
            "status": ChoiceStatus.DECIDED.value,
        }

        result = await self.update_choice(choice_uid, ChoiceUpdateRequest(**updates))
        if result.is_error:
            return result

        choice = result.value

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
        result = await self.backend.find_choices(filters=filters, limit=backend_limit)

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
        return await self.backend.count_choices(filters=filters)

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
        from core.models.choice.choice import ChoiceOption
        from core.utils.uid_generator import UIDGenerator

        # Get existing choice
        existing_result = await self.get_choice(choice_uid)
        if existing_result.is_error:
            return Result.fail(existing_result.expect_error())

        existing = existing_result.value
        if not existing:
            return Result.fail(Errors.not_found(resource="Choice", identifier=choice_uid))

        # Business Rule: Cannot modify decided/evaluated choices
        if existing.status in [ChoiceStatus.DECIDED, ChoiceStatus.EVALUATED]:
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
        from core.models.choice.choice_dto import ChoiceOptionDTO

        dto.options = [
            ChoiceOptionDTO(
                uid=opt.uid,
                title=opt.title,
                description=opt.description,
                feasibility_score=opt.feasibility_score,
                risk_level=opt.risk_level,
                potential_impact=opt.potential_impact,
                resource_requirement=opt.resource_requirement,
                estimated_duration=opt.estimated_duration,
                dependencies=list(opt.dependencies),
                tags=list(opt.tags),
            )
            for opt in updated_options
        ]

        # Update in backend
        update_result = await self.backend.update_choice(choice_uid, dto.to_dict())
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
        from core.models.choice.choice import ChoiceOption

        # Get existing choice
        existing_result = await self.get_choice(choice_uid)
        if existing_result.is_error:
            return Result.fail(existing_result.expect_error())

        existing = existing_result.value
        if not existing:
            return Result.fail(Errors.not_found(resource="Choice", identifier=choice_uid))

        # Business Rule: Cannot modify decided/evaluated choices
        if existing.status in [ChoiceStatus.DECIDED, ChoiceStatus.EVALUATED]:
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
        from core.models.choice.choice_dto import ChoiceOptionDTO

        dto.options = [
            ChoiceOptionDTO(
                uid=opt.uid,
                title=opt.title,
                description=opt.description,
                feasibility_score=opt.feasibility_score,
                risk_level=opt.risk_level,
                potential_impact=opt.potential_impact,
                resource_requirement=opt.resource_requirement,
                estimated_duration=opt.estimated_duration,
                dependencies=list(opt.dependencies),
                tags=list(opt.tags),
            )
            for opt in updated_options
        ]

        # Update in backend
        update_result = await self.backend.update_choice(choice_uid, dto.to_dict())
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
        if not existing:
            return Result.fail(Errors.not_found(resource="Choice", identifier=choice_uid))

        # Business Rule: Cannot modify decided/evaluated choices
        if existing.status in [ChoiceStatus.DECIDED, ChoiceStatus.EVALUATED]:
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
        from core.models.choice.choice_dto import ChoiceOptionDTO

        dto.options = [
            ChoiceOptionDTO(
                uid=opt.uid,
                title=opt.title,
                description=opt.description,
                feasibility_score=opt.feasibility_score,
                risk_level=opt.risk_level,
                potential_impact=opt.potential_impact,
                resource_requirement=opt.resource_requirement,
                estimated_duration=opt.estimated_duration,
                dependencies=list(opt.dependencies),
                tags=list(opt.tags),
            )
            for opt in updated_options
        ]

        # Update in backend
        update_result = await self.backend.update_choice(choice_uid, dto.to_dict())
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
