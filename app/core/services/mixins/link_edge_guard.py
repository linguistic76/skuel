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
from typing import TYPE_CHECKING, Any, Protocol

from core.models.type_hints import Neo4jProperties
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from collections.abc import Sequence

# (from_uid, to_uid, relationship_type, properties) — the batch writer's tuple.
EdgeTuple = tuple[str, str, str, Neo4jProperties | None]


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
        required_label: Neo4j label the far end must carry (e.g. ``"Habit"``), or None
            where the field legitimately accepts several kinds — a goal's
            ``required_knowledge_uids`` reaches Kus and PathSteps alike, and pinning one
            label there would refuse half of what it is for.
    """

    edge: EdgeTuple
    other_uid: str
    required_label: str | None = None


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

    An edge is kept when BOTH hold:

    - the far end is owned by ``owner_uid``, or is owned by nobody. Ownership is read
      through ``get_owner_uids_batch``, which resolves all three spellings the graph
      uses (``user_uid``, ``owner_uid``, the ``OWNS`` edge); "owned by nobody" means
      shared content — a Ku carries none of the three and must stay linkable.
    - the far end carries ``required_label``, when the write site declared one.

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
    cross_user = 0
    wrong_kind = 0

    for candidate in candidates:
        # An absent owner entry means "owned by nobody" — shared content, allowed.
        if owner_uid not in owners.get(candidate.other_uid, [owner_uid]):
            cross_user += 1
            continue
        if candidate.required_label is not None and candidate.required_label not in labels.get(
            candidate.other_uid, []
        ):
            wrong_kind += 1
            continue
        kept.append(candidate.edge)

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
