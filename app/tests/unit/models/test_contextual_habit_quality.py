"""``ContextualHabitCompletionRequest.quality`` rejects bad input as 400, not 500.

The field was annotated as a ``Literal``. FastHTML binds this model as
``body: ContextualHabitCompletionRequest`` and coerces each incoming value by
**calling** the annotation, so a ``Literal`` raised
``TypeError: Cannot instantiate typing.Literal`` — not a ``ValidationError``, so
``install_request_validation_guard`` (added in #1126) never saw it and the route
returned 500 for ordinary bad input.

Found while implementing the cascade-idempotency arc and reported rather than fixed
at the time; this pins the fix.
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
    def test_every_accepted_rating_still_validates(self, quality: str):
        assert ContextualHabitCompletionRequest(quality=quality).quality == quality

    def test_the_default_is_unchanged(self):
        assert ContextualHabitCompletionRequest().quality == "good"

    def test_an_unknown_rating_raises_validation_error_not_type_error(self):
        """The whole point: a ``ValidationError`` is what the 400 guard converts.

        A ``TypeError`` — what the ``Literal`` annotation produced — is not, and
        surfaced to the caller as a 500.
        """
        with pytest.raises(ValidationError) as exc_info:
            ContextualHabitCompletionRequest(quality="wat")

        assert "quality must be one of" in str(exc_info.value)

    def test_the_annotation_is_callable_so_fasthtml_coercion_cannot_raise(self):
        """FastHTML calls the field's annotation to coerce. ``str`` is callable.

        This is the property that actually fixes the 500 — the validator only
        works because the coercion call in front of it now succeeds. A ``Literal``
        is not callable; nor is an enum safe here, since ``Enum("bad")`` raises
        ``ValueError`` outside the model where nothing converts it either.
        """
        annotation = ContextualHabitCompletionRequest.model_fields["quality"].annotation

        assert annotation is str
        assert annotation("wat") == "wat"

    def test_environmental_factors_still_defaults_empty(self):
        assert ContextualHabitCompletionRequest().environmental_factors == {}
