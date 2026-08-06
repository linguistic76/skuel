"""
Link-Edge Guard
===============

One admission check for create paths that turn request-supplied UIDs into graph
edges (``GoalsCoreService._write_link_edges``, ``HabitsCoreService._write_link_edges``).

A request field like ``linked_goal_uids`` or ``supporting_habit_uids`` is a list of
UIDs the caller chose. Writing them straight into ``create_relationships_batch`` trusts
two things the batch does not check, and both cost something:

WHO owns the other end
    The batch validates labels, never ownership, so one user could link their entity to
    another's — and the reads that follow those edges do not filter by owner. A goal's
    context would hand back the victim's entity title; a victim's principle-alignment
    read (incoming ``EMBODIES_PRINCIPLE``) would pick up the caller's habit.

WHAT KIND the other end is
    The registry validator keys its target-label rule off the SOURCE's domain config, so
    it cannot express "the UIDs in THIS request list are Habits" — and for an edge the
    request supplies the source of (Goals' ``supporting_habit_uids`` writes
    ``(habit)-[:SUPPORTS_GOAL]->(goal)``), it is not even looking at the right end. A
    same-user Goal UID in that list writes an edge that validates and then reports a Goal
    under ``supporting_habits``, corrupting planning and progress context.

Both are properties of the WRITE SITE — the field name is what says "these are habits" —
so this is where they belong, rather than duplicated in each domain service or
approximated in the registry. Both are checked in ONE pair of batched queries.

FAIL-CLOSED: an unreadable owner or label map drops the whole batch rather than writing
it unchecked. The subject entity itself is the caller's own and is never affected — only
its edges are refused.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Protocol

from core.models.enums.neo_labels import NeoLabel
from core.models.type_hints import Neo4jProperties
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from collections.abc import Sequence

# (from_uid, to_uid, relationship_type, properties) — the batch writer's tuple.
EdgeTuple = tuple[str, str, str, Neo4jProperties | None]

# What a "knowledge" link list may point at. Both Goals' ``required_knowledge_uids`` and
# Habits' ``linked_knowledge_uids`` accept either, and the readers bear that out: the
# rich-context query collects a habit's applied knowledge from the target directly when
# it is a Ku, and through ``TRAINS_KU|USES_KU`` when it is a PathStep. Shared here so the
# two lists cannot drift into disagreeing about what knowledge is.
KNOWLEDGE_LABELS: Final = frozenset({NeoLabel.KU.value, NeoLabel.PATH_STEP.value})


class _EndpointReader(Protocol):
    """The two batched backend reads this guard needs."""

    async def get_owner_uids_batch(self, uids: list[str]) -> Result[dict[str, list[str]]]: ...

    async def get_node_labels_batch(self, uids: list[str]) -> Result[dict[str, list[str]]]: ...


@dataclass(frozen=True)
class LinkEdge:
    """One candidate edge, plus what the write site knows about its far end.

    Attributes:
        edge: the tuple handed to ``create_relationships_batch``.
        other_uid: the request-supplied end — NOT always ``edge[1]``, because an
            incoming spec puts the supplied UID in the source position.
        allowed_labels: the kinds this request field accepts, e.g. ``{"Habit"}`` for
            ``supporting_habit_uids`` or ``{"Ku", "PathStep"}`` for a knowledge list.
            A SET rather than one label because some fields legitimately take several
            — and REQUIRED, with no "any kind" default, because an opt-out is the
            escape hatch that lets an arbitrary Entity through the moment a new list
            forgets to declare itself.
    """

    edge: EdgeTuple
    other_uid: str
    allowed_labels: frozenset[str]


# Returns a plain list, not Result[...]: this is a pure filter, not a fallible
# operation. Its one failure mode — an unreadable owner/label map — is ABSORBED into
# the fail-closed contract (refuse everything), so a Result here would never error and
# would put a dead error branch in each of the two call sites.
async def keep_permitted_link_edges(  # skuel-lint: disable=SKUEL005 -- see note above
    backend: _EndpointReader,
    *,
    candidates: Sequence[LinkEdge],
    subject_uid: str,
    owner_uid: str,
    logger: Any,  # boundary: structlog BoundLogger, typed loosely as services do
) -> list[EdgeTuple]:
    """Return the candidate edges whose far end this owner may legitimately link.

    An edge is kept when ALL THREE hold:

    - the far end EXISTS. This matters because ``create_relationships_batch`` is
      all-or-nothing: one stale UID fails the whole batch, and since that failure is
      logged rather than propagated, every valid link in the same request vanishes
      silently while the create reports success. (A labelless node fails the kind
      check below too; the branch is separate so the log names the real cause.)
    - the far end is owned by ``owner_uid``, or is owned by nobody. Ownership is read
      through ``get_owner_uids_batch``, which resolves all three spellings the graph
      uses (``user_uid``, ``owner_uid``, the ``OWNS`` edge); "owned by nobody" means
      shared content — a Ku carries none of the three and must stay linkable.
    - the far end carries one of ``allowed_labels``.

    Args:
        backend: the domain backend (its two batched endpoint reads).
        candidates: edges to admit, each with its far end and expected kind.
        subject_uid: the entity being created — for log messages only.
        owner_uid: the creating user; the far end must be theirs or unowned.
        logger: service logger; refusals are logged, never raised.

    Returns:
        The permitted subset, in the original order. Empty if a lookup failed.
    """
    if not candidates:
        return []

    other_uids = sorted({candidate.other_uid for candidate in candidates})

    owners_result = await backend.get_owner_uids_batch(other_uids)
    if owners_result.is_error:
        logger.warning(
            "Skipping %d link edges for %s: owner lookup failed: %s",
            len(candidates),
            subject_uid,
            owners_result.error,
        )
        return []

    labels_result = await backend.get_node_labels_batch(other_uids)
    if labels_result.is_error:
        logger.warning(
            "Skipping %d link edges for %s: label lookup failed: %s",
            len(candidates),
            subject_uid,
            labels_result.error,
        )
        return []

    owners = owners_result.value
    labels = labels_result.value

    kept: list[EdgeTuple] = []
    missing = 0
    cross_user = 0
    wrong_kind = 0

    for candidate in candidates:
        # An absent LABELS entry means the node does not exist — absence here is
        # existence, unlike the owners map, whose absence legitimately means "owned by
        # nobody". Split from the kind check below, which would also reject a labelless
        # node, only so the log says which of the two it was: "you named something that
        # is gone" and "you named the wrong kind of thing" are different fixes.
        node_labels = labels.get(candidate.other_uid)
        if node_labels is None:
            missing += 1
            continue
        if owner_uid not in owners.get(candidate.other_uid, [owner_uid]):
            cross_user += 1
            continue
        if candidate.allowed_labels.isdisjoint(node_labels):
            wrong_kind += 1
            continue
        kept.append(candidate.edge)

    if missing:
        logger.warning(
            "Dropping %d link edge(s) for %s naming a UID that resolves to no node — "
            "the batch is all-or-nothing, so one stale UID would lose every valid link",
            missing,
            subject_uid,
        )
    if cross_user:
        logger.warning(
            "Refusing %d cross-user link edge(s) for %s (user %s)",
            cross_user,
            subject_uid,
            owner_uid,
        )
    if wrong_kind:
        logger.warning(
            "Refusing %d link edge(s) for %s whose target is the wrong entity kind",
            wrong_kind,
            subject_uid,
        )

    return kept
