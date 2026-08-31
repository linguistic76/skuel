"""`generate_suggested_actions` consumes `get_learning_context`'s DICT rows.

These intent branches were dead until activation (PR-2, 2026-08-31): the
classifier had only ever returned SPECIFIC, so no production call had reached
them — and the first call that did crashed on ``learning_paths[0].uid``,
because ``ContextRetriever.get_learning_context`` serves plain dicts
(``{"uid", "title", ...}``), not domain models. The writer decides the storage
shape; these pin the reader to it. Every prior test mocked the method away,
which is exactly how the crash stayed invisible.
"""

from __future__ import annotations

import pytest

from core.models.query_types import QueryIntent
from core.services.askesis.response_generator import ResponseGenerator

# A context carrying BOTH action sources, so a branch that fires for an intent
# it should not fire for has something to trip over.
_FULL_CONTEXT = {
    "learning_paths": [{"uid": "lp.mindfulness.101", "title": "Mindfulness 101"}],
    "related_tasks": [{"uid": "task_abc123", "title": "Practice", "status": "active"}],
}

# The only intents with a generate_suggested_actions branch. The derived list
# covers every OTHER QueryIntent member, so a future intent cannot be forgotten.
_ACTION_BEARING = {QueryIntent.HIERARCHICAL, QueryIntent.PRACTICE}


def _intent_value(intent: QueryIntent) -> str:
    return intent.value


_NON_ACTION_INTENTS: list[QueryIntent] = sorted(
    (i for i in QueryIntent if i not in _ACTION_BEARING), key=_intent_value
)


class TestGenerateSuggestedActionsConsumesWriterShape:
    def test_hierarchical_reads_the_learning_path_dict(self) -> None:
        actions = ResponseGenerator().generate_suggested_actions(
            "what should I learn next",
            {"learning_paths": [{"uid": "lp.mindfulness.101", "title": "Mindfulness 101"}]},
            QueryIntent.HIERARCHICAL,
        )

        assert actions == [
            {
                "action": "continue_learning_path",
                "target": "lp.mindfulness.101",
                "description": "Continue your current learning path",
            }
        ], "the row is get_learning_context's dict — attribute access here crashed on activation"

    def test_practice_reads_the_task_dict(self) -> None:
        actions = ResponseGenerator().generate_suggested_actions(
            "how do I actually apply this in daily life",
            {"related_tasks": [{"uid": "task_abc123", "title": "Practice", "status": "active"}]},
            QueryIntent.PRACTICE,
        )

        assert actions == [
            {
                "action": "complete_task",
                "target": "task_abc123",
                "description": "Apply knowledge through practical task",
            }
        ]

    def test_empty_context_yields_no_actions(self) -> None:
        actions = ResponseGenerator().generate_suggested_actions(
            "what should I learn next", {}, QueryIntent.HIERARCHICAL
        )

        assert actions == []

    @pytest.mark.parametrize("intent", _NON_ACTION_INTENTS, ids=_intent_value)
    def test_every_other_intent_yields_no_actions(self, intent: QueryIntent) -> None:
        """Exhaustive complement (Kody, #1208): every non-action-bearing intent —
        including any future member, since the set is derived from the enum —
        returns no actions even when both action sources are populated."""
        actions = ResponseGenerator().generate_suggested_actions(
            "any question", _FULL_CONTEXT, intent
        )

        assert actions == []
