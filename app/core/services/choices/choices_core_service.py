"""
Choices Core Service - CRUD Operations
=======================================

Handles basic CRUD operations for choices.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from core.events import publish_event
from core.events.choice_events import (
    ChoiceCreated,
    ChoiceDeleted,
    ChoiceOutcomeRecorded,
    ChoiceUpdated,
)
from core.events.embedding_publisher import publish_embedding_requested
from core.models.choice.choice import Choice
from core.models.choice.choice_dto import ChoiceDTO
from core.models.choice.choice_option import ChoiceOption
from core.models.choice.choice_update_intent import ChoiceUpdateIntent
from core.models.enums.choice_enums import ChoiceType
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.relationship_names import RelationshipName
from core.models.type_hints import Neo4jProperties, UserUID
from core.ports.query_types import ChoiceStats
from core.services.base_service import BaseService
from core.services.conversion_service import ConversionServiceV2
from core.services.domain_config import create_activity_domain_config
from core.services.mixins.hierarchy_read_mixin import HierarchyReadMixin
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import make_attribute_sort_key
from core.utils.uid_generator import UIDGenerator

if TYPE_CHECKING:
    from core.models.choice.choice_request import (
        ChoiceCreateRequest,
        ChoiceEvaluationRequest,
    )
    from core.ports.domain_protocols import ChoicesOperations


class ChoicesCoreService(
    HierarchyReadMixin["ChoicesOperations", Choice],
    BaseService["ChoicesOperations", Choice, ChoiceUpdateIntent],
):
    """
    Core CRUD operations for choices.

    Responsibilities:
    - Create, read, update, delete choices
    - List and filter choices
    - Count choices with filters
    """

    def __init__(self, backend: ChoicesOperations, event_bus=None) -> None:
        """
        Initialize choices core service.

        Args:
            backend: Protocol-based backend for choice operations
            event_bus: Event bus for publishing domain events (optional)

        Note:
            Context invalidation now happens via event-driven architecture.
            Created choices trigger ChoiceCreated events which invalidate context.
            Knowledge edges are created GRAPH-NATIVELY via the backend batch path
            (mirrors TasksCoreService), not via a relationship service.
        """
        super().__init__(backend, "choices")
        self.event_bus = event_bus
        self.logger = get_logger("skuel.services.choices.core")  # type: ignore[assignment]  # structlog BoundLogger

    # ========================================================================
    # DOMAIN-SPECIFIC CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================

    _config = create_activity_domain_config(
        dto_class=ChoiceDTO,
        model_class=Choice,
        domain_name="choices",
        date_field="decision_deadline",
        completed_statuses=(EntityStatus.COMPLETED.value,),
        status_filters={
            "pending": {"status": "pending"},
            "decided": {"status": "decided"},
            "implemented": {"status": "implemented"},
        },
    )
    # ========================================================================
    # DOMAIN-SPECIFIC VALIDATION HOOKS
    # ========================================================================

    def _validate_create(self, choice: Choice) -> Result[None]:
        """
        Validate choice creation with business rules.

        Business Rules:
        1. Options are OPTIONAL at creation, but a supplied set must hold at least 2
        2. Binary choices, once they carry options, must carry exactly 2
        3. Strategic choices require detailed description (50+ characters)

        Options are optional at creation because that is how choices are really made:
        the UI create form deliberately omits the nested options list (they are added
        on the detail page via ``add_option``), and DSL activity ingestion creates
        choices from a single line of prose with no options at all. Requiring 2 up
        front would reject every choice those doors make. The ">= 2 options" floor is
        an invariant of a choice that HAS options — enforced here on what was supplied,
        and by ``remove_option`` / ``_validate_update`` from then on.

        Args:
            choice: Choice domain model being created

        Returns:
            None if valid, Result.fail() with validation error if invalid
        """
        from core.utils.result_simplified import Errors

        if not isinstance(choice, Choice):
            return Result.ok(None)

        # A draft with no options yet is legal — rules 1 and 2 govern a supplied set.
        if choice.options:
            # Business Rule 1: a single option is not a choice
            if len(choice.options) < 2:
                return Result.fail(
                    Errors.validation(
                        message="A choice with options must have at least 2 to be meaningful",
                        field="options",
                        value=len(choice.options),
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

        return Result.ok(None)  # All validations passed

    def _validate_update(self, current: Choice, updates: ChoiceUpdateIntent) -> Result[None]:
        """
        Validate choice updates with business rules.

        Business Rules:
        1. Decision immutability: Cannot modify critical fields in DECIDED or EVALUATED states
           (decisions are historical records - can only add notes or update metadata)
        2. Option count: If updating options, must maintain minimum of 2

        Args:
            current: Current choice state
            updates: Typed ``ChoiceUpdateIntent`` of proposed changes

        Returns:
            None if valid, Result.fail() with validation error if invalid
        """
        from core.utils.result_simplified import Errors

        changes = updates.to_changes()
        # Business Rule 1: Decision immutability for critical fields
        # Once a choice is decided/evaluated, it's a historical decision point
        # Allow updates to notes/metadata, but not to the decision itself
        if current.status in [EntityStatus.ACTIVE, EntityStatus.COMPLETED]:
            # Critical fields that cannot be changed after decision
            critical_fields = {"options", "choice_type", "status", "selected_option"}
            changed_critical = set(changes.keys()) & critical_fields

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
        if "options" in changes and (not changes["options"] or len(changes["options"]) < 2):
            return Result.fail(
                Errors.validation(
                    message="Choice must maintain at least 2 options to be meaningful",
                    field="options",
                    value=len(changes["options"]) if changes["options"] else 0,
                )
            )

        return Result.ok(None)  # All validations passed

    async def create(self, entity: Choice) -> Result[Choice]:
        """THE Choices create primitive: validate → persist → publish.

        Both create doors land here, so the domain's creation rules cannot be
        skipped by picking one door over the other:

        - the generated CRUD route (``CRUDRouteFactory``) converts its schema to a
          ``Choice`` and calls ``ChoicesService.create``, which delegates here;
        - ``create_choice`` below converts its request to a ``Choice`` and calls this.

        ``super().create`` is what runs ``_validate_create`` (a supplied option set
        holds >= 2, BINARY carries exactly 2, STRATEGIC needs a 50+ char description)
        — those rules are only ever reached through ``CrudOperationsMixin.create``.
        Persisting via ``_create_and_convert`` instead, as ``create_choice`` used to,
        goes straight to ``backend.create`` and silently skips every one of them.

        Mirrors the same ``create`` override in the Goals, Habits and Events core
        services.

        Args:
            entity: Choice to create

        Returns:
            Result containing created Choice

        Events Published:
            - ChoiceCreated: when the choice is successfully created
            - EmbeddingRequested (ADR-074): post-persist embedding refresh
        """
        result = await self._create_validated(entity)
        if result.is_error:
            return result

        await self._publish_created(result.value)
        return result

    async def _create_validated(self, entity: Choice) -> Result[Choice]:
        """Validate and persist, publishing NOTHING.

        Split out from ``create`` so ``create_choice`` can finish writing the
        choice's graph edges before any event announces the choice exists — see
        ``_publish_created`` for why that ordering is load-bearing.
        """
        return await super().create(entity)

    async def _publish_created(self, choice: Choice) -> None:
        """Announce a newly created choice: ChoiceCreated + the ADR-074 embedding refresh.

        ORDERING: call this only once the choice's graph edges are written.
        ``ChoiceCreated`` is subscribed to ``invalidate_context``
        (services_bootstrap/_event_wiring.py), which debounces 100ms and then rebuilds
        the user context — and the rebuild reads ``choice_knowledge_informed`` back out
        of the graph. Publishing before ``create_relationships_batch`` finishes lets the
        rebuild observe a choice with no INFORMED_BY_KNOWLEDGE edges and cache that empty
        result for the full 300s TTL. The later KnowledgeInformedChoice events are wired
        only to substance handlers and do NOT invalidate the context, so nothing corrects
        it. (Reported by Codex on #960.)
        """
        event = ChoiceCreated(
            choice_uid=choice.uid,
            user_uid=choice.user_uid,
            choice_description=choice.description or choice.title,
            # Choice.domain is nullable (the model guards it the same way in
            # `category`), and this primitive now runs for hand-built entities from
            # the generated route too — not just for requests, whose domain always
            # defaults. ChoiceCreated.domain is a non-optional str.
            domain=choice.domain.value if choice.domain else "",
            urgency=choice.priority or "medium",
        )
        await publish_event(self.event_bus, event, self.logger)

        # Post-persist embedding refresh (ADR-074) — the background worker embeds async
        await publish_embedding_requested(self.event_bus, EntityType.CHOICE, choice, self.logger)

    async def create_choice(
        self, choice_request: ChoiceCreateRequest, user_uid: UserUID
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
        if validation.is_error:
            return Result.fail(validation)

        # Build the entity with the SAME converter the generated CRUD route uses, so
        # the two doors cannot drift on which request fields survive. Hand-listing
        # them onto ChoiceDTO.create_choice is what dropped options, choice_type,
        # decision_criteria, constraints, stakeholders and tags here: the factory
        # takes **kwargs, so every omission was silent.
        uid = UIDGenerator.generate_uid("choice", choice_request.title)
        entity = ConversionServiceV2.choice_create_to_pure(choice_request, uid, user_uid=user_uid)

        # Validate + persist, but hold the events back until the knowledge edges below
        # are written (see _publish_created). NOT _create_and_convert, which bypasses
        # _validate_create entirely.
        create_result = await self._create_validated(entity)
        if create_result.is_error:
            return create_result

        choice = create_result.value

        # GRAPH-NATIVE: Create (Choice)-[:INFORMED_BY_KNOWLEDGE]->(Ku) edges in a
        # single batch (mirrors TasksCoreService.create_task). Edges live in the
        # graph, never on the Choice/DTO; read back via PsService.find_choices_informed_by_knowledge.
        if choice_request.informed_by_knowledge_uids:
            relationships: list[tuple[str, str, str, Neo4jProperties | None]] = [
                (choice.uid, knowledge_uid, RelationshipName.INFORMED_BY_KNOWLEDGE.value, None)
                for knowledge_uid in choice_request.informed_by_knowledge_uids
            ]
            batch_result = await self.backend.create_relationships_batch(relationships)
            if batch_result.is_error:
                self.logger.warning(
                    f"Failed to create {len(relationships)} knowledge relationships "
                    f"for choice {choice.uid}: {batch_result.error}"
                )

        # Edges are written — only now announce the choice. ChoiceCreated drives the
        # user-context rebuild, which reads those edges back out of the graph.
        await self._publish_created(choice)

        # Publish knowledge substance event: single-item for 1 KU, bulk for 2+
        if choice_request.informed_by_knowledge_uids:
            from core.events.knowledge_substance_events import (
                KnowledgeBulkInformedChoice,
                KnowledgeInformedChoice,
            )

            ku_uids = choice_request.informed_by_knowledge_uids
            if len(ku_uids) == 1:
                knowledge_event: KnowledgeInformedChoice | KnowledgeBulkInformedChoice = (
                    KnowledgeInformedChoice(
                        knowledge_uid=ku_uids[0],
                        choice_uid=choice.uid,
                        user_uid=choice.user_uid,
                        choice_title=choice.title,
                    )
                )
            else:
                knowledge_event = KnowledgeBulkInformedChoice(
                    knowledge_uids=tuple(ku_uids),
                    choice_uid=choice.uid,
                    user_uid=choice.user_uid,
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

    async def get_user_choices(self, user_uid: UserUID) -> Result[list[Choice]]:
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
            return Result.fail(uids_result)

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

    @with_error_handling("update_choice", error_type="database", uid_param="choice_uid")
    async def update_choice(self, choice_uid: str, intent: ChoiceUpdateIntent) -> Result[Choice]:
        """Update a choice's node properties (ADR-066 typed update contract).

        Materializes the intent to a partial patch once, validated and written through the
        inherited CRUD ``update`` (BaseService → ``_validate_update`` → ``backend.update``),
        then publishes ``ChoiceUpdated``. Choices carry no edge fields on the update path,
        so the intent's ``to_changes()`` is written wholesale — there is nothing to split off.

        Unlike the prior implementation (which wrote ``backend.update`` directly and skipped
        validation), this keeps ``super().update`` so ``_validate_update`` — decision
        immutability for DECIDED/EVALUATED choices, option-count floor — runs on every
        property update.

        Args:
            choice_uid: UID of the choice
            intent: Typed ``ChoiceUpdateIntent`` — only its set fields are written

        Returns:
            Result containing updated Choice

        Events Published:
            - ChoiceUpdated: when any field changes, so user-context caches invalidate and
              decision-quality recalculates even for plain property edits
        """
        changes = intent.to_changes()
        # Snapshot the intended fields now: the backend stamps updated_at in place, so
        # reading the dict after the write would leak that bump into the event payload.
        updated_fields = dict(changes)

        result: Result[Choice] = await super().update(choice_uid, intent)
        if result.is_error:
            return result

        choice = result.value

        if updated_fields:
            event = ChoiceUpdated(
                choice_uid=choice.uid,
                user_uid=choice.user_uid,
                updated_fields=updated_fields,
            )
            await publish_event(self.event_bus, event, self.logger)

        # Post-persist embedding refresh (ADR-074) — only when a text field changed
        await publish_embedding_requested(
            self.event_bus,
            EntityType.CHOICE,
            choice,
            self.logger,
            changed_fields=updated_fields,
        )

        return Result.ok(choice)

    async def delete_choice(self, choice_uid: str) -> Result[bool]:
        """
        Delete a choice.

        Args:
            choice_uid: UID of the choice

        Returns:
            Result indicating success
        """
        # Get choice before deletion (for event)
        choice_result = await self.get_choice(choice_uid)
        choice_description: str | None = None
        user_uid = "unknown"
        if choice_result.is_ok:
            choice = choice_result.value
            if choice:
                choice_description = choice.description or choice.title
                user_uid = choice.user_uid or "unknown"

        result = await self.backend.delete(choice_uid, cascade=True)
        if result.is_error:
            return result

        # Publish ChoiceDeleted event (event-driven architecture)
        event = ChoiceDeleted(
            choice_uid=choice_uid,
            user_uid=UserUID(user_uid),
            choice_description=choice_description or choice_uid,
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
            return Result.fail(existing_result)

        existing = existing_result.value
        if not existing:
            return Result.fail(Errors.not_found(resource="Choice", identifier=choice_uid))
        assert isinstance(existing, Choice)

        # Create updated DTO with outcome data
        dto = existing.to_dto()
        dto.actual_outcome = evaluation.actual_outcome
        dto.satisfaction_score = evaluation.satisfaction_score
        dto.lessons_learned = evaluation.lessons_learned

        # raw-write: full-DTO entity replace (not a partial patch), publishing its own
        # ChoiceOutcomeRecorded provenance event. ADR-066's ChoiceUpdateIntent models
        # partial property patches, not whole-entity persistence — dto.to_dict() is the
        # honest shape here.
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
        # raw-write: decision finalization. Bypasses the validated/event-firing service
        # contract (ChoiceUpdateIntent → update_choice) on purpose — this path publishes
        # its own ChoiceMade below with the selected-option + confidence provenance that
        # the generic update_choice cannot express. A plain dict literal is the honest
        # type here.
        updates: Neo4jProperties = {
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
            except (AttributeError, TypeError):  # fmt: skip
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
            return Result.fail(existing_result)

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
        dto.options = cast("list[dict[str, Any]]", list(updated_options))

        # raw-write: full-DTO entity replace after rebuilding the options tuple (not a
        # partial property patch). ADR-066's ChoiceUpdateIntent does not model option
        # mutation or whole-entity persistence; this path fires its own ChoiceUpdated
        # below with the option-level provenance.
        update_result = await self.backend.update(choice_uid, dto.to_dict())
        if update_result.is_error:
            return Result.fail(update_result)

        choice = self._to_domain_model(update_result.value, ChoiceDTO, Choice)

        # Publish ChoiceUpdated event
        event = ChoiceUpdated(
            choice_uid=choice.uid,
            user_uid=choice.user_uid,
            updated_fields={"options": f"Added option: {title}"},
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
            return Result.fail(existing_result)

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
        dto.options = cast("list[dict[str, Any]]", list(updated_options))

        # raw-write: full-DTO entity replace after rebuilding the options tuple (not a
        # partial property patch). ADR-066's ChoiceUpdateIntent does not model option
        # mutation or whole-entity persistence; this path fires its own ChoiceUpdated
        # below with the option-level provenance.
        update_result = await self.backend.update(choice_uid, dto.to_dict())
        if update_result.is_error:
            return Result.fail(update_result)

        choice = self._to_domain_model(update_result.value, ChoiceDTO, Choice)

        # Publish ChoiceUpdated event
        event = ChoiceUpdated(
            choice_uid=choice.uid,
            user_uid=choice.user_uid,
            updated_fields={"options": f"Updated option: {option_uid}"},
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
            return Result.fail(existing_result)

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
        dto.options = cast("list[dict[str, Any]]", list(updated_options))

        # raw-write: full-DTO entity replace after rebuilding the options tuple (not a
        # partial property patch). ADR-066's ChoiceUpdateIntent does not model option
        # mutation or whole-entity persistence; this path fires its own ChoiceUpdated
        # below with the option-level provenance.
        update_result = await self.backend.update(choice_uid, dto.to_dict())
        if update_result.is_error:
            return Result.fail(update_result)

        choice = self._to_domain_model(update_result.value, ChoiceDTO, Choice)

        # Publish ChoiceUpdated event
        event = ChoiceUpdated(
            choice_uid=choice.uid,
            user_uid=choice.user_uid,
            updated_fields={"options": f"Removed option: {option_uid}"},
        )
        await publish_event(self.event_bus, event, self.logger)

        self.logger.info(f"Removed option {option_uid} from choice {choice_uid}")
        return Result.ok(choice)

    # ========================================================================
    # HIERARCHICAL RELATIONSHIPS (2026-01-30 - Flat UID, Rich Structure)
    # Delegated to ChoicesBackend via _HierarchyMixin (2026-03-24)
    # ========================================================================

    async def create_subchoice_relationship(
        self,
        parent_uid: str,
        subchoice_uid: str,
        order: int = 0,
        depends_on_outcome: str | None = None,
    ) -> Result[bool]:
        """Create bidirectional HAS_SUBCHOICE/SUBCHOICE_OF relationship with cycle detection."""
        forward_props: dict[str, Any] = {"order": order}
        if depends_on_outcome is not None:
            forward_props["depends_on_outcome"] = depends_on_outcome
        return await self.backend.create_hierarchy_relationship(
            parent_uid, subchoice_uid, forward_props
        )

    async def remove_subchoice_relationship(
        self, parent_uid: str, subchoice_uid: str
    ) -> Result[bool]:
        """Remove bidirectional HAS_SUBCHOICE/SUBCHOICE_OF relationship."""
        return await self.backend.remove_hierarchy_relationship(parent_uid, subchoice_uid)

    # ========================================================================
    # QUERY LAYER — Cypher-level filtering for get_filtered_context
    # ========================================================================

    async def get_stats_for_user(self, user_uid: UserUID) -> Result[ChoiceStats]:
        """Count choice stats via Cypher COUNT — no entity deserialization."""
        return await self.backend.get_stats_for_user(user_uid)

    # get_for_user_filtered: inherited from SearchOperationsMixin, driven by
    # the status_filters map in _config above.
