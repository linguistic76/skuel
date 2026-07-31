"""
Group Service
==============

CRUD operations and membership management for Groups.

Groups mediate ALL teacher-student relationships. A teacher creates a group,
adds students, and assigns work to the group. No direct TEACHES relationship.

CRUD via CRUDRouteFactory (TEACHER role for mutations, any-auth for reads).
Membership operations stay manual in groups_api.py.

See: /docs/decisions/ADR-040-teacher-exercise-workflow.md
"""

import logging
from datetime import datetime
from typing import Any

from core.events.base import BaseEvent
from core.models.enums import GroupMemberRole
from core.models.group.group import Group, GroupDTO
from core.models.relationship_names import RelationshipName
from core.models.type_hints import UserUID
from core.ports.base_protocols import BackendOperations
from core.ports.infrastructure_protocols import EventBusOperations
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.utils.decorators import with_error_handling
from core.utils.exception_types import DATA_CONVERSION_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import ErrorCategory, Errors, Result

logger = get_logger(__name__)

MAX_STUDENT_GROUPS = 4


class GroupService(BaseService):
    """
    CRUD + membership service for groups.

    Groups are the ONE PATH for teacher-student class management.
    CRUD methods override BaseService to add OWNS relationship creation,
    ownership verification via owner_uid, and member-based read access.
    """

    _config = DomainConfig(
        dto_class=GroupDTO,
        model_class=Group,
        entity_label="Group",
        search_fields=("name", "description"),
        search_order_by="created_at",
        user_ownership_relationship=RelationshipName.OWNS,
    )

    def __init__(
        self, backend: BackendOperations[Group], event_bus: EventBusOperations | None = None
    ) -> None:
        """
        Initialize with backend.

        Args:
            backend: UniversalNeo4jBackend[Group] instance
            event_bus: Optional event bus for publishing group events
        """
        super().__init__(backend, "groups")
        self.backend = backend
        self.event_bus = event_bus
        self.logger = logger  # type: ignore[assignment]  # structlog BoundLogger
        logger.info("GroupService initialized")

    @property
    def entity_label(self) -> str:
        """Return the graph label for Group entities."""
        return "Group"

    # ========================================================================
    # OWNERSHIP VERIFICATION (Group uses owner_uid, not user_uid)
    # ========================================================================

    async def verify_ownership(self, uid: str, user_uid: UserUID) -> Result[Group]:
        """Override: Group uses owner_uid instead of Entity.user_uid."""
        result = await self.get(uid)
        if result.is_error:
            return result
        entity = result.value
        if not entity:
            return Result.fail(Errors.not_found(resource="Group", identifier=uid))
        if entity.owner_uid != user_uid:
            return Result.fail(Errors.not_found(resource="Group", identifier=uid))
        return Result.ok(entity)

    async def get_for_user(self, uid: str, user_uid: UserUID) -> Result[Group]:
        """Owner OR member can view a group.

        Only a *successful* no-access answer becomes not-found. Backend
        failures propagate with their own category (matching verify_ownership
        above) so a Neo4j outage stays observable instead of masquerading as a
        missing group — an infrastructure fault is not an access decision.
        """
        no_such_group: Result[Group] = Result.fail(
            Errors.not_found(resource="Group", identifier=uid)
        )

        result = await self.get(uid)
        if result.is_error:
            # Infrastructure faults propagate; a not-found from the fetch is
            # re-raised in THIS method's own shape. Passing the inner error
            # through would make "absent" distinguishable from "not yours"
            # (the base fetch words its not-found differently), turning the
            # route back into an existence oracle.
            if result.expect_error().category is not ErrorCategory.NOT_FOUND:
                return Result.fail(result)
            return no_such_group
        if not result.value:
            return no_such_group
        group = result.value
        # Owner can always view
        if group.owner_uid == user_uid:
            return Result.ok(group)
        # Check member access
        members_result = await self.get_members(uid)
        if members_result.is_error:
            if members_result.expect_error().category is not ErrorCategory.NOT_FOUND:
                return Result.fail(members_result)
            return no_such_group
        if any(m["user_uid"] == user_uid for m in (members_result.value or [])):
            return Result.ok(group)
        # Same error as "no such group" — a non-member must not be able to tell
        # the two apart (docs/patterns/OWNERSHIP_VERIFICATION.md). Safe to
        # differentiate from the backend errors above: those do not vary with
        # the caller's access, so they reveal nothing about the group.
        return Result.fail(Errors.not_found(resource="Group", identifier=uid))

    # ========================================================================
    # CRUD OVERRIDES
    # ========================================================================

    @with_error_handling("create_group", error_type="database")
    async def create(self, entity: Group) -> Result[Group]:
        """Create a group with OWNS relationship and event publishing."""
        result = await self.backend.create(entity)
        if result.is_error:
            self.logger.error(f"Failed to create group: {result.error}")
            return result

        # Create OWNS relationship from teacher to group
        owns_result = await self.backend.create_owns_relationship(entity.owner_uid, entity.uid)
        if owns_result.is_error:
            self.logger.warning(f"Failed to create OWNS relationship: {owns_result.error}")

        if self.event_bus:
            from core.events.group_events import GroupCreated

            await _publish_event(
                self.event_bus,
                GroupCreated(
                    group_uid=entity.uid,
                    teacher_uid=entity.owner_uid,
                    group_name=entity.name,
                ),
                self.logger,
            )

        self.logger.info(f"Group created: {entity.uid} - {entity.name} (owner: {entity.owner_uid})")
        return Result.ok(entity)

    @with_error_handling("delete_group", error_type="database")
    async def delete(self, uid: str, cascade: bool = False) -> Result[bool]:
        """Delete a group and all its relationships."""
        result = await self.backend.delete(uid, cascade=True)
        if result.is_error:
            return result
        self.logger.info(f"Group deleted: {uid}")
        return Result.ok(True)

    # ========================================================================
    # DOMAIN-SPECIFIC: READ
    # ========================================================================

    @with_error_handling("get_user_groups", error_type="database")
    async def get_user_groups(
        self, user_uid: UserUID, role: str | None = None
    ) -> Result[list[Group]]:
        """
        Get all groups a user is a member of (via MEMBER_OF relationship).

        Args:
            user_uid: UID of the student/member
            role: Optional MEMBER_OF role filter — pass "student" to count
                only student-role memberships (for the per-student cap and
                the student-facing /groups hub), leave as None to get every
                group the user is a member of regardless of role.

        Returns:
            Result containing list of groups
        """
        result = await self.backend.get_user_groups(user_uid, role=role)

        if result.is_error:
            return Result.fail(result)

        groups = []
        for props in result.value or []:
            try:
                group = Group(**props)
                groups.append(group)
            except DATA_CONVERSION_EXCEPTIONS as e:
                self.logger.warning(f"Failed to deserialize group: {e}")

        return Result.ok(groups)

    # ========================================================================
    # DOMAIN-SPECIFIC: MEMBERSHIP
    # ========================================================================

    @with_error_handling("add_member", error_type="database")
    async def add_member(
        self,
        group_uid: str,
        user_uid: UserUID,
        role: str = "student",
    ) -> Result[bool]:
        """
        Add a member to a group.

        Creates a MEMBER_OF relationship from user to group.

        Args:
            group_uid: Group to add member to
            user_uid: User to add
            role: Member role (default: "student")

        Returns:
            Result[bool]: Success if added
        """
        # Check if group exists
        group_result = await self.backend.get(group_uid)
        if group_result.is_error or not group_result.value:
            return Result.fail(Errors.not_found(resource="Group", identifier=group_uid))

        group = group_result.value

        # Check max_members if set
        if group.max_members:
            member_count_result = await self._get_member_count(group_uid)
            if member_count_result.is_ok and member_count_result.value >= group.max_members:
                return Result.fail(
                    Errors.validation(
                        f"Group {group_uid} has reached its member limit ({group.max_members})"
                    )
                )

        # Enforce per-student group cap — a student cannot be an active member of
        # more than MAX_STUDENT_GROUPS groups *as a student*. Teacher/TA role
        # memberships are counted separately (see /groups hub) and do not eat
        # into the student cap.
        if role == GroupMemberRole.STUDENT.value:
            user_groups_result = await self.get_user_groups(
                user_uid, role=GroupMemberRole.STUDENT.value
            )
            if user_groups_result.is_ok:
                current_groups = user_groups_result.value or []
                already_in = any(g.uid == group_uid for g in current_groups)
                if not already_in and len(current_groups) >= MAX_STUDENT_GROUPS:
                    return Result.fail(
                        Errors.validation(
                            f"Students can belong to a maximum of {MAX_STUDENT_GROUPS} groups."
                        )
                    )

        result = await self.backend.add_member(
            group_uid=group_uid,
            user_uid=user_uid,
            joined_at=datetime.now().isoformat(),
            role=role,
        )

        if result.is_error:
            return Result.fail(result)

        records = result.value or []
        if not records:
            return Result.fail(Errors.not_found(f"User {user_uid} or Group {group_uid} not found"))

        if self.event_bus:
            from core.events.group_events import GroupMemberAdded

            await _publish_event(
                self.event_bus,
                GroupMemberAdded(
                    group_uid=group_uid,
                    user_uid=user_uid,
                    role=role,
                ),
                self.logger,
            )

        self.logger.info(f"Member {user_uid} added to group {group_uid} as {role}")
        return Result.ok(True)

    @with_error_handling("remove_member", error_type="database")
    async def remove_member(
        self,
        group_uid: str,
        user_uid: UserUID,
    ) -> Result[bool]:
        """
        Remove a member from a group.

        Deletes the MEMBER_OF relationship.

        Args:
            group_uid: Group to remove member from
            user_uid: User to remove

        Returns:
            Result[bool]: Success if removed
        """
        result = await self.backend.remove_member(group_uid=group_uid, user_uid=user_uid)

        if result.is_error:
            return Result.fail(result)

        records = result.value or []
        deleted_count = records[0]["deleted_count"] if records else 0
        if deleted_count == 0:
            return Result.fail(
                Errors.not_found(f"User {user_uid} is not a member of group {group_uid}")
            )

        if self.event_bus:
            from core.events.group_events import GroupMemberRemoved

            await _publish_event(
                self.event_bus,
                GroupMemberRemoved(
                    group_uid=group_uid,
                    user_uid=user_uid,
                ),
                self.logger,
            )

        self.logger.info(f"Member {user_uid} removed from group {group_uid}")
        return Result.ok(True)

    @with_error_handling("get_members", error_type="database")
    async def get_members(self, group_uid: str) -> Result[list[dict[str, Any]]]:
        """
        Get all members of a group.

        Returns user UID, name, role, and join timestamp.

        Args:
            group_uid: Group to query

        Returns:
            Result containing list of member dicts
        """
        result = await self.backend.get_members(group_uid)

        if result.is_error:
            return Result.fail(result)

        members = [
            {
                "user_uid": record["user_uid"],
                "user_name": record["user_name"],
                "role": record["role"],
                "joined_at": record["joined_at"],
            }
            for record in result.value or []
        ]

        return Result.ok(members)

    # ========================================================================
    # PRIVATE HELPERS
    # ========================================================================

    async def _get_member_count(self, group_uid: str) -> Result[int]:
        """Get current member count for a group."""
        return await self.backend.get_member_count(group_uid)


async def _publish_event(
    event_bus: EventBusOperations, event: BaseEvent, event_logger: logging.Logger
) -> None:
    """Publish event with error handling."""
    try:
        await event_bus.publish_async(event)
    except (ValueError, TypeError, AttributeError) as e:
        event_logger.warning(f"Failed to publish {event.event_type}: {e}")
    except Exception as e:  # safety-net: catch unexpected errors
        event_logger.warning(f"Failed to publish {event.event_type}: {e}")
