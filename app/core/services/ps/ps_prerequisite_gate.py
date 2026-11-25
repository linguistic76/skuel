"""
Path Step Prerequisite Gate
===========================

A learner undertakes a step only once every prerequisite in its chain is mastered.

A prerequisite is what the step requires through REQUIRES_STEP or REQUIRES_KNOWLEDGE,
directly or through another prerequisite. Met is the learner's MASTERED edge; marking
a prerequisite as read does not meet it. A draft is withheld, and so is a prerequisite
reached only through one: nobody can master what no reader names, so it never blocks.

The gate reads the step's chain through the same read as the PathStep page's
Blocking dependencies and the chain door's ``unmet_count``, at the same depth, so a
step the page shows as ready is a step every door admits.

The gate governs the act of undertaking a step. A step the learner already holds stays
held when a prerequisite is added to it later.

See: /docs/roadmap/done/path-step-prerequisite-gate.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from core.constants import GraphDepth
from core.utils.result_simplified import ErrorContext, Errors, Result

if TYPE_CHECKING:
    from core.ports.curriculum_protocols import PsIntelligenceBackendOperations
    from core.ports.query_types import PsPrerequisiteStatusRow


PREREQUISITE_GATE_DEPTH: Final = GraphDepth.MAXIMUM
"""How many hops of a step's prerequisite chain the gate, the PathStep page and the
chain door's default read. A prerequisite further away does not block."""

PREREQUISITES_UNMET_RULE: Final = "ps_prerequisites_unmet"
"""The ``rule`` of the refusal a door gives when a step's prerequisites are unmet."""


def step_not_found(step_uid: str) -> ErrorContext:
    """The one refusal a learner-state door gives for a uid that is not a published step:
    another kind of node, a draft and nothing at all read as a missing step."""
    return Errors.not_found("PathStep", step_uid)


def prerequisites_unmet(unmet: list[PsPrerequisiteStatusRow]) -> ErrorContext:
    """The refusal naming what the learner masters first, nearest first."""
    titles = [row["title"] for row in unmet]
    named = ", ".join(titles[:3]) + (f" and {len(titles) - 3} more" if len(titles) > 3 else "")
    return Errors.business(
        rule=PREREQUISITES_UNMET_RULE,
        message=f"Master {named} before starting this step.",
        unmet_uids=[row["uid"] for row in unmet],
    )


class PsPrerequisiteGate:
    """Admits a learner to a published step whose prerequisite chain they have mastered."""

    def __init__(self, backend: PsIntelligenceBackendOperations) -> None:
        if backend is None:
            raise ValueError("PsPrerequisiteGate requires the PathStep intelligence backend")
        self._backend = backend

    async def require_published(self, ps_uid: str) -> Result[None]:
        """Ok when the uid names a published step; ``not_found`` of the step otherwise."""
        published = await self._backend.is_published_step(ps_uid)
        if published.is_error:
            return Result.fail(published)
        if not published.value:
            return Result.fail(step_not_found(ps_uid))
        return Result.ok(None)

    async def admit(self, user_uid: str, ps_uid: str) -> Result[None]:
        """Ok when the learner may undertake the step.

        A uid that is not a published step is ``not_found`` of the step, answered before
        its prerequisites: a draft does not tell a learner what it requires. A step with
        an unmet prerequisite is a BUSINESS refusal naming each one.
        """
        published = await self.require_published(ps_uid)
        if published.is_error:
            return published

        statuses = await self._backend.fetch_prerequisite_statuses(
            ps_uid, user_uid, PREREQUISITE_GATE_DEPTH
        )
        if statuses.is_error:
            return Result.fail(statuses)
        unmet = [row for row in statuses.value or [] if not row["completed"]]
        if unmet:
            return Result.fail(prerequisites_unmet(unmet))
        return Result.ok(None)
