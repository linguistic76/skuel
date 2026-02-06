"""
Integration Tests for SKUEL DSL Pipeline
========================================

Tests the full flow from journal content to entity creation.
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.report.report import (
    ProcessorType,
    Report,
    ReportStatus,
    ReportType,
)
from core.services.dsl import (
    ActivityExtractionResult,
    JournalActivityExtractorService,
    activity_to_task_request,
    parse_journal_text,
)


class TestActivityToTaskConversion:
    """Test conversion from parsed activities to TaskCreateRequest."""

    def test_convert_simple_task(self):
        """Convert a simple parsed task to TaskCreateRequest."""
        result = parse_journal_text("- [ ] Call mom @context(task)")
        assert result.is_ok

        task_activity = result.value.get_tasks()[0]
        convert_result = activity_to_task_request(task_activity)

        assert convert_result.is_ok
        request = convert_result.value
        assert request.title == "Call mom"

    def test_convert_task_with_priority(self):
        """Priority 1 maps to CRITICAL."""
        result = parse_journal_text("- [ ] Urgent @context(task) @priority(1)")
        task_activity = result.value.get_tasks()[0]
        convert_result = activity_to_task_request(task_activity)

        assert convert_result.is_ok
        request = convert_result.value
        assert request.priority.value == "critical"

    def test_convert_task_with_due_date(self):
        """@when maps to due_date."""
        # ✅ Use dynamic future date to avoid validation errors
        from datetime import timedelta

        future_date = date.today() + timedelta(days=30)
        when_str = future_date.strftime("%Y-%m-%dT10:00")

        result = parse_journal_text(f"- [ ] Task @context(task) @when({when_str})")
        task_activity = result.value.get_tasks()[0]
        convert_result = activity_to_task_request(task_activity)

        assert convert_result.is_ok
        request = convert_result.value
        assert request.due_date == future_date

    def test_convert_task_with_duration(self):
        """@duration maps to duration_minutes."""
        result = parse_journal_text("- [ ] Task @context(task) @duration(90m)")
        task_activity = result.value.get_tasks()[0]
        convert_result = activity_to_task_request(task_activity)

        assert convert_result.is_ok
        request = convert_result.value
        assert request.duration_minutes == 90

    def test_convert_task_with_knowledge(self):
        """@ku and @link(ku:...) map to applies_knowledge_uids."""
        result = parse_journal_text(
            "- [ ] Study @context(task) @ku(ku:math/algebra) @link(ku:math/basics)"
        )
        task_activity = result.value.get_tasks()[0]
        convert_result = activity_to_task_request(task_activity)

        assert convert_result.is_ok
        request = convert_result.value
        assert "ku:math/algebra" in request.applies_knowledge_uids
        assert "ku:math/basics" in request.applies_knowledge_uids

    def test_convert_task_with_goal(self):
        """@link(goal:...) maps to fulfills_goal_uid."""
        result = parse_journal_text("- [ ] Work out @context(task) @link(goal:health/fitness)")
        task_activity = result.value.get_tasks()[0]
        convert_result = activity_to_task_request(task_activity)

        assert convert_result.is_ok
        request = convert_result.value
        assert request.fulfills_goal_uid == "goal:health/fitness"

    def test_convert_checked_task(self):
        """Checked tasks [x] become COMPLETED status."""
        result = parse_journal_text("- [x] Done task @context(task)")
        task_activity = result.value.get_tasks()[0]
        convert_result = activity_to_task_request(task_activity)

        assert convert_result.is_ok
        request = convert_result.value
        assert request.status.value == "completed"


class TestJournalActivityExtractor:
    """Test the JournalActivityExtractorService."""

    @pytest.fixture
    def mock_tasks_service(self):
        """Create a mock tasks service."""
        service = AsyncMock()
        service.create_task = AsyncMock(
            return_value=MagicMock(
                is_ok=True, is_error=False, value=MagicMock(uid="task:123", title="Test Task")
            )
        )
        return service

    @pytest.fixture
    def mock_report(self):
        """Create a mock report with journal content."""
        # ✅ Use dynamic future date to avoid validation errors
        from datetime import timedelta

        future_date = date.today() + timedelta(days=30)
        when_str = future_date.strftime("%Y-%m-%dT10:00")

        return Report(
            uid="report:test",
            user_uid="user:mike",
            report_type=ReportType.TRANSCRIPT,
            status=ReportStatus.COMPLETED,
            processor_type=ProcessorType.LLM,
            original_filename="journal.md",
            file_path="/tmp/journal.md",
            file_type="text/plain",
            file_size=1000,
            processed_content=f"""
### Today's Journal

Had a productive morning.

- [ ] Call the bank @context(task) @priority(1) @when({when_str})
- [ ] Morning meditation @context(habit) @duration(20m) @energy(spiritual)
- [ ] Read chapter 3 @context(task,learning) @ku(ku:books/productivity)

Some reflections on the day...
""",
            metadata={},
        )

    @pytest.fixture
    def extractor(self, mock_tasks_service):
        """Create extractor with mock services."""
        return JournalActivityExtractorService(
            tasks_service=mock_tasks_service,
            habits_service=None,  # Not testing habit creation
            goals_service=None,
            events_service=None,
            report_service=None,
        )

    @pytest.mark.asyncio
    async def test_extract_finds_activities(self, extractor, mock_report):
        """Extractor finds all activity lines."""
        result = await extractor.extract_and_create(
            report=mock_report,
            user_uid="user:mike",
        )

        assert result.is_ok
        extraction = result.value
        assert extraction.activities_found == 3
        assert extraction.tasks_found == 2  # Two tasks (one is task+learning)
        assert extraction.habits_found == 1

    @pytest.mark.asyncio
    async def test_extract_creates_tasks(self, extractor, mock_report, mock_tasks_service):
        """Extractor creates tasks via service."""
        result = await extractor.extract_and_create(
            report=mock_report,
            user_uid="user:mike",
        )

        assert result.is_ok
        extraction = result.value
        assert extraction.tasks_created == 2
        assert len(extraction.created_task_uids) == 2

        # Verify service was called
        assert mock_tasks_service.create_task.call_count == 2

    @pytest.mark.asyncio
    async def test_extract_handles_empty_content(self, extractor):
        """Extractor handles empty content gracefully."""
        empty_report = Report(
            uid="report:empty",
            user_uid="user:mike",
            report_type=ReportType.TRANSCRIPT,
            status=ReportStatus.COMPLETED,
            processor_type=ProcessorType.LLM,
            original_filename="empty.md",
            file_path="/tmp/empty.md",
            file_type="text/plain",
            file_size=0,
            processed_content="",
            metadata={},
        )

        result = await extractor.extract_and_create(
            report=empty_report,
            user_uid="user:mike",
        )

        assert result.is_ok
        extraction = result.value
        assert extraction.activities_found == 0
        assert extraction.total_created == 0

    def test_preview_extraction(self, extractor):
        """Preview shows what would be extracted."""
        content = """
- [ ] Task one @context(task) @priority(1)
- [ ] Task two @context(task)
- [ ] Habit @context(habit) @repeat(daily)
"""
        preview = extractor.preview_extraction(content)

        assert preview["success"]
        assert preview["total_activities"] == 3
        assert len(preview["tasks"]) == 2
        assert len(preview["habits"]) == 1


class TestExtractionResult:
    """Test ActivityExtractionResult dataclass."""

    def test_total_created(self):
        """total_created sums all entity counts."""
        result = ActivityExtractionResult(
            report_uid="test",
            user_uid="user",
            tasks_created=3,
            habits_created=2,
            goals_created=1,
            events_created=0,
        )

        assert result.total_created == 6

    def test_has_errors(self):
        """has_errors detects any error lists."""
        result_clean = ActivityExtractionResult(
            report_uid="test",
            user_uid="user",
        )
        assert not result_clean.has_errors

        result_parse_error = ActivityExtractionResult(
            report_uid="test",
            user_uid="user",
            parse_errors=["Line 5: Invalid @context"],
        )
        assert result_parse_error.has_errors

        result_create_error = ActivityExtractionResult(
            report_uid="test",
            user_uid="user",
            creation_errors=["Task creation failed"],
        )
        assert result_create_error.has_errors

    def test_to_dict(self):
        """to_dict produces serializable output."""
        result = ActivityExtractionResult(
            report_uid="test",
            user_uid="user",
            activities_found=5,
            tasks_created=2,
            created_task_uids=["task:1", "task:2"],
        )

        d = result.to_dict()
        assert d["activities_found"] == 5
        assert d["tasks_created"] == 2
        assert d["created_task_uids"] == ["task:1", "task:2"]
        assert d["total_created"] == 2


class TestFullPipeline:
    """Test the complete DSL pipeline."""

    def test_parse_convert_flow(self):
        """Test parse → convert flow for a realistic journal."""
        # ✅ Use dynamic future date to avoid validation errors
        from datetime import timedelta

        future_date = date.today() + timedelta(days=30)
        date_header = future_date.strftime("%B %d, %Y")
        when_task = future_date.strftime("%Y-%m-%dT14:00")
        when_event = future_date.strftime("%Y-%m-%dT09:30")

        journal = f"""
### Morning Focus - {date_header}

Today I want to focus on deep work and learning.

**Tasks for today:**
- [ ] Review PR for authentication feature @context(task) @priority(1) @duration(45m)
- [ ] Write documentation for API endpoints @context(task) @priority(2) @when({when_task})
- [ ] Call team standup @context(event) @when({when_event}) @duration(30m)

**Habits to maintain:**
- [ ] Morning meditation @context(habit) @duration(20m) @energy(spiritual,rest) @repeat(daily)
- [ ] Evening journaling @context(habit,journal) @duration(15m) @repeat(daily)

**Learning goals:**
- [ ] Complete Python async chapter @context(task,learning) @ku(ku:tech/python-async) @link(goal:tech/mastery)
- Reach 1000 GitHub stars @context(goal) @link(project:opensource/mylib)

Some reflections on yesterday's work...
"""

        # Step 1: Parse
        parse_result = parse_journal_text(journal)
        assert parse_result.is_ok

        parsed = parse_result.value
        assert parsed.activity_lines_found == 7

        # Step 2: Check distribution
        assert len(parsed.get_tasks()) == 3  # 2 plain tasks + 1 task/learning
        assert len(parsed.get_habits()) == 2
        assert len(parsed.get_events()) == 1
        assert len(parsed.get_goals()) == 1

        # Step 3: Convert tasks
        for task_activity in parsed.get_tasks():
            convert_result = activity_to_task_request(task_activity)
            assert convert_result.is_ok, f"Failed to convert: {task_activity.description}"

        # Step 4: Verify specific task properties
        pr_task = next(t for t in parsed.get_tasks() if "PR" in t.description)
        assert pr_task.priority == 1
        assert pr_task.duration_minutes == 45

        learning_task = next(t for t in parsed.get_tasks() if "Python" in t.description)
        assert learning_task.is_learning()
        assert learning_task.primary_ku == "ku:tech/python-async"
        assert "goal:tech/mastery" in learning_task.get_linked_goals()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
