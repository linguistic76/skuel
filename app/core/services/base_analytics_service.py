"""
Base Analytics Service
======================

Base class for domain analytics services (graph-based intelligence, no AI dependencies).

Created: January 2026
Purpose: Separate graph-based analytics from AI-powered features (ADR-030)

Analytics services contain:
- Graph context retrieval (get_with_context)
- Performance aggregation (get_performance_analytics)
- Pattern analysis (PatternAnalyzer - pure Python)
- Scoring calculations (graph queries + math)
- Domain insights (non-AI)

Analytics services explicitly DO NOT use:
- embeddings_service (semantic search)
- llm_service (AI insights)

This allows the app to function fully without any LLM dependencies.

Usage:
    class TasksIntelligenceService(BaseAnalyticsService[TasksOperations, Task]):
        _service_name = "tasks.intelligence"

        async def get_performance_analytics(self, user_uid: str) -> Result[dict]:
            # Pure graph queries and Python calculations
            ...
"""

from collections.abc import Awaitable, Callable
from typing import Any, ClassVar, Generic, TypeVar

from core.events import publish_event
from core.models.shared.dual_track import DualTrackResult
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

# Generic type vars
B = TypeVar("B")  # Backend operations protocol
T = TypeVar("T")  # Domain model type
L = TypeVar("L")  # Level enum type for dual-track assessment


class BaseAnalyticsService(Generic[B, T]):
    """
    Base class for domain analytics services.

    Provides graph-based analytics WITHOUT AI dependencies.
    The app can run with just core + analytics (no LLM required).

    Class Attributes:
        _service_name: Override for hierarchical logger name (e.g., "tasks.analytics")
        _require_relationships: If True, fail if relationships not provided (default: False)
        _require_graph_intel: If True, fail if graph_intel not provided (default: False)

    Instance Attributes:
        backend: Domain operations protocol (REQUIRED)
        graph_intel: GraphIntelligenceService for context (optional but recommended)
        relationships: UnifiedRelationshipService for relationships (optional)
        logger: Logger instance

    Architectural Invariant (enforced via __slots__):
        Analytics services CANNOT have llm or embeddings attributes.
        This prevents accidental AI coupling and ensures the app runs without LLM dependencies.
        Attempts to set these attributes will raise AttributeError.
    """

    # Architectural constraint: Restrict attributes to prevent AI coupling
    # This enforces "Analytics must never depend on AI" in executable form
    __slots__ = ("backend", "event_bus", "graph_intel", "logger", "orchestrator", "relationships")

    # Service name for hierarchical logging
    _service_name: ClassVar[str | None] = None

    # Set to True if relationships service is required for this domain
    _require_relationships: ClassVar[bool] = False

    # Set to True if graph intelligence service is required for this domain
    _require_graph_intel: ClassVar[bool] = False

    # Event handlers to auto-register
    # Format: {EventClass: "handler_method_name"}
    _event_handlers: ClassVar[dict[type, str]] = {}

    def __setattr__(self, name: str, value: Any) -> None:
        """
        Enforce architectural invariant: Analytics services cannot have AI dependencies.

        This prevents setting llm or embeddings attributes, even if child classes
        have __dict__ due to not defining __slots__.
        """
        if name in ("llm", "embeddings", "llm_service", "embeddings_service"):
            raise AttributeError(
                f"Cannot set '{name}' on {self.__class__.__name__}. "
                f"Analytics services must never depend on AI (llm/embeddings). "
                f"Use BaseAIService for AI-powered features."
            )
        object.__setattr__(self, name, value)

    def __init__(
        self,
        backend: B,
        graph_intelligence_service: Any | None = None,
        relationship_service: Any | None = None,
        event_bus: Any | None = None,
    ) -> None:
        """
        Initialize analytics service with common attributes.

        Args:
            backend: Domain operations protocol (REQUIRED)
            graph_intelligence_service: For graph context retrieval (optional)
            relationship_service: For relationship queries (optional)
            event_bus: For event publishing/subscription (optional)

        Raises:
            ValueError: If backend is None (FAIL-FAST architecture)
            ValueError: If _require_relationships is True but service not provided
            ValueError: If _require_graph_intel is True but service not provided

        NOTE: No embeddings_service or llm_service parameters - this is intentional.
        Analytics services work without AI.
        """
        # FAIL-FAST: Backend is ALWAYS required
        if not backend:
            service_name = self._service_name or self.__class__.__name__
            raise ValueError(
                f"{service_name} backend is REQUIRED. SKUEL follows fail-fast architecture."
            )

        # Required attribute
        self.backend = backend

        # Optional services (NO embeddings, NO llm)
        self.graph_intel = graph_intelligence_service
        self.relationships = relationship_service
        self.event_bus = event_bus

        # Orchestrator - initialized by child classes when graph_intel is available
        self.orchestrator: Any | None = None

        # Logger initialization
        service_name = self._service_name or self.__class__.__name__
        self.logger = get_logger(f"skuel.analytics.{service_name}")

        # Validate required services if specified by subclass
        if self._require_relationships and not self.relationships:
            raise ValueError(
                f"{self.__class__.__name__} requires relationship_service. "
                "Set _require_relationships = False to make it optional."
            )

        if self._require_graph_intel and not self.graph_intel:
            raise ValueError(
                f"{self.__class__.__name__} requires graph_intelligence_service. "
                "Set _require_graph_intel = False to make it optional."
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
    # COMMON HELPERS
    # ========================================================================

    def _require_graph_intelligence(self, operation: str) -> None:
        """
        Validate that graph intelligence service is available.

        Args:
            operation: Name of the operation for error message

        Raises:
            ValueError: If graph_intel is not available
        """
        if not self.graph_intel:
            raise ValueError(
                f"{self.__class__.__name__}.{operation}() requires graph_intelligence_service"
            )

    def _require_relationship_service(self, operation: str) -> None:
        """
        Validate that relationship service is available.

        Args:
            operation: Name of the operation for error message

        Raises:
            ValueError: If relationships is not available
        """
        if not self.relationships:
            raise ValueError(
                f"{self.__class__.__name__}.{operation}() requires relationship_service"
            )

    def _to_domain_model(self, dto_or_dict: Any, dto_class: type, model_class: type[T]) -> T:
        """
        Convert DTO or dict to domain model.

        Handles the common pattern of receiving data that may be:
        - Already the domain model (pass through)
        - A DTO that needs conversion via from_dto()
        - A dict that needs conversion to DTO then domain model

        Args:
            dto_or_dict: The data to convert (model, DTO, or dict)
            dto_class: The DTO class type for dict conversion
            model_class: The target domain model class

        Returns:
            Instance of the domain model
        """
        if isinstance(dto_or_dict, model_class):
            return dto_or_dict
        if isinstance(dto_or_dict, dto_class):
            return model_class.from_dto(dto_or_dict)  # type: ignore[attr-defined]
        if isinstance(dto_or_dict, dict):
            dto = dto_class(**dto_or_dict)
            return model_class.from_dto(dto)  # type: ignore[attr-defined]
        return dto_or_dict  # type: ignore[return-value]

    # ========================================================================
    # CONTEXT ANALYSIS TEMPLATE
    # ========================================================================

    async def _analyze_entity_with_context(
        self,
        uid: str,
        context_method: str,
        context_type: type,
        metrics_fn: Callable[[Any, Any], dict[str, Any]],
        recommendations_fn: Callable[[Any, Any, dict[str, Any]], list[str]] | None = None,
        **context_kwargs: Any,
    ) -> Result[dict[str, Any]]:
        """
        Template method for context-based entity analysis.

        Consolidates the common pattern:
        1. Fetch entity from backend
        2. Get cross-domain context via relationships service
        3. Calculate metrics using provided function
        4. Generate recommendations (optional)
        5. Return structured result

        Args:
            uid: Entity UID to analyze
            context_method: Method name on relationships service
            context_type: Expected context dataclass type
            metrics_fn: Function (entity, context) -> metrics dict
            recommendations_fn: Optional function (entity, context, metrics) -> list[str]
            **context_kwargs: Additional args for context method

        Returns:
            Result[dict] with structure:
            {
                "entity": <domain model>,
                "metrics": <calculated metrics>,
                "recommendations": <list of recommendations>,
                "context": <typed cross-domain context>,
            }
        """
        from core.utils.result_simplified import Errors

        # 1. Fetch entity from backend
        entity_result = await self.backend.get(uid)  # type: ignore[attr-defined]
        if entity_result.is_error:
            return entity_result

        entity = entity_result.value
        if not entity:
            return Result.fail(Errors.not_found(f"Entity not found: {uid}"))

        # 2. Get context via relationships service
        context = None
        if self.relationships:
            context_fn = getattr(self.relationships, context_method, None)
            if context_fn:
                try:
                    if context_kwargs:
                        try:
                            context_result = await context_fn(uid, **context_kwargs)
                        except TypeError:
                            self.logger.debug(
                                f"Context method {context_method} doesn't accept kwargs"
                            )
                            context_result = await context_fn(uid)
                    else:
                        context_result = await context_fn(uid)

                    # Handle Result wrapper if present
                    if isinstance(context_result, Result):
                        if context_result.is_ok:
                            raw_context = context_result.value
                        else:
                            self.logger.warning(
                                f"Context fetch failed for {uid}: {context_result.expect_error()}"
                            )
                            raw_context = None
                    else:
                        raw_context = context_result

                    # Convert to typed context using from_dict if available
                    if raw_context is not None:
                        from_dict_method = getattr(context_type, "from_dict", None)
                        if from_dict_method is not None and isinstance(raw_context, dict):
                            context = from_dict_method(raw_context)
                        else:
                            context = raw_context
                except Exception as e:
                    self.logger.warning(f"Failed to get context for {uid}: {e}")

        # 3. Calculate metrics
        metrics: dict[str, Any] = {}
        if context:
            try:
                metrics = metrics_fn(entity, context)
            except Exception as e:
                self.logger.warning(f"Failed to calculate metrics for {uid}: {e}")

        # 4. Generate recommendations (optional)
        recommendations: list[str] = []
        if recommendations_fn and context:
            try:
                recommendations = recommendations_fn(entity, context, metrics)
            except Exception as e:
                self.logger.warning(f"Failed to generate recommendations for {uid}: {e}")

        # 5. Return structured result
        return Result.ok(
            {
                "entity": entity,
                "metrics": metrics,
                "recommendations": recommendations,
                "context": context,
            }
        )

    # ========================================================================
    # DUAL-TRACK ASSESSMENT TEMPLATE (ADR-030 - January 2026)
    # ========================================================================

    async def _dual_track_assessment(
        self,
        uid: str,
        user_uid: str,
        # USER-DECLARED (Vision)
        user_level: L,
        user_evidence: str,
        user_reflection: str | None,
        # SYSTEM CALCULATION
        system_calculator: Callable[[Any, str], Awaitable[tuple[L, float, list[str]]]],
        # LEVEL SCORING (domain-specific enum → float)
        level_scorer: Callable[[L], float],
        # OPTIONAL CUSTOMIZATION
        entity_type: str = "",
        insight_generator: Callable[[str, float, str], list[str]] | None = None,
        recommendation_generator: Callable[[str, float, Any, list[str]], list[str]] | None = None,
        store_callback: Callable[[str, Any], Awaitable[None]] | None = None,
    ) -> "Result[DualTrackResult[L]]":
        """
        Template method for dual-track assessment.

        Compares user self-assessment (vision) with system measurement (action)
        to generate perception gap analysis and insights.

        This implements SKUEL's core philosophy:
        "The user's vision is understood via the words they use to communicate,
        the UserContext is determined via user's actions."

        Args:
            uid: Entity UID to assess
            user_uid: User making the assessment
            user_level: User's self-reported level (domain-specific enum)
            user_evidence: User's evidence for their assessment
            user_reflection: Optional reflection on their alignment
            system_calculator: Async fn(entity, user_uid) -> (level, score, evidence)
            level_scorer: Fn(level) -> float score (0.0-1.0)
            entity_type: EntityType value for result (e.g., "principle", "goal")
            insight_generator: Optional custom insight generation
            recommendation_generator: Optional custom recommendations
            store_callback: Optional async fn(uid, assessment_data) to persist

        Returns:
            Result[DualTrackResult[L]] containing dual-track assessment

        Example:
            async def assess_alignment_dual_track(
                self, principle_uid: str, user_uid: str, user_level: AlignmentLevel, ...
            ) -> Result[DualTrackResult[AlignmentLevel]]:
                return await self._dual_track_assessment(
                    uid=principle_uid,
                    user_uid=user_uid,
                    user_level=user_level,
                    user_evidence=evidence,
                    user_reflection=reflection,
                    system_calculator=self._calculate_system_alignment,
                    level_scorer=self._alignment_level_to_score,
                    entity_type="principle",
                )
        """
        from core.utils.result_simplified import Errors

        # 1. Fetch entity from backend
        entity_result = await self.backend.get(uid)  # type: ignore[attr-defined]
        if entity_result.is_error:
            return entity_result

        entity = entity_result.value
        if not entity:
            return Result.fail(Errors.not_found(f"Entity not found: {uid}"))

        # 2. Calculate user score from level
        user_score = level_scorer(user_level)

        # 3. Calculate system alignment
        try:
            system_level, system_score, system_evidence = await system_calculator(entity, user_uid)
        except Exception as e:
            self.logger.error(f"System calculation failed for {uid}: {e}")
            return Result.fail(
                Errors.system(message=f"System calculation failed: {e}", operation="dual_track")
            )

        # 4. Calculate perception gap
        gap, direction = self._calculate_perception_gap(user_score, system_score)

        # 5. Get entity name for insights
        entity_name = getattr(entity, "name", None) or getattr(entity, "title", uid)

        # 6. Generate insights
        if insight_generator:
            insights = insight_generator(direction, gap, entity_name)
        else:
            insights = self._default_gap_insights(direction, gap, entity_name)

        # 7. Generate recommendations
        if recommendation_generator:
            recommendations = recommendation_generator(direction, gap, entity, system_evidence)
        else:
            recommendations = self._default_gap_recommendations(
                direction, gap, entity, system_evidence
            )

        # 8. Store assessment if callback provided
        if store_callback:
            try:
                assessment_data = {
                    "user_level": user_level,
                    "user_evidence": user_evidence,
                    "user_reflection": user_reflection,
                }
                await store_callback(uid, assessment_data)
            except Exception as e:
                self.logger.warning(f"Failed to store assessment for {uid}: {e}")

        # 9. Build and return DualTrackResult
        result = DualTrackResult(
            entity_uid=uid,
            entity_type=entity_type,
            user_level=user_level,
            user_score=user_score,
            user_evidence=user_evidence,
            user_reflection=user_reflection,
            system_level=system_level,
            system_score=system_score,
            system_evidence=tuple(system_evidence),
            perception_gap=gap,
            gap_direction=direction,
            insights=tuple(insights),
            recommendations=tuple(recommendations[:4]),  # Limit to top 4
        )

        return Result.ok(result)

    def _calculate_perception_gap(
        self, user_score: float, system_score: float
    ) -> tuple[float, str]:
        """
        Calculate gap between user perception and system measurement.

        Args:
            user_score: User's self-assessed score (0.0-1.0)
            system_score: System-measured score (0.0-1.0)

        Returns:
            Tuple of (gap_magnitude, gap_direction)
            - gap_magnitude: Absolute difference (0.0-1.0)
            - gap_direction: "user_higher" | "system_higher" | "aligned"
        """
        gap = user_score - system_score

        if abs(gap) < 0.15:
            direction = "aligned"
        elif gap > 0:
            direction = "user_higher"  # User thinks more aligned than system shows
        else:
            direction = "system_higher"  # System shows more aligned than user thinks

        return abs(gap), direction

    @staticmethod
    def _default_gap_insights(
        direction: str,
        gap: float,
        entity_name: str,
    ) -> list[str]:
        """
        Generate default insights based on perception gap.

        Override this method in subclasses for domain-specific insights.

        Args:
            direction: "user_higher" | "system_higher" | "aligned"
            gap: Absolute gap magnitude (0.0-1.0)
            entity_name: Name of the entity being assessed

        Returns:
            List of insight strings
        """
        insights: list[str] = []

        if direction == "aligned":
            insights.append(
                f"Your self-perception of '{entity_name}' matches your recorded actions. "
                "This indicates healthy self-reflection."
            )
        elif direction == "user_higher":
            insights.append(
                f"Your self-assessment is more positive than your recorded actions suggest "
                f"(gap: {gap:.0%}). Consider: Are there activities expressing this "
                "that aren't tracked in SKUEL?"
            )
            if gap > 0.3:
                insights.append(
                    "This significant gap may indicate a blind spot in self-perception, "
                    "or opportunities to better live out this value."
                )
        else:  # system_higher
            insights.append(
                f"Your actions show stronger alignment than you perceive (gap: {gap:.0%}). "
                "You may be undervaluing your consistency."
            )
            if gap > 0.3:
                insights.append(
                    "Consider acknowledging your progress - self-recognition strengthens motivation."
                )

        return insights

    @staticmethod
    def _default_gap_recommendations(
        direction: str,
        _gap: float,
        entity: Any,
        evidence: list[str],
    ) -> list[str]:
        """
        Generate default recommendations to close the perception gap.

        Override this method in subclasses for domain-specific recommendations.

        Args:
            direction: "user_higher" | "system_higher" | "aligned"
            _gap: Absolute gap magnitude (0.0-1.0) - unused in default, available for overrides
            entity: The entity being assessed
            evidence: System-calculated evidence list

        Returns:
            List of recommendation strings (max 4)
        """
        recommendations: list[str] = []
        entity_name = getattr(entity, "name", None) or getattr(entity, "title", "this item")

        if direction == "aligned":
            recommendations.append(
                "Continue your current approach - your self-awareness is accurate."
            )
            recommendations.append(
                "Consider documenting new expressions of this value as they arise."
            )
        elif direction == "user_higher":
            recommendations.append(
                f"Review your goals and habits to ensure they explicitly connect to '{entity_name}'."
            )
            if not evidence:
                recommendations.append(
                    f"Create at least one goal or habit that directly expresses '{entity_name}'."
                )
            recommendations.append(
                f"Track specific instances where you practice '{entity_name}' over the next week."
            )
        else:  # system_higher
            recommendations.append(
                "Acknowledge the alignment you've already achieved through your actions."
            )
            if evidence:
                recommendations.append(
                    f"Celebrate your progress: {len(evidence)} activities already express this value."
                )
            recommendations.append(
                "Consider reflecting on why your self-perception doesn't match your positive actions."
            )

        return recommendations[:4]
