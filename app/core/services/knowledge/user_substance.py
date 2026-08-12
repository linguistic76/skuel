"""
Per-User Knowledge Substance
=============================

THE weight table for per-user substance, and the pure arithmetic over it.

"How much have *I* applied this knowledge?" is a different question from the one
``Curriculum.substance_score()`` answers. That method reads counters written onto
the SHARED curriculum node by ``KuBackend.increment_substance``, which carries no
``user_uid`` — so on a multi-tenant instance it is a corpus-global figure. The
per-user figure is computed instead from the six activity→knowledge channel maps
on ``UserContext``, which are by construction one learner's own.

Two differences between the two figures are deliberate and must not be "fixed"
by making them agree:

* **Six channels here, five there.** The node counters have no principles field,
  so ``GROUNDED_IN_KNOWLEDGE`` contributes to the personal score only.
* **No time decay here.** The node carries a ``last_*_date`` per channel; the
  ``UserContext`` maps carry uids only, with no timestamps anywhere. A personal
  decay curve is therefore not computable from this input, and inventing one
  from engagement timestamps would be measuring a different event (opening a
  step is not applying it). The personal score is cumulative.

**Why this module exists at all.** The same six weights and caps were written out
by hand in ``KuIntelligenceService`` and ``PsIntelligenceService``, and the
Layer-0 analytics metric was about to become a third copy. This codebase has been
bitten repeatedly by a duplicated vocabulary drifting between its copies, so the
table lives here and nowhere else; the callers own their presentation, not their
arithmetic.

See: /docs/architecture/knowledge_substance_philosophy.md § Per-User Substance
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from core.services.user import UserContext


@dataclass(frozen=True, kw_only=True)
class SubstanceChannel:
    """One activity channel through which a learner substantiates knowledge.

    ``context_field`` names the ``UserContext`` attribute holding that channel's
    ``{activity_uid: [ku_uid, ...]}`` map. It is read with ``getattr`` in exactly
    one place (:func:`build_substance_index`) and without a default, so a field
    renamed out from under this table raises there instead of quietly scoring
    every learner at zero.
    """

    name: str
    context_field: str
    weight: float
    cap: float
    recommendation: str
    """Prompt shown when the channel is empty. ``{title}`` is the entity title."""


# The canonical order is the order the ``breakdown`` dict has always been emitted
# in; it is API surface for the Ku my-context response and for the dual-track
# evidence lines, so it is fixed here rather than re-chosen per caller.
USER_SUBSTANCE_CHANNELS: Final[tuple[SubstanceChannel, ...]] = (
    SubstanceChannel(
        name="tasks",
        context_field="task_knowledge_applied",
        weight=0.05,
        cap=0.25,
        recommendation="Create a task that applies '{title}' in your work",
    ),
    SubstanceChannel(
        name="habits",
        context_field="habit_knowledge_applied",
        weight=0.10,
        cap=0.30,
        recommendation="Build a habit that reinforces '{title}' daily",
    ),
    SubstanceChannel(
        name="events",
        context_field="event_knowledge_applied",
        weight=0.05,
        cap=0.25,
        recommendation="Schedule a practice session to deepen '{title}'",
    ),
    SubstanceChannel(
        name="entries",
        context_field="entry_knowledge_applied",
        weight=0.07,
        cap=0.20,
        recommendation="Write an entry reflecting on '{title}'",
    ),
    SubstanceChannel(
        name="choices",
        context_field="choice_knowledge_informed",
        weight=0.07,
        cap=0.15,
        recommendation="Record a choice informed by '{title}'",
    ),
    SubstanceChannel(
        name="principles",
        context_field="principle_knowledge_grounded",
        weight=0.07,
        cap=0.15,
        recommendation="Write a principle grounded in '{title}'",
    ),
)

MAX_SUBSTANCE: Final = 1.0
"""The six channels contribute up to 1.30 raw; the total is capped at 1.0."""

# ku_uid -> {channel name: how many of the learner's activities hit it}
SubstanceIndex = dict[str, dict[str, int]]


def build_substance_index(user_context: UserContext) -> SubstanceIndex:
    """Invert the six channel maps into ``ku_uid -> per-channel activity counts``.

    Built ONCE per caller and then queried per Ku. The maps are keyed by activity
    uid, so answering "which of my activities touch this Ku?" directly means
    re-walking all six for every Ku — fine for one detail page, quadratic for an
    aggregate over a learner's whole engagement window.

    Counts ACTIVITIES, not edges: an activity naming the same Ku twice is one
    application of it, which is what the per-instance weights are denominated in.
    """
    index: SubstanceIndex = {}
    for channel in USER_SUBSTANCE_CHANNELS:
        applied = cast("Mapping[str, Sequence[str]]", getattr(user_context, channel.context_field))
        for ku_uids in applied.values():
            for ku_uid in dict.fromkeys(ku_uids):
                counts = index.setdefault(ku_uid, {})
                counts[channel.name] = counts.get(channel.name, 0) + 1
    return index


def channel_counts(ku_uid: str, index: SubstanceIndex) -> dict[str, int]:
    """Zero-filled per-channel activity counts for one Ku, in canonical order.

    Zero-filled rather than sparse: an absent channel and an empty one are the
    same fact to every consumer, and the callers that drive recommendations off
    "which channels are empty" would otherwise have to re-enumerate the six.
    """
    hits = index.get(ku_uid, {})
    return {channel.name: hits.get(channel.name, 0) for channel in USER_SUBSTANCE_CHANNELS}


def substance_breakdown(counts: Mapping[str, int]) -> dict[str, float]:
    """Apply each channel's per-instance weight and per-channel cap."""
    return {
        channel.name: round(min(channel.cap, counts[channel.name] * channel.weight), 3)
        for channel in USER_SUBSTANCE_CHANNELS
    }


def substance_score(breakdown: Mapping[str, float]) -> float:
    """Sum a breakdown into the capped 0.0-1.0 substance score."""
    return min(MAX_SUBSTANCE, sum(breakdown.values()))


def user_substance_score(ku_uid: str, index: SubstanceIndex) -> float:
    """The learner's substance score for one Ku — the three steps composed."""
    return substance_score(substance_breakdown(channel_counts(ku_uid, index)))


def empty_channel_prompts(counts: Mapping[str, int], title: str) -> list[str]:
    """Recommendation lines for the channels this learner has not used yet."""
    return [
        channel.recommendation.format(title=title)
        for channel in USER_SUBSTANCE_CHANNELS
        if counts[channel.name] == 0
    ]
