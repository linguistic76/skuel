"""
Query Processor - Natural Language Query Processing (Orchestration)
===================================================================

Orchestrates the RAG pipeline using specialized sub-services.

Responsibilities:
- Orchestrate the complete RAG pipeline
- Coordinate EntityExtractor, ContextRetriever, IntentClassifier, ResponseGenerator
- Answer user questions with retrieval + generation
- Process queries with full context
- Enrollment gate (PS-first) — Askesis works with active Path Steps, plus Learning Paths when available

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
ZPD + GuidanceMode wired into answer flow.
July 2026: Enrollment gate is PS-first — an active PathStep or an enrolled
Learning Path unlocks Askesis (systems-review Arc B).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from core.constants import AskesisPipelineTimeout, AskesisTokenBudget, QueryProcessorConfidence
from core.models.enums import GuidanceMode, MessageRole
from core.models.query_types import QueryIntent
from core.models.type_hints import UserUID
from core.models.user.conversation import ConversationContext
from core.services.canon import CanonContext
from core.utils.decorators import with_error_handling
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.text_truncation import truncate_to_budget

if TYPE_CHECKING:
    from core.models.search_request import SearchRequest
    from core.ports.zpd_protocols import ZPDOperations
    from core.services.askesis.context_retriever import ContextRetriever
    from core.services.askesis.entity_extractor import EntityExtractor
    from core.services.askesis.intent_classifier import IntentClassifier
    from core.services.askesis.response_generator import ResponseGenerator
    from core.services.askesis_citation_service import AskesisCitationService
    from core.services.canon import CanonRetrievalService, CanonSource
    from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
    from core.services.llm_service import LLMService
    from core.services.user.unified_user_context import UserContext
    from core.services.user_service import UserService

logger = get_logger(__name__)


# Enrollment gate response — returned when the user has neither an active
# PathStep nor an enrolled Learning Path (PS-first: either one unlocks Askesis).
_ENROLLMENT_GATE_RESPONSE: dict[str, Any] = {
    "answer": (
        "Askesis works within your learning. Start learning on a Path Step to begin — "
        "or enroll in a Learning Path."
    ),
    "context_used": {},
    "suggested_actions": [
        {"action": "start_path_step", "description": "Browse Path Steps and start learning"},
        {"action": "enroll_learning_path", "description": "Browse available Learning Paths"},
    ],
    "confidence": 1.0,
    "mode": "enrollment_gate",
    "has_citations": False,
}


def _passes_enrollment_gate(user_context: UserContext) -> bool:
    """PS-first enrollment gate — an active PathStep (IN_PROGRESS) or an enrolled
    Learning Path unlocks Askesis. Both fields are populated at standard AND rich
    context depth."""
    return bool(user_context.current_ps_uids or user_context.enrolled_path_uids)


class QueryProcessor:
    """
    Orchestrate the RAG pipeline for answering user questions.

    Implements: AskesisQueryOperations protocol (structural typing)

    This service handles query processing orchestration:
    - Answer user questions (complete RAG pipeline)
    - Process queries with context
    - Coordinate sub-services for intent, entities, context, response
    - Enrollment gate (PS-first) — requires an active PathStep or enrolled Learning Path

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
    March 2026: Absorbed Socratic pipeline. July 2026: PS-first enrollment gate.
    """

    def __init__(
        self,
        intent_classifier: IntentClassifier,
        response_generator: ResponseGenerator,
        entity_extractor: EntityExtractor,
        context_retriever: ContextRetriever,
        user_service: UserService,
        llm_service: LLMService,
        graph_intel: GraphIntelligenceService,
        zpd_service: ZPDOperations,
        citation_service: AskesisCitationService | None = None,
        canon_service: CanonRetrievalService | None = None,
        conversation_context: ConversationContext | None = None,
    ) -> None:
        """
        Initialize query processor.

        Args:
            intent_classifier: IntentClassifier for query intent classification
            response_generator: ResponseGenerator for action/context/prompt generation
            entity_extractor: EntityExtractor for entity extraction
            context_retriever: ContextRetriever for context retrieval and PS bundle loading
            user_service: UserService for accessing UserContext
            llm_service: LLMService for natural language generation
            graph_intel: GraphIntelligenceService for graph intelligence queries
            zpd_service: ZPDService for targeted KU readiness assessment
            citation_service: AskesisCitationService for source and evidence transparency (optional)
            canon_service: CanonRetrievalService for PS-scoped readings grounding
                (ADR-077, optional — None in CORE tier, guidance degrades canon-free)
        """
        self.intent_classifier = intent_classifier
        self.response_generator = response_generator
        self.entity_extractor = entity_extractor
        self.context_retriever = context_retriever
        self.user_service = user_service
        self.llm_service = llm_service
        self.graph_intel = graph_intel
        self.zpd_service = zpd_service
        self.citation_service = citation_service
        self.canon_service = canon_service
        self.conversation_context = conversation_context or ConversationContext()
        # Holds references to fire-and-forget persistence tasks so they aren't GC'd.
        self._background_tasks: set[asyncio.Task[None]] = set()

        logger.info("QueryProcessor initialized (orchestration layer)")

    # ========================================================================
    # PUBLIC API - QUERY ANSWERING
    # ========================================================================

    @with_error_handling("answer_user_question", error_type="system", uid_param="user_uid")
    async def answer_user_question(
        self,
        user_uid: UserUID,
        question: str,
        session_id: str | None = None,
        preferred_mode: GuidanceMode | None = None,
        scope: SearchRequest | None = None,
    ) -> Result[dict[str, Any]]:
        """
        Complete RAG pipeline - retrieval + generation.

        This is THE method for answering user questions about their data.
        Combines UserContext (retrieval) with LLM (generation) to produce
        natural language answers based on user's actual state.

        When an PS bundle is available, the pipeline uses ZPD evidence and
        GuidanceMode to produce a pedagogically appropriate response.

        Timeout: AskesisPipelineTimeout.ANSWER_QUESTION_SECONDS (default 30s).

        Args:
            user_uid: User's unique identifier
            question: Natural language question from user

        Returns:
            Result containing:
            - answer: Natural language response
            - context_used: Relevant entities from user's data
            - suggested_actions: Next steps user can take
            - confidence: Confidence score (0.0-1.0)
            - guidance_mode: GuidanceMode used for guided response (if PS bundle available)
        """
        try:
            return await asyncio.wait_for(
                self._answer_user_question_pipeline(
                    user_uid, question, session_id, preferred_mode, scope
                ),
                timeout=AskesisPipelineTimeout.ANSWER_QUESTION_SECONDS,
            )
        except TimeoutError:
            logger.error(
                "answer_user_question timed out after %ds for user %s",
                AskesisPipelineTimeout.ANSWER_QUESTION_SECONDS,
                user_uid,
            )
            return Result.fail(
                Errors.system(
                    message=f"Pipeline timed out after {AskesisPipelineTimeout.ANSWER_QUESTION_SECONDS}s",
                    operation="answer_user_question",
                    user_message="Your question is taking too long to process. Please try again.",
                )
            )

    async def _answer_user_question_pipeline(
        self,
        user_uid: UserUID,
        question: str,
        session_id: str | None = None,
        preferred_mode: GuidanceMode | None = None,
        scope: SearchRequest | None = None,
    ) -> Result[dict[str, Any]]:
        """Inner pipeline for answer_user_question, wrapped with timeout."""
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

        # Step 2: Enrollment gate — PS-first, LP when available
        if not _passes_enrollment_gate(user_context):
            return Result.ok(_ENROLLMENT_GATE_RESPONSE)

        # Step 3: Load conversation history
        conversation_history: list[dict[str, str]] | None = None
        session = None
        if session_id:
            session = self.conversation_context.get_or_create_session(session_id, user_uid)
            conversation_history = session.to_llm_messages(max_tokens=2000) or None

        # Step 4: Classify intent
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

        # Step 5: Extract entities
        extracted_entities: dict[str, list[dict[str, Any]]] = {
            "knowledge": [],
            "tasks": [],
            "goals": [],
            "habits": [],
            "events": [],
            "principles": [],
            "choices": [],
        }
        try:
            extracted_entities = await self.entity_extractor.extract_entities_from_query(
                question, user_context
            )
        except NEO4J_EXCEPTIONS:
            logger.warning(
                "Entity extraction failed (database error) — continuing without entity matches",
                exc_info=True,
            )
        except Exception:  # safety-net: catch unexpected errors
            logger.warning(
                "Entity extraction failed — continuing without entity matches", exc_info=True
            )

        # Step 6: Retrieve relevant context
        relevant_context = await self.context_retriever.retrieve_relevant_context(
            user_context, question, intent, scope
        )
        if any(extracted_entities.values()):
            relevant_context["mentioned_entities"] = extracted_entities

        # Step 7: Run guided pipeline (ZPD + guidance mode) — UNLESS the user set an
        # explicit facet scope. An explicit scope OVERRIDES auto-guidance (Codex #544):
        # answer from the scoped passages via the context-aware branch below, not the
        # current PS bundle — which would otherwise re-introduce unscoped curriculum
        # context and make the topic selection a silent no-op for guided users.
        if scope is not None and scope.to_property_filters():
            guided_system_prompt, guidance_mode, ps_bundle, canon_context = (
                None,
                None,
                None,
                CanonContext.empty(),
            )
        else:
            (
                guided_system_prompt,
                guidance_mode,
                ps_bundle,
                canon_context,
            ) = await self._run_guided_pipeline(user_uid, question, user_context, preferred_mode)

        # Step 8: Generate answer (guided or context-aware)
        if guided_system_prompt:
            answer = await self._generate_guided_answer(
                question, guided_system_prompt, ps_bundle, conversation_history
            )
        else:
            llm_context = self.response_generator.build_llm_context(
                user_context, question, intent, ps_bundle=ps_bundle
            )
            answer = await self.llm_service.generate_context_aware_answer(
                query=question,
                user_context=llm_context,
                additional_context=relevant_context,
                intent=intent,
                conversation_history=conversation_history,
            )

        # Step 9: Record conversation turns — in-memory context window + durable Neo4j history.
        # Neo4j writes are fire-and-forget so persistence latency can't trigger the 30s timeout.
        if session:
            session.add_turn(MessageRole.USER, question)
            session.add_turn(MessageRole.ASSISTANT, answer)
        task = asyncio.create_task(self._persist_conversation_turns(user_uid, question, answer))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

        # Step 10: Generate actions + citations
        suggested_actions = self.response_generator.generate_actions(
            user_context, intent, relevant_context
        )
        citations_text = ""
        if intent in (QueryIntent.PREREQUISITE, QueryIntent.HIERARCHICAL):
            knowledge_entities = extracted_entities.get("knowledge", [])
            if knowledge_entities:
                knowledge_uids = [uid for ku in knowledge_entities if (uid := ku.get("uid"))]
                citations_text = await self._retrieve_citations_for_knowledge_units(
                    knowledge_uids, min_evidence_count=1
                )

        # Step 11: Build response
        response = self._build_answer_response(
            answer=answer,
            relevant_context=relevant_context,
            suggested_actions=suggested_actions,
            citations_text=citations_text,
            extracted_entities=extracted_entities,
            is_guided=guided_system_prompt is not None,
            guidance_mode=guidance_mode,
            session_id=session_id,
            canon_sources=canon_context.sources(),
        )

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
        self, user_uid: UserUID, query_message: str, depth: int = 2
    ) -> Result[dict[str, Any]]:
        """
        Process Askesis query with full user context.

        PS-first, ZPD-informed pipeline. Retrieves complete user learning
        context in a single Pure Cypher query and generates personalized,
        GuidanceMode-aware responses.

        Timeout: AskesisPipelineTimeout.PROCESS_QUERY_SECONDS (default 30s).

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
        try:
            return await asyncio.wait_for(
                self._process_query_with_context_pipeline(user_uid, query_message, depth),
                timeout=AskesisPipelineTimeout.PROCESS_QUERY_SECONDS,
            )
        except TimeoutError:
            logger.error(
                "process_query_with_context timed out after %ds for user %s",
                AskesisPipelineTimeout.PROCESS_QUERY_SECONDS,
                user_uid,
            )
            return Result.fail(
                Errors.system(
                    message=f"Pipeline timed out after {AskesisPipelineTimeout.PROCESS_QUERY_SECONDS}s",
                    operation="process_query_with_context",
                    user_message="Your question is taking too long to process. Please try again.",
                )
            )

    async def _process_query_with_context_pipeline(
        self, user_uid: UserUID, query_message: str, depth: int = 2
    ) -> Result[dict[str, Any]]:
        """Inner pipeline for process_query_with_context, wrapped with timeout."""
        # Step 1: Load user context + enrollment gate
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
        if not _passes_enrollment_gate(user_context):
            return Result.ok(_ENROLLMENT_GATE_RESPONSE)

        # Step 2: Get learning context (served from already-built UserContext, no extra query)
        context_result = await self.context_retriever.get_learning_context(user_context, depth)
        if context_result.is_error:
            return context_result
        context_data = context_result.value

        # Step 3: Classify intent
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

        # Step 4: Run guided pipeline (ZPD + guidance mode)
        # canon_context: grounded prompt only in this path — sources surface is
        # answer_user_question's (P1)
        (
            guided_system_prompt,
            guidance_mode,
            ps_bundle,
            _canon_context,
        ) = await self._run_guided_pipeline(user_uid, query_message, user_context)

        # Step 5: Generate response (guided or context-aware)
        current_knowledge = context_data["knowledge_units"]
        active_learning = context_data["learning_paths"]
        active_tasks = context_data["related_tasks"]
        related_goals = context_data.get("related_goals", [])

        if guided_system_prompt:
            response = await self._generate_guided_answer(
                query_message, guided_system_prompt, ps_bundle
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

        # Step 6: Build result
        suggested_actions = self.response_generator.generate_suggested_actions(
            query_message, context_data, intent
        )
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
    # PRIVATE - SHARED PIPELINE STEPS
    # ========================================================================

    async def _persist_conversation_turns(
        self, user_uid: UserUID, question: str, answer: str
    ) -> None:
        """Fire-and-forget Neo4j persistence for a user+assistant exchange."""
        for role, content in (
            (MessageRole.USER, question),
            (MessageRole.ASSISTANT, answer),
        ):
            result = await self.user_service.add_conversation_message(user_uid, role.value, content)
            if result.is_error:
                logger.warning(
                    "Failed to persist %s conversation message: %s",
                    role.value,
                    result.expect_error().message,
                )

    async def _run_guided_pipeline(
        self,
        user_uid: UserUID,
        question: str,
        user_context: Any,
        preferred_mode: GuidanceMode | None = None,
    ) -> tuple[str | None, str | None, Any, CanonContext]:
        """
        Load PS bundle and compute guided system prompt + guidance mode.

        If preferred_mode is provided, it overrides the ZPD-determined mode while
        preserving the pedagogical intent and zone evidence for system prompt building.

        Returns:
            (guided_system_prompt, guidance_mode, ps_bundle, canon_context) — the
            first three None if no bundle available; canon_context is always a
            CanonContext (empty when no canon service, no cited Resources, or
            no resonant passage — fail-soft, ADR-077).
        """
        bundle_result = await self.context_retriever.load_ps_bundle(user_uid, user_context)
        if bundle_result.is_error:
            return None, None, None, CanonContext.empty()

        ps_bundle = bundle_result.value

        # PS-scoped canon readings (FULL-tier, fail-soft). Scope = the PS's cited
        # Resources (focus PS + its Kus + related steps, already loaded on the
        # bundle). Keyed on the learner's QUESTION, mirroring the journal keying
        # on user_reply.
        canon_context = CanonContext.empty()
        if self.canon_service is not None:
            resource_uids: list[str] = [r.uid for r in ps_bundle.resources]
            if resource_uids:
                canon_result = await self.canon_service.retrieve(
                    question, resource_uids=resource_uids
                )
                if not canon_result.is_error:
                    canon_context = canon_result.value

        target_ku_uids = self.entity_extractor.extract_from_bundle(question, ps_bundle)

        zone_evidence: dict[str, Any] = {}
        if target_ku_uids:
            zpd_result = await self.zpd_service.assess_ku_readiness(user_uid, target_ku_uids)
            if not zpd_result.is_error:
                zone_evidence = zpd_result.value
            logger.info(
                "ZPD readiness assessed for user %s: %d target KUs %s (evidence keys: %s)",
                user_uid,
                len(target_ku_uids),
                target_ku_uids,
                sorted(zone_evidence) if zone_evidence else "none",
            )

        guidance = self.intent_classifier.determine_guidance_mode(
            question, ps_bundle, zone_evidence, target_ku_uids
        )
        if preferred_mode is not None:
            from dataclasses import replace

            guidance = replace(guidance, mode=preferred_mode)
        guided_system_prompt = self.response_generator.build_guided_system_prompt(
            guidance, ps_bundle, user_context, canon_context=canon_context
        )
        return guided_system_prompt, guidance.mode.value, ps_bundle, canon_context

    async def _generate_guided_answer(
        self,
        question: str,
        guided_system_prompt: str,
        ps_bundle: Any,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> str:
        """
        Generate an LLM answer using the guided (Socratic) pipeline.

        Prepends curriculum context to the user prompt when available,
        then calls LLM with the guided system prompt.
        """
        user_prompt = question
        if ps_bundle and ps_bundle.curriculum_context_text:
            curriculum_text = truncate_to_budget(
                ps_bundle.curriculum_context_text,
                AskesisTokenBudget.MAX_USER_PROMPT_CURRICULUM_CHARS,
            )
            user_prompt = (
                f"=== CURRICULUM CONTEXT (for your reference, do NOT share directly) ===\n"
                f"{curriculum_text}\n\n"
                f"=== LEARNER'S MESSAGE ===\n{question}"
            )

        llm_response = await self.llm_service.generate(
            prompt=user_prompt,
            system_prompt=guided_system_prompt,
            temperature=0.7,
            max_tokens=500,
            conversation_history=conversation_history,
        )
        return llm_response.content or (
            "I'd like to explore this with you, but I'm having trouble "
            "formulating my response. Could you rephrase your question?"
        )

    def _build_answer_response(
        self,
        answer: str,
        relevant_context: dict[str, Any],
        suggested_actions: list[dict[str, Any]],
        citations_text: str,
        extracted_entities: dict[str, list[Any]],
        is_guided: bool,
        guidance_mode: str | None,
        session_id: str | None,
        canon_sources: tuple[CanonSource, ...] = (),
    ) -> dict[str, Any]:
        """Build the response dict for answer_user_question."""
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
            "mode": "guided" if is_guided else "llm_generated",
            "has_citations": bool(citations_text),
            # Canon readings the guided prompt drew on (ADR-077) — [] when none.
            "canon_sources": list(canon_sources),
        }
        if guidance_mode:
            response["guidance_mode"] = guidance_mode
        if session_id:
            response["session_id"] = session_id
        return response

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

        knowledge_titles = [extract_title(k) for k in current_knowledge[:5]]
        context = "\n".join(
            [
                f"Knowledge units: {len(current_knowledge)}",
                f"Active learning paths: {len(active_learning)}",
                f"Active tasks: {len(active_tasks)}",
                f"Related goals: {len(related_goals)}",
                f"Recent knowledge: {', '.join(knowledge_titles) or 'none'}",
            ]
        )

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
