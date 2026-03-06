"""
Life Path Mixin
================

Life path relationship methods implementing SKUEL's core philosophy:
"Everything flows toward the life path."

Provides:
    link_to_life_path: Create SERVES_LIFE_PATH relationship
    get_life_path_contributors: Get all entities serving a life path
    calculate_contribution_score: Measure entity contribution to life path
    update_contribution_score: Update contribution score on relationship
    remove_life_path_link: Remove SERVES_LIFE_PATH relationship

Requires on concrete class:
    backend, logger (set by UnifiedRelationshipService.__init__)

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from datetime import UTC
from typing import Any

from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Result


class LifePathMixin:
    """
    Mixin providing life path relationship methods.

    "Everything flows toward the life path" — SKUEL's core philosophy.

    Contains its own contribution scoring sub-system. No callers in other mixins.

    Requires on concrete class:
        backend: Protocol-based backend
        logger: Logger instance
    """

    # Provided by UnifiedRelationshipService.__init__ — declared for mypy
    backend: Any
    logger: Any

    # =========================================================================
    # LIFE PATH RELATIONSHIP METHODS
    # "Everything flows toward the life path"
    # =========================================================================

    @with_error_handling("link_to_life_path", error_type="database")
    async def link_to_life_path(
        self,
        entity_uid: str,
        life_path_uid: str,
        contribution_type: str | None = None,
        contribution_score: float = 0.0,
        notes: str | None = None,
    ) -> Result[bool]:
        """
        Link entity to a user's designated life path via SERVES_LIFE_PATH.

        This creates the fundamental connection that answers: "How does this
        entity contribute to my life path?"

        Args:
            entity_uid: The entity UID (task, goal, habit, etc.)
            life_path_uid: The LP UID that is the user's life path
            contribution_type: How it contributes (direct, supporting, foundational)
            contribution_score: Initial contribution score (0.0-1.0)
            notes: Optional notes about the contribution

        Returns:
            Result[bool] indicating success

        Example:
            # Link a goal to user's life path
            await relationship_service.link_to_life_path(
                entity_uid="goal:learn-python",
                life_path_uid="lp:software-engineering",
                contribution_type="direct",
                contribution_score=0.8,
            )
        """
        from datetime import datetime

        properties: dict[str, Any] = {
            "linked_at": datetime.now(UTC).isoformat(),
            "contribution_score": contribution_score,
        }
        if contribution_type:
            properties["contribution_type"] = contribution_type
        if notes:
            properties["notes"] = notes

        # Create SERVES_LIFE_PATH relationship
        query = """
        MATCH (entity {uid: $entity_uid})
        MATCH (lp:Lp {uid: $life_path_uid})
        MERGE (entity)-[r:SERVES_LIFE_PATH]->(lp)
        SET r += $properties
        RETURN r IS NOT NULL AS success
        """

        params = {
            "entity_uid": entity_uid,
            "life_path_uid": life_path_uid,
            "properties": properties,
        }

        result = await self.backend.execute_query(query, params)

        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []
        success = records[0].get("success", False) if records else False

        if success:
            self.logger.info(
                f"Linked {entity_uid} to life path {life_path_uid} "
                f"(contribution_type={contribution_type}, score={contribution_score})"
            )

        return Result.ok(success)

    @with_error_handling("get_life_path_contributors", error_type="database")
    async def get_life_path_contributors(
        self,
        life_path_uid: str,
        entity_types: list[str] | None = None,
        min_contribution_score: float = 0.0,
        limit: int = 50,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get all entities serving a user's life path.

        Returns entities with their contribution metadata, sorted by
        contribution score descending.

        Args:
            life_path_uid: The LP UID that is the user's life path
            entity_types: Optional filter by entity types (e.g., ["Goal", "Habit"])
            min_contribution_score: Minimum contribution score filter
            limit: Maximum number of results

        Returns:
            Result with list of contributor dictionaries containing:
            - uid: Entity UID
            - labels: Entity labels (e.g., ["Goal"])
            - title: Entity title
            - contribution_type: How it contributes
            - contribution_score: Score (0.0-1.0)
            - linked_at: When link was created

        Example:
            contributors = await service.get_life_path_contributors(
                life_path_uid="lp:software-engineering",
                entity_types=["Goal", "Habit"],
                min_contribution_score=0.5,
            )
        """
        # Build entity type filter
        type_filter = ""
        if entity_types:
            labels = ":".join(entity_types)
            type_filter = f"AND (entity:{labels})"

        query = f"""
        MATCH (entity)-[r:SERVES_LIFE_PATH]->(lp:Lp {{uid: $life_path_uid}})
        WHERE r.contribution_score >= $min_score
        {type_filter}
        RETURN entity.uid AS uid,
               labels(entity) AS labels,
               entity.title AS title,
               entity.description AS description,
               r.contribution_type AS contribution_type,
               r.contribution_score AS contribution_score,
               r.linked_at AS linked_at,
               r.notes AS notes
        ORDER BY r.contribution_score DESC
        LIMIT $limit
        """

        params = {
            "life_path_uid": life_path_uid,
            "min_score": min_contribution_score,
            "limit": limit,
        }

        result = await self.backend.execute_query(query, params)

        if result.is_error:
            return Result.fail(result.expect_error())

        contributors = [
            {
                "uid": record.get("uid"),
                "labels": record.get("labels", []),
                "title": record.get("title"),
                "description": record.get("description"),
                "contribution_type": record.get("contribution_type"),
                "contribution_score": record.get("contribution_score", 0.0),
                "linked_at": record.get("linked_at"),
                "notes": record.get("notes"),
            }
            for record in (result.value or [])
        ]

        self.logger.debug(f"Found {len(contributors)} contributors to life path {life_path_uid}")

        return Result.ok(contributors)

    @with_error_handling("calculate_contribution_score", error_type="database")
    async def calculate_contribution_score(
        self,
        entity_uid: str,
        life_path_uid: str,
    ) -> Result[dict[str, Any]]:
        """
        Calculate how much an entity contributes to a life path.

        Uses graph traversal to measure:
        1. Direct connection strength
        2. Indirect contributions via goals/habits
        3. Knowledge alignment with LP content
        4. Activity alignment (events, tasks practicing LP skills)

        Args:
            entity_uid: The entity UID
            life_path_uid: The LP UID

        Returns:
            Result with contribution analysis:
            - total_score: Overall contribution score (0.0-1.0)
            - direct_score: Direct SERVES_LIFE_PATH strength
            - indirect_score: Via related entities
            - knowledge_score: Knowledge alignment
            - activity_score: Activity alignment
            - breakdown: Detailed component breakdown

        Example:
            analysis = await service.calculate_contribution_score(
                entity_uid="goal:learn-python",
                life_path_uid="lp:software-engineering",
            )
            # Returns: {"total_score": 0.75, "direct_score": 0.8, ...}
        """
        # Query for direct connection
        direct_query = """
        MATCH (entity {uid: $entity_uid})-[r:SERVES_LIFE_PATH]->(lp:Lp {uid: $life_path_uid})
        RETURN r.contribution_score AS direct_score, r.contribution_type AS type
        """

        # Query for indirect connections via goals that serve LP
        indirect_query = """
        MATCH (entity {uid: $entity_uid})
        OPTIONAL MATCH (entity)-[:FULFILLS_GOAL|SUPPORTS_GOAL|CONTRIBUTES_TO_GOAL]->(g:Goal)
                       -[r:SERVES_LIFE_PATH]->(lp:Lp {uid: $life_path_uid})
        RETURN count(g) AS goal_count, avg(r.contribution_score) AS avg_goal_score
        """

        # Query for knowledge alignment with LP KUs
        knowledge_query = """
        MATCH (entity {uid: $entity_uid})
        OPTIONAL MATCH (entity)-[:REQUIRES_KNOWLEDGE|APPLIES_KNOWLEDGE|REINFORCES_KNOWLEDGE]->(ku:Entity)
                       <-[:HAS_STEP*1..3]-(lp:Lp {uid: $life_path_uid})
        RETURN count(DISTINCT ku) AS aligned_ku_count
        """

        params = {"entity_uid": entity_uid, "life_path_uid": life_path_uid}

        # Execute queries in parallel
        import asyncio

        direct_result, indirect_result, knowledge_result = await asyncio.gather(
            self.backend.execute_query(direct_query, params),
            self.backend.execute_query(indirect_query, params),
            self.backend.execute_query(knowledge_query, params),
        )

        # Parse results
        direct_score = 0.0
        contribution_type = None
        if direct_result.is_ok and direct_result.value:
            record = direct_result.value[0]
            direct_score = record.get("direct_score") or 0.0
            contribution_type = record.get("type")

        indirect_score = 0.0
        goal_count = 0
        if indirect_result.is_ok and indirect_result.value:
            record = indirect_result.value[0]
            goal_count = record.get("goal_count") or 0
            avg_score = record.get("avg_goal_score") or 0.0
            # Indirect contribution capped at 0.5, scaled by number of goals
            indirect_score = min(0.5, avg_score * min(goal_count, 3) / 3)

        knowledge_score = 0.0
        aligned_ku_count = 0
        if knowledge_result.is_ok and knowledge_result.value:
            record = knowledge_result.value[0]
            aligned_ku_count = record.get("aligned_ku_count") or 0
            # Knowledge alignment: each KU adds ~0.1, capped at 0.3
            knowledge_score = min(0.3, aligned_ku_count * 0.1)

        # Calculate total (weighted average)
        # Direct: 50%, Indirect: 30%, Knowledge: 20%
        total_score = direct_score * 0.5 + indirect_score * 0.3 + knowledge_score * 0.2

        return Result.ok(
            {
                "entity_uid": entity_uid,
                "life_path_uid": life_path_uid,
                "total_score": round(total_score, 3),
                "direct_score": round(direct_score, 3),
                "indirect_score": round(indirect_score, 3),
                "knowledge_score": round(knowledge_score, 3),
                "contribution_type": contribution_type,
                "breakdown": {
                    "direct_connection": direct_score > 0,
                    "contributing_goals": goal_count,
                    "aligned_knowledge_units": aligned_ku_count,
                },
            }
        )

    @with_error_handling("update_contribution_score", error_type="database")
    async def update_contribution_score(
        self,
        entity_uid: str,
        life_path_uid: str,
        new_score: float,
        contribution_type: str | None = None,
    ) -> Result[bool]:
        """
        Update the contribution score for an entity's life path relationship.

        Args:
            entity_uid: The entity UID
            life_path_uid: The LP UID
            new_score: New contribution score (0.0-1.0)
            contribution_type: Optional new contribution type

        Returns:
            Result[bool] indicating success
        """
        from datetime import datetime

        set_clauses = ["r.contribution_score = $new_score", "r.updated_at = $updated_at"]
        params: dict[str, Any] = {
            "entity_uid": entity_uid,
            "life_path_uid": life_path_uid,
            "new_score": max(0.0, min(1.0, new_score)),
            "updated_at": datetime.now(UTC).isoformat(),
        }

        if contribution_type:
            set_clauses.append("r.contribution_type = $contribution_type")
            params["contribution_type"] = contribution_type

        query = f"""
        MATCH (entity {{uid: $entity_uid}})-[r:SERVES_LIFE_PATH]->(lp:Lp {{uid: $life_path_uid}})
        SET {", ".join(set_clauses)}
        RETURN r IS NOT NULL AS success
        """

        result = await self.backend.execute_query(query, params)

        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []
        success = records[0].get("success", False) if records else False

        if success:
            self.logger.info(
                f"Updated contribution score for {entity_uid} → {life_path_uid}: {new_score}"
            )

        return Result.ok(success)

    @with_error_handling("remove_life_path_link", error_type="database")
    async def remove_life_path_link(
        self,
        entity_uid: str,
        life_path_uid: str,
    ) -> Result[bool]:
        """
        Remove an entity's connection to a life path.

        Args:
            entity_uid: The entity UID
            life_path_uid: The LP UID

        Returns:
            Result[bool] indicating success
        """
        query = """
        MATCH (entity {uid: $entity_uid})-[r:SERVES_LIFE_PATH]->(lp:Lp {uid: $life_path_uid})
        DELETE r
        RETURN count(r) > 0 AS deleted
        """

        params = {"entity_uid": entity_uid, "life_path_uid": life_path_uid}

        result = await self.backend.execute_query(query, params)

        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []
        deleted = records[0].get("deleted", False) if records else False

        if deleted:
            self.logger.info(f"Removed life path link: {entity_uid} → {life_path_uid}")

        return Result.ok(deleted)
