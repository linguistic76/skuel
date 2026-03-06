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

from datetime import date, datetime
from operator import attrgetter
from typing import TYPE_CHECKING, Any

from core.events import publish_event
from core.events.calendar_event_events import (
    CalendarEventCompleted,
    CalendarEventCreated,
    CalendarEventDeleted,
    CalendarEventRescheduled,
    CalendarEventUpdated,
)
from core.models.enums import EntityStatus
from core.models.enums.entity_enums import EntityType
from core.models.event.event import Event
from core.models.event.event_dto import EventDTO
from core.ports import get_enum_value
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.utils.decorators import with_error_handling
from core.utils.embedding_text_builder import build_embedding_text
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.domain_protocols import EventsOperations


class EventsCoreService(BaseService["EventsOperations", Event]):
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
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Event entities."""
        return "Entity"

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
    )
    # ========================================================================
    # DOMAIN-SPECIFIC VALIDATION HOOKS
    # ========================================================================

    def _validate_create(self, event: Event) -> Result[None] | None:
        """
        Validate event creation with business rules.

        Business Rules:
        1. Event duration sanity check: 5 minutes to 12 hours (720 minutes)

        Args:
            event: Ku domain model being created

        Returns:
            None if valid, Result.fail() with validation error if invalid
        """
        from core.utils.result_simplified import Errors

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

        return None  # All validations passed

    def _validate_update(self, current: Event, updates: dict[str, Any]) -> Result[None] | None:
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
        from core.utils.result_simplified import Errors

        # Business Rule 1: Past event immutability (with notes exception)
        # Past events are historical records, but allow adding notes retrospectively
        if current.event_date and current.event_date < date.today():
            allowed_fields = {"notes", "tags", "quality_score"}  # Can update these
            disallowed_updates = set(updates.keys()) - allowed_fields

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
        if "duration_minutes" in updates:
            duration = updates["duration_minutes"]
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

        return None  # All validations passed

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
            Result[Ku] - success contains Ku, not found is an error
        """
        return await self.get(event_uid)

    async def get_user_events(self, user_uid: str) -> Result[list[Event]]:
        """
        Get all events for a user, including learning relationships.

        Args:
            user_uid: UID of the user

        Returns:
            Result containing list of Ku objects
        """
        # Use find_by with user_uid filter (UniversalNeo4jBackend pattern)
        result = await self.backend.find_by(user_uid=user_uid)
        if result.is_error:
            return Result.fail(result.expect_error())

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
            return Result.fail(result.expect_error())

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
            return Result.fail(count_result.expect_error())
        return Result.ok(count_result.value)

    # get_user_items_in_range() is now inherited from BaseService
    # Configured via class attributes: _date_field, _completed_statuses, _dto_class, _model_class
    # CONSOLIDATED (November 27, 2025) - Removed 45 lines of duplicate code

    # ========================================================================
    # EVENT-DRIVEN CRUD OPERATIONS
    # ========================================================================

    async def create(self, entity: Event) -> Result[Event]:
        """
        Create a calendar event and publish CalendarEventCreated event.

        Args:
            entity: Ku to create

        Returns:
            Result containing created Ku

        Events Published:
            - CalendarEventCreated: When event is successfully created
        """
        # Call parent create
        result = await super().create(entity)

        # Publish CalendarEventCreated event
        if result.is_ok:
            event = result.value
            domain_event = CalendarEventCreated(
                event_uid=event.uid,
                user_uid=event.user_uid,
                title=event.title,
                event_date=event.event_date,
                calendar_event_type=get_enum_value(event.event_type)
                if event.event_type
                else "meeting",
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, domain_event, self.logger)

            # Publish embedding request event for async background generation
            # Background worker will process embeddings in batches (zero latency impact on user)
            embedding_text = build_embedding_text(EntityType.EVENT, event)
            if embedding_text:
                from core.events import EventEmbeddingRequested

                now = datetime.now()
                embedding_event = EventEmbeddingRequested(
                    entity_uid=event.uid,
                    entity_type="event",
                    embedding_text=embedding_text,
                    user_uid=event.user_uid,
                    requested_at=now,
                    occurred_at=now,
                )
                await publish_event(self.event_bus, embedding_event, self.logger)

        return result

    async def update(self, uid: str, updates: dict[str, Any]) -> Result[Event]:
        """
        Update a calendar event and publish appropriate events.

        Publishes CalendarEventUpdated, CalendarEventCompleted, or
        CalendarEventRescheduled depending on what changed.

        Args:
            uid: Event UID
            updates: Dictionary of field updates

        Returns:
            Result containing updated Ku

        Events Published:
            - CalendarEventCompleted: If status changed to COMPLETED
            - CalendarEventRescheduled: If event_date changed
            - CalendarEventUpdated: For other updates
        """
        # Get current event to track specific changes (always fetch for update events)
        old_event_date = None
        old_status = None
        current_result = await self.get(uid)
        if current_result.is_ok and current_result.value:
            old_event_date = current_result.value.event_date
            old_status = current_result.value.status

        # Call parent update
        result = await super().update(uid, updates)

        # Publish appropriate event based on what changed
        if result.is_ok:
            event = result.value

            # Priority 1: Status changed to COMPLETED (state transition only)
            if (
                "status" in updates
                and updates["status"] == EntityStatus.COMPLETED.value
                and old_status != EntityStatus.COMPLETED
            ):
                domain_event = CalendarEventCompleted(
                    event_uid=event.uid,
                    user_uid=event.user_uid,
                    completion_date=event.event_date,
                    quality_score=updates.get("quality_score"),
                    occurred_at=datetime.now(),
                )
                await publish_event(self.event_bus, domain_event, self.logger)

            # Priority 2: Event date changed (rescheduled)
            elif (
                "event_date" in updates
                and old_event_date
                and updates["event_date"] != old_event_date
            ):
                domain_event = CalendarEventRescheduled(
                    event_uid=event.uid,
                    user_uid=event.user_uid,
                    old_date=old_event_date,
                    new_date=updates["event_date"],
                    occurred_at=datetime.now(),
                )
                await publish_event(self.event_bus, domain_event, self.logger)

            # Default: Generic update
            else:
                domain_event = CalendarEventUpdated(
                    event_uid=event.uid,
                    user_uid=event.user_uid,
                    updated_fields=updates,
                    occurred_at=datetime.now(),
                )
                await publish_event(self.event_bus, domain_event, self.logger)

        return result

    async def delete(self, uid: str, cascade: bool = False) -> Result[bool]:
        """
        DETACH DELETE a calendar event and publish CalendarEventDeleted event.

        Args:
            uid: Event UID
            cascade: Whether to cascade DETACH DELETE (default False)

        Returns:
            Result indicating success

        Events Published:
            - CalendarEventDeleted: When event is successfully deleted
        """
        # Get event details before deletion for event publishing
        event_result = await self.get(uid)
        if event_result.is_error:
            return Result.fail(event_result.expect_error())

        event = event_result.value

        # Call parent delete
        result = await super().delete(uid, cascade=cascade)

        # Publish CalendarEventDeleted event
        if result.is_ok:
            domain_event = CalendarEventDeleted(
                event_uid=uid,
                user_uid=event.user_uid,
                title=event.title,
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, domain_event, self.logger)

        return result

    # ========================================================================
    # HIERARCHICAL RELATIONSHIPS (2026-01-30 - Universal Hierarchical Pattern)
    # ========================================================================

    @with_error_handling("get_subevents", error_type="database", uid_param="parent_uid")
    async def get_subevents(self, parent_uid: str, depth: int = 1) -> Result[list[Event]]:
        """
        Get all subevents of a parent event.

        Args:
            parent_uid: Parent event UID
            depth: How many levels deep (1=direct children, 2=children+grandchildren, etc.)

        Returns:
            Result containing list of subevents ordered by created_at

        Example:
            # Get direct children
            subevents = await service.get_subevents("event_abc123")

            # Get all descendants
            all_subevents = await service.get_subevents("event_abc123", depth=99)
        """
        query = f"""
        MATCH (parent:Entity {{uid: $parent_uid}})
        MATCH (parent)-[:HAS_SUBEVENT*1..{depth}]->(subevent:Entity)
        RETURN subevent
        ORDER BY subevent.created_at
        """

        result = await self.backend.execute_query(query, {"parent_uid": parent_uid})

        if result.is_error:
            return Result.fail(result.expect_error())
        if not result.value:
            return Result.ok([])

        # Convert to domain models
        events = []
        for record in result.value:
            event_data = record["subevent"]
            event = self._to_domain_model(event_data, EventDTO, Event)
            events.append(event)

        return Result.ok(events)

    @with_error_handling("get_parent_event", error_type="database", uid_param="subevent_uid")
    async def get_parent_event(self, subevent_uid: str) -> Result[Event | None]:
        """
        Get immediate parent of a subevent (if any).

        Args:
            subevent_uid: Subevent UID

        Returns:
            Result containing parent Ku or None if root-level event
        """
        query = """
        MATCH (subevent:Entity {uid: $subevent_uid})
        MATCH (parent:Entity)-[:HAS_SUBEVENT]->(subevent)
        RETURN parent
        LIMIT 1
        """

        result = await self.backend.execute_query(query, {"subevent_uid": subevent_uid})

        if result.is_error:
            return Result.fail(result.expect_error())
        if not result.value:
            return Result.ok(None)

        parent_data = result.value[0]["parent"]
        parent = self._to_domain_model(parent_data, EventDTO, Event)
        return Result.ok(parent)

    @with_error_handling("get_event_hierarchy", error_type="database", uid_param="event_uid")
    async def get_event_hierarchy(self, event_uid: str) -> Result[dict[str, Any]]:
        """
        Get full hierarchy context: ancestors, siblings, children.

        Args:
            event_uid: Event UID to get context for

        Returns:
            Result containing hierarchy dict with keys:
            - ancestors: list[Event] (root to immediate parent)
            - current: Event
            - siblings: list[Event] (other children of same parent)
            - children: list[Event] (immediate children)
            - depth: int (how deep in hierarchy, 0=root)

        Example:
            hierarchy = await service.get_event_hierarchy("event_xyz789")
            # {
            # "ancestors": [root_event, parent_event],
            # "current": event_xyz789,
            # "siblings": [sibling1, sibling2],
            # "children": [child1, child2],
            # "depth": 2
            # }
        """
        # Get ancestors
        ancestors_query = """
        MATCH path = (root:Entity)-[:HAS_SUBEVENT*]->(current:Entity {uid: $event_uid})
        WHERE NOT EXISTS((root)<-[:HAS_SUBEVENT]-())
        RETURN nodes(path) as ancestors
        """

        # Get siblings
        siblings_query = """
        MATCH (current:Entity {uid: $event_uid})
        OPTIONAL MATCH (parent:Entity)-[:HAS_SUBEVENT]->(current)
        OPTIONAL MATCH (parent)-[:HAS_SUBEVENT]->(sibling:Entity)
        WHERE sibling.uid <> $event_uid
        RETURN collect(sibling) as siblings
        """

        # Get children
        children_query = """
        MATCH (current:Entity {uid: $event_uid})
        OPTIONAL MATCH (current)-[:HAS_SUBEVENT]->(child:Entity)
        RETURN collect(child) as children
        """

        # Execute all queries
        current_result = await self.backend.get(event_uid)
        if current_result.is_error:
            return Result.fail(current_result)

        current_event = self._to_domain_model(current_result.value, EventDTO, Event)

        ancestors_result = await self.backend.execute_query(
            ancestors_query, {"event_uid": event_uid}
        )
        siblings_result = await self.backend.execute_query(siblings_query, {"event_uid": event_uid})
        children_result = await self.backend.execute_query(children_query, {"event_uid": event_uid})

        # Process ancestors
        ancestors = []
        if (
            not ancestors_result.is_error
            and ancestors_result.value
            and ancestors_result.value[0]["ancestors"]
        ):
            for node in ancestors_result.value[0]["ancestors"][:-1]:  # Exclude current
                event_data = node
                ancestors.append(self._to_domain_model(event_data, EventDTO, Event))

        # Process siblings
        siblings = []
        if (
            not siblings_result.is_error
            and siblings_result.value
            and siblings_result.value[0]["siblings"]
        ):
            for node in siblings_result.value[0]["siblings"]:
                if node:  # Skip None values
                    event_data = node
                    siblings.append(self._to_domain_model(event_data, EventDTO, Event))

        # Process children
        children = []
        if (
            not children_result.is_error
            and children_result.value
            and children_result.value[0]["children"]
        ):
            for node in children_result.value[0]["children"]:
                if node:  # Skip None values
                    event_data = node
                    children.append(self._to_domain_model(event_data, EventDTO, Event))

        return Result.ok(
            {
                "ancestors": ancestors,
                "current": current_event,
                "siblings": siblings,
                "children": children,
                "depth": len(ancestors),
            }
        )

    @with_error_handling("create_subevent_relationship", error_type="database")
    async def create_subevent_relationship(
        self,
        parent_uid: str,
        subevent_uid: str,
        order: int = 0,
        time_offset_minutes: int | None = None,
    ) -> Result[bool]:
        """
        Create bidirectional parent-child relationship.

        Args:
            parent_uid: Parent event UID
            subevent_uid: Subevent UID
            order: Display order for subevents (default: 0)
            time_offset_minutes: Minutes from parent start time (optional)

        Returns:
            Result indicating success

        Note:
            Creates both HAS_SUBEVENT (parent→child) and SUBEVENT_OF (child→parent)
            for efficient bidirectional queries.
        """
        # Validate no cycle (can't make parent a child of its descendant)
        cycle_check = await self._would_create_cycle(parent_uid, subevent_uid)
        if cycle_check:
            return Result.fail(
                Errors.validation(
                    f"Cannot create subevent relationship: would create cycle "
                    f"({subevent_uid} is ancestor of {parent_uid})"
                )
            )

        # Build relationship properties
        rel_props = {"order": order}
        if time_offset_minutes is not None:
            rel_props["time_offset_minutes"] = time_offset_minutes

        # Build property assignments for Cypher
        prop_assignments = ", ".join([f"{k}: ${k}" for k in rel_props])

        query = f"""
        MATCH (parent:Entity {{uid: $parent_uid}})
        MATCH (subevent:Entity {{uid: $subevent_uid}})

        CREATE (parent)-[:HAS_SUBEVENT {{
            {prop_assignments},
            created_at: datetime()
        }}]->(subevent)

        CREATE (subevent)-[:SUBEVENT_OF {{
            created_at: datetime()
        }}]->(parent)

        RETURN true as success
        """

        params = {"parent_uid": parent_uid, "subevent_uid": subevent_uid, **rel_props}
        result = await self.backend.execute_query(query, params)

        if result.is_error:
            return Result.fail(
                Errors.database(
                    operation="create", message="Failed to create subevent relationship"
                )
            )
        if result.value:
            self.logger.info(
                f"Created subevent relationship: {parent_uid} -> {subevent_uid} (order: {order})"
            )
            return Result.ok(True)

        return Result.fail(
            Errors.database(operation="create", message="Failed to create subevent relationship")
        )

    @with_error_handling("remove_subevent_relationship", error_type="database")
    async def remove_subevent_relationship(
        self, parent_uid: str, subevent_uid: str
    ) -> Result[bool]:
        """
        Remove bidirectional parent-child relationship.

        Args:
            parent_uid: Parent event UID
            subevent_uid: Subevent UID

        Returns:
            Result containing True if relationships were deleted
        """
        query = """
        MATCH (parent:Entity {uid: $parent_uid})-[r1:HAS_SUBEVENT]->(subevent:Entity {uid: $subevent_uid})
        MATCH (subevent)-[r2:SUBEVENT_OF]->(parent)
        DELETE r1, r2
        RETURN count(r1) + count(r2) as deleted_count
        """

        result = await self.backend.execute_query(
            query, {"parent_uid": parent_uid, "subevent_uid": subevent_uid}
        )

        if not result.is_error and result.value:
            deleted = result.value[0]["deleted_count"]
            if deleted > 0:
                self.logger.info(f"Removed subevent relationship: {parent_uid} -> {subevent_uid}")
                return Result.ok(True)

        return Result.ok(False)

    async def _would_create_cycle(self, parent_uid: str, child_uid: str) -> bool:
        """Check if adding parent->child relationship would create a cycle."""
        query = """
        MATCH (child:Entity {uid: $child_uid})
        MATCH path = (child)-[:HAS_SUBEVENT*]->(parent:Entity {uid: $parent_uid})
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

    # ========================================================================
    # QUERY LAYER — Cypher-level filtering for get_filtered_context
    # ========================================================================

    async def get_stats_for_user(self, user_uid: str) -> Result[dict[str, int]]:
        """Count event stats via Cypher COUNT — no entity deserialization."""
        query = """
        MATCH (n:Entity {user_uid: $user_uid, entity_type: 'event'})
        RETURN
            count(n) AS total,
            count(CASE WHEN n.status = 'scheduled' THEN 1 END) AS scheduled,
            count(CASE WHEN n.start_time IS NOT NULL
                       AND substring(toString(n.start_time), 0, 10) = $today
                  THEN 1 END) AS today
        """
        result = await self.backend.execute_query(
            query, {"user_uid": user_uid, "today": date.today().isoformat()}
        )
        if result.is_error:
            return Result.fail(result)
        record = result.value[0] if result.value else {}
        return Result.ok(
            {
                "total": record.get("total", 0),
                "scheduled": record.get("scheduled", 0),
                "today": record.get("today", 0),
            }
        )

    async def get_for_user_filtered(
        self, user_uid: str, status_filter: str = "scheduled"
    ) -> Result[list[Event]]:
        """Fetch events with status filter pushed to Cypher WHERE."""
        match status_filter:
            case "scheduled":
                result = await self.backend.find_by(user_uid=user_uid, status="scheduled")
            case "completed":
                result = await self.backend.find_by(user_uid=user_uid, status="completed")
            case "cancelled":
                result = await self.backend.find_by(user_uid=user_uid, status="cancelled")
            case _:  # "all" or unknown
                result = await self.backend.find_by(user_uid=user_uid)
        if result.is_error:
            return result
        return Result.ok(self._to_domain_models(result.value, EventDTO, Event))
