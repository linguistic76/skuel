"""
Goals Core Service
==================

Handles basic CRUD operations for goals.

Responsibilities:
- Basic goal retrieval (get_user_goals)
- Delegates create/update/delete to backend via BaseService
- Publishes domain events (GoalCreated, GoalUpdated, GoalAchieved, GoalAbandoned).
  GoalProgressUpdated is owned by GoalsProgressService (progress-propagation provenance).

  RelationshipRegistry (GOALS_CONFIG). Shared-neighbor pattern for
  related_goals is now defined in the registry.
  See: /core/models/relationship_registry.py
- v2.1.0 (2025-11-28): Eliminated APOC dependency.
- v2.0.0 (2025-11-05): Initial facade pattern implementation
"""

import dataclasses
from datetime import date, datetime
from typing import TYPE_CHECKING, Final

from core.models.relationship_names import RelationshipName
from core.models.type_hints import UserUID

if TYPE_CHECKING:
    from core.models.goal.goal_request import GoalCreateRequest

from core.events import publish_event
from core.events.embedding_publisher import publish_embedding_requested
from core.events.goal_events import (
    GoalAbandoned,
    GoalAchieved,
    GoalCreated,
    GoalUpdated,
)
from core.models.enums import EntityStatus
from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.goal.goal import Goal
from core.models.goal.goal_dto import GoalDTO
from core.models.goal.goal_update_intent import GoalUpdateIntent
from core.ports import get_enum_value
from core.ports.domain_protocols import GoalsOperations
from core.ports.query_types import GoalStats
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.mixins.hierarchy_read_mixin import HierarchyReadMixin
from core.services.mixins.link_edge_guard import (
    KNOWLEDGE_LABELS,
    LinkEdge,
    keep_permitted_link_edges,
)
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

# Weight the entity door stamps on HAS_SUBGOAL. progress_weight is an EDGE property that
# no Goal field carries, so a caller handing create() a ready entity cannot supply one;
# the generated route, bound to create_goal, forwards the client's value. Pinned to
# GoalCreateRequest.progress_weight's own default so the two doors agree on every request
# that leaves it unset; test_goal_habit_create_edges.py asserts that agreement.
DEFAULT_PROGRESS_WEIGHT: Final = 1.0


class GoalsCoreService(
    HierarchyReadMixin[GoalsOperations, Goal],
    BaseService[GoalsOperations, Goal, GoalUpdateIntent],
):
    """
    Core CRUD operations for goals.

    This service provides basic goal operations:
    - get_user_goals: Retrieve all goals for a user
    - Inherits: create, get, update, delete from BaseService
    - Publishes domain events for all state changes

    Event-Driven Architecture:
    - Publishes GoalCreated on creation
    - Publishes GoalUpdated on every property update (cache invalidation)
    - Publishes GoalAchieved when goal completed
    - Publishes GoalAbandoned when goal cancelled
    """

    def __init__(
        self,
        backend: GoalsOperations,
        event_bus=None,
    ) -> None:
        """
        Initialize goals core service.

        Args:
            backend: Protocol-based backend for goal operations
            event_bus: Event bus for publishing domain events (optional)
        """
        super().__init__(backend, "goals")
        self.logger = get_logger("skuel.services.goals.core")  # type: ignore[assignment]  # structlog BoundLogger
        self.event_bus = event_bus

    # ========================================================================
    # EMBEDDING HELPERS (Async Background Generation - January 2026)
    # ========================================================================

    # ========================================================================
    # DOMAIN-SPECIFIC CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================

    _config = create_activity_domain_config(
        dto_class=GoalDTO,
        model_class=Goal,
        domain_name="goals",
        date_field="target_date",
        completed_statuses=(EntityStatus.COMPLETED.value,),
        status_filters={
            "active": {"status": "active"},
            "completed": {"status": "completed"},
            "paused": {"status": "paused"},
        },
        entity_label="Entity",
    )
    # ========================================================================
    # DOMAIN-SPECIFIC VALIDATION HOOKS
    # ========================================================================

    def _validate_create(self, goal: Goal) -> Result[None]:
        """
        Validate goal creation with business rules.

        Business Rules:
        1. Target date must not precede start date (timeline consistency)

        A same-day goal is legal. ``GoalCreateRequest`` validates the same pair with
        ``validate_date_after("target_date", "start_date", allow_equal=True)`` and defaults
        ``start_date`` to ``date.today()``, so "finish this today" is a shape the API
        deliberately accepts; this hook rejected it until the rule was reachable, which
        would have made the two layers disagree the moment it started running.

        Args:
            goal: Goal domain model being created

        Returns:
            None if valid, Result.fail() with validation error if invalid
        """

        # Business Rule: Target date must not precede start date (equal is allowed —
        # same bound as the request model's allow_equal=True).
        if goal.target_date and goal.start_date and goal.target_date < goal.start_date:
            return Result.fail(
                Errors.validation(
                    message="Target date cannot be before start date",
                    field="target_date",
                    value=goal.target_date.isoformat(),
                )
            )

        return Result.ok(None)  # All validations passed

    def _validate_update(self, current: Goal, updates: GoalUpdateIntent) -> Result[None]:
        """
        Validate goal updates with business rules.

        Business Rules:
        1. Achievement state immutability: Cannot modify achieved goals
        2. Target date validation: If updating dates, target must be after start

        Note: Goal abandonment protection (checking for active tasks) is handled
        in the update() method since it requires async relationship queries.

        Args:
            current: Current goal state
            updates: Typed ``GoalUpdateIntent`` of proposed changes

        Returns:
            None if valid, Result.fail() with validation error if invalid
        """
        changes = updates.to_changes()

        # Business Rule 1: Achievement state immutability
        # Achieved goals are historical records - modifying them corrupts progress tracking
        if current.status == EntityStatus.COMPLETED:
            return Result.fail(
                Errors.validation(
                    message="Cannot modify achieved goals - they are historical records",
                    field="status",
                    value=current.status.value,
                )
            )

        # Business Rule 2: Target date validation (if both dates present)
        # Check if we're updating either date field
        if "target_date" in changes or "start_date" in changes:
            # Determine new values (use updated value if present, else current)
            new_target = changes.get("target_date", current.target_date)
            new_start = changes.get("start_date", current.start_date)

            # Both must be present and target must be after start
            if new_target and new_start:
                # Handle both date objects and ISO strings
                if isinstance(new_target, str):
                    from datetime import date as date_type

                    new_target = date_type.fromisoformat(new_target)
                if isinstance(new_start, str):
                    from datetime import date as date_type

                    new_start = date_type.fromisoformat(new_start)

                if new_target <= new_start:
                    return Result.fail(
                        Errors.validation(
                            message="Target date must be after start date",
                            field="target_date",
                            value=str(new_target),
                        )
                    )

        return Result.ok(None)  # All validations passed

    # ========================================================================
    # READ OPERATIONS WITH GRAPH CONTEXT
    # ========================================================================
    # NOTE: get_with_context() is inherited from BaseService (January 2026)
    #
    # Uses registry-driven query generation from RelationshipRegistry.
    # The GOALS_CONFIG config includes:
    # - contributing_tasks, contributing_habits (supporting activities)
    # - sub_goals, parent_goal (hierarchy)
    # - required_knowledge, aligned_principles (prerequisites and guidance)
    # - inspired_by_choice (motivation)
    # - milestones (progress tracking)
    # - related_goals (shared-neighbor pattern via FULFILLS_GOAL|SUPPORTS_GOAL)
    # - milestone_progress (calculated in BaseService._parse_context_result)
    #
    # See: /core/models/relationship_registry.py - GOALS_CONFIG
    # See: /core/services/base_service.py - get_with_context()
    # ========================================================================

    async def get_goal(self, goal_uid: str) -> Result[Goal]:
        """
        Get a specific goal by UID.

        Uses BaseService.get() which delegates to BackendOperations.get().
        Not found is returned as Result.fail(Errors.not_found(...)).

        Args:
            goal_uid: Goal UID

        Returns:
            Result[Goal] - success contains Goal, not found is an error
        """
        return await self.get(goal_uid)

    async def get_user_goals(self, user_uid: UserUID) -> Result[list[Goal]]:
        """
        Get all goals for a user, including learning relationships.

        Args:
            user_uid: User identifier

        Returns:
            Result containing list of Goal domain models
        """
        result = await self.backend.find_by(user_uid=user_uid)
        if result.is_error:
            return result

        # Convert to enriched Goal models using helper
        goals = self._to_domain_models(result.value, GoalDTO, Goal)

        self.logger.info(f"Retrieved {len(goals)} goals for user {user_uid}")
        return Result.ok(goals)

    # get_user_items_in_range() is now inherited from BaseService
    # Configured via class attributes: _date_field, _completed_statuses, _dto_class, _model_class
    # CONSOLIDATED (November 27, 2025) - Removed 45 lines of duplicate code

    # ========================================================================
    # EVENT-DRIVEN CRUD OPERATIONS
    # ========================================================================

    async def create(self, entity: Goal) -> Result[Goal]:
        """Validate, persist, link, then announce — THE create primitive for Goals.

        Both doors land here: the entity door (``GoalsService.create``) and ``create_goal``
        — which the generated CRUD route enters through, since it was bound to the
        request door (``CRUDRouteConfig.request_create_method``). ``super().create`` runs ``_validate_create`` (timeline
        consistency), so the rule cannot be reached by one door and missed by the other.

        The hierarchy edge is written here rather than in ``create_goal`` for the same
        reason: ``Goal.fulfills_goal_uid`` is carried by the ENTITY, so both doors can
        write it, and putting the write on the request door alone would have re-opened
        the door-parity gap #963 closed.

        Args:
            entity: Goal to create

        Returns:
            Result containing created Goal

        Events Published:
            - GoalCreated: when the goal is successfully created
            - GoalEmbeddingRequested (ADR-074): post-persist embedding refresh. Fired here
              rather than in ``create_goal`` so route-created goals are embedded too —
              they previously were not.
        """
        return await self._create_with_hierarchy(entity, progress_weight=DEFAULT_PROGRESS_WEIGHT)

    async def _create_with_hierarchy(
        self,
        entity: Goal,
        *,
        progress_weight: float,
        request: "GoalCreateRequest | None" = None,
    ) -> Result[Goal]:
        """The one create path: validate + persist, write the edges, then announce.

        ``progress_weight`` is a property of the HAS_SUBGOAL EDGE, not of ``Goal``, so it
        cannot ride on the entity — only the request door can supply a non-default. It is
        a parameter here rather than a second create path so that the edge has exactly one
        write site. ``request`` is likewise present only for the request door: the three
        link lists are edge-typed and reach no ``Goal`` field, so the entity door has
        nothing to pass (``None``, and no link edges written).
        """
        result: Result[Goal] = await self._create_validated(entity)
        if result.is_error:
            return result

        goal: Goal = result.value  # Type hint to help MyPy
        await self._write_hierarchy_edge(goal, progress_weight)
        if request is not None:
            await self._write_link_edges(goal, request)
        await self._publish_created(goal)
        return result

    async def _create_validated(self, entity: Goal) -> Result[Goal]:
        """Validate and persist, publishing NOTHING.

        Split out from ``create`` so the hierarchy edge below is written before any event
        announces the goal exists — see ``_publish_created`` for why that ordering is
        load-bearing. Mirrors ``ChoicesCoreService._create_validated``.
        """
        return await super().create(entity)

    async def _write_hierarchy_edge(self, goal: Goal, progress_weight: float) -> None:
        """Write (parent)-[:HAS_SUBGOAL {progress_weight}]->(goal) when the goal has a parent.

        ``Goal.fulfills_goal_uid`` (the request's ``parent_goal_uid``) is a node PROPERTY,
        and every hierarchy READER goes to the edge instead: ``GET /api/goals/children`` /
        ``/parent`` / ``/hierarchy`` traverse HAS_SUBGOAL via ``get_children_raw``, the
        user-context MEGA-QUERY collects ``sub_goals`` from it, and the GOALS_CONFIG registry
        resolves ``parent_goal`` / ``sub_goals`` from SUBGOAL_OF. Setting the property
        alone — all creation did until now — left every one of those reads empty for a
        goal the create form's own Hierarchy section had just given a parent.

        OWNERSHIP: the parent must belong to the same user. ``parent_goal_uid`` is
        attacker-controlled request input, and the hierarchy backend matches on UID and
        label alone — so without this check a caller could point a new goal at ANOTHER
        user's goal and have the edge written. The victim's context rebuild starts from
        the goals they OWN and traverses ``HAS_SUBGOAL`` without filtering the child's
        owner, so the attacker's goal would surface in the victim's cached context. The
        one pre-existing door onto this same write, ``POST /api/goals/add-child``, already
        verifies BOTH endpoints (``_register_add_child_route``); creation must not be a way
        around that. (Reported by Codex on #965.)

        A failure is logged, not propagated: the goal itself is legitimate and is created
        either way — only the edge is refused. Tasks' equivalent call makes the same
        choice for its own failures.
        """
        if not goal.fulfills_goal_uid:
            return

        parent_result = await self.get(goal.fulfills_goal_uid)
        if parent_result.is_error:
            self.logger.warning(
                "Skipping subgoal edge for %s: parent %s not found",
                goal.uid,
                goal.fulfills_goal_uid,
            )
            return
        if parent_result.value.user_uid != goal.user_uid:
            self.logger.warning(
                "Refusing cross-user subgoal edge: goal %s (user %s) named parent %s "
                "owned by a different user",
                goal.uid,
                goal.user_uid,
                goal.fulfills_goal_uid,
            )
            return

        edge_result = await self.create_subgoal_relationship(
            parent_uid=goal.fulfills_goal_uid,
            subgoal_uid=goal.uid,
            progress_weight=progress_weight,
        )
        if edge_result.is_error:
            self.logger.warning(
                "Failed to create subgoal relationship %s -> %s: %s",
                goal.fulfills_goal_uid,
                goal.uid,
                edge_result.error,
            )

    async def _write_link_edges(self, goal: Goal, request: "GoalCreateRequest") -> None:
        """GRAPH-NATIVE: turn the request's three link lists into edges, in one batch.

        Each names a registered, READ relationship that nothing was writing at creation
        (GOALS_CONFIG in core/models/relationship_registry.py):

        - ``required_knowledge_uids``  → REQUIRES_KNOWLEDGE, OUTGOING (``knowledge`` key)
        - ``guiding_principle_uids``   → GUIDED_BY_PRINCIPLE, OUTGOING (``principles``)
        - ``supporting_habit_uids``    → SUPPORTS_GOAL, **INCOMING** (``supporting_habits``)

        DIRECTION is not uniform here, unlike Habits' four: ``SUPPORTS_GOAL`` is declared
        incoming, so the HABIT is the source and the goal the target. Writing it the
        other way round persists an edge that every reader misses.

        Readers: the user-context MEGA-QUERY collects ``required_knowledge`` from
        ``(goal)-[:REQUIRES_KNOWLEDGE]->()``, and the GOALS_CONFIG habit tiers
        (``contributing_habits`` and the essentiality-filtered buckets) resolve from
        SUPPORTS_GOAL. Properties are the defaults of the existing single-link writers —
        ``link_goal_to_knowledge`` / ``link_goal_to_principle`` / ``link_goal_to_habit`` —
        so a goal linked at creation is indistinguishable from one linked afterwards.
        ``essentiality`` is load-bearing for the tier reads (see the Habits sibling).

        ADMISSION: every request-supplied UID is checked for OWNER and for KIND before it
        becomes an edge — see ``keep_permitted_link_edges``. Note each ``other_uid``
        below: for ``supporting_habit_uids`` the supplied UID is the edge's SOURCE, so
        reading the target position would check this goal against itself and leave that
        list unguarded. The declared labels come from the field names;
        ``required_knowledge_uids`` means Kus (KNOWLEDGE_LABELS). (Codex, #965.)
        """
        candidates: list[LinkEdge] = []

        candidates.extend(
            LinkEdge(
                (
                    goal.uid,
                    knowledge_uid,
                    RelationshipName.REQUIRES_KNOWLEDGE.value,
                    {"proficiency_required": "intermediate", "priority": 1},
                ),
                other_uid=knowledge_uid,
                allowed_labels=KNOWLEDGE_LABELS,
            )
            for knowledge_uid in request.required_knowledge_uids
        )
        candidates.extend(
            LinkEdge(
                (
                    goal.uid,
                    principle_uid,
                    RelationshipName.GUIDED_BY_PRINCIPLE.value,
                    {"alignment_strength": 1.0},
                ),
                other_uid=principle_uid,
                allowed_labels=frozenset({NeoLabel.PRINCIPLE.value}),
            )
            for principle_uid in request.guiding_principle_uids
        )
        # INCOMING: (habit)-[:SUPPORTS_GOAL]->(goal) — habit first, per GOALS_CONFIG.
        # The habit is therefore the edge's SOURCE and the checked endpoint.
        candidates.extend(
            LinkEdge(
                (
                    habit_uid,
                    goal.uid,
                    RelationshipName.SUPPORTS_GOAL.value,
                    {"weight": 1.0, "essentiality": "supporting"},
                ),
                other_uid=habit_uid,
                allowed_labels=frozenset({NeoLabel.HABIT.value}),
            )
            for habit_uid in request.supporting_habit_uids
        )

        if not candidates:
            return

        relationships = await keep_permitted_link_edges(
            self.backend,
            candidates=candidates,
            subject_uid=goal.uid,
            owner_uid=goal.user_uid,
            logger=self.logger,
        )
        if not relationships:
            return

        batch_result = await self.backend.create_relationships_batch(relationships)
        if batch_result.is_error:
            self.logger.warning(
                "Failed to create %d link relationships for goal %s: %s",
                len(relationships),
                goal.uid,
                batch_result.error,
            )

    async def _publish_created(self, goal: Goal) -> None:
        """Announce a newly created goal: GoalCreated + the ADR-074 embedding refresh.

        ORDERING: call this only once the goal's hierarchy edge is written. ``GoalCreated``
        is subscribed to ``invalidate_context`` (services_bootstrap/_event_wiring.py),
        which debounces and then rebuilds the user context — and the rebuild collects
        ``sub_goals`` by traversing ``(goal)-[:HAS_SUBGOAL]->(subgoal)``. Publishing before
        the edge is written lets the rebuild observe the parent with one subgoal missing
        and cache that for the full 300s TTL, with no later event to correct it.
        (Same inversion Codex reported on #960 for Choices.)
        """
        event = GoalCreated(
            goal_uid=goal.uid,
            user_uid=goal.user_uid,
            title=goal.title,
            domain=get_enum_value(goal.domain) if goal.domain else None,
            target_date=datetime.combine(goal.target_date, datetime.min.time())
            if goal.target_date
            else None,
        )
        await publish_event(self.event_bus, event, self.logger)

        # Post-persist embedding refresh (ADR-074) — the background worker embeds async
        await publish_embedding_requested(self.event_bus, EntityType.GOAL, goal, self.logger)

    async def create_goal(
        self, goal_request: "GoalCreateRequest", user_uid: UserUID
    ) -> Result[Goal]:
        """
        Create a goal from a request with user_uid.

        Args:
            goal_request: Goal creation request
            user_uid: User UID (REQUIRED - fail-fast on None)

        Returns:
            Result containing created Goal

        Builds the entity with the SAME converter the generated CRUD route used when it
        converted for itself (the route now enters here), then hands it to the one
        create primitive. The previous hand-listed ``GoalDTO(...)``
        silently dropped six request fields the route door kept — ``potential_obstacles``,
        ``strategies``, ``success_criteria``, ``tags``, ``unit_of_measurement`` and
        ``why_important`` — so the two doors persisted different goals from one request.

        ``progress_weight`` and the three edge-typed uid lists (``required_knowledge_uids``,
        ``guiding_principle_uids``, ``supporting_habit_uids``) are forwarded here because
        only this door has the request: all four are EDGE-shaped, so none rides an entity
        and the entity door cannot carry them. Since the generated route was bound
        here, every external create has them. The HAS_SUBGOAL edge itself, whose parent DOES ride on
        the entity, is written by the shared path for both doors.
        """
        # Validate user_uid (uses BaseService helper)
        validation = self._validate_required_user_uid(user_uid, "goal creation")
        if validation.is_error:
            return Result.fail(validation)

        from core.services.conversion_service import ConversionServiceV2

        # status=ACTIVE so the goal appears in the default list view; the request
        # carries no status field, so this is the door's contribution, not a default
        # the converter could supply.
        goal = ConversionServiceV2.goal_create_to_pure(
            goal_request,
            UIDGenerator.generate_random_uid("goal"),
            user_uid=user_uid,
            status=EntityStatus.ACTIVE,
        )
        return await self._create_with_hierarchy(
            goal, progress_weight=goal_request.progress_weight, request=goal_request
        )

    @with_error_handling("update_goal", error_type="database", uid_param="uid")
    async def update_goal(self, uid: str, intent: GoalUpdateIntent) -> Result[Goal]:
        """Update a goal's node properties (ADR-066 typed update contract).

        Materializes the intent to a partial patch once, validated and written through the
        inherited CRUD ``update`` (BaseService → ``_validate_update`` → ``backend.update``),
        then publishes domain events. Goals carry no edge fields on the update path, so the
        intent's ``to_changes()`` is written wholesale — there is nothing to split off.

        Args:
            uid: Goal UID
            intent: Typed ``GoalUpdateIntent`` — only its set fields are written

        Returns:
            Result containing updated Goal

        Events Published:
            - GoalUpdated: always, so user-context caches invalidate even for plain
              property edits (title / description / target_date) with no more specific event
            - GoalAchieved: if status transitions into COMPLETED

        (Manual / system progress changes fire ``GoalProgressUpdated`` from
        ``GoalsProgressService``, which owns the progress-propagation provenance.)
        """
        changes = intent.to_changes()
        # Capture the intended fields now: the backend stamps updated_at in place, so
        # reading changes.keys() after the write would leak that bump into the event.
        updated_fields = list(changes.keys())

        # Fetch the prior goal only when a status transition needs old-vs-new comparison.
        old_goal: Goal | None = None
        if "status" in changes:
            current_result = await self.get(uid)
            if current_result.is_ok:
                old_goal = current_result.value

        result: Result[Goal] = await super().update(uid, intent)
        if result.is_error:
            return result

        goal: Goal = result.value

        # GoalUpdated: always fired (cache invalidation contract).
        await publish_event(
            self.event_bus,
            GoalUpdated(goal_uid=goal.uid, user_uid=goal.user_uid, updated_fields=updated_fields),
            self.logger,
        )

        # GoalAchieved: status transitioned into COMPLETED.
        if "status" in changes and old_goal is not None:
            old_status = get_enum_value(old_goal.status)  # Handle both enum and string
            if (
                changes["status"] == EntityStatus.COMPLETED.value
                and old_status != EntityStatus.COMPLETED.value
            ):
                actual_duration_days = (
                    (datetime.now() - goal.created_at).days if goal.created_at else None
                )
                await publish_event(
                    self.event_bus,
                    GoalAchieved(
                        goal_uid=goal.uid,
                        user_uid=goal.user_uid,
                        actual_duration_days=actual_duration_days,
                    ),
                    self.logger,
                )

        # Post-persist embedding refresh (ADR-074) — only when a text field changed
        await publish_embedding_requested(
            self.event_bus, EntityType.GOAL, goal, self.logger, changed_fields=updated_fields
        )

        return result

    async def delete(self, uid: str, cascade: bool = False) -> Result[bool]:
        """
        Delete (abandon) a goal and publish GoalAbandoned event.

        Args:
            uid: Goal UID
            cascade: Whether to cascade delete (default False)

        Returns:
            Result indicating success

        Events Published:
            - GoalAbandoned: When goal is successfully deleted
        """
        # Get goal details before deletion for event publishing
        goal_result = await self.get(uid)
        if goal_result.is_error:
            return Result.fail(goal_result)

        goal = goal_result.value

        # Call parent delete
        result = await super().delete(uid, cascade=cascade)

        # Publish GoalAbandoned event
        if result.is_ok:
            progress_at_abandonment = getattr(goal, "progress", 0.0) or 0.0

            # Calculate days active
            days_active = 0
            if goal.created_at:
                days_active = (datetime.now() - goal.created_at).days

            event = GoalAbandoned(
                goal_uid=uid,
                user_uid=goal.user_uid,
                progress_at_abandonment=progress_at_abandonment,
                days_active=days_active,
            )
            await publish_event(self.event_bus, event, self.logger)

        return result

    # ========================================================================
    # STATUS OPERATIONS
    # ========================================================================

    async def activate_goal(self, uid: str) -> Result[bool]:
        """
        Activate a goal (set status to ACTIVE).

        Args:
            uid: Goal UID

        Returns:
            Result containing True if goal was activated
        """
        result = await self.update_goal(uid, GoalUpdateIntent(status=EntityStatus.ACTIVE.value))
        return Result.ok(True) if result.is_ok else Result.fail(result)

    async def pause_goal(
        self, uid: str, reason: str = "Paused", until_date: str | None = None
    ) -> Result[bool]:
        """
        Pause a goal temporarily.

        Args:
            uid: Goal UID
            reason: Reason for pausing
            until_date: Optional resume date (ISO format)

        Returns:
            Result containing True if goal was paused
        """
        # Store pause metadata
        metadata_updates = {"pause_reason": reason}
        if until_date:
            metadata_updates["paused_until"] = until_date

        result = await self.update_goal(uid, GoalUpdateIntent(status=EntityStatus.PAUSED.value))
        if result.is_ok and metadata_updates:
            # Update metadata separately
            goal = result.value
            goal.metadata.update(metadata_updates)
            await self.update_goal(uid, GoalUpdateIntent(metadata=goal.metadata))

        return Result.ok(True) if result.is_ok else Result.fail(result)

    async def complete_goal(
        self, uid: str, completion_notes: str = "", completion_date: str | None = None
    ) -> Result[bool]:
        """
        Mark a goal as completed.

        Args:
            uid: Goal UID
            completion_notes: Optional completion notes
            completion_date: Optional completion date (ISO format), defaults to today

        Returns:
            Result containing True if goal was completed
        """
        intent = GoalUpdateIntent(
            status=EntityStatus.COMPLETED.value,
            progress_percentage=100.0,
            completion_date=(
                date.fromisoformat(completion_date) if completion_date else date.today()
            ),
        )

        if completion_notes:
            # Get current goal to update metadata
            goal_result = await self.get(uid)
            if goal_result.is_ok and goal_result.value:
                goal = goal_result.value
                goal.metadata["completion_notes"] = completion_notes
                intent = dataclasses.replace(intent, metadata=goal.metadata)

        result = await self.update_goal(uid, intent)
        return Result.ok(True) if result.is_ok else Result.fail(result)

    async def archive_goal(self, uid: str, reason: str = "Archived") -> Result[bool]:
        """
        Archive a goal (set status to ARCHIVED).

        Args:
            uid: Goal UID
            reason: Reason for archiving

        Returns:
            Result containing True if goal was archived
        """
        intent = GoalUpdateIntent(status=EntityStatus.ARCHIVED.value)

        # Get current goal to update metadata
        goal_result = await self.get(uid)
        if goal_result.is_ok and goal_result.value:
            goal = goal_result.value
            goal.metadata["archive_reason"] = reason
            goal.metadata["archived_at"] = datetime.now().isoformat()
            intent = dataclasses.replace(intent, metadata=goal.metadata)

        result = await self.update_goal(uid, intent)
        return Result.ok(True) if result.is_ok else Result.fail(result)

    # ========================================================================
    # QUERY AND TIME-BASED OPERATIONS — Delegated to GoalsSearchService
    # ========================================================================
    # The facade (GoalsService) delegates all query/search methods to the
    # search sub-service (GoalsSearchService) which inherits from BaseService
    # with proper user_uid scoping. Dead duplicates removed March 2026.

    # ========================================================================
    # HIERARCHICAL RELATIONSHIPS (2026-01-30 - Universal Hierarchical Pattern)
    # Delegated to GoalsBackend via _HierarchyMixin (2026-03-24)
    # ========================================================================

    async def create_subgoal_relationship(
        self, parent_uid: str, subgoal_uid: str, progress_weight: float = 1.0
    ) -> Result[bool]:
        """Create bidirectional HAS_SUBGOAL/SUBGOAL_OF relationship with cycle detection."""
        return await self.backend.create_hierarchy_relationship(
            parent_uid, subgoal_uid, {"progress_weight": progress_weight}
        )

    async def remove_subgoal_relationship(self, parent_uid: str, subgoal_uid: str) -> Result[bool]:
        """Remove bidirectional HAS_SUBGOAL/SUBGOAL_OF relationship."""
        return await self.backend.remove_hierarchy_relationship(parent_uid, subgoal_uid)

    # ========================================================================
    # QUERY LAYER — Cypher-level filtering for get_filtered_context
    # ========================================================================

    async def get_stats_for_user(self, user_uid: UserUID) -> Result[GoalStats]:
        """Count goal stats via Cypher COUNT — no entity deserialization."""
        return await self.backend.get_stats_for_user(user_uid)

    # get_for_user_filtered: inherited from SearchOperationsMixin, driven by
    # the status_filters map in _config above.
