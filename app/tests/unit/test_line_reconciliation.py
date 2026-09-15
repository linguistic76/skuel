"""``reconcile_task_line`` — the three-way merge of a recognised vault line (R4 PR 2).

Pure and DB-free: base (the line as SKUEL last saw it), theirs (the line now)
and ours (the task) go in; at most one ``TaskUpdateIntent`` comes out. Every
status row of the build plan's table, every field rule, the period-tag
exclusion, the DSL-door restriction and the request-model refusal are pinned
here; the rig cases in ``tests/integration/test_vault_inbound_propagation.py``
drive the same function through the real sync.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from core.models.enums.activity_enums import Priority
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.user_entry_enums import CheckboxVerdict, ParseDoor
from core.models.sentinels import UNSET
from core.models.task.task import Task
from core.services.dsl.line_reconciliation import LineReconciliation, reconcile_task_line
from core.services.dsl.obsidian_tasks_adapter import obsidian_task_line_to_parsed

VAULT_ID = "sk_ab12cd"
TODAY = date.today()
D1 = date(2026, 9, 10)
D2 = date(2026, 9, 12)


def _asks_nothing(out: LineReconciliation) -> bool:
    """No intent and no refusal — the caller advances the base as is."""
    return out.intent is None and out.refusal is None


def _line(text: str, *, entry_kind: str | None = None):
    parsed = obsidian_task_line_to_parsed(text, entry_kind=entry_kind)
    assert parsed is not None, text
    return parsed


def _task(
    *,
    status: EntityStatus = EntityStatus.DRAFT,
    completion_date: date | None = None,
    title: str = "Vacuum",
    tags: tuple[str, ...] = ("period:daily",),
    due_date: date | None = None,
    priority: str | None = "medium",
) -> Task:
    return Task(
        uid="task_1",
        entity_type=EntityType.TASK,
        title=title,
        user_uid="user_1",
        status=status,
        completion_date=completion_date,
        tags=tags,
        due_date=due_date,
        priority=priority,
    )


OPEN = f"- [ ] Vacuum 🆔 {VAULT_ID}"
DONE_D1 = f"- [x] Vacuum 🆔 {VAULT_ID} ✅ {D1.isoformat()}"
DONE_D2 = f"- [x] Vacuum 🆔 {VAULT_ID} ✅ {D2.isoformat()}"
DONE_DATELESS = f"- [x] Vacuum 🆔 {VAULT_ID}"


class TestTheStatusRows:
    """The six rows of the plan's table, in order."""

    def test_row_1_vault_unchanged_keeps_a_completion_made_in_skuel(self) -> None:
        """base [ ], theirs [ ], ours completed — the C1 race: the sync right
        after a completion in SKUEL still reads ``- [ ]``. Nothing is written;
        the outbound pass writes ``[x] ✅``."""
        out = reconcile_task_line(
            _line(OPEN), _line(OPEN), _task(status=EntityStatus.COMPLETED, completion_date=D1)
        )
        assert _asks_nothing(out)
        assert out.checkbox is CheckboxVerdict.UNCHANGED

    def test_row_2_vault_checked_completes_on_the_line_date(self) -> None:
        out = reconcile_task_line(_line(OPEN), _line(DONE_D1), _task())
        assert out.checkbox is CheckboxVerdict.COMPLETED
        assert out.intent is not None
        assert out.intent.status == EntityStatus.COMPLETED.value
        assert out.intent.completion_date == D1
        assert out.intent.title is UNSET, "no field changed — nothing else in the patch"

    def test_row_2_a_dateless_tick_completes_with_today(self) -> None:
        """Checked directly in Obsidian without the plugin: no ✅ date. Today
        is the completion; the outbound pass then appends ``✅ today``."""
        out = reconcile_task_line(_line(OPEN), _line(DONE_DATELESS), _task())
        assert out.checkbox is CheckboxVerdict.COMPLETED
        assert out.intent is not None and out.intent.completion_date == TODAY

    def test_row_3_both_completed_the_later_date_wins(self) -> None:
        """base [ ], theirs [x] ✅ D2, ours completed on D1 — the vault's later
        date re-dates the task (a re-post of completed beside the date)."""
        out = reconcile_task_line(
            _line(OPEN), _line(DONE_D2), _task(status=EntityStatus.COMPLETED, completion_date=D1)
        )
        assert out.checkbox is CheckboxVerdict.REDATED
        assert out.intent is not None
        assert out.intent.status == EntityStatus.COMPLETED.value
        assert out.intent.completion_date == D2

    def test_row_3_both_completed_skuel_later_stands(self) -> None:
        out = reconcile_task_line(
            _line(OPEN), _line(DONE_D1), _task(status=EntityStatus.COMPLETED, completion_date=D2)
        )
        assert _asks_nothing(out)
        assert out.checkbox is CheckboxVerdict.STANDS

    def test_row_3_both_completed_tie_is_nothing(self) -> None:
        """The live fixture's row: the base was seeded before the outbound
        wrote ``[x] ✅`` into the note, so the first reconciliation meets its
        own write-back. A tie writes nothing — and the caller still advances
        the base, or the line would re-diff forever."""
        out = reconcile_task_line(
            _line(OPEN), _line(DONE_D1), _task(status=EntityStatus.COMPLETED, completion_date=D1)
        )
        assert _asks_nothing(out)
        assert out.checkbox is CheckboxVerdict.STANDS

    def test_row_3_a_dateless_tick_on_a_completed_task_makes_no_date_claim(self) -> None:
        out = reconcile_task_line(
            _line(OPEN),
            _line(DONE_DATELESS),
            _task(status=EntityStatus.COMPLETED, completion_date=D1),
        )
        assert _asks_nothing(out)
        assert out.checkbox is CheckboxVerdict.STANDS

    def test_row_3_a_completed_task_with_no_stamp_takes_the_vault_date(self) -> None:
        """A completion that predates the stamp holds no date; the vault's is
        applied rather than compared against nothing."""
        out = reconcile_task_line(
            _line(OPEN), _line(DONE_D1), _task(status=EntityStatus.COMPLETED, completion_date=None)
        )
        assert out.checkbox is CheckboxVerdict.REDATED
        assert out.intent is not None and out.intent.completion_date == D1

    def test_the_vault_alone_moving_a_done_date_wins_outright_even_backwards(self) -> None:
        """base [x] ✅ D2, theirs [x] ✅ D1, ours completed on D2 — SKUEL still
        says what the base said, so only the vault moved: Decision 3 applies
        the vault's date as written, earlier or not."""
        out = reconcile_task_line(
            _line(DONE_D2), _line(DONE_D1), _task(status=EntityStatus.COMPLETED, completion_date=D2)
        )
        assert out.checkbox is CheckboxVerdict.REDATED
        assert out.intent is not None and out.intent.completion_date == D1

    def test_row_4_vault_unchecked_reopens(self) -> None:
        """A stale trailing ✅ the user left is SKUEL's; the outbound un-check
        strips it. The reopen is ``status = ACTIVE``; the stamp clear is the
        guarded write's (ADR-087), not this function's."""
        stale = f"- [ ] Vacuum 🆔 {VAULT_ID} ✅ {D1.isoformat()}"
        out = reconcile_task_line(
            _line(DONE_D1), _line(stale), _task(status=EntityStatus.COMPLETED, completion_date=D1)
        )
        assert out.checkbox is CheckboxVerdict.REOPENED
        assert out.intent is not None
        assert out.intent.status == EntityStatus.ACTIVE.value
        assert out.intent.completion_date is UNSET

    def test_row_5_vault_unchanged_keeps_a_reopen_made_in_skuel(self) -> None:
        """base [x] ✅ D, theirs [x] ✅ D, ours reopened — the sync right after a
        reopen in SKUEL still reads the done line. Nothing is written; the
        outbound pass un-checks."""
        out = reconcile_task_line(_line(DONE_D1), _line(DONE_D1), _task(status=EntityStatus.ACTIVE))
        assert _asks_nothing(out)
        assert out.checkbox is CheckboxVerdict.UNCHANGED

    def test_row_6_an_unchecked_line_on_a_cancelled_task_is_not_a_reopen(self) -> None:
        out = reconcile_task_line(_line(DONE_D1), _line(OPEN), _task(status=EntityStatus.CANCELLED))
        assert _asks_nothing(out)
        assert out.checkbox is CheckboxVerdict.STANDS

    def test_row_6_a_checked_line_on_a_cancelled_task_is_a_check_applied(self) -> None:
        out = reconcile_task_line(_line(OPEN), _line(DONE_D1), _task(status=EntityStatus.CANCELLED))
        assert out.checkbox is CheckboxVerdict.COMPLETED
        assert out.intent is not None
        assert out.intent.status == EntityStatus.COMPLETED.value
        assert out.intent.completion_date == D1

    def test_an_unchecked_line_on_an_open_task_asks_nothing(self) -> None:
        out = reconcile_task_line(_line(DONE_D1), _line(OPEN), _task(status=EntityStatus.DRAFT))
        assert _asks_nothing(out)
        assert out.checkbox is CheckboxVerdict.STANDS


class TestTheFieldRules:
    """Each field three-way: applied only when theirs ≠ base."""

    def test_a_retitle_follows(self) -> None:
        out = reconcile_task_line(
            _line(OPEN), _line(f"- [ ] Vacuum the hallway 🆔 {VAULT_ID}"), _task()
        )
        assert out.changed_fields == ("title",)
        assert out.intent is not None and out.intent.title == "Vacuum the hallway"
        assert out.intent.status is UNSET
        assert out.checkbox is CheckboxVerdict.UNCHANGED

    def test_a_skuel_side_retitle_survives_an_untouched_line(self) -> None:
        """theirs == base on the title, ours differs — SKUEL's value stands."""
        out = reconcile_task_line(
            _line(OPEN), _line(OPEN), _task(title="Vacuum (renamed in SKUEL)")
        )
        assert _asks_nothing(out)

    def test_a_due_date_set_moved_and_cleared(self) -> None:
        dated = f"- [ ] Vacuum 📅 2026-09-20 🆔 {VAULT_ID}"
        moved = f"- [ ] Vacuum 📅 2026-09-21 🆔 {VAULT_ID}"

        out = reconcile_task_line(_line(OPEN), _line(dated), _task())
        assert out.changed_fields == ("due_date",)
        assert out.intent is not None and out.intent.due_date == date(2026, 9, 20)

        out = reconcile_task_line(_line(dated), _line(moved), _task(due_date=date(2026, 9, 20)))
        assert out.intent is not None and out.intent.due_date == date(2026, 9, 21)

        # A clear is an explicit ``None`` in the patch — the keep-a-day rule is
        # the domain door's to refuse, not this function's to pre-empt.
        out = reconcile_task_line(_line(dated), _line(OPEN), _task(due_date=date(2026, 9, 20)))
        assert out.changed_fields == ("due_date",)
        assert out.intent is not None and out.intent.due_date is None

    def test_a_scheduled_date_follows(self) -> None:
        scheduled = f"- [ ] Vacuum ⏳ 2026-09-18 🆔 {VAULT_ID}"
        out = reconcile_task_line(_line(OPEN), _line(scheduled), _task())
        assert out.changed_fields == ("scheduled_date",)
        assert out.intent is not None and out.intent.scheduled_date == date(2026, 9, 18)

    def test_a_skuel_side_due_date_survives_an_untouched_line(self) -> None:
        out = reconcile_task_line(_line(OPEN), _line(OPEN), _task(due_date=date(2026, 9, 25)))
        assert _asks_nothing(out)

    @pytest.mark.parametrize(
        ("emoji", "expected"),
        [("⏫", Priority.HIGH), ("🔺", Priority.HIGH), ("🔽", Priority.LOW), ("⏬", Priority.LOW)],
    )
    def test_a_priority_emoji_follows(self, emoji: str, expected: Priority) -> None:
        out = reconcile_task_line(
            _line(OPEN), _line(f"- [ ] Vacuum {emoji} 🆔 {VAULT_ID}"), _task()
        )
        assert out.changed_fields == ("priority",)
        assert out.intent is not None and out.intent.priority == expected.value

    def test_removing_the_priority_emoji_is_medium(self) -> None:
        """Absence = 3 = medium. Removing ⏫ is a change; 🔼 (Obsidian's own
        name for medium) is the same level as none, so swapping one for the
        other is not."""
        high = f"- [ ] Vacuum ⏫ 🆔 {VAULT_ID}"
        out = reconcile_task_line(_line(high), _line(OPEN), _task(priority="high"))
        assert out.intent is not None and out.intent.priority == Priority.MEDIUM.value

        medium_marked = f"- [ ] Vacuum 🔼 🆔 {VAULT_ID}"
        assert _asks_nothing(reconcile_task_line(_line(medium_marked), _line(OPEN), _task()))

    def test_tags_merge_three_ways_and_keep_skuels_own(self) -> None:
        """The vault added #home and removed #chores; the task also holds a tag
        the line never carried (the period stamp, a tag set in the UI) —
        kept."""
        before = f"- [ ] Vacuum #chores #weekly 🆔 {VAULT_ID}"
        after = f"- [ ] Vacuum #weekly #home 🆔 {VAULT_ID}"
        ours = _task(tags=("period:daily", "chores", "weekly", "from-the-ui"))
        out = reconcile_task_line(_line(before), _line(after), ours)
        assert out.changed_fields == ("tags",)
        assert out.intent is not None
        assert out.intent.tags == ["period:daily", "weekly", "from-the-ui", "home"]

    def test_the_period_stamp_is_excluded_from_the_tag_diff(self) -> None:
        """A line moved from a daily to a weekly note changes the adapter's
        ``period:{kind}`` stamp without the user touching a #tag — not an
        edit."""
        out = reconcile_task_line(
            _line(OPEN, entry_kind="daily"), _line(OPEN, entry_kind="weekly"), _task()
        )
        assert _asks_nothing(out)

    def test_reordering_tags_is_not_an_edit(self) -> None:
        a = f"- [ ] Vacuum #home #chores 🆔 {VAULT_ID}"
        b = f"- [ ] Vacuum #chores #home 🆔 {VAULT_ID}"
        assert _asks_nothing(
            reconcile_task_line(_line(a), _line(b), _task(tags=("home", "chores")))
        )

    def test_a_check_and_a_retitle_in_one_edit_ride_one_intent(self) -> None:
        both = f"- [x] Vacuum upstairs 🆔 {VAULT_ID} ✅ {D1.isoformat()}"
        out = reconcile_task_line(_line(OPEN), _line(both), _task())
        assert out.checkbox is CheckboxVerdict.COMPLETED
        assert out.changed_fields == ("title",)
        assert out.intent is not None
        assert out.intent.status == EntityStatus.COMPLETED.value
        assert out.intent.completion_date == D1
        assert out.intent.title == "Vacuum upstairs"

    def test_the_injected_id_alone_is_not_an_edit(self) -> None:
        """The seed is the pre-injection line; the first re-ingest carries the
        🆔. Same description, same everything — nothing to write (the caller
        advances the base to the injected line)."""
        assert _asks_nothing(reconcile_task_line(_line("- [ ] Vacuum"), _line(OPEN), _task()))

    def test_whitespace_only_edits_are_not_edits(self) -> None:
        assert _asks_nothing(
            reconcile_task_line(_line(OPEN), _line(f"-  [ ]   Vacuum   🆔 {VAULT_ID}"), _task())
        )


class TestTheDslDoor:
    """A ``@context(task)`` checkbox line: the checkbox is reconciled, the
    obsidian-tasks field vocabulary stays literal (one vocabulary per line)."""

    def test_only_the_checkbox_is_judged_on_a_dsl_line(self) -> None:
        base = f"- [ ] Call mom @context(task) 🆔 {VAULT_ID}"
        theirs = f"- [x] Call mom @context(task) 📅 2026-09-20 🆔 {VAULT_ID} ✅ {D1.isoformat()}"
        out = reconcile_task_line(
            _line(base), _line(theirs), _task(title="Call mom"), door=ParseDoor.DSL
        )
        assert out.checkbox is CheckboxVerdict.COMPLETED
        assert out.changed_fields == ()
        assert out.intent is not None
        assert out.intent.status == EntityStatus.COMPLETED.value
        assert out.intent.completion_date == D1
        # Neither the 📅 (literal on a DSL line) nor the description (which
        # would carry the @context tag as text) reaches the task.
        assert out.intent.due_date is UNSET
        assert out.intent.title is UNSET

    def test_a_dsl_line_edit_without_a_checkbox_change_asks_nothing(self) -> None:
        base = f"- [ ] Call mom @context(task) 🆔 {VAULT_ID}"
        theirs = f"- [ ] Call mum @context(task) @priority(1) 🆔 {VAULT_ID}"
        out = reconcile_task_line(
            _line(base), _line(theirs), _task(title="Call mom"), door=ParseDoor.DSL
        )
        assert _asks_nothing(out)


class TestTheRefusal:
    def test_a_future_done_date_is_refused_not_written(self) -> None:
        future = f"- [x] Vacuum 🆔 {VAULT_ID} ✅ 2099-01-01"
        out = reconcile_task_line(_line(OPEN), _line(future), _task())
        assert out.intent is None
        assert not _asks_nothing(out)
        assert out.refusal is not None and "future" in out.refusal
        assert out.checkbox is CheckboxVerdict.COMPLETED, (
            "the verdict is reported even when refused"
        )

    def test_a_title_the_model_rejects_is_refused(self) -> None:
        too_long = f"- [ ] {'x' * 201} 🆔 {VAULT_ID}"
        out = reconcile_task_line(_line(OPEN), _line(too_long), _task())
        assert out.intent is None and out.refusal is not None
        assert out.changed_fields == ("title",)

    def test_a_when_datetime_never_leaks_a_time_component(self) -> None:
        """The adapter's ``when`` is a midnight datetime; the intent carries a
        date (the intent down-casts too — belt and braces)."""
        dated = f"- [ ] Vacuum 📅 2026-09-20 🆔 {VAULT_ID}"
        out = reconcile_task_line(_line(OPEN), _line(dated), _task())
        assert out.intent is not None
        assert out.intent.due_date == date(2026, 9, 20)
        assert not isinstance(out.intent.due_date, datetime)
