"""Journal activity suggestions — bridge output → paste-ready DSL lines.

The journals workflow offers *suggested* activity lines beside the reflection
(the "prose + suggestions" model). These are inert: the user copies the ones
they want into a Periodic Note or a designated extraction folder, where the
existing extractor turns them into entities on sync. Nothing here creates or
persists an entity.

Pipeline: ``LLMDSLBridgeService.transform_with_context`` emits ``@context()``
lines (tag-first, no checkbox); this module parses them with the canonical
``ActivityDSLParser`` to validate + extract a clean description, then re-renders
each into the checkbox form documented in
``userguides/context-dsl-cheatsheet.md`` (``- [ ] <desc> @context(<type>) …``).

**Metadata is preserved, not normalised.** The bridge prompt produces loosely
shaped tags (``@when(Friday)``, ``@priority(high)``, ``@amount(150)``) that the
strict parser cannot turn into ISO dates / numeric priorities. Rather than drop
them, the bridge's tags are carried through verbatim — the user refines them
when curating. Only the shape (checkbox, description-first, context-first) is
normalised; lines that don't parse at all are dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from core.services.dsl.activity_dsl_parser import ActivityDSLParser, ParsedActivityLine

# Matches a single ``@name(value)`` DSL tag.
_TAG_RE = re.compile(r"@\w+\([^)]*\)")


@dataclass(frozen=True)
class SuggestedActivity:
    """One paste-ready activity suggestion derived from a journal entry.

    Attributes:
        domain: EntityType/NonKuDomain value of the first ``@context()`` (e.g. "task").
        dsl_line: Paste-ready checkbox DSL line the user copies verbatim.
        description: Human-readable label (the line with tags stripped).
    """

    domain: str
    dsl_line: str
    description: str


def render_suggestion_line(activity: ParsedActivityLine) -> str:
    """Render a parsed activity into checkbox DSL, preserving the bridge's tags.

    Produces ``- [ ] <description> @context(<type>) <remaining tags verbatim>``.
    Tags the bridge inferred are kept as-is (deadlines, priorities, durations,
    amounts) so nothing is silently lost; only the checkbox + description-first
    + context-first *shape* is normalised, and the ``@context`` value is
    canonicalised to its EntityType/NonKuDomain form.
    """
    raw = activity.raw_line or ""
    other_tags = [t for t in _TAG_RE.findall(raw) if not t.lower().startswith("@context(")]

    head = f"- [ ] {activity.description}".rstrip()
    parts = [head]
    if activity.contexts:
        parts.append(f"@context({activity.contexts[0].value})")
    parts.extend(other_tags)
    return " ".join(parts)


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
                dsl_line=render_suggestion_line(activity),
                description=activity.description.strip(),
            )
        )
    return suggestions


__all__ = [
    "SuggestedActivity",
    "build_suggestions",
    "render_suggestion_line",
]
