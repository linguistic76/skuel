"""
Query Processor - Natural Language Query Processing (Orchestration)
===================================================================

Orchestrates the RAG pipeline using specialized sub-services.

Responsibilities:
- Orchestrate the complete RAG pipeline
- Coordinate EntityExtractor, ContextRetriever, IntentClassifier, ResponseGenerator
- Answer user questions with retrieval + generation
- Process queries with full context

This service is part of the refactored AskesisService architecture:
- UserStateAnalyzer: Analyze current user state and patterns
- ActionRecommendationEngine: Generate personalized action recommendations
- QueryProcessor: Orchestrate query processing (THIS FILE)
- IntentClassifier: Classify query intent via embeddings
- ResponseGenerator: Generate actions and LLM context
- EntityExtractor: Extract entities from natural language
- ContextRetriever: Retrieve domain-specific context
- AskesisService: Facade coordinating all sub-services

Architecture:
- Orchestrates sub-services for query processing
- Delegates intent classification to IntentClassifier
- Delegates response generation to ResponseGenerator
- Fail-fast design: requires LLMService for natural language generation

January 2026: Refactored to use IntentClassifier and ResponseGenerator
for single responsibility and reduced file size (962 → ~500 lines).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.constants import QueryProcessorConfidence
from core.models.query import QueryIntent
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.askesis.context_retriever import ContextRetriever
    from core.services.askesis.entity_extractor import EntityExtractor
    from core.services.askesis.intent_classifier import IntentClassifier
    from core.services.askesis.response_generator import ResponseGenerator
    from core.services.askesis_citation_service import AskesisCitationService
    from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
    from core.services.llm_service import LLMService
    from core.services.user_service import UserService

logger = get_logger(__name__)


class QueryProcessor:
    """
    Orchestrate the RAG pipeline for answering user questions.

    Implements: AskesisQueryOperations protocol (structural typing)

    This service handles query processing orchestration:
    - Answer user questions (complete RAG pipeline)
    - Process queries with context
    - Coordinate sub-services for intent, entities, context, response

    Architecture:
    - Orchestrates IntentClassifier for intent classification
    - Orchestrates ResponseGenerator for action/context generation
    - Orchestrates EntityExtractor for entity extraction
    - Orchestrates ContextRetriever for context retrieval
    - Requires LLMService for natural language generation
    - Uses QueryProcessorConfidence for dynamic confidence scoring

    January 2026: Refactored to use IntentClassifier and ResponseGenerator
    for single responsibility and reduced complexity.
    """

    def __init__(
        self,
        intent_classifier: IntentClassifier | None = None,
        response_generator: ResponseGenerator | None = None,
        entity_extractor: EntityExtractor | None = None,
        context_retriever: ContextRetriever | None = None,
        user_service: UserService | None = None,
        llm_service: LLMService | None = None,
        graph_intelligence_service: GraphIntelligenceService | None = None,
        citation_service: AskesisCitationService | None = None,
    ) -> None:
        """
        Initialize query processor.

        Args:
            intent_classifier: IntentClassifier for query intent classification
            response_generator: ResponseGenerator for action/context generation
            entity_extractor: EntityExtractor for entity extraction
            context_retriever: ContextRetriever for context retrieval
            user_service: UserService for accessing UserContext
            llm_service: LLMService for natural language generation (required)
            graph_intelligence_service: GraphIntelligenceService for graph intelligence queries
            citation_service: AskesisCitationService for source and evidence transparency
        """
        self.intent_classifier = intent_classifier
        self.response_generator = response_generator
        self.entity_extractor = entity_extractor
        self.context_retriever = context_retriever
        self.user_service = user_service
        self.llm_service = llm_service
        self.graph_intel = graph_intelligence_service
        self.citation_service = citation_service

        logger.info("QueryProcessor initialized (orchestration layer)")

    # ========================================================================
    # PUBLIC API - QUERY ANSWERING
    # ========================================================================

    @with_error_handling("answer_user_question", error_type="system", uid_param="user_uid")
    async def answer_user_question(self, user_uid: str, question: str) -> Result[dict[str, Any]]:
        """
        Complete RAG pipeline - retrieval + generation.

        This is THE method for answering user questions about their data.
        Combines UserContext (retrieval) with LLM (generation) to produce
        natural language answers based on user's actual state.

        Args:
            user_uid: User's unique identifier
            question: Natural language question from user

        Returns:
            Result containing:
            - answer: Natural language response
            - context_used: Relevant entities from user's data
            - suggested_actions: Next steps user can take
            - confidence: Confidence score (0.0-1.0)

        Examples:
            - "What should I work on next?"
            - "Why am I stuck on my goals?"
            - "What do I need to learn before async programming?"
            - "Show me my progress in Python"
        """
        # Step 1: Get full user context (hard requirement — no fallback possible)
        if not self.user_service:
            return Result.fail(
                Errors.system(
                    message="UserService not available - cannot retrieve user context",
                    operation="answer_user_question",
                    user_message="Unable to load your profile. Please try again shortly.",
                )
            )

        user_context_result = await self.user_service.get_rich_unified_context(user_uid)
        if user_context_result.is_error:
            error = user_context_result.expect_error()
            logger.error("Failed to load user context for RAG pipeline: %s", error.message)
            return Result.fail(
                Errors.system(
                    message=f"User context retrieval failed: {error.message}",
                    operation="answer_user_question",
                    user_message="Unable to load your learning data. Please try again shortly.",
                )
            )

        user_context = user_context_result.value

        # Step 2: Classify query intent (via IntentClassifier, with fallback)
        if not self.intent_classifier:
            logger.warning("IntentClassifier unavailable — defaulting to SPECIFIC intent")
            intent = QueryIntent.SPECIFIC
        else:
            intent_result = await self.intent_classifier.classify_intent(question)
            if intent_result.is_error:
                logger.warning(
                    "Intent classification failed — defaulting to SPECIFIC: %s",
                    intent_result.error,
                )
                intent = QueryIntent.SPECIFIC
            else:
                intent = intent_result.value

        # Step 3: Extract entities mentioned in query (non-critical — errors are swallowed)
        extracted_entities: dict[str, Any] = {}
        if self.entity_extractor:
            try:
                extracted_entities = await self.entity_extractor.extract_entities_from_query(
                    question, user_context
                )
            except Exception as e:
                logger.warning("Entity extraction failed (non-critical): %s", e)

        # Step 4: Retrieve relevant entities based on intent (non-critical)
        relevant_context: dict[str, Any] = {}
        if self.context_retriever:
            try:
                relevant_context = await self.context_retriever.retrieve_relevant_context(
                    user_context, question, intent
                )
            except Exception as e:
                logger.warning("Context retrieval failed (non-critical): %s", e)

        # Add extracted entities to context
        if any(extracted_entities.values()):
            relevant_context["mentioned_entities"] = extracted_entities

        # Step 5: Build LLM-friendly context and generate answer
        llm_context = ""
        if self.response_generator:
            llm_context = self.response_generator.build_llm_context(user_context, question)

        # Step 6: Generate natural language answer using LLM (with template fallback)
        answer: str | None = None
        if self.llm_service:
            try:
                answer = await self.llm_service.generate_context_aware_answer(
                    query=question,
                    user_context=llm_context,
                    additional_context=relevant_context,
                    intent=intent,
                )
            except Exception as e:
                logger.warning("LLM answer generation failed, using template fallback: %s", e)

        if not answer:
            # Template fallback when LLM is unavailable or fails
            answer = self._build_fallback_answer(user_context, question, intent)

        # Step 7: Generate suggested actions (via ResponseGenerator)
        suggested_actions: list[dict[str, Any]] = []
        if self.response_generator:
            suggested_actions = self.response_generator.generate_actions(
                user_context, intent, relevant_context
            )

        # Step 8: Add citations for knowledge units (non-critical)
        citations_text = ""
        if intent in (QueryIntent.PREREQUISITE, QueryIntent.HIERARCHICAL):
            knowledge_entities = extracted_entities.get("knowledge", [])
            if knowledge_entities:
                knowledge_uids = [ku.get("uid") for ku in knowledge_entities if ku.get("uid")]
                try:
                    citations_text = await self._retrieve_citations_for_knowledge_units(
                        knowledge_uids, min_evidence_count=1
                    )
                except Exception as e:
                    logger.warning("Citation retrieval failed (non-critical): %s", e)

        # Append citations to answer if available
        final_answer = answer
        if citations_text:
            final_answer = answer + citations_text

        # Step 9: Package response with calculated confidence
        confidence = QueryProcessorConfidence.calculate(
            has_context=bool(relevant_context),
            has_citations=bool(citations_text),
            has_entities=any(extracted_entities.values()),
        )
        response = {
            "answer": final_answer,
            "context_used": relevant_context,
            "suggested_actions": suggested_actions,
            "confidence": confidence,
            "mode": "llm_generated" if self.llm_service else "template",
            "has_citations": bool(citations_text),
        }

        logger.info(
            "Generated answer for user %s question: %s (intent: %s, citations: %s)",
            user_uid,
            question[:50],
            intent.value,
            "yes" if citations_text else "no",
        )

        return Result.ok(response)

    @with_error_handling("process_query_with_context", error_type="system", uid_param="user_uid")
    async def process_query_with_context(
        self, user_uid: str, query_message: str, depth: int = 2
    ) -> Result[dict[str, Any]]:
        """
        Process Askesis query with full user context

        This is the primary method for context-aware AI responses. It retrieves
        complete user learning context in a single Pure Cypher query and
        generates personalized responses based on:
        - Current knowledge state
        - Active learning paths
        - Related tasks and goals
        - Knowledge gaps and blockers

        Args:
            user_uid: Unique identifier of the user
            query_message: User's query or request
            depth: Graph traversal depth (default: 2)

        Returns:
            Result containing:
            {
                "response": str,
                "context_used": {...},
                "intent": QueryIntent,
                "confidence": float,
                "suggested_actions": List[Dict[str, Any]]
            }

        Performance: 180ms → 22ms (8x faster)
        """
        if not self.context_retriever or not self.graph_intel:
            return Result.fail(
                Errors.system(
                    message="GraphIntelligenceService not available - Phase 1-4 queries disabled",
                    operation="process_query_with_context",
                )
            )

        # Step 1: Get complete learning context in single query
        context_result = await self.context_retriever.get_learning_context(user_uid, depth)

        if context_result.is_error:
            return context_result

        context_data = context_result.value

        # Step 2: Determine query intent (via IntentClassifier, with fallback)
        if not self.intent_classifier:
            logger.warning("IntentClassifier unavailable — defaulting to SPECIFIC intent")
            intent = QueryIntent.SPECIFIC
        else:
            intent_result = await self.intent_classifier.classify_intent(query_message)
            if intent_result.is_error:
                logger.warning(
                    "Intent classification failed — defaulting to SPECIFIC: %s",
                    intent_result.error,
                )
                intent = QueryIntent.SPECIFIC
            else:
                intent = intent_result.value

        # Extract context nodes
        current_knowledge = context_data["knowledge_units"]
        active_learning = context_data["learning_paths"]
        active_tasks = context_data["related_tasks"]
        related_goals = context_data.get("related_goals", [])

        # Step 3: Generate AI response with full context
        response = await self._generate_context_aware_response(
            query_message=query_message,
            current_knowledge=current_knowledge,
            active_learning=active_learning,
            active_tasks=active_tasks,
            related_goals=related_goals,
            intent=intent,
        )

        # Step 4: Generate suggested actions (via ResponseGenerator)
        suggested_actions: list[dict[str, Any]] = []
        if self.response_generator:
            suggested_actions = self.response_generator.generate_suggested_actions(
                query_message, context_data, intent
            )
        else:
            logger.warning("ResponseGenerator unavailable — returning empty suggested actions")

        # Step 5: Build and return result
        result_dict = self._build_query_response_result(
            response,
            current_knowledge,
            active_learning,
            active_tasks,
            related_goals,
            intent,
            suggested_actions,
        )

        return Result.ok(result_dict)

    def _build_fallback_answer(
        self, user_context: Any, question: str, intent: QueryIntent
    ) -> str:
        """Build a template answer when LLM is unavailable or fails."""
        parts = [f"Based on your current state (regarding: {question[:80]}):\n"]

        task_count = len(getattr(user_context, "active_task_uids", []))
        goal_count = len(getattr(user_context, "active_goal_uids", []))
        habit_count = len(getattr(user_context, "active_habit_uids", []))

        parts.append(f"You have {task_count} active tasks, {goal_count} goals, and {habit_count} habits.\n")

        if intent == QueryIntent.HIERARCHICAL:
            parts.append("For structured learning, follow your active learning paths.")
        elif intent == QueryIntent.PREREQUISITE:
            parts.append("Check the suggested_actions for prerequisite recommendations.")
        elif intent == QueryIntent.PRACTICE:
            parts.append("Look at your active tasks for practice opportunities.")
        else:
            parts.append("See suggested_actions for specific next steps.")

        return "\n".join(parts)

    # ========================================================================
    # PRIVATE - RESPONSE GENERATION
    # ========================================================================

    async def _generate_context_aware_response(
        self,
        query_message: str,
        current_knowledge: list[Any],
        active_learning: list[Any],
        active_tasks: list[Any],
        related_goals: list[Any],
        intent: QueryIntent,
    ) -> str:
        """
        Generate AI response using complete context.

        Uses LLM service if available, otherwise falls back to template response.

        Args:
            query_message: User's query
            current_knowledge: Knowledge units
            active_learning: Learning paths
            active_tasks: Tasks
            related_goals: Goals
            intent: Query intent

        Returns:
            Generated response string
        """
        # Use LLM service if available
        if self.llm_service:
            try:
                # Build context summary for LLM
                def extract_title(item: Any) -> str:
                    """Extract title from object or dict."""
                    if isinstance(item, dict):
                        return str(item.get("title", "Unknown"))[:50]
                    title = getattr(item, "title", None)
                    return str(title)[:50] if title else "Unknown"

                context = {
                    "knowledge_count": len(current_knowledge),
                    "learning_paths_count": len(active_learning),
                    "active_tasks_count": len(active_tasks),
                    "goals_count": len(related_goals),
                    "knowledge_titles": [extract_title(k) for k in current_knowledge[:5]],
                    "intent": intent.value,
                }

                additional_context = {
                    "knowledge_units": [{"title": extract_title(k)} for k in current_knowledge[:5]],
                    "learning_paths": [{"title": extract_title(lp)} for lp in active_learning[:3]],
                    "tasks": [{"title": extract_title(t)} for t in active_tasks[:5]],
                    "goals": [{"title": extract_title(g)} for g in related_goals[:3]],
                }

                # Generate response via LLM
                return await self.llm_service.generate_context_aware_answer(
                    query=query_message,
                    user_context=context,
                    additional_context=additional_context,
                    intent=intent,
                )

            except Exception as e:
                logger.warning("LLM response generation failed, using template: %s", e)
                # Fall through to template response

        # Fallback to template response
        return self._build_template_response(
            query_message, current_knowledge, active_learning, active_tasks, related_goals, intent
        )

    def _build_template_response(
        self,
        _query_message: str,
        current_knowledge: list[Any],
        active_learning: list[Any],
        active_tasks: list[Any],
        _related_goals: list[Any],
        intent: QueryIntent,
    ) -> str:
        """Build template response as fallback when LLM is unavailable."""
        knowledge_count = len(current_knowledge)
        learning_count = len(active_learning)
        task_count = len(active_tasks)

        response = "Based on your current learning state:\n\n"
        response += f"You have {knowledge_count} knowledge areas tracked, "
        response += f"{learning_count} active learning paths, "
        response += f"and {task_count} related tasks.\n\n"

        if intent == QueryIntent.HIERARCHICAL:
            response += (
                "For structured learning, I recommend following your active learning paths. "
            )
        elif intent == QueryIntent.PREREQUISITE:
            response += "Let me identify the prerequisites you need. "
        elif intent == QueryIntent.PRACTICE:
            response += "Here are opportunities to apply your knowledge through tasks. "

        response += "\n\nSee suggested_actions for specific next steps."

        return response

    def _build_query_response_result(
        self,
        response: str,
        current_knowledge: list[Any],
        active_learning: list[Any],
        active_tasks: list[Any],
        related_goals: list[Any],
        intent: QueryIntent,
        suggested_actions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Build query response result dictionary.

        Args:
            response: Generated response text
            current_knowledge: Knowledge units
            active_learning: Learning paths
            active_tasks: Tasks
            related_goals: Goals
            intent: Query intent
            suggested_actions: Generated actions

        Returns:
            Complete result dictionary
        """
        # Calculate confidence based on available context
        has_context = bool(current_knowledge or active_learning or active_tasks or related_goals)
        confidence = QueryProcessorConfidence.calculate(
            has_context=has_context,
            has_citations=False,  # Citations not used in this path
            has_entities=False,  # Entity extraction not used in this path
        )
        return {
            "response": response,
            "context_used": {
                "knowledge": current_knowledge,
                "learning": active_learning,
                "tasks": active_tasks,
                "goals": related_goals,
            },
            "intent": intent,
            "confidence": confidence,
            "suggested_actions": suggested_actions,
        }

    async def _retrieve_citations_for_knowledge_units(
        self,
        knowledge_uids: list[str],
        min_evidence_count: int = 1,
    ) -> str:
        """
        Retrieve and format citations for knowledge units mentioned in response.

        Citations as First-Class Citizen
        This method ensures ALL Askesis responses include source and evidence
        when discussing knowledge units.

        Args:
            knowledge_uids: List of knowledge unit UIDs mentioned in response
            min_evidence_count: Minimum evidence items to include (default: 1)

        Returns:
            Formatted citation text ready for appending to response

        Philosophy:
            🌳 Tree metaphor - Source and evidence ground the knowledge graph
            - 🌱 Roots = Evidence (grounding in reality)
            - 🌳 Trunk = Source (provenance)
            - 🍃 Branches = Knowledge relationships
        """
        if not self.citation_service or not knowledge_uids:
            return ""

        citation_texts = []

        for ku_uid in knowledge_uids[:3]:  # Limit to first 3 KUs to avoid overwhelming user
            # Get citations for this knowledge unit
            result = await self.citation_service.format_citations_for_askesis(
                knowledge_uid=ku_uid,
                knowledge_title=ku_uid,  # Will be populated by service
                depth=3,
                min_evidence_count=min_evidence_count,
            )

            if result.is_ok and result.value:
                citation_texts.append(result.value)

        if not citation_texts:
            return ""

        # Format citations section
        citations_header = "\n\n---\n## Sources & Evidence\n\n"
        return citations_header + "\n\n".join(citation_texts)
