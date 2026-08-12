"""
Drift guards for the ONE per-user substance weight table.
==========================================================

``core.services.knowledge.user_substance`` exists because the same six weights
and caps were written out by hand in ``KuIntelligenceService`` and
``PsIntelligenceService``, and the Layer-0 analytics metric was about to become
a third copy. Consolidating only helps if the consolidated table cannot rot, so
these tests pin the two ways it can:

1. **Silent zero.** Every channel names a ``UserContext`` field by string. Rename
   that field and the table stops finding the learner's activity — which does
   not raise, it scores everyone 0.0. ``build_substance_index`` reads with a
   bare ``getattr`` precisely so this fails loudly, and the first test proves
   that door is actually shut.
2. **Silent divergence from the philosophy.** The weights are a product
   decision documented in ``knowledge_substance_philosophy.md``. The table is
   the executable copy; the second test pins the numbers so an edit to either
   has to be an edit to both.

The arithmetic tests below deliberately assert at the CAP boundaries. A weight
that is wrong by one channel is invisible in a total when the channel is capped,
so each channel is exercised at one below its cap and at three above it.
"""

import dataclasses
from typing import cast

import pytest

from core.models.enums import EntityType
from core.ports.query_types import UserKnowledgeChannelRow
from core.services.knowledge.user_substance import (
    MAX_SUBSTANCE,
    SUBSTANCE_ACTIVITY_TYPES,
    USER_SUBSTANCE_CHANNELS,
    build_substance_index,
    build_substance_index_from_context,
    channel_counts,
    channel_maps_from_rows,
    empty_channel_prompts,
    substance_breakdown,
    substance_score,
    user_substance_score,
)
from core.services.user import UserContext

# The philosophy doc's table, transcribed: (channel, per-instance weight, cap).
# Duplicated here ON PURPOSE — a guard that imports the value it is guarding
# asserts nothing.
PHILOSOPHY_WEIGHTS = {
    "habits": (0.10, 0.30),
    "entries": (0.07, 0.20),
    "choices": (0.07, 0.15),
    "principles": (0.07, 0.15),
    "events": (0.05, 0.25),
    "tasks": (0.05, 0.25),
}


def _context(**channels: dict[str, list[str]]) -> UserContext:
    """A UserContext carrying only the named activity→knowledge maps."""
    return UserContext(user_uid="user_substance_unit", **channels)


class TestChannelTableIntegrity:
    def test_every_channel_names_a_real_user_context_field(self):
        """A renamed field must be a crash here, not a flat zero in production."""
        fields = {f.name for f in dataclasses.fields(UserContext)}
        missing = [
            c.context_field for c in USER_SUBSTANCE_CHANNELS if c.context_field not in fields
        ]
        assert not missing, (
            f"channel fields absent from UserContext: {missing} — "
            "build_substance_index would raise AttributeError at runtime"
        )

    def test_weights_match_the_published_philosophy(self):
        """The table IS the philosophy doc's table, not a drifting cousin."""
        assert {c.name for c in USER_SUBSTANCE_CHANNELS} == set(PHILOSOPHY_WEIGHTS), (
            "a channel was added or dropped without updating "
            "docs/architecture/knowledge_substance_philosophy.md"
        )
        for channel in USER_SUBSTANCE_CHANNELS:
            assert (channel.weight, channel.cap) == PHILOSOPHY_WEIGHTS[channel.name], (
                f"{channel.name}: table says {(channel.weight, channel.cap)}, "
                f"philosophy says {PHILOSOPHY_WEIGHTS[channel.name]}"
            )

    def test_every_channel_discriminator_is_an_entity_type_value(self):
        """No parallel vocabulary of raw discriminator strings.

        The backend groups its rows by ``entity_type`` and the table looks them
        up by the same key. A literal here that drifted from ``EntityType``
        would not raise — the lookup would simply miss, every channel would come
        back empty, and the learner would score a flat zero.
        """
        valid = {member.value for member in EntityType}
        for channel in USER_SUBSTANCE_CHANNELS:
            assert channel.entity_type in valid, (
                f"{channel.name}: {channel.entity_type!r} is not an EntityType value"
            )

    def test_every_channel_carries_a_prompt(self):
        """A scored channel with no recommendation is a channel users never hear about."""
        for channel in USER_SUBSTANCE_CHANNELS:
            assert "{title}" in channel.recommendation, channel.name


class TestScoring:
    @pytest.mark.parametrize("channel", USER_SUBSTANCE_CHANNELS, ids=lambda c: c.name)
    def test_each_channel_scores_and_caps_independently(self, channel):
        """Below the cap the weight is linear; above it, the cap holds."""
        ku = "ku_target"
        below = max(1, int(channel.cap / channel.weight) - 1)
        above = int(channel.cap / channel.weight) + 3

        for count, expected in ((below, below * channel.weight), (above, channel.cap)):
            context = _context(**{channel.context_field: {f"act_{i}": [ku] for i in range(count)}})
            breakdown = substance_breakdown(
                channel_counts(ku, build_substance_index_from_context(context))
            )
            assert breakdown[channel.name] == pytest.approx(expected, abs=1e-9), (
                f"{channel.name} at {count} activities"
            )
            # Nothing else moved.
            assert all(v == 0.0 for k, v in breakdown.items() if k != channel.name)

    def test_an_activity_naming_a_ku_twice_counts_once(self):
        """The weights are per ACTIVITY. An edge written twice is not two habits."""
        context = _context(habit_knowledge_applied={"habit_1": ["ku_a", "ku_a", "ku_a"]})
        assert user_substance_score(
            "ku_a", build_substance_index_from_context(context)
        ) == pytest.approx(0.10)

    def test_an_unknown_ku_scores_zero_rather_than_raising(self):
        """A step whose Kus the learner never touched is a reading, not a gap."""
        index = build_substance_index_from_context(
            _context(task_knowledge_applied={"t": ["ku_other"]})
        )
        assert user_substance_score("ku_untouched", index) == 0.0
        assert channel_counts("ku_untouched", index) == dict.fromkeys(
            (c.name for c in USER_SUBSTANCE_CHANNELS), 0
        )

    def test_the_total_is_capped_at_one(self):
        """All six channels saturated sum to 1.30 raw — the score must not exceed 1.0."""
        ku = "ku_everything"
        channels = {
            c.context_field: {f"{c.name}_{i}": [ku] for i in range(10)}
            for c in USER_SUBSTANCE_CHANNELS
        }
        breakdown = substance_breakdown(
            channel_counts(ku, build_substance_index_from_context(_context(**channels)))
        )
        assert sum(breakdown.values()) == pytest.approx(1.30), "the caps themselves changed"
        assert substance_score(breakdown) == MAX_SUBSTANCE

    def test_one_learners_activity_does_not_score_for_another(self):
        """The whole point: this is a per-CONTEXT figure, and a context is one user's."""
        mine = build_substance_index_from_context(
            _context(habit_knowledge_applied={"h1": ["ku_shared"]})
        )
        theirs = build_substance_index_from_context(_context())
        assert user_substance_score("ku_shared", mine) == pytest.approx(0.10)
        assert user_substance_score("ku_shared", theirs) == 0.0

    def test_both_sources_produce_the_same_index(self):
        """The windowed and unwindowed sources must feed identical arithmetic.

        Two entry points into one calculation is the shape that drifts, so this
        asserts they agree on the same underlying facts rather than trusting
        that they were written to.
        """
        from_context = build_substance_index_from_context(
            _context(
                habit_knowledge_applied={"h1": ["ku_a"], "h2": ["ku_a"]},
                task_knowledge_applied={"t1": ["ku_a", "ku_b"]},
            )
        )
        from_rows = build_substance_index(
            channel_maps_from_rows(
                [
                    {"entity_type": "habit", "activity_uid": "h1", "ku_uids": ["ku_a"]},
                    {"entity_type": "habit", "activity_uid": "h2", "ku_uids": ["ku_a"]},
                    {"entity_type": "task", "activity_uid": "t1", "ku_uids": ["ku_a", "ku_b"]},
                ]
            )
        )
        assert from_rows == from_context
        assert user_substance_score("ku_a", from_rows) == pytest.approx(0.25)  # 0.20 + 0.05

    def test_a_row_from_a_non_substance_entity_is_dropped_not_bucketed(self):
        """A goal names knowledge but is not one of the six channels.

        Dropping it is the honest move: the query filters on
        SUBSTANCE_ACTIVITY_TYPES, so a stray row means query and table have
        diverged, and quietly bucketing it into some channel would score the
        learner for a channel the philosophy does not weight.
        """
        assert "goal" not in SUBSTANCE_ACTIVITY_TYPES
        channels = channel_maps_from_rows(
            [
                {"entity_type": "goal", "activity_uid": "g1", "ku_uids": ["ku_a"]},
                {"entity_type": "habit", "activity_uid": "h1", "ku_uids": ["ku_a"]},
            ]
        )
        assert user_substance_score("ku_a", build_substance_index(channels)) == pytest.approx(0.10)

    def test_a_malformed_row_raises_rather_than_reading_as_no_activity(self):
        """A contract break must not be absorbed as "this learner applied nothing".

        The backend's processor indexes each RETURN alias, so drift raises
        there. This pins the consumer side of the same rule: a row missing a key
        raises here instead of being skipped, because a skipped row is
        indistinguishable from a learner with no activity — a confident zero,
        which is the failure this whole area keeps producing.

        The ``cast`` is the subject, not a workaround: mypy rejects this literal,
        which is exactly right and is why the typed row is worth having. It
        cannot police the runtime boundary the rows actually cross — the driver
        hands back raw dicts — so the cast reproduces a violated contract that
        static typing has already done all it can about.
        """
        malformed = cast(
            "UserKnowledgeChannelRow", {"entity_type": "habit", "ku_uids": ["ku_a"]}
        )  # no activity_uid
        with pytest.raises(KeyError):
            channel_maps_from_rows([malformed])

    def test_activity_types_cover_every_channel(self):
        """The query's filter is derived from the table, so it cannot under-select."""
        assert set(SUBSTANCE_ACTIVITY_TYPES) == {c.entity_type for c in USER_SUBSTANCE_CHANNELS}
        assert len(SUBSTANCE_ACTIVITY_TYPES) == len(USER_SUBSTANCE_CHANNELS), (
            "duplicate entity_type"
        )

    def test_prompts_cover_exactly_the_empty_channels(self):
        context = _context(habit_knowledge_applied={"h1": ["ku_a"]})
        counts = channel_counts("ku_a", build_substance_index_from_context(context))
        prompts = empty_channel_prompts(counts, "Breath Awareness")

        assert len(prompts) == len(USER_SUBSTANCE_CHANNELS) - 1, "habits is used, so not prompted"
        assert all("Breath Awareness" in p for p in prompts)
        assert not any("habit" in p.lower() for p in prompts)
