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

**Architecture:**

The bridge uses a two-phase approach:
1. **Recognition Phase**: LLM identifies actionable items in the text
2. **Tagging Phase**: LLM adds appropriate @context tags and attributes
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

# ============================================================================
# DOMAIN RECOGNITION PROMPTS - ALL 13 DOMAINS + 1
# ============================================================================

DOMAIN_RECOGNITION_PROMPT = """You are analyzing journal text to identify activities that map to SKUEL's 13 domains.

## THE 13 DOMAINS

### Activity Domains (7) - What I DO:
- @context(task) - One-time actions with deadlines
- @context(habit) - Recurring behaviors to build
- @context(goal) - Outcomes to achieve
- @context(event) - Scheduled appointments/meetings
- @context(principle) - Values/beliefs to embody
- @context(choice) - Decisions to make
- @context(finance) - Money matters (expenses/income/budget)

### Curriculum Domains (3) - What I LEARN:
- @context(ku) - Knowledge to acquire (concepts, facts, skills)
- @context(ls) - Learning activities (reading, courses, practice)
- @context(lp) - Learning paths (sequences of learning)

### Meta Domains (3) - How I ORGANIZE:
- @context(report) - Content to process (files, voice memos)
- @context(analytics) - Analytics to generate
- @context(calendar) - Time blocks to schedule

### The Destination (+1) - Where I'm GOING:
- @context(lifepath) - Life vision alignment, ultimate goals

## DSL SYNTAX

Each activity line should include:
- @context(type) - REQUIRED: The domain type
- @priority(low|medium|high|critical) - Optional: Importance level
- @when(date/time) - Optional: Due date, deadline, or scheduled time
- @repeat(daily|weekly|monthly|yearly) - Optional: For habits
- @duration(minutes) - Optional: Time estimate
- @energy(low|medium|high) - Optional: Energy state requirements
- @amount(number) - Optional: For finance items
- @goal(goal_description) - Optional: Link to a goal
- @principle(principle_name) - Optional: Link to a principle
- @ku(knowledge_unit) - Optional: Link to knowledge

## EXAMPLES

Input: "I need to finish the quarterly report by Friday. Also want to start meditating daily - 10 minutes each morning."

Output:
- @context(task) Finish the quarterly report @when(Friday) @priority(high)
- @context(habit) Meditate @repeat(daily) @duration(10) @energy(low)

Input: "Thinking about whether to take that new job offer. Spent $150 on groceries today."

Output:
- @context(choice) Decide on job offer @priority(high)
- @context(finance) Groceries @amount(150) @when(today)

Input: "I want to learn Python for data science. Need to master pandas first."

Output:
- @context(lp) Python for data science @priority(high)
- @context(ku) Pandas library fundamentals @goal(Python for data science)

Input: "Meeting with Sarah at 3pm tomorrow. Life goal: become a respected teacher who inspires others."

Output:
- @context(event) Meeting with Sarah @when(tomorrow 3pm)
- @context(lifepath) Become a respected teacher who inspires others

## INSTRUCTIONS

1. Read the journal text carefully
2. Identify all actionable items, decisions, learnings, and reflections
3. Classify each into one of the 13 domains
4. Output ONLY the structured activity lines (one per line, starting with -)
5. Preserve the original intent and key details
6. Add appropriate attributes (@when, @priority, @duration, etc.)
7. If something doesn't fit a domain, skip it (narrative text is fine)

## JOURNAL TEXT TO ANALYZE:

{journal_text}

## STRUCTURED OUTPUT (activity lines only):
"""


DOMAIN_RECOGNITION_PROMPT_COMPACT = """Analyze this journal and extract activities into SKUEL DSL format.

DOMAINS: task, habit, goal, event, principle, choice, finance, ku, ls, lp, report, analytics, calendar, lifepath

SYNTAX: - @context(type) description @attr(value)...
ATTRS: @priority, @when, @repeat, @duration, @energy, @amount, @goal, @principle, @ku

JOURNAL:
{journal_text}

OUTPUT (- @context lines only):
"""


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
    learning_steps_identified: int = 0
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
                "learning_steps": self.learning_steps_identified,
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
    bridge = LLMDSLBridgeService(openai_client=client)

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

    **Integration with Pipeline:**

    ```python
    # In ReportProcessorService or JournalCoreService

    # 1. Transform raw text to DSL format
    transform_result = await llm_bridge.transform(raw_journal_text, user_uid)
    if transform_result.is_error:
        return transform_result

    dsl_text = transform_result.value.transformed_text

    # 2. Append DSL activities to formatted content
    formatted_content = (
        original_content + "\\n\\n## Extracted Activities\\n" + dsl_text
    )

    # 3. Parse with DSL parser
    parse_result = dsl_parser.parse_journal(formatted_content)

    # 4. Create entities
    extraction_result = await extractor.extract_and_create(...)
    ```
    """

    def __init__(
        self,
        openai_client=None,
        model: str = "gpt-4o-mini",
        use_compact_prompt: bool = False,
    ) -> None:
        """
        Initialize the LLM DSL Bridge.

        Args:
            openai_client: OpenAI client for LLM calls
            model: Model to use for transformation (default: gpt-4o-mini)
            use_compact_prompt: Use shorter prompt to reduce tokens
        """
        self.client = openai_client
        self.model = model
        self.use_compact_prompt = use_compact_prompt
        self.logger = get_logger("skuel.dsl.llm_bridge")

    @with_error_handling(error_type="integration", operation="transform")
    async def transform(
        self,
        text: str,
        user_uid: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> Result[DSLTransformResult]:
        """
        Transform natural journal text into DSL format with @context tags.

        This is the main entry point for the bridge service.

        Args:
            text: Natural language journal text
            user_uid: Optional user UID for personalization
            context: Optional context (goals, recent journals, etc.)

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

        if not self.client:
            return Result.fail(
                Errors.integration(
                    service="OpenAI",
                    message="OpenAI client not configured for LLM DSL Bridge",
                    operation="transform",
                )
            )

        transform_result = DSLTransformResult(
            original_text=text,
            transformed_text="",
            model_used=self.model,
        )

        # Select prompt template
        prompt_template = (
            DOMAIN_RECOGNITION_PROMPT_COMPACT
            if self.use_compact_prompt
            else DOMAIN_RECOGNITION_PROMPT
        )

        # Build prompt with journal text
        prompt = prompt_template.format(journal_text=text)

        # Call LLM
        response = await self._call_llm(prompt)

        if response.is_error:
            return Result.fail(response.expect_error())

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
        user_uid: str,
        active_goals: list[dict[str, str]] | None = None,
        recent_topics: list[str] | None = None,
        user_principles: list[str] | None = None,
    ) -> Result[DSLTransformResult]:
        """
        Transform with user context for better domain recognition.

        The context helps the LLM make better decisions about:
        - Linking tasks to existing goals
        - Recognizing knowledge areas the user is learning
        - Aligning with user's stated principles

        Args:
            text: Natural language journal text
            user_uid: User UID
            active_goals: User's active goals (for @goal linking)
            recent_topics: Recent topics the user has journaled about
            user_principles: User's stated principles

        Returns:
            Result containing DSLTransformResult with transformed text
        """
        # Build context-enhanced prompt
        context_block = self._build_context_block(
            active_goals=active_goals,
            recent_topics=recent_topics,
            user_principles=user_principles,
        )

        # Prepend context to journal text
        enhanced_text = text
        if context_block:
            enhanced_text = f"{context_block}\n\n---\n\n{text}"

        return await self.transform(enhanced_text, user_uid)

    def transform_sync(
        self,
        text: str,
        user_uid: str | None = None,
    ) -> Result[DSLTransformResult]:
        """
        Synchronous transformation (for non-async contexts).

        This is a simpler rule-based fallback when LLM is not available
        or for testing purposes.

        Args:
            text: Natural language journal text
            user_uid: Optional user UID

        Returns:
            Result containing DSLTransformResult with transformed text
        """
        transform_result = DSLTransformResult(
            original_text=text,
            transformed_text="",
        )

        # Simple rule-based extraction (fallback)
        activity_lines = self._rule_based_extraction(text)

        self._count_domains(activity_lines, transform_result)

        transform_result.activity_lines = activity_lines
        transform_result.transformed_text = "\n".join(activity_lines)
        transform_result.activities_identified = len(activity_lines)
        transform_result.transform_completed_at = datetime.now()

        return Result.ok(transform_result)

    # ========================================================================
    # PRIVATE METHODS
    # ========================================================================

    @with_error_handling(error_type="integration", operation="call_llm")
    async def _call_llm(self, prompt: str) -> Result[str]:
        """Call the LLM with the prompt and return the response."""
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a structured data extraction assistant. Output only the requested format, no explanations.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            temperature=0.3,  # Lower temperature for more consistent output
            max_tokens=2000,
        )

        content = response.choices[0].message.content
        return Result.ok(content.strip() if content else "")

    def _parse_llm_output(self, output: str) -> list[str]:
        """Parse LLM output into individual activity lines."""
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
                result.learning_steps_identified += 1
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
            return "## USER CONTEXT\n" + "\n".join(parts)

        return ""

    def _rule_based_extraction(self, text: str) -> list[str]:
        """
        Simple rule-based extraction as fallback.

        This is a basic pattern matcher for common activity phrases.
        Not as accurate as LLM but works offline.
        """
        lines = []

        # Task patterns
        task_patterns = [
            "need to",
            "have to",
            "should",
            "must",
            "deadline",
            "by friday",
            "by monday",
            "by tomorrow",
            "due",
        ]

        # Habit patterns
        habit_patterns = [
            "every day",
            "daily",
            "weekly",
            "each morning",
            "start doing",
            "build a habit",
            "regularly",
        ]

        # Finance patterns
        finance_patterns = [
            "spent",
            "paid",
            "cost",
            "bought",
            "purchased",
            "$",
            "dollars",
            "budget",
        ]

        # Event patterns
        event_patterns = [
            "meeting",
            "appointment",
            "call with",
            "lunch with",
            "at 3pm",
            "at 2pm",
            "tomorrow at",
        ]

        # Simple sentence extraction (very basic)
        sentences = text.replace(".", ". ").split(". ")

        for sentence in sentences:
            sentence_lower = sentence.lower().strip()
            if not sentence_lower:
                continue

            # Check patterns
            if any(p in sentence_lower for p in task_patterns):
                lines.append(f"- @context(task) {sentence.strip()}")
            elif any(p in sentence_lower for p in habit_patterns):
                lines.append(f"- @context(habit) {sentence.strip()}")
            elif any(p in sentence_lower for p in finance_patterns):
                lines.append(f"- @context(finance) {sentence.strip()}")
            elif any(p in sentence_lower for p in event_patterns):
                lines.append(f"- @context(event) {sentence.strip()}")

        return lines


# ============================================================================
# FACTORY FUNCTION
# ============================================================================


def create_llm_dsl_bridge(
    openai_api_key: str | None = None,
    model: str = "gpt-4o-mini",
) -> LLMDSLBridgeService:
    """
    Factory function to create an LLM DSL Bridge with proper configuration.

    Args:
        openai_api_key: OpenAI API key (uses env var if not provided)
        model: Model to use (default: gpt-4o-mini for cost efficiency)

    Returns:
        Configured LLMDSLBridgeService instance
    """
    import os

    from openai import AsyncOpenAI

    api_key = openai_api_key or os.getenv("OPENAI_API_KEY")

    if not api_key:
        # Return service without client (will use rule-based fallback)
        return LLMDSLBridgeService(openai_client=None, model=model)

    client = AsyncOpenAI(api_key=api_key)
    return LLMDSLBridgeService(openai_client=client, model=model)
