"""
LLM DSL Bridge Service
======================

Transforms natural journal text into structured DSL format using LLM intelligence.
This bridges the gap between free-form journaling and SKUEL's 13-domain architecture.

**The Problem:**

Users write naturally:
    "I need to finish the quarterly report by Friday. Also want to start
    meditating daily - 10 minutes each morning. Thinking about whether
    to take that job offer. Spent $150 on groceries today."

**The Solution:**

LLM recognizes activities and adds @context tags:
    - @context(task) Finish the quarterly report @when(Friday) @priority(high)
    - @context(habit) Meditate daily @repeat(daily) @duration(10)
    - @context(choice) Decide on job offer @when(soon)
    - @context(finance) Groceries @amount(150) @when(today)

**Integration Point:**

```
Natural Journal Text
        ↓
LLMDSLBridgeService.transform()  ← YOU ARE HERE
        ↓
Text with @context() tags
        ↓
ActivityDSLParser.parse_journal()
        ↓
ParsedJournal with typed activities
        ↓
ActivityExtractorService.extract_and_create()
        ↓
SKUEL Entities (Tasks, Habits, Goals, etc.)
```

The bridge uses a two-phase approach:
1. **Recognition Phase**: LLM identifies actionable items in the text
2. **Tagging Phase**: LLM adds appropriate @context tags and attributes
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.models.type_hints import UserUID
from core.prompts import PROMPT_REGISTRY
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.llm_protocols import ChatCompletionPort

# ``@link(...)`` as the parser's TAG_PATTERN reads it; ``_parse_llm_output`` drops it.
_LINK_TAG_RE = re.compile(r"\s*@link\([^)]*\)")

# ============================================================================
# TRANSFORMATION RESULT
# ============================================================================


@dataclass
class DSLTransformResult:
    """
    Result of LLM DSL transformation.

    Contains both the transformed text with @context tags and
    metadata about the transformation process.
    """

    # Original input
    original_text: str

    # Transformed output with @context tags
    transformed_text: str

    # Activity lines extracted (for preview)
    activity_lines: list[str] = field(default_factory=list)

    # Statistics
    activities_identified: int = 0

    # Domain breakdown
    tasks_identified: int = 0
    habits_identified: int = 0
    goals_identified: int = 0
    events_identified: int = 0
    principles_identified: int = 0
    choices_identified: int = 0
    finances_identified: int = 0
    kus_identified: int = 0
    path_steps_identified: int = 0
    learning_paths_identified: int = 0
    reports_identified: int = 0
    analytics_identified: int = 0
    calendar_items_identified: int = 0
    lifepath_items_identified: int = 0

    # Processing metadata
    model_used: str = ""
    tokens_used: int = 0
    transform_started_at: datetime = field(default_factory=datetime.now)
    transform_completed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage/API response."""
        return {
            "original_length": len(self.original_text),
            "transformed_length": len(self.transformed_text),
            "activities_identified": self.activities_identified,
            "activity_lines": self.activity_lines,
            "breakdown": {
                # Activity Domains (7)
                "tasks": self.tasks_identified,
                "habits": self.habits_identified,
                "goals": self.goals_identified,
                "events": self.events_identified,
                "principles": self.principles_identified,
                "choices": self.choices_identified,
                "finances": self.finances_identified,
                # Curriculum Domains (3)
                "kus": self.kus_identified,
                "path_steps": self.path_steps_identified,
                "learning_paths": self.learning_paths_identified,
                # Meta Domains (3)
                "reports": self.reports_identified,
                "analytics": self.analytics_identified,
                "calendar_items": self.calendar_items_identified,
                # The Destination (+1)
                "lifepath_items": self.lifepath_items_identified,
            },
            "model_used": self.model_used,
            "tokens_used": self.tokens_used,
            "transform_started_at": self.transform_started_at.isoformat(),
            "transform_completed_at": self.transform_completed_at.isoformat()
            if self.transform_completed_at
            else None,
        }


# ============================================================================
# LLM DSL BRIDGE SERVICE
# ============================================================================


class LLMDSLBridgeService:
    """
    Transforms natural journal text into structured DSL format using LLM.

    This service bridges the gap between free-form journaling and SKUEL's
    13-domain DSL architecture. It uses an LLM to intelligently identify
    actionable items and add the appropriate @context tags.

    **Usage:**

    ```python
    bridge = LLMDSLBridgeService(chat_port=openai_chat_adapter)

    # Transform natural text to DSL
    result = await bridge.transform(
        text="I need to finish the report by Friday and start exercising daily.",
        user_uid="user:mike",
    )

    if result.is_ok:
        transform = result.value
        print(transform.transformed_text)
        # - @context(task) Finish the report @when(Friday) @priority(high)
        # - @context(habit) Exercise @repeat(daily)
    ```

    **Pipeline integration (wired — ADR-069):**

    `UserEntryProcessingService._run_extract_activities` runs
    transform_with_context() as the optional pre-pass of
    `Pipeline.EXTRACT_ACTIVITIES`, grounded in the user's active goals via the
    shared `core.services.dsl.grounding` builder — the same grounding the inert
    journal "Suggested activities" panel uses, so the entity-creating path and
    the preview path recognise prose against identical context. On success the
    returned `activity_lines` are appended to the working text under an
    `## Extracted Activities` heading before the Analog parser runs; on
    failure the run degrades to parser-only over the original text (the
    bridge enhances, never gates). The compose root injects the bridge on
    FULL tier with a configured key, else None.
    """

    def __init__(
        self,
        chat_port: "ChatCompletionPort | None" = None,
        model: str = "gpt-4o-mini",
        use_compact_prompt: bool = False,
    ) -> None:
        """
        Initialize the LLM DSL Bridge.

        Args:
            chat_port: Chat-completion adapter for LLM calls. When None,
                transform() returns an integration error — LLM is required.
            model: Model to use for transformation (default: gpt-4o-mini)
            use_compact_prompt: Use shorter prompt to reduce tokens
        """
        self.chat_port = chat_port
        self.model = model
        self.use_compact_prompt = use_compact_prompt
        self.logger = get_logger("skuel.dsl.llm_bridge")

    @with_error_handling(error_type="integration", operation="transform")
    async def transform(
        self,
        text: str,
        user_uid: UserUID | None = None,
        context_block: str = "",
    ) -> Result[DSLTransformResult]:
        """
        Transform natural journal text into DSL format with @context tags.

        This is the main entry point for the bridge service.

        Args:
            text: Natural language journal text — the ONLY material extracted into
                activity lines.
            user_uid: Optional user UID for personalization
            context_block: Optional pre-rendered "USER CONTEXT" block (built by
                ``transform_with_context`` from active goals / topics / principles).
                Rendered into a SEPARATE, explicitly non-extractable prompt slot so
                grounding can disambiguate the text WITHOUT the LLM emitting
                activity lines from the context itself — which on the
                entity-creating extraction path would persist phantom entities with
                ``EXTRACTED_FROM`` provenance. Empty string = ungrounded.

        Returns:
            Result containing DSLTransformResult with transformed text
        """
        if not text or not text.strip():
            return Result.ok(
                DSLTransformResult(
                    original_text="",
                    transformed_text="",
                )
            )

        if not self.chat_port:
            return Result.fail(
                Errors.integration(
                    service="OpenAI",
                    message="Chat adapter not configured for LLM DSL Bridge",
                    operation="transform",
                )
            )

        transform_result = DSLTransformResult(
            original_text=text,
            transformed_text="",
            model_used=self.model,
        )

        # Select and render prompt template. The grounding block lands in its own
        # {user_context} slot (marked "background only — do not extract"), keeping
        # {journal_text} as the sole extractable material.
        template_id = (
            "dsl_domain_recognition_compact"
            if self.use_compact_prompt
            else "dsl_domain_recognition"
        )
        prompt = PROMPT_REGISTRY.render(template_id, journal_text=text, user_context=context_block)

        # Call LLM
        response = await self._call_llm(prompt)

        if response.is_error:
            return Result.fail(response)

        llm_output = response.value

        # Parse LLM output into activity lines
        activity_lines = self._parse_llm_output(llm_output)

        # Count by domain
        self._count_domains(activity_lines, transform_result)

        # Build transformed text
        transform_result.activity_lines = activity_lines
        transform_result.transformed_text = "\n".join(activity_lines)
        transform_result.activities_identified = len(activity_lines)
        transform_result.transform_completed_at = datetime.now()

        self.logger.info(
            f"Transformed journal text: {len(text)} chars → "
            f"{transform_result.activities_identified} activities identified"
        )

        return Result.ok(transform_result)

    async def transform_with_context(
        self,
        text: str,
        user_uid: UserUID,
        active_goals: list[dict[str, str]] | None = None,
        recent_topics: list[str] | None = None,
        user_principles: list[str] | None = None,
    ) -> Result[DSLTransformResult]:
        """
        Transform with user context for better domain recognition.

        The context helps the LLM recognise what the text is about — a task
        that serves an existing goal, a knowledge area in progress, a stated
        principle — and nothing more: grounding is recognition-only, and the
        bridge emits no link (``core.services.dsl.grounding``).

        Args:
            text: Natural language journal text
            user_uid: User UID
            active_goals: User's active goals (titles; recognition only)
            recent_topics: Recent topics the user has journaled about
            user_principles: User's stated principles

        Returns:
            Result containing DSLTransformResult with transformed text
        """
        # The grounding block rides the dedicated, non-extractable {user_context}
        # slot — see ``transform``'s ``context_block`` for what that guarantees.
        context_block = self._build_context_block(
            active_goals=active_goals,
            recent_topics=recent_topics,
            user_principles=user_principles,
        )

        return await self.transform(text, user_uid, context_block=context_block)

    # ========================================================================
    # PRIVATE METHODS
    # ========================================================================

    @with_error_handling(error_type="integration", operation="call_llm")
    async def _call_llm(self, prompt: str) -> Result[str]:
        """Call the LLM with the prompt and return the response."""
        # transform() guarantees chat_port is set before reaching here.
        assert self.chat_port is not None
        result = await self.chat_port.complete(
            [{"role": "user", "content": prompt}],
            system_prompt=(
                "You are a structured data extraction assistant. "
                "Output only the requested format, no explanations."
            ),
            model=self.model,
            temperature=0.3,  # Lower temperature for more consistent output
            max_tokens=2000,
        )
        if result.is_error:
            return Result.fail(result)
        content = result.value.text
        return Result.ok(content.strip() if content else "")

    def _parse_llm_output(self, output: str) -> list[str]:
        """Parse LLM output into individual activity lines.

        A bridge line carries no ``@link``: a link's id is a UID, and the model
        has no source for one (grounding passes titles), so any ``@link`` it
        emits is dropped here and the line reaches the parser link-free. Links
        on both bridge paths are the user's own.
        """
        lines = []

        for line in output.split("\n"):
            line = line.strip()

            # Skip empty lines
            if not line:
                continue

            # Remove leading bullet/dash if present
            if line.startswith("-") or line.startswith("*") or line.startswith("•"):
                line = line[1:].strip()

            # Skip lines without @context
            if "@context(" not in line:
                continue

            line = _LINK_TAG_RE.sub("", line).strip()

            # Ensure line starts with - for DSL format
            if not line.startswith("-"):
                line = f"- {line}"

            lines.append(line)

        return lines

    def _count_domains(self, activity_lines: list[str], result: DSLTransformResult) -> None:
        """Count activities by domain type."""
        for line in activity_lines:
            line_lower = line.lower()

            # Activity Domains (7)
            if "@context(task)" in line_lower:
                result.tasks_identified += 1
            elif "@context(habit)" in line_lower:
                result.habits_identified += 1
            elif "@context(goal)" in line_lower:
                result.goals_identified += 1
            elif "@context(event)" in line_lower:
                result.events_identified += 1
            elif "@context(principle)" in line_lower:
                result.principles_identified += 1
            elif "@context(choice)" in line_lower:
                result.choices_identified += 1
            elif "@context(finance)" in line_lower:
                result.finances_identified += 1

            # Curriculum Domains (3)
            elif "@context(ku)" in line_lower:
                result.kus_identified += 1
            elif "@context(ls)" in line_lower:
                result.path_steps_identified += 1
            elif "@context(lp)" in line_lower:
                result.learning_paths_identified += 1

            # Meta Domains (3)
            elif "@context(report)" in line_lower:
                result.reports_identified += 1
            elif "@context(analytics)" in line_lower:
                result.analytics_identified += 1
            elif "@context(calendar)" in line_lower:
                result.calendar_items_identified += 1

            # The Destination (+1)
            elif "@context(lifepath)" in line_lower:
                result.lifepath_items_identified += 1

    def _build_context_block(
        self,
        active_goals: list[dict[str, str]] | None = None,
        recent_topics: list[str] | None = None,
        user_principles: list[str] | None = None,
    ) -> str:
        """Build context block to enhance LLM recognition."""
        parts = []

        if active_goals:
            goals_text = ", ".join(g.get("title", "") for g in active_goals[:5])
            parts.append(f"User's active goals: {goals_text}")

        if recent_topics:
            topics_text = ", ".join(recent_topics[:10])
            parts.append(f"Recent topics: {topics_text}")

        if user_principles:
            principles_text = ", ".join(user_principles[:5])
            parts.append(f"User's principles: {principles_text}")

        if parts:
            # The header reinforces the template's instruction: this block is
            # background for linking only, never material to extract activities
            # from. Returns "" (no section at all) when there is nothing to ground.
            return (
                "## USER CONTEXT (background only — do NOT create activities from "
                "these; use only to recognise/classify items in the journal)\n" + "\n".join(parts)
            )

        return ""


# NOTE: the create_llm_dsl_bridge() factory moved below the hexagonal boundary
# to adapters/external/llm/dsl_bridge_factory.py — it constructs the OpenAI
# chat adapter, which core/ must not import (ADR-044 / SKUEL022). Inject a
# ChatCompletionPort into LLMDSLBridgeService directly, or use that factory.
