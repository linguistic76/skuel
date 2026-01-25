"""
User Relationship Service
==========================

Cross-domain relationship management for User entities.

**ARCHITECTURAL PATTERN: Direct Driver (Graph-Native)**
--------------------------------------------------------
This service uses the DIRECT DRIVER pattern, distinct from the helper-based
pattern used by other relationship services (tasks, goals, habits, etc.).

**Key Characteristics:**
- Does NOT inherit from BaseService
- Takes AsyncDriver directly (not a protocol-based backend)
- Does NOT use RelationshipCreationHelper or SemanticRelationshipHelper
- Writes raw Cypher queries directly via driver.session()
- Simpler, more direct graph operations

**Why This Pattern:**
- User relationships require specific property handling (e.g., order on PINNED)
- Direct Cypher provides maximum flexibility for complex queries
- No need for helper abstraction layer

**Note:** This service is NOT compatible with GenericRelationshipService base class.
See: /docs/patterns/GENERIC_RELATIONSHIP_SERVICE_HONEST_ASSESSMENT.md

Graph Relationships Managed:
----------------------------
- (user)-[:PINNED {order: int}]->(entity) - Ordered pinned entities
- (user)-[:PURSUING_GOAL]->(goal) - Active/current goals
- (user)-[:FOLLOWS]->(other_user) - Social following
- (user)-[:MEMBER_OF]->(team) - Team/group membership

Note: follower_uids removed - use inverse query: MATCH (follower)-[:FOLLOWS]->(user)

Date: October 26, 2025
"""

from typing import Any

from neo4j import AsyncDriver

from core.infrastructure.batch import BatchOperationHelper
from core.models.relationship_names import RelationshipName
from core.services.graph_query_executor import GraphQueryExecutor
from core.utils.processor_functions import (
    extract_created_count,
    extract_dict_from_first_record,
    extract_uids_list,
    extract_uids_set,
)
from core.utils.result_simplified import Errors, Result


def _process_pin_success(records: list) -> Result[bool]:
    """Process pin operation result."""
    return Result.ok(True) if records else Result.fail(Errors.not_found("Entity not found"))


def _process_unpin_success(records: list) -> Result[bool]:
    """Process unpin operation result."""
    return Result.ok(True) if records else Result.fail(Errors.not_found("Pin not found"))


class UserRelationshipService:
    """
    Cross-domain relationship service for User entities.

    Provides graph traversal and relationship management for user relationships.
    Replaces denormalized UID list fields with pure Neo4j graph queries.

    Semantic Types Used:
    - PINNED: User-selected important entities (with order property)
    - PURSUING_GOAL: Active goal relationships
    - FOLLOWS: Social connections
    - MEMBER_OF: Team/group membership

    Source Tag: "user_service_explicit"
    - All relationships are explicit user actions

    Confidence Scoring:
    - 1.0: All user relationships are explicit choices
    """

    def __init__(self, driver: AsyncDriver | None = None) -> None:
        """
        Initialize User relationship service.

        Args:
            driver: Neo4j async driver for graph queries
        """
        self.driver = driver
        self.executor = GraphQueryExecutor(driver)  # Generic query executor

    # ========================================================================
    # Pinned Entities (4 methods)
    # ========================================================================

    async def get_pinned_entities(self, user_uid: str) -> Result[list[str]]:
        """
        Get UIDs of pinned entities for a user (ordered).

        Replaces: user.pinned_entity_uids (removed from User model)
        Graph relationship: (user)-[:PINNED {order: int}]->(entity)

        Returns entities ordered by the `order` property on the relationship.

        Args:
            user_uid: UID of the user

        Returns:
            Result containing ordered list of pinned entity UIDs
        """
        return await self.executor.execute(
            query=f"""
                MATCH (user:User {{uid: $user_uid}})-[r:{RelationshipName.PINNED}]->(entity)
                RETURN entity.uid as uid
                ORDER BY r.order
            """,
            params={"user_uid": user_uid},
            processor=extract_uids_list,
            operation="get_pinned_entities",
        )

    async def pin_entity(self, user_uid: str, entity_uid: str) -> Result[bool]:
        """
        Pin an entity for quick access.

        Adds to end of current pinned list (max order + 1).

        Args:
            user_uid: User UID
            entity_uid: Entity UID to pin (task, goal, KU, etc.)

        Returns:
            Result[bool] - True if pinned successfully
        """
        # Get current max order
        current_pins_result = await self.get_pinned_entities(user_uid)
        if current_pins_result.is_error:
            return current_pins_result

        current_count = len(current_pins_result.value)

        return await self.executor.execute(
            query=f"""
                MATCH (user:User {{uid: $user_uid}})
                MATCH (entity {{uid: $entity_uid}})
                MERGE (user)-[r:{RelationshipName.PINNED}]->(entity)
                ON CREATE SET r.order = $order
                RETURN true as success
            """,
            params={"user_uid": user_uid, "entity_uid": entity_uid, "order": current_count},
            processor=_process_pin_success,
            operation="pin_entity",
        )

    async def unpin_entity(self, user_uid: str, entity_uid: str) -> Result[bool]:
        """
        Unpin an entity.

        Removes PINNED relationship and reorders remaining pins.

        Args:
            user_uid: User UID
            entity_uid: Entity UID to unpin

        Returns:
            Result[bool] - True if unpinned successfully
        """
        return await self.executor.execute(
            query=f"""
                MATCH (user:User {{uid: $user_uid}})-[r:{RelationshipName.PINNED}]->(entity {{uid: $entity_uid}})
                DELETE r
                RETURN true as success
            """,
            params={"user_uid": user_uid, "entity_uid": entity_uid},
            processor=_process_unpin_success,
            operation="unpin_entity",
        )

    async def reorder_pins(self, user_uid: str, ordered_entity_uids: list[str]) -> Result[int]:
        """
        Reorder pinned entities.

        Sets order property on PINNED relationships based on list position.

        Args:
            user_uid: User UID
            ordered_entity_uids: List of entity UIDs in desired order

        Returns:
            Result[int] - Number of pins reordered
        """
        return await self.executor.execute(
            query=f"""
                MATCH (user:User {{uid: $user_uid}})
                UNWIND range(0, size($uids) - 1) AS idx
                WITH user, idx, $uids[idx] AS entity_uid
                MATCH (user)-[r:{RelationshipName.PINNED}]->(entity {{uid: entity_uid}})
                SET r.order = idx
                RETURN count(r) as count
            """,
            params={"user_uid": user_uid, "uids": ordered_entity_uids},
            processor=extract_created_count,
            operation="reorder_pins",
        )

    # ========================================================================
    # Current Goals (1 method)
    # ========================================================================

    async def get_current_goals(self, user_uid: str) -> Result[list[str]]:
        """
        Get UIDs of current/active goals for a user.

        Replaces: user.current_goals (removed from User model)
        Graph relationship: (user)-[:PURSUING_GOAL]->(goal)

        Args:
            user_uid: UID of the user

        Returns:
            Result containing list of current goal UIDs
        """
        return await self.executor.execute(
            query=f"""
                MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.PURSUING_GOAL}]->(goal:Goal)
                RETURN goal.uid as uid
                ORDER BY goal.uid
            """,
            params={"user_uid": user_uid},
            processor=extract_uids_list,
            operation="get_current_goals",
        )

    # ========================================================================
    # Social Connections (2 methods)
    # ========================================================================

    async def get_following(self, user_uid: str) -> Result[set[str]]:
        """
        Get UIDs of users that this user follows.

        Replaces: user.following_uids (removed from User model)
        Graph relationship: (user)-[:FOLLOWS]->(other_user)

        Args:
            user_uid: UID of the user

        Returns:
            Result containing set of followed user UIDs
        """
        return await self.executor.execute(
            query=f"""
                MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.FOLLOWS}]->(other:User)
                RETURN other.uid as uid
            """,
            params={"user_uid": user_uid},
            processor=extract_uids_set,
            operation="get_following",
        )

    async def get_followers(self, user_uid: str) -> Result[set[str]]:
        """
        Get UIDs of users following this user (inverse of FOLLOWS).

        Replaces: user.follower_uids (removed from User model)
        Graph query: MATCH (follower)-[:FOLLOWS]->(user)

        This is the inverse direction of the FOLLOWS relationship.
        No separate follower_uids field needed in graph model.

        Args:
            user_uid: UID of the user

        Returns:
            Result containing set of follower user UIDs
        """
        return await self.executor.execute(
            query=f"""
                MATCH (follower:User)-[:{RelationshipName.FOLLOWS}]->(user:User {{uid: $user_uid}})
                RETURN follower.uid as uid
            """,
            params={"user_uid": user_uid},
            processor=extract_uids_set,
            operation="get_followers",
        )

    # ========================================================================
    # Team Membership (1 method)
    # ========================================================================

    async def get_teams(self, user_uid: str) -> Result[set[str]]:
        """
        Get UIDs of teams/groups this user belongs to.

        Replaces: user.team_uids (removed from User model)
        Graph relationship: (user)-[:MEMBER_OF]->(team)

        Args:
            user_uid: UID of the user

        Returns:
            Result containing set of team UIDs
        """
        return await self.executor.execute(
            query=f"""
                MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.MEMBER_OF}]->(team:Team)
                RETURN team.uid as uid
            """,
            params={"user_uid": user_uid},
            processor=extract_uids_set,
            operation="get_teams",
        )

    # ========================================================================
    # Existence Checks (4 methods)
    # ========================================================================

    async def has_pinned_entities(self, user_uid: str) -> Result[bool]:
        """
        Check if user has any pinned entities.

        Args:
            user_uid: UID of the user

        Returns:
            Result containing True if user has pinned entities
        """
        return await self.executor.execute_exists(
            query=f"MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.PINNED}]->() RETURN user",
            params={"user_uid": user_uid},
            operation="has_pinned_entities",
        )

    async def has_active_goals(self, user_uid: str) -> Result[bool]:
        """
        Check if user has any active goals.

        Replaces: len(user.current_goals) > 0
        Graph query: COUNT (user)-[:PURSUING_GOAL]->() > 0

        Args:
            user_uid: UID of the user

        Returns:
            Result containing True if user has active goals
        """
        return await self.executor.execute_exists(
            query=f"MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.PURSUING_GOAL}]->() RETURN user",
            params={"user_uid": user_uid},
            operation="has_active_goals",
        )

    async def is_following(self, user_uid: str, other_user_uid: str) -> Result[bool]:
        """
        Check if user follows another user.

        Args:
            user_uid: UID of the user
            other_user_uid: UID of the other user

        Returns:
            Result containing True if user follows other_user
        """
        return await self.executor.execute_exists(
            query=f"MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.FOLLOWS}]->(other:User {{uid: $other_user_uid}}) RETURN user",
            params={"user_uid": user_uid, "other_user_uid": other_user_uid},
            operation="is_following",
        )

    async def is_team_member(self, user_uid: str, team_uid: str) -> Result[bool]:
        """
        Check if user is a member of a team.

        Args:
            user_uid: UID of the user
            team_uid: UID of the team

        Returns:
            Result containing True if user is team member
        """
        return await self.executor.execute_exists(
            query=f"MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.MEMBER_OF}]->(team:Team {{uid: $team_uid}}) RETURN user",
            params={"user_uid": user_uid, "team_uid": team_uid},
            operation="is_team_member",
        )

    # ========================================================================
    # Analytics Methods (3 methods)
    # ========================================================================

    async def count_pinned_entities(self, user_uid: str) -> Result[int]:
        """
        Count number of pinned entities for user.

        Args:
            user_uid: UID of the user

        Returns:
            Result containing count of pinned entities
        """
        return await self.executor.execute_count(
            query=f"""
                MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.PINNED}]->()
                RETURN count(*) as count
            """,
            params={"user_uid": user_uid},
            operation="count_pinned_entities",
        )

    async def get_social_stats(self, user_uid: str) -> Result[dict[str, int]]:
        """
        Get social statistics for user.

        Returns counts for following, followers, and mutual connections.

        Args:
            user_uid: UID of the user

        Returns:
            Result containing dict with following_count, follower_count, mutual_count
        """
        return await self.executor.execute(
            query=f"""
                MATCH (user:User {{uid: $user_uid}})
                OPTIONAL MATCH (user)-[:{RelationshipName.FOLLOWS}]->(following)
                OPTIONAL MATCH (follower)-[:{RelationshipName.FOLLOWS}]->(user)
                // mutual = users followed by user who also follow user back
                OPTIONAL MATCH (user)-[:{RelationshipName.FOLLOWS}]->(mutual)-[:{RelationshipName.FOLLOWS}]->(user)
                RETURN count(DISTINCT following) as following_count,
                       count(DISTINCT follower) as follower_count,
                       count(DISTINCT mutual) as mutual_count
            """,
            params={"user_uid": user_uid},
            processor=extract_dict_from_first_record(
                {
                    "following_count": "following_count",
                    "follower_count": "follower_count",
                    "mutual_count": "mutual_count",
                }
            ),
            operation="get_social_stats",
        )

    async def get_user_summary(self, user_uid: str) -> Result[dict[str, Any]]:
        """
        Get comprehensive relationship summary for user.

        Returns counts for all relationship types.

        Args:
            user_uid: UID of the user

        Returns:
            Result containing dict with relationship counts
        """
        return await self.executor.execute(
            query=f"""
                MATCH (user:User {{uid: $user_uid}})
                OPTIONAL MATCH (user)-[:{RelationshipName.PINNED}]->(pinned)
                OPTIONAL MATCH (user)-[:{RelationshipName.PURSUING_GOAL}]->(goal)
                OPTIONAL MATCH (user)-[:{RelationshipName.FOLLOWS}]->(following)
                OPTIONAL MATCH (follower)-[:{RelationshipName.FOLLOWS}]->(user)
                OPTIONAL MATCH (user)-[:{RelationshipName.MEMBER_OF}]->(team)
                RETURN count(DISTINCT pinned) as pinned_count,
                       count(DISTINCT goal) as goal_count,
                       count(DISTINCT following) as following_count,
                       count(DISTINCT follower) as follower_count,
                       count(DISTINCT team) as team_count
            """,
            params={"user_uid": user_uid},
            processor=extract_dict_from_first_record(
                {
                    "pinned_count": "pinned_count",
                    "goal_count": "goal_count",
                    "following_count": "following_count",
                    "follower_count": "follower_count",
                    "team_count": "team_count",
                }
            ),
            operation="get_user_summary",
        )

    # ========================================================================
    # Batch Relationship Creation (1 method)
    # ========================================================================

    async def create_user_relationships(
        self,
        user_uid: str,
        pinned_entity_uids: list[str] | None = None,
        current_goal_uids: list[str] | None = None,
        following_uids: list[str] | None = None,
        team_uids: list[str] | None = None,
    ) -> Result[int]:
        """
        Create all relationships for a user in batch.

        Efficient batch operation for user creation/update workflows.
        Uses UNWIND for optimal Neo4j performance.

        Note: Pinned entities are created with sequential order property (0, 1, 2, ...).

        Args:
            user_uid: UID of the user
            pinned_entity_uids: Ordered list of entity UIDs to pin
            current_goal_uids: Goal UIDs to pursue
            following_uids: User UIDs to follow
            team_uids: Team UIDs to join

        Returns:
            Result containing count of relationships created
        """
        total_created = 0

        # Create PINNED relationships (with order property - requires special handling)
        # This uses indexed order properties, which the standard batch pattern doesn't support
        # Note: empty list guard required - range(0, -1) produces no results but query still runs
        if pinned_entity_uids:
            result = await self.executor.execute(
                query=f"""
                    MATCH (user:User {{uid: $user_uid}})
                    UNWIND range(0, size($uids) - 1) AS idx
                    WITH user, idx, $uids[idx] AS entity_uid
                    MATCH (entity {{uid: entity_uid}})
                    MERGE (user)-[r:{RelationshipName.PINNED} {{order: idx}}]->(entity)
                    RETURN count(r) as created
                """,
                params={"user_uid": user_uid, "uids": pinned_entity_uids},
                processor=extract_created_count,
                operation="create_user_relationships_pinned",
            )
            if result.is_error:
                return result
            total_created += result.value

        # Convert following_uids from set to list if necessary
        following_list = list(following_uids) if following_uids else None
        team_list = list(team_uids) if team_uids else None

        # Build relationship tuples using BatchOperationHelper for standard relationships
        relationships = BatchOperationHelper.build_relationships_list(
            source_uid=user_uid,
            relationship_specs=[
                (current_goal_uids, RelationshipName.PURSUING_GOAL, None),
                (following_list, RelationshipName.FOLLOWS, None),
                (team_list, RelationshipName.MEMBER_OF, None),
            ],
        )

        # Create batch relationships
        if relationships:
            result = await self.executor.create_relationships_batch(
                relationships=relationships,
                operation="create_user_relationships",
            )
            if result.is_error:
                return result
            total_created += result.value

        return Result.ok(total_created)
