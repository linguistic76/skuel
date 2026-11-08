"""
Choices Core Service - CRUD Operations
=======================================

Handles basic CRUD operations for choices.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.events import publish_event
from core.events.choice_events import (
    ChoiceCreated,
    ChoiceDeleted,
    ChoiceMade,
    ChoiceOutcomeRecorded,
    ChoiceUpdated,
)
from core.events.embedding_publisher import publish_embedding_requested
from core.events.knowledge_credit_publisher import KnowledgeCreditSource, publish_knowledge_credit
from core.models.choice.choice import Choice, outcome_quality
from core.models.choice.choice_dto import ChoiceDTO
from core.models.choice.choice_option import ChoiceOption
from core.models.choice.choice_update_intent import ChoiceUpdateIntent
from core.models.enums.choice_enums import ChoiceType
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.relationship_names import RelationshipName
from core.models.type_hints import Neo4jProperties, UserUID
from core.models.update_contracts import StatusGuardedOutcome, StatusWriteGuard
from core.ports.query_types import ChoiceStats
from core.services.base_service import BaseService
from core.services.completion_stamp import status_transition_guard, stranded_stamp_error
from core.services.conversion_service import ConversionServiceV2
from core.services.domain_config import create_activity_domain_config
from core.services.mixins.hierarchy_read_mixin import HierarchyReadMixin
from core.services.mixins.link_edge_guard import (
    KNOWLEDGE_LABELS,
    LinkEdge,
    keep_permitted_link_edges,
)
from core.services.whole_set_read import find_all_by
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import ErrorContext, Errors, Result
from core.utils.sort_functions import make_attribute_sort_key
from core.utils.type_converters import get_enum_value
from core.utils.uid_generator import UIDGenerator
from core.utils.zone_context import current_zone

if TYPE_CHECKING:
    from core.models.choice.choice_request import (
        ChoiceCreateRequest,
        ChoiceEvaluationRequest,
        ChoiceOptionRequest,
    )
    from core.ports.domain_protocols import ChoicesOperations


def _decision_edit_refusal(
    choice: Choice,
    # boundary: a materialized update patch (``ChoiceUpdateIntent.to_changes()``) — genuinely
    # heterogeneous, and NOT ``Neo4jProperties`` (an intent patch can carry a bare ``dict`` or
    # a ``list[dict]``, neither a ``Neo4jValue``). Only ``status``'s value is read, and
    # compared with a canonical value; every other use is a key test.
    changes: Mapping[str, Any],
) -> ErrorContext | None:
    """Business Rule 1: a decided choice's decision is a historical record.

    Of what an update may carry (``ChoiceUpdateIntent``), two fields touch the decision:

    - ``choice_type`` is frozen with the options, while ``Choice.options_open`` says
      they may not change (decided, or in a decided status);
    - ``status`` may not go back to ``draft`` once a decision is recorded
      (``decided_at``). Any other legal status is open to it: a decided choice is
      completed or archived, and reopened, as any activity is.

    The options and the selected option are not on the intent: the option writers
    and ``make_decision`` hold their own rules.

    Asked of the choice as it stands under its lock (``update_choice``), so a decision
    recorded a moment before the write is the one this rule sees.

    Returns:
        ``None`` when the update may be written, otherwise the refusal.
    """
    if "choice_type" in changes and not choice.options_open():
        return Errors.validation(
            message="Cannot change the type of a decided choice. Decisions are historical "
            "records. Create a new choice to reconsider.",
            field="choice_type",
            value=get_enum_value(choice.status),
        )
    if changes.get("status") == EntityStatus.DRAFT.value and choice.decided_at is not None:
        return Errors.validation(
            message="A decided choice cannot go back to draft. Decisions are historical "
            "records. Create a new choice to reconsider.",
            field="status",
            value=get_enum_value(choice.status),
        )
    return None


@dataclasses.dataclass(frozen=True)
class _ChoiceRewrite:
    """A choice write planned from the choice under its lock (``GuardedWritePlan``)."""

    # boundary: pre-serialization patch — ``options`` is a list of ``ChoiceOption``
    # dataclasses, JSON-encoded at the write (``to_neo4j_node``) as the create door's are.
    updates: dict[str, Any]
    guard: StatusWriteGuard


def _options_rewrite(options: list[ChoiceOption]) -> _ChoiceRewrite:
    """The write of a choice's whole option list, and nothing else.

    It names no status, so no status rule applies to it: the option rules are asked of
    the locked choice by the planner.
    """
    return _ChoiceRewrite(updates={"options": options}, guard=StatusWriteGuard())


def _options_frozen_error(choice: Choice, action: str) -> ErrorContext | None:
    """The refusal of an option edit on a decided choice (``Choice.options_open``), or
    ``None`` when its options may change."""
    if choice.options_open():
        return None
    return Errors.validation(
        message=f"Cannot {action} a decided choice. Decisions are historical records.",
        field="status",
        value=get_enum_value(choice.status),
    )


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
        and by ``remove_option`` from then on.

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
        """Validate a choice update against the domain's rules.

        One rule: a decided choice's decision is a historical record
        (``_decision_edit_refusal``). ``update_choice`` asks it of the choice it holds
        under the lock. The option-count floor belongs to ``remove_option``, the one
        write that takes an option away.

        Args:
            current: The choice the update would be written over
            updates: Typed ``ChoiceUpdateIntent`` of proposed changes

        Returns:
            None if valid, Result.fail() with validation error if invalid
        """
        refusal = _decision_edit_refusal(current, updates.to_changes())
        if refusal is not None:
            return Result.fail(refusal)
        return Result.ok(None)

    async def create(self, entity: Choice) -> Result[Choice]:
        """THE Choices create primitive: validate → persist → publish.

        Both create doors land here, so the domain's creation rules cannot be
        skipped by picking one door over the other:

        - the entity door (``ChoicesService.create``) delegates here — the generated
          CRUD route entered that way until it was bound to ``create_choice``
          (``CRUDRouteConfig.request_create_method``);
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
            # the entity door too — not just for requests, whose domain always
            # defaults. ChoiceCreated.domain is a non-optional str.
            domain=choice.domain.value if choice.domain else "",
            urgency=choice.priority or "medium",
        )
        await publish_event(self.event_bus, event, self.logger)

        # Post-persist embedding refresh (ADR-074) — the background worker embeds async
        await publish_embedding_requested(self.event_bus, EntityType.CHOICE, choice, self.logger)

    async def _write_link_edges(self, choice: Choice, request: ChoiceCreateRequest) -> list[str]:
        """GRAPH-NATIVE: turn the request's knowledge links into edges, in one batch.

        ``informed_by_knowledge_uids`` → INFORMED_BY_KNOWLEDGE, declared ``outgoing``
        from the choice, so the choice is the source of every tuple. Edges live in the
        graph, never on the Choice or its DTO; read back by the user context's choices
        statement (``choice_knowledge_informed``).

        ADMISSION: every uid is request input, so each is checked for existence, OWNER
        and KIND before it becomes an edge — ``keep_permitted_link_edges``. The field
        name declares the kind: a knowledge list means Kus (``KNOWLEDGE_LABELS``, see
        there for why the atom and not the PathStep). The registry cannot make that
        check — its Choice spec for INFORMED_BY_KNOWLEDGE names the target ``Entity`` —
        and the batch is all-or-nothing, so an unadmitted dangling uid would refuse every
        valid link in the same request.

        Returns:
            The knowledge uids actually WRITTEN, deduplicated, in request order — the
            caller announces substance from these, never from what was requested, so a
            refused or dangling link cannot claim knowledge informed a choice that no
            edge backs.

        A failure is logged, not propagated — the choice itself is created.
        """
        candidates = [
            LinkEdge(
                (choice.uid, knowledge_uid, RelationshipName.INFORMED_BY_KNOWLEDGE.value, None),
                other_uid=knowledge_uid,
                allowed_labels=KNOWLEDGE_LABELS,
            )
            for knowledge_uid in request.informed_by_knowledge_uids
        ]
        if not candidates:
            return []

        relationships = await keep_permitted_link_edges(
            self.backend,
            candidates=candidates,
            subject_uid=choice.uid,
            owner_uid=choice.user_uid,
            logger=self.logger,
        )
        if not relationships:
            return []

        batch_result = await self.backend.create_relationships_batch(relationships)
        if batch_result.is_error:
            self.logger.warning(
                "Failed to create %d knowledge relationships for choice %s: %s",
                len(relationships),
                choice.uid,
                batch_result.error,
            )
            # The batch is all-or-nothing, so a failure means NOTHING was written.
            # Reporting the admitted uids here would announce substance for edges that
            # do not exist.
            return []

        # DEDUPED: the batch MERGEs, so a uid repeated in the request yields ONE edge —
        # but the bulk substance event UNWINDs what it is given, crediting the knowledge
        # once per row. dict.fromkeys keeps the order.
        return list(dict.fromkeys(target_uid for _src, target_uid, _rel, _props in relationships))

    async def _publish_knowledge_substance(self, choice: Choice, knowledge_uids: list[str]) -> None:
        """Announce the knowledge that informed the choice: single-item for 1 Ku, bulk for 2+.

        Driven by the uids ``_write_link_edges`` actually WROTE, never by what the request
        asked for. The substance pipeline credits knowledge per uid it is handed, so
        announcing a refused, dangling or cross-user link would claim a choice was
        informed by knowledge that no INFORMED_BY_KNOWLEDGE edge backs.

        Published AFTER ``ChoiceCreated``: these reach only substance handlers and do not
        invalidate the user context, so they carry no ordering constraint of their own —
        but they must not precede the announcement of the choice they describe. Through
        ``publish_knowledge_credit``.
        """
        await publish_knowledge_credit(
            self.event_bus,
            KnowledgeCreditSource(
                entity_type=EntityType.CHOICE,
                uid=choice.uid,
                user_uid=choice.user_uid,
                title=choice.title,
            ),
            knowledge_uids,
            self.logger,
        )

    async def create_choice(
        self, choice_request: ChoiceCreateRequest, user_uid: UserUID
    ) -> Result[Choice]:
        """Create a choice from a request: validate + persist, write its knowledge
        edges, announce it, then credit the knowledge those edges name.

        Only this door holds the request, so only this door can write
        ``informed_by_knowledge_uids`` — the list rides on no ``Choice`` field, and the
        entity door (``create``) cannot carry it.

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

        # Build the entity with the SAME converter the generated CRUD route used when
        # it converted for itself (it now enters here), so the doors cannot drift
        # on which request fields survive. Hand-listing
        # them onto ChoiceDTO.create_choice is what dropped options, choice_type,
        # decision_criteria, constraints, stakeholders and tags here: the factory
        # takes **kwargs, so every omission was silent.
        uid = UIDGenerator.generate_random_uid("choice")
        entity = ConversionServiceV2.choice_create_to_pure(choice_request, uid, user_uid=user_uid)

        # Validate + persist, but hold the events back until the knowledge edges below
        # are written (see _publish_created). NOT _create_and_convert, which bypasses
        # _validate_create entirely.
        create_result = await self._create_validated(entity)
        if create_result.is_error:
            return create_result

        choice = create_result.value

        # Edges first, then the announcement: ChoiceCreated drives the user-context
        # rebuild, which reads those edges back out of the graph (see _publish_created).
        written_knowledge_uids = await self._write_link_edges(choice, choice_request)
        await self._publish_created(choice)
        await self._publish_knowledge_substance(choice, written_knowledge_uids)

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
        result = await find_all_by(self.backend, self.logger, "Choice list", user_uid=user_uid)
        if result.is_error:
            return result

        choices = self._to_domain_models(result.value, ChoiceDTO, Choice)
        return Result.ok(choices)

    @with_error_handling("update_choice", error_type="database", uid_param="choice_uid")
    async def update_choice(self, choice_uid: str, intent: ChoiceUpdateIntent) -> Result[Choice]:
        """Update a choice's node properties (ADR-066 typed update contract).

        Materializes the intent to a partial patch and writes it exactly once, planned
        from the choice under its lock (``_rewrite_choice``), then publishes
        ``ChoiceUpdated``. Choices carry no edge fields on the update path, so the
        intent's ``to_changes()`` is written wholesale. Status transitions are validated
        against the Choice lifecycle and completion stamping (``completed_at``) is
        applied here — the domain's one update chokepoint (``core.services.completion_stamp``):
        completing stamps it, reopening clears it.

        Two rules can refuse the write, each where it can be judged:

        - **decision immutability** (``_validate_update``) is asked of the locked choice,
          so it reads ``decided_at`` as well as the status: a decision recorded a moment
          earlier by ``make_decision``, which writes past this method, is the one it
          sees, and an archived decided choice is still decided. A refusal writes nothing.
        - **the bare-stamp gate** (``completed_at`` with no status needs a completed
          prior) is a condition of the guarded write (ADR-087), reported back as
          ``applied=False``.

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

        # Status-target validation + completion stamping, expressed as conditions the
        # write evaluates against the prior it reads under the node's lock (ADR-087).
        # Judged from the patch alone, so an illegal target is refused before any read.
        guard_result = status_transition_guard(EntityType.CHOICE, changes, zone=current_zone())
        if guard_result.is_error:
            return Result.fail(guard_result)
        guard = guard_result.value
        if not changes and not guard.has_patches():
            return Result.fail(Errors.validation("No updates provided", field="updates"))

        def plan(choice: Choice) -> Result[_ChoiceRewrite]:
            validation = self._validate_update(choice, intent)
            if validation.is_error:
                return Result.fail(validation)
            return Result.ok(_ChoiceRewrite(updates=dict(changes), guard=guard))

        rewrite = await self._rewrite_choice(choice_uid, plan)
        if rewrite.is_error:
            return Result.fail(rewrite)
        outcome = rewrite.value
        if not outcome.applied:
            # The guard's one refuse condition is the bare-stamp gate.
            return Result.fail(stranded_stamp_error(EntityType.CHOICE, outcome.prior_status))

        choice = outcome.entity

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
        """Record how a decided choice turned out: satisfaction, what happened, lessons.

        Refused, with the choice unchanged, when the choice is not decided
        (``Choice.is_decided``): an outcome is what a decision led to. A decided choice
        takes one open or closed, and a later one replaces it.

        The write carries ``satisfaction_score``, ``actual_outcome`` and
        ``lessons_learned`` alone, planned from the choice under its lock
        (``_rewrite_choice``), so it neither writes a status nor loses a close made
        at the same moment.

        Args:
            choice_uid: UID of the choice
            evaluation: The outcome: satisfaction on the 1-5 scale, what happened, and
                the lessons, one per item

        Returns:
            Result containing the choice as written

        Events Published:
            - ChoiceOutcomeRecorded: the outcome's quality (``outcome_quality``, 0.0-1.0
              from the satisfaction) and the lessons, one per line
            - EmbeddingRequested (ADR-074): ``actual_outcome`` is embedded
        """
        # boundary: pre-serialization patch — ``lessons_learned`` is a ``list[str]``.
        updates: dict[str, Any] = {
            "satisfaction_score": evaluation.satisfaction_score,
            "actual_outcome": evaluation.actual_outcome,
            "lessons_learned": list(evaluation.lessons_learned),
        }

        def record(choice: Choice) -> Result[_ChoiceRewrite]:
            if not choice.is_decided():
                return Result.fail(
                    Errors.validation(
                        message="Decide this choice before recording how it turned out.",
                        field="status",
                        value=get_enum_value(choice.status),
                    )
                )
            return Result.ok(_ChoiceRewrite(updates=dict(updates), guard=StatusWriteGuard()))

        rewrite = await self._rewrite_choice(choice_uid, record)
        if rewrite.is_error:
            return Result.fail(rewrite)
        choice = rewrite.value.entity

        event = ChoiceOutcomeRecorded(
            choice_uid=choice.uid,
            user_uid=choice.user_uid,
            outcome_quality=outcome_quality(evaluation.satisfaction_score),
            lessons_learned="\n".join(evaluation.lessons_learned) or None,
        )
        await publish_event(self.event_bus, event, self.logger)

        # Post-persist embedding refresh (ADR-074). This path writes ``actual_outcome``,
        # which EMBEDDING_FIELD_MAPS[CHOICE] now names — without this the stored vector
        # would stay stale until an unrelated text edit or a manual backfill. Passed
        # explicitly rather than via ``changed_fields``: the outcome write is exactly the
        # embeddable change, so there is nothing to filter.
        await publish_embedding_requested(self.event_bus, EntityType.CHOICE, choice, self.logger)

        return Result.ok(choice)

    async def make_decision(
        self,
        choice_uid: str,
        selected_option_uid: str,
        decision_rationale: str | None = None,
        confidence: float = 0.5,
    ) -> Result[Choice]:
        """Record the decision on a choice: one of its own options, selected once.

        Refused, with the choice unchanged, when the choice is already decided
        (decisions are historical records: a new choice reconsiders), when it holds
        fewer than two options, or when ``selected_option_uid`` is not one of them.
        Each refusal is decided from the choice as it stands under its lock
        (``rewrite_choice_under_lock``), so an option removed or a decision recorded a
        moment earlier cannot slip past it.

        The write sets ``selected_option_uid``, ``decision_rationale`` and
        ``decided_at``, and moves the choice to ACTIVE (a decided choice stays ACTIVE
        until it is completed) through ``status_transition_guard``, the domain's one
        status rule. ``confidence`` is not stored: it rides on the ``ChoiceMade``
        event this publishes, beside the rationale.

        Args:
            choice_uid: UID of the choice
            selected_option_uid: UID of one of the choice's options
            decision_rationale: Optional reasoning for the option selected
            confidence: Confidence in the decision (0.0-1.0), carried on the event

        Returns:
            Result containing the decided Choice
        """
        # raw-write: decision finalization. Bypasses the validated/event-firing service
        # contract (ChoiceUpdateIntent → update_choice) on purpose — this path publishes
        # its own ChoiceMade below with the selected-option + confidence provenance that
        # the generic update_choice cannot express.
        updates: Neo4jProperties = {
            "selected_option_uid": selected_option_uid,
            "decision_rationale": decision_rationale,
            "decided_at": datetime.now().isoformat(),
            "status": EntityStatus.ACTIVE.value,
        }
        # The prior a decision can land on is undecided (DRAFT, or an ARCHIVED choice
        # never decided), so the reopen clear this guard carries for a COMPLETED prior
        # never applies; it is the shared rule all the same, and refuses an illegal
        # target, which ACTIVE never is. It carries no refuse condition.
        guard_result = status_transition_guard(EntityType.CHOICE, updates, zone=current_zone())
        if guard_result.is_error:
            return Result.fail(guard_result)
        guard = guard_result.value

        def decide(choice: Choice) -> Result[_ChoiceRewrite]:
            if choice.is_decided():
                return Result.fail(
                    Errors.validation(
                        message="This choice is already decided. Decisions are historical "
                        "records. Create a new choice to reconsider.",
                        field="status",
                        value=get_enum_value(choice.status),
                    )
                )
            if len(choice.options) < 2:
                return Result.fail(
                    Errors.validation(
                        message="Add at least two options before deciding.",
                        field="options",
                        value=len(choice.options),
                    )
                )
            if selected_option_uid not in {option.uid for option in choice.options}:
                return Result.fail(
                    Errors.validation(
                        message="The selected option is not one of this choice's options.",
                        field="selected_option_uid",
                        value=selected_option_uid,
                    )
                )
            return Result.ok(_ChoiceRewrite(updates=dict(updates), guard=guard))

        rewrite = await self._rewrite_choice(choice_uid, decide)
        if rewrite.is_error:
            return Result.fail(rewrite)
        choice = rewrite.value.entity

        event = ChoiceMade(
            choice_uid=choice.uid,
            user_uid=choice.user_uid,
            selected_option=selected_option_uid,
            confidence=confidence,
            metadata={"rationale": decision_rationale} if decision_rationale else None,
        )
        await publish_event(self.event_bus, event, self.logger)

        return Result.ok(choice)

    async def _rewrite_choice(
        self,
        choice_uid: str,
        decide: Callable[[Choice], Result[_ChoiceRewrite]],
    ) -> Result[StatusGuardedOutcome[Choice]]:
        """Plan one rewrite from the choice under its lock and write it; the write's outcome.

        ``decide`` reads the locked choice and answers the write, or the refusal its
        caller owes the client; a refusal writes nothing. A choice that does not exist
        is the backend's not found. The outcome is ``applied`` unless the planned guard
        carries a refuse condition the prior met (only ``update_choice``'s can).
        """
        refusals: list[Result[_ChoiceRewrite]] = []

        def plan(choice: Choice) -> _ChoiceRewrite | None:
            decided = decide(choice)
            if decided.is_error:
                refusals.append(decided)
                return None
            return decided.value

        result = await self.backend.rewrite_choice_under_lock(choice_uid, plan)
        if result.is_error:
            return Result.fail(result)
        if result.value is None:
            if refusals:
                return Result.fail(refusals[0])
            return Result.fail(
                Errors.system(message=f"The rewrite of choice {choice_uid} wrote nothing.")
            )
        return Result.ok(result.value.outcome)

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
    # Each option write is planned from the choice under its lock and carries the
    # options alone: it can neither lose an option written at the same moment nor
    # undo a decision recorded first.

    async def add_option(self, choice_uid: str, option: ChoiceOptionRequest) -> Result[Choice]:
        """
        Append one option to an undecided choice.

        Business Rules:
        1. A decided choice's options are part of the decision (a historical record)
        2. Binary choices can only have exactly 2 options

        The option is built by ``ConversionServiceV2.choice_option_from_request``, the
        builder the create door uses, so the two store an option alike.

        Args:
            choice_uid: UID of the choice
            option: The option to add

        Returns:
            Result containing updated Choice with new option
        """
        new_option = ConversionServiceV2.choice_option_from_request(option)

        def append(choice: Choice) -> Result[_ChoiceRewrite]:
            frozen = _options_frozen_error(choice, "add options to")
            if frozen is not None:
                return Result.fail(frozen)
            if choice.choice_type == ChoiceType.BINARY and len(choice.options) >= 2:
                return Result.fail(
                    Errors.validation(
                        message="Binary choices can only have exactly 2 options",
                        field="choice_type",
                        value=choice.choice_type.value,
                    )
                )
            return Result.ok(_options_rewrite([*choice.options, new_option]))

        rewrite = await self._rewrite_choice(choice_uid, append)
        if rewrite.is_error:
            return Result.fail(rewrite)
        choice = rewrite.value.entity

        event = ChoiceUpdated(
            choice_uid=choice.uid,
            user_uid=choice.user_uid,
            updated_fields={"options": f"Added option: {new_option.title}"},
        )
        await publish_event(self.event_bus, event, self.logger)

        self.logger.info(f"Added option '{new_option.title}' to choice {choice_uid}")
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
        1. A decided choice's options are part of the decision (a historical record)
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

        def revise(opt: ChoiceOption) -> ChoiceOption:
            return ChoiceOption(
                uid=opt.uid,
                title=title if title is not None else opt.title,
                description=description if description is not None else opt.description,
                feasibility_score=(
                    feasibility_score if feasibility_score is not None else opt.feasibility_score
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
                    estimated_duration if estimated_duration is not None else opt.estimated_duration
                ),
                dependencies=tuple(dependencies) if dependencies is not None else opt.dependencies,
                tags=tuple(tags) if tags is not None else opt.tags,
            )

        def replace(choice: Choice) -> Result[_ChoiceRewrite]:
            frozen = _options_frozen_error(choice, "update options in")
            if frozen is not None:
                return Result.fail(frozen)
            if option_uid not in {opt.uid for opt in choice.options}:
                return Result.fail(Errors.not_found(resource="ChoiceOption", identifier=option_uid))
            return Result.ok(
                _options_rewrite(
                    [revise(opt) if opt.uid == option_uid else opt for opt in choice.options]
                )
            )

        rewrite = await self._rewrite_choice(choice_uid, replace)
        if rewrite.is_error:
            return Result.fail(rewrite)
        choice = rewrite.value.entity

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
        1. A decided choice's options are part of the decision (a historical record)
        2. Cannot remove options if it would leave less than 2 options
        3. Cannot remove the selected option
        4. Option must exist in the choice

        Args:
            choice_uid: UID of the choice
            option_uid: UID of the option to remove

        Returns:
            Result containing updated Choice
        """

        def drop(choice: Choice) -> Result[_ChoiceRewrite]:
            frozen = _options_frozen_error(choice, "remove options from")
            if frozen is not None:
                return Result.fail(frozen)
            if choice.selected_option_uid == option_uid:
                return Result.fail(
                    Errors.validation(
                        message="Cannot remove the selected option",
                        field="selected_option_uid",
                        value=option_uid,
                    )
                )
            remaining = [opt for opt in choice.options if opt.uid != option_uid]
            if len(remaining) == len(choice.options):
                return Result.fail(Errors.not_found(resource="ChoiceOption", identifier=option_uid))
            if len(remaining) < 2:
                return Result.fail(
                    Errors.validation(
                        message="Choice must have at least 2 options. Cannot remove.",
                        field="options",
                        value=len(remaining),
                    )
                )
            return Result.ok(_options_rewrite(remaining))

        rewrite = await self._rewrite_choice(choice_uid, drop)
        if rewrite.is_error:
            return Result.fail(rewrite)
        choice = rewrite.value.entity

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

    # get_all_for_user: inherited from SearchOperationsMixin.
