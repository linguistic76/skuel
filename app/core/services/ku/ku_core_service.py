"""
Knowledge Core Service - CRUD Operations
=========================================

Clean rewrite following CLAUDE.md patterns.
Handles basic create, read, update, DETACH DELETE operations for knowledge units.

**Responsibilities:**
- Create knowledge units with content and chunking
- Read knowledge units with content
- Update knowledge units and re-chunk content
- DETACH DELETE knowledge units and cleanup
- Status transitions (publish, archive)
- Content analysis integration

**Dependencies:**
- KuOperations (backend protocol)
- ContentOperations (content storage)
- Intelligence service (content analysis)
- Chunking service (optional RAG)

**Architecture (January 2026 Unified):**
- Inherits from BaseService for unified Activity/Curriculum patterns
- Uses CurriculumOperations[Ku] protocol hierarchy
- Returns Result[KuDTO] for backward compatibility with facade
"""

from datetime import UTC, datetime
from typing import Any

from core.events import publish_event
from core.models.enums import Domain, KnowledgeStatus
from core.models.ku.ku import Ku
from core.models.ku.ku_dto import KuDTO
from core.models.relationship_names import RelationshipName
from core.services.base_service import BaseService
from core.services.domain_config import create_curriculum_domain_config
from core.services.metadata_manager_mixin import MetadataManagerMixin
from core.services.protocols.content_protocols import ensure_content_protocol
from core.services.protocols.curriculum_protocols import CurriculumOperations
from core.utils.decorators import with_error_handling
from core.utils.metrics import track_query_metrics
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator


class KuCoreService(BaseService[CurriculumOperations[Ku], Ku], MetadataManagerMixin):
    """
    Core CRUD operations for knowledge units.

    **Architecture (January 2026 Unified):**
    Inherits from BaseService to provide:
    - Standard CRUD operations
    - Prerequisite/enables traversal
    - User progress tracking
    - Content operations with graph context

    **KU-Specific Extensions:**
    - Content chunking for RAG
    - Content analysis integration
    - Status transitions (publish, archive)
    - Semantic relationship management


    Source Tag: "ku_core_service_explicit"
    - Format: "ku_core_service_explicit" for user-created relationships
    - Format: "ku_core_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from ku_core metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging
    """

    # BaseService configuration (January 2026 - DomainConfig)
    _config = create_curriculum_domain_config(
        dto_class=KuDTO,
        model_class=Ku,
        domain_name="ku",
        search_fields=("title", "summary", "tags"),
        supports_user_progress=True,  # KU supports mastery tracking
        user_ownership_relationship=None,  # KU is shared content
        prerequisite_relationships=(RelationshipName.REQUIRES_KNOWLEDGE.value,),
        enables_relationships=(RelationshipName.ENABLES_KNOWLEDGE.value,),
    )

    @property
    def entity_label(self) -> str:
        """Entity label for Neo4j queries."""
        return "Ku"

    def _get_content_query(self) -> str:
        """
        Return Cypher query fragment for fetching KU metadata.

        Content lives on the :Content node (via HAS_CONTENT), not on the :Ku node.
        """
        return """
        RETURN n
        """

    def __init__(
        self, repo=None, content_repo=None, intelligence=None, chunking=None, event_bus=None
    ) -> None:
        """
        Initialize core service with required dependencies.

        Args:
            repo: CurriculumOperations[Ku] backend (typically UniversalNeo4jBackend[Ku])
            content_repo: ContentOperations backend for content storage
            intelligence: Intelligence service for content analysis
            chunking: Optional chunking service for RAG
            event_bus: Event bus for publishing domain events (optional)

        Note:
            Context invalidation now happens via event-driven architecture.
            Knowledge operations trigger domain events which invalidate context.
        """
        # Fail-fast validation (CLAUDE.md: no graceful degradation)
        if not repo:
            raise ValueError("KU repository is required")
        if not content_repo:
            raise ValueError("Content repository is required")
        if not intelligence:
            raise ValueError("Intelligence service is required")

        # Initialize base service with backend
        super().__init__(backend=repo)

        # Store KU-specific dependencies
        self.content_repo = content_repo
        self.intelligence = intelligence
        self.chunking_service = chunking
        self.event_bus = event_bus

    # ========================================================================
    # CREATE
    # ========================================================================

    @track_query_metrics("ku_create")
    @with_error_handling("create", error_type="database")
    async def create(
        self,
        title: str,
        body: str,
        summary: str = "",
        tags: list[str] | None = None,
        **metadata: Any,
    ) -> Result[KuDTO]:
        """
        Create a new knowledge unit with content.

        Flow:
        1. Validate inputs
        2. Generate UID
        3. Store unit metadata
        4. Process and store content (with chunking if available)
        5. Analyze content quality
        6. Return KuDTO

        Args:
            title: Knowledge unit title,
            body: Full markdown content,
            summary: Optional summary (defaults to title[:100]),
            tags: Optional list of tags
            **metadata: Additional fields (domain, complexity, etc.)

        Returns:
            Result containing created KuDTO
        """
        # Validation
        if not title or not body:
            return Result.fail(Errors.validation("Title and body are required", field="title,body"))

        # Generate flat UID (Universal Hierarchical Pattern)
        # Parent relationship handled separately via ORGANIZES edge
        uid = UIDGenerator.generate_knowledge_uid(title=title)

        # Compute word_count from body (stored as metadata on Ku node)
        word_count = len(body.strip().split())

        # Prepare unit data with timestamps (via MetadataManagerMixin)
        # Content body is NOT stored on the Ku node — it goes to the :Content node
        unit_data = {
            "uid": uid,
            "title": title.strip(),
            "word_count": word_count,
            "summary": summary or title[:100],
            "tags": tags or [],
            "status": KnowledgeStatus.DRAFT.value,
            **self.timestamp_properties(use_utc=True),
            **metadata,
        }

        # Store unit in graph
        await self.backend.create(unit_data)

        # Handle parent organization if specified (Universal Hierarchical Pattern)
        parent_uid = metadata.get("parent_uid")
        if parent_uid:
            organize_result = await self.organize_ku(
                parent_uid=parent_uid,
                child_uid=uid,
                order=metadata.get("order", 0),
                importance=metadata.get("importance", "normal"),
            )
            if organize_result.is_error:
                self.logger.warning(
                    f"Failed to create ORGANIZES relationship from {parent_uid} to {uid}: "
                    f"{organize_result.error}"
                )

        # Process and store content
        await self._store_content(uid, body, title, tags, metadata)

        # Build DTO
        dto = KuDTO(
            uid=uid,
            title=title.strip(),
            domain=Domain[metadata.get("domain", "KNOWLEDGE")],
            word_count=word_count,
            tags=tags or [],
            metadata=metadata,
        )

        # Analyze content quality (async, non-blocking)
        await self._analyze_content_async(dto)

        # Publish KnowledgeCreated event
        from core.events import KnowledgeCreated

        event = KnowledgeCreated(
            ku_uid=uid,
            title=title.strip(),
            domain=metadata.get("domain"),
            occurred_at=datetime.now(UTC),
            created_by_user=metadata.get("created_by_user"),
            created_from_template=metadata.get("created_from_template", False),
        )
        await publish_event(self.event_bus, event, self.logger)

        self.logger.info(f"Created knowledge unit: {uid}")
        return Result.ok(dto)

    async def _store_content(
        self, uid: str, body: str, title: str, tags: list, metadata: dict
    ) -> None:
        """
        Store content with optional chunking.

        Pattern: Try chunking first, fallback to simple storage.
        """
        if self.chunking_service:
            # Process with chunking — pass body directly, not via Ku model
            chunking_result = await self.chunking_service.process_ku_content(
                knowledge=None, content_body=body.strip(), format="markdown", parent_uid=uid
            )

            if chunking_result.is_ok:
                content_obj, _ = chunking_result.value

                # Try to store with chunks (new method, might not exist)
                store_method = getattr(self.content_repo, "store_content_with_chunks", None)

                if store_method and callable(store_method):
                    await self.content_repo.store_content_with_chunks(uid=uid, content=content_obj)
                    self.logger.info(
                        f"Stored content with {content_obj.chunk_count} chunks for {uid}"
                    )

                    # Publish chunk embedding request event (async background processing)
                    chunks = getattr(content_obj, "chunks", None)
                    if chunks and len(chunks) > 0:
                        from core.events import ChunkEmbeddingRequested

                        chunk_uids = tuple(chunk.chunk_id for chunk in chunks)
                        chunk_texts = tuple(chunk.context_window for chunk in chunks)

                        now = datetime.now(UTC)
                        embedding_event = ChunkEmbeddingRequested(
                            ku_uid=uid,
                            chunk_uids=chunk_uids,
                            chunk_texts=chunk_texts,
                            requested_at=now,
                            occurred_at=now,
                            user_uid=metadata.get("created_by_user"),
                        )
                        await publish_event(self.event_bus, embedding_event, self.logger)
                        self.logger.debug(f"Requested embeddings for {len(chunks)} chunks of {uid}")

                    return

        # Fallback: simple content storage
        await self.content_repo.create_content(unit_uid=uid, body=body.strip())

    async def _analyze_content_async(self, dto: KuDTO) -> None:
        """
        Analyze content quality asynchronously.

        Non-blocking - logs results but doesn't fail creation.
        """
        try:
            content_adapter = ensure_content_protocol(dto)
            analysis_result = await self.intelligence.analyze_content(content_adapter)

            if analysis_result.is_ok:
                quality = analysis_result.value.quality_score
                self.logger.debug(f"Content analysis complete for {dto.uid}: quality={quality:.2f}")
        except Exception as e:
            self.logger.warning(f"Content analysis failed for {dto.uid}: {e}")

    # ========================================================================
    # READ
    # ========================================================================

    @track_query_metrics("ku_get")
    @with_error_handling("get", error_type="database", uid_param="uid")
    async def get(self, uid: str) -> Result[Ku]:
        """
        Get a knowledge unit with its content.

        Args:
            uid: Knowledge unit UID

        Returns:
            Result containing Ku domain model with content
        """
        # Get unit data from backend
        unit_result = await self.backend.get(uid)
        if unit_result.is_error or not unit_result.value:
            return Result.fail(Errors.not_found(f"Knowledge unit {uid} not found"))

        # Backend returns Ku via from_neo4j_node() (entity_class=Ku)
        return Result.ok(unit_result.value)

    @track_query_metrics("ku_get_with_context")
    @with_error_handling("get_with_context", error_type="database", uid_param="uid")
    async def get_with_context(self, uid: str, min_confidence: float = 0.7) -> Result[KuDTO]:
        """
        Get knowledge unit WITH graph neighborhood context in single query.

        **Neo4j Optimization:** Fetches entity + relationships in ONE database round-trip
        instead of 3-4 separate queries. This is the RECOMMENDED method when UI needs
        rich context (prerequisites, dependents, related knowledge, mastery stats).

        Graph Context Included:
        - prerequisites: Knowledge units required before this one (with confidence scores)
        - dependents: Knowledge units that depend on this one (who needs it)
        - related: Related knowledge units (lateral connections)
        - mastery_count: Number of users who mastered this KU
        - similar: Similar knowledge via shared neighbors (Jaccard similarity)

        Args:
            uid: Knowledge unit UID
            min_confidence: Minimum relationship confidence (default: 0.7)

        Returns:
            Result containing KuDTO with graph context in metadata field:
            {
                "graph_context": {
                    "prerequisites": [{uid, title, confidence}, ...],
                    "dependents": [{uid, title, confidence}, ...],
                    "related": [{uid, title, confidence}, ...],
                    "mastery_count": int,
                    "similar": [{uid, title, similarity}, ...]
                }
            }

        Example:
            result = await ku_service.get_with_context("ku.python_basics")
            if result.is_ok:
                dto = result.value
                context = dto.metadata["graph_context"]
                print(f"Prerequisites: {len(context['prerequisites'])}")
                print(f"Mastered by: {context['mastery_count']} users")
        """
        # Build graph-native query - fetches everything in ONE round-trip
        query = """
        MATCH (ku:Ku {uid: $uid})

        // Fetch prerequisites (1-hop incoming REQUIRES_KNOWLEDGE)
        OPTIONAL MATCH (ku)-[r1:REQUIRES_KNOWLEDGE]->(prereq:Ku)
        WHERE coalesce(r1.confidence, 1.0) >= $min_confidence
        WITH ku, collect(DISTINCT {
            uid: prereq.uid,
            title: prereq.title,
            confidence: coalesce(r1.confidence, 1.0)
        }) as prerequisites

        // Fetch dependents (who needs this KU - outgoing REQUIRES_KNOWLEDGE)
        OPTIONAL MATCH (dependent:Ku)-[r2:REQUIRES_KNOWLEDGE]->(ku)
        WHERE coalesce(r2.confidence, 1.0) >= $min_confidence
        WITH ku, prerequisites, collect(DISTINCT {
            uid: dependent.uid,
            title: dependent.title,
            confidence: coalesce(r2.confidence, 1.0)
        }) as dependents

        // Fetch related knowledge (lateral connections)
        OPTIONAL MATCH (ku)-[r3:RELATED_TO|EXTENDS_PATTERN|DEEPENS_UNDERSTANDING]-(related:Ku)
        WHERE coalesce(r3.confidence, 1.0) >= $min_confidence * 0.85
        WITH ku, prerequisites, dependents, collect(DISTINCT {
            uid: related.uid,
            title: related.title,
            confidence: coalesce(r3.confidence, 1.0),
            relationship_type: type(r3)
        }) as related

        // Fetch mastery statistics (how many users mastered this)
        OPTIONAL MATCH (ku)<-[:MASTERED]-(user:User)
        WITH ku, prerequisites, dependents, related, count(DISTINCT user) as mastery_count

        // Fetch similar knowledge (shared neighbors - Jaccard similarity)
        OPTIONAL MATCH (ku)-[]-(shared)-[]-(similar:Ku)
        WHERE similar <> ku
        WITH ku, prerequisites, dependents, related, mastery_count,
             similar, count(DISTINCT shared) as shared_count

        // Collect all similar nodes, then filter by shared_count
        WITH ku, prerequisites, dependents, related, mastery_count,
             collect(DISTINCT {
                 uid: similar.uid,
                 title: similar.title,
                 shared_neighbors: shared_count
             }) as all_similar

        // Filter to nodes with 2+ shared connections and take top 5
        WITH ku, prerequisites, dependents, related, mastery_count,
             [s IN all_similar WHERE s.shared_neighbors >= 2][0..5] as similar_knowledge

        RETURN ku, prerequisites, dependents, related, mastery_count, similar_knowledge
        """

        params = {"uid": uid, "min_confidence": min_confidence}

        # Execute single query via protocol-compliant backend
        result = await self.backend.execute_query(query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        if not result.value:
            return Result.fail(Errors.not_found(resource="Ku", identifier=uid))

        record = result.value[0]
        ku_node = record["ku"]

        # Build KuDTO from node
        dto = KuDTO.from_dict(ku_node)

        # Enrich metadata with graph context
        dto.metadata["graph_context"] = {
            "prerequisites": [p for p in record["prerequisites"] if p.get("uid")],
            "dependents": [d for d in record["dependents"] if d.get("uid")],
            "related": [r for r in record["related"] if r.get("uid")],
            "mastery_count": record["mastery_count"],
            "similar": [s for s in record["similar_knowledge"] if s.get("uid")],
            "query_timestamp": datetime.now(UTC).isoformat(),
            "min_confidence_used": min_confidence,
        }

        self.logger.info(
            f"Fetched KU with context: {uid} "
            f"(prereqs={len(dto.metadata['graph_context']['prerequisites'])}, "
            f"deps={len(dto.metadata['graph_context']['dependents'])}, "
            f"related={len(dto.metadata['graph_context']['related'])})"
        )

        return Result.ok(dto)

    @track_query_metrics("ku_get_with_content")
    @with_error_handling("get_with_content", error_type="database", uid_param="uid")
    async def get_with_content(self, uid: str) -> Result[tuple[Ku, str]]:
        """
        Get a knowledge unit with its full content body.

        Content lives on the :Content node (via HAS_CONTENT), not on the :Ku node.
        Use this method for detail views that need to render markdown.

        Args:
            uid: Knowledge unit UID

        Returns:
            Result containing (Ku, content_body) tuple
        """
        ku_result = await self.get(uid)
        if ku_result.is_error:
            return ku_result

        ku = ku_result.value
        content_body = ""

        if self.content_repo:
            content_result = await self.content_repo.get_content(uid)
            if content_result.is_ok and content_result.value:
                content_body = content_result.value.get("content", "")

        return Result.ok((ku, content_body))

    # ========================================================================
    # UPDATE
    # ========================================================================

    @track_query_metrics("ku_update")
    @with_error_handling("update", error_type="database", uid_param="uid")
    async def update(self, uid: str, **updates: Any) -> Result[KuDTO]:
        """
        Update a knowledge unit.

        Handles:
        - Unit metadata updates
        - Content updates (with re-chunking)
        - Timestamp management
        - Content re-analysis

        Args:
            uid: Knowledge unit UID
            **updates: Fields to update (title, body, tags, etc.)

        Returns:
            Result containing updated KuDTO
        """
        # Verify existence
        existing_result = await self.get(uid)
        if existing_result.is_error:
            return existing_result

        # Handle content update separately
        if "body" in updates or "content" in updates:
            new_body = updates.pop("body", None) or updates.pop("content", None)
            await self._update_content(uid, new_body, existing_result.value)

        # Update unit metadata (via MetadataManagerMixin)
        if updates:
            updates.update(self.update_properties(use_utc=True))
            await self.backend.update(uid, updates)

        # Return updated DTO
        return await self.get(uid)

    async def _update_content(self, uid: str, new_body: str, existing_dto: Ku) -> None:
        """
        Update content with optional re-chunking.

        Pattern: Re-chunk if chunking service available, fallback to simple update.
        Also recomputes word_count on the Ku node.

        Note: existing_dto is actually a Ku instance (backend uses entity_class=Ku).
        """
        # Recompute word_count on the Ku node
        new_word_count = len(new_body.strip().split())
        await self.backend.update(uid, {"word_count": new_word_count})

        if self.chunking_service:
            # Re-process with chunking — pass body directly
            chunking_result = await self.chunking_service.update_ku_content(
                knowledge=None, new_content_body=new_body, parent_uid=uid
            )

            if chunking_result.is_ok:
                content_obj, _ = chunking_result.value
                self.logger.info(f"Re-chunked content: {content_obj.chunk_count} chunks for {uid}")
                # Content repo update handled by chunking service
                return

        # Fallback: simple content update
        await self.content_repo.update_content(uid, new_body)

    # ========================================================================
    # DELETE
    # ========================================================================

    @track_query_metrics("ku_delete")
    @with_error_handling("delete", error_type="database", uid_param="uid")
    async def delete(self, uid: str) -> Result[bool]:
        """
        DETACH DELETE a knowledge unit and all related data.

        Cascade deletes:
        1. Content chunks (if chunking enabled)
        2. Content data
        3. Unit metadata

        Args:
            uid: Knowledge unit UID

        Returns:
            Result containing deletion success (True/False)
        """
        # Delete content first (gracefully handle missing content)
        try:
            await self.content_repo.delete_content(uid)
        except Exception as e:
            self.logger.debug(f"Content delete failed (might not exist): {e}")

        # Delete unit from backend
        deleted = await self.backend.delete(uid)

        # Clear chunking cache
        if self.chunking_service:
            try:
                self.chunking_service.clear_cache(uid)
            except Exception as e:
                self.logger.debug(f"Cache clear failed: {e}")

        self.logger.info(f"Deleted knowledge unit: {uid} (success={deleted})")
        return Result.ok(deleted)

    # ========================================================================
    # STATUS TRANSITIONS
    # ========================================================================

    async def publish(self, uid: str) -> Result[KuDTO]:
        """
        Publish a knowledge unit (DRAFT → PUBLISHED).

        Args:
            uid: Knowledge unit UID

        Returns:
            Result containing updated KuDTO with PUBLISHED status
        """
        return await self.update(uid, status=KnowledgeStatus.PUBLISHED.value)

    async def archive(self, uid: str) -> Result[KuDTO]:
        """
        Archive a knowledge unit (any status → ARCHIVED).

        Args:
            uid: Knowledge unit UID

        Returns:
            Result containing updated KuDTO with ARCHIVED status
        """
        return await self.update(uid, status=KnowledgeStatus.ARCHIVED.value)

    # ========================================================================
    # CONTENT OPERATIONS
    # ========================================================================

    @track_query_metrics("ku_get_chunks")
    @with_error_handling("get_chunks", error_type="database", uid_param="uid")
    async def get_chunks(self, uid: str, chunk_type=None) -> Result[list]:
        """
        Get content chunks for a knowledge unit.

        Requires chunking service.

        Args:
            uid: Knowledge unit UID
            chunk_type: Optional filter by chunk type

        Returns:
            Result containing list of content chunks
        """
        if not self.chunking_service:
            return Result.fail(
                Errors.system(message="Chunking service not available", operation="get_chunks")
            )

        chunks = await self.chunking_service.get_chunks(uid, chunk_type)
        return Result.ok(chunks)

    @track_query_metrics("ku_analyze_content")
    @with_error_handling("analyze_content", error_type="system", uid_param="uid")
    async def analyze_content(self, uid: str) -> Result[dict]:
        """
        Analyze knowledge unit content quality.

        Returns structured analysis including:
        - Quality score
        - Readability metrics
        - Complexity assessment
        - Topic extraction

        Args:
            uid: Knowledge unit UID

        Returns:
            Result containing content analysis dict
        """
        # Get the knowledge unit
        result = await self.get(uid)
        if result.is_error:
            return Result.fail(result.expect_error())

        dto = result.value

        # Analyze content
        content_adapter = ensure_content_protocol(dto)
        analysis_result = await self.intelligence.analyze_content(content_adapter)

        if analysis_result.is_ok:
            # Convert to dict for API response
            return Result.ok(analysis_result.value.__dict__)
        else:
            return analysis_result

    @track_query_metrics
    @with_error_handling("get_user_mastery", error_type="database", uid_param="ku_uid")
    async def get_user_mastery(self, user_uid: str, ku_uid: str) -> Result[float]:
        """
        Get user's mastery level for a specific knowledge unit.

        Queries the graph for (User)-[:MASTERED {level: float}]->(KnowledgeUnit)
        relationship to retrieve the mastery level.

        Args:
            user_uid: User's unique identifier
            ku_uid: Knowledge unit UID

        Returns:
            Result[float]: Mastery level (0.0-1.0) or 0.0 if not found

        Example:
            result = await ku_service.get_user_mastery("user_mike", "ku.python.basics")
            if result.is_ok:
                mastery = result.value  # 0.85
        """
        # Query graph for mastery relationship
        query = """
        MATCH (user:User {uid: $user_uid})-[r:MASTERED]->(ku:Ku {uid: $ku_uid})
        RETURN r.level as mastery
        """
        params = {"user_uid": user_uid, "ku_uid": ku_uid}

        result = await self.backend.execute_query(query, params)

        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value
        if records and len(records) > 0:
            mastery = records[0].get("mastery", 0.0)
            self.logger.info(f"Retrieved mastery for {user_uid} on {ku_uid}: {mastery}")
            return Result.ok(mastery)
        else:
            # No mastery relationship found - return 0.0
            self.logger.debug(f"No mastery found for {user_uid} on {ku_uid}, returning 0.0")
            return Result.ok(0.0)

    # ========================================================================
    # HIERARCHICAL METHODS (Universal Hierarchical Pattern - 2026-01-30)
    # ========================================================================

    @track_query_metrics("ku_get_subkus")
    @with_error_handling("get_subkus", error_type="database", uid_param="parent_uid")
    async def get_subkus(
        self, parent_uid: str, depth: int = 1, include_metadata: bool = False
    ) -> Result[list[Ku]]:
        """
        Get all KUs organized under this parent KU (MOC pattern).

        Universal Hierarchical Pattern: Uses ORGANIZES relationships to
        retrieve child KUs, supporting multi-level hierarchy traversal.

        Args:
            parent_uid: Parent KU UID
            depth: How many levels deep (1 = direct children only, 2 = children + grandchildren)
            include_metadata: Include relationship metadata (order, importance)

        Returns:
            Result containing list of child KUs

        Example:
            # Get all KUs organized under "Yoga Fundamentals" MOC
            result = await ku_service.get_subkus("ku_yoga-fundamentals_abc123")
            if result.is_ok:
                for child_ku in result.value:
                    print(f"  - {child_ku.title}")

        See: /docs/patterns/UNIVERSAL_HIERARCHICAL_PATTERN.md
        """
        query = f"""
        MATCH (parent:Ku {{uid: $parent_uid}})-[r:ORGANIZES*1..{depth}]->(child:Ku)
        RETURN child, r
        ORDER BY r[0].order ASC
        """

        result = await self.backend.execute_query(query, {"parent_uid": parent_uid})
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert to Ku domain objects using from_neo4j_node (picks up ALL fields)
        from core.utils.neo4j_mapper import from_neo4j_node

        kus = [from_neo4j_node(record["child"], Ku) for record in result.value]

        self.logger.info(f"Found {len(kus)} subKUs for parent {parent_uid} (depth={depth})")
        return Result.ok(kus)

    @track_query_metrics("ku_get_parent_kus")
    @with_error_handling("get_parent_kus", error_type="database", uid_param="ku_uid")
    async def get_parent_kus(self, ku_uid: str) -> Result[list[Ku]]:
        """
        Get all parent KUs (can have multiple via MOC pattern).

        Universal Hierarchical Pattern: A single KU can be organized under
        multiple parent KUs (MOCs), supporting DAG structure.

        Args:
            ku_uid: Child KU UID

        Returns:
            Result containing list of parent KUs

        Example:
            # "Machine Learning" might be in multiple MOCs
            result = await ku_service.get_parent_kus("ku_machine-learning_xyz789")
            # Could return: ["AI Fundamentals", "Data Science", "Python Advanced"]

        See: /docs/patterns/UNIVERSAL_HIERARCHICAL_PATTERN.md
        """
        query = """
        MATCH (parent:Ku)-[:ORGANIZES]->(child:Ku {uid: $ku_uid})
        RETURN parent
        ORDER BY parent.title
        """

        result = await self.backend.execute_query(query, {"ku_uid": ku_uid})
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert to Ku domain objects using from_neo4j_node (picks up ALL fields)
        from core.utils.neo4j_mapper import from_neo4j_node

        parents = [from_neo4j_node(record["parent"], Ku) for record in result.value]

        self.logger.info(f"Found {len(parents)} parent KUs for {ku_uid}")
        return Result.ok(parents)

    @track_query_metrics("ku_get_hierarchy")
    @with_error_handling("get_ku_hierarchy", error_type="database", uid_param="ku_uid")
    async def get_ku_hierarchy(self, ku_uid: str) -> Result[dict]:
        """
        Get full hierarchy context for a KU.

        Universal Hierarchical Pattern: Returns complete hierarchical context
        including ancestors, siblings, children, and depth level.

        Returns:
            dict with:
            - ancestors: List of ancestor KUs (grandparent, parent, etc.)
            - siblings: Other KUs with same parents
            - children: Direct child KUs
            - depth: How deep in hierarchy (0 = root, no parents)

        Example:
            hierarchy = {
                "ancestors": [
                    {"uid": "ku_yoga_abc", "title": "Yoga Fundamentals", "level": 1},
                    {"uid": "ku_meditation_def", "title": "Meditation", "level": 2}
                ],
                "siblings": [...]  # Other KUs under same parents
                "children": [...]  # KUs this KU organizes
                "depth": 3  # Three levels from root
            }

        See: /docs/patterns/UNIVERSAL_HIERARCHICAL_PATTERN.md
        """
        # Get ancestors
        ancestors_query = """
        MATCH path = (ancestor:Ku)-[:ORGANIZES*]->(ku:Ku {uid: $ku_uid})
        RETURN ancestor, length(path) as depth
        ORDER BY depth DESC
        """

        # Get children
        children_query = """
        MATCH (ku:Ku {uid: $ku_uid})-[:ORGANIZES]->(child:Ku)
        RETURN child
        ORDER BY child.title
        """

        # Get siblings (KUs with same parents)
        siblings_query = """
        MATCH (parent:Ku)-[:ORGANIZES]->(sibling:Ku)
        WHERE (parent)-[:ORGANIZES]->(:Ku {uid: $ku_uid})
        AND sibling.uid <> $ku_uid
        RETURN DISTINCT sibling
        ORDER BY sibling.title
        """

        # Execute queries
        ancestors_result = await self.backend.execute_query(ancestors_query, {"ku_uid": ku_uid})
        children_result = await self.backend.execute_query(children_query, {"ku_uid": ku_uid})
        siblings_result = await self.backend.execute_query(siblings_query, {"ku_uid": ku_uid})

        if ancestors_result.is_error:
            return Result.fail(ancestors_result.expect_error())
        if children_result.is_error:
            return Result.fail(children_result.expect_error())
        if siblings_result.is_error:
            return Result.fail(siblings_result.expect_error())

        hierarchy = {
            "ancestors": [
                {"uid": r["ancestor"]["uid"], "title": r["ancestor"]["title"], "level": r["depth"]}
                for r in ancestors_result.value
            ],
            "children": [
                {"uid": r["child"]["uid"], "title": r["child"]["title"]}
                for r in children_result.value
            ],
            "siblings": [
                {"uid": r["sibling"]["uid"], "title": r["sibling"]["title"]}
                for r in siblings_result.value
            ],
            "depth": len(ancestors_result.value),
        }

        self.logger.info(
            f"Hierarchy for {ku_uid}: depth={hierarchy['depth']}, "
            f"ancestors={len(hierarchy['ancestors'])}, "
            f"children={len(hierarchy['children'])}, "
            f"siblings={len(hierarchy['siblings'])}"
        )

        return Result.ok(hierarchy)

    @track_query_metrics("ku_organize")
    @with_error_handling("organize_ku", error_type="database")
    async def organize_ku(
        self, parent_uid: str, child_uid: str, order: int = 0, importance: str = "normal"
    ) -> Result[bool]:
        """
        Create ORGANIZES relationship between KUs (MOC pattern).

        Universal Hierarchical Pattern: Creates parent-child relationship via
        ORGANIZES edge. Supports multiple parents (DAG) and relationship metadata.

        Args:
            parent_uid: Parent KU UID (the MOC)
            child_uid: Child KU UID
            order: Display order (0 = first, higher = later)
            importance: "core", "normal", "supplemental"

        Returns:
            Result[bool] - True if created

        Example:
            # Add "Meditation" to "Yoga Fundamentals" MOC
            await ku_service.organize_ku(
                parent_uid="ku_yoga-fundamentals_abc123",
                child_uid="ku_meditation_xyz789",
                order=1,
                importance="core"
            )

        See: /docs/patterns/UNIVERSAL_HIERARCHICAL_PATTERN.md
        """
        # Validate importance
        if importance not in ("core", "normal", "supplemental"):
            return Result.fail(
                Errors.validation(
                    f"Invalid importance: {importance}. Must be 'core', 'normal', or 'supplemental'",
                    field="importance",
                )
            )

        # Check for cycle prevention
        cycle_query = """
        MATCH path = (child:Ku {uid: $child_uid})-[:ORGANIZES*]->(parent:Ku {uid: $parent_uid})
        RETURN length(path) as cycle_length
        LIMIT 1
        """
        cycle_result = await self.backend.execute_query(
            cycle_query, {"parent_uid": parent_uid, "child_uid": child_uid}
        )
        if cycle_result.is_error:
            return Result.fail(cycle_result.expect_error())

        if cycle_result.value:
            return Result.fail(
                Errors.validation(
                    f"Cannot organize: would create cycle ({child_uid} already organizes {parent_uid})",
                    field="parent_uid,child_uid",
                )
            )

        # Create ORGANIZES relationship
        query = """
        MATCH (parent:Ku {uid: $parent_uid})
        MATCH (child:Ku {uid: $child_uid})
        MERGE (parent)-[r:ORGANIZES]->(child)
        SET r.order = $order,
            r.importance = $importance,
            r.created_at = COALESCE(r.created_at, datetime()),
            r.updated_at = datetime()
        RETURN r
        """

        result = await self.backend.execute_query(
            query,
            {
                "parent_uid": parent_uid,
                "child_uid": child_uid,
                "order": order,
                "importance": importance,
            },
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        success = len(result.value) > 0
        if success:
            self.logger.info(
                f"Created ORGANIZES: {parent_uid} -> {child_uid} "
                f"(order={order}, importance={importance})"
            )
        else:
            self.logger.warning(f"Failed to create ORGANIZES: {parent_uid} -> {child_uid}")

        return Result.ok(success)

    @track_query_metrics("ku_unorganize")
    @with_error_handling("unorganize_ku", error_type="database")
    async def unorganize_ku(self, parent_uid: str, child_uid: str) -> Result[bool]:
        """
        Remove ORGANIZES relationship between KUs.

        Universal Hierarchical Pattern: Removes parent-child relationship while
        preserving both KU nodes. Useful for reorganization.

        Args:
            parent_uid: Parent KU UID
            child_uid: Child KU UID

        Returns:
            Result[bool] - True if removed

        Example:
            # Remove "Meditation" from "Yoga Fundamentals" MOC
            await ku_service.unorganize_ku(
                parent_uid="ku_yoga-fundamentals_abc123",
                child_uid="ku_meditation_xyz789"
            )

        See: /docs/patterns/UNIVERSAL_HIERARCHICAL_PATTERN.md
        """
        query = """
        MATCH (parent:Ku {uid: $parent_uid})-[r:ORGANIZES]->(child:Ku {uid: $child_uid})
        DELETE r
        RETURN count(r) as deleted
        """

        result = await self.backend.execute_query(
            query, {"parent_uid": parent_uid, "child_uid": child_uid}
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        deleted = result.value[0]["deleted"] if result.value else 0
        success = deleted > 0

        if success:
            self.logger.info(f"Removed ORGANIZES: {parent_uid} -> {child_uid}")
        else:
            self.logger.warning(
                f"No ORGANIZES relationship found to remove: {parent_uid} -> {child_uid}"
            )

        return Result.ok(success)
