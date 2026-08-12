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
  channel maps carry uids only, with no timestamps anywhere. A personal decay
  curve is therefore not computable from this input, and inventing one from
  engagement timestamps would be measuring a different event (opening a step is
  not applying it). The personal score is cumulative.

⚠ **The score is only as cumulative as its SOURCE.** These functions take the six
maps; they do not fetch them. ``UserContext``'s copies are built by the MEGA-QUERY
for *planning*, so they are window-bounded — and inconsistently, which is the part
that bites: an ACTIVE habit is admitted at any age, while an event is admitted
only if it falls inside the window at all. Scoring off that context yields
"substance among my live and recent activity", which is not what this module's
arithmetic claims. A caller wanting the cumulative figure must source the maps
from ``CrossDomainBackendOperations.get_user_knowledge_channels``, which applies
no window. See § Two sources, one calculation in the philosophy doc.

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

from core.models.enums import EntityType

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from core.ports.query_types import UserKnowledgeChannelRow
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
    entity_type: str
    """The ``EntityType`` value of the activity that feeds this channel — the key
    the unwindowed backend read groups by, since three channels (tasks, events,
    entries) travel over the SAME edge and are told apart only by what sits at
    the tail.

    An ``EntityType`` member value, never a literal: a renamed or re-normalised
    discriminator would otherwise stop matching the rows the backend returns, and
    the failure mode is empty channels and a flat-zero score, not an error."""
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
        entity_type=EntityType.TASK.value,
        weight=0.05,
        cap=0.25,
        recommendation="Create a task that applies '{title}' in your work",
    ),
    SubstanceChannel(
        name="habits",
        context_field="habit_knowledge_applied",
        entity_type=EntityType.HABIT.value,
        weight=0.10,
        cap=0.30,
        recommendation="Build a habit that reinforces '{title}' daily",
    ),
    SubstanceChannel(
        name="events",
        context_field="event_knowledge_applied",
        entity_type=EntityType.EVENT.value,
        weight=0.05,
        cap=0.25,
        recommendation="Schedule a practice session to deepen '{title}'",
    ),
    SubstanceChannel(
        name="entries",
        context_field="entry_knowledge_applied",
        entity_type=EntityType.USER_ENTRY.value,
        weight=0.07,
        cap=0.20,
        recommendation="Write an entry reflecting on '{title}'",
    ),
    SubstanceChannel(
        name="choices",
        context_field="choice_knowledge_informed",
        entity_type=EntityType.CHOICE.value,
        weight=0.07,
        cap=0.15,
        recommendation="Record a choice informed by '{title}'",
    ),
    SubstanceChannel(
        name="principles",
        context_field="principle_knowledge_grounded",
        entity_type=EntityType.PRINCIPLE.value,
        weight=0.07,
        cap=0.15,
        recommendation="Write a principle grounded in '{title}'",
    ),
)

MAX_SUBSTANCE: Final = 1.0
"""The six channels contribute up to 1.30 raw; the total is capped at 1.0."""

# ku_uid -> {channel name: how many of the learner's activities hit it}
SubstanceIndex = dict[str, dict[str, int]]


def build_substance_index(channels: Mapping[str, Mapping[str, Sequence[str]]]) -> SubstanceIndex:
    """Invert the six channel maps into ``ku_uid -> per-channel activity counts``.

    Built ONCE per caller and then queried per Ku. The maps are keyed by activity
    uid, so answering "which of my activities touch this Ku?" directly means
    re-walking all six for every Ku — fine for one detail page, quadratic for an
    aggregate over a learner's whole engagement window.

    Counts ACTIVITIES, not edges: an activity naming the same Ku twice is one
    application of it, which is what the per-instance weights are denominated in.

    Takes the maps rather than fetching them so the windowed (UserContext) and
    unwindowed (backend) sources run the SAME arithmetic — the alternative is two
    scorers that agree until one is edited.
    """
    index: SubstanceIndex = {}
    for channel in USER_SUBSTANCE_CHANNELS:
        for ku_uids in channels.get(channel.name, {}).values():
            for ku_uid in dict.fromkeys(ku_uids):
                counts = index.setdefault(ku_uid, {})
                counts[channel.name] = counts.get(channel.name, 0) + 1
    return index


def channel_maps_from_context(
    user_context: UserContext,
) -> dict[str, Mapping[str, Sequence[str]]]:
    """Read the six maps off a UserContext, keyed by channel name.

    ⚠ WINDOW-BOUNDED, and unevenly so — see the module docstring. Correct for a
    detail page answering "how am I applying this *lately*"; wrong for a
    cumulative figure, which must come from
    ``CrossDomainBackendOperations.get_user_knowledge_channels``.

    One ``getattr`` per channel, without a default, so a ``UserContext`` field
    renamed out from under the table raises here rather than quietly scoring
    every learner at zero.
    """
    return {
        channel.name: cast(
            "Mapping[str, Sequence[str]]", getattr(user_context, channel.context_field)
        )
        for channel in USER_SUBSTANCE_CHANNELS
    }


def build_substance_index_from_context(user_context: UserContext) -> SubstanceIndex:
    """``build_substance_index`` over a UserContext's (windowed) channel maps."""
    return build_substance_index(channel_maps_from_context(user_context))


SUBSTANCE_ACTIVITY_TYPES: Final[tuple[str, ...]] = tuple(
    channel.entity_type for channel in USER_SUBSTANCE_CHANNELS
)
"""The activity ``entity_type``s that carry substance — the backend read's filter.

Derived from the channel table rather than listed again in the persistence layer,
so adding a seventh channel widens the query by construction.
"""

_CHANNEL_BY_ENTITY_TYPE: Final[dict[str, str]] = {
    channel.entity_type: channel.name for channel in USER_SUBSTANCE_CHANNELS
}


def channel_maps_from_rows(
    rows: Iterable[UserKnowledgeChannelRow],
) -> dict[str, dict[str, list[str]]]:
    """Fold ``UserKnowledgeChannelRow``s into the channel maps.

    The unwindowed counterpart of :func:`channel_maps_from_context`, over
    ``CrossDomainBackendOperations.get_user_knowledge_channels``.

    Keys are INDEXED, not ``.get``-ed with a fallback: the backend's processor
    already raises on alias drift, so a missing key here would be a genuine
    contract break and must not be absorbed as "this learner has no activity" —
    that reads as a confident zero, which is the failure this area keeps
    producing.

    A row whose ``entity_type`` is not a substance channel IS dropped, and that
    one is deliberate rather than defensive: the query filters on
    ``SUBSTANCE_ACTIVITY_TYPES``, so a stray type means query and table have
    diverged, and bucketing it into some channel would score the learner for a
    channel the philosophy does not weight.
    """
    channels: dict[str, dict[str, list[str]]] = {
        channel.name: {} for channel in USER_SUBSTANCE_CHANNELS
    }
    for row in rows:
        channel_name = _CHANNEL_BY_ENTITY_TYPE.get(row["entity_type"])
        if channel_name is None:
            continue
        ku_uids = list(dict.fromkeys(row["ku_uids"]))
        if ku_uids:
            channels[channel_name][row["activity_uid"]] = ku_uids
    return channels


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
