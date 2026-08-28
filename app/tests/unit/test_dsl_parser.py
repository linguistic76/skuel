# mypy: disable-error-code="index"
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

    def test_parse_with_when_date_only(self):
        """Parse @when with a date-only value (obsidian-tasks 📅 granularity) — midnight."""
        from datetime import timedelta

        future_date = datetime.now() + timedelta(days=30)
        when_str = future_date.strftime("%Y-%m-%d")

        result = parse_activity_line(f"- [ ] Plan week @context(task) @when({when_str})")

        assert result.is_ok
        activity = result.value
        expected = future_date.replace(hour=0, minute=0, second=0, microsecond=0)
        assert activity.when == expected
        assert activity.when_has_clock_time is False, (
            "a bare date parses to midnight; nobody stated a time of day"
        )

    def test_when_clock_time_flag_tracks_what_the_author_actually_wrote(self):
        """Midnight-from-a-date and midnight-from-00:00 are the same datetime.

        Only the flag separates them, and habit slot inference turns on it —
        without it a bare date reads as LATE_NIGHT and schedules at 02:00.
        """
        from datetime import timedelta

        day = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        cases = {
            day: False,
            f"{day}T00:00": True,
            f"{day} 00:00": True,
            f"{day}T09:30": True,
            f"{day} 09:30": True,
        }
        for when_str, expected in cases.items():
            result = parse_activity_line(f"- [ ] Sit @context(habit) @when({when_str})")
            assert result.is_ok, when_str
            assert result.value.when_has_clock_time is expected, when_str

    def test_unparseable_when_carries_no_clock_time(self):
        result = parse_activity_line("- [ ] Finish report @context(task) @when(Friday)")

        assert result.is_ok
        assert result.value.when is None
        assert result.value.when_has_clock_time is False

    def test_parse_with_when_unparseable_drops_schedule(self):
        """An unparseable @when value keeps the line but drops the schedule."""
        result = parse_activity_line("- [ ] Finish report @context(task) @when(Friday)")

        assert result.is_ok
        assert result.value.when is None

    def test_parse_with_when_impossible_date_drops_schedule(self):
        """An impossible calendar date keeps the line but drops the schedule (all formats)."""
        for when in ("2026-02-31", "2026-02-31T09:30", "2026-13-01 10:00"):
            result = parse_activity_line(f"- [ ] Plan @context(task) @when({when})")

            assert result.is_ok, f"line should survive @when({when})"
            assert result.value.when is None

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
            "- [ ] Study mindfulness @context(task,learning) @ku(ku.sel/mindfulness-intro)"
        )

        assert result.is_ok
        assert result.value.primary_ku == "ku.sel/mindfulness-intro"

    def test_parse_ku_colon_spelling_rejected(self):
        """The retired colon spelling is OMITTED (None), never rewritten —
        the old lenient fallback minted garbage (``ku.ku:…``) that parsed
        successfully but silently missed the intended Ku (Codex P1 #1054)."""
        result = parse_activity_line(
            "- [ ] Study mindfulness @context(task,learning) @ku(ku:sel/mindfulness-intro)"
        )

        assert result.is_ok
        assert result.value.primary_ku is None

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
            "@ku(ku.teens-yoga/focus-lesson) "
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
        assert activity.primary_ku == "ku.teens-yoga/focus-lesson"
        assert len(activity.links) == 1

    def test_parse_full_habit(self):
        """Parse a fully-tagged habit line."""
        line = (
            "- [ ] Morning meditation "
            "@context(habit) "
            "@repeat(daily) "
            "@duration(20m) "
            "@energy(spiritual,rest) "
            "@ku(ku.yoga/meditation-intro)"
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
- [ ] Learn Python async @context(task,learning) @ku(ku.tech/python-async)

Some notes without @context that should be ignored.

More activities:
- [ ] Evening journaling @context(habit) @duration(15m)
"""

        result = parse_journal_text(journal_text)

        assert result.is_ok
        parsed = result.value

        assert parsed.activity_lines_found == 4
        assert len(parsed.activities) == 4
        assert len(parsed.get_tasks()) == 2  # proposal + Learn Python (task,learning)
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


class TestPeriodicNoteParseContract:
    """The periodic-note parse contract (E3, calendar-periodic-notes-arc).

    Recognized entity-creating shapes = checkbox lines + explicit ``@context()``
    DSL markers, nothing else. A section heading is prose, not a parse
    instruction — bare lines under ``## Goals`` create nothing; Choices and
    Principles become entities ONLY via explicit markers.
    """

    def test_specimen_periodic_note_parses_only_marked_shapes(self):
        from core.models.enums.entity_enums import EntityType
        from core.services.dsl.activity_dsl_parser import ActivityDSLParser

        # Specimen SHAPE of a daily periodic note (obsidian-tasks checkbox
        # with due date + 🆔 join key; compass lines with explicit markers;
        # unmarked prose including bare lines under a "## Goals" heading).
        specimen = """\
## Tasks
- [ ] Water the garden 📅 2099-01-15 🆔 sk_ab12cd

## Goals
Get fit someday
Read more books

## Compass
I choose to prioritize deep work this week @context(choice)
Act with patience in every conversation @context(principle)

## Notes
Reflected on the morning walk. It felt unhurried.
"""
        result = ActivityDSLParser().parse_journal(specimen, entry_kind="daily")

        assert result.is_ok
        parsed = result.value

        # Exactly the three marked lines — nothing inferred from prose or
        # headings (no Goal from the "## Goals" section, nothing from Notes).
        assert parsed.activity_lines_found == 3
        tasks = parsed.get_tasks()
        assert len(tasks) == 1
        assert tasks[0].description == "Water the garden"
        assert tasks[0].vault_id == "sk_ab12cd"
        assert tasks[0].contexts == [EntityType.TASK]

        choices = parsed.get_choices()
        assert len(choices) == 1
        assert "prioritize deep work" in choices[0].description

        principles = parsed.get_principles()
        assert len(principles) == 1
        assert "patience" in principles[0].description

        assert parsed.get_goals() == []
        assert parsed.get_habits() == []
        assert parsed.get_events() == []

    def test_tagged_checkbox_explicit_marker_wins_over_adapter(self):
        """Precedence pin (Codex #924): a checkbox line that ALSO carries
        ``@context(...)`` is a DSL line — the explicit marker wins (Goal, not
        Task) and the obsidian-tasks vocabulary is NOT interpreted: emoji/🆔
        stay literal description text; ``vault_id``/``when`` are not captured.
        Documented in DSL_USAGE_GUIDE § Periodic Notes — The Parse Contract
        ("one vocabulary per line"); changing this routing must update that
        contract in the same PR.
        """
        from core.models.enums.entity_enums import EntityType
        from core.services.dsl.activity_dsl_parser import ActivityDSLParser

        line = "- [ ] Ship the plan @context(goal) 📅 2099-01-15 🆔 sk_zz99yy"
        result = ActivityDSLParser().parse_journal(line, entry_kind="daily")

        assert result.is_ok
        parsed = result.value
        assert parsed.activity_lines_found == 1
        assert parsed.get_tasks() == []  # the adapter did NOT claim the line

        goals = parsed.get_goals()
        assert len(goals) == 1
        assert goals[0].contexts == [EntityType.GOAL]
        # Obsidian-tasks metadata is not interpreted on a DSL line: the 📅 date
        # does not become a schedule, the 🆔 token is not captured as the
        # ADR-070 join key — both remain literal description text.
        assert goals[0].when is None
        assert goals[0].vault_id is None
        assert "sk_zz99yy" in goals[0].description


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

    def test_empty_description_fails(self):
        """Tags-only lines fail — extraction would mint a titleless entity."""
        for line in ("- [ ] @context(task)", "@context(task) @priority(1)"):
            result = parse_activity_line(line)

            assert result.is_error, f"should reject: {line}"
            assert "description" in result.expect_error().message

    def test_tag_first_line_with_description_parses(self):
        """Bridge-style tag-first lines keep their description (it follows the tags)."""
        result = parse_activity_line("@context(task) Call mom @priority(1)")

        assert result.is_ok
        assert result.value.description == "Call mom"

    def test_system_side_contexts_rejected(self):
        """Enum members outside the DSL vocabulary fail like typos (menu ruling)."""
        for ctx in ("interaction", "form_template", "exercise", "activity_report", "group"):
            result = parse_activity_line(f"- [ ] Something @context({ctx})")

            assert result.is_error, f"@context({ctx}) should be rejected"
            message = result.expect_error().message
            assert "Invalid context types" in message
            # Error guidance lists the sanctioned vocabulary, not the full enum dump.
            assert "form_template" not in message.split("Valid types:")[1]

    def test_dropped_tag_values_recorded_as_warnings(self):
        """Unparseable tag values drop softly AND leave a per-line warning."""
        result = parse_activity_line(
            "- [ ] Plan sprint @context(task) @when(Friday) @priority(99) "
            "@duration(10) @repeat(yearly)"
        )

        assert result.is_ok
        activity = result.value
        assert activity.when is None
        assert activity.priority is None
        assert activity.duration_minutes is None
        assert activity.repeat_pattern is None
        joined = " ".join(activity.tag_warnings)
        for fragment in ("@when(Friday)", "@priority(99)", "@duration(10)", "@repeat(yearly)"):
            assert fragment in joined, f"missing warning for {fragment}"
        assert len(activity.tag_warnings) == 4

    def test_malformed_repeat_values_dropped_with_warning(self):
        """Prefixed-but-malformed repeats drop with a warning, not a fake recurrence."""
        for rep in (
            "weekly:",
            "weekly:Funday",
            "weekly:Mon,Funday",
            "monthly:x",
            "monthly:0",
            "monthly:32",
            "every:d",
            "every:2dfoo",
            "every:3x",
        ):
            result = parse_activity_line(f"- [ ] Chore @context(habit) @repeat({rep})")

            assert result.is_ok, rep
            assert result.value.repeat_pattern is None, f"@repeat({rep}) should drop"
            assert any("@repeat" in w for w in result.value.tag_warnings), rep

    def test_interval_repeat_long_unit_forms_accepted(self):
        """Natural spellings (every:3days) parse to the same interval as every:3d."""
        for rep, unit in (("every:3d", "days"), ("every:3days", "days"), ("every:2weeks", "weeks")):
            result = parse_activity_line(f"- [ ] Chore @context(habit) @repeat({rep})")

            assert result.is_ok, rep
            pattern = result.value.repeat_pattern
            assert pattern == {
                "type": "interval",
                "interval": int(rep.split(":")[1][0]),
                "unit": unit,
            }, rep
            assert result.value.tag_warnings == []

    def test_valid_tag_values_produce_no_warnings(self):
        """Fully valid lines carry an empty tag_warnings list."""
        result = parse_activity_line(
            "- [ ] Plan sprint @context(task) @when(2026-08-01) @priority(2) "
            "@duration(45m) @repeat(daily)"
        )

        assert result.is_ok
        assert result.value.tag_warnings == []

    def test_learning_only_context_rejected(self):
        """learning is a modifier — alone it would create nothing, so it fails."""
        result = parse_activity_line("- [ ] Read chapter @context(learning)")

        assert result.is_error
        assert "modifier" in result.expect_error().message

    def test_staged_contexts_still_parse(self):
        """Staged domain types (create surface unwired) remain valid vocabulary."""
        for ctx in ("ps", "lp", "path_step", "calendar", "lifepath", "finance"):
            result = parse_activity_line(f"- [ ] Something @context({ctx})")

            assert result.is_ok, f"@context({ctx}) should parse"

    def test_knowledge_alias_parses_to_ku(self):
        """knowledge is the friendly spelling for ku (alias restored 2026-08-15)."""
        from core.models.enums.entity_enums import EntityType

        result = parse_activity_line("- [ ] Study spaced repetition @context(knowledge)")

        assert result.is_ok
        assert result.value.contexts == [EntityType.KU]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestInlineCodeIsLiteral:
    """A DSL marker inside inline code is documentation, never intent.

    Live incident 2026-08-27: a daily note's legend line
    ``> Events: `- [ ] Description @context(event) @when(YYYY-MM-DDTHH:MM) @duration(1h)` ``
    minted a junk Event titled with the legend itself. Backticks mean "literal text"
    everywhere in Markdown; the parser must read them the same way.
    """

    LEGEND = "> Events: `- [ ] Description @context(event) @when(YYYY-MM-DDTHH:MM) @duration(1h)`  "

    def test_legend_line_is_not_an_activity_line(self):
        assert not is_activity_line(self.LEGEND)
        result = parse_activity_line(self.LEGEND)
        assert result.is_error
        assert "missing @context" in str(result.error)

    def test_legend_line_creates_nothing_in_a_journal(self):
        text = "## Events\n\n" + self.LEGEND + "\n\n- [ ] Real task @context(task)\n"
        parsed = parse_journal_text(text).value
        assert [a.description for a in parsed.activities] == ["Real task"]

    def test_real_marker_survives_a_code_span_on_the_same_line(self):
        """Only the marker outside the code span counts; the code text stays in the description."""
        line = "- [ ] Fix the `@context(habit)` example in the guide @context(task) @priority(2)"
        result = parse_activity_line(line)
        assert result.is_ok
        activity = result.value
        assert activity.context_values == ["task"]
        assert activity.priority == 2
        assert activity.description == "Fix the `@context(habit)` example in the guide"

    def test_unclosed_backtick_is_not_a_code_span(self):
        """A lone backtick masks nothing — the marker after it is real."""
        assert is_activity_line("- [ ] Run `pytest @context(task)")

    def test_multi_backtick_code_spans_are_literal_too(self):
        """CommonMark: a run of N backticks opens a span closed by exactly N (Codex #1167)."""
        assert not is_activity_line("Explain ``@context(event)`` literally")
        assert not is_activity_line("Explain ``` @context(event) ``` literally")
        # A single backtick INSIDE a double-backtick span does not close it.
        assert not is_activity_line("See ``the ` and @context(task) form`` here")
        # …and a real marker after such a span still counts, code text kept verbatim.
        result = parse_activity_line("- [ ] Doc ``the ` @context(habit) form`` @context(task)")
        assert result.is_ok
        assert result.value.context_values == ["task"]
        assert result.value.description == "Doc ``the ` @context(habit) form``"
