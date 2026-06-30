"""Journal activity suggestions — bridge output → paste-ready DSL lines.

The journals workflow offers *suggested* activity lines beside the reflection
(the "prose + suggestions" model). These are inert: the user copies the ones
they want into a Periodic Note or a designated extraction folder, where the
existing extractor turns them into entities on sync. Nothing here creates or
persists an entity.

Pipeline: ``LLMDSLBridgeService.transform_with_context`` emits ``@context()``
lines (tag-first, no checkbox); this module parses them with the canonical
``ActivityDSLParser`` and re-renders each into the checkbox form documented in
``userguides/context-dsl-cheatsheet.md`` (``- [ ] <desc> @context(<type>) …``),
dropping anything that doesn't parse. The result is a list the panel can show
and the user can paste verbatim.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.services.dsl.activity_dsl_parser import ActivityDSLParser, ParsedActivityLine


@dataclass(frozen=True)
class SuggestedActivity:
    """One paste-ready activity suggestion derived from a journal entry.

    Attributes:
        domain: EntityType/NonKuDomain value of the first ``@context()`` (e.g. "task").
        dsl_line: Canonical checkbox DSL line the user copies verbatim.
        description: Human-readable label (the line with tags stripped).
    """

    domain: str
    dsl_line: str
    description: str


def _render_repeat(repeat: dict[str, Any] | None) -> str | None:
    """Reconstruct an ``@repeat()`` value string from the parsed repeat dict."""
    if not repeat:
        return None
    kind = repeat.get("type")
    if kind == "daily":
        return "daily"
    if kind == "custom":
        return "custom"
    if kind == "weekly":
        days = repeat.get("days") or []
        return "weekly:" + ",".join(days) if days else "weekly"
    if kind == "monthly":
        days = repeat.get("days") or []
        return "monthly:" + ",".join(str(d) for d in days) if days else "monthly"
    if kind == "interval":
        unit_abbr = {"days": "d", "hours": "h", "weeks": "w", "months": "m"}.get(
            str(repeat.get("unit", "days")), "d"
        )
        return f"every:{repeat.get('interval', 1)}{unit_abbr}"
    return None


def render_canonical_dsl(activity: ParsedActivityLine) -> str:
    """Render a parsed activity into canonical checkbox DSL.

    Produces ``- [ ] <description> @context(<type>) <optional tags>`` so the
    line displays as a task in Obsidian, round-trips via VaultBridge, and
    matches the cheat-sheet form the extractor consumes.
    """
    tokens: list[str] = []
    if activity.contexts:
        tokens.append(f"@context({activity.contexts[0].value})")
    if activity.when:
        tokens.append(f"@when({activity.when.strftime('%Y-%m-%dT%H:%M')})")
    if activity.priority:
        tokens.append(f"@priority({activity.priority})")
    if activity.duration_minutes:
        tokens.append(f"@duration({activity.duration_minutes}m)")
    if activity.energy_states:
        tokens.append(f"@energy({','.join(activity.energy_states)})")
    repeat = _render_repeat(activity.repeat_pattern)
    if repeat:
        tokens.append(f"@repeat({repeat})")
    if activity.primary_ku:
        tokens.append(f"@ku({activity.primary_ku})")
    for link in activity.links:
        link_id = link.get("id")
        if link_id:
            tokens.append(f"@link({link_id})")

    head = f"- [ ] {activity.description}".rstrip()
    return " ".join([head, *tokens]) if tokens else head


def build_suggestions(activity_lines: list[str]) -> list[SuggestedActivity]:
    """Parse bridge ``@context()`` lines into paste-ready suggestions.

    Lines that don't parse, or carry no description, are dropped — the panel
    only ever shows valid, copyable lines.
    """
    if not activity_lines:
        return []

    parser = ActivityDSLParser()
    parsed = parser.parse_journal("\n".join(activity_lines))
    if parsed.is_error:
        return []

    suggestions: list[SuggestedActivity] = []
    for activity in parsed.value.activities:
        if not activity.contexts or not activity.description.strip():
            continue
        suggestions.append(
            SuggestedActivity(
                domain=activity.contexts[0].value,
                dsl_line=render_canonical_dsl(activity),
                description=activity.description.strip(),
            )
        )
    return suggestions


__all__ = ["SuggestedActivity", "build_suggestions", "render_canonical_dsl"]
