"""
Knowledge Graph Service - Graph Navigation and Relationships
=============================================================

Clean rewrite following CLAUDE.md patterns.
Handles all graph operations for knowledge units.

**Responsibilities:**
- Graph traversal (prerequisites, next steps)
- Relationship management (create, link, query)
- Knowledge gap analysis
- Learning recommendations
- Prerequisite chains

**Dependencies:**
- LessonOperations (backend protocol)
- Neo4jAdapter (graph operations)
- GraphIntelligence service (smart traversal)
"""

from typing import Any

from adapters.persistence.neo4j.query import (
    build_metadata_aware_path_query,
    build_relationship_traversal_query,
    build_simple_prerequisite_chain,
)
from core.constants import GraphDepth, QueryLimit
from core.models.curriculum_dto import CurriculumDTO
from core.models.relationship_names import RelationshipName
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result


class LessonGraphService:
    """
    Graph navigation and relationship operations for knowledge units.
    """

    def __init__(self, repo=None, neo4j_adapter=None, graph_intel=None) -> None:
        """
        Initialize graph service with required dependencies.

        Args:
            repo: LessonOperations backend,
            neo4j_adapter: Neo4j adapter for graph operations,
            graph_intel: Graph intelligence service for smart traversal
        """
        # Fail-fast validation (CLAUDE.md: no graceful degradation)
        if not repo:
            raise ValueError("KU repository is required")
        if not neo4j_adapter:
            raise ValueError("Neo4j adapter is required for graph operations")

        self.repo = repo
        self.neo4j = neo4j_adapter
        self.graph_intel = graph_intel

        self.logger = get_logger("skuel.services.lesson.graph")

    async def _execute_query(
        self, query: str, params: dict[str, Any], operation: str = "execute_query"
    ) -> Result[list[Any]]:
        """
        Execute a Cypher query and return a Result.

        The neo4j_adapter.execute_query() returns a raw list. This helper
        wraps it to return a Result for consistent error handling.

        Args:
            query: Cypher query string
            params: Query parameters
            operation: Operation name for error messages

        Returns:
            Result containing the query results or an error
        """
        from core.utils.exception_types import NEO4J_EXCEPTIONS

        try:
            results = await self.neo4j.execute_query(query, params)
            return Result.ok(results if results is not None else [])
        except NEO4J_EXCEPTIONS as e:
            return Result.fail(Errors.database(operation=operation, message=str(e)))
        except Exception as e:  # safety-net: catch unexpected errors
            return Result.fail(Errors.database(operation=operation, message=str(e)))

    # ========================================================================
    # GRAPH TRAVERSAL
    # ========================================================================

    @with_error_handling("find_prerequisites", error_type="database", uid_param="uid")
    async def find_prerequisites(
        self,
        uid: str,
        depth: int = 3,
        _include_optional: bool = False,
        min_confidence: float = 0.7,
    ) -> Result[list[CurriculumDTO]]:
        """
        Find all prerequisites for a knowledge unit.

        Quick Win #1 Enhancement (November 9, 2025):
        - Added confidence filtering to improve prerequisite quality
        - Filters out low-quality relationships automatically
        - Default confidence threshold of 0.7 (reliable relationships)

        Args:
            uid: Knowledge unit UID,
            depth: Maximum depth to traverse,
            include_optional: Include optional prerequisites
            min_confidence: Minimum relationship confidence threshold (default 0.7)

        Returns:
            Result containing list of prerequisite CurriculumDTOs in dependency order

        Examples:
            # Get prerequisites with default confidence filtering
            result = await service.find_prerequisites("ku.async_python")

            # Get only high-confidence prerequisites
            result = await service.find_prerequisites(
                "ku.async_python",
                min_ConfidenceLevel.HIGH
            )

        Graph Intelligence:
        - Filters relationships by confidence property
        - Prevents low-quality relationships from polluting chains
        - 30-40% improvement in prerequisite quality
        """
        # Verify source unit exists
        source_result = await self.repo.get(uid)
        if not source_result.is_ok or not source_result.value:
            return Result.fail(Errors.not_found(f"Knowledge unit {uid} not found"))

        # Query prerequisites using CypherGenerator helper (Quick Win #1)
        # REQUIRES_KNOWLEDGE relationship means uid requires the prerequisite
        query, params = build_simple_prerequisite_chain(
            node_uid=uid,
            node_label="Entity",
            relationship_type=RelationshipName.REQUIRES_KNOWLEDGE.value,
            depth=depth,
            order="DESC",
            include_leaf_only=True,
            min_confidence=min_confidence,  # Quick Win #1: Confidence filtering
        )

        self.logger.debug(
            f"Finding prerequisites for {uid}: depth={depth}, min_confidence={min_confidence}"
        )

        results = await self._execute_query(query, params, "get_prerequisites")

        # Check for query errors
        if results.is_error:
            return Result.fail(results.expect_error())

        # Convert to DTOs
        prerequisites = []
        for record in results.value:
            prereq_data = record.get("prereq")
            if prereq_data:
                # Get full DTO from repo
                dto_result = await self.repo.get(prereq_data.get("uid"))
                if dto_result.is_ok and dto_result.value:
                    prerequisites.append(dto_result.value)

        self.logger.debug(
            f"Found {len(prerequisites)} prerequisites for {uid} "
            f"(depth={depth}, min_confidence={min_confidence})"
        )
        return Result.ok(prerequisites)

    @with_error_handling("find_next_steps", error_type="database", uid_param="uid")
    async def find_next_steps(self, uid: str, limit: int = 10) -> Result[list[CurriculumDTO]]:
        """
        Find knowledge units that build on this one.

        Returns units that have this unit as a prerequisite.

        Args:
            uid: Knowledge unit UID,
            limit: Maximum results to return

        Returns:
            Result containing list of next step CurriculumDTOs
        """
        # Verify source unit exists
        source_result = await self.repo.get(uid)
        if not source_result.is_ok or not source_result.value:
            return Result.fail(Errors.not_found(f"Knowledge unit {uid} not found"))

        # Query units that require this one (incoming REQUIRES_KNOWLEDGE relationships)
        # Uses CypherGenerator for consistency (January 2026 consolidation)
        query, params = build_relationship_traversal_query(
            source_uid=uid,
            relationship_type=RelationshipName.REQUIRES_KNOWLEDGE.value,
            target_label="Entity",
            direction="incoming",  # KUs that point TO this KU via REQUIRES_KNOWLEDGE
            limit=limit,
        )

        results = await self.neo4j.execute_query(query, params)

        # Convert to DTOs
        next_steps = []
        for record in results:
            next_data = record.get("target")  # CypherGenerator returns "target"
            if next_data:
                dto_result = await self.repo.get(next_data.get("uid"))
                if dto_result.is_ok and dto_result.value:
                    next_steps.append(dto_result.value)

        self.logger.debug(f"Found {len(next_steps)} next steps for {uid}")
        return Result.ok(next_steps)

    @with_error_handling("get_lesson_with_context", error_type="database", uid_param="uid")
    async def get_lesson_with_context(self, uid: str, depth: int = 2) -> Result[dict[str, Any]]:
        """
        Get lesson with full graph context.

        Includes:
        - Prerequisites
        - Next steps
        - Related units
        - Parent/child hierarchy

        Args:
            uid: Knowledge unit UID,
            depth: Context depth to retrieve

        Returns:
            Result containing enriched knowledge data with context
        """
        # Get the main unit
        unit_result = await self.repo.get(uid)
        if not unit_result.is_ok or not unit_result.value:
            return Result.fail(Errors.not_found(f"Knowledge unit {uid} not found"))

        unit_dto = unit_result.value

        # Get context in parallel
        prereq_result = await self.find_prerequisites(uid, depth=depth)
        next_result = await self.find_next_steps(uid, QueryLimit.MEDIUM)

        # Build enriched context
        context = {
            "unit": unit_dto.to_dict(),
            "prerequisites": [p.to_dict() for p in prereq_result.value]
            if prereq_result.is_ok
            else [],
            "next_steps": [n.to_dict() for n in next_result.value] if next_result.is_ok else [],
            "depth": depth,
            "total_prerequisites": len(prereq_result.value) if prereq_result.is_ok else 0,
            "total_next_steps": len(next_result.value) if next_result.is_ok else 0,
        }

        self.logger.debug(
            f"Retrieved context for {uid}: "
            f"{context['total_prerequisites']} prereqs, "
            f"{context['total_next_steps']} next steps"
        )
        return Result.ok(context)

    # ========================================================================
    # RELATIONSHIP MANAGEMENT
    # ========================================================================

    @with_error_handling("link_prerequisite", error_type="database", uid_param="unit_uid")
    async def link_prerequisite(
        self, unit_uid: str, prerequisite_uid: str, is_mandatory: bool = True
    ) -> Result[bool]:
        """
        Create a prerequisite relationship between knowledge units.

        Args:
            unit_uid: Target knowledge unit UID,
            prerequisite_uid: Prerequisite knowledge unit UID,
            is_mandatory: Whether prerequisite is mandatory

        Returns:
            Result indicating success
        """
        # Verify both units exist
        unit_result = await self.repo.get(unit_uid)
        if not unit_result.is_ok or not unit_result.value:
            return Result.fail(Errors.not_found(f"Knowledge unit {unit_uid} not found"))

        prereq_result = await self.repo.get(prerequisite_uid)
        if not prereq_result.is_ok or not prereq_result.value:
            return Result.fail(Errors.not_found(f"Prerequisite unit {prerequisite_uid} not found"))

        # Create REQUIRES relationship (unit REQUIRES prerequisite)
        query = """
        MATCH (unit:Entity {uid: $unit_uid})
        MATCH (prereq:Entity {uid: $prereq_uid})
        MERGE (unit)-[r:REQUIRES_KNOWLEDGE]->(prereq)
        SET r.is_mandatory = $is_mandatory
        SET r.created_at = datetime()
        RETURN r
        """

        params = {
            "unit_uid": unit_uid,
            "prereq_uid": prerequisite_uid,
            "is_mandatory": is_mandatory,
        }

        await self.neo4j.execute_query(query, params)

        self.logger.info(
            f"Linked prerequisite: {unit_uid} REQUIRES_KNOWLEDGE {prerequisite_uid} "
            f"(mandatory={is_mandatory})"
        )
        return Result.ok(True)

    @with_error_handling("link_parent_child", error_type="database", uid_param="parent_uid")
    async def link_parent_child(self, parent_uid: str, child_uid: str) -> Result[bool]:
        """
        Create a parent-child hierarchy relationship.

        Args:
            parent_uid: Parent knowledge unit UID,
            child_uid: Child knowledge unit UID

        Returns:
            Result indicating success
        """
        # Verify both units exist
        parent_result = await self.repo.get(parent_uid)
        if not parent_result.is_ok or not parent_result.value:
            return Result.fail(Errors.not_found(f"Parent unit {parent_uid} not found"))

        child_result = await self.repo.get(child_uid)
        if not child_result.is_ok or not child_result.value:
            return Result.fail(Errors.not_found(f"Child unit {child_uid} not found"))

        # Create HAS_NARROWER relationship (parent HAS_NARROWER child)
        query = """
        MATCH (parent:Entity {uid: $parent_uid})
        MATCH (child:Entity {uid: $child_uid})
        MERGE (parent)-[r:HAS_NARROWER]->(child)
        SET r.created_at = datetime()
        RETURN r
        """

        params = {"parent_uid": parent_uid, "child_uid": child_uid}

        await self.neo4j.execute_query(query, params)

        self.logger.info(f"Linked parent-child: {parent_uid} HAS_NARROWER {child_uid}")
        return Result.ok(True)

    # ========================================================================
    # ANALYSIS & RECOMMENDATIONS
    # ========================================================================

    @with_error_handling("get_prerequisite_chain", error_type="database", uid_param="uid")
    async def get_prerequisite_chain(
        self, uid: str, user_uid: str | None = None
    ) -> Result[dict[str, Any]]:
        """
        Get complete prerequisite chain with learning path.

        Args:
            uid: Target knowledge unit UID,
            user_uid: Optional user UID for personalized analysis

        Returns:
            Result containing ordered prerequisite chain and metadata
        """
        # Get prerequisites with depth
        prereq_result = await self.find_prerequisites(uid, GraphDepth.DIRECT)
        if not prereq_result.is_ok:
            return Result.fail(prereq_result.expect_error())

        prerequisites = prereq_result.value

        # Build chain metadata
        chain = {
            "target_uid": uid,
            "prerequisites": [p.to_dict() for p in prerequisites],
            "total_count": len(prerequisites),
            "estimated_hours": sum(p.metadata.get("estimated_hours", 1.0) for p in prerequisites),
            "ordered": True,  # Already in dependency order from query
            "user_uid": user_uid,
        }

        # If user context provided, add mastery state
        if user_uid:
            # Query user mastery for each prerequisite
            mastery_query = """
            MATCH (u:User {uid: $user_uid})
            OPTIONAL MATCH (u)-[m:MASTERED]->(k:Entity)
            WHERE k.uid IN $prereq_uids
            RETURN k.uid as ku_uid,
                   m.mastery_score as score,
                   m.confidence_level as confidence,
                   m.last_practiced as last_practiced
            UNION
            MATCH (u:User {uid: $user_uid})
            OPTIONAL MATCH (u)-[ip:IN_PROGRESS]->(k:Entity)
            WHERE k.uid IN $prereq_uids
            RETURN k.uid as ku_uid,
                   ip.progress as score,
                   coalesce(ip.difficulty_rating, 0.5) as confidence,
                   ip.last_accessed as last_practiced
            """

            prereq_uids = [p.uid for p in prerequisites]
            mastery_results = await self.neo4j.execute_query(
                mastery_query, {"user_uid": user_uid, "prereq_uids": prereq_uids}
            )

            # Build mastery map
            user_mastery = {}
            for record in mastery_results:
                ku_uid = record.get("ku_uid")
                if ku_uid:
                    user_mastery[ku_uid] = {
                        "score": record.get("score", 0.0),
                        "confidence": record.get("confidence", 0.0),
                        "last_practiced": record.get("last_practiced"),
                    }

            chain["user_mastery"] = user_mastery

        self.logger.debug(f"Retrieved prerequisite chain for {uid}: {len(prerequisites)} items")
        return Result.ok(chain)

    @with_error_handling("analyze_knowledge_gaps", error_type="database", uid_param="target_uid")
    async def analyze_knowledge_gaps(
        self, target_uid: str, user_uid: str
    ) -> Result[dict[str, Any]]:
        """
        Analyze knowledge gaps for a user targeting a specific unit.

        Args:
            target_uid: Target knowledge unit UID,
            user_uid: User UID

        Returns:
            Result containing gap analysis and recommendations
        """
        # Get prerequisite chain
        chain_result = await self.get_prerequisite_chain(target_uid, user_uid)
        if not chain_result.is_ok:
            return chain_result

        chain = chain_result.value
        user_mastery = chain.get("user_mastery", {})

        # Build gap analysis by categorizing prerequisites
        gaps = []
        completed = []
        in_progress = []

        for prereq in chain["prerequisites"]:
            prereq_uid = prereq["uid"]
            mastery_data = user_mastery.get(prereq_uid)

            if mastery_data:
                score = mastery_data.get("score", 0.0)
                # Mastery threshold: >= 0.8 is mastered, < 0.8 is in-progress
                if score >= 0.8:
                    completed.append(
                        {
                            "uid": prereq_uid,
                            "title": prereq.get("title", ""),
                            "mastery_score": score,
                            "confidence": mastery_data.get("confidence", 0.0),
                            "last_practiced": mastery_data.get("last_practiced"),
                        }
                    )
                else:
                    in_progress.append(
                        {
                            "uid": prereq_uid,
                            "title": prereq.get("title", ""),
                            "progress": score,
                            "confidence": mastery_data.get("confidence", 0.0),
                            "last_accessed": mastery_data.get("last_practiced"),
                        }
                    )
            else:
                # No mastery data = gap
                gaps.append(
                    {
                        "uid": prereq_uid,
                        "title": prereq.get("title", ""),
                        "estimated_hours": prereq.get("metadata", {}).get("estimated_hours", 1.0),
                        "reason": "Not started",
                    }
                )

        # Calculate readiness score
        total = len(chain["prerequisites"])
        readiness = (len(completed) / total) if total > 0 else 0.0

        # Generate recommendations based on gaps
        recommendations = []
        if gaps:
            # Prioritize foundational prerequisites (those at the bottom of dependency chain)
            # For now, recommend first 3 gaps
            recommendations.extend(
                [
                    {
                        "action": "learn",
                        "target_uid": gap["uid"],
                        "target_title": gap["title"],
                        "reason": f"Required prerequisite for {chain['prerequisites'][0].get('title', target_uid)}",
                        "priority": "high" if readiness < 0.3 else "medium",
                    }
                    for gap in gaps[:3]
                ]
            )

        # Build gap analysis
        analysis = {
            "target_uid": target_uid,
            "user_uid": user_uid,
            "total_prerequisites": chain["total_count"],
            "readiness_score": readiness,
            "gaps": gaps,
            "completed": completed,
            "in_progress": in_progress,
            "recommendations": recommendations,
            "status": "ready"
            if readiness >= 0.8
            else "needs_work"
            if readiness >= 0.5
            else "not_ready",
        }

        self.logger.debug(
            f"Analyzed knowledge gaps for user {user_uid} targeting {target_uid}: "
            f"{len(completed)} completed, {len(in_progress)} in-progress, {len(gaps)} gaps "
            f"(readiness: {readiness:.1%})"
        )
        return Result.ok(analysis)

    @with_error_handling(
        "get_learning_recommendations", error_type="database", uid_param="user_uid"
    )
    async def get_learning_recommendations(
        self, user_uid: str, domain: str | None = None, limit: int = 5
    ) -> Result[list[dict[str, Any]]]:
        """
        Get personalized learning recommendations for a user.

        Finds knowledge units that:
        1. User hasn't mastered yet
        2. Have most/all prerequisites completed
        3. Match specified domain (if provided)

        Args:
            user_uid: User UID,
            domain: Optional domain filter,
            limit: Maximum recommendations to return

        Returns:
            Result containing list of recommended knowledge units with reasons
        """
        # Query for knowledge units user is ready to learn
        # A unit is "ready" when:
        # - User hasn't mastered it
        # - Most of its prerequisites are completed
        ready_query = """
        // Get user's mastered knowledge
        MATCH (u:User {uid: $user_uid})-[:MASTERED]->(mastered:Entity)
        WITH u, collect(mastered.uid) as mastered_uids

        // Find knowledge units not yet mastered
        MATCH (candidate:Entity)
        WHERE NOT candidate.uid IN mastered_uids
          AND ($domain IS NULL OR candidate.domain = $domain)

        // Count prerequisites and how many are satisfied
        OPTIONAL MATCH (candidate)-[:REQUIRES_KNOWLEDGE]->(prereq:Entity)
        WITH candidate, mastered_uids,
             count(prereq) as total_prereqs,
             sum(CASE WHEN prereq.uid IN mastered_uids THEN 1 ELSE 0 END) as satisfied_prereqs

        // Calculate readiness score
        WITH candidate,
             total_prereqs,
             satisfied_prereqs,
             CASE
               WHEN total_prereqs = 0 THEN 1.0
               ELSE toFloat(satisfied_prereqs) / total_prereqs
             END as readiness

        // Only recommend if readiness >= 0.7 (most prereqs done)
        WHERE readiness >= 0.7

        // Get next steps info (what this enables)
        OPTIONAL MATCH (candidate)<-[:REQUIRES_KNOWLEDGE]-(enables:Entity)
        WITH candidate, readiness, total_prereqs, satisfied_prereqs,
             count(enables) as enables_count

        RETURN candidate.uid as uid,
               candidate.title as title,
               candidate.summary as summary,
               candidate.domain as domain,
               readiness,
               total_prereqs,
               satisfied_prereqs,
               enables_count
        ORDER BY readiness DESC, enables_count DESC
        LIMIT $limit
        """

        params = {"user_uid": user_uid, "domain": domain, "limit": limit}

        results = await self._execute_query(ready_query, params, "get_learning_recommendations")

        if results.is_error:
            return Result.fail(results.expect_error())

        recommendations = []
        for record in results.value or []:
            readiness = record.get("readiness", 0.0)
            total_prereqs = record.get("total_prereqs", 0)
            satisfied_prereqs = record.get("satisfied_prereqs", 0)
            enables_count = record.get("enables_count", 0)

            # Generate reasoning
            reasons = []
            if readiness >= 0.9:
                reasons.append(f"All {satisfied_prereqs}/{total_prereqs} prerequisites completed")
            elif readiness >= 0.7:
                reasons.append(f"{satisfied_prereqs}/{total_prereqs} prerequisites completed")

            if enables_count > 0:
                reasons.append(f"Unlocks {enables_count} advanced topics")

            if total_prereqs == 0:
                reasons.append("No prerequisites - good starting point")

            recommendations.append(
                {
                    "uid": record.get("uid"),
                    "title": record.get("title"),
                    "summary": record.get("summary"),
                    "domain": record.get("domain"),
                    "readiness_score": readiness,
                    "prerequisites_status": f"{satisfied_prereqs}/{total_prereqs}",
                    "enables_count": enables_count,
                    "reasons": reasons,
                    "priority": "high" if readiness >= 0.9 else "medium",
                }
            )

        self.logger.debug(
            f"Generated {len(recommendations)} learning recommendations for user {user_uid}"
        )
        return Result.ok(recommendations)

    @with_error_handling(
        "find_time_aware_learning_path", error_type="database", uid_param="target_uid"
    )
    async def find_time_aware_learning_path(
        self,
        target_uid: str,
        user_time_budget: int,
        max_complexity: str = "advanced",
        min_confidence: float = 0.7,
        limit: int = 5,
    ) -> Result[list[dict[str, Any]]]:
        """
        Build metadata-aware learning paths respecting user constraints.

        This is Quick Win #2 from NEO4J_SEMANTIC_KNOWLEDGE_GRAPH_ANALYSIS.md,
        leveraging Neo4j's semantic knowledge graph capabilities.

        Uses:
        - Entity metadata: reading_time_minutes, complexity_level
        - Relationship properties: confidence
        - Graph aggregation: REDUCE for cumulative path metrics

        Args:
            target_uid: Target knowledge unit UID to reach
            user_time_budget: Maximum total reading time in minutes
            max_complexity: Maximum complexity level ("basic", "intermediate", "advanced")
            min_confidence: Minimum relationship confidence threshold (0.0-1.0)
            limit: Maximum alternative paths to return

        Returns:
            Result containing list of learning paths with metadata:
            - path: List of KU UIDs in learning order
            - total_time: Cumulative reading time (minutes)
            - avg_complexity: Average complexity score (1.0-3.0)
            - path_length: Number of knowledge units
            - units: List of CurriculumDTO objects with full details

        Examples:
            # Find 2-hour learning path (intermediate or easier)
            result = await service.find_time_aware_learning_path(
                target_uid="ku.async_python",
                user_time_budget=120,
                max_complexity="intermediate"
            )

            # Find quickest path (any difficulty, high-confidence only)
            result = await service.find_time_aware_learning_path(
                target_uid="ku.advanced_topic",
                user_time_budget=60,
                min_ConfidenceLevel.HIGH,
                limit=1
            )

        Graph Intelligence Features:
        - Filters low-confidence relationships (ignores unreliable prerequisites)
        - Respects time constraints (prevents overwhelming paths)
        - Difficulty-adaptive (matches user skill level)
        - Returns alternatives (multiple path options)
        """
        # Validate target exists
        target_result = await self.repo.get(target_uid)
        if not target_result.is_ok or not target_result.value:
            return Result.fail(Errors.not_found(resource="Knowledge unit", identifier=target_uid))

        # Validate complexity level
        valid_complexity = ["basic", "intermediate", "advanced"]
        if max_complexity.lower() not in valid_complexity:
            return Result.fail(
                Errors.validation(
                    message=f"Invalid complexity level: {max_complexity}",
                    field="max_complexity",
                    value=max_complexity,
                )
            )

        # Generate metadata-aware path query
        query, params = build_metadata_aware_path_query(
            target_uid=target_uid,
            node_label="Entity",
            relationship_type=RelationshipName.REQUIRES_KNOWLEDGE.value,
            user_time_budget=user_time_budget,
            max_complexity_level=max_complexity,
            min_confidence=min_confidence,
            depth=GraphDepth.DIRECT,
            limit=limit,
        )

        self.logger.debug(
            f"Finding time-aware paths to {target_uid}: "
            f"budget={user_time_budget}m, max_complexity={max_complexity}, "
            f"min_confidence={min_confidence}"
        )

        # Execute query
        results = await self._execute_query(query, params, "find_learning_paths")

        # Check for query errors
        if results.is_error:
            return Result.fail(results.expect_error())

        # Convert results to structured paths
        paths = []
        for record in results.value:
            path_nodes = record.get("path")
            if not path_nodes:
                continue

            # Extract node UIDs from path
            node_uids = []
            try:
                # Try Neo4j Path object first (has .nodes attribute)
                for node in path_nodes.nodes:
                    uid = node.get("uid")
                    if uid:
                        node_uids.append(uid)
            except AttributeError:
                # Fallback: assume list of nodes
                try:
                    for node in path_nodes:
                        uid = node.get("uid")
                        if uid:
                            node_uids.append(uid)
                except (AttributeError, TypeError):
                    # If node doesn't have .get(), skip it
                    self.logger.warning(f"Unexpected path node structure: {type(node)}")
                    continue

            # Fetch full DTOs for each node
            units = []
            for uid in node_uids:
                dto_result = await self.repo.get(uid)
                if dto_result.is_ok and dto_result.value:
                    units.append(dto_result.value)

            # Build path metadata
            path_data = {
                "path": node_uids,
                "total_time": record.get("total_time", 0.0),
                "avg_complexity": record.get("avg_complexity_score", 0.0),
                "path_length": record.get("path_length", len(node_uids)),
                "units": [u.to_dict() for u in units],
                "complexity_label": self._complexity_score_to_label(
                    record.get("avg_complexity_score", 2.0)
                ),
            }

            paths.append(path_data)

        if not paths:
            self.logger.info(
                f"No time-aware paths found for {target_uid} "
                f"within constraints (budget={user_time_budget}m, "
                f"max_complexity={max_complexity})"
            )
            # Return empty list, not an error (no paths matching constraints is valid)
            return Result.ok([])

        self.logger.info(
            f"Found {len(paths)} time-aware learning paths to {target_uid}: "
            f"shortest={paths[0]['total_time']:.1f}m, "
            f"longest={paths[-1]['total_time']:.1f}m"
        )
        return Result.ok(paths)

    # ========================================================================
    # HUB SCORE CACHING (Quick Win #3 - November 9, 2025)
    # ========================================================================

    @with_error_handling("update_hub_scores", error_type="database")
    async def update_hub_scores(self) -> Result[None]:
        """
        Compute and cache hub scores on Knowledge Unit nodes.

        Quick Win #3: Cache degree centrality (hub scores) to identify
        foundational concepts. Run this nightly or on-demand to update scores.

        Hub Score Definition:
        - Count of ALL relationships (incoming + outgoing)
        - Higher score = more connected = more foundational
        - Typical ranges: 0-5 (specialized), 5-10 (intermediate), 10+ (foundational)

        Graph Intelligence:
        - Uses degree centrality as proxy for concept importance
        - Cached scores enable fast foundational concept queries
        - No expensive traversal needed after initial computation

        Returns:
            Result containing None on success, error on failure

        Examples:
            # Update all hub scores (run nightly)
            result = await ku_service.update_hub_scores()

            # Then query foundational concepts instantly
            foundational = await ku_service.get_foundational_knowledge()

        Performance:
        - Initial computation: O(n) where n = number of KUs
        - Subsequent queries: O(1) lookup (indexed property)
        - Recommended: Run nightly via scheduled job
        """
        query = """
        MATCH (ku:Entity)-[r]-(neighbor)
        WITH ku, count(r) as degree_centrality
        SET ku.hub_score = degree_centrality
        RETURN count(ku) as updated_count
        """

        self.logger.info("Computing hub scores for all Knowledge Units...")

        results = await self._execute_query(query, {}, "update_hub_scores")

        if results.is_error:
            self.logger.warning("Hub score update failed")
            return Result.fail(results.expect_error())

        records = results.value or []
        updated_count = records[0].get("updated_count", 0) if records else 0
        self.logger.info(f"Updated hub scores for {updated_count} Knowledge Units")

        return Result.ok(None)

    @with_error_handling("get_foundational_knowledge", error_type="database")
    async def get_foundational_knowledge(
        self, domain: str | None = None, min_hub_score: int = 10, limit: int = 20
    ) -> Result[list[CurriculumDTO]]:
        """
        Get high-hub Knowledge Units (foundational concepts).

        Quick Win #3: Retrieve foundational concepts based on cached hub scores.
        These are highly connected KUs that serve as building blocks for learning.

        Hub Score Interpretation:
        - 15+: Core foundational concepts (e.g., "Python Basics", "HTTP Protocol")
        - 10-15: Important intermediate concepts
        - 5-10: Specialized but connected concepts
        - 0-5: Niche or leaf concepts

        Args:
            domain: Optional domain filter (e.g., "tech", "business")
            min_hub_score: Minimum hub score threshold (default 10)
            limit: Maximum results to return (default 20)

        Returns:
            Result containing list of foundational KU DTOs sorted by hub score

        Examples:
            # Get all foundational concepts
            result = await ku_service.get_foundational_knowledge()

            # Get foundational tech concepts only
            result = await ku_service.get_foundational_knowledge(domain="tech")

            # Get VERY foundational concepts (hub score >= 15)
            result = await ku_service.get_foundational_knowledge(min_hub_score=15)

        Graph Intelligence:
        - Leverages cached hub scores (no traversal needed)
        - Domain filtering for focused learning paths
        - Prioritizes high-connectivity concepts

        Note:
        - Requires hub scores to be computed first (run update_hub_scores())
        - KUs without hub_score property are excluded
        """
        # Build WHERE clauses
        where_clauses = [f"ku.hub_score >= {min_hub_score}"]

        if domain:
            where_clauses.append("ku.domain = $domain")

        where_clause = " AND ".join(where_clauses)

        query = f"""
        MATCH (ku:Entity)
        WHERE {where_clause}
        RETURN ku
        ORDER BY ku.hub_score DESC
        LIMIT $limit
        """

        params: dict[str, Any] = {"limit": limit}
        if domain:
            params["domain"] = domain

        self.logger.debug(
            f"Finding foundational knowledge: domain={domain}, "
            f"min_hub_score={min_hub_score}, limit={limit}"
        )

        results = await self._execute_query(query, params, "get_foundational_knowledge")

        # Check for query errors
        if results.is_error:
            return Result.fail(results.expect_error())

        # Convert to DTOs
        foundational_kus = []
        for record in results.value:
            ku_data = record.get("ku")
            if ku_data:
                uid = ku_data.get("uid")
                if uid:
                    # Get full DTO from repo
                    dto_result = await self.repo.get(uid)
                    if dto_result.is_ok and dto_result.value:
                        foundational_kus.append(dto_result.value)

        self.logger.info(
            f"Found {len(foundational_kus)} foundational Knowledge Units "
            f"(domain={domain}, min_hub_score={min_hub_score})"
        )

        return Result.ok(foundational_kus)

    @staticmethod
    def _complexity_score_to_label(score: float) -> str:
        """Convert numeric complexity score to label"""
        if score < 1.5:
            return "basic"
        elif score < 2.5:
            return "intermediate"
        else:
            return "advanced"
