"""Askesis grounding projection — the named curated rendering of UserContext (ADR-082 D2).

Askesis grounds every turn on the real ``build_rich()`` UserContext (~250
fields), but what reaches the prompt is THIS projection — a legible, tunable
rendering, never an open-ended dump. ``ASKESIS_GROUNDING_FIELDS`` is the
explicit list of UserContext fields the projection may read; the recording
test in ``tests/unit/services/test_askesis_grounding_projection.py`` fails if
the renderer reaches beyond it. That explicit list is ADR-082's named
mitigation for the scope-creep risk.

The content is Askesis-natural and DISTINCT from the Journals projection
(``core/services/journal/grounding_projection.py``) — the two companions
share mechanism, never voice or content (ADR-082 two-companions ruling):
identity, LifePath framing, learning-journey position (enrolled paths,
current steps, mastery counts), and light activity relevance where it serves
study. Skeleton-tolerant: a thin LifePath or empty curriculum degrades to
NOTHING — sections are omitted, never padded with filler.

Unlike Journals (standard ``build()`` depth — UIDs joined against
service-fetched models), Askesis rides RICH depth, where titles arrive
inline (``current_path_steps``, ``enrolled_paths_rich``, ``entities_rich``)
— so the render is a pure function of the context alone, no service joins.

Privacy wall (ADR-073/078): the projection reads structural UserContext
only — never chat transcripts, never Journals content. Guarded by the
understanding-wall tests in
``tests/unit/conversation/test_conversation_understanding_wall.py``.

See: /docs/decisions/ADR-082-askesis-instruction-home-and-grounding.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.ports.query_types import RichLearningPathItem
    from core.services.user.unified_user_context import UserContext

# The EXPLICIT UserContext field list this projection reads (ADR-082 D2).
# Adding a field here is a deliberate grounding decision — extend the render
# AND the tests together, never silently.
ASKESIS_GROUNDING_FIELDS: tuple[str, ...] = (
    # Identity
    "display_name",
    # LifePath framing (skeleton-tolerant)
    "life_path_uid",
    "life_path_alignment_score",
    # Learning-journey position
    "enrolled_paths_rich",
    "current_path_steps",
    "mastered_knowledge_uids",
    "in_progress_knowledge_uids",
    # Light activity relevance — the goals study serves
    "active_goal_uids",
    "entities_rich",
)

# Grounding stays light — same spirit as the Journals per-domain cap.
_MAX_PATHS = 3
_MAX_STEPS = 3
_MAX_GOALS = 3


def render_askesis_grounding(context: UserContext) -> str:
    """Render the curated learner-grounding block for an Askesis prompt.

    Pure function over an already-built rich ``UserContext`` — no I/O, so the
    projection is testable byte-for-byte. Every UserContext read stays inside
    ``ASKESIS_GROUNDING_FIELDS``. A skeleton context (no LifePath, nothing
    enrolled, no mastery) renders ``""`` — callers skip the empty block.
    """
    lines: list[str] = []

    if context.display_name:
        lines.append(f"You are studying with {context.display_name}.")

    if context.life_path_uid:
        if context.life_path_alignment_score > 0:
            lines.append(
                "They have designated a LifePath — current activity alignment "
                f"with it: {context.life_path_alignment_score:.0%}."
            )
        else:
            lines.append("They have designated a LifePath.")

    path_entries = [
        entry for item in context.enrolled_paths_rich[:_MAX_PATHS] if (entry := _path_entry(item))
    ]
    if path_entries:
        lines.append("Enrolled learning paths: " + ", ".join(path_entries) + ".")

    steps = [step["title"] for step in context.current_path_steps[:_MAX_STEPS] if step["title"]]
    if steps:
        lines.append("Now studying: " + ", ".join(steps) + ".")

    mastered = len(context.mastered_knowledge_uids)
    in_progress = len(context.in_progress_knowledge_uids)
    if mastered or in_progress:
        lines.append(f"Knowledge base: {mastered} concepts mastered, {in_progress} in progress.")

    goal_titles = _active_goal_titles(context)
    if goal_titles:
        lines.append("Goals they are working toward: " + ", ".join(goal_titles) + ".")

    return "\n".join(lines)


def _path_entry(item: RichLearningPathItem) -> str:
    """One enrolled-path entry: title, with step progress when the graph has it."""
    path = item.get("path") or {}
    title = path.get("title")
    if not title:
        return ""
    graph_context = item.get("graph_context") or {}
    total = graph_context.get("total_steps") or 0
    if total:
        completed = graph_context.get("completed_steps") or 0
        return f"{title} ({completed}/{total} steps)"
    return str(title)


def _active_goal_titles(context: UserContext) -> list[str]:
    """Titles of active goals, joined inline from the rich entity payload.

    ``active_goal_uids`` is the relevance lens (the status rule the rest of
    the app trusts); ``entities_rich`` carries titles for active AND
    recently-touched completed entities, so membership in the active list
    decides — completed goals must not resurface as current direction.
    """
    by_uid: dict[str, str] = {}
    for item in context.entities_rich.get("goals", []):
        entity = item.get("entity") or {}
        uid, title = entity.get("uid"), entity.get("title")
        if uid and title:
            by_uid[uid] = title
    titles = [by_uid[uid] for uid in context.active_goal_uids if uid in by_uid]
    return titles[:_MAX_GOALS]
