"""The hub methods' questions — the vocabulary of the Insights cards.

``UserContextIntelligence`` (``core/services/user/intelligence/``) answers nine
questions for one user from a ``RichUserContext``. Six of them answer on an
Insights card today, each loaded by an HTMX fragment whose route segment is the
member's value; this enum is the one list the section renders from and the
route dispatches on, so a card and its door cannot drift apart.

Not members: the daily plan (method 5) has its own door (``/api/context/next-action``
and the Today surface); "where can I apply this" (method 3) answers on the Ku
detail page, a question about one Ku rather than the user; the critical path
(method 2) waits on the learning-path walk (``_HUB_CRITICAL_PATH`` in
``scripts/detect_bloat.py``) and is a staged note on the section, not a card.
"""

from enum import StrEnum


class HubQuestion(StrEnum):
    """A hub method that answers on an Insights card; the value is its route segment."""

    LEARN_NEXT = "learn-next"
    UNBLOCK_FIRST = "unblock-first"
    SYNERGIES = "synergies"
    ALIGNMENT = "alignment"
    RIGHT_NOW = "right-now"
    PERCEPTION = "perception"

    def number(self) -> int:
        """The hub method's number in the nine-method catalog."""
        return {
            HubQuestion.LEARN_NEXT: 1,
            HubQuestion.UNBLOCK_FIRST: 4,
            HubQuestion.SYNERGIES: 6,
            HubQuestion.ALIGNMENT: 7,
            HubQuestion.RIGHT_NOW: 8,
            HubQuestion.PERCEPTION: 9,
        }[self]

    def label(self) -> str:
        """The question as the card asks it."""
        return {
            HubQuestion.LEARN_NEXT: "What should I learn next?",
            HubQuestion.UNBLOCK_FIRST: "What unlocks the most?",
            HubQuestion.SYNERGIES: "What helps many things at once?",
            HubQuestion.ALIGNMENT: "Am I living toward my life path?",
            HubQuestion.RIGHT_NOW: "What fits right now?",
            HubQuestion.PERCEPTION: "How well do I know myself?",
        }[self]

    def fragment_url(self) -> str:
        """The HTMX fragment that answers this question."""
        return f"/insights/hub/{self.value}"

    def mount_id(self) -> str:
        """The element id the fragment swaps into, on the section and on the card."""
        return f"hub-{self.value}"


__all__ = ["HubQuestion"]
