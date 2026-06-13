"""
Activity Extractor Service
==========================

Extracts Activity Lines from UserEntry content and creates corresponding
SKUEL entities:

**Activity Domains (7) - What I DO:**
- Tasks, Habits, Goals, Events (original 4)
- Principles, Choices, Finance (added for 7-domain completeness)

**Curriculum Domains (3) - What I LEARN:**
- KnowledgeUnit (KU), PathStep (PS), LearningPath (LP)

**Meta Domain (1) - How I ORGANIZE:**
- Calendar

**The Destination (+1) - Where I'm GOING:**
- LifePath (the ultimate life goal)

**Design Principles:**

1. **Non-destructive**: Extraction doesn't modify the entry content
2. **Two-guard idempotency** (ADR-069): the completed-run metadata guard lives
   in `UserEntryProcessingService._run_extract_activities` (re-process is a
   no-op without `force`); per-line SHA-256 hash dedup against existing
   `EXTRACTED_FROM` edges makes re-extraction skip already-extracted lines —
   it never mutates or duplicates entities.
3. **Graph-aware**: Creates entities connected to the user's ownership graph;
   the caller writes `(created)-[:EXTRACTED_FROM]->(entry)` provenance from
   `ActivityExtractionResult.created_links`.
4. **Ownership-gated**: curriculum (`@context(ku|ls|lp)`) *creation* lines
   require `allow_curriculum_creation` (teacher/admin —
   `User.can_create_curriculum()`); `@ku()` *references* always resolve.

Wired as the `Pipeline.EXTRACT_ACTIVITIES` branch of
`UserEntryProcessingService.process()` (ADR-069 Decision 1).
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.models.type_hints import UserUID
from core.models.user_entry.user_entry import UserEntry
from core.services.dsl.activity_domain_converters import (
    # Activity Domains (6)
    activity_to_choice_request,
    activity_to_event_request,
    activity_to_goal_request,
    activity_to_habit_request,
    activity_to_principle_request,
    activity_to_task_request,
)
from core.services.dsl.activity_dsl_parser import (
    ActivityDSLParser,
    ParsedActivityLine,
)
from core.services.dsl.specialized_domain_converters import (
    # Meta Domains (2)
    activity_to_calendar_dict,
    activity_to_finance_dict,
    # Curriculum Domains (3)
    activity_to_ku_dict,
    # The Destination (+1)
    activity_to_lifepath_dict,
    activity_to_lp_dict,
    activity_to_ps_dict,
)
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

# ============================================================================
# LINE PROVENANCE
# ============================================================================


def normalized_line_hash(raw_line: str) -> str:
    """SHA-256 of the whitespace-normalized DSL line.

    The `source_line_hash` provenance/dedup key on `EXTRACTED_FROM` edges:
    stable across re-indentation and whitespace edits, distinct per line
    content.
    """
    return hashlib.sha256(" ".join(raw_line.split()).encode("utf-8")).hexdigest()


# ============================================================================
# EXTRACTION RESULT
# ============================================================================


@dataclass
class ActivityExtractionResult:
    """
    Result of activity extraction from a UserEntry.

    Contains counts of created entities across the DSL-extractable SKUEL
    domains, per-entity line provenance (`created_links`), resolved `@ku()`
    references, and any errors encountered.

    **Domain Categories:**
    - Activity Domains (7): Tasks, Habits, Goals, Events, Principles, Choices, Finance
    - Curriculum Domains (3): KU, PS, LP
    - Meta Domain (1): Calendar
    - The Destination (+1): LifePath
    """

    # Source
    entry_uid: str
    user_uid: UserUID

    # ========================================================================
    # PARSED ACTIVITIES - FOUND COUNTS
    # ========================================================================
    activities_found: int = 0

    # Activity Domains (7)
    tasks_found: int = 0
    habits_found: int = 0
    goals_found: int = 0
    events_found: int = 0
    principles_found: int = 0
    choices_found: int = 0
    finances_found: int = 0

    # Curriculum Domains (3)
    kus_found: int = 0
    path_steps_found: int = 0
    learning_paths_found: int = 0

    # Meta Domain (1)
    calendar_items_found: int = 0

    # The Destination (+1)
    lifepath_items_found: int = 0

    # ========================================================================
    # CREATED ENTITIES - CREATED COUNTS
    # ========================================================================

    # Activity Domains (7)
    tasks_created: int = 0
    habits_created: int = 0
    goals_created: int = 0
    events_created: int = 0
    principles_created: int = 0
    choices_created: int = 0
    finances_created: int = 0

    # Curriculum Domains (3)
    kus_created: int = 0
    path_steps_created: int = 0
    learning_paths_created: int = 0

    # Meta Domain (1)
    calendar_items_created: int = 0

    # The Destination (+1)
    lifepath_items_created: int = 0

    # ========================================================================
    # ENTITY UIDS (for relationship creation)
    # ========================================================================

    # Activity Domains (7)
    created_task_uids: list[str] = field(default_factory=list)
    created_habit_uids: list[str] = field(default_factory=list)
    created_goal_uids: list[str] = field(default_factory=list)
    created_event_uids: list[str] = field(default_factory=list)
    created_principle_uids: list[str] = field(default_factory=list)
    created_choice_uids: list[str] = field(default_factory=list)
    created_finance_uids: list[str] = field(default_factory=list)

    # Curriculum Domains (3)
    created_ku_uids: list[str] = field(default_factory=list)
    created_ps_uids: list[str] = field(default_factory=list)
    created_lp_uids: list[str] = field(default_factory=list)

    # Meta Domain (1)
    created_calendar_uids: list[str] = field(default_factory=list)

    # The Destination (+1)
    created_lifepath_uids: list[str] = field(default_factory=list)

    # ========================================================================
    # PROVENANCE & KNOWLEDGE LINKS (ADR-069)
    # ========================================================================
    # (created_uid, source_line_hash) pairs across all domains — the input to
    # the EXTRACTED_FROM batch edge write.
    created_links: list[tuple[str, str]] = field(default_factory=list)
    # Deduped Ku UIDs referenced via @ku()/linked-knowledge tags on any parsed
    # line (including dedup-skipped ones) — APPLIES_KNOWLEDGE candidates.
    referenced_ku_uids: list[str] = field(default_factory=list)
    # Lines skipped because their hash already has an EXTRACTED_FROM edge.
    lines_skipped_existing: int = 0

    # ========================================================================
    # ERRORS & TIMING
    # ========================================================================
    parse_errors: list[str] = field(default_factory=list)
    creation_errors: list[str] = field(default_factory=list)
    extraction_started_at: datetime = field(default_factory=datetime.now)
    extraction_completed_at: datetime | None = None

    @property
    def total_created(self) -> int:
        """Total entities created across all entity types."""
        return (
            # Activity Domains (7)
            self.tasks_created
            + self.habits_created
            + self.goals_created
            + self.events_created
            + self.principles_created
            + self.choices_created
            + self.finances_created
            # Curriculum Domains (3)
            + self.kus_created
            + self.path_steps_created
            + self.learning_paths_created
            # Meta Domain (1)
            + self.calendar_items_created
            # The Destination (+1)
            + self.lifepath_items_created
        )

    @property
    def has_errors(self) -> bool:
        """Check if any errors occurred."""
        return len(self.parse_errors) > 0 or len(self.creation_errors) > 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage in entry metadata."""
        return {
            "activities_found": self.activities_found,
            # ================================================================
            # Found counts - Activity Domains (7)
            # ================================================================
            "tasks_found": self.tasks_found,
            "habits_found": self.habits_found,
            "goals_found": self.goals_found,
            "events_found": self.events_found,
            "principles_found": self.principles_found,
            "choices_found": self.choices_found,
            "finances_found": self.finances_found,
            # Curriculum Domains (3)
            "kus_found": self.kus_found,
            "path_steps_found": self.path_steps_found,
            "learning_paths_found": self.learning_paths_found,
            # Meta Domain (1)
            "calendar_items_found": self.calendar_items_found,
            # The Destination (+1)
            "lifepath_items_found": self.lifepath_items_found,
            # ================================================================
            # Created counts - Activity Domains (7)
            # ================================================================
            "tasks_created": self.tasks_created,
            "habits_created": self.habits_created,
            "goals_created": self.goals_created,
            "events_created": self.events_created,
            "principles_created": self.principles_created,
            "choices_created": self.choices_created,
            "finances_created": self.finances_created,
            # Curriculum Domains (3)
            "kus_created": self.kus_created,
            "path_steps_created": self.path_steps_created,
            "learning_paths_created": self.learning_paths_created,
            # Meta Domain (1)
            "calendar_items_created": self.calendar_items_created,
            # The Destination (+1)
            "lifepath_items_created": self.lifepath_items_created,
            # ================================================================
            # Created UIDs - Activity Domains (7)
            # ================================================================
            "created_task_uids": self.created_task_uids,
            "created_habit_uids": self.created_habit_uids,
            "created_goal_uids": self.created_goal_uids,
            "created_event_uids": self.created_event_uids,
            "created_principle_uids": self.created_principle_uids,
            "created_choice_uids": self.created_choice_uids,
            "created_finance_uids": self.created_finance_uids,
            # Curriculum Domains (3)
            "created_ku_uids": self.created_ku_uids,
            "created_ps_uids": self.created_ps_uids,
            "created_lp_uids": self.created_lp_uids,
            # Meta Domain (1)
            "created_calendar_uids": self.created_calendar_uids,
            # The Destination (+1)
            "created_lifepath_uids": self.created_lifepath_uids,
            # ================================================================
            # Provenance & knowledge links (ADR-069)
            # ================================================================
            "created_links": [[uid, line_hash] for uid, line_hash in self.created_links],
            "referenced_ku_uids": self.referenced_ku_uids,
            "lines_skipped_existing": self.lines_skipped_existing,
            # ================================================================
            # Aggregates
            # ================================================================
            "total_created": self.total_created,
            "parse_errors": self.parse_errors,
            "creation_errors": self.creation_errors,
            "extraction_started_at": self.extraction_started_at.isoformat(),
            "extraction_completed_at": self.extraction_completed_at.isoformat()
            if self.extraction_completed_at
            else None,
        }


# ============================================================================
# ACTIVITY EXTRACTOR SERVICE
# ============================================================================


class ActivityExtractorService:
    """
    Extracts Activity Lines from UserEntry content and creates SKUEL entities
    across the DSL-extractable SKUEL domains.

    **Activity Domains (7) - What I DO:**
    - Tasks: One-time actions with deadlines
    - Habits: Recurring behaviors to build
    - Goals: Outcomes to achieve
    - Events: Scheduled appointments/meetings
    - Principles: Values/beliefs to embody
    - Choices: Decisions to make
    - Finance: Money matters (expenses/income)

    **Curriculum Domains (3) - What I LEARN:**
    - KnowledgeUnit (KU): Atomic unit of knowledge content
    - PathStep (PS): Single step in a learning journey
    - LearningPath (LP): Complete learning sequence

    **Meta Domain (1) - How I ORGANIZE:**
    - Calendar: Scheduled activity views

    **The Destination (+1) - Where I'm GOING:**
    - LifePath: The ultimate life goal alignment

    **Entity Creation Flow:**

    1. Parse the working text for Activity Lines (@context)
    2. Skip lines whose hash already carries an EXTRACTED_FROM edge
    3. Convert each remaining activity to the domain's typed create request
    4. Call the domain facade to create the entity
    5. Return counts, UIDs, (uid, line_hash) provenance pairs, and resolved
       @ku() references — the caller (`UserEntryProcessingService`) persists
       provenance edges, APPLIES_KNOWLEDGE edges, and the run summary.
    """

    def __init__(
        self,
        # Activity Domains (7)
        tasks_service: Any = None,  # TasksService facade
        habits_service: Any = None,  # HabitsService facade
        goals_service: Any = None,  # GoalsService facade
        events_service: Any = None,  # EventsService facade
        principles_service: Any = None,  # PrinciplesService facade
        choices_service: Any = None,  # ChoicesService facade
        finance_service: Any = None,  # no create-capable service exists (ADR-052)
        # Curriculum Domains (3)
        ku_service: Any = None,  # KuService facade
        ps_service: Any = None,  # no dict-create surface exists today
        lp_service: Any = None,  # no dict-create surface exists today
        # Meta Domain (1)
        calendar_service: Any = None,  # read/aggregate-only today
        # The Destination (+1)
        lifepath_service: Any = None,  # read/aggregate-only today
    ) -> None:
        """
        Initialize the extractor with domain services.

        All services are optional — extraction skips entity types for which
        no service is provided (the line still counts in `*_found`).
        """
        # Activity Domains (7)
        self.tasks_service = tasks_service
        self.habits_service = habits_service
        self.goals_service = goals_service
        self.events_service = events_service
        self.principles_service = principles_service
        self.choices_service = choices_service
        self.finance_service = finance_service

        # Curriculum Domains (3)
        self.ku_service = ku_service
        self.ps_service = ps_service
        self.lp_service = lp_service

        # Meta Domain (1)
        self.calendar_service = calendar_service

        # The Destination (+1)
        self.lifepath_service = lifepath_service

        self.parser = ActivityDSLParser()
        self.logger = get_logger("skuel.dsl.extractor")

    # ========================================================================
    # MAIN EXTRACTION METHOD
    # ========================================================================

    async def extract_and_create(
        self,
        entry: UserEntry,
        user_uid: UserUID,
        *,
        content_override: str | None = None,
        allow_curriculum_creation: bool = True,
        existing_line_hashes: frozenset[str] = frozenset(),
    ) -> Result[ActivityExtractionResult]:
        """
        Extract Activity Lines from a UserEntry and create corresponding entities.

        This is the main entry point for the extraction pipeline.

        Args:
            entry: UserEntry whose content to extract from
            user_uid: User UID for entity ownership
            content_override: Parse this text instead of the entry's content
                (the LLM bridge pre-pass hands its augmented working text here
                without mutating the entry)
            allow_curriculum_creation: Whether curriculum (`ku`/`ls`/`lp`)
                *creation* lines may create entities — teacher/admin only.
                `@ku()` references are unaffected.
            existing_line_hashes: `source_line_hash` values already carrying an
                EXTRACTED_FROM edge to this entry; matching lines are skipped.

        Returns:
            Result containing ActivityExtractionResult with counts, UIDs,
            provenance pairs, and resolved @ku() references
        """
        extraction = ActivityExtractionResult(
            entry_uid=entry.uid,
            user_uid=user_uid,
        )

        content = (
            content_override
            if content_override is not None
            else (entry.processed_content or entry.content or "")
        )
        if not content:
            self.logger.warning(f"No content to extract from entry {entry.uid}")
            extraction.extraction_completed_at = datetime.now()
            return Result.ok(extraction)

        # Step 1: Parse for Activity Lines
        parse_result = self.parser.parse_journal(content, source_file=entry.uid)

        if parse_result.is_error:
            return Result.fail(parse_result)

        parsed = parse_result.value
        extraction.activities_found = parsed.activity_lines_found
        extraction.parse_errors = parsed.parse_errors

        # Collect resolved @ku() references across ALL parsed lines (including
        # ones the hash dedup will skip — APPLIES_KNOWLEDGE writes are
        # MERGE-idempotent, and a reference stays a reference on re-runs).
        seen_refs: set[str] = set()
        for activity in parsed.activities:
            for ku_uid in activity.get_linked_knowledge():
                if ku_uid not in seen_refs:
                    seen_refs.add(ku_uid)
                    extraction.referenced_ku_uids.append(ku_uid)

        # ================================================================
        # Count by type - all entity types
        # ================================================================

        # Activity Domains (7)
        extraction.tasks_found = len(parsed.get_tasks())
        extraction.habits_found = len(parsed.get_habits())
        extraction.goals_found = len(parsed.get_goals())
        extraction.events_found = len(parsed.get_events())
        extraction.principles_found = len(parsed.get_principles())
        extraction.choices_found = len(parsed.get_choices())
        extraction.finances_found = len(parsed.get_finances())

        # Curriculum Domains (3)
        extraction.kus_found = len(parsed.get_knowledge_units())
        extraction.path_steps_found = len(parsed.get_path_steps())
        extraction.learning_paths_found = len(parsed.get_learning_paths())

        # Meta Domain (1)
        extraction.calendar_items_found = len(parsed.get_calendar_items())

        # The Destination (+1)
        extraction.lifepath_items_found = len(parsed.get_lifepath_items())

        self.logger.info(
            f"Parsed {extraction.activities_found} activities from entry {entry.uid}: "
            # Activity Domains (7)
            f"{extraction.tasks_found} tasks, {extraction.habits_found} habits, "
            f"{extraction.goals_found} goals, {extraction.events_found} events, "
            f"{extraction.principles_found} principles, {extraction.choices_found} choices, "
            f"{extraction.finances_found} finances, "
            # Curriculum Domains (3)
            f"{extraction.kus_found} KUs, {extraction.path_steps_found} LSs, "
            f"{extraction.learning_paths_found} LPs, "
            # Meta Domain (1)
            f"{extraction.calendar_items_found} calendar items, "
            # The Destination (+1)
            f"{extraction.lifepath_items_found} lifepath items"
        )

        # ================================================================
        # Step 2: Create entities for each activity type
        # ================================================================

        # ================================================================
        # ACTIVITY DOMAINS (7) - What I DO
        # ================================================================

        if self.tasks_service and extraction.tasks_found > 0:
            created, uids = await self._create_for_domain(
                parsed.get_tasks(),
                self._create_task,
                "Task",
                user_uid,
                extraction,
                existing_line_hashes,
            )
            extraction.tasks_created += created
            extraction.created_task_uids.extend(uids)

        if self.habits_service and extraction.habits_found > 0:
            created, uids = await self._create_for_domain(
                parsed.get_habits(),
                self._create_habit,
                "Habit",
                user_uid,
                extraction,
                existing_line_hashes,
            )
            extraction.habits_created += created
            extraction.created_habit_uids.extend(uids)

        if self.goals_service and extraction.goals_found > 0:
            created, uids = await self._create_for_domain(
                parsed.get_goals(),
                self._create_goal,
                "Goal",
                user_uid,
                extraction,
                existing_line_hashes,
            )
            extraction.goals_created += created
            extraction.created_goal_uids.extend(uids)

        if self.events_service and extraction.events_found > 0:
            created, uids = await self._create_for_domain(
                parsed.get_events(),
                self._create_event,
                "Event",
                user_uid,
                extraction,
                existing_line_hashes,
            )
            extraction.events_created += created
            extraction.created_event_uids.extend(uids)

        if self.principles_service and extraction.principles_found > 0:
            created, uids = await self._create_for_domain(
                parsed.get_principles(),
                self._create_principle,
                "Principle",
                user_uid,
                extraction,
                existing_line_hashes,
            )
            extraction.principles_created += created
            extraction.created_principle_uids.extend(uids)

        if self.choices_service and extraction.choices_found > 0:
            created, uids = await self._create_for_domain(
                parsed.get_choices(),
                self._create_choice,
                "Choice",
                user_uid,
                extraction,
                existing_line_hashes,
            )
            extraction.choices_created += created
            extraction.created_choice_uids.extend(uids)

        if self.finance_service and extraction.finances_found > 0:
            created, uids = await self._create_for_domain(
                parsed.get_finances(),
                self._create_finance,
                "Finance",
                user_uid,
                extraction,
                existing_line_hashes,
            )
            extraction.finances_created += created
            extraction.created_finance_uids.extend(uids)

        # ================================================================
        # CURRICULUM DOMAINS (3) - What I LEARN
        # Creation is SHARED-tier (teacher/admin) — the role gate fires
        # BEFORE the service-availability check so non-privileged users get
        # an explicit creation_error instead of a silent skip.
        # ================================================================

        if extraction.kus_found > 0:
            if not allow_curriculum_creation:
                self._record_curriculum_gate(parsed.get_knowledge_units(), "KU", extraction)
            elif self.ku_service:
                created, uids = await self._create_for_domain(
                    parsed.get_knowledge_units(),
                    self._create_ku,
                    "KU",
                    user_uid,
                    extraction,
                    existing_line_hashes,
                )
                extraction.kus_created += created
                extraction.created_ku_uids.extend(uids)

        if extraction.path_steps_found > 0:
            if not allow_curriculum_creation:
                self._record_curriculum_gate(parsed.get_path_steps(), "PS", extraction)
            elif self.ps_service:
                created, uids = await self._create_for_domain(
                    parsed.get_path_steps(),
                    self._create_ls,
                    "PS",
                    user_uid,
                    extraction,
                    existing_line_hashes,
                )
                extraction.path_steps_created += created
                extraction.created_ps_uids.extend(uids)

        if extraction.learning_paths_found > 0:
            if not allow_curriculum_creation:
                self._record_curriculum_gate(parsed.get_learning_paths(), "LP", extraction)
            elif self.lp_service:
                created, uids = await self._create_for_domain(
                    parsed.get_learning_paths(),
                    self._create_lp,
                    "LP",
                    user_uid,
                    extraction,
                    existing_line_hashes,
                )
                extraction.learning_paths_created += created
                extraction.created_lp_uids.extend(uids)

        # ================================================================
        # META DOMAIN (1) - How I ORGANIZE
        # ================================================================

        if self.calendar_service and extraction.calendar_items_found > 0:
            created, uids = await self._create_for_domain(
                parsed.get_calendar_items(),
                self._create_calendar_item,
                "Calendar",
                user_uid,
                extraction,
                existing_line_hashes,
            )
            extraction.calendar_items_created += created
            extraction.created_calendar_uids.extend(uids)

        # ================================================================
        # THE DESTINATION (+1) - Where I'm GOING
        # ================================================================

        if self.lifepath_service and extraction.lifepath_items_found > 0:
            created, uids = await self._create_for_domain(
                parsed.get_lifepath_items(),
                self._create_lifepath,
                "LifePath",
                user_uid,
                extraction,
                existing_line_hashes,
            )
            extraction.lifepath_items_created += created
            extraction.created_lifepath_uids.extend(uids)

        extraction.extraction_completed_at = datetime.now()

        self.logger.info(
            f"Extraction complete for {entry.uid}: "
            f"created {extraction.total_created} entities, "
            f"skipped {extraction.lines_skipped_existing} already-extracted lines "
            f"({len(extraction.creation_errors)} errors)"
        )

        return Result.ok(extraction)

    # ========================================================================
    # DOMAIN LOOP HELPERS
    # ========================================================================

    async def _create_for_domain(
        self,
        activities: list[ParsedActivityLine],
        creator: Any,  # boundary: bound async creator method (activity, user_uid) -> Result[str | None]
        label: str,
        user_uid: UserUID,
        extraction: ActivityExtractionResult,
        existing_line_hashes: frozenset[str],
    ) -> tuple[int, list[str]]:
        """Run one domain's create loop with hash dedup and provenance capture.

        Returns (created_count, created_uids); appends (uid, line_hash) pairs
        to `extraction.created_links` and failures to
        `extraction.creation_errors`.
        """
        created = 0
        uids: list[str] = []
        for activity in activities:
            line_hash = normalized_line_hash(activity.raw_line or activity.description)
            if line_hash in existing_line_hashes:
                extraction.lines_skipped_existing += 1
                continue
            result = await creator(activity, user_uid)
            if result.is_ok and result.value:
                created += 1
                uids.append(result.value)
                extraction.created_links.append((result.value, line_hash))
            elif result.is_error:
                extraction.creation_errors.append(
                    f"{label} '{activity.description[:30]}...': {result.error}"
                )
        return created, uids

    def _record_curriculum_gate(
        self,
        activities: list[ParsedActivityLine],
        label: str,
        extraction: ActivityExtractionResult,
    ) -> None:
        """Record gate errors for curriculum creation lines (non-teacher user)."""
        for activity in activities:
            extraction.creation_errors.append(
                f"{label} '{activity.description[:30]}...': "
                "curriculum creation requires teacher/admin role"
            )

    # ========================================================================
    # ENTITY CREATION METHODS
    # ========================================================================

    @with_error_handling(error_type="system", operation="create_task")
    async def _create_task(
        self, activity: ParsedActivityLine, user_uid: UserUID
    ) -> Result[str | None]:
        """
        Create a task from parsed activity.

        Returns the created task UID or None if creation failed.
        """
        convert_result = activity_to_task_request(activity)
        if convert_result.is_error:
            return Result.fail(convert_result)

        create_result = await self.tasks_service.create_task(convert_result.value, user_uid)
        if create_result.is_error:
            return Result.fail(create_result)

        task = create_result.value
        self.logger.debug(f"Created task: {task.uid} - '{task.title}'")
        return Result.ok(task.uid)

    @with_error_handling(error_type="system", operation="create_habit")
    async def _create_habit(
        self, activity: ParsedActivityLine, user_uid: UserUID
    ) -> Result[str | None]:
        """
        Create a habit from parsed activity.

        Returns the created habit UID or None if creation failed.
        """
        convert_result = activity_to_habit_request(activity)
        if convert_result.is_error:
            return Result.fail(convert_result)

        create_result = await self.habits_service.create_habit(convert_result.value, user_uid)
        if create_result.is_error:
            return Result.fail(create_result)

        habit = create_result.value
        self.logger.debug(f"Created habit: {habit.uid}")
        return Result.ok(habit.uid)

    @with_error_handling(error_type="system", operation="create_goal")
    async def _create_goal(
        self, activity: ParsedActivityLine, user_uid: UserUID
    ) -> Result[str | None]:
        """
        Create a goal from parsed activity.

        Returns the created goal UID or None if creation failed.
        """
        convert_result = activity_to_goal_request(activity)
        if convert_result.is_error:
            return Result.fail(convert_result)

        create_result = await self.goals_service.create_goal(convert_result.value, user_uid)
        if create_result.is_error:
            return Result.fail(create_result)

        goal = create_result.value
        self.logger.debug(f"Created goal: {goal.uid}")
        return Result.ok(goal.uid)

    @with_error_handling(error_type="system", operation="create_event")
    async def _create_event(
        self, activity: ParsedActivityLine, user_uid: UserUID
    ) -> Result[str | None]:
        """
        Create an event from parsed activity.

        Returns the created event UID or None if creation failed.
        """
        convert_result = activity_to_event_request(activity)
        if convert_result.is_error:
            return Result.fail(convert_result)

        create_result = await self.events_service.create_event(convert_result.value, user_uid)
        if create_result.is_error:
            return Result.fail(create_result)

        event = create_result.value
        self.logger.debug(f"Created event: {event.uid}")
        return Result.ok(event.uid)

    @with_error_handling(error_type="system", operation="create_principle")
    async def _create_principle(
        self, activity: ParsedActivityLine, user_uid: UserUID
    ) -> Result[str | None]:
        """
        Create a principle from parsed activity.

        Returns the created principle UID or None if creation failed.
        """
        convert_result = activity_to_principle_request(activity)
        if convert_result.is_error:
            return Result.fail(convert_result)

        create_result = await self.principles_service.create_principle(
            convert_result.value, user_uid
        )
        if create_result.is_error:
            return Result.fail(create_result)

        principle = create_result.value
        self.logger.debug(f"Created principle: {principle.uid}")
        return Result.ok(principle.uid)

    @with_error_handling(error_type="system", operation="create_choice")
    async def _create_choice(
        self, activity: ParsedActivityLine, user_uid: UserUID
    ) -> Result[str | None]:
        """
        Create a choice from parsed activity.

        Returns the created choice UID or None if creation failed.
        """
        convert_result = activity_to_choice_request(activity)
        if convert_result.is_error:
            return Result.fail(convert_result)

        create_result = await self.choices_service.create_choice(convert_result.value, user_uid)
        if create_result.is_error:
            return Result.fail(create_result)

        choice = create_result.value
        self.logger.debug(f"Created choice: {choice.uid}")
        return Result.ok(choice.uid)

    @with_error_handling(error_type="system", operation="create_finance")
    async def _create_finance(
        self, activity: ParsedActivityLine, user_uid: UserUID
    ) -> Result[str | None]:
        """
        Create a finance entry (expense) from parsed activity.

        Returns the created finance/expense UID or None if creation failed.
        """
        convert_result = activity_to_finance_dict(activity)
        if convert_result.is_error:
            return Result.fail(convert_result)

        finance_dict = convert_result.value

        # Create expense via service (DSL finance path; the native expense service
        # was removed in ADR-052 Phase 5, so this degrades to a no-op error unless a
        # create-capable finance service is injected).
        if getattr(self.finance_service, "create_expense", None):
            create_result = await self.finance_service.create_expense(finance_dict, user_uid)
        elif getattr(self.finance_service, "create", None):
            create_result = await self.finance_service.create(finance_dict, user_uid)
        else:
            return Result.fail(
                Errors.system(
                    message="Finance service has no create method",
                    operation="create_finance",
                )
            )

        if create_result.is_error:
            return Result.fail(create_result)

        expense = create_result.value
        expense_uid = expense.uid if getattr(expense, "uid", None) else expense.get("uid")
        self.logger.debug(f"Created expense: {expense_uid}")

        return Result.ok(expense_uid)

    # ========================================================================
    # CURRICULUM DOMAIN CREATION METHODS (3) - What I LEARN
    # ========================================================================

    @with_error_handling(error_type="system", operation="create_ku")
    async def _create_ku(
        self, activity: ParsedActivityLine, user_uid: UserUID
    ) -> Result[str | None]:
        """
        Create a KnowledgeUnit from parsed activity.

        Returns the created KU UID or None if creation failed.
        """
        convert_result = activity_to_ku_dict(activity)
        if convert_result.is_error:
            return Result.fail(convert_result)

        # ConversionResult is a union; the ku converter always returns a dict.
        raw = convert_result.value
        ku_dict: dict[str, Any] = raw if isinstance(raw, dict) else raw.model_dump()

        # KuService.create_ku takes kwargs, not a dict. The converter's
        # `complexity`/`prerequisites` keys have no create_ku parameter — the
        # prerequisite edges are an ORGANIZES/graph concern, not a node field.
        create_result = await self.ku_service.create_ku(
            title=ku_dict["title"],
            description=ku_dict.get("content"),
            domain=ku_dict.get("domain"),
            tags=ku_dict.get("tags"),
        )

        if create_result.is_error:
            return Result.fail(create_result)

        ku = create_result.value
        if ku is None:
            return Result.fail(
                Errors.system(
                    message="Created KU has no UID",
                    operation="create_ku",
                )
            )
        self.logger.debug(f"Created KU: {ku.uid}")
        return Result.ok(ku.uid)

    @with_error_handling(error_type="system", operation="create_ls")
    async def _create_ls(
        self, activity: ParsedActivityLine, user_uid: UserUID
    ) -> Result[str | None]:
        """
        Create a PathStep from parsed activity.

        Returns the created PathStep UID or None if creation failed.
        """
        convert_result = activity_to_ps_dict(activity)
        if convert_result.is_error:
            return Result.fail(convert_result)

        ps_dict = convert_result.value

        # No create-capable PS surface exists today — this probe is the seam a
        # future dict-create method plugs into (the compose root injects None).
        if getattr(self.ps_service, "create_ls", None):
            create_result = await self.ps_service.create_ls(ps_dict, user_uid)
        elif getattr(self.ps_service, "create", None):
            create_result = await self.ps_service.create(ps_dict, user_uid)
        else:
            return Result.fail(
                Errors.system(
                    message="PS service has no create method",
                    operation="create_ps",
                )
            )

        if create_result.is_error:
            return Result.fail(create_result)

        ps = create_result.value
        ps_uid = ps.uid if getattr(ps, "uid", None) else ps.get("uid")
        self.logger.debug(f"Created PS: {ps_uid}")

        return Result.ok(ps_uid)

    @with_error_handling(error_type="system", operation="create_lp")
    async def _create_lp(
        self, activity: ParsedActivityLine, user_uid: UserUID
    ) -> Result[str | None]:
        """
        Create a LearningPath from parsed activity.

        Returns the created LP UID or None if creation failed.
        """
        convert_result = activity_to_lp_dict(activity)
        if convert_result.is_error:
            return Result.fail(convert_result)

        lp_dict = convert_result.value

        # No create-capable LP surface exists today — see _create_ls.
        if getattr(self.lp_service, "create_lp", None):
            create_result = await self.lp_service.create_lp(lp_dict, user_uid)
        elif getattr(self.lp_service, "create", None):
            create_result = await self.lp_service.create(lp_dict, user_uid)
        else:
            return Result.fail(
                Errors.system(
                    message="LP service has no create method",
                    operation="create_lp",
                )
            )

        if create_result.is_error:
            return Result.fail(create_result)

        lp = create_result.value
        lp_uid = lp.uid if getattr(lp, "uid", None) else lp.get("uid")
        self.logger.debug(f"Created LP: {lp_uid}")

        return Result.ok(lp_uid)

    # ========================================================================
    # META DOMAIN CREATION METHOD (1) - How I ORGANIZE
    # ========================================================================

    @with_error_handling(error_type="system", operation="create_calendar_item")
    async def _create_calendar_item(
        self, activity: ParsedActivityLine, user_uid: UserUID
    ) -> Result[str | None]:
        """
        Create a Calendar item from parsed activity.

        Calendar items can be time blocks, scheduled activities, etc.

        Returns the created calendar item UID or None if creation failed.
        """
        convert_result = activity_to_calendar_dict(activity)
        if convert_result.is_error:
            return Result.fail(convert_result)

        calendar_dict = convert_result.value

        # CalendarService is read/aggregate-only today — see _create_ls.
        if getattr(self.calendar_service, "create_time_block", None):
            create_result = await self.calendar_service.create_time_block(calendar_dict, user_uid)
        elif getattr(self.calendar_service, "create", None):
            create_result = await self.calendar_service.create(calendar_dict, user_uid)
        else:
            return Result.fail(
                Errors.system(
                    message="Calendar service has no create method",
                    operation="create_calendar_item",
                )
            )

        if create_result.is_error:
            return Result.fail(create_result)

        calendar_item = create_result.value
        calendar_uid = (
            calendar_item.uid if getattr(calendar_item, "uid", None) else calendar_item.get("uid")
        )
        self.logger.debug(f"Created Calendar item: {calendar_uid}")

        return Result.ok(calendar_uid)

    # ========================================================================
    # THE DESTINATION CREATION METHOD (+1) - Where I'm GOING
    # ========================================================================

    @with_error_handling(error_type="system", operation="create_lifepath")
    async def _create_lifepath(
        self, activity: ParsedActivityLine, user_uid: UserUID
    ) -> Result[str | None]:
        """
        Create/update a LifePath alignment from parsed activity.

        The LifePath represents the user's ultimate life goal - everything
        flows toward this destination. LifePath entries from user entries
        help refine and articulate this vision.

        Returns a lifepath reference UID or None if creation failed.
        """
        convert_result = activity_to_lifepath_dict(activity)
        if convert_result.is_error:
            return Result.fail(convert_result)

        lifepath_dict = convert_result.value

        # LifePathService has no DSL-shaped write surface today — see _create_ls.
        if getattr(self.lifepath_service, "update_lifepath", None):
            create_result = await self.lifepath_service.update_lifepath(lifepath_dict, user_uid)
        elif getattr(self.lifepath_service, "create", None):
            create_result = await self.lifepath_service.create(lifepath_dict, user_uid)
        elif getattr(self.lifepath_service, "record_alignment", None):
            create_result = await self.lifepath_service.record_alignment(lifepath_dict, user_uid)
        else:
            return Result.fail(
                Errors.system(
                    message="LifePath service has no update/create method",
                    operation="create_lifepath",
                )
            )

        if create_result.is_error:
            return Result.fail(create_result)

        lifepath = create_result.value
        lifepath_uid = (
            lifepath.uid
            if getattr(lifepath, "uid", None)
            else lifepath.get("uid", f"lifepath:{user_uid}")
        )
        self.logger.debug(f"Created/Updated LifePath: {lifepath_uid}")

        return Result.ok(lifepath_uid)

    # ========================================================================
    # EXTRACTION-ONLY (NO ENTITY CREATION)
    # ========================================================================

    def preview_extraction(self, content: str) -> dict[str, Any]:
        """
        Preview what would be extracted without creating entities.

        Returns a summary dict suitable for UI display covering the
        DSL-extractable SKUEL domains.

        Args:
            content: Entry content to parse

        Returns:
            Dict with activity counts and previews for all entity types
        """
        result = self.parser.parse_journal(content)

        if result.is_error:
            return {
                "success": False,
                "error": str(result.error),
                "activities": [],
            }

        parsed = result.value

        return {
            "success": True,
            "total_activities": parsed.activity_lines_found,
            # ================================================================
            # ACTIVITY DOMAINS (7) - What I DO
            # ================================================================
            "tasks": [
                {
                    "description": a.description,
                    "priority": a.priority,
                    "when": str(a.when) if a.when else None,
                }
                for a in parsed.get_tasks()
            ],
            "habits": [
                {"description": a.description, "repeat": a.repeat_pattern}
                for a in parsed.get_habits()
            ],
            "goals": [{"description": a.description} for a in parsed.get_goals()],
            "events": [
                {"description": a.description, "when": str(a.when) if a.when else None}
                for a in parsed.get_events()
            ],
            "principles": [
                {
                    "description": a.description,
                    "energy_states": a.energy_states,
                    "priority": a.priority,
                }
                for a in parsed.get_principles()
            ],
            "choices": [
                {
                    "description": a.description,
                    "when": str(a.when) if a.when else None,
                    "linked_goals": a.get_linked_goals(),
                }
                for a in parsed.get_choices()
            ],
            "finances": [
                {
                    "description": a.description,
                    "amount": a.get_amount(),
                    "when": str(a.when) if a.when else None,
                }
                for a in parsed.get_finances()
            ],
            # ================================================================
            # CURRICULUM DOMAINS (3) - What I LEARN
            # ================================================================
            "knowledge_units": [
                {
                    "description": a.description,
                    "priority": a.priority,
                    "energy_states": a.energy_states,
                }
                for a in parsed.get_knowledge_units()
            ],
            "path_steps": [
                {
                    "description": a.description,
                    "duration_minutes": a.duration_minutes,
                    "primary_ku": a.primary_ku,
                }
                for a in parsed.get_path_steps()
            ],
            "learning_paths": [
                {
                    "description": a.description,
                    "priority": a.priority,
                    "linked_goals": a.get_linked_goals(),
                }
                for a in parsed.get_learning_paths()
            ],
            # ================================================================
            # META DOMAIN (1) - How I ORGANIZE
            # ================================================================
            "calendar_items": [
                {
                    "description": a.description,
                    "when": str(a.when) if a.when else None,
                    "duration_minutes": a.duration_minutes,
                }
                for a in parsed.get_calendar_items()
            ],
            # ================================================================
            # THE DESTINATION (+1) - Where I'm GOING
            # ================================================================
            "lifepath_items": [
                {
                    "description": a.description,
                    "linked_principles": a.get_linked_principles(),
                    "linked_goals": a.get_linked_goals(),
                }
                for a in parsed.get_lifepath_items()
            ],
            "parse_errors": parsed.parse_errors,
        }
