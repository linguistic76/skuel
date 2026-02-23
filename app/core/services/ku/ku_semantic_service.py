"""
Knowledge Semantic Service - Semantic Relationship Management
==============================================================

Clean rewrite following CLAUDE.md patterns.
Handles all semantic relationship operations for knowledge units.

**Responsibilities:**
- Create knowledge units with semantic relationships
- Query semantic neighborhoods
- Manage semantic relationships (add, remove, update)
- Discover relationship patterns
- Cross-domain semantic bridges

**Dependencies:**
- KuOperations (backend protocol)
- Neo4jAdapter (graph operations)
- CypherGenerator (semantic query building)
- SemanticRelationshipType (relationship types)
"""

from typing import Any

from core.infrastructure.relationships.semantic_relationships import (
    RelationshipMetadata,
    SemanticRelationshipType,
    SemanticTriple,
)
from core.models.curriculum.curriculum_dto import CurriculumDTO
from core.models.query import build_semantic_context
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result


class KuSemanticService:
    """
    Semantic relationship management for knowledge units.


    Source Tag: "ku_semantic_service_explicit"
    - Format: "ku_semantic_service_explicit" for user-created relationships
    - Format: "ku_semantic_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from ku_semantic metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging
    """

    def __init__(self, repo=None, neo4j_adapter=None, intelligence=None) -> None:
        """
        Initialize semantic service with required dependencies.

        Args:
            repo: KuOperations backend,
            neo4j_adapter: Neo4j adapter for graph operations,
            intelligence: Optional intelligence service for relationship inference
        """
        # Fail-fast validation (CLAUDE.md: no graceful degradation)
        if not repo:
            raise ValueError("KU repository is required")
        if not neo4j_adapter:
            raise ValueError("Neo4j adapter is required for semantic operations")

        self.repo = repo
        self.neo4j = neo4j_adapter
        self.intelligence = intelligence

        self.logger = get_logger("skuel.services.ku.semantic")

    # ========================================================================
    # CREATE WITH RELATIONSHIPS
    # ========================================================================

    @with_error_handling("create_with_semantic_relationships", error_type="database")
    async def create_with_semantic_relationships(
        self, ku_data: dict[str, Any], relationships: list[SemanticTriple]
    ) -> Result[CurriculumDTO]:
        """
        Create a knowledge unit with semantic relationships.

        Args:
            ku_data: Knowledge unit data (title, content, domain, etc.),
            relationships: List of semantic triples to create

        Returns:
            Result containing created CurriculumDTO with relationships
        """
        # First, create the knowledge unit
        create_result = await self.repo.create(ku_data)
        if not create_result.is_ok or not create_result.value:
            return Result.fail(
                Errors.database(
                    operation="create_with_semantic_relationships",
                    message="Failed to create knowledge unit",
                )
            )

        ku_dto = create_result.value
        uid = ku_dto.uid

        # Create semantic relationships
        for triple in relationships:
            # Update subject to be the newly created unit
            triple_to_create = SemanticTriple(
                subject=uid,
                predicate=triple.predicate,
                object=triple.object,
                metadata=triple.metadata,
            )

            # Create relationship in Neo4j
            await self._create_semantic_relationship(triple_to_create)

        self.logger.info(
            f"Created knowledge unit {uid} with {len(relationships)} semantic relationships"
        )

        # Refresh DTO to include relationships
        refresh_result = await self.repo.get(uid)
        if refresh_result.is_ok and refresh_result.value:
            return Result.ok(refresh_result.value)

        return Result.ok(ku_dto)

    @with_error_handling("_create_semantic_relationship", error_type="database")
    async def _create_semantic_relationship(self, triple: SemanticTriple) -> Result[bool]:
        """
        Internal method to create a single semantic relationship.

        Args:
            triple: Semantic triple to create

        Returns:
            Result indicating success
        """
        query = triple.to_cypher_merge()
        params = triple.to_cypher_params()

        await self.neo4j.execute_query(query, params)

        self.logger.debug(f"Created semantic relationship: {triple}")
        return Result.ok(True)

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
        Get the semantic neighborhood of a knowledge unit.

        Returns all semantically related units within the specified depth,
        optionally filtered by relationship types and confidence threshold.

        Args:
            uid: Knowledge unit UID,
            depth: Maximum depth to traverse,
            semantic_types: Optional list of relationship types to include,
            min_confidence: Minimum confidence threshold (0.0-1.0)

        Returns:
            Result containing semantic neighborhood data with nodes and relationships
        """
        # Verify source unit exists
        source_result = await self.repo.get(uid)
        if not source_result.is_ok or not source_result.value:
            return Result.fail(Errors.not_found(f"Knowledge unit {uid} not found"))

        # Build semantic context query
        query, params = build_semantic_context(
            node_uid=uid,
            semantic_types=semantic_types,
            depth=depth,
            min_confidence=min_confidence,
        )

        # Execute query
        results = await self.neo4j.execute_query(query, params)

        # Check for query errors
        if results.is_error:
            return Result.fail(results.expect_error())

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
    # RELATIONSHIP MANAGEMENT
    # ========================================================================

    @with_error_handling(
        "add_semantic_relationship", error_type="database", uid_param="subject_uid"
    )
    async def add_semantic_relationship(
        self,
        subject_uid: str,
        predicate: SemanticRelationshipType,
        object_uid: str,
        confidence: float = 1.0,
        strength: float = 1.0,
        notes: str | None = None,
    ) -> Result[bool]:
        """
        Add a semantic relationship between two knowledge units.

        Args:
            subject_uid: Subject knowledge unit UID,
            predicate: Semantic relationship type,
            object_uid: Object knowledge unit UID,
            confidence: Confidence in relationship (0.0-1.0),
            strength: Strength of relationship (0.0-1.0),
            notes: Optional notes about the relationship

        Returns:
            Result indicating success
        """
        # Verify both units exist
        subject_result = await self.repo.get(subject_uid)
        if not subject_result.is_ok or not subject_result.value:
            return Result.fail(Errors.not_found(f"Subject unit {subject_uid} not found"))

        object_result = await self.repo.get(object_uid)
        if not object_result.is_ok or not object_result.value:
            return Result.fail(Errors.not_found(f"Object unit {object_uid} not found"))

        # Create semantic triple
        metadata = RelationshipMetadata(confidence=confidence, strength=strength, notes=notes)

        triple = SemanticTriple(
            subject=subject_uid, predicate=predicate, object=object_uid, metadata=metadata
        )

        # Create relationship
        result = await self._create_semantic_relationship(triple)
        if not result.is_ok:
            return result

        self.logger.info(
            f"Added semantic relationship: {subject_uid} --[{predicate.value}]--> {object_uid}"
        )
        return Result.ok(True)

    @with_error_handling(
        "remove_semantic_relationship", error_type="database", uid_param="subject_uid"
    )
    async def remove_semantic_relationship(
        self, subject_uid: str, predicate: SemanticRelationshipType, object_uid: str
    ) -> Result[bool]:
        """
        Remove a semantic relationship between two knowledge units.

        Args:
            subject_uid: Subject knowledge unit UID,
            predicate: Semantic relationship type,
            object_uid: Object knowledge unit UID

        Returns:
            Result indicating success
        """
        # Build relationship name for Neo4j
        rel_name = predicate.to_neo4j_name()

        # Delete relationship query
        query = f"""
        MATCH (s:Entity {{uid: $subject_uid}})
              -[r:{rel_name}]->
              (o:Entity {{uid: $object_uid}})
        DETACH DELETE r
        RETURN count(r) as deleted
        """

        params = {"subject_uid": subject_uid, "object_uid": object_uid}

        results = await self.neo4j.execute_query(query, params)

        deleted_count = results[0].get("deleted", 0) if results else 0

        if deleted_count > 0:
            self.logger.info(
                f"Removed semantic relationship: {subject_uid} --[{predicate.value}]--> {object_uid}"
            )
            return Result.ok(True)
        else:
            return Result.fail(
                Errors.not_found(
                    f"Relationship not found: {subject_uid} --[{predicate.value}]--> {object_uid}"
                )
            )

    @with_error_handling("get_relationships_by_type", error_type="database", uid_param="uid")
    async def get_relationships_by_type(
        self, uid: str, predicate: SemanticRelationshipType, direction: str = "outgoing"
    ) -> Result[list[dict[str, Any]]]:
        """
        Get all relationships of a specific type for a knowledge unit.

        Args:
            uid: Knowledge unit UID,
            predicate: Semantic relationship type to query,
            direction: "outgoing", "incoming", or "both"

        Returns:
            Result containing list of relationships with metadata
        """
        # Verify unit exists
        source_result = await self.repo.get(uid)
        if not source_result.is_ok or not source_result.value:
            return Result.fail(Errors.not_found(f"Knowledge unit {uid} not found"))

        rel_name = predicate.to_neo4j_name()

        # Build query based on direction
        if direction == "outgoing":
            pattern = f"(source)-[r:{rel_name}]->(target)"
        elif direction == "incoming":
            pattern = f"(source)<-[r:{rel_name}]-(target)"
        else:  # both
            pattern = f"(source)-[r:{rel_name}]-(target)"

        query = f"""
        MATCH {pattern}
        WHERE source.uid = $uid
        RETURN target, r,
               startNode(r).uid as subject_uid,
               endNode(r).uid as object_uid
        """

        params = {"uid": uid}

        results = await self.neo4j.execute_query(query, params)

        # Check for query errors
        if results.is_error:
            return Result.fail(results.expect_error())

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
        Discover cross-domain semantic bridges from a knowledge unit.

        Finds units in other domains that share semantic patterns or
        principles with the source unit.

        Args:
            uid: Source knowledge unit UID,
            target_domain: Optional target domain to focus on,
            max_results: Maximum number of bridges to return

        Returns:
            Result containing list of discovered bridges
        """
        # Verify source unit exists
        source_result = await self.repo.get(uid)
        if not source_result.is_ok or not source_result.value:
            return Result.fail(Errors.not_found(f"Knowledge unit {uid} not found"))

        # Query for cross-domain bridges
        # Look for shared semantic relationships
        query = """
        MATCH (source:Entity {uid: $uid})
        MATCH (source)-[r1]->(shared)
        MATCH (target:Entity)-[r2]->(shared)
        WHERE source.domain <> target.domain
        AND ($target_domain IS NULL OR target.domain = $target_domain)
        AND type(r1) = type(r2)
        RETURN DISTINCT target,
               type(r1) as bridge_type,
               shared.uid as shared_concept,
               r1.confidence + r2.confidence as combined_confidence
        ORDER BY combined_confidence DESC
        LIMIT $limit
        """

        params = {"uid": uid, "target_domain": target_domain, "limit": max_results}

        results = await self.neo4j.execute_query(query, params)

        # Check for query errors
        if results.is_error:
            return Result.fail(results.expect_error())

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
            uid: Knowledge unit UID,
            max_inferences: Maximum inferences to return,
            min_confidence: Minimum confidence threshold

        Returns:
            Result containing list of inferred relationships with confidence scores
        """
        # Verify unit exists
        source_result = await self.repo.get(uid)
        if not source_result.is_ok or not source_result.value:
            return Result.fail(Errors.not_found(f"Knowledge unit {uid} not found"))

        # Transitive closure: if A->B and B->C, infer A->C
        # This is a simple pattern - could be enhanced with ML
        query = """
        MATCH (source:Entity {uid: $uid})-[r1]->(intermediate)
              -[r2]->(target:Entity)
        WHERE NOT (source)-[]->(target)
        AND type(r1) = type(r2)
        RETURN DISTINCT target,
               type(r1) as inferred_type,
               intermediate.uid as via_uid,
               (r1.confidence * r2.confidence) as confidence
        ORDER BY confidence DESC
        LIMIT $limit
        """

        params = {"uid": uid, "limit": max_inferences}

        results = await self.neo4j.execute_query(query, params)

        # Check for query errors
        if results.is_error:
            return Result.fail(results.expect_error())

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
