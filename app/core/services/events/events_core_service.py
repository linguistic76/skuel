"""
Events Core Service
===================

Handles basic CRUD operations for events.

Responsibilities:
- Get event by UID
- Get user's events
- List events with filters
- Count events
- Basic event retrieval operations
- Publishes domain events (CalendarEventCreated, CalendarEventUpdated, etc.)
"""

from __future__ import annotations

from datetime import date
from operator import attrgetter
from typing import TYPE_CHECKING, Any

from core.events import publish_event
from core.events.base import BaseEvent
from core.events.calendar_event_events import (
    CalendarEventCompleted,
    CalendarEventCreated,
    CalendarEventDeleted,
    CalendarEventRescheduled,
    CalendarEventUpdated,
)
from core.events.embedding_publisher import publish_embedding_requested
from core.models.enums import EntityStatus, EventType
from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.event.event import Event
from core.models.event.event_dto import EventDTO
from core.models.event.event_request import EventCreateRequest
from core.models.event.event_update_intent import EventUpdateIntent
from core.models.relationship_names import RelationshipName
from core.models.type_hints import UserUID
from core.ports.query_types import EventStats
from core.services.base_service import BaseService
from core.services.completion_stamp import (
    completion_moment,
    is_completion_transition,
    status_transition_guard,
)
from core.services.domain_config import create_activity_domain_config
from core.services.mixins.hierarchy_read_mixin import HierarchyReadMixin
from core.services.mixins.link_edge_guard import LinkEdge, keep_permitted_link_edges
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

if TYPE_CHECKING:
    from core.ports.domain_protocols import EventsOperations


class EventsCoreService(
    HierarchyReadMixin["EventsOperations", Event],
    BaseService["EventsOperations", Event, EventUpdateIntent],
):
    """
    Core CRUD service for events.

    Handles:
    - Basic retrieval operations
    - User event queries
    - Event listing and filtering
    - Event counting
    - Publishes domain events for all state changes

    Event-Driven Architecture:
    - Publishes CalendarEventCreated on creation
    - Publishes CalendarEventUpdated on update
    - Publishes CalendarEventCompleted on completion
    - Publishes CalendarEventDeleted on deletion
    - Publishes CalendarEventRescheduled on date change
    """

    def __init__(self, backend: EventsOperations, event_bus=None) -> None:
        """
        Initialize events core service.

        Args:
            backend: Protocol-based backend for event operations
            event_bus: Event bus for publishing domain events (optional)

        Note:
            Context invalidation now happens via event-driven architecture.
            Calendar event operations trigger domain events which invalidate context.
        """
        super().__init__(backend, "events.core")
        self.event_bus = event_bus

    # ========================================================================
    # EMBEDDING HELPERS (Async Background Generation - January 2026)
    # ========================================================================

    # ========================================================================
    # DOMAIN-SPECIFIC CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================

    _config = create_activity_domain_config(
        dto_class=EventDTO,
        model_class=Event,
        entity_label="Entity",
        domain_name="events",
        date_field="event_date",
        completed_statuses=(EntityStatus.COMPLETED.value,),
        status_filters={
            "scheduled": {"status": "scheduled"},
            "completed": {"status": "completed"},
            "cancelled": {"status": "cancelled"},
        },
    )
    # ========================================================================
    # DOMAIN-SPECIFIC VALIDATION HOOKS
    # ========================================================================

    def _validate_create(self, event: Event) -> Result[None]:
        """
        Validate event creation with business rules.

        Business Rules:
        1. Event duration sanity check: 5 minutes to 12 hours (720 minutes)

        Args:
            event: Ku domain model being created

        Returns:
            None if valid, Result.fail() with validation error if invalid
        """

        # Business Rule: Event duration sanity check
        # Catches data entry errors and suggests better patterns
        duration = event.duration_minutes
        if duration:
            if duration < 5:
                return Result.fail(
                    Errors.validation(
                        message="Event duration must be at least 5 minutes",
                        field="duration_minutes",
                        value=duration,
                    )
                )

            if duration > 720:  # 12 hours
                return Result.fail(
                    Errors.validation(
                        message="Event duration exceeds 12 hours. Use multi-day event or split into sessions.",
                        field="duration_minutes",
                        value=duration,
                    )
                )

        return Result.ok(None)  # All validations passed

    def _validate_update(self, current: Event, updates: EventUpdateIntent) -> Result[None]:
        """
        Validate event updates with business rules.

        Business Rules:
        1. Past event immutability: Can't modify past events (except notes/tags)
        2. Duration sanity check: If updating duration, must be 5-720 minutes

        Args:
            current: Current event state
            updates: Dictionary of proposed changes

        Returns:
            None if valid, Result.fail() with validation error if invalid
        """

        changes = updates.to_changes()
        # Business Rule 1: Past event immutability (with notes exception)
        # Past events are historical records, but allow adding notes retrospectively
        if current.event_date and current.event_date < date.today():
            allowed_fields = {"notes", "tags", "quality_score"}  # Can update these
            disallowed_updates = set(changes.keys()) - allowed_fields

            if disallowed_updates:
                return Result.fail(
                    Errors.validation(
                        message=f"Cannot modify past events (except notes/tags/quality_score). "
                        f"Attempted to change: {', '.join(disallowed_updates)}",
                        field="event_date",
                        value=current.event_date.isoformat(),
                    )
                )

        # Business Rule 2: Duration sanity check on update
        if "duration_minutes" in changes:
            duration = changes["duration_minutes"]
            if duration < 5:
                return Result.fail(
                    Errors.validation(
                        message="Event duration must be at least 5 minutes",
                        field="duration_minutes",
                        value=duration,
                    )
                )

            if duration > 720:  # 12 hours
                return Result.fail(
                    Errors.validation(
                        message="Event duration exceeds 12 hours. Use multi-day event or split into sessions.",
                        field="duration_minutes",
                        value=duration,
                    )
                )

        return Result.ok(None)  # All validations passed

    # ========================================================================
    # BASIC CRUD OPERATIONS
    # ========================================================================

    async def get_event(self, event_uid: str) -> Result[Event]:
        """
        Get a specific event by UID.

        Uses BaseService.get() which delegates to BackendOperations.get().
        Not found is returned as Result.fail(Errors.not_found(...)).

        Args:
            event_uid: Event UID

        Returns:
            Result[Event] - success contains Event, not found is an error
        """
        return await self.get(event_uid)

    async def get_user_events(self, user_uid: UserUID) -> Result[list[Event]]:
        """
        Get all events for a user, including learning relationships.

        Args:
            user_uid: UID of the user

        Returns:
            Result containing list of Event objects
        """
        # Use find_by with user_uid filter (UniversalNeo4jBackend pattern)
        result = await self.backend.find_by(user_uid=user_uid)
        if result.is_error:
            return Result.fail(result)

        # find_by returns domain models directly (no DTO conversion needed)
        return result

    async def find_events(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str | None = None,
        order_desc: bool = False,
    ) -> Result[list[Event]]:
        """
        Find events with filters and pagination.

        Args:
            filters: Optional filters to apply,
            limit: Maximum number of results,
            offset: Pagination offset,
            order_by: Field to order by,
            order_desc: Whether to order descending

        Returns:
            Result containing list of events
        """
        # Use backend's list_events method
        result = await self.backend.list(filters=filters or {}, limit=limit, offset=offset)

        if result.is_error:
            return Result.fail(result)

        # Unpack tuple: backend.list() returns (events, total_count)
        events_data, _ = result.value

        # Use BaseService helper for batch DTO conversion
        events = self._to_domain_models(events_data, EventDTO, Event)

        # Sort if requested
        if order_by and events:
            reverse = order_desc
            if order_by == "event_date":
                events.sort(key=attrgetter("event_date"), reverse=reverse)
            elif order_by == "title":
                events.sort(key=attrgetter("title"), reverse=reverse)
            elif order_by == "created_at":
                events.sort(key=attrgetter("created_at"), reverse=reverse)

        return Result.ok(events)

    async def count_events(self, filters: dict[str, Any] | None = None) -> Result[int]:
        """
        Count events matching filters efficiently.

        Args:
            filters: Optional filters to apply

        Returns:
            Result containing count
        """
        count_result = await self.backend.count(**(filters or {}))
        if count_result.is_error:
            return Result.fail(count_result)
        return Result.ok(count_result.value)

    # get_user_items_in_range() is now inherited from BaseService
    # Configured via class attributes: _date_field, _completed_statuses, _dto_class, _model_class
    # CONSOLIDATED (November 27, 2025) - Removed 45 lines of duplicate code

    # ========================================================================
    # EVENT-DRIVEN CRUD OPERATIONS
    # ========================================================================

    async def create(self, entity: Event) -> Result[Event]:
        """Persist, link, then announce — THE create primitive for Events.

        Both doors land here: the entity door (``EventsService.create``) and
        ``create_event`` below — which the generated CRUD route enters through, since
        it was bound to the request door (``CRUDRouteConfig.request_create_method``). ``reinforces_habit_uid`` rides on the ``Event``, so
        it is written as the REINFORCES_HABIT edge on this shared path for both doors.
        Leaving that write on the request door alone is what made
        ``POST /api/events/create`` lose the link entirely: since #967 the mapper skips
        the field as a node property (it is DERIVED FROM EDGE), and nothing on the route
        path wrote the edge — the value was simply dropped (measured 2026-08-06; Tasks'
        identical defect, fixed the same way).

        Args:
            entity: Event to create

        Returns:
            Result containing created Event

        Events Published:
            - CalendarEventCreated: when the event is successfully created
            - EventEmbeddingRequested (ADR-074): post-persist embedding refresh
        """
        return await self._create_with_links(entity, request=None)

    async def _create_with_links(
        self, entity: Event, *, request: EventCreateRequest | None
    ) -> Result[Event]:
        """The one create path: persist, write every edge, then announce.

        ``request`` is present only for the request door:
        ``milestone_celebration_for_goal`` is edge-shaped (CELEBRATES_GOAL) and reaches
        no ``Event`` field, so the entity door has nothing to pass (``None``, and no
        goal edge written).

        Mirrors ``TasksCoreService._create_with_links``, including its trap:
        ``reinforces_habit_uid`` is a RELATIONSHIP_SKIP_FIELD, so it DOES NOT SURVIVE
        THE ROUND-TRIP — ``backend.create`` returns ``from_neo4j_node`` over the
        properties it wrote, and the mapper dropped the field on the way in. It is read
        off the INPUT entity and passed down explicitly.
        """
        result: Result[Event] = await self._create_validated(entity)
        if result.is_error:
            return result

        event = result.value
        await self._write_link_edges(event, entity.reinforces_habit_uid, request)

        # Every edge is written — only now announce the event.
        await self._publish_created(event)
        return result

    async def _create_validated(self, entity: Event) -> Result[Event]:
        """Persist, publishing NOTHING.

        Split out from ``create`` so ``_create_with_links`` can finish writing the
        event's graph edges before any domain event announces it exists — see
        ``_publish_created`` for why that ordering is load-bearing. Runs
        ``_validate_create`` (duration sanity) via the inherited CRUD create. Mirrors
        ``ChoicesCoreService._create_validated``.
        """
        return await super().create(entity)

    async def _write_link_edges(
        self, event: Event, habit_uid: str | None, request: EventCreateRequest | None
    ) -> None:
        """GRAPH-NATIVE: turn the event's cross-domain links into edges, in one batch.

        Two registered relationships, from two different sources:

        - ``Event.reinforces_habit_uid`` → REINFORCES_HABIT — from the ENTITY, so BOTH
          doors write it. Passed in as ``habit_uid`` rather than read off ``event``,
          which cannot carry it once persisted (see ``_create_with_links``).
        - ``request.milestone_celebration_for_goal`` → CELEBRATES_GOAL — request door
          only; the ``Event`` carries no such field, so the ENTITY door can never write
          it (a link the entity cannot carry is a link that door cannot write) —
          HTTP callers sit on the request door since the route was bound here.

        ADMISSION: both UIDs are request input, so each is checked for existence, OWNER
        and KIND before it becomes an edge — see ``keep_permitted_link_edges``. The
        declared kinds come from the field names, because the registry cannot check
        them: Events' REINFORCES_HABIT spec declares its target label as ``Entity``, so
        the batch would admit a Goal as a habit. The request door previously wrote both
        edges through ``UnifiedRelationshipService`` with no owner or kind check — the
        cross-tenant defect class #965 recorded.

        A failure is logged, not propagated — the event itself is legitimate and is
        created either way. This DELIBERATELY changes the request door's contract,
        which used to fail the whole create on a bad edge: the Activity Domains now
        agree that a refused link never kills the entity it decorates (Tasks, Goals and
        Habits already behaved this way), and the two Events doors no longer disagree
        on whether a bad habit UID kills the event.

        ``practices_knowledge_uids`` / ``executes_tasks`` reach no edge here — the
        request door has always dropped them; the unit suite pins that as a known gap
        rather than a silent one.
        """
        candidates: list[LinkEdge] = []

        if habit_uid:
            candidates.append(
                LinkEdge(
                    (event.uid, habit_uid, RelationshipName.REINFORCES_HABIT.value, None),
                    other_uid=habit_uid,
                    allowed_labels=frozenset({NeoLabel.HABIT.value}),
                )
            )
        if request is not None and request.milestone_celebration_for_goal:
            goal_uid = request.milestone_celebration_for_goal
            candidates.append(
                LinkEdge(
                    (event.uid, goal_uid, RelationshipName.CELEBRATES_GOAL.value, None),
                    other_uid=goal_uid,
                    allowed_labels=frozenset({NeoLabel.GOAL.value}),
                )
            )

        if not candidates:
            return

        relationships = await keep_permitted_link_edges(
            self.backend,
            candidates=candidates,
            subject_uid=event.uid,
            owner_uid=event.user_uid,
            logger=self.logger,
        )
        if not relationships:
            return

        batch_result = await self.backend.create_relationships_batch(relationships)
        if batch_result.is_error:
            self.logger.warning(
                "Failed to create %d link relationships for event %s: %s",
                len(relationships),
                event.uid,
                batch_result.error,
            )

    async def _publish_created(self, event: Event) -> None:
        """Announce a newly created event: CalendarEventCreated, CalendarEventCompleted
        when it was born completed, and the ADR-074 embedding refresh.

        ORDERING: call this only once the event's graph edges are written.
        ``CalendarEventCreated`` is subscribed to ``invalidate_context``
        (services_bootstrap/_event_wiring.py), which debounces and then rebuilds the
        user context — and the rebuild reads ``(event)-[:REINFORCES_HABIT]->(:Habit)``
        back out of the graph (adapters/persistence/neo4j/user_context_queries.py). The
        old request door wrote its edges AFTER the publish, so the rebuild could observe
        an event with no links and cache that empty result for the full TTL — the same
        inversion Codex reported on #960, closed for Tasks in #967.
        """
        domain_event = CalendarEventCreated(
            event_uid=event.uid,
            user_uid=event.user_uid,
            title=event.title,
            event_date=event.event_date or date.today(),
            # Canonical member, not the former lowercase "meeting" literal:
            # EventAdapter compares against EventType's UPPERCASE members.
            # (get_enum_value was a no-op here — event_type is a str field.)
            calendar_event_type=event.event_type or EventType.MEETING,
        )
        await publish_event(self.event_bus, domain_event, self.logger)

        await self._publish_born_completed(event)

        # Post-persist embedding refresh (ADR-074) — the background worker embeds async
        await publish_embedding_requested(self.event_bus, EntityType.EVENT, event, self.logger)

    async def _publish_born_completed(self, event: Event) -> None:
        """Publish ``CalendarEventCompleted`` for an event that was CREATED completed.

        The entity door persists whatever status it is handed, so a vault-authored or
        API-created ``status: completed`` event never passes through ``update_event`` and
        every ``CalendarEventCompleted`` subscriber — habit reinforcement, PS practice
        tracking, PS engagement auto-complete, attendance analytics, context invalidation
        — used to be skipped for it. A create has no prior status, so this is
        unambiguously a transition INTO completed.

        ``occurred_at`` carries the event's own ``completed_at`` so a backdated event
        reports the moment it was completed rather than the ingest moment.

        ``quality_score`` is honestly ``None`` here for the same reason it is at the
        update chokepoint: the score is owned by the progress / habit-completion
        services, which fire their own ``CalendarEventCompleted`` carrying it.
        """
        if event.status is not EntityStatus.COMPLETED:
            return

        await publish_event(
            self.event_bus,
            CalendarEventCompleted(
                event_uid=event.uid,
                user_uid=event.user_uid,
                completion_date=event.event_date or date.today(),
                quality_score=None,
                occurred_at=completion_moment(event.completed_at),
            ),
            self.logger,
        )

    async def create_event(self, request: EventCreateRequest, user_uid: UserUID) -> Result[Event]:
        """Create an event from a validated request — the request door.

        Moved from the facade (which now delegates) so the door sits beside the
        primitive it feeds, as ``create_goal`` / ``create_habit`` / ``create_task`` do
        in their domains. ``reinforces_habit_uid`` is set ON the entity so the shared
        path writes the habit edge for this door exactly as it does for the entity door;
        only ``milestone_celebration_for_goal`` is forwarded via ``request``, because it
        is edge-shaped and reaches no ``Event`` field.

        Args:
            request: Validated event creation request
            user_uid: User UID (REQUIRED — fail-fast on None)

        Returns:
            Result containing created Event
        """
        validation = self._validate_required_user_uid(user_uid, "event creation")
        if validation.is_error:
            return Result.fail(validation)

        event = Event(
            uid=UIDGenerator.generate_uid("event", request.title),
            user_uid=user_uid,
            title=request.title,
            description=request.description,
            event_date=request.event_date,
            start_time=request.start_time,
            end_time=request.end_time,
            event_type=request.event_type,
            visibility=request.visibility,
            location=request.location,
            is_online=request.is_online,
            meeting_url=request.meeting_url,
            tags=tuple(request.tags),
            priority=request.priority,
            attendee_emails=tuple(request.attendee_emails),
            max_attendees=request.max_attendees,
            recurrence_pattern=request.recurrence_pattern,
            recurrence_end_date=request.recurrence_end_date,
            reminder_minutes=request.reminder_minutes,
            habit_completion_quality=request.habit_completion_quality,
            knowledge_retention_check=request.knowledge_retention_check,
            reinforces_habit_uid=request.reinforces_habit_uid,
        )
        return await self._create_with_links(event, request=request)

    @with_error_handling("update_event", error_type="database", uid_param="uid")
    async def update_event(self, uid: str, intent: EventUpdateIntent) -> Result[Event]:
        """Update a calendar event's node properties (ADR-066 typed update contract).

        Materializes the intent to a partial patch and writes it exactly once, at the
        single ``backend.update_with_status_guard`` seam, then publishes the appropriate
        calendar event. The domain rules (``_validate_update`` — past-event immutability,
        duration bounds) run here, explicitly: the facade routes the generic CRUD to this
        method, so the inherited hook never fires for Events.

        Events is the one chokepoint whose advisory pre-read is UNCONDITIONAL. Past-event
        immutability reads ``current.event_date`` and applies to every field of every
        update, so there is no narrower gate to put it behind — unlike Tasks, which reads
        only for a priority change. The same read supplies the old date the reschedule
        event reports.

        The facade (``EventsService.update_event``) splits the two edge fields off the
        intent before calling this, so ``intent.to_changes()`` here carries only node
        properties. Status transitions are validated against the Event lifecycle and
        completion stamping (``completed_at``) is applied here — the domain's one
        update chokepoint (``core.services.completion_stamp``) — as a condition the WRITE
        evaluates against the status the node holds under its lock, not against the
        advisory read above (ADR-087).

        Args:
            uid: Event UID
            intent: Typed ``EventUpdateIntent`` (property sub-intent) — only set fields written

        Returns:
            Result containing updated Event

        Events Published:
            - CalendarEventCompleted: if status transitions into COMPLETED
            - CalendarEventRescheduled: if event_date changed
            - CalendarEventUpdated: otherwise (cache invalidation contract)
        """
        changes = intent.to_changes()
        # Capture the intended fields now: the backend stamps updated_at in place, so
        # reading changes.keys() after the write would leak that bump into the event.
        updated_fields: dict[str, Any] = dict(changes)

        # Advisory pre-read — unconditional, because past-event immutability applies to
        # every field of every update (see the docstring). It also carries the old date
        # the reschedule event reports.
        current_result = await self.get(uid)
        if current_result.is_error:
            return Result.fail(current_result)
        old_event = current_result.value
        old_event_date = old_event.event_date

        # Domain validation BEFORE the write. Called explicitly because the facade routes
        # ``update`` / ``update_for_user`` to this method, so the inherited CRUD hook that
        # would otherwise run it is unreachable for Events — dropping this call is how a
        # live domain rule dies silently (cascade-idempotency arc, correction #14).
        validation = self._validate_update(old_event, intent)
        if validation.is_error:
            return Result.fail(validation)

        # Status-target validation + completion stamping, expressed as conditions the
        # WRITE evaluates against the prior it reads under the node's lock (ADR-087).
        guard_result = status_transition_guard(EntityType.EVENT, changes)
        if guard_result.is_error:
            return Result.fail(guard_result)

        update_result = await self.backend.update_with_status_guard(
            uid, changes, guard_result.value
        )
        if update_result.is_error:
            return Result.fail(update_result)

        # This guard refuses nothing (``refuse_if_prior_in`` is empty), so the write
        # always applied; only the prior it returned is news.
        outcome = update_result.value
        event = outcome.entity

        domain_event: BaseEvent
        # Priority 1: Status changed to COMPLETED (state transition only).
        if is_completion_transition(outcome.prior_status, changes):
            domain_event = CalendarEventCompleted(
                event_uid=event.uid,
                user_uid=event.user_uid,
                completion_date=event.event_date or date.today(),
                # quality_score never flows through the generic update path — it is owned
                # by the progress / habit-completion services, which fire their own
                # CalendarEventCompleted with the score (honest None, not a dead key read).
                quality_score=None,
            )
        # Priority 2: Event date changed (rescheduled).
        elif "event_date" in changes and old_event_date and changes["event_date"] != old_event_date:
            domain_event = CalendarEventRescheduled(
                event_uid=event.uid,
                user_uid=event.user_uid,
                old_date=old_event_date,
                new_date=changes["event_date"],
            )
        # Default: Generic update (cache invalidation contract).
        else:
            domain_event = CalendarEventUpdated(
                event_uid=event.uid,
                user_uid=event.user_uid,
                updated_fields=updated_fields,
            )
        await publish_event(self.event_bus, domain_event, self.logger)

        # Post-persist embedding refresh (ADR-074) — only when a text field changed
        await publish_embedding_requested(
            self.event_bus, EntityType.EVENT, event, self.logger, changed_fields=updated_fields
        )

        return Result.ok(event)

    async def delete(self, uid: str, cascade: bool = False) -> Result[bool]:
        """
        Delete a calendar event and publish CalendarEventDeleted event.

        Args:
            uid: Event UID
            cascade: Whether to cascade delete (default False)

        Returns:
            Result indicating success

        Events Published:
            - CalendarEventDeleted: When event is successfully deleted
        """
        # Get event details before deletion for event publishing
        event_result = await self.get(uid)
        if event_result.is_error:
            return Result.fail(event_result)

        event = event_result.value

        # Call parent delete
        result = await super().delete(uid, cascade=cascade)

        # Publish CalendarEventDeleted event
        if result.is_ok:
            domain_event = CalendarEventDeleted(
                event_uid=uid,
                user_uid=event.user_uid,
                title=event.title,
            )
            await publish_event(self.event_bus, domain_event, self.logger)

        return result

    # ========================================================================
    # HIERARCHICAL RELATIONSHIPS (2026-01-30 - Flat UID, Rich Structure)
    # Delegated to EventsBackend via _HierarchyMixin (2026-03-24)
    # ========================================================================

    async def create_subevent_relationship(
        self,
        parent_uid: str,
        subevent_uid: str,
        order: int = 0,
        time_offset_minutes: int | None = None,
    ) -> Result[bool]:
        """Create bidirectional HAS_SUBEVENT/SUBEVENT_OF relationship with cycle detection."""
        forward_props: dict[str, Any] = {"order": order}
        if time_offset_minutes is not None:
            forward_props["time_offset_minutes"] = time_offset_minutes
        return await self.backend.create_hierarchy_relationship(
            parent_uid, subevent_uid, forward_props
        )

    async def remove_subevent_relationship(
        self, parent_uid: str, subevent_uid: str
    ) -> Result[bool]:
        """Remove bidirectional HAS_SUBEVENT/SUBEVENT_OF relationship."""
        return await self.backend.remove_hierarchy_relationship(parent_uid, subevent_uid)

    # ========================================================================
    # QUERY LAYER — Cypher-level filtering for get_filtered_context
    # ========================================================================

    async def get_stats_for_user(self, user_uid: UserUID) -> Result[EventStats]:
        """Count event stats via Cypher COUNT — no entity deserialization."""
        return await self.backend.get_stats_for_user(user_uid)

    # get_for_user_filtered: inherited from SearchOperationsMixin, driven by
    # the status_filters map in _config above.
