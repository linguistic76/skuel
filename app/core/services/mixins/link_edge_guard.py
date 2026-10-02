"""
Link-Edge Guard
===============

One admission rule for every door that turns a request-supplied UID into a graph
edge, in two shapes:

- a CREATE door admits a list of links and drops the ones it may not write — each
  domain's ``_write_link_edges`` goes through ``keep_permitted_link_edges``;
- a LINK door names one far end and is refused when it may not write it —
  ``UnifiedRelationshipService`` admits every edge it writes through
  ``admit_far_ends_for_source``, and a door that links entities it is about to
  create goes through ``admit_far_ends_for_owner``;
- the personal-vault door admits a file's frontmatter targets through
  ``partition_link_edges`` — the create doors' filter with its failure kept, so
  a sync can leave the file unstamped and retry rather than lose its edges.

A request field like ``linked_goal_uids`` or ``knowledge_uid`` is a UID the caller
chose. Writing it straight into ``create_relationships_batch`` trusts two things the
batch does not check, and both cost something:

WHO owns the other end
    The batch validates labels, never ownership, so one user could link their entity to
    another's. The path-aware neighbourhood reader refuses to return across such an edge
    (it ties every node to its center's owner), but an edge is a fact other reads take
    at face value — the Events pages render a linked goal's title, the user context
    carries a linked node's title — and one that joins two users' entities is a wrong
    fact wherever it is read. It is refused here, where it would be written.

WHAT KIND the other end is
    The registry validator keys its target-label rule off the SOURCE's domain config, so
    it cannot express "the UIDs in THIS request list are Habits" — and for an edge the
    request supplies the source of (Goals' ``supporting_habit_uids`` writes
    ``(habit)-[:SUPPORTS_GOAL]->(goal)``), it is not even looking at the right end. A
    same-user Goal UID in that list writes an edge that validates and then reports a Goal
    under ``supporting_habits``, corrupting planning and progress context.

Both are properties of the WRITE SITE — the field name is what says "these are habits" —
so the write site declares the kind (``LinkEdge.allowed_labels`` / ``LinkFarEnd``) and
the rule is applied here, in ONE pair of batched queries.

THE RULE: the far end exists, carries an allowed label, and is owned by nobody (shared
content) or by an owner of the source. A source nobody owns links to shared content only.

FAIL-CLOSED: an unreadable owner or label map writes nothing. A create door drops the
whole batch (its subject entity is the caller's own and is never affected — only its
edges are refused); a link door fails with the read's error.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Protocol

from core.models.enums.neo_labels import NeoLabel
from core.models.type_hints import Neo4jProperties
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

# (from_uid, to_uid, relationship_type, properties) — the batch writer's tuple.
EdgeTuple = tuple[str, str, str, Neo4jProperties | None]

# What a "knowledge" link list may point at: the ATOM only. Every knowledge link list
# on a create request documents itself as KU UIDs, and the substance pipeline fans out
# from the atom — ``KuBackend.increment_substance`` credits whatever uid it names, and
# fans OUT to the PathSteps composing it. It has no inverse, so a PathStep UID would
# credit the PathStep and leave every atom it teaches untouched, while the context reader
# (which DOES expand a PathStep through ``TRAINS_KU|USES_KU``) reported those atoms as
# reinforced. Writing atoms keeps the two halves agreeing, and the fan-out still credits
# the PathStep.
#
# This narrows what the CREATE doors write, not what the readers accept: PathStep-targeted
# knowledge edges from other writers keep resolving as before. No create form offers
# these fields — the forms omit list-typed links by design — so no UI flow narrows.
# Shared so the lists cannot drift into disagreeing about what knowledge is.
KNOWLEDGE_LABELS: Final = frozenset({NeoLabel.KU.value})


@dataclass(frozen=True)
class LinkFarEnd:
    """What a link door accepts at its far end.

    Attributes:
        labels: the kinds the door links to. REQUIRED, with no "any kind" value, for the
            reason ``LinkEdge.allowed_labels`` is.
        resource: the name a refusal answers with (``Errors.not_found(resource, uid)``).
    """

    labels: frozenset[str]
    resource: str


@dataclass(frozen=True)
class AdmittedFarEnds:
    """Proof that a source's far ends passed admission.

    ``UnifiedRelationshipService.admit_far_ends`` returns one; handing it back as a
    write's ``far_end`` writes the edge on that admission, with no second read. A door
    that admits before its first write and links after it uses this, so the link cannot
    fail on an endpoint read once the door has started writing.
    """

    source_uid: str
    far_uids: frozenset[str]

    def covers(self, source_uid: str, far_uid: str) -> bool:
        """Whether this admission is for exactly this link."""
        return source_uid == self.source_uid and far_uid in self.far_uids


KNOWLEDGE_FAR_END: Final = LinkFarEnd(KNOWLEDGE_LABELS, "Ku")
GOAL_FAR_END: Final = LinkFarEnd(frozenset({NeoLabel.GOAL.value}), "Goal")
HABIT_FAR_END: Final = LinkFarEnd(frozenset({NeoLabel.HABIT.value}), "Habit")
PRINCIPLE_FAR_END: Final = LinkFarEnd(frozenset({NeoLabel.PRINCIPLE.value}), "Principle")
CHOICE_FAR_END: Final = LinkFarEnd(frozenset({NeoLabel.CHOICE.value}), "Choice")


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
            ``supporting_habit_uids`` or ``KNOWLEDGE_LABELS`` for a knowledge list.
            A SET rather than one label so a field that takes several kinds can
            declare them all — and REQUIRED, with no "any kind" default, because an
            opt-out is the escape hatch that lets an arbitrary Entity through the
            moment a new list forgets to declare itself.
    """

    edge: EdgeTuple
    other_uid: str
    allowed_labels: frozenset[str]


def _refusal_reason(
    node_labels: Sequence[str] | None,
    far_owners: Sequence[str] | None,
    owner_uids: frozenset[str],
    allowed_labels: frozenset[str],
) -> str | None:
    """Why this far end may not be linked, or ``None`` when it may.

    ``node_labels`` is ``None`` for a UID that resolves to no node — absence in the
    LABELS map is non-existence. ``far_owners`` is ``None`` for a node nobody owns —
    absence in the OWNERS map is shared content. An owned far end needs an owner in
    ``owner_uids``; an empty ``owner_uids`` (a shared source) therefore admits shared
    content only. A labelless node fails the kind check too; the missing branch is
    separate so the reason names the real cause.
    """
    if node_labels is None:
        return "missing"
    if far_owners and owner_uids.isdisjoint(far_owners):
        return "cross_user"
    if allowed_labels.isdisjoint(node_labels):
        return "wrong_kind"
    return None


def _admit(
    *,
    owner_uids: frozenset[str],
    owners: dict[str, list[str]],
    labels: dict[str, list[str]],
    far_uids: Sequence[str],
    far_end: LinkFarEnd,
) -> Result[None]:
    for far_uid in far_uids:
        reason = _refusal_reason(
            labels.get(far_uid), owners.get(far_uid), owner_uids, far_end.labels
        )
        if reason is not None:
            return Result.fail(Errors.not_found(far_end.resource, far_uid, reason=reason))
    return Result.ok(None)


async def admit_far_ends_for_owner(
    backend: _EndpointReader,
    *,
    owner_uid: str,
    far_uids: Sequence[str],
    far_end: LinkFarEnd,
) -> Result[None]:
    """Admit the far ends a door links entities it creates for ``owner_uid`` to.

    Fails with the first refused UID as ``not_found`` — a UID that names nothing,
    another user's node and a node of the wrong kind answer alike (the diagnosis is
    in ``details["reason"]`` only). A failed endpoint read fails with its own error.
    """
    uids = sorted(set(far_uids))
    if not uids:
        return Result.ok(None)
    owners = await backend.get_owner_uids_batch(uids)
    if owners.is_error:
        return Result.fail(owners)
    labels = await backend.get_node_labels_batch(uids)
    if labels.is_error:
        return Result.fail(labels)
    return _admit(
        owner_uids=frozenset({owner_uid}),
        owners=owners.value,
        labels=labels.value,
        far_uids=far_uids,
        far_end=far_end,
    )


async def admit_far_ends_for_source(
    backend: _EndpointReader,
    *,
    source_uid: str,
    source_resource: str,
    far_uids: Sequence[str],
    far_end: LinkFarEnd,
) -> Result[None]:
    """Admit the far ends an existing entity is linked to, its owner read from the node.

    The owner is whoever owns ``source_uid`` in the graph — no caller passes a user, so
    no caller can pass the wrong one. A source nobody owns links to shared content only.
    Refusals answer as in ``admit_far_ends_for_owner``; a source that resolves to no
    node is ``not_found(source_resource)``, and a link from an entity to itself is a
    validation error.
    """
    if not far_uids:
        return Result.ok(None)
    if source_uid in far_uids:
        return Result.fail(
            Errors.validation("An entity cannot be linked to itself", field="target_uid")
        )
    uids = sorted({source_uid, *far_uids})
    owners = await backend.get_owner_uids_batch(uids)
    if owners.is_error:
        return Result.fail(owners)
    labels = await backend.get_node_labels_batch(uids)
    if labels.is_error:
        return Result.fail(labels)
    if source_uid not in labels.value:
        return Result.fail(Errors.not_found(source_resource, source_uid))
    return _admit(
        owner_uids=frozenset(owners.value.get(source_uid, ())),
        owners=owners.value,
        labels=labels.value,
        far_uids=far_uids,
        far_end=far_end,
    )


@dataclass(frozen=True)
class LinkPartition:
    """The candidates a rule admitted, and the ones it refused with the reason.

    ``refused`` pairs each edge with the reason ``_refusal_reason`` gave —
    ``missing``, ``cross_user`` or ``wrong_kind`` — for the caller's log only. A
    caller that reports a refusal to the user reports all three alike, so a uid
    that names another user's node reads exactly as one that names nothing.
    """

    kept: list[LinkEdge] = field(default_factory=list)
    refused: list[tuple[LinkEdge, str]] = field(default_factory=list)


async def partition_link_edges(
    backend: _EndpointReader,
    *,
    candidates: Sequence[LinkEdge],
    owner_uid: str,
    pending_labels: Mapping[str, Sequence[str]] | None = None,
) -> Result[LinkPartition]:
    """Split ``candidates`` into the edges ``owner_uid`` may write and the ones it may not.

    The rule is ``_refusal_reason`` — the far end exists, carries one of the
    candidate's allowed labels, and is owned by ``owner_uid`` or by nobody.

    ``pending_labels`` names far ends the SAME write is about to create for
    ``owner_uid`` (a vault sync's own files, whose nodes land after this check): a
    uid the graph does not hold yet but this map does counts as the owner's, with
    these labels. The graph wins for a uid it already holds — a pending file whose
    uid names another user's node does not make that node the owner's.

    Fails with the read's error when either endpoint read fails — the caller
    decides what fail-closed means for it (``keep_permitted_link_edges`` writes no
    edge; the vault door leaves the file unstamped).
    """
    if not candidates:
        return Result.ok(LinkPartition())
    other_uids = sorted({candidate.other_uid for candidate in candidates})
    owners_result = await backend.get_owner_uids_batch(other_uids)
    if owners_result.is_error:
        return Result.fail(owners_result)
    labels_result = await backend.get_node_labels_batch(other_uids)
    if labels_result.is_error:
        return Result.fail(labels_result)
    owners = dict(owners_result.value)
    labels = dict(labels_result.value)
    for uid, pending in (pending_labels or {}).items():
        if uid not in labels:
            labels[uid] = list(pending)
            owners[uid] = [owner_uid]

    owner_uids = frozenset({owner_uid})
    partition = LinkPartition()
    for candidate in candidates:
        reason = _refusal_reason(
            labels.get(candidate.other_uid),
            owners.get(candidate.other_uid),
            owner_uids,
            candidate.allowed_labels,
        )
        if reason is None:
            partition.kept.append(candidate)
        else:
            partition.refused.append((candidate, reason))
    return Result.ok(partition)


# Returns a plain list, not Result[...]: this is a pure filter, not a fallible
# operation. Its one failure mode — an unreadable owner/label map — is ABSORBED into
# the fail-closed contract (refuse everything), so a Result here would never error and
# would put a dead error branch in every call site.
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

    partition = await partition_link_edges(backend, candidates=candidates, owner_uid=owner_uid)
    if partition.is_error:
        logger.warning(
            "Skipping %d link edges for %s: endpoint lookup failed: %s",
            len(candidates),
            subject_uid,
            partition.error,
        )
        return []

    # Counted apart so the log says which it was: "you named something that is
    # gone" and "you named the wrong kind of thing" are different fixes.
    reasons = [reason for _, reason in partition.value.refused]
    missing = reasons.count("missing")
    cross_user = reasons.count("cross_user")
    wrong_kind = reasons.count("wrong_kind")
    kept = [candidate.edge for candidate in partition.value.kept]

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
