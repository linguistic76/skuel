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
from core.models.ku.ku import Ku
from core.models.ku.ku_dto import KuDTO
from core.models.relationship_names import RelationshipName
from core.models.shared_enums import Domain, KnowledgeStatus
from core.services.base_service import BaseService
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

    # BaseService configuration (January 2026 - Unified)
    _dto_class = KuDTO
    _model_class = Ku
    _search_fields = ["title", "content", "tags"]
    _content_field = "content"
    _prerequisite_relationships = [RelationshipName.REQUIRES_KNOWLEDGE.value]
    _enables_relationships = [RelationshipName.ENABLES_KNOWLEDGE.value]
    _supports_user_progress = True  # KU supports mastery tracking
    _user_ownership_relationship = None  # KU is shared content

    @property
    def entity_label(self) -> str:
        """Entity label for Neo4j queries."""
        return "Ku"

    def _get_content_query(self) -> str:
        """
        Return Cypher query fragment for fetching KU content.

        KUs store content inline, so we just return the content field.
        """
        return """
        RETURN n, n.content as content
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

        # Generate UID
        uid = UIDGenerator.generate_knowledge_uid(
            title=title,
            parent_uid=metadata.get("parent_uid"),
            domain_uid=metadata.get("domain_uid"),
        )

        # Prepare unit data with timestamps (via MetadataManagerMixin)
        unit_data = {
            "uid": uid,
            "title": title.strip(),
            "content": body.strip(),  # Required for KuDTO
            "summary": summary or title[:100],
            "tags": tags or [],
            "status": KnowledgeStatus.DRAFT.value,
            **self.timestamp_properties(use_utc=True),
            **metadata,
        }

        # Store unit in graph
        await self.backend.create(unit_data)

        # Process and store content
        await self._store_content(uid, body, title, tags, metadata)

        # Build DTO
        dto = KuDTO(
            uid=uid,
            title=title.strip(),
            content=body.strip(),
            domain=Domain[metadata.get("domain", "KNOWLEDGE")],
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
            # Create domain model for chunking
            from core.models.shared_enums import SELCategory

            knowledge = Ku(
                uid=uid,
                title=title.strip(),
                content=body.strip(),
                domain=metadata.get("domain", Domain.KNOWLEDGE),
                sel_category=metadata.get("sel_category", SELCategory.SELF_MANAGEMENT),
                tags=tuple(tags or []),
                complexity=metadata.get("complexity", "medium"),
            )

            # Process with chunking
            chunking_result = await self.chunking_service.process_ku_content(
                knowledge=knowledge, content_body=body.strip(), format="markdown"
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
    async def get(self, uid: str) -> Result[KuDTO]:
        """
        Get a knowledge unit with its content.

        Args:
            uid: Knowledge unit UID

        Returns:
            Result containing KuDTO with content
        """
        # Get unit data from backend
        unit_result = await self.backend.get(uid)
        if unit_result.is_error or not unit_result.value:
            return Result.fail(Errors.not_found(f"Knowledge unit {uid} not found"))

        # Backend already returns KuDTO via from_neo4j_node()
        dto = unit_result.value

        # If content field is empty and we have a content repo, try fetching it
        # (This is for backward compatibility with old three-tier architecture)
        if self.content_repo and (not dto.content or dto.content == ""):
            content_result = await self.content_repo.get_content(uid)
            if content_result.is_ok and content_result.value:
                # Update the content field (bypass frozen via object.__setattr__)
                new_content = content_result.value.get("content", dto.content)
                object.__setattr__(dto, "content", new_content)

        return Result.ok(dto)

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

        # Execute single query (returns EagerResult with .records attribute)
        result = await self.backend.driver.execute_query(query, params)
        records = result.records  # EagerResult.records is list[Record]

        if not records or len(records) == 0:
            return Result.fail(Errors.not_found(resource="Ku", identifier=uid))

        record = records[0]
        ku_node = record["ku"]

        # Build KuDTO from node
        dto = KuDTO.from_dict(dict(ku_node))

        # Fetch content if needed
        if not dto.content or dto.content == "":
            content_result = await self.content_repo.get_content(uid)
            if content_result.is_ok and content_result.value:
                dto.content = content_result.value.get("content", dto.content)

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

    async def _update_content(self, uid: str, new_body: str, existing_dto: KuDTO) -> None:
        """
        Update content with optional re-chunking.

        Pattern: Re-chunk if chunking service available, fallback to simple update.
        """
        if self.chunking_service:
            # Re-create domain model for re-chunking
            from core.models.shared_enums import SELCategory

            knowledge = Ku(
                uid=uid,
                title=existing_dto.title,
                content=new_body,
                domain=existing_dto.domain,
                sel_category=existing_dto.metadata.get("sel_category", SELCategory.SELF_MANAGEMENT),
                tags=existing_dto.tags,
                complexity=existing_dto.metadata.get("complexity", "medium"),
            )

            # Re-process with chunking
            chunking_result = await self.chunking_service.update_ku_content(
                knowledge=knowledge, new_content_body=new_body
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
            return result

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
