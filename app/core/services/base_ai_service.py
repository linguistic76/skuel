"""
Base AI Service
===============

Base class for domain AI services (LLM/embeddings-powered features).

Separates AI-powered features from graph-based analytics (ADR-024).

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

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeVar

from core.events import publish_event
from core.models.entity import Entity
from core.models.enums.entity_enums import EntityType
from core.models.type_hints import EntityUID
from core.utils.embedding_text_builder import build_embedding_text
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_second_item
from core.utils.vector_math import normalized_cosine_similarity

if TYPE_CHECKING:
    from core.services.embeddings_service import EmbeddingsService
    from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
    from core.services.llm_service import LLMService

# Generic type vars
B = TypeVar("B")  # Backend operations protocol
T = TypeVar("T")  # Domain model type


class BaseAIService(Generic[B, T]):
    """
    Base class for domain AI services.

    Provides AI-powered features using LLM and embeddings.
    These services are OPTIONAL - the app works without them.

    ARCHITECTURE (Post-GenAI Migration):
    - AI services accept optional LLM/embeddings (can be None)
    - Services gracefully degrade when AI unavailable
    - Runtime checks in methods that need AI features
    - No _require_* flags - all AI is optional

    Class Attributes:
        _service_name: Override for hierarchical logger name (e.g., "tasks.ai")

    Instance Attributes:
        backend: Domain operations protocol (REQUIRED)
        llm: LLMService for AI insights (optional)
        embeddings: EmbeddingsService for semantic search (optional)
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

    # Event handlers to auto-register
    _event_handlers: ClassVar[dict[type, str]] = {}

    def __init__(
        self,
        backend: B,
        llm_service: LLMService | None = None,
        embeddings_service: EmbeddingsService | None = None,
        graph_intel: GraphIntelligenceService | None = None,
        relationship_service: Any | None = None,
        event_bus: Any | None = None,
    ) -> None:
        """
        Initialize AI service with common attributes.

        GRACEFUL DEGRADATION:
        - LLM and embeddings services are optional (can be None)
        - Services warn when AI unavailable but continue functioning
        - Methods check at runtime and return Result.fail() if needed

        Args:
            backend: Domain operations protocol (REQUIRED)
            llm_service: LLMService for AI insights (optional)
            embeddings_service: EmbeddingsService for semantic search (optional)
            graph_intel: For graph context retrieval (optional)
            relationship_service: For relationship queries (optional)
            event_bus: For event publishing/subscription (optional)

        Raises:
            ValueError: If backend is None (FAIL-FAST architecture)
        """
        # FAIL-FAST: Backend is ALWAYS required
        if not backend:
            service_name = self._service_name or self.__class__.__name__
            raise ValueError(
                f"{service_name} backend is REQUIRED. SKUEL follows fail-fast architecture."
            )

        # Required attribute
        self.backend = backend

        # AI services (optional - can be None)
        self.llm = llm_service
        self.embeddings = embeddings_service

        # Optional services
        self.graph_intel = graph_intel
        self.relationships = relationship_service
        self.event_bus = event_bus

        # Logger initialization
        service_name = self._service_name or self.__class__.__name__
        self.logger = get_logger(f"skuel.ai.{service_name}")

        # Warn if AI services unavailable (graceful degradation)
        if not self.llm:
            self.logger.warning(
                f"{self.__class__.__name__}: LLM service unavailable - AI insights disabled"
            )

        if not self.embeddings:
            self.logger.warning(
                f"{self.__class__.__name__}: Embeddings service unavailable - semantic search disabled"
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

    async def _generate_insight(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        max_tokens: int = 500,
    ) -> Result[str]:
        """
        Generate AI insight using LLM service.

        ``LLMService.generate`` always answers: a provider failure comes back
        as a response with empty ``content`` and a set ``error``, never as an
        exception. This helper is where that degraded response becomes a
        failed ``Result``, so a caller that parses the text never sees an
        empty answer as success.

        Args:
            prompt: The prompt for the LLM
            context: Optional context to include
            max_tokens: Maximum tokens in response

        Returns:
            Result containing the generated text, or an integration error
        """
        if not self.llm:
            return Result.fail(
                Errors.unavailable(
                    feature="ai_insights",
                    reason="LLM service not configured",
                    operation="generate_insight",
                )
            )

        # Build full prompt with context if provided
        full_prompt = prompt
        if context:
            context_str = "\n".join(f"{k}: {v}" for k, v in context.items())
            full_prompt = f"Context:\n{context_str}\n\n{prompt}"

        response = await self.llm.generate(full_prompt, max_tokens=max_tokens)
        if response.error is not None:
            self.logger.error(f"LLM generation failed ({response.provider}): {response.error}")
            return Result.fail(
                Errors.integration(
                    message=f"LLM generation failed: {response.error}",
                    service="llm",
                )
            )
        return Result.ok(response.content)

    async def _rank_similar_entities(
        self,
        source: Entity,
        entity_type: EntityType,
        candidate_pool: Sequence[Entity],
        *,
        exclude_uid: str,
        limit: int = 5,
    ) -> Result[list[tuple[EntityUID, float]]]:
        """Rank ``candidate_pool`` by cosine similarity of stored vectors to ``source``.

        The shared tail of every Activity ``find_similar_*`` method. Each
        candidate is scored by the ``embedding`` its model carries (the vector
        the embedding worker stored on the node); a candidate without one, and
        ``exclude_uid``, are left out of the ranking. The source's own stored
        vector is used when it has one; otherwise its canonical embedding text
        (``build_embedding_text``, the text the stored vectors were built from)
        is embedded once through ``create_embedding``, and that failure is
        propagated.

        Scores are ``normalized_cosine_similarity`` — the ``[0, 1]`` scale the
        vector indexes answer on — so an Activity ranking and a curriculum
        index query speak one scale. No threshold is applied: the top ``limit``
        of the pool are returned however weak.

        Callers own the backend read of the pool — the owner-scoped
        ``find_by(user_uid=...)`` — because ownership is theirs to state.
        """
        candidates: list[tuple[EntityUID, Sequence[float]]] = [
            (EntityUID(entity.uid), entity.embedding)
            for entity in candidate_pool
            if entity.uid != exclude_uid and entity.embedding is not None
        ]
        if not candidates:
            return Result.ok([])

        source_vector: Sequence[float]
        if source.embedding is not None:
            source_vector = source.embedding
        else:
            if not self.embeddings:
                return Result.fail(
                    Errors.unavailable(
                        feature="semantic_search",
                        reason="Embeddings service not configured",
                        operation="rank_similar_entities",
                    )
                )
            embedding_result = await self.embeddings.create_embedding(
                build_embedding_text(entity_type, source)
            )
            if embedding_result.is_error:
                return Result.fail(embedding_result)
            source_vector = embedding_result.value

        ranked = [
            (uid, normalized_cosine_similarity(source_vector, vector)) for uid, vector in candidates
        ]
        ranked.sort(key=get_second_item, reverse=True)
        return Result.ok(ranked[:limit])
