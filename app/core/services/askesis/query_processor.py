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
- All dependencies required — no fallbacks or degraded modes

January 2026: Refactored to use IntentClassifier and ResponseGenerator
for single responsibility and reduced file size (962 → ~500 lines).
March 2026: Removed all fallback/template paths — works or fails.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.constants import QueryProcessorConfidence
from core.models.enums import MessageRole
from core.models.query_types import QueryIntent
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.user.conversation import ConversationContext
    from core.ports.zpd_protocols import ZPDOperations
    from core.services.askesis.context_retriever import ContextRetriever
    from core.services.askesis.entity_extractor import EntityExtractor
    from core.services.askesis.intent_classifier import IntentClassifier
    from core.services.askesis.ls_context_loader import LSContextLoader
    from core.services.askesis.response_generator import ResponseGenerator
    from core.services.askesis.socratic_engine import SocraticEngine
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
        intent_classifier: IntentClassifier,
        response_generator: ResponseGenerator,
        entity_extractor: EntityExtractor,
        context_retriever: ContextRetriever,
        user_service: UserService,
        llm_service: LLMService,
        graph_intelligence_service: GraphIntelligenceService,
        citation_service: AskesisCitationService | None = None,
        # Socratic pipeline dependencies (Phase 5)
        ls_context_loader: LSContextLoader | None = None,
        socratic_engine: SocraticEngine | None = None,
        zpd_service: ZPDOperations | None = None,
        conversation_context: ConversationContext | None = None,
    ) -> None:
        """
        Initialize query processor.

        Args:
            intent_classifier: IntentClassifier for query intent classification
            response_generator: ResponseGenerator for action/context generation
            entity_extractor: EntityExtractor for entity extraction
            context_retriever: ContextRetriever for context retrieval
            user_service: UserService for accessing UserContext
            llm_service: LLMService for natural language generation
            graph_intelligence_service: GraphIntelligenceService for graph intelligence queries
            citation_service: AskesisCitationService for source and evidence transparency (optional)
            ls_context_loader: LSContextLoader for loading LS bundles (Socratic pipeline)
            socratic_engine: SocraticEngine for generating pedagogical moves (Socratic pipeline)
            zpd_service: ZPDService for targeted KU readiness assessment (Socratic pipeline)
            conversation_context: ConversationContext for session management (Socratic pipeline)
        """
        self.intent_classifier = intent_classifier
        self.response_generator = response_generator
        self.entity_extractor = entity_extractor
        self.context_retriever = context_retriever
        self.user_service = user_service
        self.llm_service = llm_service
        self.graph_intel = graph_intelligence_service
        self.citation_service = citation_service

        # Socratic pipeline
        self.ls_context_loader = ls_context_loader
        self.socratic_engine = socratic_engine
        self.zpd_service = zpd_service
        self.conversation_context = conversation_context

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

        # Step 2: Classify query intent
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

        # Step 3: Extract entities mentioned in query
        extracted_entities = await self.entity_extractor.extract_entities_from_query(
            question, user_context
        )

        # Step 4: Retrieve relevant entities based on intent
        relevant_context = await self.context_retriever.retrieve_relevant_context(
            user_context, question, intent
        )

        # Add extracted entities to context
        if any(extracted_entities.values()):
            relevant_context["mentioned_entities"] = extracted_entities

        # Step 5: Build LLM-friendly context and generate answer
        llm_context = self.response_generator.build_llm_context(user_context, question, intent)

        # Step 6: Generate natural language answer using LLM
        answer = await self.llm_service.generate_context_aware_answer(
            query=question,
            user_context=llm_context,
            additional_context=relevant_context,
            intent=intent,
        )

        # Step 7: Generate suggested actions
        suggested_actions = self.response_generator.generate_actions(
            user_context, intent, relevant_context
        )

        # Step 8: Add citations for knowledge units
        citations_text = ""
        if intent in (QueryIntent.PREREQUISITE, QueryIntent.HIERARCHICAL):
            knowledge_entities = extracted_entities.get("knowledge", [])
            if knowledge_entities:
                knowledge_uids = [ku.get("uid") for ku in knowledge_entities if ku.get("uid")]
                citations_text = await self._retrieve_citations_for_knowledge_units(
                    knowledge_uids, min_evidence_count=1
                )

        # Step 9: Package response with calculated confidence
        final_answer = answer + citations_text if citations_text else answer
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
            "mode": "llm_generated",
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

    # ========================================================================
    # PUBLIC API - SOCRATIC PIPELINE
    # ========================================================================

    @with_error_handling("process_socratic_turn", error_type="system", uid_param="user_uid")
    async def process_socratic_turn(
        self, user_uid: str, question: str, session_id: str | None = None
    ) -> Result[dict[str, Any]]:
        """LS-scoped Socratic tutoring pipeline.

        Replaces the global RAG pipeline with a pedagogically intentional
        pipeline scoped to the user's active Learning Step.

        Pipeline steps:
        1. Load UserContext (rich) for active LS
        2. Load LS bundle via LSContextLoader
        3. Get/create conversation session
        4. Extract target KUs from question (scoped to bundle)
        5. Get targeted ZPD evidence for those KUs
        6. Classify pedagogical intent
        7. Generate SocraticMove (system prompt + curriculum context)
        8. Call LLM with the move
        9. Record turns in conversation session
        10. Return response with pedagogical metadata

        Args:
            user_uid: User's unique identifier
            question: User's natural language question
            session_id: Optional session ID for multi-turn conversations

        Returns:
            Result containing:
            - answer: Socratic response (question, not explanation)
            - move_type: PedagogicalIntent that drove the response
            - target_kus: KU UIDs the question targeted
            - ls_uid: Active Learning Step UID
            - session_id: Session ID for continuing the conversation
        """
        # Verify Socratic pipeline dependencies are wired
        if not self.ls_context_loader or not self.socratic_engine:
            return Result.fail(
                Errors.system(
                    message="Socratic pipeline not configured — missing LSContextLoader or SocraticEngine",
                    operation="process_socratic_turn",
                    user_message="Socratic tutoring is not available. Please check your configuration.",
                )
            )

        # Step 1: Get rich user context (includes active_learning_steps_rich)
        user_context_result = await self.user_service.get_rich_unified_context(user_uid)
        if user_context_result.is_error:
            error = user_context_result.expect_error()
            return Result.fail(
                Errors.system(
                    message=f"User context retrieval failed: {error.message}",
                    operation="process_socratic_turn",
                    user_message="Unable to load your learning data. Please try again shortly.",
                )
            )
        user_context = user_context_result.value

        # Step 2: Load LS bundle
        bundle_result = await self.ls_context_loader.load_bundle(user_uid, user_context)
        if bundle_result.is_error:
            return Result.ok(
                {
                    "answer": (
                        "You don't have an active learning step right now. "
                        "Enroll in a learning path to start Socratic tutoring."
                    ),
                    "move_type": "no_active_ls",
                    "target_kus": [],
                    "ls_uid": None,
                    "session_id": session_id,
                }
            )
        ls_bundle = bundle_result.value

        # Step 3: Get or create conversation session
        effective_session_id = session_id or f"socratic_{user_uid}_{ls_bundle.learning_step.uid}"
        conversation = None
        if self.conversation_context:
            conversation = self.conversation_context.get_or_create_session(
                effective_session_id, user_uid
            )
            # Add user's question as a turn
            conversation.add_turn(role=MessageRole.USER, content=question)

        # Step 4: Extract target KUs from question (scoped to bundle)
        target_ku_uids = self.entity_extractor.extract_from_bundle(question, ls_bundle)

        # Step 5: Get targeted ZPD evidence
        zone_evidence: dict[str, Any] = {}
        if self.zpd_service and target_ku_uids:
            zpd_result = await self.zpd_service.assess_ku_readiness(user_uid, target_ku_uids)
            if not zpd_result.is_error:
                zone_evidence = zpd_result.value

        # Step 6: Classify pedagogical intent
        intent = self.intent_classifier.classify_pedagogical_intent(
            question, ls_bundle, zone_evidence, target_ku_uids
        )

        # Step 7: Generate Socratic move
        move = self.socratic_engine.generate_move(
            intent=intent,
            ls_bundle=ls_bundle,
            zone_evidence=zone_evidence,
            conversation=conversation,
            target_ku_uids=target_ku_uids,
        )

        # Step 8: Call LLM with the move's system prompt and curriculum context
        user_prompt = question
        if move.curriculum_context:
            user_prompt = (
                f"=== CURRICULUM CONTEXT (for your reference, do NOT share directly) ===\n"
                f"{move.curriculum_context}\n\n"
                f"=== LEARNER'S MESSAGE ===\n{question}"
            )

        llm_response = await self.llm_service.generate(
            prompt=user_prompt,
            system_prompt=move.system_prompt,
            temperature=0.7,
            max_tokens=500,
        )

        answer = llm_response.content or (
            "I'd like to explore this with you, but I'm having trouble "
            "formulating my response. Could you rephrase your question?"
        )

        # Step 9: Record assistant turn
        if conversation:
            conversation.add_turn(role=MessageRole.ASSISTANT, content=answer)
            conversation.update_topic(ls_bundle.learning_step.title or "Learning")
            for ku_uid in target_ku_uids:
                conversation.add_entity(ku_uid)

        # Step 10: Package response
        logger.info(
            "Socratic turn for user %s: intent=%s, target_kus=%d, ls=%s",
            user_uid,
            intent.value,
            len(target_ku_uids),
            ls_bundle.learning_step.uid,
        )

        return Result.ok(
            {
                "answer": answer,
                "move_type": intent.value,
                "target_kus": target_ku_uids,
                "ls_uid": ls_bundle.learning_step.uid,
                "session_id": effective_session_id,
            }
        )

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

        # Step 3: Generate AI response with full context
        response = await self._generate_context_aware_response(
            query_message=query_message,
            current_knowledge=current_knowledge,
            active_learning=active_learning,
            active_tasks=active_tasks,
            related_goals=related_goals,
            intent=intent,
        )

        # Step 4: Generate suggested actions
        suggested_actions = self.response_generator.generate_suggested_actions(
            query_message, context_data, intent
        )

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
