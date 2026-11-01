"""
Content Enrichment Service
===========================

Enriches submitted content (audio transcripts, text) into formatted documents
using AI and Neo4j context.

Pipeline:
Submit (voice or text) → Extract (transcribe if audio) → Enrich (LLM + instructions)

The power comes from Neo4j context awareness:
- Active goals for personalized, goal-aware editing

The formatting instructions are the prompt registry's ``transcript_formatting``
template — overridden locally by ``data/instructions/transcript_formatting.md``.
"""

from dataclasses import asdict
from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.constants import PromptInput
from core.models.entity import Entity
from core.models.entity_dto import EntityDTO
from core.models.relationship_names import RelationshipName
from core.models.type_hints import UserUID
from core.ports import BackendOperations
from core.prompts import PROMPT_REGISTRY
from core.services.base_service import BaseService
from core.services.content_enrichment.types import (
    EnrichmentContext,
    EnrichmentInsights,
)
from core.services.domain_config import DomainConfig
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.text_truncation import truncate_to_budget

if TYPE_CHECKING:
    from core.ports.llm_protocols import ChatCompletionPort


class ContentEnrichmentService(BaseService[BackendOperations[Entity], Entity]):
    """
    Transcript processor service - transforms raw transcripts into formatted documents.

    Core Capabilities:
    - Process transcript → formatted document (via AI pipeline)
    - Apply the registry's formatting instructions (``transcript_formatting``)
    - Edit transcript using UserContext intelligence
    - Basic CRUD for storing processed documents

    NOT included (removed bloat):
    - ❌ Analytics (streaks, statistics, mood trends)
    - ❌ Category management
    - ❌ Tag management
    - ❌ Advanced search
    - ❌ Mood/energy tracking

    ARCHITECTURE NOTE:
    =================
    This service processes transcripts according to the prompt registry's
    ``transcript_formatting`` template. The output is stored in
    Report.processed_content (Option A architecture).

    Semantic Types Used:
    - APPLIES_KNOWLEDGE: Processed documents apply knowledge units practically
    - REQUIRES_KNOWLEDGE: Processed documents require prerequisite knowledge
    """

    # =========================================================================
    # DomainConfig (January 2026)
    # =========================================================================
    _config = DomainConfig(
        dto_class=EntityDTO,
        model_class=Entity,
        entity_label="Entity",
        search_fields=("title", "content", "processed_content"),
        search_order_by="created_at",
        user_ownership_relationship=RelationshipName.OWNS,  # User-owned content
    )

    def __init__(
        self,
        backend: BackendOperations[Entity],
        transcription_service=None,
        chat_port: ChatCompletionPort | None = None,  # For intelligent editing
        event_bus=None,  # For publishing domain events
    ) -> None:
        """
        Initialize transcript processor service.

        Args:
            backend: Backend for Ku storage,
            transcription_service: TranscriptionService for audio → text,
            chat_port: Chat-completion adapter for intelligent editing,
            event_bus: Event bus for publishing domain events (optional)
        """
        super().__init__(backend, "ContentEnrichmentService")
        self.transcription_service = transcription_service
        self.chat_port = chat_port
        self.event_bus = event_bus
        self.logger = get_logger("skuel.services.content_enrichment")  # type: ignore[assignment]  # structlog BoundLogger

    # ========================================================================
    # CORE PURPOSE: TRANSCRIPT PROCESSING
    # ========================================================================

    @with_error_handling("process_transcript")
    async def process_transcript(
        self,
        raw_transcript: str,
        user_uid: UserUID | None = None,
    ) -> Result[EnrichmentInsights]:
        """
        Process raw transcript into formatted journal using Neo4j context.

        This is the PRIMARY method - the core purpose of this service.

        REFACTORED (November 10, 2025) - Option A Implementation:
        - No longer creates or stores entities directly
        - Returns EnrichmentInsights (formatted data only)
        - SubmissionsProcessingService stores insights in Report.processed_content
        - SubmissionsRelationshipService creates graph relationships

        Steps:
        1. Pull active-goal context from Neo4j
        2. Render the formatting instructions (``transcript_formatting``)
        3. Apply AI-powered editing with context awareness
        4. Return formatted insights (NO entity creation)

        Args:
            raw_transcript: Raw text from transcription service,
            user_uid: User identifier (optional, enables context-aware processing)

        Returns:
            Result containing EnrichmentInsights (formatted content, title, summary, themes, actions)
        """
        # Step 1: Pull context from Neo4j (optional, but improves quality)
        context_obj = await self._gather_context(user_uid) if user_uid else None
        context = asdict(context_obj) if context_obj else None

        # Step 2: The formatting instructions
        instructions = PROMPT_REGISTRY.render("transcript_formatting")

        # Step 3: Apply intelligent editing
        insights_result = await self._apply_intelligent_editing(
            raw_transcript=raw_transcript, instructions=instructions, context=context
        )

        if insights_result.is_error:
            return insights_result

        insights = insights_result.value

        self.logger.info(
            f"Processed transcript: {len(raw_transcript)} chars → {len(insights.formatted_content)} chars formatted"
        )

        # Return formatted insights (NO entity creation)
        return Result.ok(insights)

    @with_error_handling("process_audio")
    async def process_audio(
        self,
        audio_file_path: str,
        user_uid: UserUID | None = None,
    ) -> Result[EnrichmentInsights]:
        """
        Process audio file into formatted journal insights (full pipeline).

        Pipeline: Audio → Transcription → Processing → EnrichmentInsights

        Args:
            audio_file_path: Path to audio file,
            user_uid: User identifier (REQUIRED for context-aware processing)

        Returns:
            Result containing EnrichmentInsights (formatted content, title, summary, themes)
        """
        if not user_uid:
            return Result.fail(
                Errors.validation(
                    "user_uid is REQUIRED for journal creation (fail-fast)", field="user_uid"
                )
            )
        if not self.transcription_service:
            return Result.fail(
                Errors.system(
                    "Transcription service not available - cannot process audio",
                    operation="process_audio",
                )
            )

        # Step 1: Transcribe audio → raw text
        transcription_result = await self.transcription_service.transcribe_file(audio_file_path)

        if transcription_result.is_error:
            return Result.fail(transcription_result)

        raw_transcript = transcription_result.value.get("text") or transcription_result.value.get(
            "transcript"
        )

        # Step 2: Process transcript → formatted insights
        return await self.process_transcript(raw_transcript=raw_transcript, user_uid=user_uid)

    # ========================================================================
    # CONTEXT GATHERING (Neo4j Intelligence)
    # ========================================================================

    @with_error_handling(
        "get_journal_context_for_processing", error_type="database", uid_param="user_uid"
    )
    async def get_journal_context_for_processing(
        self, user_uid: UserUID
    ) -> Result[EnrichmentContext]:
        """
        Get active-goal context for intelligent transcript processing.

        ADR-054 dismantled the rich-journal model (mood/energy_level/key_topics/
        entry_date were dropped from UserEntry), so the former recent-journal,
        trending-topic, and mood-trend signals read gone properties and were
        removed. Active goals are the only live enrichment context.

        Args:
            user_uid: User identifier

        Returns:
            Result containing EnrichmentContext with active-goal context
        """
        query_result = await self.backend.get_journal_processing_context(user_uid)  # type: ignore[attr-defined]

        if query_result.is_error:
            return Result.fail(query_result)

        records = query_result.value or []
        context_data = records[0]["context"] if records else {}

        active_goals_list = [
            {
                "uid": g["uid"],
                "title": g.get("title", ""),
                "description": g.get("description", ""),
            }
            for g in context_data.get("active_goals", [])
            if g and g.get("uid")
        ]

        return Result.ok(
            EnrichmentContext(
                user_uid=user_uid,
                gathered_at=datetime.now().isoformat(),
                active_goals=active_goals_list,
            )
        )

    async def _gather_context(self, user_uid: UserUID) -> EnrichmentContext:
        """
        Gather active-goal context from Neo4j for intelligent editing.

        Convenience wrapper that returns EnrichmentContext directly (not Result[T])
        for the transcript-processing path, falling back to an empty context on
        error so enrichment degrades gracefully.

        Args:
            user_uid: User identifier

        Returns:
            Context dataclass for AI editing
        """
        result = await self.get_journal_context_for_processing(user_uid)

        if result.is_error:
            self.logger.warning(f"Failed to gather context: {result.error}")
            # Return empty context on error
            return EnrichmentContext(
                user_uid=user_uid,
                gathered_at=datetime.now().isoformat(),
                active_goals=[],
            )

        return result.value

    # ========================================================================
    # AI-POWERED INTELLIGENT EDITING
    # ========================================================================

    @with_error_handling("apply_intelligent_editing", error_type="integration")
    async def _apply_intelligent_editing(
        self, raw_transcript: str, instructions: str, context: dict[str, Any] | None = None
    ) -> Result[EnrichmentInsights]:
        """
        Apply AI-powered editing with context awareness.

        This is where the magic happens:
        1. Combines raw transcript + instructions + Neo4j context
        2. Sends to AI (OpenAI/Anthropic) for intelligent editing
        3. Returns formatted, context-aware insights

        REFACTORED (November 10, 2025) - Option A Implementation:
        - Returns EnrichmentInsights directly (not dict)
        - No entity creation

        Args:
            raw_transcript: Raw text from transcription,
            instructions: Formatting instructions,
            context: Neo4j context (goals, tasks, recent journals)

        Returns:
            Result containing EnrichmentInsights (formatted content, metadata)
        """
        # Fail-fast: a chat adapter is required for journal formatting
        if not self.chat_port:
            return Result.fail(
                Errors.system(
                    message="A chat adapter is required for journal formatting - "
                    "set INTELLIGENCE_TIER=full and configure OPENAI_API_KEY",
                    operation="format_with_llm",
                )
            )

        # Build AI prompt with context
        prompt = self._build_editing_prompt(raw_transcript, instructions, context)

        # Call the chat adapter for intelligent editing. Pass the model
        # explicitly to preserve the pre-W1 default (the former OpenAIService
        # path defaulted to gpt-4o-mini; the adapter's own default is gpt-4).
        ai_result = await self.chat_port.complete(
            [{"role": "user", "content": prompt}],
            model="gpt-4o-mini",
            max_tokens=8000,
            temperature=0.3,  # Lower temperature for consistent formatting
        )

        if ai_result.is_error:
            self.logger.error(f"AI generation failed: {ai_result.error}")
            return Result.fail(ai_result)

        insights = self._parse_ai_response(ai_result.value.text)

        # Return EnrichmentInsights directly (not dict)
        return Result.ok(insights)

    def _build_editing_prompt(
        self, raw_transcript: str, instructions: str, context: dict[str, Any] | None
    ) -> str:
        """The editing task: the instructions, the context section, the transcript.

        Rendered from ``transcript_editing``; a context (when given) fills its
        ``{context_section}`` from ``transcript_editing_context``. The transcript
        is bounded at ``PromptInput.DOCUMENT_MAX_CHARS`` before it enters.
        """
        context_section = ""
        if context:
            active_goals = context.get("active_goals") or []
            goal_block = ""
            if active_goals:
                goal_lines = [
                    f"  - {goal.get('title', 'Untitled')}: {(goal.get('description') or '')[:100]}"
                    for goal in active_goals
                    if goal and isinstance(goal, dict)
                ]
                goal_block = "\n".join(["**Active Goals**:", *goal_lines, ""]) + "\n"
            goal_titles = ", ".join(
                goal.get("title", "")
                for goal in active_goals[:3]
                if goal and isinstance(goal, dict) and goal.get("title")
            )
            rendered = PROMPT_REGISTRY.render(
                "transcript_editing_context",
                active_goals=goal_block,
                goal_titles=goal_titles or "none",
            )
            context_section = f"{rendered.strip()}\n\n"

        return PROMPT_REGISTRY.render(
            "transcript_editing",
            instructions=instructions,
            context_section=context_section,
            raw_transcript=truncate_to_budget(raw_transcript, PromptInput.DOCUMENT_MAX_CHARS),
        )

    def _parse_ai_response(self, ai_response: str) -> EnrichmentInsights:
        """
        Parse AI response from Markdown format into structured format.

        Expected Markdown structure:
        # Title
        **Summary**: Summary text
        ## Journal Entry
        [content]
        ## Key Themes
        - Theme 1
        ## Action Items
        - [ ] Action 1
        """
        import re

        # Defensive check: handle None or empty response
        if not ai_response:
            self.logger.warning("AI response is None or empty")
            return EnrichmentInsights(
                title="Journal Entry",
                formatted_content="",
                summary="AI response was empty",
                themes=[],
                action_items=[],
                edits_summary="AI response empty",
                context_summary=None,
            )

        # Strip code fences if present (in case AI wraps in ```markdown)
        content = ai_response.strip()
        if content.startswith("```markdown"):
            content = content[len("```markdown") :].strip()
        if content.startswith("```"):
            content = content[3:].strip()
        if content.endswith("```"):
            content = content[:-3].strip()

        try:
            # Extract title (first # heading)
            title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            title = title_match.group(1).strip() if title_match else "Journal Entry"

            # Extract summary (**Summary**: text)
            summary_match = re.search(r"\*\*Summary\*\*:\s*(.+?)(?:\n|$)", content, re.IGNORECASE)
            summary = summary_match.group(1).strip() if summary_match else ""

            # Extract journal entry content (between ## Journal Entry and ## Key Themes)
            journal_match = re.search(
                r"##\s+Journal Entry\s*\n(.+?)(?=##\s+Key Themes|##\s+Action Items|$)",
                content,
                re.DOTALL | re.IGNORECASE,
            )
            formatted_content = journal_match.group(1).strip() if journal_match else content

            # Extract themes (bullet points under ## Key Themes)
            themes = []
            themes_section = re.search(
                r"##\s+Key Themes\s*\n(.+?)(?=##\s+Action Items|$)",
                content,
                re.DOTALL | re.IGNORECASE,
            )
            if themes_section:
                theme_lines = themes_section.group(1).strip().split("\n")
                themes = [
                    re.sub(r"^[-*]\s*", "", line.strip())
                    for line in theme_lines
                    if line.strip()
                    and (line.strip().startswith("-") or line.strip().startswith("*"))
                ]

            # Extract action items (checkbox items under ## Action Items)
            action_items = []
            actions_section = re.search(
                r"##\s+Action Items\s*\n(.+?)$", content, re.DOTALL | re.IGNORECASE
            )
            if actions_section:
                action_lines = actions_section.group(1).strip().split("\n")
                action_items = [
                    re.sub(r"^[-*]\s*\[\s*\]\s*", "", line.strip())
                    for line in action_lines
                    if line.strip() and ("[ ]" in line or "[x]" in line or "[X]" in line)
                ]

            self.logger.info(
                f"Parsed Markdown: title='{title[:50]}', themes={len(themes)}, actions={len(action_items)}"
            )

            return EnrichmentInsights(
                title=title,
                formatted_content=formatted_content,
                summary=summary if summary else formatted_content[:200] + "...",
                themes=themes,
                action_items=action_items,
                edits_summary="AI editing applied successfully (Markdown)",
                context_summary="Context-aware editing completed",
            )

        except (ValueError, TypeError, AttributeError, KeyError, IndexError) as e:
            self.logger.error(f"Error parsing Markdown response: {e}", exc_info=True)
            # Fallback: treat entire response as formatted content
            return EnrichmentInsights(
                title="Journal Entry",
                formatted_content=ai_response,
                summary=ai_response[:200] + "..." if len(ai_response) > 200 else ai_response,
                themes=[],
                action_items=[],
                edits_summary="AI editing applied (Markdown parse error)",
                context_summary=None,
            )

    # ========================================================================
    # NOTE: CRUD methods removed (ADR-054). CES is now a
    # pure stateless enrichment processor — persistence of enriched output is
    # the responsibility of UserEntryService / UserEntryProcessingService.
    # BaseService still exposes .get() via the CRUD mixin for callers that
    # need to fetch an Entity by UID (e.g. adapters.inbound.exercises_api).
    # ========================================================================
