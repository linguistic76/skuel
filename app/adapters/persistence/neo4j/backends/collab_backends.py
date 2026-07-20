"""Collaboration backends: Group, LateralRelationship, Notification, ReviewQueue."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums.pipeline import Pipeline
from core.models.relationship_names import RelationshipName
from core.models.type_hints import EntityUID, Neo4jProperties, UserUID
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
    from core.models.exercises.revised_exercise import RevisedExercise  # noqa: F401
    from core.models.forms.form_template import FormTemplate  # noqa: F401
    from core.models.group.group import Group  # noqa: F401
    from core.models.interaction.interaction import Interaction  # noqa: F401
    from core.models.report_schedule import ReportSchedule  # noqa: F401
    from core.models.resource.resource import Resource  # noqa: F401
    from core.ports.query_types import (
        BlockingChainRow,
        CousinRow,
        LateralRelationshipRow,
        RelationshipGraphRow,
        SiblingRow,
    )


class GroupBackend(UniversalNeo4jBackend["Group"]):
    """
    Domain backend for Group entities.

    Provides:
    - create_owns_relationship — OWNS relationship from teacher to group
    - get_user_groups          — Groups a user is a member of
    - add_member               — Create MEMBER_OF relationship
    - remove_member            — Delete MEMBER_OF relationship
    - get_members              — Query members with metadata
    - get_member_count         — Count members in a group
    """

    async def create_owns_relationship(self, teacher_uid: str, group_uid: str) -> Result[bool]:
        """Create OWNS relationship from teacher to group."""
        result = await self.execute_query(
            """
            MATCH (teacher:User {uid: $teacher_uid})
            MATCH (group:Group {uid: $group_uid})
            MERGE (teacher)-[:OWNS]->(group)
            RETURN true as success
            """,
            {"teacher_uid": teacher_uid, "group_uid": group_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(True)

    async def get_user_groups(
        self, user_uid: UserUID, role: str | None = None
    ) -> Result[list[Neo4jProperties]]:
        """Get all groups a user is a member of (via MEMBER_OF relationship).

        Args:
            user_uid: UID of the member.
            role: Optional MEMBER_OF role filter (e.g. "student", "teacher").
                None returns memberships in all roles.
        """
        params: dict[str, Any] = {"user_uid": user_uid}
        role_clause = ""
        if role is not None:
            role_clause = "AND r.role = $role"
            params["role"] = role
        result = await self.execute_query(
            f"""
            MATCH (user:User {{uid: $user_uid}})-[r:{RelationshipName.MEMBER_OF}]->(group:Group)
            WHERE group.is_active = true {role_clause}
            RETURN group
            ORDER BY group.created_at DESC
            """,
            params,
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok([dict(record["group"]) for record in (result.value or [])])

    async def add_member(
        self,
        group_uid: str,
        user_uid: UserUID,
        joined_at: str,
        role: str = "student",
    ) -> Result[list[Neo4jProperties]]:
        """Create MEMBER_OF relationship from user to group."""
        result = await self.execute_query(
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
                "joined_at": joined_at,
                "role": role,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def remove_member(
        self, group_uid: str, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Delete MEMBER_OF relationship between user and group."""
        result = await self.execute_query(
            f"""
            MATCH (user:User {{uid: $user_uid}})-[r:{RelationshipName.MEMBER_OF}]->(group:Group {{uid: $group_uid}})
            DELETE r
            RETURN count(r) as deleted_count
            """,
            {"user_uid": user_uid, "group_uid": group_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def get_members(self, group_uid: str) -> Result[list[Neo4jProperties]]:
        """Get all members of a group with metadata."""
        result = await self.execute_query(
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
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def get_member_count(self, group_uid: str) -> Result[int]:
        """Get current member count for a group."""
        result = await self.execute_query(
            f"""
            MATCH (user:User)-[:{RelationshipName.MEMBER_OF}]->(group:Group {{uid: $group_uid}})
            RETURN count(user) as member_count
            """,
            {"group_uid": group_uid},
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        count = records[0]["member_count"] if records else 0
        return Result.ok(count)

    # ========================================================================
    # TEACHER REVIEW OPERATIONS (migrated from TeacherReviewService)
    # ========================================================================

    async def get_teacher_groups_with_stats(
        self, teacher_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Get teacher's groups with member, exercise, and pending submission counts."""
        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})-[:{RelationshipName.OWNS.value}]->(g:Group)
        OPTIONAL MATCH (member:User)-[:{RelationshipName.MEMBER_OF.value}]->(g)
        OPTIONAL MATCH (ex:Entity:Exercise)-[:{RelationshipName.SHARED_WITH_GROUP.value}]->(g)
        OPTIONAL MATCH (sub:Entity:UserEntry)-[:{RelationshipName.SHARED_WITH_GROUP.value}]->(g)
          WHERE sub.pipeline = $pipeline
            AND NOT sub.status IN ['completed', 'archived']
        RETURN g.uid AS uid,
               g.name AS name,
               g.description AS description,
               g.is_active AS is_active,
               g.created_at AS created_at,
               count(DISTINCT member) AS member_count,
               count(DISTINCT ex) AS exercise_count,
               count(DISTINCT sub) AS pending_count
        ORDER BY created_at DESC
        """
        return await self.execute_query(
            query, {"teacher_uid": teacher_uid, "pipeline": Pipeline.TEACHER_REVIEW.value}
        )

    async def get_group_detail(
        self, group_uid: str, teacher_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Get members of a teacher's group with their submission progress."""
        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})-[:{RelationshipName.OWNS.value}]->(g:Group {{uid: $group_uid}})
        MATCH (member:User)-[r:{RelationshipName.MEMBER_OF.value}]->(g)
        OPTIONAL MATCH (member)-[:{RelationshipName.OWNS.value}]->(sub:Entity:UserEntry)
                      -[:{RelationshipName.SHARED_WITH_GROUP.value}]->(g)
          WHERE sub.pipeline = $pipeline
        RETURN member.uid AS user_uid,
               member.name AS user_name,
               r.role AS role,
               r.joined_at AS joined_at,
               count(DISTINCT sub) AS submission_count,
               count(DISTINCT CASE WHEN sub.status = 'completed' THEN sub.uid END) AS reviewed_count,
               count(DISTINCT CASE WHEN sub.status IN ['submitted', 'active', 'revision_requested'] THEN sub.uid END) AS pending_count
        ORDER BY r.joined_at
        """
        return await self.execute_query(
            query,
            {
                "group_uid": group_uid,
                "teacher_uid": teacher_uid,
                "pipeline": Pipeline.TEACHER_REVIEW.value,
            },
        )

    async def get_or_create_default_group(
        self, teacher_uid: str, now: str
    ) -> Result[list[Neo4jProperties]]:
        """MERGE the admin's default group, creating it if it doesn't exist.

        Returns a record with group_uid.
        """
        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})
        MERGE (teacher)-[:{RelationshipName.OWNS.value}]->(g:Group {{uid: 'group_default_' + $teacher_uid}})
        ON CREATE SET g.name = 'Default Group',
                      g.description = 'Auto-created default group',
                      g.is_active = true,
                      g.created_at = datetime($now)
        RETURN g.uid AS group_uid
        """
        return await self.execute_query(query, {"teacher_uid": teacher_uid, "now": now})

    async def ensure_group_member(
        self, user_uid: UserUID, group_uid: str, now: str
    ) -> Result[list[Neo4jProperties]]:
        """MERGE MEMBER_OF relationship — idempotent student enrolment in a group."""
        query = f"""
        MATCH (user:User {{uid: $user_uid}})
        MATCH (group:Group {{uid: $group_uid}})
        MERGE (user)-[r:{RelationshipName.MEMBER_OF.value}]->(group)
        ON CREATE SET r.joined_at = datetime($now), r.role = 'student'
        RETURN true AS success
        """
        return await self.execute_query(
            query, {"user_uid": user_uid, "group_uid": group_uid, "now": now}
        )


class LateralRelationshipBackend:
    """
    Backend for lateral relationship Cypher queries.

    Lateral relationships are cross-entity-type graph operations (BLOCKS, PREREQUISITE_FOR,
    ALTERNATIVE_TO, COMPLEMENTARY_TO, SIBLING, RELATED_TO). This backend encapsulates all
    Cypher queries, keeping LateralRelationshipService free of inline queries.

    Similar to NotificationBackend — uses raw Cypher via executor rather than
    UniversalNeo4jBackend, since it manages relationships between arbitrary entity
    types rather than CRUD on a single entity type.

    See: /docs/architecture/RELATIONSHIPS_ARCHITECTURE.md
    """

    def __init__(self, executor: Neo4jQueryExecutor) -> None:
        self.executor = executor

    # ========================================================================
    # CRUD Methods (4)
    # ========================================================================

    async def create_relationship(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: RelationshipName,
        metadata: dict[str, Any],
    ) -> Result[list[Neo4jProperties]]:
        """Create a lateral relationship between two entities (idempotent)."""
        return await self.executor.execute_query(
            f"""
            MATCH (source {{uid: $source_uid}})
            MATCH (target {{uid: $target_uid}})
            MERGE (source)-[r:{relationship_type}]->(target)
            SET r += $metadata
            RETURN r
            """,
            {
                "source_uid": source_uid,
                "target_uid": target_uid,
                "metadata": metadata,
            },
        )

    async def delete_relationship(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: RelationshipName,
    ) -> Result[list[Neo4jProperties]]:
        """Delete a lateral relationship. Returns deleted_count."""
        return await self.executor.execute_query(
            f"""
            MATCH (source {{uid: $source_uid}})-[r:{relationship_type}]->(target {{uid: $target_uid}})
            DELETE r
            RETURN count(r) as deleted_count
            """,
            {"source_uid": source_uid, "target_uid": target_uid},
        )

    async def create_inverse(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: RelationshipName,
        metadata: dict[str, Any],
    ) -> Result[list[Neo4jProperties]]:
        """Create inverse relationship for asymmetric types (idempotent)."""
        return await self.executor.execute_query(
            f"""
            MATCH (source {{uid: $source_uid}})
            MATCH (target {{uid: $target_uid}})
            MERGE (source)-[r:{relationship_type}]->(target)
            SET r += $metadata
            """,
            {
                "source_uid": source_uid,
                "target_uid": target_uid,
                "metadata": metadata,
            },
        )

    async def delete_inverse(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: RelationshipName,
    ) -> Result[list[Neo4jProperties]]:
        """Delete inverse relationship for asymmetric types."""
        return await self.executor.execute_query(
            f"""
            MATCH (source {{uid: $source_uid}})-[r:{relationship_type}]->(target {{uid: $target_uid}})
            DELETE r
            """,
            {"source_uid": source_uid, "target_uid": target_uid},
        )

    # ========================================================================
    # Query Methods (6)
    # ========================================================================

    async def get_relationships(
        self,
        entity_uid: EntityUID,
        type_filter: str,
        pattern: str,
    ) -> Result[list[LateralRelationshipRow]]:
        """Get lateral relationships for an entity.

        Args:
            entity_uid: Entity UID
            type_filter: Pipe-separated relationship types (e.g. "BLOCKS|PREREQUISITE_FOR")
            pattern: Direction pattern — one of "outgoing", "incoming", "both"
        """
        if pattern == "outgoing":
            match_pattern = f"(entity)-[r:{type_filter}]->(related)"
        elif pattern == "incoming":
            match_pattern = f"(entity)<-[r:{type_filter}]-(related)"
        else:
            match_pattern = f"(entity)-[r:{type_filter}]-(related)"

        result = await self.executor.execute_query(
            f"""
            MATCH {match_pattern}
            WHERE entity.uid = $entity_uid
            RETURN
                type(r) as relationship_type,
                related.uid as related_uid,
                related.title as related_title,
                properties(r) as metadata,
                CASE
                    WHEN startNode(r) = entity THEN 'outgoing'
                    ELSE 'incoming'
                END as direction
            ORDER BY relationship_type, related_title
            """,
            {"entity_uid": entity_uid},
        )
        if result.is_error:
            return Result.fail(result)
        rows: list[LateralRelationshipRow] = [
            {
                "relationship_type": r["relationship_type"],
                "related_uid": r["related_uid"],
                "related_title": r["related_title"],
                "metadata": r["metadata"],
                "direction": r["direction"],
            }
            for r in result.value or []
        ]
        return Result.ok(rows)

    async def get_siblings(self, entity_uid: EntityUID) -> Result[list[SiblingRow]]:
        """Get sibling entities derived from hierarchy (same parent).

        "Same parent" is defined by the forward (parent→child) hierarchy edges:
        the six ``HAS_SUB*`` composition edges written by
        ``_HierarchyMixin.create_hierarchy_relationship``, plus ``HAS_STEP``
        (LearningPath→PathStep) and ``ORGANIZES`` (MOC composition). The inverse
        ``SUB*_OF`` edges are deliberately absent — they point child→parent, the
        wrong way round for this traversal.

        Both the anchor edge and the sibling edge are constrained to that set, so
        an unrelated edge into the entity (``BLOCKS``, ``OWNS``, …) cannot
        manufacture a false parent.
        """
        result = await self.executor.execute_query(
            """
            MATCH (parent)-[anchor]->(entity {uid: $entity_uid})
            MATCH (parent)-[r]->(sibling)
            WHERE sibling.uid != $entity_uid
            AND type(anchor) IN ['HAS_SUBTASK', 'HAS_SUBGOAL', 'HAS_SUBHABIT',
                                 'HAS_SUBEVENT', 'HAS_SUBCHOICE',
                                 'HAS_SUBPRINCIPLE', 'HAS_STEP', 'ORGANIZES']
            AND type(r) IN ['HAS_SUBTASK', 'HAS_SUBGOAL', 'HAS_SUBHABIT',
                            'HAS_SUBEVENT', 'HAS_SUBCHOICE', 'HAS_SUBPRINCIPLE',
                            'HAS_STEP', 'ORGANIZES']
            RETURN
                sibling.uid as sibling_uid,
                sibling.title as sibling_title,
                type(r) as hierarchy_type,
                coalesce(r.order, r.sequence) as order
            ORDER BY coalesce(r.order, r.sequence), sibling.title
            """,
            {"entity_uid": entity_uid},
        )
        if result.is_error:
            return Result.fail(result)
        rows: list[SiblingRow] = [
            {
                "sibling_uid": r["sibling_uid"],
                "sibling_title": r["sibling_title"],
                "hierarchy_type": r["hierarchy_type"],
                "order": r["order"],
            }
            for r in result.value or []
        ]
        return Result.ok(rows)

    async def get_cousins(self, entity_uid: EntityUID) -> Result[list[CousinRow]]:
        """Get first-cousin entities (same grandparent, different parent).

        Uses the same forward hierarchy vocabulary as ``get_siblings`` — the
        "not a sibling" exclusion is only correct if both methods agree on what
        a parent edge is.
        """
        result = await self.executor.execute_query(
            """
            MATCH (grandparent)-[gp]->(parent1)-[p1]->(entity {uid: $entity_uid})
            MATCH (grandparent)-[gp2]->(parent2)-[p2]->(cousin)
            WHERE parent1 != parent2
            AND cousin.uid != $entity_uid
            AND all(rel IN [gp, p1, gp2, p2] WHERE type(rel) IN
                ['HAS_SUBTASK', 'HAS_SUBGOAL', 'HAS_SUBHABIT', 'HAS_SUBEVENT',
                 'HAS_SUBCHOICE', 'HAS_SUBPRINCIPLE', 'HAS_STEP', 'ORGANIZES'])
            AND NOT EXISTS {
                MATCH (parent1)-[s]->(cousin)
                WHERE type(s) IN
                    ['HAS_SUBTASK', 'HAS_SUBGOAL', 'HAS_SUBHABIT', 'HAS_SUBEVENT',
                     'HAS_SUBCHOICE', 'HAS_SUBPRINCIPLE', 'HAS_STEP', 'ORGANIZES']
            } // Not a sibling
            RETURN
                cousin.uid as cousin_uid,
                cousin.title as cousin_title,
                grandparent.uid as shared_ancestor_uid,
                grandparent.title as shared_ancestor_title
            ORDER BY cousin.title
            """,
            {"entity_uid": entity_uid},
        )
        if result.is_error:
            return Result.fail(result)
        rows: list[CousinRow] = [
            {
                "cousin_uid": r["cousin_uid"],
                "cousin_title": r["cousin_title"],
                "shared_ancestor_uid": r["shared_ancestor_uid"],
                "shared_ancestor_title": r["shared_ancestor_title"],
            }
            for r in result.value or []
        ]
        return Result.ok(rows)

    async def get_blocking_chain(self, entity_uid: EntityUID) -> Result[list[BlockingChainRow]]:
        """Get transitive blocking chain with depth levels."""
        result = await self.executor.execute_query(
            """
            MATCH path = (blocker)-[:BLOCKS*1..10]->(entity {uid: $uid})
            WITH blocker, path, length(path) as depth
            RETURN
                blocker.uid as uid,
                blocker.title as title,
                blocker.status as status,
                labels(blocker)[0] as entity_type,
                depth,
                COUNT { (blocker)-[:BLOCKS]->() } as blocks_count
            ORDER BY depth DESC
            """,
            {"uid": entity_uid},
        )
        if result.is_error:
            return Result.fail(result)
        rows: list[BlockingChainRow] = [
            {
                "uid": r["uid"],
                "title": r["title"],
                "status": r["status"],
                "entity_type": r["entity_type"],
                "depth": r["depth"],
                "blocks_count": r["blocks_count"],
            }
            for r in result.value or []
        ]
        return Result.ok(rows)

    async def get_alternatives_comparison(
        self, entity_uid: EntityUID
    ) -> Result[list[Neo4jProperties]]:
        """Get alternative entities with side-by-side comparison data."""
        return await self.executor.execute_query(
            """
            MATCH (entity:Entity {uid: $uid})-[r:ALTERNATIVE_TO]-(alternative)
            RETURN
                alternative.uid as uid,
                alternative.title as title,
                alternative.description as description,
                alternative.status as status,
                alternative.priority as priority,
                labels(alternative)[0] as entity_type,
                r.comparison_criteria as comparison_criteria,
                r.tradeoffs as tradeoffs,
                r.timeframe as timeframe,
                r.difficulty as difficulty,
                r.resources as resources,
                properties(alternative) as all_properties,
                properties(r) as rel_properties
            """,
            {"uid": entity_uid},
        )

    async def get_relationship_graph(
        self,
        entity_uid: EntityUID,
        type_filter: str,
        depth: int,
    ) -> Result[list[RelationshipGraphRow]]:
        """Get relationship graph in Vis.js Network format."""
        result = await self.executor.execute_query(
            f"""
            MATCH path = (center {{uid: $uid}})-[r:{type_filter}*1..{depth}]-(related)
            WITH center, r, related, length(path) as depth_level
            RETURN DISTINCT
                center.uid as center_uid,
                center.title as center_title,
                labels(center)[0] as center_type,
                center.status as center_status,
                related.uid as related_uid,
                related.title as related_title,
                labels(related)[0] as related_type,
                related.status as related_status,
                [rel in r | {{
                    type: type(rel),
                    from: startNode(rel).uid,
                    to: endNode(rel).uid
                }}] as relationships,
                depth_level
            """,
            {"uid": entity_uid},
        )
        if result.is_error:
            return Result.fail(result)
        rows: list[RelationshipGraphRow] = [
            {
                "center_uid": r["center_uid"],
                "center_title": r["center_title"],
                "center_type": r["center_type"],
                "center_status": r["center_status"],
                "related_uid": r["related_uid"],
                "related_title": r["related_title"],
                "related_type": r["related_type"],
                "related_status": r["related_status"],
                "relationships": r["relationships"],
                "depth_level": r["depth_level"],
            }
            for r in result.value or []
        ]
        return Result.ok(rows)

    # ========================================================================
    # Validation Methods (4)
    # ========================================================================

    async def check_entities_exist(
        self, source_uid: str, target_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Verify both entities exist in the graph."""
        # :Entity throughout this validation block — a :Content shadow shares
        # its entity's uid, so unlabeled uid MATCHes double-count/misvalidate
        # (G13); lateral-relationship endpoints are always entities.
        return await self.executor.execute_query(
            """
            MATCH (source:Entity {uid: $source_uid})
            MATCH (target:Entity {uid: $target_uid})
            RETURN count(source) as source_count, count(target) as target_count
            """,
            {"source_uid": source_uid, "target_uid": target_uid},
        )

    async def check_same_parent(
        self, source_uid: str, target_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Verify entities share the same parent."""
        return await self.executor.execute_query(
            """
            MATCH (parent)-[]->(source:Entity {uid: $source_uid})
            MATCH (parent)-[]->(target:Entity {uid: $target_uid})
            RETURN count(parent) as shared_parent_count
            """,
            {"source_uid": source_uid, "target_uid": target_uid},
        )

    async def check_same_depth(
        self, source_uid: str, target_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Verify entities are at the same hierarchical depth."""
        return await self.executor.execute_query(
            """
            MATCH path1 = (root)-[*]->(source:Entity {uid: $source_uid})
            WHERE NOT ()-[]->(root)
            WITH length(path1) as source_depth
            MATCH path2 = (root2)-[*]->(target:Entity {uid: $target_uid})
            WHERE NOT ()-[]->(root2)
            WITH source_depth, length(path2) as target_depth
            RETURN source_depth, target_depth
            LIMIT 1
            """,
            {"source_uid": source_uid, "target_uid": target_uid},
        )

    async def check_no_cycles(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: RelationshipName,
    ) -> Result[list[Neo4jProperties]]:
        """Check that creating this relationship won't create a circular dependency."""
        return await self.executor.execute_query(
            f"""
            MATCH (target:Entity {{uid: $target_uid}})-[:{relationship_type}*1..10]->(source:Entity {{uid: $source_uid}})
            RETURN count(*) as cycle_count
            """,
            {"source_uid": source_uid, "target_uid": target_uid},
        )


class NotificationBackend:
    """
    Backend for Notification nodes in Neo4j.

    Notifications are infrastructure, not domain entities — they use raw Cypher
    without BaseService/UniversalNeo4jBackend. This backend encapsulates all
    notification Cypher queries, keeping NotificationService free of inline queries.

    Graph pattern: (User)-[:HAS_NOTIFICATION]->(Notification)
    """

    def __init__(self, executor: Neo4jQueryExecutor) -> None:
        self.executor = executor

    async def create_notification(
        self,
        params: dict[str, Any],
    ) -> Result[list[Neo4jProperties]]:
        """Create a notification node and link to user via HAS_NOTIFICATION."""
        query = """
        MATCH (u:User {uid: $user_uid})
        CREATE (n:Notification {
            uid: $uid,
            user_uid: $user_uid,
            notification_type: $notification_type,
            title: $title,
            message: $message,
            source_uid: $source_uid,
            source_type: $source_type,
            read: false,
            created_at: datetime($now)
        })
        CREATE (u)-[:HAS_NOTIFICATION]->(n)
        RETURN n.uid as uid
        """
        return await self.executor.execute_query(query, params)

    async def get_unread_count(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Get count of unread notifications for a user."""
        query = """
        MATCH (u:User {uid: $user_uid})-[:HAS_NOTIFICATION]->(n:Notification {read: false})
        RETURN count(n) as count
        """
        return await self.executor.execute_query(query, {"user_uid": user_uid})

    async def get_notifications(
        self, user_uid: UserUID, limit: int, include_read: bool = True
    ) -> Result[list[Neo4jProperties]]:
        """Get notifications for a user, unread first."""
        read_filter = "" if include_read else "AND n.read = false"
        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[:HAS_NOTIFICATION]->(n:Notification)
        WHERE n.user_uid = $user_uid {read_filter}
        RETURN n.uid as uid,
               n.notification_type as notification_type,
               n.title as title,
               n.message as message,
               n.source_uid as source_uid,
               n.source_type as source_type,
               n.read as read,
               n.created_at as created_at
        ORDER BY n.read ASC, n.created_at DESC
        LIMIT $limit
        """
        return await self.executor.execute_query(query, {"user_uid": user_uid, "limit": limit})

    async def mark_read(
        self, notification_uid: str, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Mark a single notification as read."""
        query = """
        MATCH (u:User {uid: $user_uid})-[:HAS_NOTIFICATION]->(n:Notification {uid: $notification_uid})
        SET n.read = true
        RETURN n.uid as uid
        """
        return await self.executor.execute_query(
            query, {"user_uid": user_uid, "notification_uid": notification_uid}
        )

    async def mark_all_read(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Mark all notifications as read for a user."""
        query = """
        MATCH (u:User {uid: $user_uid})-[:HAS_NOTIFICATION]->(n:Notification {read: false})
        SET n.read = true
        RETURN count(n) as count
        """
        return await self.executor.execute_query(query, {"user_uid": user_uid})


class ReviewQueueBackend:
    """
    Backend for ReviewRequest node CRUD.

    ReviewRequest is a lightweight workflow marker — not an Entity subclass,
    not managed by UniversalNeo4jBackend. Uses raw Cypher via executor.

    See: /docs/architecture/REPORT_ARCHITECTURE.md
    """

    def __init__(self, executor: Neo4jQueryExecutor) -> None:
        self.executor = executor

    async def create_review_request(
        self,
        user_uid: str,
        uid: str,
        time_period: str,
        domains: list[str],
        message: str,
        now: str,
    ) -> Result[list[Neo4jProperties]]:
        """Create a ReviewRequest node linked to the user via REQUESTED."""
        return await self.executor.execute_query(
            f"""
            MATCH (u:User {{uid: $user_uid}})
            CREATE (r:ReviewRequest {{
                uid: $uid,
                user_uid: $user_uid,
                time_period: $time_period,
                domains: $domains,
                message: $message,
                status: 'pending',
                created_at: datetime($now)
            }})
            CREATE (u)-[:{RelationshipName.REQUESTED.value}]->(r)
            RETURN r.uid AS uid, r.status AS status
            """,
            {
                "user_uid": user_uid,
                "uid": uid,
                "time_period": time_period,
                "domains": domains,
                "message": message,
                "now": now,
            },
        )

    async def get_pending_reviews(self, limit: int = 20) -> Result[list[Neo4jProperties]]:
        """Get pending review requests with user context, ordered by created_at ASC."""
        return await self.executor.execute_query(
            f"""
            MATCH (u:User)-[:{RelationshipName.REQUESTED.value}]->(r:ReviewRequest {{status: 'pending'}})
            RETURN r.uid AS uid, r.user_uid AS user_uid, r.time_period AS time_period,
                   r.domains AS domains, r.message AS message,
                   toString(r.created_at) AS created_at,
                   u.title AS username
            ORDER BY r.created_at ASC
            LIMIT $limit
            """,
            {"limit": limit},
        )
