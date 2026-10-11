"""A follow-up's history fits its budget and keeps both ends of the conversation.

``render_follow_up_context`` rebuilds the conversation before the last answer
for ``run_follow_up``. Over the budget it keeps the opening turn and the
newest turns — the message that prompted the last answer is never the part
that is lost — with a marker where the middle was left out.
"""

from __future__ import annotations

from core.constants import PromptInput
from core.models.conversation import ROLE_ASSISTANT, ROLE_USER
from core.services.conversation.transcript_codec import (
    HISTORY_OMISSION,
    render_follow_up_context,
)

#: Words and sentences, so a cut has boundaries to find.
LONG = ("A sentence of ordinary words that runs on. " * 1200)[:50_000]


def _conversation() -> list[tuple[str, str]]:
    return [
        (ROLE_USER, "OPENING note about the week."),
        (ROLE_ASSISTANT, LONG),
        (ROLE_USER, "MIDDLE question."),
        (ROLE_ASSISTANT, "A middle answer."),
        (ROLE_USER, "NEWEST question that prompted the last answer."),
        (ROLE_ASSISTANT, "The last answer."),
    ]


def test_a_history_within_the_budget_is_rendered_whole() -> None:
    items = [
        (ROLE_USER, "Hello."),
        (ROLE_ASSISTANT, "Hi."),
        (ROLE_USER, "More."),
        (ROLE_ASSISTANT, "Ok."),
    ]

    history, last = render_follow_up_context(items)

    assert history == "# You\n\nHello.\n\n# Journal\n\nHi.\n\n# You\n\nMore."
    assert last == "Ok."


def test_an_over_budget_history_keeps_the_opening_and_the_newest_turns() -> None:
    history, last = render_follow_up_context(_conversation())

    assert len(history) <= PromptInput.DOCUMENT_MAX_CHARS
    assert history.startswith("# You\n\nOPENING note")
    assert history.endswith("# You\n\nNEWEST question that prompted the last answer.")
    assert "MIDDLE question." in history
    assert HISTORY_OMISSION in history
    assert LONG not in history
    assert last == "The last answer."


def test_a_newest_turn_over_the_budget_rides_cut() -> None:
    items = [
        (ROLE_USER, "OPENING note."),
        (ROLE_ASSISTANT, "An answer."),
        (ROLE_USER, LONG),
        (ROLE_ASSISTANT, "The last answer."),
    ]

    history, _ = render_follow_up_context(items)

    assert len(history) <= PromptInput.DOCUMENT_MAX_CHARS
    assert history.startswith("# You\n\nOPENING note.")
    assert "# You\n\nA sentence of ordinary words" in history
    assert history.endswith("...")


def test_a_single_long_turn_is_cut_to_the_budget() -> None:
    history, _ = render_follow_up_context([(ROLE_USER, LONG), (ROLE_ASSISTANT, "Ok.")])

    assert len(history) <= PromptInput.DOCUMENT_MAX_CHARS
    assert history.startswith("# You\n\nA sentence")
    assert HISTORY_OMISSION not in history
