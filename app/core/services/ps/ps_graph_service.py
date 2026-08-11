"""
Path Step Graph Service - Graph Navigation and Relationships
=============================================================

Clean rewrite following CLAUDE.md patterns.
Handles all graph operations for path steps.

**Responsibilities:**
- Graph traversal (prerequisites, next steps)
- Relationship management (create, link, query)
- Knowledge gap analysis
- Learning recommendations
- Prerequisite chains

**Dependencies:**
- PathStepOperations (backend protocol)
- GraphIntelligence service (smart traversal)
"""

from dataclasses import asdict
from typing import Any

from core.constants import GraphDepth
from core.models.pathways.path_step import PathStep
from core.models.type_hints import UserUID
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result


class PsGraphService:
    """
    Graph navigation and relationship operations for path steps.
    """

    def __init__(self, repo=None, graph_intel=None) -> None:
        """
        Initialize graph service with required dependencies.

        Args:
            repo: PathStepOperations backend
            graph_intel: Graph intelligence service for smart traversal
        """
        # Fail-fast validation (CLAUDE.md: no graceful degradation)
        if not repo:
            raise ValueError("PathStep repository is required")

        self.repo = repo
        self.graph_intel = graph_intel

        self.logger = get_logger("skuel.services.ps.graph")

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
    ) -> Result[list[PathStep]]:
        """
        Find all prerequisites for a path step.

        Quick Win #1 Enhancement (November 9, 2025):
        - Added confidence filtering to improve prerequisite quality
        - Filters out low-quality relationships automatically
        - Default confidence threshold of 0.7 (reliable relationships)

        Args:
            uid: Path step UID,
            depth: Maximum depth to traverse,
            include_optional: Include optional prerequisites
            min_confidence: Minimum relationship confidence threshold (default 0.7)

        Returns:
            Result containing list of prerequisite CurriculumDTOs in dependency order
        """
        # Verify source unit exists
        source_result = await self.repo.get(uid)
        if not source_result.is_ok or not source_result.value:
            return Result.fail(Errors.not_found(f"Path step {uid} not found"))

        self.logger.debug(
            f"Finding prerequisites for {uid}: depth={depth}, min_confidence={min_confidence}"
        )

        results = await self.repo.find_prerequisite_chain(uid, depth, min_confidence)

        # Check for query errors
        if results.is_error:
            return Result.fail(results)

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
    async def find_next_steps(self, uid: str, limit: int = 10) -> Result[list[PathStep]]:
        """
        Find path steps that build on this one.

        Returns steps that have this step as a prerequisite.

        Args:
            uid: Path step UID,
            limit: Maximum results to return

        Returns:
            Result containing list of next step CurriculumDTOs
        """
        # Verify source unit exists
        source_result = await self.repo.get(uid)
        if not source_result.is_ok or not source_result.value:
            return Result.fail(Errors.not_found(f"Path step {uid} not found"))

        results = await self.repo.find_next_steps(uid, limit)

        if results.is_error:
            return Result.fail(results)

        # Convert to DTOs
        next_steps = []
        for record in results.value:
            next_data = record.get("target")  # the cypher/ builder returns "target"
            if next_data:
                dto_result = await self.repo.get(next_data.get("uid"))
                if dto_result.is_ok and dto_result.value:
                    next_steps.append(dto_result.value)

        self.logger.debug(f"Found {len(next_steps)} next steps for {uid}")
        return Result.ok(next_steps)

    # ========================================================================
    # RELATIONSHIP MANAGEMENT
    # ========================================================================

    @with_error_handling("link_prerequisite", error_type="database", uid_param="unit_uid")
    async def link_prerequisite(
        self, unit_uid: str, prerequisite_uid: str, is_mandatory: bool = True
    ) -> Result[bool]:
        """
        Create a prerequisite relationship between path steps.

        Args:
            unit_uid: Target path step UID,
            prerequisite_uid: Prerequisite path step UID,
            is_mandatory: Whether prerequisite is mandatory

        Returns:
            Result indicating success
        """
        # Verify both units exist
        unit_result = await self.repo.get(unit_uid)
        if not unit_result.is_ok or not unit_result.value:
            return Result.fail(Errors.not_found(f"Path step {unit_uid} not found"))

        prereq_result = await self.repo.get(prerequisite_uid)
        if not prereq_result.is_ok or not prereq_result.value:
            return Result.fail(Errors.not_found(f"Prerequisite step {prerequisite_uid} not found"))

        await self.repo.link_prerequisite(unit_uid, prerequisite_uid, is_mandatory)

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
            parent_uid: Parent path step UID,
            child_uid: Child path step UID

        Returns:
            Result indicating success
        """
        # Verify both units exist
        parent_result = await self.repo.get(parent_uid)
        if not parent_result.is_ok or not parent_result.value:
            return Result.fail(Errors.not_found(f"Parent step {parent_uid} not found"))

        child_result = await self.repo.get(child_uid)
        if not child_result.is_ok or not child_result.value:
            return Result.fail(Errors.not_found(f"Child step {child_uid} not found"))

        await self.repo.link_parent_child(parent_uid, child_uid)

        self.logger.info(f"Linked parent-child: {parent_uid} HAS_NARROWER {child_uid}")
        return Result.ok(True)

    # ========================================================================
    # ANALYSIS & RECOMMENDATIONS
    # ========================================================================

    @with_error_handling("get_prerequisite_chain", error_type="database", uid_param="uid")
    async def get_prerequisite_chain(
        self, uid: str, user_uid: UserUID | None = None
    ) -> Result[dict[str, Any]]:
        """
        Get complete prerequisite chain with learning path.

        Args:
            uid: Target path step UID,
            user_uid: Optional user UID for personalized analysis

        Returns:
            Result containing ordered prerequisite chain and metadata
        """
        # Get prerequisites with depth
        prereq_result = await self.find_prerequisites(uid, GraphDepth.DIRECT)
        if not prereq_result.is_ok:
            return Result.fail(prereq_result)

        prerequisites = prereq_result.value

        # Build chain metadata
        chain = {
            "target_uid": uid,
            "prerequisites": [asdict(p) for p in prerequisites],
            "total_count": len(prerequisites),
            "estimated_hours": sum(p.metadata.get("estimated_hours", 1.0) for p in prerequisites),
            "ordered": True,  # Already in dependency order from query
            "user_uid": user_uid,
        }

        # If user context provided, add mastery state
        if user_uid:
            prereq_uids = [p.uid for p in prerequisites]
            mastery_results = await self.repo.query_user_mastery_for_prereqs(user_uid, prereq_uids)

            if mastery_results.is_ok:
                # Build mastery map
                user_mastery = {}
                for record in mastery_results.value:
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
        self, target_uid: str, user_uid: UserUID
    ) -> Result[dict[str, Any]]:
        """
        Analyze knowledge gaps for a user targeting a specific path step.

        Args:
            target_uid: Target path step UID,
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
        self, user_uid: UserUID, domain: str | None = None, limit: int = 5
    ) -> Result[list[dict[str, Any]]]:
        """
        Get personalized learning recommendations for a user.

        Finds path steps that:
        1. User hasn't mastered yet
        2. Have most/all prerequisites completed
        3. Match specified domain (if provided)

        Args:
            user_uid: User UID,
            domain: Optional domain filter,
            limit: Maximum recommendations to return

        Returns:
            Result containing list of recommended path steps with reasons
        """
        results = await self.repo.find_learning_recommendations(user_uid, domain, limit)

        if results.is_error:
            return Result.fail(results)

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

    # ========================================================================
    # HUB SCORE CACHING (Quick Win #3 - November 9, 2025)
    # ========================================================================

    @with_error_handling("update_hub_scores", error_type="database")
    async def update_hub_scores(self) -> Result[None]:
        """
        Compute and cache hub scores on path step nodes.

        Returns:
            Result containing None on success, error on failure
        """
        self.logger.info("Computing hub scores for all path steps...")

        results = await self.repo.compute_hub_scores()

        if results.is_error:
            self.logger.warning("Hub score update failed")
            return Result.fail(results)

        records = results.value or []
        updated_count = records[0].get("updated_count", 0) if records else 0
        self.logger.info(f"Updated hub scores for {updated_count} path steps")

        return Result.ok(None)

    @with_error_handling("get_foundational_knowledge", error_type="database")
    async def get_foundational_knowledge(
        self, domain: str | None = None, min_hub_score: int = 10, limit: int = 20
    ) -> Result[list[PathStep]]:
        """
        Get high-hub path steps (foundational concepts).

        Args:
            domain: Optional domain filter (e.g., "tech", "business")
            min_hub_score: Minimum hub score threshold (default 10)
            limit: Maximum results to return (default 20)

        Returns:
            Result containing list of foundational path step DTOs sorted by hub score
        """
        self.logger.debug(
            f"Finding foundational knowledge: domain={domain}, "
            f"min_hub_score={min_hub_score}, limit={limit}"
        )

        results = await self.repo.query_foundational_knowledge(domain, min_hub_score, limit)

        # Check for query errors
        if results.is_error:
            return Result.fail(results)

        # Convert to DTOs
        foundational_steps = []
        for record in results.value:
            step_data = record.get("ku")
            if step_data:
                uid = step_data.get("uid")
                if uid:
                    # Get full DTO from repo
                    dto_result = await self.repo.get(uid)
                    if dto_result.is_ok and dto_result.value:
                        foundational_steps.append(dto_result.value)

        self.logger.info(
            f"Found {len(foundational_steps)} foundational path steps "
            f"(domain={domain}, min_hub_score={min_hub_score})"
        )

        return Result.ok(foundational_steps)
