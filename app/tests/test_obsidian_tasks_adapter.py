# mypy: disable-error-code="union-attr"
"""
Tests for the Obsidian-Tasks Extractor Adapter
==============================================

Covers `obsidian_task_line_to_parsed` (line → ParsedActivityLine for each
emoji), the converter's scheduled_date + tag merge, and the `parse_journal`
second-pass integration that makes periodic notes extract Tasks without
`@context` tags.
"""

from datetime import date, datetime

import pytest

from core.models.enums.entity_enums import EntityType
from core.services.dsl.activity_domain_converters import activity_to_task_request
from core.services.dsl.activity_dsl_parser import ActivityDSLParser
from core.services.dsl.obsidian_tasks_adapter import obsidian_task_line_to_parsed


class TestCheckboxGate:
    """Only markdown checkbox lines produce a ParsedActivityLine."""

    @pytest.mark.parametrize(
        "line",
        ["- [ ] A task", "- [x] Done task", "- [X] Done task", "* [ ] Star bullet task"],
    )
    def test_checkbox_lines_parse(self, line):
        assert obsidian_task_line_to_parsed(line) is not None

    @pytest.mark.parametrize(
        "line",
        ["## Heading", "- plain bullet", "Just a note", "", "   ", "1. numbered"],
    )
    def test_non_checkbox_lines_return_none(self, line):
        assert obsidian_task_line_to_parsed(line) is None

    def test_context_is_always_task(self):
        parsed = obsidian_task_line_to_parsed("- [ ] Something")
        assert parsed.contexts == [EntityType.TASK]
        assert parsed.is_task()


class TestCheckedState:
    def test_unchecked(self):
        assert obsidian_task_line_to_parsed("- [ ] Open").is_checked is False

    def test_checked(self):
        assert obsidian_task_line_to_parsed("- [x] Closed").is_checked is True

    def test_raw_line_normalized_for_stable_hash(self):
        """Checked box is normalized to '- [ ]' so the dedup hash is stable."""
        parsed = obsidian_task_line_to_parsed("- [x] Closed ⏬")
        assert parsed.raw_line == "- [ ] Closed ⏬"

    def test_raw_line_canonicalizes_star_bullet(self):
        """'*' bullets normalize to '- [ ]' too (checked and unchecked)."""
        assert obsidian_task_line_to_parsed("* [ ] Star").raw_line == "- [ ] Star"
        assert obsidian_task_line_to_parsed("* [x] Star").raw_line == "- [ ] Star"

    def test_hash_stable_across_check_for_star_bullet(self):
        """Star-bullet check/uncheck must hash identically (no duplicate on re-sync)."""
        from core.services.dsl.activity_extractor import normalized_line_hash

        unchecked = obsidian_task_line_to_parsed("* [ ] Star task 📅 2026-06-25")
        checked = obsidian_task_line_to_parsed("* [x] Star task 📅 2026-06-25")
        assert normalized_line_hash(unchecked.raw_line) == normalized_line_hash(checked.raw_line)


class TestDates:
    def test_due_date_via_calendar_emoji(self):
        parsed = obsidian_task_line_to_parsed("- [ ] Ship it 📅 2026-06-20")
        assert parsed.when == datetime(2026, 6, 20)

    def test_scheduled_date_via_hourglass_emoji(self):
        parsed = obsidian_task_line_to_parsed("- [ ] Prep ⏳ 2026-06-18")
        assert parsed.scheduled_date == date(2026, 6, 18)

    def test_both_dates(self):
        parsed = obsidian_task_line_to_parsed("- [ ] Plan ⏳ 2026-06-18 📅 2026-06-25")
        assert parsed.scheduled_date == date(2026, 6, 18)
        assert parsed.when.date() == date(2026, 6, 25)

    def test_no_dates(self):
        parsed = obsidian_task_line_to_parsed("- [ ] Undated")
        assert parsed.when is None
        assert parsed.scheduled_date is None

    def test_malformed_date_ignored(self):
        parsed = obsidian_task_line_to_parsed("- [ ] Bad 📅 2026-13-99")
        assert parsed.when is None


class TestPriority:
    @pytest.mark.parametrize(
        "emoji,expected",
        [("🔺", 1), ("⏫", 1), ("🔼", 2), ("🔽", 4), ("⏬", 5)],
    )
    def test_priority_emoji_mapping(self, emoji, expected):
        parsed = obsidian_task_line_to_parsed(f"- [ ] Task {emoji}")
        assert parsed.priority == expected

    def test_no_priority_defaults_medium(self):
        assert obsidian_task_line_to_parsed("- [ ] Task").priority == 3


class TestTags:
    def test_hashtags_become_extra_tags(self):
        parsed = obsidian_task_line_to_parsed("- [ ] Task #work #home/office")
        assert parsed.extra_tags == ["work", "home/office"]

    def test_period_tag_from_entry_kind(self):
        parsed = obsidian_task_line_to_parsed("- [ ] Task #work", entry_kind="daily")
        assert parsed.extra_tags == ["work", "period:daily"]

    def test_no_period_tag_without_entry_kind(self):
        parsed = obsidian_task_line_to_parsed("- [ ] Task")
        assert parsed.extra_tags == []


class TestDescriptionCleaning:
    def test_strips_emoji_dates_and_tags(self):
        parsed = obsidian_task_line_to_parsed(
            "- [ ] Write the report 📅 2026-06-20 ⏳ 2026-06-18 ⏫ #work #urgent",
            entry_kind="daily",
        )
        assert parsed.description == "Write the report"


class TestConverterIntegration:
    """The task converter carries scheduled_date + merged tags through."""

    def test_scheduled_date_and_tags_flow_to_request(self):
        parsed = obsidian_task_line_to_parsed(
            "- [ ] Build 📅 2026-06-25 ⏳ 2026-06-20 ⏫ #work",
            entry_kind="weekly",
        )
        result = activity_to_task_request(parsed)
        assert result.is_ok
        request = result.value
        assert request.title == "Build"
        assert request.due_date == date(2026, 6, 25)
        assert request.scheduled_date == date(2026, 6, 20)
        assert request.tags == ["work", "period:weekly"]

    def test_tags_merge_dedups(self):
        parsed = obsidian_task_line_to_parsed("- [ ] T #focus", entry_kind="daily")
        parsed.energy_states = ["focus"]  # also present as a #tag
        result = activity_to_task_request(parsed)
        assert result.is_ok
        # 'focus' appears once; order preserved (energy first).
        assert result.value.tags == ["focus", "period:daily"]


class TestParseJournalSecondPass:
    """parse_journal extracts obsidian-tasks lines alongside @context lines."""

    def test_mixed_journal(self):
        text = (
            "## Tasks\n"
            "- [ ] Obsidian task 📅 2026-06-25 #home\n"
            "- [x] Done thing\n"
            "- plain bullet, not a task\n"
            "- [ ] DSL task @context(task)\n"
            "## Notes\n"
            "Some prose.\n"
        )
        result = ActivityDSLParser().parse_journal(text, source_file="ue:test", entry_kind="daily")
        assert result.is_ok
        tasks = result.value.get_tasks()
        assert len(tasks) == 3
        descriptions = {t.description for t in tasks}
        assert "Obsidian task" in descriptions
        assert "Done thing" in descriptions
        assert "DSL task" in descriptions

    def test_period_tag_stamped_in_second_pass(self):
        result = ActivityDSLParser().parse_journal(
            "- [ ] Task #work", source_file="ue:x", entry_kind="monthly"
        )
        assert result.is_ok
        (task,) = result.value.get_tasks()
        assert "period:monthly" in task.extra_tags

    def test_source_provenance_carried(self):
        result = ActivityDSLParser().parse_journal("- [ ] Task", source_file="ue:abc")
        (task,) = result.value.get_tasks()
        assert task.source_file == "ue:abc"
        assert task.source_line == 1
