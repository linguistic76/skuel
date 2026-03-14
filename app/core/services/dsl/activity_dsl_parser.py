"""
SKUEL Activity DSL Parser
=========================

Parses Activity Lines from journal text into structured entities with **type-safe contexts**.

The DSL transforms freeform journal input into SKUEL's domain architecture:

**Activity Domains (6):**
- Tasks: One-time actions with deadlines
- Habits: Recurring behaviors to build
- Goals: Outcomes to achieve
- Events: Scheduled appointments/meetings
- Principles: Values/beliefs to embody
- Choices: Decisions to make

**Curriculum Domains (3):**
- KnowledgeUnit (ku): Atomic unit of knowledge content
- LearningStep (ls): Single step in a learning journey
- LearningPath (lp): Complete learning sequence

**Non-Ku Domains:**
- Finance: Money matters (expenses/income)
- Calendar: Scheduled activity views

**Content Processing:**
- Report: File uploads and processing

**+1 - The Destination:**
- LifePath: Ultimate life goal alignment

This is the bridge from "user speaks/writes" to "structured action".

**DSL Syntax (v0.5 - EntityType/NonKuDomain Contexts):**

```markdown
- [ ] Description @context(task) @when(2025-11-27T09:30) @priority(1)
      @duration(90m) @energy(focus) @ku(ku:sel/mindfulness) @link(goal:health)
```

**Required:** `@context()` - determines entity type (uses EntityType or NonKuDomain enums)
**Optional:** All other tags

**Type Safety:**

The `@context()` tag values are now parsed to `EntityType` or `NonKuDomain` enum values, providing:
- Compile-time verification of valid context values
- IDE autocomplete for entity types
- Exhaustiveness checking in pattern matching
- Clear error messages for invalid context strings
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.models.enums.entity_enums import EntityType, NonKuDomain
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

# DSL-specific aliases that map user-facing context strings to EntityType/NonKuDomain.
# EntityType.from_string() handles most aliases (e.g. "ku" -> KU, "ls" -> LEARNING_STEP),
# but DSL historically accepted some forms not in the EntityType alias table.
_DSL_CONTEXT_ALIASES: dict[str, EntityType | NonKuDomain] = {
    "learningstep": EntityType.LEARNING_STEP,
    "learningpath": EntityType.LEARNING_PATH,
    "journal": EntityType.JOURNAL_SUBMISSION,
    "life_path": EntityType.LIFE_PATH,
}

# ============================================================================
# PARSED ACTIVITY LINE (Intermediate Representation)
# ============================================================================


@dataclass
class ParsedActivityLine:
    """
    Intermediate representation of a parsed Activity Line.

    This is the output of the parser - a structured representation
    that can be converted to domain-specific entities (Task, Habit, etc.).

    **Type Safety:**

    The `contexts` field uses `list[EntityType | NonKuDomain]` instead of `list[str]`,
    providing compile-time verification of valid entity types. This means:

    - `EntityType.TASK in contexts` instead of `"task" in contexts`
    - Invalid context strings are caught during parsing, not at entity creation
    - IDE autocomplete shows all valid EntityType/NonKuDomain values

    **Fields:**

    All fields are optional except `description` and `contexts`.

    Attributes:
        description: Human-readable activity description
        contexts: List of EntityType/NonKuDomain values from @context() tag (type-safe)
        when: Optional datetime from @when() tag
        duration_minutes: Optional duration in minutes from @duration() tag
        repeat_pattern: Optional repeat configuration from @repeat() tag
        priority: Optional priority 1-5 from @priority() tag
        energy_states: List of energy states from @energy() tag
        primary_ku: Optional primary KnowledgeUnit UID from @ku() tag
        links: List of graph links from @link() tag
        source_file: Optional source file path for tracking
        source_line: Optional line number in source
        raw_line: Original unparsed line text
        is_checked: Whether checkbox is checked ([x] vs [ ])

    Example:
        ```python
        activity = ParsedActivityLine(
            description="Call mom",
            contexts=[EntityType.TASK],
            priority=1,
        )

        # Type-safe context checking
        if EntityType.TASK in activity.contexts:
            create_task(activity)

        # Or use helper methods
        if activity.is_task():
            create_task(activity)
        ```

    See Also:
        - EntityType: Enum defining Ku-based context values
        - NonKuDomain: Enum defining non-Ku context values (Finance, Calendar, Learning)
        - ActivityDSLParser: Parser that creates ParsedActivityLine instances
    """

    # Core content
    description: str
    contexts: list[
        EntityType | NonKuDomain
    ]  # Type-safe: [EntityType.TASK], [EntityType.HABIT, NonKuDomain.LEARNING]

    # Temporal
    when: datetime | None = None  # @when(2025-11-27T09:30)
    duration_minutes: int | None = None  # @duration(90m)
    repeat_pattern: dict[str, Any] | None = None  # @repeat(daily)

    # Importance
    priority: int | None = None  # @priority(1) - 1=highest, 5=lowest

    # Energy/behavioral
    energy_states: list[str] = field(default_factory=list)  # @energy(focus,creative)

    # Knowledge graph connections
    primary_ku: str | None = None  # @ku(ku:sel/mindfulness)
    links: list[dict[str, str]] = field(default_factory=list)  # @link(goal:health)

    # Source tracking
    source_file: str | None = None
    source_line: int | None = None
    raw_line: str | None = None

    # Checkbox state
    is_checked: bool = False  # [x] vs [ ]

    # ========================================================================
    # ACTIVITY DOMAINS (7) - Type-Safe Checks
    # ========================================================================

    def is_task(self) -> bool:
        """
        Check if this is a task activity.

        Returns:
            True if EntityType.TASK is in contexts
        """
        return EntityType.TASK in self.contexts

    def is_habit(self) -> bool:
        """
        Check if this is a habit activity.

        Returns:
            True if EntityType.HABIT is in contexts
        """
        return EntityType.HABIT in self.contexts

    def is_goal(self) -> bool:
        """
        Check if this is a goal activity.

        Returns:
            True if EntityType.GOAL is in contexts
        """
        return EntityType.GOAL in self.contexts

    def is_event(self) -> bool:
        """
        Check if this is an event activity.

        Returns:
            True if EntityType.EVENT is in contexts
        """
        return EntityType.EVENT in self.contexts

    def is_learning(self) -> bool:
        """
        Check if this is a learning activity.

        Returns:
            True if NonKuDomain.LEARNING is in contexts
        """
        return NonKuDomain.LEARNING in self.contexts

    def is_principle(self) -> bool:
        """
        Check if this is a principle activity.

        Returns:
            True if EntityType.PRINCIPLE is in contexts
        """
        return EntityType.PRINCIPLE in self.contexts

    def is_choice(self) -> bool:
        """
        Check if this is a choice/decision activity.

        Returns:
            True if EntityType.CHOICE is in contexts
        """
        return EntityType.CHOICE in self.contexts

    def is_finance(self) -> bool:
        """
        Check if this is a finance/expense activity.

        Returns:
            True if NonKuDomain.FINANCE is in contexts
        """
        return NonKuDomain.FINANCE in self.contexts

    # ========================================================================
    # CURRICULUM DOMAINS (3) - Type-Safe Checks
    # ========================================================================

    def is_lesson(self) -> bool:
        """
        Check if this is a Lesson activity.

        Returns:
            True if EntityType.LESSON is in contexts
        """
        return EntityType.LESSON in self.contexts

    def is_ls(self) -> bool:
        """
        Check if this is a LearningStep activity.

        Returns:
            True if EntityType.LEARNING_STEP is in contexts
        """
        return EntityType.LEARNING_STEP in self.contexts

    def is_lp(self) -> bool:
        """
        Check if this is a LearningPath activity.

        Returns:
            True if EntityType.LEARNING_PATH is in contexts
        """
        return EntityType.LEARNING_PATH in self.contexts

    # ========================================================================
    # META DOMAINS (3) - Type-Safe Checks
    # ========================================================================

    def is_report(self) -> bool:
        """
        Check if this is a Report activity (file uploads, processing).

        Returns:
            True if EntityType.SUBMISSION is in contexts
        """
        return EntityType.EXERCISE_SUBMISSION in self.contexts

    def is_calendar(self) -> bool:
        """
        Check if this is a Calendar activity.

        Returns:
            True if NonKuDomain.CALENDAR is in contexts
        """
        return NonKuDomain.CALENDAR in self.contexts

    # ========================================================================
    # THE DESTINATION (+1) - Type-Safe Check
    # ========================================================================

    def is_lifepath(self) -> bool:
        """
        Check if this is a LifePath alignment activity.

        Returns:
            True if EntityType.LIFE_PATH is in contexts
        """
        return EntityType.LIFE_PATH in self.contexts

    @property
    def primary_context(self) -> EntityType | NonKuDomain | None:
        """
        Get the primary (first) context for this activity.

        Returns:
            The first EntityType or NonKuDomain in contexts, or None if contexts is empty
        """
        return self.contexts[0] if self.contexts else None

    @property
    def context_values(self) -> list[str]:
        """
        Get context values as strings (for serialization/logging).

        This provides backward compatibility for code that expects string contexts.

        Returns:
            List of context string values (e.g., ["task", "learning"])
        """
        return [ctx.value for ctx in self.contexts]

    # ========================================================================
    # LINK EXTRACTION METHODS
    # ========================================================================

    def get_linked_goals(self) -> list[str]:
        """Get goal UIDs from @link() tags."""
        return [link["id"] for link in self.links if link.get("type") == EntityType.GOAL.value]

    def get_linked_principles(self) -> list[str]:
        """Get principle UIDs from @link() tags."""
        return [link["id"] for link in self.links if link.get("type") == EntityType.PRINCIPLE.value]

    def get_linked_knowledge(self) -> list[str]:
        """Get all knowledge UIDs (primary + linked)."""
        uids = []
        if self.primary_ku:
            uids.append(self.primary_ku)
        uids.extend(
            [
                link["id"]
                for link in self.links
                if link.get("type") in (EntityType.LESSON.value, EntityType.KU.value)
            ]
        )
        return uids

    def get_linked_choices(self) -> list[str]:
        """Get choice UIDs from @link() tags."""
        return [link["id"] for link in self.links if link.get("type") == EntityType.CHOICE.value]

    def get_amount(self) -> float | None:
        """
        Extract amount from description for finance activities.

        Looks for patterns like: $50, $100.50, 50 USD, etc.
        """
        # Match patterns: $50, $100.50, 50.00
        pattern = r"\$?([\d,]+\.?\d*)"
        match = re.search(pattern, self.description)
        if match:
            try:
                # Remove commas and convert to float
                amount_str = match.group(1).replace(",", "")
                return float(amount_str)
            except ValueError:
                return None
        return None


# ============================================================================
# PARSER RESULT (Batch)
# ============================================================================


@dataclass
class ParsedJournal:
    """
    Result of parsing a full journal entry.

    Contains all parsed activity lines plus metadata.

    Attributes:
        activities: List of ParsedActivityLine instances with type-safe contexts
        total_lines: Total number of lines in the source text
        activity_lines_found: Number of lines successfully parsed as activities
        parse_errors: List of error messages for failed parses
        source_file: Optional source file path
    """

    activities: list[ParsedActivityLine]

    # Statistics
    total_lines: int = 0
    activity_lines_found: int = 0
    parse_errors: list[str] = field(default_factory=list)

    # Source
    source_file: str | None = None

    # ========================================================================
    # ACTIVITY DOMAINS (7) - Filtered Accessors
    # ========================================================================

    def get_tasks(self) -> list[ParsedActivityLine]:
        """Get all task activities."""
        return [a for a in self.activities if a.is_task()]

    def get_habits(self) -> list[ParsedActivityLine]:
        """Get all habit activities."""
        return [a for a in self.activities if a.is_habit()]

    def get_goals(self) -> list[ParsedActivityLine]:
        """Get all goal activities."""
        return [a for a in self.activities if a.is_goal()]

    def get_events(self) -> list[ParsedActivityLine]:
        """Get all event activities."""
        return [a for a in self.activities if a.is_event()]

    def get_principles(self) -> list[ParsedActivityLine]:
        """Get all principle activities."""
        return [a for a in self.activities if a.is_principle()]

    def get_choices(self) -> list[ParsedActivityLine]:
        """Get all choice/decision activities."""
        return [a for a in self.activities if a.is_choice()]

    def get_finances(self) -> list[ParsedActivityLine]:
        """Get all finance/expense activities."""
        return [a for a in self.activities if a.is_finance()]

    # ========================================================================
    # CURRICULUM DOMAINS (3) - Filtered Accessors
    # ========================================================================

    def get_knowledge_units(self) -> list[ParsedActivityLine]:
        """Get all KnowledgeUnit activities."""
        return [a for a in self.activities if a.is_lesson()]

    def get_learning_steps(self) -> list[ParsedActivityLine]:
        """Get all LearningStep activities."""
        return [a for a in self.activities if a.is_ls()]

    def get_learning_paths(self) -> list[ParsedActivityLine]:
        """Get all LearningPath activities."""
        return [a for a in self.activities if a.is_lp()]

    # ========================================================================
    # META DOMAINS (3) - Filtered Accessors
    # ========================================================================

    def get_reports(self) -> list[ParsedActivityLine]:
        """Get all Report activities."""
        return [a for a in self.activities if a.is_report()]

    def get_calendar_items(self) -> list[ParsedActivityLine]:
        """Get all Calendar activities."""
        return [a for a in self.activities if a.is_calendar()]

    # ========================================================================
    # THE DESTINATION (+1) - Filtered Accessor
    # ========================================================================

    def get_lifepath_items(self) -> list[ParsedActivityLine]:
        """Get all LifePath alignment activities."""
        return [a for a in self.activities if a.is_lifepath()]


# ============================================================================
# DSL PARSER
# ============================================================================


class ActivityDSLParser:
    """
    Parser for SKUEL Activity DSL with type-safe EntityType/NonKuDomain contexts.

    Extracts structured activity data from markdown text containing
    Activity Lines with @context(), @when(), @priority(), etc. tags.

    **Type Safety:**

    The parser converts @context() string values to EntityType or NonKuDomain enum
    values, providing compile-time verification. Invalid context strings result
    in parse errors with clear messages listing valid options.

    **Usage:**

    ```python
    parser = ActivityDSLParser()

    # Parse single line
    result = parser.parse_line("- [ ] Call mom @context(task) @priority(1)")
    if result.is_ok:
        activity = result.value
        print(activity.description)  # "Call mom"
        print(activity.contexts)  # [EntityType.TASK]
        print(activity.priority)  # 1

        # Type-safe context checking
        if EntityType.TASK in activity.contexts:
            print("This is a task!")

    # Parse full journal
    journal_text = '''
    ### Today's Focus

    - [ ] Morning meditation @context(habit) @duration(20m) @energy(spiritual)
    - [ ] Write proposal @context(task) @priority(1) @when(2025-11-27T09:00)
    - [ ] Learn Python async @context(learning) @ku(ku:tech/python-async)
    '''

    result = parser.parse_journal(journal_text)
    if result.is_ok:
        parsed = result.value
        for task in parsed.get_tasks():
            print(f"Task: {task.description}")
    ```

    **Error Handling:**

    Invalid context values produce clear error messages:

    ```python
    result = parser.parse_line("- [ ] Test @context(invalid_type)")
    if result.is_error:
        print(result.error.user_message)
        # "Invalid context types: ['invalid_type']. Valid types: task, habit, goal, ..."
    ```

    See Also:
        - EntityType: Enum defining Ku-based context values
        - NonKuDomain: Enum defining non-Ku context values
        - ParsedActivityLine: The parsed activity representation
        - ParsedJournal: Collection of parsed activities
    """

    # ========================================================================
    # REGEX PATTERNS
    # ========================================================================

    # Tag extraction pattern: @tag(value)
    TAG_PATTERN = re.compile(r"@([a-zA-Z_][a-zA-Z0-9_]*)\(([^)]*)\)")

    # Checkbox patterns
    CHECKBOX_UNCHECKED = re.compile(r"^[-*]\s*\[\s*\]\s*")
    CHECKBOX_CHECKED = re.compile(r"^[-*]\s*\[[xX]\]\s*")
    BULLET_ONLY = re.compile(r"^[-*]\s+")

    # Timestamp formats
    ISO_DATETIME_T = re.compile(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})")
    ISO_DATETIME_SPACE = re.compile(r"(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})")

    # Duration format: 90m, 1h, 1h30m
    DURATION_PATTERN = re.compile(r"(?:(\d+)h)?(?:(\d+)m)?")

    def __init__(self) -> None:
        """Initialize the parser."""
        self.logger = get_logger("skuel.dsl.parser")

    # ========================================================================
    # MAIN PARSING METHODS
    # ========================================================================

    def parse_line(
        self, line: str, source_file: str | None = None, source_line_num: int | None = None
    ) -> Result[ParsedActivityLine]:
        """
        Parse a single Activity Line with type-safe context validation.

        An Activity Line MUST contain @context() to be valid. The context
        values are validated against EntityType and NonKuDomain enums - invalid
        values produce clear error messages.

        Args:
            line: The raw line text
            source_file: Optional source file path for tracking
            source_line_num: Optional line number in source

        Returns:
            Result containing ParsedActivityLine with EntityType/NonKuDomain contexts, or error

        Example:
            ```python
            result = parser.parse_line("- [ ] Call mom @context(task) @priority(1)")
            if result.is_ok:
                activity = result.value
                assert EntityType.TASK in activity.contexts  # Type-safe!
            ```
        """
        if not line or not line.strip():
            return Result.fail(
                Errors.validation(
                    message="Empty line",
                    field="line",
                    value=line,
                )
            )

        # Check for @context() - required for Activity Line
        if "@context(" not in line:
            return Result.fail(
                Errors.validation(
                    message="Not an Activity Line (missing @context)",
                    field="line",
                    value=line[:50],
                )
            )

        try:
            # Extract all tags
            tags = self._extract_tags(line)

            # Validate @context exists and has values
            if "context" not in tags or not tags["context"]:
                return Result.fail(
                    Errors.validation(
                        message="@context() is empty",
                        field="context",
                        value="",
                    )
                )

            # Parse contexts to EntityType/NonKuDomain (type-safe)
            contexts_result = self._parse_contexts(tags["context"])
            if contexts_result.is_error:
                return Result.fail(contexts_result.expect_error())

            contexts = contexts_result.value

            # Extract description (everything before first @tag, minus checkbox)
            description = self._extract_description(line)

            # Check checkbox state
            is_checked = bool(self.CHECKBOX_CHECKED.match(line))

            # Parse optional tags
            when = self._parse_when(tags.get("when"))
            priority = self._parse_priority(tags.get("priority"))
            duration = self._parse_duration(tags.get("duration"))
            energy = self._parse_list_value(tags.get("energy", ""))
            repeat = self._parse_repeat(tags.get("repeat"))
            primary_ku = self._parse_ku(tags.get("ku"))
            links = self._parse_links(tags.get("link", ""))

            activity = ParsedActivityLine(
                description=description,
                contexts=contexts,
                when=when,
                priority=priority,
                duration_minutes=duration,
                energy_states=energy,
                repeat_pattern=repeat,
                primary_ku=primary_ku,
                links=links,
                source_file=source_file,
                source_line=source_line_num,
                raw_line=line,
                is_checked=is_checked,
            )

            self.logger.debug(
                f"Parsed activity: '{description[:30]}...' "
                f"contexts={[c.value for c in contexts]} priority={priority}"
            )

            return Result.ok(activity)

        except Exception as e:
            self.logger.warning(f"Parse error for line: {line[:50]}... - {e}")
            return Result.fail(
                Errors.system(
                    message=f"Parse error: {e}",
                    operation="parse_line",
                    exception=e,
                )
            )

    def parse_journal(self, text: str, source_file: str | None = None) -> Result[ParsedJournal]:
        """
        Parse a full journal/document for Activity Lines.

        Scans all lines and extracts those containing @context().
        Each context value is validated against EntityType and NonKuDomain enums.

        Args:
            text: Full document text
            source_file: Optional source file path

        Returns:
            Result containing ParsedJournal with all activities (type-safe contexts)
        """
        if not text:
            return Result.ok(
                ParsedJournal(
                    activities=[],
                    total_lines=0,
                    activity_lines_found=0,
                    source_file=source_file,
                )
            )

        lines = text.split("\n")
        activities: list[ParsedActivityLine] = []
        errors: list[str] = []

        for line_num, line in enumerate(lines, start=1):
            # Skip lines without @context
            if "@context(" not in line:
                continue

            result = self.parse_line(line, source_file, line_num)

            if result.is_ok:
                activities.append(result.value)
            else:
                errors.append(
                    f"Line {line_num}: {result.error.user_message if result.error else 'Unknown error'}"
                )

        parsed = ParsedJournal(
            activities=activities,
            total_lines=len(lines),
            activity_lines_found=len(activities),
            parse_errors=errors,
            source_file=source_file,
        )

        self.logger.info(
            f"Parsed journal: {len(activities)} activities from {len(lines)} lines "
            f"({len(errors)} errors)"
        )

        return Result.ok(parsed)

    # ========================================================================
    # TAG EXTRACTION
    # ========================================================================

    def _extract_tags(self, line: str) -> dict[str, str]:
        """
        Extract all @tag(value) pairs from a line.

        Returns dict mapping tag name to raw value string.
        """
        tags = {}
        for match in self.TAG_PATTERN.finditer(line):
            tag_name = match.group(1).lower()
            tag_value = match.group(2).strip()
            tags[tag_name] = tag_value
        return tags

    def _extract_description(self, line: str) -> str:
        """
        Extract the human-readable description from the line.

        Steps:
        1. Remove leading checkbox/bullet
        2. Remove all @tag() segments
        3. Trim whitespace
        """
        # Remove checkbox or bullet
        text = self.CHECKBOX_UNCHECKED.sub("", line)
        text = self.CHECKBOX_CHECKED.sub("", text)
        text = self.BULLET_ONLY.sub("", text)

        # Remove all @tag() segments
        text = self.TAG_PATTERN.sub("", text)

        # Clean up whitespace
        text = " ".join(text.split())

        return text.strip()

    # ========================================================================
    # VALUE PARSERS
    # ========================================================================

    def _parse_contexts(self, value: str) -> Result[list[EntityType | NonKuDomain]]:
        """
        Parse @context() value to typed EntityType/NonKuDomain list.

        Converts comma-separated context strings to EntityType or NonKuDomain enum
        values. EntityType is tried first (covers most domains), then NonKuDomain
        (Finance, Calendar, Learning, Group). Invalid context strings produce a
        validation error with the list of valid options.

        Args:
            value: Raw @context() value (e.g., "task", "habit,learning")

        Returns:
            Result containing list of EntityType/NonKuDomain values, or validation error

        Example:
            ```python
            result = self._parse_contexts("task,learning")
            # Returns Result.ok([EntityType.TASK, NonKuDomain.LEARNING])

            result = self._parse_contexts("invalid")
            # Returns Result.fail(ValidationError with valid options)
            ```
        """
        contexts: list[EntityType | NonKuDomain] = []
        invalid: list[str] = []

        for v in value.split(","):
            v = v.strip().lower()
            if not v:
                continue

            # Check DSL-specific aliases first (e.g. "learningstep", "journal")
            dsl_alias = _DSL_CONTEXT_ALIASES.get(v)
            if dsl_alias is not None:
                contexts.append(dsl_alias)
                continue

            # Try EntityType (covers most domains)
            entity_type = EntityType.from_string(v)
            if entity_type is not None:
                contexts.append(entity_type)
                continue

            # Try NonKuDomain (Finance, Calendar, Learning, Group)
            non_ku = NonKuDomain.from_string(v)
            if non_ku is not None:
                contexts.append(non_ku)
                continue

            invalid.append(v)

        if invalid:
            # Build helpful error message with valid options from both enums
            all_values = sorted({e.value for e in EntityType} | {e.value for e in NonKuDomain})
            valid_options = ", ".join(all_values)
            return Result.fail(
                Errors.validation(
                    message=f"Invalid context types: {invalid}. Valid types: {valid_options}",
                    field="context",
                    value=value,
                )
            )

        if not contexts:
            return Result.fail(
                Errors.validation(
                    message="@context() must contain at least one valid entity type",
                    field="context",
                    value=value,
                )
            )

        return Result.ok(contexts)

    def _parse_list_value(self, value: str) -> list[str]:
        """Parse comma-separated values into list (for non-EntityType fields)."""
        if not value:
            return []
        return [v.strip().lower() for v in value.split(",") if v.strip()]

    def _parse_when(self, value: str | None) -> datetime | None:
        """
        Parse @when() timestamp.

        Accepts:
        - 2025-11-27T09:30 (ISO with T)
        - 2025-11-27 09:30 (ISO with space)
        """
        if not value:
            return None

        # Try ISO with T
        match = self.ISO_DATETIME_T.match(value)
        if match:
            year, month, day, hour, minute = map(int, match.groups())
            return datetime(year, month, day, hour, minute)

        # Try ISO with space
        match = self.ISO_DATETIME_SPACE.match(value)
        if match:
            year, month, day, hour, minute = map(int, match.groups())
            return datetime(year, month, day, hour, minute)

        self.logger.warning(f"Could not parse @when value: {value}")
        return None

    def _parse_priority(self, value: str | None) -> int | None:
        """Parse @priority() value (1-5)."""
        if not value:
            return None
        try:
            priority = int(value)
            if 1 <= priority <= 5:
                return priority
            self.logger.warning(f"Priority {priority} out of range 1-5, ignoring")
            return None
        except ValueError:
            self.logger.warning(f"Invalid priority value: {value}")
            return None

    def _parse_duration(self, value: str | None) -> int | None:
        """
        Parse @duration() value to minutes.

        Accepts: 90m, 1h, 1h30m, 2h15m
        """
        if not value:
            return None

        total_minutes = 0

        # Extract hours
        hours_match = re.search(r"(\d+)h", value)
        if hours_match:
            total_minutes += int(hours_match.group(1)) * 60

        # Extract minutes
        mins_match = re.search(r"(\d+)m", value)
        if mins_match:
            total_minutes += int(mins_match.group(1))

        return total_minutes if total_minutes > 0 else None

    def _parse_repeat(self, value: str | None) -> dict[str, Any] | None:
        """
        Parse @repeat() pattern.

        Accepts:
        - daily
        - weekly:Mon,Wed,Fri
        - monthly:1,15
        - every:3d
        - custom
        """
        if not value:
            return None

        value = value.strip().lower()

        if value == "daily":
            return {"type": "daily"}

        if value == "custom":
            return {"type": "custom"}

        if value.startswith("weekly:"):
            days_str = value[7:]  # Remove "weekly:"
            days = [d.strip().capitalize() for d in days_str.split(",")]
            return {"type": "weekly", "days": days}

        if value.startswith("monthly:"):
            days_str = value[8:]  # Remove "monthly:"
            day_numbers = [int(d.strip()) for d in days_str.split(",") if d.strip().isdigit()]
            return {"type": "monthly", "days": day_numbers}

        if value.startswith("every:"):
            interval_str = value[6:]  # Remove "every:"
            match = re.match(r"(\d+)([dhwm])", interval_str)
            if match:
                amount = int(match.group(1))
                unit_map = {"d": "days", "h": "hours", "w": "weeks", "m": "months"}
                unit = unit_map.get(match.group(2), "days")
                return {"type": "interval", "interval": amount, "unit": unit}

        self.logger.warning(f"Unknown repeat pattern: {value}")
        return None

    def _parse_ku(self, value: str | None) -> str | None:
        """
        Parse @ku() knowledge unit reference.

        Expected format: ku:namespace/slug
        Returns the full UID string.
        """
        if not value:
            return None

        # Clean up the value
        value = value.strip()

        # Validate format (should start with ku:)
        if not value.startswith("ku:"):
            self.logger.warning(f"Invalid KU format (missing ku: prefix): {value}")
            # Be lenient - add prefix if missing
            return f"ku:{value}"

        return value

    def _parse_links(self, value: str) -> list[dict[str, str]]:
        """
        Parse @link() connections.

        Format: type:id[, type:id...]

        Returns list of dicts: [{"type": "goal", "id": "goal:health/fitness"}, ...]
        """
        if not value:
            return []

        links = []
        for link_str in value.split(","):
            link_str = link_str.strip()
            if ":" in link_str:
                # Split on first colon only (id may contain colons)
                parts = link_str.split(":", 1)
                if len(parts) == 2:
                    link_type = parts[0].strip().lower()
                    link_id = parts[1].strip()

                    # Normalize DSL prefix to EntityType value
                    # e.g. @link(ku:...) -> type="lesson" (EntityType.LESSON)
                    normalized = EntityType.from_string(link_type)
                    if normalized is not None:
                        link_type = normalized.value

                    # Reconstruct full UID if needed
                    if link_type in ("goal", "principle", "project", "person", "vortex"):
                        # These don't need prefix in the ID
                        full_id = f"{link_type}:{link_id}"
                    else:
                        full_id = link_str  # Keep as-is (e.g., ku:namespace/slug)

                    links.append({"type": link_type, "id": full_id})

        return links


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================


def parse_activity_line(line: str) -> Result[ParsedActivityLine]:
    """
    Convenience function to parse a single Activity Line.

    Args:
        line: Raw line text containing @context() and other tags

    Returns:
        Result containing ParsedActivityLine with type-safe EntityType/NonKuDomain contexts

    Example:
        ```python
        result = parse_activity_line("- [ ] Call mom @context(task)")
        if result.is_ok:
            assert EntityType.TASK in result.value.contexts
        ```
    """
    parser = ActivityDSLParser()
    return parser.parse_line(line)


def parse_journal_text(text: str) -> Result[ParsedJournal]:
    """
    Convenience function to parse journal text.

    Args:
        text: Full journal text

    Returns:
        Result containing ParsedJournal with all activities (type-safe EntityType/NonKuDomain contexts)
    """
    parser = ActivityDSLParser()
    return parser.parse_journal(text)


def is_activity_line(line: str) -> bool:
    """
    Quick check if a line is an Activity Line.

    Activity Lines contain @context().
    """
    return "@context(" in line
