# skuel-lint: disable-file=SKUEL005 -- soft-enhancement helpers, deliberately infallible: degrade to [] (module docstring); JournalService adds the Result wrapper at the service contract layer
"""Shared grounding for the LLM DSL bridge.

Grounding is recognition-only: the titles of the user's active goals go to the
bridge so prose is recognised against the goals the user actually holds, and
recognition is all that comes back. A goal link on the bridge paths has one
source, the user's own ``@link(goal:<uid>)`` — the bridge output carries no
``@link`` (``LLMDSLBridgeService._parse_llm_output`` drops any the model
emits). Ruled 2026-09-02; ADR-069 § Decision 1.1 holds the record.

Both bridge entry points ground ``transform_with_context`` through this one
builder, so they can never drift to different grounding:

- the inert journal "Suggested activities" panel (``JournalService``), and
- the entity-creating ``Pipeline.EXTRACT_ACTIVITIES`` extractor
  (``UserEntryProcessingService``).

Grounding is a soft signal: a missing service or a goals-query failure degrades
to no grounding (empty list), never an error — the bridge enhances, never gates.
Principles / recent-topics grounding is registered work:
``docs/roadmap/deferred-work.md`` § DSL-Bridge Grounding.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.models.type_hints import UserUID

if TYPE_CHECKING:
    from core.services.goals_service import GoalsService

# ``get_active`` filters terminal states (completed/cancelled/archived); the
# bridge labels this block "active goals", so stale goals must not leak in
# (``get_user_goals`` would return all). Mirrors the cap used by the suggestion
# path's cache-keying snapshot.
_GROUNDING_GOAL_LIMIT = 10


async def active_goal_titles(goals_service: GoalsService | None, user_uid: UserUID) -> list[str]:
    """Titles of the user's active goals — the grounding fed to the DSL bridge.

    Returns an empty list (never an error) when no goals service is wired or the
    query fails: grounding is a soft enhancement, so a goals-side problem must
    degrade to ungrounded recognition rather than break the bridge pass.

    Backend: GoalsService.get_active.
    """
    if goals_service is None:
        return []
    goals_result = await goals_service.get_active(user_uid, limit=_GROUNDING_GOAL_LIMIT)
    if goals_result.is_error:
        return []
    return [g.title for g in goals_result.value or []]


def goals_as_context(titles: list[str]) -> list[dict[str, str]] | None:
    """Shape active-goal titles into the ``active_goals`` arg of the bridge.

    ``transform_with_context`` reads each entry's ``"title"`` key. Returns
    ``None`` (not an empty list) when there are no titles so the bridge skips
    the context block entirely.
    """
    return [{"title": t} for t in titles] or None


__all__ = ["active_goal_titles", "goals_as_context"]
