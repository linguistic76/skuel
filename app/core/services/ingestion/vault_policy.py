"""
Vault Policy — what a vault file may write, by the kind of vault it lives in
=============================================================================

A personal vault belongs to one user, so what a file in it can say is narrower
than what the content vault can (ADR-070 Decision 11, ruled 2026-10-01):

- **What it may hold.** A personal vault ingests the six Activity types, the
  user's ``life_path`` and ``user_entry`` notes (journals, fulfilled assignments,
  knowledge notes). An Edge file, a Group file and every curriculum type belong
  to the content vault and are refused — reported as ignored-with-reason, never
  half-written.
- **Whose identity it has.** A uid-less personal Activity or life-path file mints
  its own uid on its first sync (``task_{slug}_{random}``, the API's form) and keeps
  it through its tracker row, so two users with the same filename hold two
  entities and a rename keeps the entity. The content vault keeps
  ``{prefix}.{file stem}``. ``user_entry`` has its own path-keyed identity
  (``UnifiedIngestionService._resolve_prior_user_entry_uid``).
- **What it may link.** A personal file's frontmatter targets are its owner's or
  unowned content — the link-edge guard's rule (``partition_link_edges``), applied
  before the node lands so no foreign uid reaches a property either. A refused
  target is reported exactly as a missing one.

Two rules hold for every vault and live where the write is: the node upsert never
changes a node's owner (``bulk_upsert_backend.build_node_upsert_template``), and an
Edge file joins two entities (``IngestionWriteBackend.ingest_edge``).

See: /docs/decisions/ADR-070-bidirectional-vault-bridge.md,
     /docs/decisions/ADR-085-ownership-read-enforcement-contract.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from core.models.enums.entity_enums import EntityType, NonKuDomain
from core.services.mixins.link_edge_guard import LinkEdge, partition_link_edges
from core.services.vault.vault_descriptor import VaultKind
from core.utils.result_simplified import Result
from core.utils.uid_generator import UIDGenerator

from .config import ENTITY_CONFIGS
from .detector import detect_entity_type, is_edge_type, read_document

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from core.ingestion.ingestion_types import RelationshipConfig
    from core.ports.ingestion_protocols import IngestionWriteOperations

    from .ingestion_tracker import IngestionTracker

# The six Activity types plus the user's own life path and notes — derived from the
# enum's activity trait, so a seventh Activity type is personal by construction.
PERSONAL_VAULT_TYPES: Final[frozenset[EntityType]] = frozenset(
    {member for member in EntityType if member.is_activity()}
    | {EntityType.USER_ENTRY, EntityType.LIFE_PATH}
)

# The personal types a uid-less file mints its own identity for. ``user_entry`` is
# not one: its notes already take a path-keyed identity through their own door.
MINTED_IDENTITY_TYPES: Final[frozenset[EntityType]] = PERSONAL_VAULT_TYPES - {EntityType.USER_ENTRY}

_PERSONAL_TYPE_NAMES: Final = ", ".join(sorted(member.value for member in PERSONAL_VAULT_TYPES))


def personal_vault_refusal(
    entity_type: EntityType | NonKuDomain | None, data: Mapping[str, Any]
) -> str | None:
    """Why a personal vault refuses this file, or ``None`` when it ingests it.

    ``entity_type`` is ``None`` for an Edge file. ``data`` is the file's parsed
    frontmatter — read only to name a typeless ``moc: true`` map, which the
    detector types as a PathStep, so its author learns how to keep it personal.
    """
    if entity_type is None:
        return (
            "Edge files are synced from the content vault only — link your own "
            "entities with a 'connections:' line in a file's frontmatter"
        )
    if entity_type in PERSONAL_VAULT_TYPES:
        return None
    if entity_type is NonKuDomain.GROUP:
        return "Group files are synced from the content vault only"
    if entity_type is EntityType.PATH_STEP and not data.get("type") and data.get("moc") is True:
        return (
            "a 'moc: true' file with no type is a PathStep, which is curriculum — "
            "for a personal map add 'type: user_entry' and 'pipeline: knowledge'"
        )
    return (
        f"'type: {entity_type.value}' is synced from the content vault only — a "
        f"personal vault syncs {_PERSONAL_TYPE_NAMES} files"
    )


def vault_refusal(
    kind: VaultKind | None,
    entity_type: EntityType | NonKuDomain | None,
    data: Mapping[str, Any],
) -> str | None:
    """Why the vault of ``kind`` refuses this file, or ``None``.

    ``kind`` is ``None`` when no vault governs the path (a minimal compose, a
    script outside every root): nothing is refused by kind there, as nothing is
    attributed by kind there either. The content vault refuses no type.
    """
    if kind is VaultKind.PERSONAL:
        return personal_vault_refusal(entity_type, data)
    return None


def file_vault_refusal(file_path: Path, kind: VaultKind | None) -> str | None:
    """``vault_refusal`` for a file on disk — the sync preview's reading of it.

    Reads the file the way the ingest gate does. A file that does not parse, has
    no type, or has an unknown one is not refused BY KIND — the sync reports those
    faults itself — so this returns ``None`` for them.
    """
    if kind is not VaultKind.PERSONAL:
        return None
    data = read_document(file_path)
    if data is None:
        return None
    if is_edge_type(data):
        return vault_refusal(kind, None, data)
    try:
        entity_type = detect_entity_type(data, file_path)
    except ValueError:
        return None
    return vault_refusal(kind, entity_type, data)


def uid_in_use_reason(uid: str) -> str:
    """The refusal for a file whose uid names a node this vault cannot write.

    One sentence for every vault and every case — it never says whose node it is.
    """
    return (
        f"uid '{uid}' is already in use by an entity this vault does not own — give the "
        "file its own 'uid:', or remove the line"
    )


def missing_target_warning(source_uid: str, target_uid: str) -> str:
    """The warning for a frontmatter target that draws no edge.

    The same words whether the target names nothing, the wrong kind of entity, or
    another user's entity — so the warning never confirms that a uid exists.
    """
    return f"{source_uid}: relationship target '{target_uid}' does not exist — edge not created"


# ---------------------------------------------------------------------------
# Per-file identity
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrackedIdentity:
    """A file's tracker row uid, and what that uid names in the graph now.

    ``labels`` is empty when the uid names no node; ``owners`` is every owner the
    node has, in any of the three spellings.
    """

    uid: str
    labels: frozenset[str]
    owners: frozenset[str]


async def read_tracked_identities(
    tracker: IngestionTracker,
    reader: IngestionWriteOperations,
    files: Sequence[Path],
) -> Result[dict[str, TrackedIdentity]]:
    """The tracker's identity for each file, keyed by canonical path.

    A file with no row is absent. Fails closed: a failed read would otherwise mint
    a fresh uid for every file and duplicate each one's entity.
    """
    rows = await tracker.get_ingestion_metadata(list(files))
    if rows.is_error:
        return Result.fail(rows)
    uids = sorted({str(row.entity_uid) for row in rows.value.values()})
    if not uids:
        return Result.ok({})
    labels = await reader.get_node_labels_batch(uids)
    if labels.is_error:
        return Result.fail(labels)
    owners = await reader.get_owner_uids_batch(uids)
    if owners.is_error:
        return Result.fail(owners)
    return Result.ok(
        {
            path: TrackedIdentity(
                uid=str(row.entity_uid),
                labels=frozenset(labels.value.get(str(row.entity_uid), ())),
                owners=frozenset(owners.value.get(str(row.entity_uid), ())),
            )
            for path, row in rows.value.items()
        }
    )


def personal_file_uid(
    entity_type: EntityType,
    file_path: Path,
    owner_uid: str,
    tracked: TrackedIdentity | None,
) -> str:
    """The uid a uid-less personal file takes: its tracked one, or a fresh one.

    The tracked uid is kept only while it still names a node of this type owned by
    this vault's owner alone. Anything else — a row from when the file was another
    type, an Edge file's identity, a node deleted in the app, or a node someone else
    holds — gives the file a fresh identity rather than a borrowed one.
    """
    config = ENTITY_CONFIGS[entity_type]
    if (
        tracked is not None
        and config.entity_label in tracked.labels
        and tracked.owners == frozenset({owner_uid})
    ):
        return tracked.uid
    return str(UIDGenerator.generate_uid(config.uid_prefix, file_path.stem))


# ---------------------------------------------------------------------------
# Frontmatter targets
# ---------------------------------------------------------------------------


def _targets(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(target) for target in value if target]
    return []


# A Task's goal link is one fact held twice — the edge and this column
# (``preparer._reconcile_task_goal_link``) — so a refused goal target clears both.
_TASK_GOAL_FIELD: Final = "connections.fulfills_goal"
_TASK_GOAL_COLUMN: Final = "fulfills_goal_uid"


@dataclass(frozen=True)
class _TargetSite:
    entity: dict[str, Any]
    field_name: str
    target_uid: str


async def admit_frontmatter_targets(
    reader: IngestionWriteOperations,
    *,
    entities: Sequence[tuple[dict[str, Any], Mapping[str, RelationshipConfig]]],
    owner_uid: str,
    pending_labels: Mapping[str, Sequence[str]],
) -> Result[list[str]]:
    """Drop every frontmatter target ``owner_uid`` may not link; return the warnings.

    Each entity is paired with its relationship config. A target is kept when the
    link-edge guard admits it: it names an entity of the field's kind that is the
    owner's or nobody's. ``pending_labels`` names the uids this same sync is about
    to create (their nodes land after this check). Refused targets are removed
    from the entity in place, BEFORE its node and edges are written, so no foreign
    uid reaches an edge — or the property a Task keeps beside its goal edge, which
    is realigned here. Each refusal is warned in the words a missing target is.

    Fails with the read's error; the caller writes nothing on a failure.
    """
    candidates: list[LinkEdge] = []
    sites: dict[int, _TargetSite] = {}
    for entity, rel_config in entities:
        source_uid = str(entity["uid"])
        for field_name, rel_info in rel_config.items():
            for target_uid in _targets(entity.get(field_name)):
                rel_type = str(rel_info["rel_type"])
                edge = (
                    (target_uid, source_uid, rel_type, None)
                    if rel_info.get("direction") == "incoming"
                    else (source_uid, target_uid, rel_type, None)
                )
                candidate = LinkEdge(
                    edge=edge,
                    other_uid=target_uid,
                    allowed_labels=frozenset({str(rel_info["target_label"])}),
                )
                sites[id(candidate)] = _TargetSite(entity, field_name, target_uid)
                candidates.append(candidate)
    if not candidates:
        return Result.ok([])

    partition = await partition_link_edges(
        reader, candidates=candidates, owner_uid=owner_uid, pending_labels=pending_labels
    )
    if partition.is_error:
        return Result.fail(partition)

    warnings: list[str] = []
    for candidate, _reason in partition.value.refused:
        site = sites[id(candidate)]
        remaining = [t for t in _targets(site.entity.get(site.field_name)) if t != site.target_uid]
        site.entity[site.field_name] = remaining
        warnings.append(missing_target_warning(str(site.entity["uid"]), site.target_uid))
        if (
            site.field_name == _TASK_GOAL_FIELD
            and site.entity.get("entity_type") == EntityType.TASK.value
        ):
            site.entity[_TASK_GOAL_COLUMN] = remaining[0] if remaining else None
    return Result.ok(warnings)


__all__ = [
    "MINTED_IDENTITY_TYPES",
    "PERSONAL_VAULT_TYPES",
    "TrackedIdentity",
    "admit_frontmatter_targets",
    "file_vault_refusal",
    "missing_target_warning",
    "personal_file_uid",
    "personal_vault_refusal",
    "read_tracked_identities",
    "uid_in_use_reason",
    "vault_refusal",
]
