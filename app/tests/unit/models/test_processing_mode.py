"""ProcessingMode contract — the journals upload-door discriminator (ADR-073).

The parse contract is the point of this enum: an unrecognised wire value must
resolve to ``None`` so both upload doors fail closed. ``JournalMode``-style
defaulting is what previously let an unknown mode reach the transcribe tail
after spending Deepgram/LLM quota.
"""

from __future__ import annotations

import pytest

from core.models.enums.pipeline import Pipeline, ProcessingMode


class TestWireValues:
    """The values are a public contract: Alpine compares them client-side and
    the form posts them verbatim. Changing one is a breaking change."""

    def test_values_are_frozen(self) -> None:
        assert ProcessingMode.TRANSCRIBE_ONLY.value == "transcribe_only"
        assert ProcessingMode.TRANSCRIBE_AND_INSTRUCTIONS.value == "transcribe_and_instructions"
        assert ProcessingMode.INSTRUCTIONS_ONLY.value == "instructions_only"

    def test_membership_is_exactly_three(self) -> None:
        assert len(ProcessingMode) == 3

    @pytest.mark.parametrize("pipeline", list(Pipeline))
    def test_no_pipeline_value_parses_as_a_mode(self, pipeline: Pipeline) -> None:
        # Pipeline is a PERSISTED UserEntry field carrying audience semantics;
        # ProcessingMode is a transient, zero-persistence upload discriminator.
        # Their near-twin names (TRANSCRIBE / TRANSCRIBE_AND_STRUCTURE /
        # LLM_SUMMARY) are the trap. Asserting the *values* differ is a
        # tautology MyPy already proves — what matters is that a Pipeline value
        # arriving on the wire is rejected, not silently coerced.
        assert ProcessingMode.from_string(pipeline.value) is None


class TestFromString:
    def test_default_is_transcribe_only(self) -> None:
        assert ProcessingMode.default() is ProcessingMode.TRANSCRIBE_ONLY

    @pytest.mark.parametrize("mode", list(ProcessingMode))
    def test_round_trips_every_member(self, mode: ProcessingMode) -> None:
        assert ProcessingMode.from_string(mode.value) is mode

    @pytest.mark.parametrize("absent", [None, "", "   "])
    def test_absent_takes_the_default(self, absent: object) -> None:
        # Preserves the form's pre-enum behaviour: an omitted field is not an
        # error, it is "the composer's default selection".
        assert ProcessingMode.from_string(absent) is ProcessingMode.default()

    @pytest.mark.parametrize("bogus", ["surprise_mode", "TRANSCRIBE", "transcribe", "llm_summary"])
    def test_unrecognised_returns_none(self, bogus: str) -> None:
        # None, never a default — the caller must fail closed. `llm_summary` is
        # included deliberately: a valid *Pipeline* value is not a valid mode.
        assert ProcessingMode.from_string(bogus) is None

    def test_normalises_case_and_surrounding_space(self) -> None:
        assert ProcessingMode.from_string("  Instructions_Only  ") is (
            ProcessingMode.INSTRUCTIONS_ONLY
        )
