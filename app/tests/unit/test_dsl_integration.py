# mypy: disable-error-code="union-attr"
"""
Integration Tests for SKUEL DSL Pipeline
========================================

Tests the full flow from journal content to entity creation.
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.pipeline import Pipeline
from core.models.user_entry.user_entry import UserEntry
from core.services.dsl import (
    ActivityExtractionResult,
    ActivityExtractorService,
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
        # Use dynamic future date to avoid validation errors
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
            "- [ ] Study @context(task) @ku(ku.math/algebra) @link(ku:math/basics)"
        )
        task_activity = result.value.get_tasks()[0]
        convert_result = activity_to_task_request(task_activity)

        assert convert_result.is_ok
        request = convert_result.value
        assert "ku.math/algebra" in request.applies_knowledge_uids
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
    """Test the ActivityExtractorService."""

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
    def mock_ku(self):
        """Create a mock entity with journal content."""
        # Use dynamic future date to avoid validation errors
        from datetime import timedelta

        future_date = date.today() + timedelta(days=30)
        when_str = future_date.strftime("%Y-%m-%dT10:00")

        return UserEntry(
            uid="report:test",
            title="Test Journal",
            user_uid="user_mike",
            entity_type=EntityType.USER_ENTRY,
            status=EntityStatus.COMPLETED,
            pipeline=Pipeline.NONE,
            original_filename="journal.md",
            file_path="/tmp/journal.md",
            file_type="text/plain",
            file_size=1000,
            processed_content=f"""
### Today's Journal

Had a productive morning.

- [ ] Call the bank @context(task) @priority(1) @when({when_str})
- [ ] Morning meditation @context(habit) @duration(20m) @energy(spiritual)
- [ ] Read chapter 3 @context(task,learning) @ku(ku.books/productivity)

Some reflections on the day...
""",
        )

    @pytest.fixture
    def extractor(self, mock_tasks_service):
        """Create extractor with mock services."""
        return ActivityExtractorService(
            tasks_service=mock_tasks_service,
            habits_service=None,  # Not testing habit creation
            goals_service=None,
            events_service=None,
        )

    @pytest.mark.asyncio
    async def test_extract_finds_activities(self, extractor, mock_ku):
        """Extractor finds all activity lines."""
        result = await extractor.extract_and_create(mock_ku, "user_mike")

        assert result.is_ok
        extraction = result.value
        assert extraction.activities_found == 3
        assert extraction.tasks_found == 2  # Two tasks (one is task+learning)
        assert extraction.habits_found == 1

    @pytest.mark.asyncio
    async def test_extract_creates_tasks(self, extractor, mock_ku, mock_tasks_service):
        """Extractor creates tasks via service."""
        result = await extractor.extract_and_create(mock_ku, "user_mike")

        assert result.is_ok
        extraction = result.value
        assert extraction.tasks_created == 2
        assert len(extraction.created_task_uids) == 2

        # Verify service was called
        assert mock_tasks_service.create_task.call_count == 2

    @pytest.mark.asyncio
    async def test_extract_records_line_provenance(self, extractor, mock_ku):
        """Each created entity carries a (uid, line_hash, vault_id) provenance triple."""
        result = await extractor.extract_and_create(mock_ku, "user_mike")

        assert result.is_ok
        extraction = result.value
        assert len(extraction.created_links) == extraction.total_created
        for uid, line_hash, _vault_id in extraction.created_links:
            assert uid == "task:123"
            assert len(line_hash) == 64  # sha256 hex digest

    @pytest.mark.asyncio
    async def test_extract_skips_existing_line_hashes(self, extractor, mock_ku):
        """Guard 2: lines whose hash already has an EXTRACTED_FROM edge skip."""
        first = await extractor.extract_and_create(mock_ku, "user_mike")
        assert first.is_ok
        existing = frozenset(line_hash for _, line_hash, _vault_id in first.value.created_links)

        second = await extractor.extract_and_create(
            mock_ku, "user_mike", existing_line_hashes=existing
        )

        assert second.is_ok
        extraction = second.value
        assert extraction.tasks_created == 0
        assert extraction.created_links == []
        assert extraction.lines_skipped_existing == 2

    @pytest.mark.asyncio
    async def test_extract_collects_ku_references(self, extractor, mock_ku):
        """@ku() references are collected for APPLIES_KNOWLEDGE edge writes."""
        result = await extractor.extract_and_create(mock_ku, "user_mike")

        assert result.is_ok
        assert result.value.referenced_ku_uids == ["ku.books/productivity"]

    @pytest.mark.asyncio
    async def test_extract_content_override_wins(self, extractor, mock_ku):
        """content_override is parsed instead of the entry's own content."""
        result = await extractor.extract_and_create(
            mock_ku,
            "user_mike",
            content_override="- [ ] Only this @context(task)",
        )

        assert result.is_ok
        extraction = result.value
        assert extraction.activities_found == 1
        assert extraction.tasks_found == 1
        assert extraction.habits_found == 0

    @pytest.mark.asyncio
    async def test_curriculum_creation_gated_for_non_teacher(self, mock_tasks_service):
        """Non-teacher @context(ku) creation lines are recorded, not created."""
        mock_ku_service = AsyncMock()
        extractor = ActivityExtractorService(
            tasks_service=mock_tasks_service,
            ku_service=mock_ku_service,
        )
        entry = UserEntry(
            uid="ue_gate",
            title="Gate test",
            user_uid="user_member",
            entity_type=EntityType.USER_ENTRY,
            status=EntityStatus.COMPLETED,
            pipeline=Pipeline.EXTRACT_ACTIVITIES,
            content=(
                "- [ ] Python decorators @context(ku)\n"
                "- [ ] Practice decorators @context(task) @ku(ku.tech/decorators)\n"
            ),
        )

        result = await extractor.extract_and_create(
            entry, "user_member", allow_curriculum_creation=False
        )

        assert result.is_ok
        extraction = result.value
        assert extraction.kus_created == 0
        mock_ku_service.create_ku.assert_not_called()
        assert any(
            "curriculum creation requires teacher/admin role" in e
            for e in extraction.creation_errors
        )
        # The @ku() reference on the task line still resolves
        assert "ku.tech/decorators" in extraction.referenced_ku_uids
        assert extraction.tasks_created == 1

    @pytest.mark.asyncio
    async def test_extract_handles_empty_content(self, extractor):
        """Extractor handles empty content gracefully."""
        empty_entry = UserEntry(
            uid="ue_empty",
            title="Empty",
            user_uid="user_mike",
            entity_type=EntityType.USER_ENTRY,
            status=EntityStatus.COMPLETED,
            pipeline=Pipeline.NONE,
            original_filename="empty.md",
            file_path="/tmp/empty.md",
            file_type="text/plain",
            file_size=0,
            processed_content="",
        )

        result = await extractor.extract_and_create(empty_entry, "user_mike")

        assert result.is_ok
        extraction = result.value
        assert extraction.activities_found == 0
        assert extraction.total_created == 0

    @pytest.mark.asyncio
    async def test_unrouted_lines_surface_as_warnings(self, extractor):
        """Lines whose contexts all lack a wired create surface are recorded, not silent."""
        entry = UserEntry(
            uid="ue_unrouted",
            title="Unrouted",
            user_uid="user_mike",
            entity_type=EntityType.USER_ENTRY,
            status=EntityStatus.COMPLETED,
            pipeline=Pipeline.NONE,
            original_filename="unrouted.md",
            file_path="/tmp/unrouted.md",
            file_type="text/plain",
            file_size=100,
            # ps is staged (ps_service unwired in this fixture AND production);
            # the task line routes normally.
            processed_content=("- [ ] Study step @context(ps)\n- [ ] Call bank @context(task)\n"),
        )

        result = await extractor.extract_and_create(entry, "user_mike")

        assert result.is_ok
        extraction = result.value
        assert extraction.tasks_created == 1
        assert len(extraction.unrouted_lines) == 1
        assert "Study step" in extraction.unrouted_lines[0]
        assert "path_step" in extraction.unrouted_lines[0]
        # Rides into the persisted summary the sync warnings read
        assert extraction.to_dict()["unrouted_lines"] == extraction.unrouted_lines

    @pytest.mark.asyncio
    async def test_mixed_context_reports_skipped_context(self, extractor):
        """@context(task,ps): Task is created AND the skipped ps context is reported."""
        entry = UserEntry(
            uid="ue_mixed",
            title="Mixed",
            user_uid="user_mike",
            entity_type=EntityType.USER_ENTRY,
            status=EntityStatus.COMPLETED,
            pipeline=Pipeline.NONE,
            original_filename="mixed.md",
            file_path="/tmp/mixed.md",
            file_type="text/plain",
            file_size=100,
            processed_content="- [ ] Draft lesson @context(task,ps)\n",
        )

        result = await extractor.extract_and_create(entry, "user_mike")

        assert result.is_ok
        extraction = result.value
        assert extraction.tasks_created == 1
        assert len(extraction.unrouted_lines) == 1
        warning = extraction.unrouted_lines[0]
        assert "path_step" in warning and "skipped" in warning
        assert "task" in warning  # names what WAS created

    @pytest.mark.asyncio
    async def test_tag_warnings_ride_into_extraction_summary(self, extractor):
        """Dropped tag values surface in the run summary the sync warnings read."""
        entry = UserEntry(
            uid="ue_tagwarn",
            title="TagWarn",
            user_uid="user_mike",
            entity_type=EntityType.USER_ENTRY,
            status=EntityStatus.COMPLETED,
            pipeline=Pipeline.NONE,
            original_filename="tagwarn.md",
            file_path="/tmp/tagwarn.md",
            file_type="text/plain",
            file_size=100,
            processed_content="- [ ] Finish report @context(task) @when(Friday)\n",
        )

        result = await extractor.extract_and_create(entry, "user_mike")

        assert result.is_ok
        extraction = result.value
        assert extraction.tasks_created == 1  # entity still created
        assert len(extraction.tag_warnings) == 1
        assert "Finish report" in extraction.tag_warnings[0]
        assert "@when(Friday)" in extraction.tag_warnings[0]
        assert extraction.to_dict()["tag_warnings"] == extraction.tag_warnings

    @pytest.mark.asyncio
    async def test_tag_warnings_not_repeated_for_already_extracted_lines(self, extractor):
        """A line already carrying EXTRACTED_FROM provenance doesn't re-warn on re-sync."""
        from core.services.dsl.activity_extractor import normalized_line_hash

        line = "- [ ] Finish report @context(task) @when(Friday)"
        entry = UserEntry(
            uid="ue_renag",
            title="ReNag",
            user_uid="user_mike",
            entity_type=EntityType.USER_ENTRY,
            status=EntityStatus.COMPLETED,
            pipeline=Pipeline.NONE,
            original_filename="renag.md",
            file_path="/tmp/renag.md",
            file_type="text/plain",
            file_size=100,
            processed_content=f"{line}\n",
        )

        result = await extractor.extract_and_create(
            entry,
            "user_mike",
            existing_line_hashes=frozenset({normalized_line_hash(line)}),
        )

        assert result.is_ok
        extraction = result.value
        assert extraction.tasks_created == 0  # Guard 2 skipped the line
        assert extraction.tag_warnings == []  # and the warning is gated with it

    @pytest.mark.asyncio
    async def test_a_line_whose_vault_id_is_already_extracted_is_skipped_by_identity(
        self, extractor
    ):
        """Guard 2b. SKUEL's own ``[x]`` + ``✅ date`` write-back moves a line's
        hash (the ✅ date is a discriminator, kept in the digest), so Guard 2
        misses it and Guard 4 ignores the now-terminal twin — the line's 🆔,
        already on this entry's EXTRACTED_FROM edge, is what says "mine". The
        edge's stale digest is retired BEFORE any line is checked against it,
        so a same-text unchecked sibling in the same ingest (placed FIRST here)
        is a new task, as is a line carrying a 🆔 the entry has never seen. A
        🆔 that holds TWO edges — the original task and the copy the bug once
        made — is treated as one line: every stale edge retired and refreshed,
        an edge already at the current digest left alone."""
        from core.services.dsl.activity_extractor import (
            ExtractedByVaultId,
            normalized_line_hash,
        )

        original = "- [ ] Water the plants"  # what the edge was extracted from
        mine = "- [x] Water the plants 🆔 sk_mine01 ✅ 2026-08-17"  # after the write-back
        entry = UserEntry(
            uid="ue_ident",
            title="Identity",
            user_uid="user_mike",
            entity_type=EntityType.USER_ENTRY,
            status=EntityStatus.COMPLETED,
            pipeline=Pipeline.NONE,
            original_filename="ident.md",
            file_path="/tmp/ident.md",
            file_type="text/plain",
            # Plain obsidian-tasks checkbox lines — the shape the vault holds
            # and the only parser pass that reads the 🆔 off a line.
            processed_content=(
                f"{original}\n"  # the new sibling, same text as the ORIGINAL line
                f"{mine}\n"
                "- [x] Water the plants 🆔 sk_other2 ✅ 2026-08-19\n"
            ),
        )

        result = await extractor.extract_and_create(
            entry,
            "user_mike",
            existing_line_hashes=frozenset(
                {normalized_line_hash(original), normalized_line_hash(mine)}
            ),
            existing_vault_ids={
                "sk_mine01": (
                    ExtractedByVaultId("task_mine", normalized_line_hash(original)),  # stale
                    ExtractedByVaultId("task_copy", normalized_line_hash(mine)),  # current
                )
            },
        )

        assert result.is_ok
        extraction = result.value
        assert extraction.lines_skipped_existing == 1
        assert extraction.tasks_created == 2, extraction.to_dict()
        assert [vault_id for _uid, _hash, vault_id in extraction.created_links] == [
            None,
            "sk_other2",
        ]
        # The matched edge's change signal moves with the line: a stale digest
        # would swallow the next same-text line the user adds.
        assert extraction.refreshed_links == [
            ("task_mine", normalized_line_hash(mine), "sk_mine01")
        ], "only the stale edge is refreshed; the copy's edge is already current"
        assert extraction.to_dict()["lines_rehashed"] == 1

    @pytest.mark.asyncio
    async def test_bridge_generated_lines_never_tag_warn(self, extractor):
        """Bridge lines carry deliberately loose tags — not the user's values to fix."""
        from core.services.dsl.activity_extractor import normalized_line_hash

        line = "- [ ] Finish report @context(task) @when(Friday)"
        entry = UserEntry(
            uid="ue_bridge",
            title="Bridge",
            user_uid="user_mike",
            entity_type=EntityType.USER_ENTRY,
            status=EntityStatus.COMPLETED,
            pipeline=Pipeline.NONE,
            original_filename="bridge.md",
            file_path="/tmp/bridge.md",
            file_type="text/plain",
            file_size=100,
            processed_content=f"{line}\n",
        )

        result = await extractor.extract_and_create(
            entry,
            "user_mike",
            bridge_line_hashes=frozenset({normalized_line_hash(line)}),
        )

        assert result.is_ok
        extraction = result.value
        assert extraction.tasks_created == 1  # bridge line still extracts
        assert extraction.tag_warnings == []  # but never nags about loose tags

    @pytest.mark.asyncio
    async def test_learning_modifier_never_reported_as_skipped(self, extractor):
        """@context(task,learning): modifier creates nothing by design — no warning."""
        entry = UserEntry(
            uid="ue_modifier",
            title="Modifier",
            user_uid="user_mike",
            entity_type=EntityType.USER_ENTRY,
            status=EntityStatus.COMPLETED,
            pipeline=Pipeline.NONE,
            original_filename="modifier.md",
            file_path="/tmp/modifier.md",
            file_type="text/plain",
            file_size=100,
            processed_content="- [ ] Read chapter @context(task,learning)\n",
        )

        result = await extractor.extract_and_create(entry, "user_mike")

        assert result.is_ok
        extraction = result.value
        assert extraction.tasks_created == 1
        assert extraction.unrouted_lines == []

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
            entry_uid="test",
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
            entry_uid="test",
            user_uid="user",
        )
        assert not result_clean.has_errors

        result_parse_error = ActivityExtractionResult(
            entry_uid="test",
            user_uid="user",
            parse_errors=["Line 5: Invalid @context"],
        )
        assert result_parse_error.has_errors

        result_create_error = ActivityExtractionResult(
            entry_uid="test",
            user_uid="user",
            creation_errors=["Task creation failed"],
        )
        assert result_create_error.has_errors

    def test_to_dict(self):
        """to_dict produces serializable output."""
        result = ActivityExtractionResult(
            entry_uid="test",
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
        # Use dynamic future date to avoid validation errors
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
- [ ] Evening journaling @context(habit) @duration(15m) @repeat(daily)

**Learning goals:**
- [ ] Complete Python async chapter @context(task,learning) @ku(ku.tech/python-async) @link(goal:tech/mastery)
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
        assert learning_task.primary_ku == "ku.tech/python-async"
        assert "goal:tech/mastery" in learning_task.get_linked_goals()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
