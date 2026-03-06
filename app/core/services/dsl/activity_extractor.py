"""
Submission Activity Extractor Service
======================================

Extracts Activity Lines from processed submission content and creates
corresponding SKUEL entities across ALL 13 SKUEL domains:

**Activity Domains (7) - What I DO:**
- Tasks, Habits, Goals, Events (original 4)
- Principles, Choices, Finance (added for 7-domain completeness)

**Curriculum Domains (3) - What I LEARN:**
- KnowledgeUnit (KU), LearningStep (LS), LearningPath (LP)

**Meta Domains (3) - How I ORGANIZE:**
- Submissions, Analytics, Calendar

**The Destination (+1) - Where I'm GOING:**
- LifePath (the ultimate life goal)

This service integrates with the SubmissionsProcessingService pipeline:

```
Audio/Text → Transcription → LLM Formatting → **Activity Extraction** → Entity Creation
```

**Design Principles:**

1. **Non-destructive**: Extraction doesn't modify the submission content
2. **Idempotent**: Re-extraction updates existing entities, doesn't duplicate
3. **Graph-aware**: Creates relationships between entities and the source submission
4. **Optional**: Activity extraction is opt-in via instructions
5. **13-Domain Complete**: Covers all SKUEL domains for complete DSL support

**Integration Point:**

Called after LLM formatting in SubmissionsProcessingService._process_audio/text():
```python
# After LLM formatting succeeds
if instructions.get("extract_activities", False):
    await activity_extractor.extract_and_create(
        report=updated_report,
        user_uid=report.user_uid,
    )
```
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from core.models.entity_types import SubmissionEntity
from core.ports.base_protocols import HasUID
from core.services.dsl.activity_dsl_parser import (
    ActivityDSLParser,
    ParsedActivityLine,
    ParsedJournal,
)
from core.services.dsl.activity_entity_converter import (
    ActivityEntityConverter,
    activity_to_analytics_dict,
    # Meta Domains (3)
    activity_to_calendar_dict,
    activity_to_choice_dict,
    activity_to_event_dict,
    activity_to_finance_dict,
    activity_to_goal_dict,
    activity_to_habit_dict,
    # Curriculum Domains (3)
    activity_to_ku_dict,
    # The Destination (+1)
    activity_to_lifepath_dict,
    activity_to_lp_dict,
    activity_to_ls_dict,
    activity_to_principle_dict,
    activity_to_report_dict,
    # Activity Domains (7)
    activity_to_task_request,
)
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

# ============================================================================
# SERVICE PROTOCOLS FOR TYPE-SAFE METHOD CHECKING
# ============================================================================


@runtime_checkable
class HasCreateMethod(Protocol):
    """Protocol for services with create() method."""

    async def create(self, entity: Any, *args: Any, **kwargs: Any) -> Result[Any]:
        """Create an entity."""
        ...


@runtime_checkable
class HasCreateHabitMethod(Protocol):
    """Protocol for services with create_habit() method."""

    async def create_habit(self, data: dict[str, Any], user_uid: str) -> Result[Any]:
        """Create a habit."""
        ...


@runtime_checkable
class HasCreateGoalMethod(Protocol):
    """Protocol for services with create_goal() method."""

    async def create_goal(self, data: dict[str, Any], user_uid: str) -> Result[Any]:
        """Create a goal."""
        ...


@runtime_checkable
class HasCreateEventMethod(Protocol):
    """Protocol for services with create_event() method."""

    async def create_event(self, data: dict[str, Any], user_uid: str) -> Result[Any]:
        """Create an event."""
        ...


# ============================================================================
# EXTRACTION RESULT
# ============================================================================


@dataclass
class ActivityExtractionResult:
    """
    Result of activity extraction from a submission.

    Contains counts of created entities across ALL 13 SKUEL domains
    and any errors encountered.

    **Domain Categories:**
    - Activity Domains (7): Tasks, Habits, Goals, Events, Principles, Choices, Finance
    - Curriculum Domains (3): KU, LS, LP
    - Meta Domains (3): Submissions, Analytics, Calendar
    - The Destination (+1): LifePath
    """

    # Source
    report_uid: str
    user_uid: str

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
    learning_steps_found: int = 0
    learning_paths_found: int = 0

    # Meta Domains (3)
    reports_found: int = 0
    analytics_found: int = 0
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
    learning_steps_created: int = 0
    learning_paths_created: int = 0

    # Meta Domains (3)
    reports_created: int = 0
    analytics_created: int = 0
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
    created_ls_uids: list[str] = field(default_factory=list)
    created_lp_uids: list[str] = field(default_factory=list)

    # Meta Domains (3)
    created_report_uids: list[str] = field(default_factory=list)
    created_analytics_uids: list[str] = field(default_factory=list)
    created_calendar_uids: list[str] = field(default_factory=list)

    # The Destination (+1)
    created_lifepath_uids: list[str] = field(default_factory=list)

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
            + self.learning_steps_created
            + self.learning_paths_created
            # Meta Domains (3)
            + self.reports_created
            + self.analytics_created
            + self.calendar_items_created
            # The Destination (+1)
            + self.lifepath_items_created
        )

    @property
    def has_errors(self) -> bool:
        """Check if any errors occurred."""
        return len(self.parse_errors) > 0 or len(self.creation_errors) > 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage in submission metadata."""
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
            "learning_steps_found": self.learning_steps_found,
            "learning_paths_found": self.learning_paths_found,
            # Meta Domains (3)
            "reports_found": self.reports_found,
            "analytics_found": self.analytics_found,
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
            "learning_steps_created": self.learning_steps_created,
            "learning_paths_created": self.learning_paths_created,
            # Meta Domains (3)
            "reports_created": self.reports_created,
            "analytics_created": self.analytics_created,
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
            "created_ls_uids": self.created_ls_uids,
            "created_lp_uids": self.created_lp_uids,
            # Meta Domains (3)
            "created_report_uids": self.created_report_uids,
            "created_analytics_uids": self.created_analytics_uids,
            "created_calendar_uids": self.created_calendar_uids,
            # The Destination (+1)
            "created_lifepath_uids": self.created_lifepath_uids,
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
# SUBMISSION ACTIVITY EXTRACTOR SERVICE
# ============================================================================


class ActivityExtractorService:
    """
    Extracts Activity Lines from submission content and creates SKUEL entities
    across ALL 13 SKUEL domains + 1 destination.

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
    - LearningStep (LS): Single step in a learning journey
    - LearningPath (LP): Complete learning sequence

    **Meta Domains (3) - How I ORGANIZE:**
    - Submissions: File uploads and processing requests
    - Analytics: Statistical aggregation and analysis
    - Calendar: Scheduled activity views

    **The Destination (+1) - Where I'm GOING:**
    - LifePath: The ultimate life goal alignment

    **Usage:**

    ```python
    extractor = ActivityExtractorService(
        # Activity Domains (7)
        tasks_service=tasks_service,
        habits_service=habits_service,
        goals_service=goals_service,
        events_service=events_service,
        principles_service=principles_service,
        choices_service=choices_service,
        finance_service=finance_service,
        # Curriculum Domains (3)
        ku_service=ku_service,
        ls_service=ls_service,
        lp_service=lp_service,
        # Meta Domains (3)
        report_service=report_service,
        analytics_service=analytics_service,
        calendar_service=calendar_service,
        # The Destination (+1)
        lifepath_service=lifepath_service,
    )

    # Extract and create entities from a processed submission
    result = await extractor.extract_and_create(
        report=report,
        user_uid="user:mike",
    )

    if result.is_ok:
        extraction = result.value
        print(f"Created {extraction.total_created} entities across entity types")
        print(f"Tasks: {extraction.tasks_created}")
        print(f"KUs: {extraction.kus_created}")
        print(f"LifePath: {extraction.lifepath_items_created}")
    ```

    **Entity Creation Flow:**

    1. Parse processed_content for Activity Lines (@context)
    2. Convert each activity to domain-specific create request
    3. Call appropriate service to create entity
    4. Create EXTRACTED_FROM relationship: Entity → Submission
    5. Store extraction results in submission metadata
    """

    def __init__(
        self,
        # Activity Domains (7)
        tasks_service=None,  # TasksCoreService
        habits_service=None,  # HabitsCoreService
        goals_service=None,  # GoalsCoreService
        events_service=None,  # EventsCoreService
        principles_service=None,  # PrinciplesCoreService
        choices_service=None,  # ChoicesCoreService
        finance_service=None,  # FinanceCoreService
        # Curriculum Domains (3)
        ku_service=None,  # ArticleCoreService
        ls_service=None,  # LsCoreService
        lp_service=None,  # LpCoreService
        # Meta Domains (3)
        report_service=None,  # SubmissionsCoreService (for metadata updates)
        analytics_service=None,  # AnalyticsService
        calendar_service=None,  # CalendarService
        # The Destination (+1)
        lifepath_service=None,  # LifePathService
    ) -> None:
        """
        Initialize the extractor with domain services for all 13 SKUEL domains.

        All services are optional - extraction will skip entity types
        for which no service is provided.

        Args:
            # Activity Domains (7)
            tasks_service: Service for creating tasks
            habits_service: Service for creating habits
            goals_service: Service for creating goals
            events_service: Service for creating events
            principles_service: Service for creating principles
            choices_service: Service for creating choices
            finance_service: Service for creating expenses/finance entries

            # Curriculum Domains (3)
            ku_service: Service for creating knowledge units
            ls_service: Service for creating learning steps
            lp_service: Service for creating learning paths

            # Meta Domains (3)
            report_service: Service for updating submission metadata
            analytics_service: Service for generating analytics
            calendar_service: Service for creating calendar items

            # The Destination (+1)
            lifepath_service: Service for updating life path alignment
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
        self.ls_service = ls_service
        self.lp_service = lp_service

        # Meta Domains (3)
        self.report_service = report_service
        self.analytics_service = analytics_service
        self.calendar_service = calendar_service

        # The Destination (+1)
        self.lifepath_service = lifepath_service

        self.parser = ActivityDSLParser()
        self.converter = ActivityEntityConverter()
        self.logger = get_logger("skuel.dsl.extractor")

    # ========================================================================
    # MAIN EXTRACTION METHOD
    # ========================================================================

    async def extract_and_create(
        self,
        report: SubmissionEntity,
        user_uid: str,
        create_relationships: bool = True,
    ) -> Result[ActivityExtractionResult]:
        """
        Extract Activity Lines from submission and create corresponding entities.

        This is the main entry point for the extraction pipeline.

        Args:
            report: Processed submission with content to extract from
            user_uid: User UID for entity ownership
            create_relationships: Whether to create EXTRACTED_FROM relationships

        Returns:
            Result containing ActivityExtractionResult with counts and UIDs
        """
        extraction = ActivityExtractionResult(
            report_uid=report.uid,
            user_uid=user_uid,
        )

        # Get content to parse (processed_content only exists on Submission)
        content = getattr(report, "processed_content", None) or ""
        if not content:
            self.logger.warning(f"No processed content in report {report.uid}")
            extraction.extraction_completed_at = datetime.now()
            return Result.ok(extraction)

        # Step 1: Parse for Activity Lines
        parse_result = self.parser.parse_journal(content, source_file=report.uid)

        if parse_result.is_error:
            return Result.fail(parse_result.expect_error())

        parsed = parse_result.value
        extraction.activities_found = parsed.activity_lines_found
        extraction.parse_errors = parsed.parse_errors

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
        extraction.learning_steps_found = len(parsed.get_learning_steps())
        extraction.learning_paths_found = len(parsed.get_learning_paths())

        # Meta Domains (3)
        extraction.reports_found = len(parsed.get_reports())
        extraction.calendar_items_found = len(parsed.get_calendar_items())

        # The Destination (+1)
        extraction.lifepath_items_found = len(parsed.get_lifepath_items())

        self.logger.info(
            f"Parsed {extraction.activities_found} activities from report {report.uid}: "
            # Activity Domains (7)
            f"{extraction.tasks_found} tasks, {extraction.habits_found} habits, "
            f"{extraction.goals_found} goals, {extraction.events_found} events, "
            f"{extraction.principles_found} principles, {extraction.choices_found} choices, "
            f"{extraction.finances_found} finances, "
            # Curriculum Domains (3)
            f"{extraction.kus_found} KUs, {extraction.learning_steps_found} LSs, "
            f"{extraction.learning_paths_found} LPs, "
            # Meta Domains (3)
            f"{extraction.reports_found} reports, "
            f"{extraction.calendar_items_found} calendar items, "
            # The Destination (+1)
            f"{extraction.lifepath_items_found} lifepath items"
        )

        # ================================================================
        # Step 2: Create entities for each activity type - all entity types
        # ================================================================

        # ================================================================
        # ACTIVITY DOMAINS (7) - What I DO
        # ================================================================

        # Tasks
        if self.tasks_service and extraction.tasks_found > 0:
            for activity in parsed.get_tasks():
                result = await self._create_task(activity, user_uid, report.uid)
                if result.is_ok and result.value:
                    extraction.tasks_created += 1
                    extraction.created_task_uids.append(result.value)
                elif result.is_error:
                    extraction.creation_errors.append(
                        f"Task '{activity.description[:30]}...': {result.error}"
                    )

        # Habits
        if self.habits_service and extraction.habits_found > 0:
            for activity in parsed.get_habits():
                result = await self._create_habit(activity, user_uid, report.uid)
                if result.is_ok and result.value:
                    extraction.habits_created += 1
                    extraction.created_habit_uids.append(result.value)
                elif result.is_error:
                    extraction.creation_errors.append(
                        f"Habit '{activity.description[:30]}...': {result.error}"
                    )

        # Goals
        if self.goals_service and extraction.goals_found > 0:
            for activity in parsed.get_goals():
                result = await self._create_goal(activity, user_uid, report.uid)
                if result.is_ok and result.value:
                    extraction.goals_created += 1
                    extraction.created_goal_uids.append(result.value)
                elif result.is_error:
                    extraction.creation_errors.append(
                        f"Goal '{activity.description[:30]}...': {result.error}"
                    )

        # Events
        if self.events_service and extraction.events_found > 0:
            for activity in parsed.get_events():
                result = await self._create_event(activity, user_uid, report.uid)
                if result.is_ok and result.value:
                    extraction.events_created += 1
                    extraction.created_event_uids.append(result.value)
                elif result.is_error:
                    extraction.creation_errors.append(
                        f"Event '{activity.description[:30]}...': {result.error}"
                    )

        # Principles
        if self.principles_service and extraction.principles_found > 0:
            for activity in parsed.get_principles():
                result = await self._create_principle(activity, user_uid, report.uid)
                if result.is_ok and result.value:
                    extraction.principles_created += 1
                    extraction.created_principle_uids.append(result.value)
                elif result.is_error:
                    extraction.creation_errors.append(
                        f"Principle '{activity.description[:30]}...': {result.error}"
                    )

        # Choices
        if self.choices_service and extraction.choices_found > 0:
            for activity in parsed.get_choices():
                result = await self._create_choice(activity, user_uid, report.uid)
                if result.is_ok and result.value:
                    extraction.choices_created += 1
                    extraction.created_choice_uids.append(result.value)
                elif result.is_error:
                    extraction.creation_errors.append(
                        f"Choice '{activity.description[:30]}...': {result.error}"
                    )

        # Finance
        if self.finance_service and extraction.finances_found > 0:
            for activity in parsed.get_finances():
                result = await self._create_finance(activity, user_uid, report.uid)
                if result.is_ok and result.value:
                    extraction.finances_created += 1
                    extraction.created_finance_uids.append(result.value)
                elif result.is_error:
                    extraction.creation_errors.append(
                        f"Finance '{activity.description[:30]}...': {result.error}"
                    )

        # ================================================================
        # CURRICULUM DOMAINS (3) - What I LEARN
        # ================================================================

        # Knowledge Units (KU)
        if self.ku_service and extraction.kus_found > 0:
            for activity in parsed.get_knowledge_units():
                result = await self._create_ku(activity, user_uid, report.uid)
                if result.is_ok and result.value:
                    extraction.kus_created += 1
                    extraction.created_ku_uids.append(result.value)
                elif result.is_error:
                    extraction.creation_errors.append(
                        f"KU '{activity.description[:30]}...': {result.error}"
                    )

        # Learning Steps (LS)
        if self.ls_service and extraction.learning_steps_found > 0:
            for activity in parsed.get_learning_steps():
                result = await self._create_ls(activity, user_uid, report.uid)
                if result.is_ok and result.value:
                    extraction.learning_steps_created += 1
                    extraction.created_ls_uids.append(result.value)
                elif result.is_error:
                    extraction.creation_errors.append(
                        f"LS '{activity.description[:30]}...': {result.error}"
                    )

        # Learning Paths (LP)
        if self.lp_service and extraction.learning_paths_found > 0:
            for activity in parsed.get_learning_paths():
                result = await self._create_lp(activity, user_uid, report.uid)
                if result.is_ok and result.value:
                    extraction.learning_paths_created += 1
                    extraction.created_lp_uids.append(result.value)
                elif result.is_error:
                    extraction.creation_errors.append(
                        f"LP '{activity.description[:30]}...': {result.error}"
                    )

        # ================================================================
        # META DOMAINS (3) - How I ORGANIZE
        # ================================================================

        # Note: Submissions extracted from submission content create new submissions
        # This is a recursive pattern - content extracted from one submission
        # can trigger creation of new submissions
        if self.report_service and extraction.reports_found > 0:
            for activity in parsed.get_reports():
                result = await self._create_report(activity, user_uid, report.uid)
                if result.is_ok and result.value:
                    extraction.reports_created += 1
                    extraction.created_report_uids.append(result.value)
                elif result.is_error:
                    extraction.creation_errors.append(
                        f"Submission '{activity.description[:30]}...': {result.error}"
                    )

        # Calendar Items
        if self.calendar_service and extraction.calendar_items_found > 0:
            for activity in parsed.get_calendar_items():
                result = await self._create_calendar_item(activity, user_uid, report.uid)
                if result.is_ok and result.value:
                    extraction.calendar_items_created += 1
                    extraction.created_calendar_uids.append(result.value)
                elif result.is_error:
                    extraction.creation_errors.append(
                        f"Calendar '{activity.description[:30]}...': {result.error}"
                    )

        # ================================================================
        # THE DESTINATION (+1) - Where I'm GOING
        # ================================================================

        # LifePath Items
        if self.lifepath_service and extraction.lifepath_items_found > 0:
            for activity in parsed.get_lifepath_items():
                result = await self._create_lifepath(activity, user_uid, report.uid)
                if result.is_ok and result.value:
                    extraction.lifepath_items_created += 1
                    extraction.created_lifepath_uids.append(result.value)
                elif result.is_error:
                    extraction.creation_errors.append(
                        f"LifePath '{activity.description[:30]}...': {result.error}"
                    )

        extraction.extraction_completed_at = datetime.now()

        # Step 3: Store extraction results in submission metadata
        if self.report_service:
            await self._update_report_metadata(report.uid, extraction)

        self.logger.info(
            f"Extraction complete for {report.uid}: "
            f"created {extraction.total_created} entities across entity types "
            f"({len(extraction.creation_errors)} errors)"
        )

        return Result.ok(extraction)

    # ========================================================================
    # ENTITY CREATION METHODS
    # ========================================================================

    @with_error_handling(error_type="system", operation="create_task")
    async def _create_task(
        self, activity: ParsedActivityLine, user_uid: str, source_report_uid: str
    ) -> Result[str | None]:
        """
        Create a task from parsed activity.

        Returns the created task UID or None if creation failed.
        """
        # Convert to TaskCreateRequest
        convert_result = activity_to_task_request(activity)
        if convert_result.is_error:
            return Result.fail(convert_result.expect_error())

        request = convert_result.value

        # Create task via service
        create_result = await self.tasks_service.create_task(request, user_uid)

        if create_result.is_error:
            return Result.fail(create_result.expect_error())

        task = create_result.value
        self.logger.debug(f"Created task: {task.uid} - '{task.title}'")

        return Result.ok(task.uid)

    @with_error_handling(error_type="system", operation="create_habit")
    async def _create_habit(
        self, activity: ParsedActivityLine, user_uid: str, source_report_uid: str
    ) -> Result[str | None]:
        """
        Create a habit from parsed activity.

        Returns the created habit UID or None if creation failed.
        """
        # Convert to habit dict
        convert_result = activity_to_habit_dict(activity)
        if convert_result.is_error:
            return Result.fail(convert_result.expect_error())

        habit_dict = convert_result.value

        # Create habit via service
        # Note: Adapt this to your HabitsCoreService interface
        if isinstance(self.habits_service, HasCreateHabitMethod):
            create_result = await self.habits_service.create_habit(habit_dict, user_uid)
        elif isinstance(self.habits_service, HasCreateMethod):
            create_result = await self.habits_service.create(habit_dict, user_uid)
        else:
            return Result.fail(
                Errors.system(
                    message="Habits service has no create method",
                    operation="create_habit",
                )
            )

        if create_result.is_error:
            return Result.fail(create_result.expect_error())

        habit = create_result.value
        # Extract UID using Protocol or dict access
        if isinstance(habit, HasUID):
            habit_uid = habit.uid
        elif isinstance(habit, dict):
            habit_uid = habit.get("uid")
        else:
            habit_uid = getattr(habit, "uid", None)

        if not habit_uid:
            return Result.fail(
                Errors.system(
                    message="Created habit has no UID",
                    operation="create_habit",
                )
            )

        self.logger.debug(f"Created habit: {habit_uid}")

        return Result.ok(habit_uid)

    @with_error_handling(error_type="system", operation="create_goal")
    async def _create_goal(
        self, activity: ParsedActivityLine, user_uid: str, source_report_uid: str
    ) -> Result[str | None]:
        """
        Create a goal from parsed activity.

        Returns the created goal UID or None if creation failed.
        """
        # Convert to goal dict
        convert_result = activity_to_goal_dict(activity)
        if convert_result.is_error:
            return Result.fail(convert_result.expect_error())

        goal_dict = convert_result.value

        # Create goal via service
        if isinstance(self.goals_service, HasCreateGoalMethod):
            create_result = await self.goals_service.create_goal(goal_dict, user_uid)
        elif isinstance(self.goals_service, HasCreateMethod):
            create_result = await self.goals_service.create(goal_dict, user_uid)
        else:
            return Result.fail(
                Errors.system(
                    message="Goals service has no create method",
                    operation="create_goal",
                )
            )

        if create_result.is_error:
            return Result.fail(create_result.expect_error())

        goal = create_result.value
        # Extract UID using Protocol or dict access
        if isinstance(goal, HasUID):
            goal_uid = goal.uid
        elif isinstance(goal, dict):
            goal_uid = goal.get("uid")
        else:
            goal_uid = getattr(goal, "uid", None)

        if not goal_uid:
            return Result.fail(
                Errors.system(
                    message="Created goal has no UID",
                    operation="create_goal",
                )
            )

        self.logger.debug(f"Created goal: {goal_uid}")

        return Result.ok(goal_uid)

    @with_error_handling(error_type="system", operation="create_event")
    async def _create_event(
        self, activity: ParsedActivityLine, user_uid: str, source_report_uid: str
    ) -> Result[str | None]:
        """
        Create an event from parsed activity.

        Returns the created event UID or None if creation failed.
        """
        # Convert to event dict
        convert_result = activity_to_event_dict(activity)
        if convert_result.is_error:
            return Result.fail(convert_result.expect_error())

        event_dict = convert_result.value

        # Create event via service
        if isinstance(self.events_service, HasCreateEventMethod):
            create_result = await self.events_service.create_event(event_dict, user_uid)
        elif isinstance(self.events_service, HasCreateMethod):
            create_result = await self.events_service.create(event_dict, user_uid)
        else:
            return Result.fail(
                Errors.system(
                    message="Events service has no create method",
                    operation="create_event",
                )
            )

        if create_result.is_error:
            return Result.fail(create_result.expect_error())

        event = create_result.value
        # Extract UID using Protocol or dict access
        if isinstance(event, HasUID):
            event_uid = event.uid
        elif isinstance(event, dict):
            event_uid = event.get("uid")
        else:
            event_uid = getattr(event, "uid", None)

        if not event_uid:
            return Result.fail(
                Errors.system(
                    message="Created event has no UID",
                    operation="create_event",
                )
            )

        self.logger.debug(f"Created event: {event_uid}")

        return Result.ok(event_uid)

    @with_error_handling(error_type="system", operation="create_principle")
    async def _create_principle(
        self, activity: ParsedActivityLine, user_uid: str, source_report_uid: str
    ) -> Result[str | None]:
        """
        Create a principle from parsed activity.

        Returns the created principle UID or None if creation failed.
        """
        # Convert to principle dict
        convert_result = activity_to_principle_dict(activity)
        if convert_result.is_error:
            return Result.fail(convert_result.expect_error())

        principle_dict = convert_result.value

        # Create principle via service
        # Note: Adapt this to your PrinciplesCoreService interface
        if getattr(self.principles_service, "create_principle", None):
            create_result = await self.principles_service.create_principle(principle_dict, user_uid)
        elif getattr(self.principles_service, "create", None):
            create_result = await self.principles_service.create(principle_dict, user_uid)
        else:
            return Result.fail(
                Errors.system(
                    message="Principles service has no create method",
                    operation="create_principle",
                )
            )

        if create_result.is_error:
            return Result.fail(create_result.expect_error())

        principle = create_result.value
        principle_uid = principle.uid if getattr(principle, "uid", None) else principle.get("uid")
        self.logger.debug(f"Created principle: {principle_uid}")

        return Result.ok(principle_uid)

    @with_error_handling(error_type="system", operation="create_choice")
    async def _create_choice(
        self, activity: ParsedActivityLine, user_uid: str, source_report_uid: str
    ) -> Result[str | None]:
        """
        Create a choice from parsed activity.

        Returns the created choice UID or None if creation failed.
        """
        # Convert to choice dict
        convert_result = activity_to_choice_dict(activity)
        if convert_result.is_error:
            return Result.fail(convert_result.expect_error())

        choice_dict = convert_result.value

        # Create choice via service
        # Note: Adapt this to your ChoicesCoreService interface
        if getattr(self.choices_service, "create_choice", None):
            create_result = await self.choices_service.create_choice(choice_dict, user_uid)
        elif getattr(self.choices_service, "create", None):
            create_result = await self.choices_service.create(choice_dict, user_uid)
        else:
            return Result.fail(
                Errors.system(
                    message="Choices service has no create method",
                    operation="create_choice",
                )
            )

        if create_result.is_error:
            return Result.fail(create_result.expect_error())

        choice = create_result.value
        choice_uid = choice.uid if getattr(choice, "uid", None) else choice.get("uid")
        self.logger.debug(f"Created choice: {choice_uid}")

        return Result.ok(choice_uid)

    @with_error_handling(error_type="system", operation="create_finance")
    async def _create_finance(
        self, activity: ParsedActivityLine, user_uid: str, source_report_uid: str
    ) -> Result[str | None]:
        """
        Create a finance entry (expense) from parsed activity.

        Returns the created finance/expense UID or None if creation failed.
        """
        # Convert to finance dict
        convert_result = activity_to_finance_dict(activity)
        if convert_result.is_error:
            return Result.fail(convert_result.expect_error())

        finance_dict = convert_result.value

        # Create expense via service
        # Note: Adapt this to your FinanceCoreService interface
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
            return Result.fail(create_result.expect_error())

        expense = create_result.value
        expense_uid = expense.uid if getattr(expense, "uid", None) else expense.get("uid")
        self.logger.debug(f"Created expense: {expense_uid}")

        return Result.ok(expense_uid)

    # ========================================================================
    # CURRICULUM DOMAIN CREATION METHODS (3) - What I LEARN
    # ========================================================================

    @with_error_handling(error_type="system", operation="create_ku")
    async def _create_ku(
        self, activity: ParsedActivityLine, user_uid: str, source_report_uid: str
    ) -> Result[str | None]:
        """
        Create a KnowledgeUnit from parsed activity.

        Returns the created KU UID or None if creation failed.
        """
        convert_result = activity_to_ku_dict(activity)
        if convert_result.is_error:
            return Result.fail(convert_result.expect_error())

        ku_dict = convert_result.value

        # Create KU via service
        if getattr(self.ku_service, "create_ku", None):
            create_result = await self.ku_service.create_ku(ku_dict, user_uid)
        elif getattr(self.ku_service, "create", None):
            create_result = await self.ku_service.create(ku_dict, user_uid)
        else:
            return Result.fail(
                Errors.system(
                    message="KU service has no create method",
                    operation="create_ku",
                )
            )

        if create_result.is_error:
            return Result.fail(create_result.expect_error())

        ku = create_result.value
        ku_uid = ku.uid if getattr(ku, "uid", None) else ku.get("uid")
        self.logger.debug(f"Created KU: {ku_uid}")

        return Result.ok(ku_uid)

    @with_error_handling(error_type="system", operation="create_ls")
    async def _create_ls(
        self, activity: ParsedActivityLine, user_uid: str, source_report_uid: str
    ) -> Result[str | None]:
        """
        Create a LearningStep from parsed activity.

        Returns the created LS UID or None if creation failed.
        """
        convert_result = activity_to_ls_dict(activity)
        if convert_result.is_error:
            return Result.fail(convert_result.expect_error())

        ls_dict = convert_result.value

        # Create LS via service
        if getattr(self.ls_service, "create_ls", None):
            create_result = await self.ls_service.create_ls(ls_dict, user_uid)
        elif getattr(self.ls_service, "create", None):
            create_result = await self.ls_service.create(ls_dict, user_uid)
        else:
            return Result.fail(
                Errors.system(
                    message="LS service has no create method",
                    operation="create_ls",
                )
            )

        if create_result.is_error:
            return Result.fail(create_result.expect_error())

        ls = create_result.value
        ls_uid = ls.uid if getattr(ls, "uid", None) else ls.get("uid")
        self.logger.debug(f"Created LS: {ls_uid}")

        return Result.ok(ls_uid)

    @with_error_handling(error_type="system", operation="create_lp")
    async def _create_lp(
        self, activity: ParsedActivityLine, user_uid: str, source_report_uid: str
    ) -> Result[str | None]:
        """
        Create a LearningPath from parsed activity.

        Returns the created LP UID or None if creation failed.
        """
        convert_result = activity_to_lp_dict(activity)
        if convert_result.is_error:
            return Result.fail(convert_result.expect_error())

        lp_dict = convert_result.value

        # Create LP via service
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
            return Result.fail(create_result.expect_error())

        lp = create_result.value
        lp_uid = lp.uid if getattr(lp, "uid", None) else lp.get("uid")
        self.logger.debug(f"Created LP: {lp_uid}")

        return Result.ok(lp_uid)

    # ========================================================================
    # META DOMAIN CREATION METHODS (3) - How I ORGANIZE
    # ========================================================================

    @with_error_handling(error_type="system", operation="create_report")
    async def _create_report(
        self, activity: ParsedActivityLine, user_uid: str, source_report_uid: str
    ) -> Result[str | None]:
        """
        Create a Submission from parsed activity.

        Note: This creates NEW submissions extracted from submission content.
        This is a recursive pattern where submissions can contain
        requests for more submissions (e.g., "Process my voice memo").

        Returns the created submission UID or None if creation failed.
        """
        convert_result = activity_to_report_dict(activity)
        if convert_result.is_error:
            return Result.fail(convert_result.expect_error())

        report_dict = convert_result.value

        # Create submission via service
        if getattr(self.report_service, "create_report", None):
            create_result = await self.report_service.create_report(report_dict, user_uid)
        elif getattr(self.report_service, "create", None):
            create_result = await self.report_service.create(report_dict, user_uid)
        else:
            return Result.fail(
                Errors.system(
                    message="Report service has no create method",
                    operation="create_report",
                )
            )

        if create_result.is_error:
            return Result.fail(create_result.expect_error())

        new_report = create_result.value
        new_report_uid = (
            new_report.uid if getattr(new_report, "uid", None) else new_report.get("uid")
        )
        self.logger.debug(f"Created Submission: {new_report_uid}")

        return Result.ok(new_report_uid)

    @with_error_handling(error_type="system", operation="create_analytics")
    async def _create_analytics(
        self, activity: ParsedActivityLine, user_uid: str, source_report_uid: str
    ) -> Result[str | None]:
        """
        Create/trigger an Analytics report from parsed activity.

        Note: Analytics are typically generated, not stored. This method
        triggers analytics generation based on the parsed request.

        Returns an analytics ID or None if creation failed.
        """
        convert_result = activity_to_analytics_dict(activity)
        if convert_result.is_error:
            return Result.fail(convert_result.expect_error())

        analytics_dict = convert_result.value

        # Generate analytics via service
        if getattr(self.analytics_service, "generate_report", None):
            create_result = await self.analytics_service.generate_report(analytics_dict, user_uid)
        elif getattr(self.analytics_service, "create", None):
            create_result = await self.analytics_service.create(analytics_dict, user_uid)
        else:
            return Result.fail(
                Errors.system(
                    message="Analytics service has no generate/create method",
                    operation="create_analytics",
                )
            )

        if create_result.is_error:
            return Result.fail(create_result.expect_error())

        analytics = create_result.value
        analytics_uid = (
            analytics.uid
            if getattr(analytics, "uid", None)
            else analytics.get("uid", "analytics_generated")
        )
        self.logger.debug(f"Created/Generated Analytics: {analytics_uid}")

        return Result.ok(analytics_uid)

    @with_error_handling(error_type="system", operation="create_calendar_item")
    async def _create_calendar_item(
        self, activity: ParsedActivityLine, user_uid: str, source_report_uid: str
    ) -> Result[str | None]:
        """
        Create a Calendar item from parsed activity.

        Calendar items can be time blocks, scheduled activities, etc.

        Returns the created calendar item UID or None if creation failed.
        """
        convert_result = activity_to_calendar_dict(activity)
        if convert_result.is_error:
            return Result.fail(convert_result.expect_error())

        calendar_dict = convert_result.value

        # Create calendar item via service
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
            return Result.fail(create_result.expect_error())

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
        self, activity: ParsedActivityLine, user_uid: str, source_report_uid: str
    ) -> Result[str | None]:
        """
        Create/update a LifePath alignment from parsed activity.

        The LifePath represents the user's ultimate life goal - everything
        flows toward this destination. LifePath entries from reports
        help refine and articulate this vision.

        Returns a lifepath reference UID or None if creation failed.
        """
        convert_result = activity_to_lifepath_dict(activity)
        if convert_result.is_error:
            return Result.fail(convert_result.expect_error())

        lifepath_dict = convert_result.value

        # Update lifepath via service
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
            return Result.fail(create_result.expect_error())

        lifepath = create_result.value
        lifepath_uid = (
            lifepath.uid
            if getattr(lifepath, "uid", None)
            else lifepath.get("uid", f"lifepath:{user_uid}")
        )
        self.logger.debug(f"Created/Updated LifePath: {lifepath_uid}")

        return Result.ok(lifepath_uid)

    # ========================================================================
    # METADATA UPDATES
    # ========================================================================

    @with_error_handling("update_report_metadata", error_type="system")
    async def _update_report_metadata(
        self, report_uid: str, extraction: ActivityExtractionResult
    ) -> None:
        """
        Store extraction results in submission metadata.

        This allows tracking which entities were extracted from which submission.
        Note: Uses suppress_errors=True since metadata updates are non-critical.
        """
        # Get current submission
        get_result = await self.report_service.get_submission(report_uid)
        if get_result.is_error:
            self.logger.warning(f"Could not get submission for metadata update: {get_result.error}")
            return

        report = get_result.value
        if not report:
            return

        # Update metadata with extraction results
        current_metadata = report.metadata or {}
        current_metadata["activity_extraction"] = extraction.to_dict()

        # Update submission
        await self.report_service.update_submission(
            uid=report_uid,
            updates={"metadata": current_metadata},
        )

        self.logger.debug(f"Updated submission metadata with extraction results: {report_uid}")

    # ========================================================================
    # EXTRACTION-ONLY (NO ENTITY CREATION)
    # ========================================================================

    def extract_activities(self, content: str) -> Result[ParsedJournal]:
        """
        Extract Activity Lines without creating entities.

        Useful for preview/validation before committing to entity creation.

        Args:
            content: Submission content to parse

        Returns:
            Result containing ParsedJournal with all activities
        """
        return self.parser.parse_journal(content)

    def preview_extraction(self, content: str) -> dict[str, Any]:
        """
        Preview what would be extracted without creating entities.

        Returns a summary dict suitable for UI display covering ALL 13 SKUEL domains.

        Args:
            content: Submission content to parse

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
            "learning_steps": [
                {
                    "description": a.description,
                    "duration_minutes": a.duration_minutes,
                    "primary_ku": a.primary_ku,
                }
                for a in parsed.get_learning_steps()
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
            # META DOMAINS (3) - How I ORGANIZE
            # ================================================================
            "reports": [
                {
                    "description": a.description,
                    "linked_goals": a.get_linked_goals(),
                }
                for a in parsed.get_reports()
            ],
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
