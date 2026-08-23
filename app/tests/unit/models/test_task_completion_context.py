"""``TaskCompletionContext`` — the typed body of POST /api/context/task/complete.

The request model used to carry ``context: dict[str, Any]`` whose three keys
existed only in a ``json_schema_extra`` example, so ``time_invested_minutes``
reached the service completely unvalidated. Typing it puts the ``ge=0``
constraint (the same one ``TaskCreateRequest.actual_minutes`` carries) at the
boundary, where CLAUDE.md says validation belongs.

Breakage budget for that change, pinned here: lax-mode coercion still applies
and unknown keys are still ignored, so the only newly-rejected input is a
negative number.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.models.task.task_request import ContextualTaskCompletionRequest, TaskCompletionContext


class TestDefaults:
    def test_empty_context_is_valid_and_reports_nothing(self) -> None:
        context = TaskCompletionContext()

        assert context.time_invested_minutes is None
        assert context.knowledge_applied == []
        assert context.quality == "good"

    def test_request_defaults_to_an_empty_context(self) -> None:
        request = ContextualTaskCompletionRequest()

        assert request.context.time_invested_minutes is None
        assert request.reflection == ""

    def test_default_lists_are_not_shared_between_instances(self) -> None:
        first = TaskCompletionContext()
        first.knowledge_applied.append("ku.python")

        assert TaskCompletionContext().knowledge_applied == []


class TestTimeInvestedMinutes:
    def test_negative_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            TaskCompletionContext(time_invested_minutes=-1)

    def test_zero_is_accepted(self) -> None:
        assert TaskCompletionContext(time_invested_minutes=0).time_invested_minutes == 0

    def test_numeric_string_still_coerced(self) -> None:
        """Pydantic v2 lax mode: an existing client sending ``"120"`` keeps working."""
        assert TaskCompletionContext(time_invested_minutes="120").time_invested_minutes == 120


class TestExtraKeys:
    def test_unknown_keys_are_ignored_not_rejected(self) -> None:
        """No ``extra="forbid"`` anywhere in the chain — unknown keys stay ignored."""
        request = ContextualTaskCompletionRequest(context={"energy": "high"})

        assert request.context.quality == "good"
        assert "energy" not in request.context.model_dump()
