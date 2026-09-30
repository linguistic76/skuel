"""``ContextualHabitCompletionRequest.quality`` accepts exactly ``CONTEXTUAL_QUALITY_VALUES``.

An unknown rating is a ``ValidationError`` — the error ``parse_body`` turns into a 400.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.models.habit.habit_request import (
    CONTEXTUAL_QUALITY_VALUES,
    ContextualHabitCompletionRequest,
)


class TestContextualHabitQuality:
    @pytest.mark.parametrize("quality", CONTEXTUAL_QUALITY_VALUES)
    def test_every_accepted_rating_validates(self, quality: str):
        assert ContextualHabitCompletionRequest(quality=quality).quality == quality

    def test_the_default_is_good(self):
        assert ContextualHabitCompletionRequest().quality == "good"

    def test_an_unknown_rating_raises_validation_error(self):
        with pytest.raises(ValidationError) as exc_info:
            ContextualHabitCompletionRequest(quality="wat")

        assert "quality must be one of" in str(exc_info.value)

    def test_environmental_factors_defaults_empty(self):
        assert ContextualHabitCompletionRequest().environmental_factors == {}
