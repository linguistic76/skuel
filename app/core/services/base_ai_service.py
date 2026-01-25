"""
Base AI Service
===============

Base class for domain AI services (LLM/embeddings-powered features).

Created: January 2026
Purpose: Separate AI-powered features from graph-based analytics (ADR-030)

AI services contain features that REQUIRE:
- embeddings_service (semantic search, similarity matching)
- llm_service (AI-generated insights, recommendations, natural language)

AI services are OPTIONAL - the app functions fully without them.
They enhance the user experience but are not required for core functionality.

Usage:
    class TasksAIService(BaseAIService[TasksOperations, Task]):
        _service_name = "tasks.ai"

        async def get_semantic_similar_tasks(self, task_uid: str) -> Result[list[Task]]:
            # Uses embeddings for semantic similarity
            ...

        async def generate_task_insights(self, task_uid: str) -> Result[str]:
            # Uses LLM for natural language insights
            ...
"""

from typing import Any, ClassVar, Generic, TypeVar

from core.events import publish_event
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_second_item

# Generic type vars
B = TypeVar("B")  # Backend operations protocol
T = TypeVar("T")  # Domain model type


class BaseAIService(Generic[B, T]):
    """
    Base class for domain AI services.

    Provides AI-powered features using LLM and embeddings.
    These services are OPTIONAL - the app works without them.

    Class Attributes:
        _service_name: Override for hierarchical logger name (e.g., "tasks.ai")
        _require_llm: If True, fail if llm_service not provided (default: True)
        _require_embeddings: If True, fail if embeddings_service not provided (default: True)

    Instance Attributes:
        backend: Domain operations protocol (REQUIRED)
        llm: LLMService for AI insights (optional but often required)
        embeddings: EmbeddingsService for semantic search (optional but often required)
        graph_intel: GraphIntelligenceService for context (optional)
        relationships: UnifiedRelationshipService for relationships (optional)
        logger: Logger instance

    Philosophy:
        AI services provide enhanced features but are not required for the app to function.
        Core + Analytics works without AI. AI services add:
        - Semantic search (find similar items by meaning, not keywords)
        - Natural language insights (AI-generated explanations)
        - Intelligent recommendations (context-aware suggestions)
    """

    # Service name for hierarchical logging
    _service_name: ClassVar[str | None] = None

    # Set to True if LLM service is required for this AI service
    _require_llm: ClassVar[bool] = True

    # Set to True if embeddings service is required for this AI service
    _require_embeddings: ClassVar[bool] = True

    # Event handlers to auto-register
    _event_handlers: ClassVar[dict[type, str]] = {}

    def __init__(
        self,
        backend: B,
        llm_service: Any | None = None,
        embeddings_service: Any | None = None,
        graph_intelligence_service: Any | None = None,
        relationship_service: Any | None = None,
        event_bus: Any | None = None,
    ) -> None:
        """
        Initialize AI service with common attributes.

        Args:
            backend: Domain operations protocol (REQUIRED)
            llm_service: LLMService for AI insights (often required)
            embeddings_service: EmbeddingsService for semantic search (often required)
            graph_intelligence_service: For graph context retrieval (optional)
            relationship_service: For relationship queries (optional)
            event_bus: For event publishing/subscription (optional)

        Raises:
            ValueError: If backend is None (FAIL-FAST architecture)
            ValueError: If _require_llm is True but llm_service not provided
            ValueError: If _require_embeddings is True but embeddings_service not provided
        """
        # FAIL-FAST: Backend is ALWAYS required
        if not backend:
            service_name = self._service_name or self.__class__.__name__
            raise ValueError(
                f"{service_name} backend is REQUIRED. SKUEL follows fail-fast architecture."
            )

        # Required attribute
        self.backend = backend

        # AI services
        self.llm = llm_service
        self.embeddings = embeddings_service

        # Optional services
        self.graph_intel = graph_intelligence_service
        self.relationships = relationship_service
        self.event_bus = event_bus

        # Logger initialization
        service_name = self._service_name or self.__class__.__name__
        self.logger = get_logger(f"skuel.ai.{service_name}")

        # Validate required AI services if specified by subclass
        if self._require_llm and not self.llm:
            raise ValueError(
                f"{self.__class__.__name__} requires llm_service. "
                "Set _require_llm = False to make it optional."
            )

        if self._require_embeddings and not self.embeddings:
            raise ValueError(
                f"{self.__class__.__name__} requires embeddings_service. "
                "Set _require_embeddings = False to make it optional."
            )

        # Auto-register event handlers
        self._register_event_handlers()

    # ========================================================================
    # EVENT HANDLING
    # ========================================================================

    def _register_event_handlers(self) -> None:
        """Auto-register event handlers from _event_handlers class attribute."""
        if not self.event_bus or not self._event_handlers:
            return

        for event_type, handler_name in self._event_handlers.items():
            handler = getattr(self, handler_name, None)
            if handler:
                self.event_bus.subscribe(event_type, handler)
                self.logger.debug(f"Registered handler {handler_name} for {event_type.__name__}")
            else:
                self.logger.warning(f"Handler {handler_name} for {event_type.__name__} not found")

    async def _publish_event(self, event: Any) -> None:
        """Publish an event to the event bus if available."""
        await publish_event(self.event_bus, event, self.logger)

    # ========================================================================
    # AI HELPERS
    # ========================================================================

    def _require_llm_service(self, operation: str) -> None:
        """
        Validate that LLM service is available.

        Args:
            operation: Name of the operation for error message

        Raises:
            ValueError: If llm is not available
        """
        if not self.llm:
            raise ValueError(f"{self.__class__.__name__}.{operation}() requires llm_service")

    def _require_embeddings_service(self, operation: str) -> None:
        """
        Validate that embeddings service is available.

        Args:
            operation: Name of the operation for error message

        Raises:
            ValueError: If embeddings is not available
        """
        if not self.embeddings:
            raise ValueError(f"{self.__class__.__name__}.{operation}() requires embeddings_service")

    async def _get_embedding(self, text: str) -> Result[list[float]]:
        """
        Get embedding vector for text using embeddings service.

        Args:
            text: Text to embed

        Returns:
            Result containing embedding vector or error
        """
        if not self.embeddings:
            return Result.fail(
                Errors.unavailable(
                    feature="embeddings",
                    reason="Embeddings service not configured",
                    operation="get_embedding",
                )
            )

        try:
            embedding = await self.embeddings.embed_text(text)
            return Result.ok(embedding)
        except Exception as e:
            self.logger.error(f"Embedding generation failed: {e}")
            return Result.fail(
                Errors.integration(
                    message=f"Embedding generation failed: {e}",
                    service="embeddings",
                )
            )

    async def _generate_insight(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        max_tokens: int = 500,
    ) -> Result[str]:
        """
        Generate AI insight using LLM service.

        Args:
            prompt: The prompt for the LLM
            context: Optional context to include
            max_tokens: Maximum tokens in response

        Returns:
            Result containing generated text or error
        """
        if not self.llm:
            return Result.fail(
                Errors.unavailable(
                    feature="ai_insights",
                    reason="LLM service not configured",
                    operation="generate_insight",
                )
            )

        try:
            # Build full prompt with context if provided
            full_prompt = prompt
            if context:
                context_str = "\n".join(f"{k}: {v}" for k, v in context.items())
                full_prompt = f"Context:\n{context_str}\n\n{prompt}"

            response = await self.llm.generate(full_prompt, max_tokens=max_tokens)
            return Result.ok(response)
        except Exception as e:
            self.logger.error(f"LLM generation failed: {e}")
            return Result.fail(
                Errors.integration(
                    message=f"LLM generation failed: {e}",
                    service="llm",
                )
            )

    async def _semantic_search(
        self,
        query: str,
        candidates: list[tuple[str, str]],
        top_k: int = 5,
    ) -> Result[list[tuple[str, float]]]:
        """
        Perform semantic search using embeddings.

        Args:
            query: Search query
            candidates: List of (uid, text) tuples to search
            top_k: Number of results to return

        Returns:
            Result containing list of (uid, similarity_score) tuples
        """
        if not self.embeddings:
            return Result.fail(
                Errors.unavailable(
                    feature="semantic_search",
                    reason="Embeddings service not configured",
                    operation="semantic_search",
                )
            )

        try:
            # Get query embedding
            query_embedding = await self.embeddings.embed_text(query)

            # Get candidate embeddings and calculate similarity
            results: list[tuple[str, float]] = []
            for uid, text in candidates:
                candidate_embedding = await self.embeddings.embed_text(text)
                similarity = self._cosine_similarity(query_embedding, candidate_embedding)
                results.append((uid, similarity))

            # Sort by similarity and return top_k
            results.sort(key=get_second_item, reverse=True)
            return Result.ok(results[:top_k])
        except Exception as e:
            self.logger.error(f"Semantic search failed: {e}")
            return Result.fail(
                Errors.integration(
                    message=f"Semantic search failed: {e}",
                    service="embeddings",
                )
            )

    @staticmethod
    def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        import math

        dot_product = sum(a * b for a, b in zip(vec1, vec2, strict=False))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)
