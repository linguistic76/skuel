"""
Query Processor - Natural Language Query Processing (Orchestration)
===================================================================

Orchestrates the RAG pipeline using specialized sub-services.

Responsibilities:
- Orchestrate the complete RAG pipeline
- Coordinate EntityExtractor, ContextRetriever, IntentClassifier, ResponseGenerator
- Answer user questions with retrieval + generation
- Process queries with full context
- LP enrollment gate — Askesis works within enrolled Learning Paths

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
- All dependencies required — no fallbacks or degraded modes

January 2026: Refactored to use IntentClassifier and ResponseGenerator
for single responsibility and reduced file size (962 -> ~500 lines).
March 2026: Removed all fallback/template paths — works or fails.
March 2026: Absorbed Socratic pipeline into main RAG pipeline.
LP enrollment gate. ZPD + GuidanceMode wired into answer flow.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.constants import QueryProcessorConfidence
from core.models.query_types import QueryIntent
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.zpd_protocols import ZPDOperations
    from core.services.askesis.context_retriever import ContextRetriever
    from core.services.askesis.entity_extractor import EntityExtractor
    from core.services.askesis.intent_classifier import IntentClassifier
    from core.services.askesis.response_generator import ResponseGenerator
    from core.services.askesis_citation_service import AskesisCitationService
    from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
    from core.services.llm_service import LLMService
    from core.services.user_service import UserService

logger = get_logger(__name__)


# Enrollment gate response — returned when user has no enrolled Learning Paths.
_ENROLLMENT_GATE_RESPONSE: dict[str, Any] = {
    "answer": "Askesis works within your Learning Path. Enroll in a Learning Path to begin.",
    "context_used": {},
    "suggested_actions": [
        {"action": "enroll_learning_path", "description": "Browse available Learning Paths"}
    ],
    "confidence": 1.0,
    "mode": "enrollment_gate",
}


class QueryProcessor:
    """
    Orchestrate the RAG pipeline for answering user questions.

    Implements: AskesisQueryOperations protocol (structural typing)

    This service handles query processing orchestration:
    - Answer user questions (complete RAG pipeline)
    - Process queries with context
    - Coordinate sub-services for intent, entities, context, response
    - LP enrollment gate — requires enrolled Learning Paths

    Architecture:
    - Orchestrates IntentClassifier for intent classification
    - Orchestrates ResponseGenerator for action/context generation
    - Orchestrates EntityExtractor for entity extraction
    - Orchestrates ContextRetriever for context retrieval
    - Requires LLMService for natural language generation
    - Uses QueryProcessorConfidence for dynamic confidence scoring
    - Uses ZPDService for targeted KU readiness assessment

    January 2026: Refactored to use IntentClassifier and ResponseGenerator
    for single responsibility and reduced complexity.
    March 2026: Absorbed Socratic pipeline. LP enrollment gate.
    """

    def __init__(
        self,
        intent_classifier: IntentClassifier,
        response_generator: ResponseGenerator,
        entity_extractor: EntityExtractor,
        context_retriever: ContextRetriever,
        user_service: UserService,
        llm_service: LLMService,
        graph_intelligence_service: GraphIntelligenceService,
        zpd_service: ZPDOperations,
        citation_service: AskesisCitationService | None = None,
    ) -> None:
        """
        Initialize query processor.

        Args:
            intent_classifier: IntentClassifier for query intent classification
            response_generator: ResponseGenerator for action/context/prompt generation
            entity_extractor: EntityExtractor for entity extraction
            context_retriever: ContextRetriever for context retrieval and LS bundle loading
            user_service: UserService for accessing UserContext
            llm_service: LLMService for natural language generation
            graph_intelligence_service: GraphIntelligenceService for graph intelligence queries
            zpd_service: ZPDService for targeted KU readiness assessment
            citation_service: AskesisCitationService for source and evidence transparency (optional)
        """
        self.intent_classifier = intent_classifier
        self.response_generator = response_generator
        self.entity_extractor = entity_extractor
        self.context_retriever = context_retriever
        self.user_service = user_service
        self.llm_service = llm_service
        self.graph_intel = graph_intelligence_service
        self.zpd_service = zpd_service
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

        When an LS bundle is available, the pipeline uses ZPD evidence and
        GuidanceMode to produce a pedagogically appropriate response.

        Args:
            user_uid: User's unique identifier
            question: Natural language question from user

        Returns:
            Result containing:
            - answer: Natural language response
            - context_used: Relevant entities from user's data
            - suggested_actions: Next steps user can take
            - confidence: Confidence score (0.0-1.0)
            - guidance_mode: GuidanceMode used for guided response (if LS bundle available)
        """
        # Step 1: Get full user context
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

        # Step 2: LP enrollment gate
        if not user_context.enrolled_path_uids:
            return Result.ok(_ENROLLMENT_GATE_RESPONSE)

        # Step 3: Classify query intent
        intent_result = await self.intent_classifier.classify_intent(question)
        if intent_result.is_error:
            return Result.fail(
                Errors.system(
                    message=f"Intent classification failed: {intent_result.error}",
                    operation="answer_user_question",
                    user_message="Unable to understand your question. Please try rephrasing.",
                )
            )
        intent = intent_result.value

        # Step 4: Extract entities mentioned in query
        extracted_entities = await self.entity_extractor.extract_entities_from_query(
            question, user_context
        )

        # Step 5: Retrieve relevant entities based on intent
        relevant_context = await self.context_retriever.retrieve_relevant_context(
            user_context, question, intent
        )

        # Add extracted entities to context
        if any(extracted_entities.values()):
            relevant_context["mentioned_entities"] = extracted_entities

        # Step 6: Check for LS bundle and apply guided pipeline if available
        guided_system_prompt: str | None = None
        guidance_mode: str | None = None
        ls_bundle = None

        bundle_result = await self.context_retriever.load_ls_bundle(user_uid, user_context)
        if not bundle_result.is_error:
            ls_bundle = bundle_result.value

            # Get target KU UIDs from question (scoped to bundle)
            target_ku_uids = self.entity_extractor.extract_from_bundle(question, ls_bundle)

            # Get ZPD evidence for target KUs (empty dict if no KUs matched)
            zone_evidence: dict[str, Any] = {}
            if target_ku_uids:
                zpd_result = await self.zpd_service.assess_ku_readiness(user_uid, target_ku_uids)
                if not zpd_result.is_error:
                    zone_evidence = zpd_result.value

            # Determine guidance mode — works even when target_ku_uids is empty
            # (classify_pedagogical_intent returns OUT_OF_SCOPE or ENCOURAGE_PRACTICE)
            guidance = self.intent_classifier.determine_guidance_mode(
                question, ls_bundle, zone_evidence, target_ku_uids
            )

            # Build guided system prompt
            guided_system_prompt = self.response_generator.build_guided_system_prompt(
                guidance, ls_bundle, user_context
            )
            guidance_mode = guidance.mode.value

        # Step 7: Build LLM-friendly context and generate answer
        llm_context = self.response_generator.build_llm_context(
            user_context, question, intent, ls_bundle=ls_bundle
        )

        # Step 8: Generate natural language answer using LLM
        if guided_system_prompt:
            # Use guided pipeline with Socratic system prompt
            user_prompt = question
            if ls_bundle and ls_bundle.curriculum_context_text:
                user_prompt = (
                    f"=== CURRICULUM CONTEXT (for your reference, do NOT share directly) ===\n"
                    f"{ls_bundle.curriculum_context_text}\n\n"
                    f"=== LEARNER'S MESSAGE ===\n{question}"
                )

            llm_response = await self.llm_service.generate(
                prompt=user_prompt,
                system_prompt=guided_system_prompt,
                temperature=0.7,
                max_tokens=500,
            )
            answer = llm_response.content or (
                "I'd like to explore this with you, but I'm having trouble "
                "formulating my response. Could you rephrase your question?"
            )
        else:
            answer = await self.llm_service.generate_context_aware_answer(
                query=question,
                user_context=llm_context,
                additional_context=relevant_context,
                intent=intent,
            )

        # Step 9: Generate suggested actions
        suggested_actions = self.response_generator.generate_actions(
            user_context, intent, relevant_context
        )

        # Step 10: Add citations for knowledge units
        citations_text = ""
        if intent in (QueryIntent.PREREQUISITE, QueryIntent.HIERARCHICAL):
            knowledge_entities = extracted_entities.get("knowledge", [])
            if knowledge_entities:
                knowledge_uids = [ku.get("uid") for ku in knowledge_entities if ku.get("uid")]
                citations_text = await self._retrieve_citations_for_knowledge_units(
                    knowledge_uids, min_evidence_count=1
                )

        # Step 11: Package response with calculated confidence
        final_answer = answer + citations_text if citations_text else answer
        confidence = QueryProcessorConfidence.calculate(
            has_context=bool(relevant_context),
            has_citations=bool(citations_text),
            has_entities=any(extracted_entities.values()),
        )
        response: dict[str, Any] = {
            "answer": final_answer,
            "context_used": relevant_context,
            "suggested_actions": suggested_actions,
            "confidence": confidence,
            "mode": "guided" if guided_system_prompt else "llm_generated",
            "has_citations": bool(citations_text),
        }

        if guidance_mode:
            response["guidance_mode"] = guidance_mode

        logger.info(
            "Generated answer for user %s question: %s (intent: %s, citations: %s, guidance: %s)",
            user_uid,
            question[:50],
            intent.value,
            "yes" if citations_text else "no",
            guidance_mode or "none",
        )

        return Result.ok(response)

    @with_error_handling("process_query_with_context", error_type="system", uid_param="user_uid")
    async def process_query_with_context(
        self, user_uid: str, query_message: str, depth: int = 2
    ) -> Result[dict[str, Any]]:
        """
        Process Askesis query with full user context.

        LP-scoped, ZPD-informed pipeline. Retrieves complete user learning
        context in a single Pure Cypher query and generates personalized,
        GuidanceMode-aware responses.

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
                "suggested_actions": list[dict[str, Any]],
                "guidance_mode": str | None
            }
        """
        # LP enrollment gate: load user context to check enrollment
        user_context_result = await self.user_service.get_rich_unified_context(user_uid)
        if user_context_result.is_error:
            error = user_context_result.expect_error()
            return Result.fail(
                Errors.system(
                    message=f"User context retrieval failed: {error.message}",
                    operation="process_query_with_context",
                    user_message="Unable to load your learning data. Please try again shortly.",
                )
            )

        user_context = user_context_result.value
        if not user_context.enrolled_path_uids:
            return Result.ok(_ENROLLMENT_GATE_RESPONSE)

        # Step 1: Get complete learning context in single query
        context_result = await self.context_retriever.get_learning_context(user_uid, depth)

        if context_result.is_error:
            return context_result

        context_data = context_result.value

        # Step 2: Determine query intent
        intent_result = await self.intent_classifier.classify_intent(query_message)
        if intent_result.is_error:
            return Result.fail(
                Errors.system(
                    message=f"Intent classification failed: {intent_result.error}",
                    operation="process_query_with_context",
                    user_message="Unable to understand your question. Please try rephrasing.",
                )
            )
        intent = intent_result.value

        # Extract context nodes
        current_knowledge = context_data["knowledge_units"]
        active_learning = context_data["learning_paths"]
        active_tasks = context_data["related_tasks"]
        related_goals = context_data.get("related_goals", [])

        # Step 3: Load LS bundle and apply guided pipeline if available
        guided_system_prompt: str | None = None
        guidance_mode: str | None = None

        bundle_result = await self.context_retriever.load_ls_bundle(user_uid, user_context)
        if not bundle_result.is_error:
            ls_bundle = bundle_result.value
            target_ku_uids = self.entity_extractor.extract_from_bundle(query_message, ls_bundle)

            # Get ZPD evidence for target KUs (empty dict if no KUs matched)
            zone_evidence: dict[str, Any] = {}
            if target_ku_uids:
                zpd_result = await self.zpd_service.assess_ku_readiness(user_uid, target_ku_uids)
                if not zpd_result.is_error:
                    zone_evidence = zpd_result.value

            # Determine guidance mode — works even when target_ku_uids is empty
            guidance = self.intent_classifier.determine_guidance_mode(
                query_message, ls_bundle, zone_evidence, target_ku_uids
            )
            guided_system_prompt = self.response_generator.build_guided_system_prompt(
                guidance, ls_bundle, user_context
            )
            guidance_mode = guidance.mode.value

        # Step 4: Generate AI response
        if guided_system_prompt:
            ls_bundle = bundle_result.value
            user_prompt = query_message
            if ls_bundle.curriculum_context_text:
                user_prompt = (
                    f"=== CURRICULUM CONTEXT (for your reference, do NOT share directly) ===\n"
                    f"{ls_bundle.curriculum_context_text}\n\n"
                    f"=== LEARNER'S MESSAGE ===\n{query_message}"
                )

            llm_response = await self.llm_service.generate(
                prompt=user_prompt,
                system_prompt=guided_system_prompt,
                temperature=0.7,
                max_tokens=500,
            )
            response = llm_response.content or (
                "I'd like to explore this with you, but I'm having trouble "
                "formulating my response. Could you rephrase your question?"
            )
        else:
            response = await self._generate_context_aware_response(
                query_message=query_message,
                current_knowledge=current_knowledge,
                active_learning=active_learning,
                active_tasks=active_tasks,
                related_goals=related_goals,
                intent=intent,
            )

        # Step 5: Generate suggested actions
        suggested_actions = self.response_generator.generate_suggested_actions(
            query_message, context_data, intent
        )

        # Step 6: Build and return result
        result_dict = self._build_query_response_result(
            response,
            current_knowledge,
            active_learning,
            active_tasks,
            related_goals,
            intent,
            suggested_actions,
        )

        if guidance_mode:
            result_dict["guidance_mode"] = guidance_mode

        return Result.ok(result_dict)

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

        return await self.llm_service.generate_context_aware_answer(
            query=query_message,
            user_context=context,
            additional_context=additional_context,
            intent=intent,
        )

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

        Args:
            knowledge_uids: List of knowledge unit UIDs mentioned in response
            min_evidence_count: Minimum evidence items to include (default: 1)

        Returns:
            Formatted citation text ready for appending to response
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
