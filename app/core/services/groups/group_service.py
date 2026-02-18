"""
Group Service
==============

CRUD operations and membership management for Groups.

Groups mediate ALL teacher-student relationships. A teacher creates a group,
adds students, and assigns work to the group. No direct TEACHES relationship.

TEACHER role required for group creation.

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from datetime import datetime
from typing import Any

from core.models.group.group import Group, GroupDTO, create_group
from core.models.relationship_names import RelationshipName
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

logger = get_logger(__name__)


class GroupService(BaseService):
    """
    CRUD + membership service for groups.

    Groups are the ONE PATH for teacher-student class management.
    """

    _config = DomainConfig(
        dto_class=GroupDTO,
        model_class=Group,
        entity_label="Group",
        search_fields=("name", "description"),
        search_order_by="created_at",
        user_ownership_relationship=RelationshipName.OWNS,
    )

    def __init__(self, backend: Any, event_bus: Any = None) -> None:
        """
        Initialize with backend.

        Args:
            backend: UniversalNeo4jBackend[Group] instance
            event_bus: Optional event bus for publishing group events
        """
        super().__init__(backend, "groups")
        self.backend = backend
        self.event_bus = event_bus
        self.logger = logger
        logger.info("GroupService initialized")

    @property
    def entity_label(self) -> str:
        """Return the graph label for Group entities."""
        return "Group"

    # ========================================================================
    # CREATE
    # ========================================================================

    @with_error_handling("create_group", error_type="database")
    async def create_group(
        self,
        teacher_uid: str,
        name: str,
        description: str | None = None,
        max_members: int | None = None,
    ) -> Result[Group]:
        """
        Create a new group. TEACHER role required (enforced at route level).

        Args:
            teacher_uid: Teacher who owns this group
            name: Display name (e.g., "Physics 101 - Spring 2026")
            description: Optional description
            max_members: Optional member cap

        Returns:
            Result[Group] - The created group
        """
        uid = UIDGenerator.generate_uid("group")

        group = create_group(
            uid=uid,
            name=name,
            owner_uid=teacher_uid,
            description=description,
            max_members=max_members,
        )

        result = await self.backend.create(group)
        if result.is_error:
            self.logger.error(f"Failed to create group: {result.error}")
            return result

        # Create OWNS relationship from teacher to group
        owns_result = await self.backend.execute_query(
            """
            MATCH (teacher:User {uid: $teacher_uid})
            MATCH (group:Group {uid: $group_uid})
            MERGE (teacher)-[:OWNS]->(group)
            RETURN true as success
            """,
            {"teacher_uid": teacher_uid, "group_uid": uid},
        )
        if owns_result.is_error:
            self.logger.warning(f"Failed to create OWNS relationship: {owns_result.error}")

        if self.event_bus:
            from core.events.group_events import GroupCreated

            await _publish_event(
                self.event_bus,
                GroupCreated(
                    group_uid=uid,
                    teacher_uid=teacher_uid,
                    group_name=name,
                    occurred_at=datetime.now(),
                ),
                self.logger,
            )

        self.logger.info(f"Group created: {uid} - {name} (owner: {teacher_uid})")
        return Result.ok(group)

    # ========================================================================
    # READ
    # ========================================================================

    @with_error_handling("get_group", error_type="database")
    async def get_group(self, uid: str) -> Result[Group | None]:
        """Get a specific group by UID."""
        result = await self.backend.get(uid)
        if result.is_error:
            return result
        return Result.ok(result.value)

    @with_error_handling("list_teacher_groups", error_type="database")
    async def list_teacher_groups(self, teacher_uid: str) -> Result[list[Group]]:
        """List all groups owned by a teacher."""
        result = await self.backend.find_by(owner_uid=teacher_uid)
        if result.is_error:
            return result

        groups = result.value or []
        self.logger.info(f"Found {len(groups)} groups for teacher {teacher_uid}")
        return Result.ok(groups)

    @with_error_handling("get_user_groups", error_type="database")
    async def get_user_groups(self, user_uid: str) -> Result[list[Group]]:
        """
        Get all groups a user is a member of (via MEMBER_OF relationship).

        Args:
            user_uid: UID of the student/member

        Returns:
            Result containing list of groups
        """
        result = await self.backend.execute_query(
            f"""
            MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.MEMBER_OF}]->(group:Group)
            WHERE group.is_active = true
            RETURN group
            ORDER BY group.created_at DESC
            """,
            {"user_uid": user_uid},
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        groups = []
        for record in result.value or []:
            props = record["group"]
            try:
                group = Group(**props)
                groups.append(group)
            except Exception as e:
                self.logger.warning(f"Failed to deserialize group: {e}")

        return Result.ok(groups)

    # ========================================================================
    # UPDATE
    # ========================================================================

    @with_error_handling("update_group", error_type="database")
    async def update_group(
        self,
        uid: str,
        name: str | None = None,
        description: str | None = None,
        max_members: int | None = None,
        is_active: bool | None = None,
    ) -> Result[Group]:
        """
        Update a group. Only provided fields will be updated.
        """
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return get_result
        if not get_result.value:
            return Result.fail(Errors.not_found(resource="Group", identifier=uid))

        updates: dict[str, Any] = {}
        if name is not None:
            updates["name"] = name
        if description is not None:
            updates["description"] = description
        if max_members is not None:
            updates["max_members"] = max_members
        if is_active is not None:
            updates["is_active"] = is_active

        updates["updated_at"] = datetime.now().isoformat()

        result = await self.backend.update(uid, updates)
        if result.is_error:
            self.logger.error(f"Failed to update group {uid}: {result.error}")
            return result

        self.logger.info(f"Group updated: {uid}")
        return result

    # ========================================================================
    # DELETE
    # ========================================================================

    @with_error_handling("delete_group", error_type="database")
    async def delete_group(self, uid: str) -> Result[bool]:
        """Delete a group and all its relationships."""
        result = await self.backend.delete(uid, cascade=True)
        if result.is_error:
            return result
        self.logger.info(f"Group deleted: {uid}")
        return Result.ok(True)

    # ========================================================================
    # MEMBERSHIP
    # ========================================================================

    @with_error_handling("add_member", error_type="database")
    async def add_member(
        self,
        group_uid: str,
        user_uid: str,
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

        result = await self.backend.execute_query(
            f"""
            MATCH (user:User {{uid: $user_uid}})
            MATCH (group:Group {{uid: $group_uid}})
            MERGE (user)-[r:{RelationshipName.MEMBER_OF}]->(group)
            SET r.joined_at = datetime($joined_at),
                r.role = $role
            RETURN true as success
            """,
            {
                "user_uid": user_uid,
                "group_uid": group_uid,
                "joined_at": datetime.now().isoformat(),
                "role": role,
            },
        )

        if result.is_error:
            return Result.fail(result.expect_error())

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
                    occurred_at=datetime.now(),
                ),
                self.logger,
            )

        self.logger.info(f"Member {user_uid} added to group {group_uid} as {role}")
        return Result.ok(True)

    @with_error_handling("remove_member", error_type="database")
    async def remove_member(
        self,
        group_uid: str,
        user_uid: str,
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
        result = await self.backend.execute_query(
            f"""
            MATCH (user:User {{uid: $user_uid}})-[r:{RelationshipName.MEMBER_OF}]->(group:Group {{uid: $group_uid}})
            DELETE r
            RETURN count(r) as deleted_count
            """,
            {"user_uid": user_uid, "group_uid": group_uid},
        )

        if result.is_error:
            return Result.fail(result.expect_error())

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
                    occurred_at=datetime.now(),
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
        result = await self.backend.execute_query(
            f"""
            MATCH (user:User)-[r:{RelationshipName.MEMBER_OF}]->(group:Group {{uid: $group_uid}})
            RETURN user.uid as user_uid,
                   user.name as user_name,
                   r.role as role,
                   r.joined_at as joined_at
            ORDER BY r.joined_at
            """,
            {"group_uid": group_uid},
        )

        if result.is_error:
            return Result.fail(result.expect_error())

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
        result = await self.backend.execute_query(
            f"""
            MATCH (user:User)-[:{RelationshipName.MEMBER_OF}]->(group:Group {{uid: $group_uid}})
            RETURN count(user) as member_count
            """,
            {"group_uid": group_uid},
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []
        count = records[0]["member_count"] if records else 0
        return Result.ok(count)


async def _publish_event(event_bus: Any, event: Any, event_logger: Any) -> None:
    """Publish event with error handling."""
    try:
        await event_bus.publish(event)
    except Exception as e:
        event_logger.warning(f"Failed to publish {event.event_type}: {e}")
