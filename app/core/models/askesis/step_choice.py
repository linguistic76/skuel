"""
Step Choice - Which Step in Progress Askesis Guides On
======================================================

``ContextRetriever.choose_path_step`` ranks the learner's steps in progress by
the ADR-059 rule (an engaged step first, else one not engaged) and guides on the
first that reads as a PathStep. A step whose stored properties do not read is no
candidate; the ones the rule would have chosen ahead of the guided step are named
here, so the learner is told which step could not be opened.

See: /docs/decisions/ADR-059-askesis-engagement-alignment.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.pathways.path_step import PathStep
    from core.ports.query_types import RichPathStepItem
    from core.services.ps_engagement.engagement import Engagement


@dataclass(frozen=True)
class ChosenStep:
    """The step Askesis guides on: its rich-context item, read as a PathStep.

    ``engagement`` is the learner's active ``ENGAGED_WITH`` edge to it, None when
    the step is in progress without one.
    """

    item: RichPathStepItem
    path_step: PathStep
    engagement: Engagement | None = None


@dataclass(frozen=True)
class StepChoice:
    """The step chosen, and the steps ranked ahead of it that did not read.

    ``chosen`` is None when no step in progress reads, or none is in progress.
    ``unopened_titles`` holds each passed-over step's stored title in rank order
    (None when it has no readable title).
    """

    chosen: ChosenStep | None = None
    unopened_titles: tuple[str | None, ...] = ()

    def unopened_notice(self) -> str:
        """The sentence that tells the learner which step could not be opened.

        Empty when no step was passed over. It names the step guided on instead,
        or says the answer is not drawn from the step's material.
        """
        count = len(self.unopened_titles)
        if count == 0:
            return ""
        named = [f'"{title}"' for title in self.unopened_titles if title]
        if count == 1:
            which = f"your step {named[0]}" if named else "one of your steps"
        else:
            which = f"{count} of your steps" + (f" ({_join(named)})" if named else "")
        if self.chosen is not None:
            return f"I couldn't open {which} just now, so I'm working from \"{self.chosen.path_step.title}\"."
        material = "its" if count == 1 else "their"
        return f"I couldn't open {which} just now, so this answer isn't drawn from {material} material."


def _join(names: list[str]) -> str:
    """``"A"``, ``"A and B"``, ``"A, B and C"``."""
    if len(names) <= 2:
        return " and ".join(names)
    return f"{', '.join(names[:-1])} and {names[-1]}"
