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

import pytest

from core.services.knowledge.user_substance import (
    MAX_SUBSTANCE,
    USER_SUBSTANCE_CHANNELS,
    build_substance_index,
    channel_counts,
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
            breakdown = substance_breakdown(channel_counts(ku, build_substance_index(context)))
            assert breakdown[channel.name] == pytest.approx(expected, abs=1e-9), (
                f"{channel.name} at {count} activities"
            )
            # Nothing else moved.
            assert all(v == 0.0 for k, v in breakdown.items() if k != channel.name)

    def test_an_activity_naming_a_ku_twice_counts_once(self):
        """The weights are per ACTIVITY. An edge written twice is not two habits."""
        context = _context(habit_knowledge_applied={"habit_1": ["ku_a", "ku_a", "ku_a"]})
        assert user_substance_score("ku_a", build_substance_index(context)) == pytest.approx(0.10)

    def test_an_unknown_ku_scores_zero_rather_than_raising(self):
        """A step whose Kus the learner never touched is a reading, not a gap."""
        index = build_substance_index(_context(task_knowledge_applied={"t": ["ku_other"]}))
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
            channel_counts(ku, build_substance_index(_context(**channels)))
        )
        assert sum(breakdown.values()) == pytest.approx(1.30), "the caps themselves changed"
        assert substance_score(breakdown) == MAX_SUBSTANCE

    def test_one_learners_activity_does_not_score_for_another(self):
        """The whole point: this is a per-CONTEXT figure, and a context is one user's."""
        mine = build_substance_index(_context(habit_knowledge_applied={"h1": ["ku_shared"]}))
        theirs = build_substance_index(_context())
        assert user_substance_score("ku_shared", mine) == pytest.approx(0.10)
        assert user_substance_score("ku_shared", theirs) == 0.0

    def test_prompts_cover_exactly_the_empty_channels(self):
        context = _context(habit_knowledge_applied={"h1": ["ku_a"]})
        counts = channel_counts("ku_a", build_substance_index(context))
        prompts = empty_channel_prompts(counts, "Breath Awareness")

        assert len(prompts) == len(USER_SUBSTANCE_CHANNELS) - 1, "habits is used, so not prompted"
        assert all("Breath Awareness" in p for p in prompts)
        assert not any("habit" in p.lower() for p in prompts)
