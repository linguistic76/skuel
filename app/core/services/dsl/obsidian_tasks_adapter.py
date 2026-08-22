"""
Obsidian-Tasks Extractor Adapter
================================

Bridges the **obsidian-tasks-plugin** checkbox syntax into SKUEL's DSL
intermediate representation (`ParsedActivityLine`), so that ordinary periodic
notes authored in Obsidian flow into the existing `EXTRACT_ACTIVITIES` pipeline
(ADR-069) without a new editor or a parallel parser.

A periodic note = one `UserEntry` (the journal); each `- [ ]` checkbox line in
its body = a `Task` extracted from that entry. This adapter turns one such line
into a `ParsedActivityLine` with `contexts=[EntityType.TASK]` — the same shape
the `@context(task)` DSL produces — which then rides the unchanged
converter → facade create path.

**Obsidian-Tasks emoji handled** (https://publish.obsidian.md/tasks/):
- ``📅 YYYY-MM-DD`` → due date (``when`` → ``due_date``)
- ``⏳ YYYY-MM-DD`` → scheduled date (``scheduled_date``)
- ``✅ YYYY-MM-DD`` → completion date (``completion_date``, checked lines only —
  the converter falls back to today when a checked line carries no done date)
- Priority: ``🔺``/``⏫`` → 1 (highest/high), ``🔼`` → 2, none → 3,
  ``🔽`` → 4, ``⏬`` → 5
- ``#tag`` → ``extra_tags`` (plus ``period:{entry_kind}`` when supplied)

Other obsidian-tasks markers (``🛫`` start, the created-date marker, ``🔁``
recurrence) are stripped from the description but not yet mapped to fields —
recurrence/round-trip are deferred follow-ons.

The stored ``raw_line`` is checkbox-normalized to ``- [ ]`` (the ``[x]``/``[X]``
state is captured separately in ``is_checked``) so the per-line dedup hash
(`normalized_line_hash`) is stable across check/uncheck — preventing duplicate
creation when a user ticks a box and re-syncs.
"""

import re
from datetime import date, datetime

from core.models.enums.entity_enums import EntityType
from core.ports.vault_bridge_protocol import VAULT_ID_RE
from core.services.dsl.activity_dsl_parser import ParsedActivityLine

# Checkbox gate — reuse the parser's patterns so the two paths agree on what a
# checkbox line is (no second definition to drift).
_UNCHECKED = re.compile(r"^[-*]\s*\[\s*\]\s*")
_CHECKED = re.compile(r"^[-*]\s*\[[xX]\]\s*")

# Emoji that carry a trailing ISO date. The created-date marker is written as
# an escape to keep the source ASCII-unambiguous (RUF001).
_DATE_EMOJI = "📅🛫⏳✅\u2795"
# Standalone marker emoji (priority + recurrence) with no inline value we keep.
_MARKER_EMOJI = "🔺⏫🔼🔽⏬🔁"

# An optional Unicode variation selector can follow any emoji.
_VS = r"️?"

_DUE_RE = re.compile(rf"📅{_VS}\s*(\d{{4}}-\d{{2}}-\d{{2}})")
_SCHEDULED_RE = re.compile(rf"⏳{_VS}\s*(\d{{4}}-\d{{2}}-\d{{2}})")
_DONE_RE = re.compile(rf"✅{_VS}\s*(\d{{4}}-\d{{2}}-\d{{2}})")


# Description cleanup: drop date-emoji+date pairs, drop standalone markers, drop
# #tags, then collapse whitespace (mirrors ActivityDSLParser._extract_description).
_DATE_EMOJI_PAIR_RE = re.compile(rf"[{_DATE_EMOJI}]{_VS}\s*\d{{4}}-\d{{2}}-\d{{2}}")
_MARKER_RE = re.compile(rf"[{_MARKER_EMOJI}]{_VS}")
_TAG_RE = re.compile(r"#([\w/-]+)")

# Priority emoji → DSL priority (1 highest .. 5 lowest); absence → 3 (medium).
_PRIORITY_BY_EMOJI: dict[str, int] = {
    "🔺": 1,  # highest
    "⏫": 1,  # high
    "🔼": 2,  # medium
    "🔽": 4,  # low
    "⏬": 5,  # lowest
}


def _parse_iso_date(value: str) -> date | None:
    """Parse a ``YYYY-MM-DD`` token, returning ``None`` on a malformed date."""
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def obsidian_task_line_to_parsed(
    line: str,
    *,
    entry_kind: str | None = None,
    source_file: str | None = None,
    source_line: int | None = None,
) -> ParsedActivityLine | None:
    """Convert one obsidian-tasks checkbox line to a `ParsedActivityLine`.

    Returns ``None`` for any line that is not a markdown checkbox (``- [ ]`` /
    ``- [x]``) — the caller leaves such lines untouched.

    Args:
        line: A single raw markdown line.
        entry_kind: The periodic-note kind (``daily``/``weekly``/...) from the
            entry's ``metadata.entry_kind``; when set, a ``period:{entry_kind}``
            tag is stamped into ``extra_tags`` (foundation for the deferred
            period filter).
        source_file: Optional source UID/path for provenance.
        source_line: Optional 1-based line number for provenance.

    Returns:
        A task-context `ParsedActivityLine`, or ``None`` if not a checkbox line.
    """
    is_checked = bool(_CHECKED.match(line))
    if not is_checked and not _UNCHECKED.match(line):
        return None

    # obsidian-tasks 🆔 join key (ADR-070)
    vault_id_match = VAULT_ID_RE.search(line)
    vault_id = vault_id_match.group(1) if vault_id_match else None

    # Dates
    due_match = _DUE_RE.search(line)
    due_date = _parse_iso_date(due_match.group(1)) if due_match else None
    when = datetime(due_date.year, due_date.month, due_date.day) if due_date else None

    scheduled_match = _SCHEDULED_RE.search(line)
    scheduled_date = _parse_iso_date(scheduled_match.group(1)) if scheduled_match else None

    # ✅ done date — meaningful only on a checked line (a stray ✅ on an unchecked
    # line is stripped from the description like any other marker but carries no
    # completion claim).
    done_match = _DONE_RE.search(line) if is_checked else None
    completion_date = _parse_iso_date(done_match.group(1)) if done_match else None

    # Priority — first recognized emoji wins; default 3 (medium).
    priority = 3
    for emoji, value in _PRIORITY_BY_EMOJI.items():
        if emoji in line:
            priority = value
            break

    # Tags — #tag (without the '#'), plus the period marker when known.
    extra_tags = _TAG_RE.findall(line)
    if entry_kind:
        extra_tags = [*extra_tags, f"period:{entry_kind}"]

    # Description — strip checkbox, 🆔 token, emoji/date markers, and #tags; collapse ws.
    description = _CHECKED.sub("", line) if is_checked else _UNCHECKED.sub("", line)
    description = VAULT_ID_RE.sub(" ", description)
    description = _DATE_EMOJI_PAIR_RE.sub(" ", description)
    description = _MARKER_RE.sub(" ", description)
    description = _TAG_RE.sub(" ", description)
    description = " ".join(description.split())

    # Empty checkbox = template scaffolding (daily notes ship a blank '- [ ] '
    # slot), not a task. Creating it would just fail title validation and spam
    # every sync report with the same warning (G10 alarm fatigue). A blank line
    # that DOES carry a 🆔 join key still parses — it references a real task.
    if not description and not vault_id:
        return None

    # Canonicalize the checkbox prefix to '- [ ] ' — collapsing BOTH the checked
    # state AND the bullet char ('-' vs '*') — so the dedup hash is stable across
    # check/uncheck and bullet style (the active flip-to-COMPLETED round-trip is
    # deferred). Normalizing only the checked branch would leave a '* [ ]' task
    # hashing differently from its '* [x]' twin and let a force re-run duplicate it.
    #
    # Also strip 🆔 from raw_line so the hash is stable across ID injection
    # (ADR-070): a line without an ID and the same line after SKUEL injects
    # '🆔 sk_abc123' must hash identically — otherwise re-sync after injection
    # treats the task as new and creates a duplicate.
    checkbox_re = _CHECKED if is_checked else _UNCHECKED
    normalized_raw = checkbox_re.sub("- [ ] ", line, count=1)
    normalized_raw = VAULT_ID_RE.sub("", normalized_raw)
    normalized_raw = " ".join(normalized_raw.split())

    return ParsedActivityLine(
        description=description,
        contexts=[EntityType.TASK],
        when=when,
        scheduled_date=scheduled_date,
        completion_date=completion_date,
        priority=priority,
        extra_tags=extra_tags,
        source_file=source_file,
        source_line=source_line,
        raw_line=normalized_raw,
        is_checked=is_checked,
        vault_id=vault_id,
    )
