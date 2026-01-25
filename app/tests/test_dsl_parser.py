"""
Tests for SKUEL Activity DSL Parser
===================================

Tests the core parsing functionality for Activity Lines.
"""

from datetime import datetime

import pytest

from core.services.dsl import (
    is_activity_line,
    parse_activity_line,
    parse_journal_text,
)


class TestActivityLineDetection:
    """Test detection of Activity Lines."""

    def test_is_activity_line_with_context(self):
        """Lines with @context are Activity Lines."""
        assert is_activity_line("- [ ] Task @context(task)")
        assert is_activity_line("Call mom @context(task)")
        assert is_activity_line("@context(habit) Morning meditation")

    def test_is_not_activity_line_without_context(self):
        """Lines without @context are not Activity Lines."""
        assert not is_activity_line("- [ ] Simple task")
        assert not is_activity_line("Just a note")
        assert not is_activity_line("")


class TestSingleLineParsing:
    """Test parsing individual Activity Lines."""

    def test_parse_simple_task(self):
        """Parse a simple task with just @context."""
        result = parse_activity_line("- [ ] Call mom @context(task)")

        assert result.is_ok
        activity = result.value
        assert activity.description == "Call mom"
        assert activity.contexts == ["task"]
        assert activity.is_task()

    def test_parse_with_priority(self):
        """Parse task with @priority."""
        result = parse_activity_line("- [ ] Urgent task @context(task) @priority(1)")

        assert result.is_ok
        activity = result.value
        assert activity.priority == 1

    def test_parse_with_when_iso_t(self):
        """Parse task with @when (ISO format with T)."""
        # ✅ Use dynamic future date to avoid validation errors
        from datetime import timedelta

        future_date = datetime.now() + timedelta(days=30)
        when_str = future_date.strftime("%Y-%m-%dT%H:%M")

        result = parse_activity_line(f"- [ ] Meeting @context(event) @when({when_str})")

        assert result.is_ok
        activity = result.value
        expected = future_date.replace(second=0, microsecond=0)
        assert activity.when == expected

    def test_parse_with_when_iso_space(self):
        """Parse task with @when (ISO format with space)."""
        # ✅ Use dynamic future date to avoid validation errors
        from datetime import timedelta

        future_date = datetime.now() + timedelta(days=30)
        when_str = future_date.strftime("%Y-%m-%d %H:%M")

        result = parse_activity_line(f"- [ ] Meeting @context(event) @when({when_str})")

        assert result.is_ok
        activity = result.value
        expected = future_date.replace(second=0, microsecond=0)
        assert activity.when == expected

    def test_parse_duration_minutes(self):
        """Parse @duration with minutes."""
        result = parse_activity_line("- [ ] Quick task @context(task) @duration(30m)")

        assert result.is_ok
        assert result.value.duration_minutes == 30

    def test_parse_duration_hours(self):
        """Parse @duration with hours."""
        result = parse_activity_line("- [ ] Long task @context(task) @duration(2h)")

        assert result.is_ok
        assert result.value.duration_minutes == 120

    def test_parse_duration_mixed(self):
        """Parse @duration with hours and minutes."""
        result = parse_activity_line("- [ ] Medium task @context(task) @duration(1h30m)")

        assert result.is_ok
        assert result.value.duration_minutes == 90

    def test_parse_energy_single(self):
        """Parse @energy with single state."""
        result = parse_activity_line("- [ ] Deep work @context(task) @energy(focus)")

        assert result.is_ok
        assert result.value.energy_states == ["focus"]

    def test_parse_energy_multiple(self):
        """Parse @energy with multiple states."""
        result = parse_activity_line("- [ ] Creative work @context(task) @energy(focus,creative)")

        assert result.is_ok
        assert result.value.energy_states == ["focus", "creative"]

    def test_parse_multiple_contexts(self):
        """Parse multiple contexts."""
        result = parse_activity_line("- [ ] Learn Python @context(task,learning)")

        assert result.is_ok
        activity = result.value
        assert activity.contexts == ["task", "learning"]
        assert activity.is_task()
        assert activity.is_learning()

    def test_parse_checked_checkbox(self):
        """Parse checked checkbox [x]."""
        result = parse_activity_line("- [x] Done task @context(task)")

        assert result.is_ok
        assert result.value.is_checked

    def test_parse_unchecked_checkbox(self):
        """Parse unchecked checkbox [ ]."""
        result = parse_activity_line("- [ ] Todo task @context(task)")

        assert result.is_ok
        assert not result.value.is_checked


class TestKnowledgeAndLinks:
    """Test @ku and @link parsing."""

    def test_parse_ku(self):
        """Parse @ku knowledge unit reference."""
        result = parse_activity_line(
            "- [ ] Study mindfulness @context(learning) @ku(ku:sel/mindfulness-intro)"
        )

        assert result.is_ok
        assert result.value.primary_ku == "ku:sel/mindfulness-intro"

    def test_parse_single_link(self):
        """Parse single @link."""
        result = parse_activity_line("- [ ] Exercise @context(habit) @link(goal:health/fitness)")

        assert result.is_ok
        links = result.value.links
        assert len(links) == 1
        assert links[0]["type"] == "goal"
        assert links[0]["id"] == "goal:health/fitness"

    def test_parse_multiple_links(self):
        """Parse multiple @link values."""
        result = parse_activity_line(
            "- [ ] Meditate @context(habit) @link(goal:wellness, principle:inner-peace)"
        )

        assert result.is_ok
        links = result.value.links
        assert len(links) == 2

    def test_get_linked_goals(self):
        """Test get_linked_goals helper method."""
        result = parse_activity_line(
            "- [ ] Task @context(task) @link(goal:one, goal:two, principle:x)"
        )

        assert result.is_ok
        goals = result.value.get_linked_goals()
        assert len(goals) == 2
        assert "goal:one" in goals
        assert "goal:two" in goals


class TestRepeatPatterns:
    """Test @repeat parsing."""

    def test_parse_repeat_daily(self):
        """Parse @repeat(daily)."""
        result = parse_activity_line("- [ ] Meditate @context(habit) @repeat(daily)")

        assert result.is_ok
        assert result.value.repeat_pattern == {"type": "daily"}

    def test_parse_repeat_weekly(self):
        """Parse @repeat(weekly:Mon,Wed,Fri)."""
        result = parse_activity_line("- [ ] Exercise @context(habit) @repeat(weekly:Mon,Wed,Fri)")

        assert result.is_ok
        pattern = result.value.repeat_pattern
        assert pattern["type"] == "weekly"
        assert pattern["days"] == ["Mon", "Wed", "Fri"]

    def test_parse_repeat_monthly(self):
        """Parse @repeat(monthly:1,15)."""
        result = parse_activity_line("- [ ] Review @context(habit) @repeat(monthly:1,15)")

        assert result.is_ok
        pattern = result.value.repeat_pattern
        assert pattern["type"] == "monthly"
        assert pattern["days"] == [1, 15]

    def test_parse_repeat_interval(self):
        """Parse @repeat(every:3d)."""
        result = parse_activity_line("- [ ] Check-in @context(habit) @repeat(every:3d)")

        assert result.is_ok
        pattern = result.value.repeat_pattern
        assert pattern["type"] == "interval"
        assert pattern["interval"] == 3
        assert pattern["unit"] == "days"


class TestFullActivityLine:
    """Test parsing complete Activity Lines with all tags."""

    def test_parse_full_task(self):
        """Parse a fully-tagged task line."""
        # ✅ Use dynamic future date to avoid validation errors
        from datetime import timedelta

        future_date = datetime.now() + timedelta(days=30)
        when_str = future_date.strftime("%Y-%m-%dT%H:%M")

        line = (
            "- [ ] Draft Teens.yoga lesson on focus "
            "@context(task,learning) "
            f"@when({when_str}) "
            "@duration(90m) "
            "@priority(1) "
            "@energy(focus,creative) "
            "@ku(ku:teens-yoga/focus-lesson) "
            "@link(goal:teens-yoga/20-members)"
        )

        result = parse_activity_line(line)

        assert result.is_ok
        activity = result.value

        assert activity.description == "Draft Teens.yoga lesson on focus"
        assert activity.contexts == ["task", "learning"]
        expected = future_date.replace(second=0, microsecond=0)
        assert activity.when == expected
        assert activity.duration_minutes == 90
        assert activity.priority == 1
        assert activity.energy_states == ["focus", "creative"]
        assert activity.primary_ku == "ku:teens-yoga/focus-lesson"
        assert len(activity.links) == 1

    def test_parse_full_habit(self):
        """Parse a fully-tagged habit line."""
        line = (
            "- [ ] Morning meditation "
            "@context(habit) "
            "@repeat(daily) "
            "@duration(20m) "
            "@energy(spiritual,rest) "
            "@ku(ku:yoga/meditation-intro)"
        )

        result = parse_activity_line(line)

        assert result.is_ok
        activity = result.value

        assert activity.description == "Morning meditation"
        assert activity.is_habit()
        assert activity.repeat_pattern == {"type": "daily"}
        assert activity.duration_minutes == 20


class TestJournalParsing:
    """Test parsing full journal documents."""

    def test_parse_journal_with_activities(self):
        """Parse a journal with multiple activity lines."""
        # ✅ Use dynamic future date to avoid validation errors
        from datetime import timedelta

        future_date = datetime.now() + timedelta(days=30)
        when_str = future_date.strftime("%Y-%m-%dT%H:%M")
        date_header = future_date.strftime("%Y-%m-%d")

        journal_text = f"""
### {date_header} — Focus Day

Today's goals:
- [ ] Morning meditation @context(habit) @duration(20m) @energy(spiritual)
- [ ] Write proposal @context(task) @priority(1) @when({when_str})
- [ ] Learn Python async @context(learning) @ku(ku:tech/python-async)

Some notes without @context that should be ignored.

More activities:
- [ ] Evening journaling @context(habit,journal) @duration(15m)
"""

        result = parse_journal_text(journal_text)

        assert result.is_ok
        parsed = result.value

        assert parsed.activity_lines_found == 4
        assert len(parsed.activities) == 4
        assert len(parsed.get_tasks()) == 1
        assert len(parsed.get_habits()) == 2  # meditation + journaling (has habit context)

    def test_parse_empty_journal(self):
        """Parse an empty journal."""
        result = parse_journal_text("")

        assert result.is_ok
        assert result.value.activity_lines_found == 0

    def test_parse_journal_no_activities(self):
        """Parse a journal with no Activity Lines."""
        journal_text = """
Just some thoughts today.

No tasks or habits here, just plain text.
"""

        result = parse_journal_text(journal_text)

        assert result.is_ok
        assert result.value.activity_lines_found == 0


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_missing_context_fails(self):
        """Lines without @context should fail."""
        result = parse_activity_line("- [ ] Task without context")

        assert result.is_error

    def test_empty_context_fails(self):
        """Empty @context() should fail."""
        result = parse_activity_line("- [ ] Task @context()")

        assert result.is_error

    def test_invalid_priority_ignored(self):
        """Invalid priority values are ignored."""
        result = parse_activity_line("- [ ] Task @context(task) @priority(99)")

        assert result.is_ok
        assert result.value.priority is None  # Invalid value ignored

    def test_invalid_when_ignored(self):
        """Invalid @when values are ignored."""
        result = parse_activity_line("- [ ] Task @context(task) @when(not-a-date)")

        assert result.is_ok
        assert result.value.when is None  # Invalid value ignored


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
