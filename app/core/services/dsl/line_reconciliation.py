"""
Line Reconciliation — the three-way merge of a recognised vault line (ADR-070 Decision 3, R4)
============================================================================================

A 🆔 line SKUEL already owns comes back on a note's re-ingest in one of two states:
the vault changed it, or SKUEL changed the task behind it and the outbound pass has
not written that back yet. The two look the same to a hash and to a bare comparison
of line against task — and the sync runs inbound BEFORE outbound, so a bare "line
state ≠ task state ⇒ apply the line" would reopen every task completed in SKUEL on
the very next sync (R4 build plan, C1). What tells them apart is the line as SKUEL
LAST SAW IT — the ``EXTRACTED_FROM.source_line`` base — so each field is judged
three ways:

    base   — the stored line, parsed
    theirs — the current line, parsed
    ours   — the task

A field the vault changed (theirs ≠ base) is applied; a field the vault left alone
keeps SKUEL's value, and the outbound pass writes it back as ever. Both sides changed
the same field ⇒ the vault wins (the user just pushed "sync"); for the checkbox, the
later ``✅`` date wins.

``reconcile_task_line`` is pure and DB-free: it reads three values and returns at
most one status transition and one field patch, as ONE ``TaskUpdateIntent`` — one
write, one verdict, so the base can advance exactly when that write lands (C1). The
caller (``ActivityExtractorService``'s Guard 2b identity branch) parses the base and
the line through the same adapter that minted the task, reads the task, applies the
intent through ``tasks_service.update_task`` (ADR-087's status-guarded door: legality,
the ``completion_date`` stamp, ``TaskCompleted`` / ``TaskReopened``, the keep-a-day
rule) and advances the edge's base and digest only on ok. No base ⇒ the caller seeds
it and applies nothing; this function is never reached.

Field rules apply to obsidian-tasks lines only (``ParseDoor.OBSIDIAN_TASKS``): on a
DSL line the obsidian-tasks metadata vocabulary is literal text (DSL_USAGE_GUIDE § The
Parse Contract — one vocabulary per line), so only its checkbox is reconciled.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from pydantic import ValidationError

from core.models.enums.entity_enums import EntityStatus
from core.models.enums.user_entry_enums import CheckboxVerdict, ParseDoor
from core.models.task.task import Task
from core.models.task.task_request import TaskUpdateRequest
from core.models.task.task_update_intent import TaskUpdateIntent
from core.services.dsl.activity_dsl_parser import ParsedActivityLine
from core.services.dsl.dsl_mappings import map_dsl_priority_to_enum

__all__ = ["LineReconciliation", "reconcile_task_line"]

# The tag the obsidian-tasks adapter stamps from the note's ``entry_kind`` — SKUEL's
# own marker, never a vault edit: a line moved from a daily to a weekly note changes
# it without the user touching a #tag.
_PERIOD_TAG_PREFIX = "period:"


@dataclass(frozen=True)
class LineReconciliation:
    """What one recognised vault line asks of its task — at most one write.

    ``intent`` is the one ``TaskUpdateIntent`` to post (``None`` when the line asks
    nothing: the vault changed nothing SKUEL does not already hold). ``checkbox`` is
    the status row the merge landed on; ``changed_fields`` names the field patches
    the intent carries (``title``, ``due_date``, ``scheduled_date``, ``priority``,
    ``tags``). ``refusal`` is set when the request model refused the line's values
    (a future ``✅`` date, a blank or over-long title) — nothing is written, the
    base is held, and the line re-warns every sync until it and the task agree.
    """

    intent: TaskUpdateIntent | None
    checkbox: CheckboxVerdict
    changed_fields: tuple[str, ...]
    refusal: str | None = None


@dataclass(frozen=True)
class _Checkbox:
    """The checkbox as one value: checked or not, and the ``✅`` date a checked box claims."""

    checked: bool
    done: date | None

    @classmethod
    def of_line(cls, line: ParsedActivityLine) -> _Checkbox:
        # The adapter reads a ✅ date only on a checked line, so an unchecked
        # box never carries one here.
        return cls(checked=line.is_checked, done=line.completion_date if line.is_checked else None)

    @classmethod
    def of_task(cls, task: Task) -> _Checkbox:
        completed = task.status == EntityStatus.COMPLETED
        return cls(checked=completed, done=task.completion_date if completed else None)


def _reconcile_checkbox(
    base: _Checkbox, theirs: _Checkbox, ours: _Checkbox
) -> tuple[CheckboxVerdict, dict[str, object]]:
    """The six status rows of the build plan's table, as one three-way merge.

    Returns the verdict and the status half of the patch (``status`` and, on a
    completion or re-date, ``completion_date``).
    """
    if theirs == base:
        # Rows 1 and 5: the vault did not touch the box. A completion or reopen
        # made in SKUEL stands, and the outbound pass writes it back.
        return CheckboxVerdict.UNCHANGED, {}

    if not theirs.checked:
        # Row 4: the vault un-checked a box the base had checked. A completed
        # task reopens; a stale trailing ✅ the user left is SKUEL's, and the
        # outbound un-check strips it. Row 6: a cancel is SKUEL's decision, not
        # a completion the vault can withdraw — the line stays open and
        # diverges visibly. An already-open task has nothing to reopen.
        if ours.checked:
            return CheckboxVerdict.REOPENED, {"status": EntityStatus.ACTIVE}
        return CheckboxVerdict.STANDS, {}

    # The vault checked the box (or moved the ✅ date of a box it had checked).
    if not ours.checked:
        # Row 2 — and row 6's other half: [x] on a cancelled task is a check,
        # applied. Completed on the line's ✅ date, today when the tick carries
        # none (the outbound pass then appends SKUEL's ``✅ today``).
        return CheckboxVerdict.COMPLETED, {
            "status": EntityStatus.COMPLETED,
            "completion_date": theirs.done or date.today(),
        }

    # Row 3: both completed. Did SKUEL change the completion since the base was
    # taken? If the task still says what the base said, only the vault moved,
    # and the vault wins outright — its ✅ date is applied as written. If both
    # moved, the later date wins and a tie changes nothing.
    if theirs.done is None or theirs.done == ours.done:
        # A dateless tick makes no date claim, and an equal date is a tie:
        # SKUEL's completion and its date stand; the outbound pass writes the
        # ✅ date onto the line where the tick has none.
        return CheckboxVerdict.STANDS, {}
    skuel_unchanged = base.checked and base.done == ours.done
    if skuel_unchanged or ours.done is None or theirs.done > ours.done:
        # A re-post of ``completed`` beside a corrected date re-dates the task
        # without firing a completion event (a re-post is not a transition).
        return CheckboxVerdict.REDATED, {
            "status": EntityStatus.COMPLETED,
            "completion_date": theirs.done,
        }
    return CheckboxVerdict.STANDS, {}


def _line_tags(line: ParsedActivityLine) -> list[str]:
    """The line's ``#tags`` — the adapter's ``period:{kind}`` stamp excluded."""
    return [tag for tag in line.extra_tags if not tag.startswith(_PERIOD_TAG_PREFIX)]


def _reconcile_fields(
    base: ParsedActivityLine, theirs: ParsedActivityLine, ours: Task
) -> dict[str, object]:
    """Title, due (📅), scheduled (⏳), priority (emoji → int, absence = 3), #tags —
    each applied only when the vault changed it (theirs ≠ base)."""
    patch: dict[str, object] = {}

    if theirs.description != base.description:
        patch["title"] = theirs.description

    if theirs.when != base.when:
        patch["due_date"] = theirs.when.date() if theirs.when else None

    if theirs.scheduled_date != base.scheduled_date:
        patch["scheduled_date"] = theirs.scheduled_date

    if theirs.priority != base.priority:
        patch["priority"] = map_dsl_priority_to_enum(theirs.priority)

    base_tags, theirs_tags = _line_tags(base), _line_tags(theirs)
    if set(theirs_tags) != set(base_tags):
        # A set-valued field merges three ways too: what the vault added joins
        # the task's tags, what it removed leaves them, and a tag SKUEL holds
        # that the line never carried (the period stamp, a tag set in the UI)
        # is kept. Order: SKUEL's, then the additions in the line's order.
        added = [tag for tag in theirs_tags if tag not in base_tags]
        removed = {tag for tag in base_tags if tag not in theirs_tags}
        kept = [tag for tag in ours.tags if tag not in removed]
        patch["tags"] = list(dict.fromkeys([*kept, *added]))

    return patch


def reconcile_task_line(
    base: ParsedActivityLine,
    theirs: ParsedActivityLine,
    ours: Task,
    *,
    door: ParseDoor = ParseDoor.OBSIDIAN_TASKS,
) -> LineReconciliation:
    """Three-way merge of one recognised 🆔 line against the task it names.

    ``base`` and ``theirs`` are the stored and the current line, both parsed through
    ``obsidian_task_line_to_parsed`` (the one parser for both — a checkbox and a
    ``✅`` date read the same way on either door); ``ours`` is the task as it stands.
    ``door`` is the door the note's parser routed the line through: the field rules
    (title, due, scheduled, priority, tags) apply only to an obsidian-tasks line —
    on a DSL line that vocabulary is literal text, so only its checkbox is judged.

    Returns the one intent to post (or none), the checkbox verdict, the fields
    changed, and a refusal when the request model rejected the line's values.
    """
    verdict, patch = _reconcile_checkbox(
        _Checkbox.of_line(base), _Checkbox.of_line(theirs), _Checkbox.of_task(ours)
    )
    changed_fields: tuple[str, ...] = ()
    if door.interprets_task_metadata:
        field_patch = _reconcile_fields(base, theirs, ours)
        changed_fields = tuple(field_patch)
        patch.update(field_patch)

    if not patch:
        return LineReconciliation(intent=None, checkbox=verdict, changed_fields=())

    try:
        # Only the changed fields are named, so ``to_intent`` carries a true
        # partial patch: everything else stays UNSET — untouched by the write.
        request = TaskUpdateRequest.model_validate(patch)
    except ValidationError as exc:
        reasons = "; ".join(
            str(error.get("msg", "invalid value")).removeprefix("Value error, ")
            for error in exc.errors()
        )
        return LineReconciliation(
            intent=None, checkbox=verdict, changed_fields=changed_fields, refusal=reasons
        )
    return LineReconciliation(
        intent=request.to_intent(), checkbox=verdict, changed_fields=changed_fields
    )
