"""
Content Enrichment Service
===========================

Enriches submitted content (audio transcripts, text) into formatted documents
using AI and Neo4j context.

Pipeline:
Submit (voice or text) → Extract (transcribe if audio) → Enrich (LLM + instructions)

The power comes from Neo4j context awareness:
- Active goals for personalized, goal-aware editing
- Processing instructions stored as Exercise Entity nodes in Neo4j
"""

from dataclasses import asdict
from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.models.entity import Entity
from core.models.entity_dto import EntityDTO
from core.models.relationship_names import RelationshipName
from core.models.type_hints import UserUID
from core.ports import BackendOperations
from core.services.base_service import BaseService
from core.services.content_enrichment.types import (
    EnrichmentContext,
    EnrichmentInsights,
)
from core.services.domain_config import DomainConfig
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.llm_protocols import ChatCompletionPort


class ContentEnrichmentService(BaseService[BackendOperations[Entity], Entity]):
    """
    Transcript processor service - transforms raw transcripts into formatted documents.

    Core Capabilities:
    - Process transcript → formatted document (via AI pipeline)
    - Apply formatting instructions from Neo4j
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
    This service processes transcripts according to instruction sets stored in Neo4j.
    The output is stored in Report.processed_content (Option A architecture).

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
        chat_port: "ChatCompletionPort | None" = None,  # For intelligent editing
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
        instructions_uid: str | None = None,
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
        2. Load formatting instructions (from Neo4j markdown)
        3. Apply AI-powered editing with context awareness
        4. Return formatted insights (NO entity creation)

        Args:
            raw_transcript: Raw text from transcription service,
            instructions_uid: UID of instruction set in Neo4j (default: use standard),
            user_uid: User identifier (optional, enables context-aware processing)

        Returns:
            Result containing EnrichmentInsights (formatted content, title, summary, themes, actions)
        """
        # Step 1: Pull context from Neo4j (optional, but improves quality)
        context_obj = await self._gather_context(user_uid) if user_uid else None
        context = asdict(context_obj) if context_obj else None

        # Step 2: Load formatting instructions
        instructions = await self._load_instructions(instructions_uid)
        if instructions.is_error:
            return Result.fail(instructions)

        # Step 3: Apply intelligent editing
        insights_result = await self._apply_intelligent_editing(
            raw_transcript=raw_transcript, instructions=instructions.value, context=context
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
        instructions_uid: str | None = None,
        user_uid: UserUID | None = None,
    ) -> Result[EnrichmentInsights]:
        """
        Process audio file into formatted journal insights (full pipeline).

        Pipeline: Audio → Transcription → Processing → EnrichmentInsights

        Args:
            audio_file_path: Path to audio file,
            instructions_uid: UID of instruction set,
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
        return await self.process_transcript(
            raw_transcript=raw_transcript,
            instructions_uid=instructions_uid,
            user_uid=user_uid,
        )

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
    # INSTRUCTION SET MANAGEMENT
    # ========================================================================

    async def _load_instructions(self, instructions_uid: str | None = None) -> Result[str]:
        """
        Load formatting instructions from Neo4j.

        Instructions are stored as markdown files in Neo4j.
        Each set is ~8000 characters with formatting rules.

        Args:
            instructions_uid: UID of instruction set (None = default),

        Returns:
            Result containing instruction text
        """
        if not instructions_uid:
            instructions_uid = "instructions:default-report-formatting"

        # Load from Neo4j (instructions stored as Exercise Entity nodes)
        result = await self.backend.load_exercise_instructions(instructions_uid)  # type: ignore[attr-defined]

        if result.is_error:
            self.logger.warning(f"Failed to load instructions, using default: {result.error}")
            return Result.ok(self._get_default_instructions())

        records = result.value or []
        if not records:
            # Return default instructions if not found
            return Result.ok(self._get_default_instructions())

        record = records[0]
        instructions = record["instructions"]
        self.logger.info(f"Loaded instructions: {record['name']} ({len(instructions)} chars)")

        return Result.ok(instructions)

    def _get_default_instructions(self) -> str:
        """
        Default formatting instructions.

        These are used when no custom instruction set is specified.
        """
        return """
# Journal Formatting Instructions

## Purpose
Transform raw transcript into well-formatted, flowing journal entry.

## Formatting Rules
1. **Structure**: Organize into coherent paragraphs
2. **Flow**: Remove verbal fillers ("um", "uh", "like")
3. **Clarity**: Improve sentence structure while preserving meaning
4. **Themes**: Identify main themes and group related content
5. **Action Items**: Extract concrete action items mentioned
6. **Title**: Generate concise, descriptive title

## Context Integration
- Reference active goals, tasks, habits when relevant
- Link to recent journal themes for continuity
- Identify learning opportunities from current paths

## Output Format
- Title (concise, descriptive)
- Summary (2-3 sentences)
- Main content (well-formatted paragraphs)
- Key themes (bullet list)
- Action items (if any)

Preserve the author's voice and authenticity while improving readability.
"""

    @with_error_handling("create_instruction_set", error_type="database", uid_param="uid")
    async def create_instruction_set(
        self, name: str, content: str, uid: str | None = None
    ) -> Result[dict[str, Any]]:
        """
        Create new instruction set in Neo4j.

        Args:
            name: Instruction set name,
            content: Markdown instructions (~8000 chars),
            uid: Optional custom UID

        Returns:
            Result containing created instruction set
        """
        if not uid:
            uid = f"instructions:{name.lower().replace(' ', '-')}"

        result = await self.backend.create_exercise_instruction_set(  # type: ignore[attr-defined]
            uid=uid, name=name, instructions=content
        )

        if result.is_error:
            return Result.fail(result)

        return Result.ok({"uid": uid, "name": name, "char_count": len(content)})

    @with_error_handling("list_instruction_sets", error_type="database")
    async def list_instruction_sets(self) -> Result[list[dict[str, Any]]]:
        """List all available exercise instruction sets."""
        result = await self.backend.list_exercise_instruction_sets()  # type: ignore[attr-defined]

        if result.is_error:
            return Result.fail(result)

        instruction_sets = [
            {"uid": record["uid"], "name": record["name"], "char_count": record["char_count"]}
            for record in result.value or []
        ]

        return Result.ok(instruction_sets)

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

        completion_text = ai_result.value.text

        # Debug logging
        self.logger.info(
            f"AI result length: {len(completion_text)}, value: {completion_text[:100] if completion_text else 'None'}"
        )

        # Parse AI response
        insights = self._parse_ai_response(completion_text)

        # Debug logging
        self.logger.info(
            f"Parsed AI response: title={insights.title[:50] if insights.title else 'None'}"
        )

        # Return EnrichmentInsights directly (not dict)
        return Result.ok(insights)

    def _build_editing_prompt(
        self, raw_transcript: str, instructions: str, context: dict[str, Any] | None
    ) -> str:
        """Build comprehensive prompt for AI editing."""
        # COMPREHENSIVE ERROR TRACING - Find the exact .get() on None location
        self.logger.info(
            f"_build_editing_prompt called with context type: {type(context)}, context is None: {context is None}"
        )

        try:
            prompt_parts = [
                "# Journal Transcript Editing Task",
                "",
                "## Instructions",
                instructions,
                "",
            ]

            # Add enhanced context if available (Step 1 implementation)
            if context:
                prompt_parts.extend(
                    [
                        "## User Context (Enhanced Intelligence)",
                        "Use this context to provide intelligent, personalized, context-aware editing:",
                        "",
                    ]
                )

                # Active Goals (the only live enrichment signal post-ADR-054)
                self.logger.info("Processing active_goals context section")
                if context.get("active_goals"):
                    prompt_parts.append("**Active Goals**:")
                    prompt_parts.extend(
                        f"  - {goal.get('title', 'Untitled')}: {goal.get('description', '')[:100]}"
                        for goal in context["active_goals"]
                        if goal and isinstance(goal, dict)  # Defensive check
                    )
                    prompt_parts.append("")

                # Extraction guidance - with defensive None handling
                self.logger.info("Building extraction guidance")
                active_goals_list: Any = []
                try:
                    active_goals_list = context.get("active_goals", []) or []
                    goal_titles = ", ".join(
                        [
                            g.get("title", "")
                            for g in active_goals_list[:3]
                            if g and isinstance(g, dict) and g.get("title")
                        ]
                    )
                except (TypeError, AttributeError, KeyError) as e:
                    self.logger.error(
                        f"Error building goal_titles: {e}, active_goals_list = {active_goals_list}"
                    )
                    goal_titles = "none"

                prompt_parts.extend(
                    [
                        "**Extract from this transcript**:",
                        "1. **Key topics** (main subjects discussed)",
                        "2. **Knowledge applications** (which concepts are being used/practiced?)",
                        f"3. **Goal progress** (which goals mentioned: {goal_titles if goal_titles else 'none'})",
                        "4. **Action items** (specific next steps mentioned)",
                        "",
                    ]
                )

            # Add raw transcript
            self.logger.info("Adding raw transcript to prompt")
            prompt_parts.extend(
                [
                    "## Raw Transcript",
                    "```",
                    raw_transcript,
                    "```",
                    "",
                    "## Task",
                    "Format this transcript according to instructions above, using context for intelligent editing.",
                    "",
                    "**Output Format: Return ONLY Markdown in this exact structure:**",
                    "",
                    "```markdown",
                    "# [Descriptive Title]",
                    "",
                    "**Summary**: [1-2 sentence summary of key points]",
                    "",
                    "## Journal Entry",
                    "",
                    "[Formatted journal content with proper markdown - use headings, lists, emphasis as appropriate]",
                    "",
                    "## Key Themes",
                    "- Theme 1",
                    "- Theme 2",
                    "- Theme 3",
                    "",
                    "## Action Items",
                    "- [ ] Action item 1",
                    "- [ ] Action item 2",
                    "```",
                    "",
                    "Do NOT wrap the output in code fences. Return the raw Markdown directly.",
                ]
            )

            result = "\n".join(prompt_parts)
            self.logger.info(f"Successfully built prompt: {len(result)} chars")
            return result

        except (TypeError, AttributeError, KeyError, ValueError) as e:
            self.logger.error(f"CRITICAL ERROR in _build_editing_prompt: {e}", exc_info=True)
            self.logger.error(f"Context type: {type(context)}, context value: {context}")
        except Exception as e:  # safety-net: catch unexpected errors
            self.logger.error(f"CRITICAL ERROR in _build_editing_prompt: {e}", exc_info=True)
            self.logger.error(f"Context type: {type(context)}, context value: {context}")

        # Return minimal prompt on error (reached by either except block)
        return f"""
# Journal Transcript Editing Task

## Instructions
{instructions}

## Raw Transcript
```
{raw_transcript}
```

## Task
Format this transcript according to instructions above.

Return ONLY Markdown in this structure:
# [Title]
**Summary**: [Summary]
## Journal Entry
[Content]
## Key Themes
- Theme 1
## Action Items
- [ ] Action 1
"""

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
