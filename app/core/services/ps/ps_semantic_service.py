"""
Path Step Semantic Service - Semantic Relationship Reads
=========================================================

Clean rewrite following CLAUDE.md patterns.
Handles all semantic relationship operations for path steps.

**Responsibilities:**
- Query semantic neighborhoods and relationships by type
- Discover relationship patterns
- Cross-domain semantic bridges

**Dependencies:**
- Backend protocol (via repo)
- SemanticRelationshipType (relationship types)
"""

from typing import Any

from core.infrastructure.relationships.semantic_relationships import (
    SemanticRelationshipType,
)
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result


class PsSemanticService:
    """
    Semantic relationship management for path steps.
    """

    def __init__(self, repo: Any = None, intelligence: Any = None) -> None:
        """
        Initialize semantic service with required dependencies.

        Args:
            repo: Backend protocol for path step operations
            intelligence: Optional intelligence service for relationship inference
        """
        # Fail-fast validation (CLAUDE.md: no graceful degradation)
        if not repo:
            raise ValueError("Path step repository is required")

        self.repo = repo
        self.intelligence = intelligence

        self.logger = get_logger("skuel.services.ps.semantic")

    # ========================================================================
    # SEMANTIC NEIGHBORHOOD
    # ========================================================================

    @with_error_handling("get_semantic_neighborhood", error_type="database", uid_param="uid")
    async def get_semantic_neighborhood(
        self,
        uid: str,
        depth: int = 2,
        semantic_types: list[SemanticRelationshipType] | None = None,
        min_confidence: float = 0.0,
    ) -> Result[dict[str, Any]]:
        """
        Get the semantic neighborhood of a path step.

        Returns all semantically related units within the specified depth,
        optionally filtered by relationship types and confidence threshold.

        Args:
            uid: Path step UID,
            depth: Maximum depth to traverse,
            semantic_types: Optional list of relationship types to include,
            min_confidence: Minimum confidence threshold (0.0-1.0)

        Returns:
            Result containing semantic neighborhood data with nodes and relationships
        """
        # Verify source unit exists
        source_result = await self.repo.get(uid)
        if not source_result.is_ok or not source_result.value:
            return Result.fail(Errors.not_found("PathStep", uid))

        # None means "include all semantic relationship types"
        resolved_types = (
            semantic_types if semantic_types is not None else list(SemanticRelationshipType)
        )

        # Execute query via backend
        results = await self.repo.query_semantic_neighborhood(
            uid, resolved_types, depth, min_confidence
        )

        # Check for query errors
        if results.is_error:
            return Result.fail(results)

        # Process results into neighborhood structure
        neighbors = []
        relationships = []
        seen_uids = {uid}  # Track to avoid duplicates

        for record in results.value:
            # Extract neighbor node
            neighbor_data = record.get("neighbor")
            if neighbor_data:
                neighbor_uid = neighbor_data.get("uid")
                if neighbor_uid and neighbor_uid not in seen_uids:
                    seen_uids.add(neighbor_uid)

                    # Get full DTO from repo
                    dto_result = await self.repo.get(neighbor_uid)
                    if dto_result.is_ok and dto_result.value:
                        neighbors.append(dto_result.value)

            # Extract relationship
            rel_data = record.get("relationship")
            if rel_data:
                relationships.append(
                    {
                        "type": rel_data.get("type", "UNKNOWN"),
                        "confidence": rel_data.get("confidence", 1.0),
                        "strength": rel_data.get("strength", 1.0),
                        "source": rel_data.get("source"),
                        "notes": rel_data.get("notes"),
                    }
                )

        # Build neighborhood context
        neighborhood = {
            "central_uid": uid,
            "depth": depth,
            "neighbors": [n.to_dict() for n in neighbors],
            "relationships": relationships,
            "total_neighbors": len(neighbors),
            "total_relationships": len(relationships),
            "semantic_types_used": [st.value for st in semantic_types] if semantic_types else None,
            "min_confidence": min_confidence,
        }

        self.logger.debug(
            f"Retrieved semantic neighborhood for {uid}: "
            f"{len(neighbors)} neighbors, {len(relationships)} relationships"
        )
        return Result.ok(neighborhood)

    # ========================================================================
    # RELATIONSHIP QUERIES
    # ========================================================================

    @with_error_handling("get_relationships_by_type", error_type="database", uid_param="uid")
    async def get_relationships_by_type(
        self, uid: str, predicate: SemanticRelationshipType, direction: str = "outgoing"
    ) -> Result[list[dict[str, Any]]]:
        """
        Get all relationships of a specific type for a path step.

        Args:
            uid: Path step UID,
            predicate: Semantic relationship type to query,
            direction: "outgoing", "incoming", or "both"

        Returns:
            Result containing list of relationships with metadata
        """
        # Verify unit exists
        source_result = await self.repo.get(uid)
        if not source_result.is_ok or not source_result.value:
            return Result.fail(Errors.not_found("PathStep", uid))

        rel_name = predicate.to_neo4j_name()

        results = await self.repo.query_relationships_by_type(
            uid, rel_name, direction, semantic_type=predicate.value
        )

        # Check for query errors
        if results.is_error:
            return Result.fail(results)

        relationships = []
        for record in results.value:
            target_data = record.get("target")
            rel_data = record.get("r")

            if target_data and rel_data:
                relationships.append(
                    {
                        "subject_uid": record.get("subject_uid"),
                        "predicate": predicate.value,
                        "object_uid": record.get("object_uid"),
                        "target_title": target_data.get("title"),
                        "confidence": rel_data.get("confidence", 1.0),
                        "strength": rel_data.get("strength", 1.0),
                        "notes": rel_data.get("notes"),
                    }
                )

        self.logger.debug(
            f"Found {len(relationships)} {direction} {predicate.value} relationships for {uid}"
        )
        return Result.ok(relationships)

    # ========================================================================
    # RELATIONSHIP DISCOVERY
    # ========================================================================

    @with_error_handling("discover_semantic_bridges", error_type="database", uid_param="uid")
    async def discover_semantic_bridges(
        self, uid: str, target_domain: str | None = None, max_results: int = 10
    ) -> Result[list[dict[str, Any]]]:
        """
        Discover cross-domain semantic bridges from a path step.

        Finds units in other domains that share semantic patterns or
        principles with the source path step.

        Args:
            uid: Source path step UID,
            target_domain: Optional target domain to focus on,
            max_results: Maximum number of bridges to return

        Returns:
            Result containing list of discovered bridges
        """
        # Verify source unit exists
        source_result = await self.repo.get(uid)
        if not source_result.is_ok or not source_result.value:
            return Result.fail(Errors.not_found("PathStep", uid))

        results = await self.repo.discover_semantic_bridges(uid, target_domain, max_results)

        # Check for query errors
        if results.is_error:
            return Result.fail(results)

        bridges = []
        for record in results.value:
            target_data = record.get("target")
            if target_data:
                bridges.append(
                    {
                        "target_uid": target_data.get("uid"),
                        "target_title": target_data.get("title"),
                        "target_domain": target_data.get("domain"),
                        "bridge_type": record.get("bridge_type"),
                        "shared_concept": record.get("shared_concept"),
                        "transferability": record.get("combined_confidence", 1.0) / 2.0,
                    }
                )

        self.logger.debug(f"Discovered {len(bridges)} semantic bridges for {uid}")
        return Result.ok(bridges)

    @with_error_handling("infer_relationships", error_type="database", uid_param="uid")
    async def infer_relationships(
        self, uid: str, max_inferences: int = 10, min_confidence: float = 0.7
    ) -> Result[list[dict[str, Any]]]:
        """
        Infer potential semantic relationships using graph patterns.

        Uses existing relationship patterns to suggest new relationships
        that might be valid.

        Args:
            uid: Path step UID,
            max_inferences: Maximum inferences to return,
            min_confidence: Minimum confidence threshold

        Returns:
            Result containing list of inferred relationships with confidence scores
        """
        # Verify unit exists
        source_result = await self.repo.get(uid)
        if not source_result.is_ok or not source_result.value:
            return Result.fail(Errors.not_found("PathStep", uid))

        results = await self.repo.infer_transitive_relationships(uid, max_inferences)

        # Check for query errors
        if results.is_error:
            return Result.fail(results)

        inferences = []
        for record in results.value:
            confidence = record.get("confidence", 0.0)
            if confidence >= min_confidence:
                target_data = record.get("target")
                if target_data:
                    inferences.append(
                        {
                            "target_uid": target_data.get("uid"),
                            "target_title": target_data.get("title"),
                            "inferred_type": record.get("inferred_type"),
                            "via_uid": record.get("via_uid"),
                            "confidence": confidence,
                            "reasoning": f"Transitive relationship via {record.get('via_uid')}",
                        }
                    )

        self.logger.debug(f"Inferred {len(inferences)} potential relationships for {uid}")
        return Result.ok(inferences)
