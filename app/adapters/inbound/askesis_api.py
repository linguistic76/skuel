"""
Askesis API Routes - Migrated to service-based architecture
============================================================

Migrated from mock responses to actual service integration.

Before: 577 lines with manual response helpers and mock data
After: ~300 lines with boundary_handler and service integration

Note: This API is 100% domain-specific (conversation management, guidance, analytics),
so CRUDRouteFactory is not applicable. Migration focuses on:
1. Removing custom response helpers (use boundary_handler)
2. Removing mock data responses
3. Adding Pydantic validation
4. Preparing for service integration
5. Adding proper HTTP status codes (201 for creates)
"""

__version__ = "2.0"

from typing import TYPE_CHECKING, Any

from fasthtml.common import Request

from core.models.askesis.askesis_request import (
    AskesisAnalyticsRequest,
    AskesisCreateRequest,
    AskesisUpdateRequest,
    ConversationSessionCreateRequest,
    DomainInteractionRequest,
    DomainSuggestionRequest,
    GuidanceRecommendationCreateRequest,
    IntelligenceUpdateRequest,
)
from core.services.protocols import AskesisOperations
from core.utils.error_boundary import boundary_handler
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from neo4j import AsyncDriver

logger = get_logger("skuel.routes.askesis.api")


def create_askesis_api_routes(
    _app: Any,
    rt: Any,
    _askesis_service: AskesisOperations,
    _askesis_core_service: Any = None,
    driver: "AsyncDriver | None" = None,
) -> list[Any]:
    """
    Create clean API routes for Askesis functionality with service integration.

    Args:
        app: FastHTML application instance
        rt: Route decorator
        askesis_service: AskesisService instance (intelligence)
        askesis_core_service: AskesisCoreService instance (CRUD operations)
        driver: Neo4j driver for UserContextBuilder (required for context-aware routes)

    Returns:
        Empty list (routes registered via decorators)
    """

    # ========================================================================
    # CORE ASKESIS OPERATIONS
    # ========================================================================

    @rt("/api/askesis/ask")
    @boundary_handler()
    async def ask_question_route(request: Request) -> Result[dict[str, Any]]:
        """
        Ask Askesis a question using RAG pipeline.

        Query Parameters:
            user_uid (str): User identifier
            question (str): Natural language question

        Returns:
            Result[dict]: Response containing:
                - answer (str): LLM-generated answer
                - context_used (dict): Context that informed the answer
                - suggested_actions (list): Actionable next steps
                - entities_extracted (dict): Entities mentioned in question
                - query_intent (str): Detected question intent

        Example:
            GET /api/askesis/ask?user_uid=user.mike&question=What should I learn next?
        """
        user_uid = request.query_params.get("user_uid")
        question = request.query_params.get("question")

        # Validate required parameters
        if not user_uid:
            return Result.fail(
                Errors.validation(
                    message="user_uid is required",
                    field="user_uid",
                    value=None,
                )
            )

        if not question:
            return Result.fail(
                Errors.validation(
                    message="question is required",
                    field="question",
                    value=None,
                )
            )

        # Call RAG pipeline
        logger.info(f"RAG question from {user_uid}: {question}")
        result = await _askesis_service.answer_user_question(user_uid, question)

        if result.is_ok:
            logger.info(f"RAG answer generated for {user_uid}")
        else:
            logger.error(f"RAG pipeline failed for {user_uid}: {result.error}")

        return result

    @rt("/api/askesis/user")
    @boundary_handler()
    async def get_user_askesis_route(request: Request, user_uid: str) -> Result:
        """Get user's Askesis AI assistant instance (or create if not exists)."""

        if not _askesis_core_service:
            return Result.fail(
                Errors.system(
                    message="Askesis core service not available",
                    operation="get_user_askesis",
                )
            )

        # Get or create Askesis instance for user
        return await _askesis_core_service.get_or_create_for_user(user_uid)

    @rt("/api/askesis")
    @boundary_handler(success_status=201)
    async def create_askesis_instance_route(request: Request) -> Result:
        """Create new Askesis AI assistant instance."""
        body = await request.json()

        askesis_request = AskesisCreateRequest.model_validate(body)
        user_uid = body.get("user_uid")

        if not user_uid:
            return Result.fail(
                Errors.validation(
                    message="user_uid is required",
                    field="user_uid",
                    value=None,
                )
            )

        if not _askesis_core_service:
            return Result.fail(
                Errors.system(
                    message="Askesis core service not available",
                    operation="create_askesis_instance",
                )
            )

        # Create Askesis instance
        return await _askesis_core_service.create_askesis(user_uid, askesis_request)

    @rt("/api/askesis/settings", methods=["PUT"])
    @boundary_handler()
    async def update_askesis_settings_route(request: Request, askesis_uid: str) -> Result[Any]:
        """Update Askesis settings and preferences."""
        body = await request.json()

        askesis_update = AskesisUpdateRequest.model_validate(body)

        if not _askesis_core_service:
            return Result.fail(
                Errors.system(
                    message="Askesis core service not available",
                    operation="update_askesis_settings",
                )
            )

        # Update Askesis settings
        return await _askesis_core_service.update_askesis(askesis_uid, askesis_update)

    # ========================================================================
    # CONVERSATION MANAGEMENT
    # ========================================================================
    #
    # FUTURE ENHANCEMENT: Conversation management routes
    #
    # Note: The /api/askesis/ask route already provides Q&A functionality
    # using the RAG pipeline. Full conversation session management with
    # state tracking and multi-turn dialogue is planned for a future release.
    #
    # Planned features:
    # - Conversation session creation and tracking
    # - Multi-turn dialogue with context preservation
    # - Conversation history and retrieval
    # - Session analytics and insights
    #
    # For now, use /api/askesis/ask for single-turn Q&A interactions.
    # ========================================================================

    @rt("/api/askesis/conversations", methods=["POST"])
    @boundary_handler(success_status=201)
    async def create_conversation_route(request: Request, askesis_uid: str) -> Result[Any]:
        """
        Start new conversation session.

        FUTURE ENHANCEMENT: Full conversation session management coming soon.
        Use /api/askesis/ask for Q&A interactions.
        """
        body = await request.json()

        ConversationSessionCreateRequest.model_validate(body)

        return Result.fail(
            Errors.system(
                message="Conversation sessions are a future enhancement. Use /api/askesis/ask for Q&A.",
                operation="create_conversation",
            )
        )

    @rt("/api/askesis/conversations/messages", methods=["POST"])
    @boundary_handler(success_status=201)
    async def send_message_route(request: Request, conversation_uid: str) -> Result[Any]:
        """
        Send message in conversation.

        FUTURE ENHANCEMENT: Multi-turn dialogue coming soon.
        Use /api/askesis/ask for Q&A interactions.
        """
        body = await request.json()

        # Simple validation - message content required
        user_message = body.get("message")
        if not user_message:
            return Result.fail(
                Errors.validation(message="Message content is required", field="message")
            )

        return Result.fail(
            Errors.system(
                message="Multi-turn dialogue is a future enhancement. Use /api/askesis/ask for Q&A.",
                operation="send_message",
            )
        )

    @rt("/api/askesis/conversations/get")
    @boundary_handler()
    async def get_conversation_route(request: Request, conversation_uid: str) -> Result[Any]:
        """
        Get conversation details and history.

        FUTURE ENHANCEMENT: Conversation history coming soon.
        Use /api/askesis/ask for Q&A interactions.
        """

        return Result.fail(
            Errors.system(
                message="Conversation history is a future enhancement. Use /api/askesis/ask for Q&A.",
                operation="get_conversation",
            )
        )

    # ========================================================================
    # GUIDANCE AND RECOMMENDATIONS
    # ========================================================================

    @rt("/api/askesis/guidance", methods=["POST"])
    @boundary_handler(success_status=200)
    async def generate_proactive_guidance_route(request: Request, askesis_uid: str) -> Result[Any]:
        """
        Generate proactive guidance and recommendations.

        Uses user context to provide next best action recommendation.
        """
        body = await request.json()

        GuidanceRecommendationCreateRequest.model_validate(body)

        if not _askesis_service:
            return Result.fail(
                Errors.system(
                    message="Askesis intelligence service not available",
                    operation="generate_guidance",
                )
            )

        # Get user UID from askesis instance
        if not _askesis_core_service:
            return Result.fail(
                Errors.system(
                    message="Askesis core service not available",
                    operation="generate_guidance",
                )
            )

        askesis_result = await _askesis_core_service.get_askesis(askesis_uid)
        if askesis_result.is_error:
            return askesis_result

        askesis = askesis_result.value
        user_uid = askesis.user_uid

        # Get user context
        from core.services.user.user_context_builder import UserContextBuilder

        if not driver:
            return Result.fail(
                Errors.system(
                    message="Driver not available for context building",
                    operation="generate_guidance",
                )
            )
        context_builder = UserContextBuilder(driver)
        context_result = await context_builder.build(user_uid)

        if context_result.is_error:
            return Result.fail(context_result.expect_error())

        user_context = context_result.value

        # Get next best action recommendation
        recommendation_result = await _askesis_service.get_next_best_action(user_context)

        if recommendation_result.is_error:
            return Result.fail(recommendation_result.expect_error())

        return Result.ok({"guidance": recommendation_result.value})

    @rt("/api/askesis/insights")
    @boundary_handler()
    async def get_ai_insights_route(request: Request, askesis_uid: str) -> Result[Any]:
        """
        Get AI-generated insights about user patterns.

        Analyzes user state and identifies behavioral patterns.
        """
        params = dict(request.query_params)

        params.get("timeframe", "7d")
        params.get("domains", "all")

        if not _askesis_service or not _askesis_core_service:
            return Result.fail(
                Errors.system(
                    message="Askesis services not available",
                    operation="get_ai_insights",
                )
            )

        # Get user UID from askesis instance
        askesis_result = await _askesis_core_service.get_askesis(askesis_uid)
        if askesis_result.is_error:
            return askesis_result

        askesis = askesis_result.value
        user_uid = askesis.user_uid

        # Get user context
        from core.services.user.user_context_builder import UserContextBuilder

        if not driver:
            return Result.fail(
                Errors.system(
                    message="Driver not available for context building",
                    operation="generate_guidance",
                )
            )
        context_builder = UserContextBuilder(driver)
        context_result = await context_builder.build(user_uid)

        if context_result.is_error:
            return Result.fail(context_result.expect_error())

        user_context = context_result.value

        # Analyze user state
        analysis_result = await _askesis_service.analyze_user_state(user_context)

        if analysis_result.is_error:
            return Result.fail(analysis_result.expect_error())

        # Identify patterns
        patterns_result = await _askesis_service.identify_patterns(user_context)

        if patterns_result.is_error:
            return Result.fail(patterns_result.expect_error())

        return Result.ok({"analysis": analysis_result.value, "patterns": patterns_result.value})

    # ========================================================================
    # DOMAIN INTEGRATION
    # ========================================================================

    @rt("/api/askesis/domain-integration", methods=["POST"])
    @boundary_handler(success_status=200)
    async def trigger_domain_integration_route(request: Request, askesis_uid: str) -> Result[Any]:
        """
        Trigger cross-domain integration and analysis.

        Analyzes workflow optimization opportunities across domains.
        """
        body = await request.json()

        DomainInteractionRequest.model_validate(body)

        if not _askesis_service or not _askesis_core_service:
            return Result.fail(
                Errors.system(
                    message="Askesis services not available",
                    operation="trigger_domain_integration",
                )
            )

        # Get user UID from askesis instance
        askesis_result = await _askesis_core_service.get_askesis(askesis_uid)
        if askesis_result.is_error:
            return askesis_result

        askesis = askesis_result.value
        user_uid = askesis.user_uid

        # Get user context
        from core.services.user.user_context_builder import UserContextBuilder

        if not driver:
            return Result.fail(
                Errors.system(
                    message="Driver not available for context building",
                    operation="generate_guidance",
                )
            )
        context_builder = UserContextBuilder(driver)
        context_result = await context_builder.build(user_uid)

        if context_result.is_error:
            return Result.fail(context_result.expect_error())

        user_context = context_result.value

        # Optimize workflow across domains
        optimization_result = await _askesis_service.optimize_workflow(user_context)

        if optimization_result.is_error:
            return Result.fail(optimization_result.expect_error())

        return Result.ok({"integrations": optimization_result.value})

    @rt("/api/askesis/analytics")
    @boundary_handler()
    async def get_askesis_analytics_route(request: Request, askesis_uid: str) -> Result[Any]:
        """
        Get Askesis performance and intelligence analytics.

        Provides system health metrics and predictions.
        """
        params = dict(request.query_params)

        analytics_request = AskesisAnalyticsRequest.model_validate(
            {
                "timeframe": params.get("timeframe", "30d"),
                "include_predictions": params.get("predictions", "false") == "true",
            }
        )

        if not _askesis_service or not _askesis_core_service:
            return Result.fail(
                Errors.system(
                    message="Askesis services not available",
                    operation="get_analytics",
                )
            )

        # Get askesis instance
        askesis_result = await _askesis_core_service.get_askesis(askesis_uid)
        if askesis_result.is_error:
            return askesis_result

        askesis = askesis_result.value
        user_uid = askesis.user_uid

        # Get user context
        from core.services.user.user_context_builder import UserContextBuilder

        if not driver:
            return Result.fail(
                Errors.system(
                    message="Driver not available for context building",
                    operation="generate_guidance",
                )
            )
        context_builder = UserContextBuilder(driver)
        context_result = await context_builder.build(user_uid)

        if context_result.is_error:
            return Result.fail(context_result.expect_error())

        user_context = context_result.value

        # Calculate system health
        health = _askesis_service.calculate_system_health(user_context)

        # Optionally get predictions
        predictions = None
        if analytics_request.include_predictions:
            predictions_result = await _askesis_service.predict_future_state(
                user_context, days_ahead=7
            )
            if predictions_result.is_ok:
                predictions = predictions_result.value

        return Result.ok(
            {
                "askesis_metrics": {
                    "intelligence_confidence": askesis.intelligence_confidence,
                    "total_conversations": askesis.total_conversations,
                    "integration_success_rate": askesis.integration_success_rate,
                },
                "system_health": health,
                "predictions": predictions,
            }
        )

    # ========================================================================
    # ADDITIONAL DOMAIN-SPECIFIC ROUTES
    # ========================================================================

    @rt("/api/askesis/suggestions")
    @boundary_handler(success_status=200)
    async def get_domain_suggestions_route(request: Request) -> Result[Any]:
        """
        Get domain suggestions based on user query.

        Uses the RAG pipeline to suggest relevant domains and entities.
        """
        body = await request.json()

        DomainSuggestionRequest.model_validate(body)
        user_uid = body.get("user_uid")
        query = body.get("query")

        if not user_uid or not query:
            return Result.fail(
                Errors.validation(
                    message="user_uid and query are required",
                    field="user_uid/query",
                    value=None,
                )
            )

        if not _askesis_service:
            return Result.fail(
                Errors.system(
                    message="Askesis intelligence service not available",
                    operation="get_domain_suggestions",
                )
            )

        # Use the RAG pipeline to process query
        answer_result = await _askesis_service.answer_user_question(user_uid, query)

        if answer_result.is_error:
            return Result.fail(answer_result.expect_error())

        # Extract entities from the answer
        entities = answer_result.value.get("entities_extracted", {})

        return Result.ok(
            {
                "query": query,
                "suggested_domains": list(entities.keys()),
                "entities": entities,
                "context": answer_result.value.get("context_used", {}),
            }
        )

    @rt("/api/askesis/intelligence", methods=["POST"])
    @boundary_handler(success_status=200)
    async def update_intelligence_route(request: Request, askesis_uid: str) -> Result[Any]:
        """
        Update Askesis intelligence based on feedback.

        Records conversation and updates intelligence metrics.
        """
        body = await request.json()

        IntelligenceUpdateRequest.model_validate(body)

        if not _askesis_core_service:
            return Result.fail(
                Errors.system(
                    message="Askesis core service not available",
                    operation="update_intelligence",
                )
            )

        # Record conversation (updates metrics)
        result = await _askesis_core_service.record_conversation(askesis_uid)

        if result.is_error:
            return Result.fail(result.expect_error())

        askesis = result.value

        return Result.ok(
            {
                "askesis_uid": askesis.uid,
                "intelligence_confidence": askesis.intelligence_confidence,
                "total_conversations": askesis.total_conversations,
                "last_interaction": askesis.last_interaction.isoformat()
                if askesis.last_interaction
                else None,
            }
        )

    # ========================================================================
    # 13-DOMAIN INTELLIGENCE ROUTES (UserContextIntelligence Integration)
    # ========================================================================
    #
    # These endpoints leverage the full 13-domain architecture for comprehensive
    # daily planning and learning step recommendations.
    #
    # Architecture:
    #   UserContextIntelligence = UserContext + 13 Domain Services
    #                           = User State + Complete Graph Intelligence
    #
    # The 13 Domains:
    #   Activity Domains (6): Tasks, Goals, Habits, Events, Choices, Principles
    #   Curriculum Domains (3): KU, LS, LP
    #   Processing Domains (3): Assignments, Journals, Reports
    #   Temporal Domain (1): Calendar
    #
    # ========================================================================

    @rt("/api/askesis/daily-plan")
    @boundary_handler()
    async def get_daily_work_plan_route(request: Request, askesis_uid: str) -> Result[Any]:
        """
        🎯 THE FLAGSHIP METHOD - What should the user focus on TODAY?

        Synthesizes ALL 13 domains to create a comprehensive daily plan:
        - At-risk habits (maintain streaks - highest priority)
        - Today's events (can't reschedule)
        - Overdue and actionable tasks
        - Daily habits (consistency)
        - Learning (if capacity allows)
        - Advancing goals
        - Pending decisions (high priority only)
        - Aligned principles (for focus)

        Query Parameters:
            prioritize_life_path (bool): Weight life path alignment highly (default: true)
            respect_capacity (bool): Don't exceed available time (default: true)

        Returns:
            Result[DailyWorkPlan]: Complete daily plan with:
                - Domain-specific item lists (learning, tasks, habits, events, goals, choices, principles)
                - Contextual items (enriched with relationships)
                - Estimated time and capacity utilization
                - Rationale and warnings
        """
        params = dict(request.query_params)

        prioritize_life_path = params.get("prioritize_life_path", "true").lower() == "true"
        respect_capacity = params.get("respect_capacity", "true").lower() == "true"

        if not _askesis_service or not _askesis_core_service:
            return Result.fail(
                Errors.system(
                    message="Askesis services not available",
                    operation="get_daily_work_plan",
                )
            )

        # Get user UID from askesis instance
        askesis_result = await _askesis_core_service.get_askesis(askesis_uid)
        if askesis_result.is_error:
            return askesis_result

        askesis = askesis_result.value
        user_uid = askesis.user_uid

        # Get user context
        from core.services.user.user_context_builder import UserContextBuilder

        if not driver:
            return Result.fail(
                Errors.system(
                    message="Driver not available for context building",
                    operation="generate_guidance",
                )
            )
        context_builder = UserContextBuilder(driver)
        context_result = await context_builder.build(user_uid)

        if context_result.is_error:
            return Result.fail(context_result.expect_error())

        user_context = context_result.value

        # Get daily work plan using 13-domain intelligence
        plan_result = await _askesis_service.get_daily_work_plan(
            user_context,
            prioritize_life_path=prioritize_life_path,
            respect_capacity=respect_capacity,
        )

        if plan_result.is_error:
            return Result.fail(plan_result.expect_error())

        plan = plan_result.value

        # Convert dataclass to dict for JSON response
        return Result.ok(
            {
                "daily_plan": {
                    "learning": plan.learning,
                    "tasks": plan.tasks,
                    "habits": plan.habits,
                    "events": plan.events,
                    "goals": plan.goals,
                    "choices": plan.choices,
                    "principles": plan.principles,
                    "estimated_time_minutes": plan.estimated_time_minutes,
                    "fits_capacity": plan.fits_capacity,
                    "workload_utilization": plan.workload_utilization,
                    "rationale": plan.rationale,
                    "priorities": plan.priorities,
                    "warnings": plan.warnings,
                },
                "user_uid": user_uid,
                "askesis_uid": askesis_uid,
            }
        )

    @rt("/api/askesis/learning-steps")
    @boundary_handler()
    async def get_optimal_learning_steps_route(request: Request, askesis_uid: str) -> Result[Any]:
        """
        Determine what to learn next based on ALL factors.

        **Synthesizes:**
        - KU service: get_ready_to_learn_for_user() - Prerequisites met
        - Goals service: Goal alignment
        - Tasks service: Knowledge application opportunities
        - Context: Capacity, energy, life path alignment

        **Ranking Factors:**
        - Prerequisites met (ready to learn)
        - Goal alignment (helps achieve goals)
        - User capacity (fits available time)
        - Life path alignment (flows toward ultimate path)
        - Unblocking potential (unlocks other items)

        Query Parameters:
            max_steps (int): Maximum number of steps to return (default: 5)
            consider_goals (bool): Weight by goal alignment (default: true)
            consider_capacity (bool): Respect user capacity limits (default: true)

        Returns:
            Result[list[LearningStep]]: Ranked list with:
                - ku_uid, title, rationale
                - prerequisites_met, aligns_with_goals
                - unlocks_count, estimated_time_minutes
                - priority_score, application_opportunities
        """
        params = dict(request.query_params)

        max_steps = int(params.get("max_steps", "5"))
        consider_goals = params.get("consider_goals", "true").lower() == "true"
        consider_capacity = params.get("consider_capacity", "true").lower() == "true"

        if not _askesis_service or not _askesis_core_service:
            return Result.fail(
                Errors.system(
                    message="Askesis services not available",
                    operation="get_optimal_learning_steps",
                )
            )

        # Get user UID from askesis instance
        askesis_result = await _askesis_core_service.get_askesis(askesis_uid)
        if askesis_result.is_error:
            return askesis_result

        askesis = askesis_result.value
        user_uid = askesis.user_uid

        # Get user context
        from core.services.user.user_context_builder import UserContextBuilder

        if not driver:
            return Result.fail(
                Errors.system(
                    message="Driver not available for context building",
                    operation="generate_guidance",
                )
            )
        context_builder = UserContextBuilder(driver)
        context_result = await context_builder.build(user_uid)

        if context_result.is_error:
            return Result.fail(context_result.expect_error())

        user_context = context_result.value

        # Get optimal learning steps using 13-domain intelligence
        steps_result = await _askesis_service.get_optimal_next_learning_steps(
            user_context,
            max_steps=max_steps,
            consider_goals=consider_goals,
            consider_capacity=consider_capacity,
        )

        if steps_result.is_error:
            return Result.fail(steps_result.expect_error())

        steps = steps_result.value

        # Convert dataclass list to dict list for JSON response
        return Result.ok(
            {
                "learning_steps": [
                    {
                        "ku_uid": step.ku_uid,
                        "title": step.title,
                        "rationale": step.rationale,
                        "prerequisites_met": step.prerequisites_met,
                        "aligns_with_goals": step.aligns_with_goals,
                        "unlocks_count": step.unlocks_count,
                        "estimated_time_minutes": step.estimated_time_minutes,
                        "priority_score": step.priority_score,
                        "application_opportunities": step.application_opportunities,
                    }
                    for step in steps
                ],
                "user_uid": user_uid,
                "askesis_uid": askesis_uid,
                "total_steps": len(steps),
            }
        )

    @rt("/api/askesis/critical-path")
    @boundary_handler()
    async def get_learning_critical_path_route(request: Request, askesis_uid: str) -> Result[Any]:
        """
        What's the fastest route to life path alignment?

        **Synthesizes:**
        - LP service: Learning path structure
        - KU service: Prerequisite chains
        - Context: Current mastery levels

        Returns:
            Result[list[str]]: Ordered list of KU UIDs representing critical path
        """

        if not _askesis_service or not _askesis_core_service:
            return Result.fail(
                Errors.system(
                    message="Askesis services not available",
                    operation="get_learning_critical_path",
                )
            )

        # Get user UID from askesis instance
        askesis_result = await _askesis_core_service.get_askesis(askesis_uid)
        if askesis_result.is_error:
            return askesis_result

        askesis = askesis_result.value
        user_uid = askesis.user_uid

        # Get user context
        from core.services.user.user_context_builder import UserContextBuilder

        if not driver:
            return Result.fail(
                Errors.system(
                    message="Driver not available for context building",
                    operation="generate_guidance",
                )
            )
        context_builder = UserContextBuilder(driver)
        context_result = await context_builder.build(user_uid)

        if context_result.is_error:
            return Result.fail(context_result.expect_error())

        user_context = context_result.value

        # Get critical path using 13-domain intelligence
        path_result = await _askesis_service.get_learning_path_critical_path(user_context)

        if path_result.is_error:
            return Result.fail(path_result.expect_error())

        critical_path = path_result.value

        return Result.ok(
            {
                "critical_path": critical_path,
                "total_steps": len(critical_path),
                "user_uid": user_uid,
                "askesis_uid": askesis_uid,
            }
        )

    @rt("/api/askesis/unblocking-order")
    @boundary_handler()
    async def get_unblocking_priority_route(request: Request, askesis_uid: str) -> Result[Any]:
        """
        What should I learn first to unlock the most items?

        **Synthesizes:**
        - Context: prerequisites_needed mapping
        - KU service: Readiness status
        - Tasks service: Blocked task counts

        Returns:
            Result[list[tuple[str, int]]]: List of (ku_uid, blocked_count) sorted by impact
        """

        if not _askesis_service or not _askesis_core_service:
            return Result.fail(
                Errors.system(
                    message="Askesis services not available",
                    operation="get_unblocking_priority",
                )
            )

        # Get user UID from askesis instance
        askesis_result = await _askesis_core_service.get_askesis(askesis_uid)
        if askesis_result.is_error:
            return askesis_result

        askesis = askesis_result.value
        user_uid = askesis.user_uid

        # Get user context
        from core.services.user.user_context_builder import UserContextBuilder

        if not driver:
            return Result.fail(
                Errors.system(
                    message="Driver not available for context building",
                    operation="generate_guidance",
                )
            )
        context_builder = UserContextBuilder(driver)
        context_result = await context_builder.build(user_uid)

        if context_result.is_error:
            return Result.fail(context_result.expect_error())

        user_context = context_result.value

        # Get unblocking priority order using 13-domain intelligence
        order_result = await _askesis_service.get_unblocking_priority_order(user_context)

        if order_result.is_error:
            return Result.fail(order_result.expect_error())

        unblocking_order = order_result.value

        return Result.ok(
            {
                "unblocking_order": [
                    {"ku_uid": ku_uid, "blocked_count": count} for ku_uid, count in unblocking_order
                ],
                "total_blockers": len(unblocking_order),
                "user_uid": user_uid,
                "askesis_uid": askesis_uid,
            }
        )

    # =========================================================================
    # PHASE 2: Cross-Domain Synergies (Habit→Goal, Task→Habit, etc.)
    # =========================================================================

    @rt("/api/askesis/synergies")
    @boundary_handler()
    async def get_cross_domain_synergies_route(request: Request, askesis_uid: str) -> Result[Any]:
        """
        Detect synergies between entities across different domains.

        **Phase 2 Addition:** Cross-domain correlation for habit→goal synergies
        and other high-leverage connections.

        **Synergy Types Detected:**
        1. habit_goal: Habits supporting multiple goals (high leverage)
        2. task_habit: Tasks that build habits (behavior change)
        3. knowledge_task: Knowledge enabling tasks (skill application)
        4. principle_goal: Principles guiding goal pursuit (value alignment)
        5. goal_learning: Goals requiring specific knowledge (learning gaps)

        **Query Parameters:**
        - min_score: Minimum synergy score (0.0-1.0, default 0.3)
        - types: Comma-separated synergy types to include (default: all)

        Returns:
            Result containing synergies sorted by score (highest first)
        """

        # Parse query parameters
        min_score = float(request.query_params.get("min_score", "0.3"))
        types_param = request.query_params.get("types", "")
        include_types = types_param.split(",") if types_param else None

        if not _askesis_service or not _askesis_core_service:
            return Result.fail(
                Errors.system(
                    message="Askesis services not available",
                    operation="get_cross_domain_synergies",
                )
            )

        # Get user UID from askesis instance
        askesis_result = await _askesis_core_service.get_askesis(askesis_uid)
        if askesis_result.is_error:
            return askesis_result

        askesis = askesis_result.value
        user_uid = askesis.user_uid

        # Get user context
        from core.services.user.user_context_builder import UserContextBuilder

        if not driver:
            return Result.fail(
                Errors.system(
                    message="Driver not available for context building",
                    operation="generate_guidance",
                )
            )
        context_builder = UserContextBuilder(driver)
        context_result = await context_builder.build(user_uid)

        if context_result.is_error:
            return Result.fail(context_result.expect_error())

        user_context = context_result.value

        # Get cross-domain synergies using 13-domain intelligence
        synergies_result = await _askesis_service.get_cross_domain_synergies(
            user_context,
            min_synergy_score=min_score,
            include_types=include_types,
        )

        if synergies_result.is_error:
            return Result.fail(synergies_result.expect_error())

        synergies = synergies_result.value

        # Convert to JSON-serializable format
        from dataclasses import asdict

        return Result.ok(
            {
                "synergies": [asdict(s) for s in synergies],
                "total_synergies": len(synergies),
                "synergy_types": list(set(s.synergy_type for s in synergies)),
                "high_leverage_count": len([s for s in synergies if s.synergy_score >= 0.7]),
                "user_uid": user_uid,
                "askesis_uid": askesis_uid,
                "filter_params": {
                    "min_score": min_score,
                    "include_types": include_types,
                },
            }
        )

    # =========================================================================
    # PHASE 3: Life Path Alignment Scoring
    # =========================================================================

    @rt("/api/askesis/life-path-alignment")
    @boundary_handler()
    async def get_life_path_alignment_route(request: Request, askesis_uid: str) -> Result[Any]:
        """
        Calculate comprehensive life path alignment score.

        **Phase 3 Addition:** 5-dimensional alignment scoring showing how well
        the user's current activities align with their life path.

        **5 Dimensions (Weighted):**
        1. Knowledge Score (25%): Mastery of life path-relevant knowledge
        2. Activity Score (25%): Tasks/habits aligned with life path
        3. Goal Score (20%): Goal alignment with life path milestones
        4. Principle Score (15%): Values alignment
        5. Momentum Score (15%): Recent progress and trajectory

        **Alignment Levels:**
        - "drifting" (0.0-0.3): Minimal alignment, need course correction
        - "exploring" (0.3-0.5): Some alignment, finding direction
        - "aligned" (0.5-0.7): Good alignment, on track
        - "flourishing" (0.7-1.0): Strong alignment, thriving

        Returns:
            Result containing:
                - overall_score: 0.0-1.0
                - alignment_level: "drifting" | "exploring" | "aligned" | "flourishing"
                - dimension scores (knowledge, activity, goal, principle, momentum)
                - strengths, gaps, recommendations
                - life_path_milestones_completed / total
                - aligned_goals, supporting_habits, knowledge_gaps
        """

        if not _askesis_service or not _askesis_core_service:
            return Result.fail(
                Errors.system(
                    message="Askesis services not available",
                    operation="get_life_path_alignment",
                )
            )

        # Get user UID from askesis instance
        askesis_result = await _askesis_core_service.get_askesis(askesis_uid)
        if askesis_result.is_error:
            return askesis_result

        askesis = askesis_result.value
        user_uid = askesis.user_uid

        # Get user context
        from core.services.user.user_context_builder import UserContextBuilder

        if not driver:
            return Result.fail(
                Errors.system(
                    message="Driver not available for context building",
                    operation="generate_guidance",
                )
            )
        context_builder = UserContextBuilder(driver)
        context_result = await context_builder.build(user_uid)

        if context_result.is_error:
            return Result.fail(context_result.expect_error())

        user_context = context_result.value

        # Calculate life path alignment using 13-domain intelligence
        alignment_result = await _askesis_service.calculate_life_path_alignment(
            user_context,
        )

        if alignment_result.is_error:
            return Result.fail(alignment_result.expect_error())

        alignment = alignment_result.value

        # Convert to JSON-serializable format
        from dataclasses import asdict

        return Result.ok(
            {
                "life_path_alignment": asdict(alignment),
                "summary": {
                    "overall_score": alignment.overall_score,
                    "alignment_level": alignment.alignment_level,
                    "milestones": f"{alignment.life_path_milestones_completed}/{alignment.life_path_milestones_total}",
                    "top_strength": alignment.strengths[0] if alignment.strengths else None,
                    "critical_gap": alignment.gaps[0] if alignment.gaps else None,
                },
                "user_uid": user_uid,
                "askesis_uid": askesis_uid,
            }
        )

    # =========================================================================
    # PHASE 4: Schedule-Aware Recommendations
    # =========================================================================

    @rt("/api/askesis/schedule-recommendations")
    @boundary_handler()
    async def get_schedule_aware_recommendations_route(
        request: Request, askesis_uid: str
    ) -> Result[Any]:
        """
        Get recommendations that consider the user's schedule and capacity.

        **Phase 4 Addition:** Schedule-aware intelligence that provides:
        - Time-optimal recommendations based on available slots
        - Energy-matched suggestions
        - Priority-ranked actions across all domains
        - Rest recommendations when capacity is exceeded

        **Recommendation Types:**
        - "learn": Knowledge unit to study (best in morning)
        - "task": Task to complete (flexible timing)
        - "habit": Habit to maintain (protect streaks)
        - "goal": Goal to advance (focused time blocks)
        - "rest": Rest recommendation (capacity exceeded)
        - "reschedule": Reschedule suggestion for conflicts

        **Query Parameters:**
        - max_recommendations: Maximum number to return (default: 5)
        - time_horizon_hours: How far ahead to look (default: 8)
        - respect_energy: Consider current energy level (default: true)

        **Scoring Weights:**
        - Priority: 40%
        - Schedule Fit: 35%
        - Energy Match: 25%

        Returns:
            Result containing:
                - recommendations: List of ScheduleAwareRecommendation
                - summary: Quick overview (top recommendation, total count)
                - schedule_context: Available time, current energy, time slot
        """

        # Parse query parameters
        max_recommendations = int(request.query_params.get("max_recommendations", "5"))
        time_horizon_hours = int(request.query_params.get("time_horizon_hours", "8"))
        respect_energy = request.query_params.get("respect_energy", "true").lower() == "true"

        if not _askesis_service or not _askesis_core_service:
            return Result.fail(
                Errors.system(
                    message="Askesis services not available",
                    operation="get_schedule_aware_recommendations",
                )
            )

        # Get user UID from askesis instance
        askesis_result = await _askesis_core_service.get_askesis(askesis_uid)
        if askesis_result.is_error:
            return askesis_result

        askesis = askesis_result.value
        user_uid = askesis.user_uid

        # Get user context
        from core.services.user.user_context_builder import UserContextBuilder

        if not driver:
            return Result.fail(
                Errors.system(
                    message="Driver not available for context building",
                    operation="generate_guidance",
                )
            )
        context_builder = UserContextBuilder(driver)
        context_result = await context_builder.build(user_uid)

        if context_result.is_error:
            return Result.fail(context_result.expect_error())

        user_context = context_result.value

        # Get schedule-aware recommendations using 13-domain intelligence
        recommendations_result = await _askesis_service.get_schedule_aware_recommendations(
            user_context,
            max_recommendations=max_recommendations,
            time_horizon_hours=time_horizon_hours,
            respect_energy=respect_energy,
        )

        if recommendations_result.is_error:
            return Result.fail(recommendations_result.expect_error())

        recommendations = recommendations_result.value

        # Convert to JSON-serializable format
        from dataclasses import asdict

        return Result.ok(
            {
                "recommendations": [asdict(r) for r in recommendations],
                "total_recommendations": len(recommendations),
                "summary": {
                    "top_recommendation": asdict(recommendations[0]) if recommendations else None,
                    "recommendation_types": list(
                        set(r.recommendation_type for r in recommendations)
                    ),
                    "has_rest_recommendation": any(
                        r.recommendation_type == "rest" for r in recommendations
                    ),
                    "high_priority_count": len(
                        [r for r in recommendations if r.priority_score >= 0.7]
                    ),
                },
                "schedule_context": {
                    "time_horizon_hours": time_horizon_hours,
                    "respect_energy": respect_energy,
                    "current_workload": user_context.current_workload_score,
                    "available_minutes": user_context.available_minutes_daily,
                    "today_events": len(user_context.today_event_uids),
                },
                "user_uid": user_uid,
                "askesis_uid": askesis_uid,
            }
        )

    logger.info(
        "✅ Askesis API routes registered (service-based architecture + 13-domain intelligence + Phase 2-4)"
    )
    return []  # Routes registered via @rt() decorators (no objects returned)


# Export the route creation function
__all__ = ["create_askesis_api_routes"]


# Migration Statistics:
# =====================
# Before (askesis_api.py):     577 lines (mock data, custom response helpers)
# After (askesis_api_migrated): ~280 lines (boundary_handler, Pydantic validation)
# Reduction:                    ~297 lines (51% reduction)
#
# Note: This API is 100% domain-specific (no CRUD pattern), so CRUDRouteFactory
# is not applicable. Migration focuses on:
# 1. Removed custom success_response() and error_response() helpers
# 2. All routes now use @boundary_handler for consistent response handling
# 3. Added Pydantic validation for all request bodies
# 4. Removed all mock data responses
# 5. Added proper HTTP status codes (201 for POST creates)
# 6. Prepared for service integration with TODOs
#
# Routes Summary (10 routes):
# 1. GET  /api/askesis/{user_uid} - Get Askesis instance
# 2. POST /api/askesis - Create Askesis instance
# 3. PUT  /api/askesis/{askesis_uid} - Update settings
# 4. POST /api/askesis/{askesis_uid}/conversations - Start conversation
# 5. POST /api/askesis/conversations/{conversation_uid}/messages - Send message
# 6. GET  /api/askesis/conversations/{conversation_uid} - Get conversation
# 7. POST /api/askesis/{askesis_uid}/guidance - Generate guidance
# 8. GET  /api/askesis/{askesis_uid}/insights - Get AI insights
# 9. POST /api/askesis/{askesis_uid}/domain-integration - Domain integration
# 10. GET /api/askesis/{askesis_uid}/analytics - Get analytics
# 11. POST /api/askesis/suggestions - Domain suggestions
# 12. POST /api/askesis/{askesis_uid}/intelligence - Update intelligence
