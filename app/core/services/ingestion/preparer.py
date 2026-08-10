"""
Ingestion Preparer - Entity Data Preparation
=============================================

Handles UID generation, content extraction, default injection, and
relationship data flattening. One synchronous path serves both ingest doors
(single-file and batch).

Ingestion never embeds inline (ADR-074): embedding generation is event-driven
— the post-persist step in UnifiedIngestionService publishes
``*EmbeddingRequested`` events for the entity types whose
``ENTITY_CONFIGS.embeddable`` flag is set, and the background worker embeds
asynchronously.

Extracted from unified_ingestion_service.py for separation of concerns.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

from core.models.enum_field_registry import ENUM_FIELD_TYPES
from core.models.enums.entity_enums import EntityType, NonKuDomain
from core.models.type_hints import TypeConverter, UserUID
from core.utils.logging import get_logger

from .config import DEFAULT_USER_UID, ENTITY_CONFIGS
from .moc_links import extract_moc_link_suffixes

logger = get_logger("skuel.ingestion.preparer")


def normalize_uid(uid: str) -> str:
    """
    Normalize UID to dot notation.

    Converts colon notation to dot notation:
        "ku:machine-learning" -> "ku.machine-learning"

    Args:
        uid: Raw UID from file

    Returns:
        Normalized UID with dot notation
    """
    return uid.replace(":", ".")


def generate_uid(entity_type: EntityType | NonKuDomain, file_path: Path) -> str:
    """
    Generate UID from entity type and file path.

    Pattern: {uid_prefix}.{file_stem}

    Uses uid_prefix from ENTITY_CONFIGS (e.g., "ku" for CURRICULUM, not "curriculum").
    This preserves stable UID formats regardless of enum value changes.

    Args:
        entity_type: EntityType | NonKuDomain enum value
        file_path: Path to the file

    Returns:
        Generated UID (e.g., "ku.machine-learning")
    """
    from core.services.ingestion.config import ENTITY_CONFIGS

    config = ENTITY_CONFIGS.get(entity_type)
    prefix = config.uid_prefix if config else entity_type.value
    return f"{prefix}.{file_path.stem}"


def canonicalize_enum_values(entity_data: dict[str, Any]) -> None:
    """
    Canonicalize authored enum values in place — the write-door mirror of the
    ``parse_enum_field`` read tolerances (#513, #536).

    Exact-match property filters (the faceted ``sel_category`` facet) compare
    raw strings, so only canonical member values may reach the graph. For
    every registered enum-valued field, in order:

    - a canonical member value is left untouched;
    - a value whose only problem is casing is lowercased (also how an enum
      WITH a "NONE" member accepts that spelling);
    - a value the enum's own alias-aware boundary parser (``from_string``)
      resolves is rewritten to the parsed member's value — e.g.
      ``status: pending`` → ``draft``; aliases are input-only, the graph
      always stores canonical (ENUM_ARCHITECTURE emission rule);
    - the authored absence marker ``none`` (any casing, on an enum with no
      such member) becomes ``None`` — deliberately-unassigned is VALID (the
      rawness principle, PR #536), and a null map value removes the property
      at the bulk upsert, so a re-sync also cleans a previously-persisted
      ``"none"`` string;
    - anything else falls through to ``validate_entity_data``'s vocabulary
      gate (same registry), which rejects the file — an unsanctioned value
      never reaches the graph.
    """
    for field_name, enum_cls in ENUM_FIELD_TYPES.items():
        value = entity_data.get(field_name)
        if not isinstance(value, str):
            continue
        member_values = {member.value for member in enum_cls}
        if value in member_values:
            continue
        lowered = value.lower()
        if lowered in member_values:
            entity_data[field_name] = lowered
            continue
        # SKUEL011: getattr, not hasattr — only some registered enums define
        # the alias-aware boundary parser (EntityStatus, EntityType, Domain).
        parser = getattr(enum_cls, "from_string", None)
        if callable(parser):
            parsed = parser(value)
            if isinstance(parsed, enum_cls):
                entity_data[field_name] = parsed.value
                continue
        if lowered == "none":
            entity_data[field_name] = None


def prepare_entity_data(
    entity_type: EntityType | NonKuDomain,
    data: dict[str, Any],
    body: str | None,
    file_path: Path,
    default_user_uid: UserUID = DEFAULT_USER_UID,
    *,
    owner_is_authoritative: bool = False,
) -> dict[str, Any]:
    """
    Prepare parsed file data for persistence — the one path for both ingest doors.

    Handles:
    - UID generation/normalization
    - Content extraction (body for MD)
    - Default value injection
    - Relationship data flattening
    - Timestamp injection

    Args:
        entity_type: EntityType | NonKuDomain enum value
        data: Parsed frontmatter/YAML data
        body: Body content (for markdown) or None
        file_path: Source file path
        default_user_uid: Default user UID for multi-tenant entities
        owner_is_authoritative: When True (descriptor-governed ingestion), the
            vault-resolved owner overrides any file-supplied ``user_uid``.

    Returns:
        Prepared entity data dict

    Raises:
        ValueError: If entity type is unknown
    """
    config = ENTITY_CONFIGS.get(entity_type)
    if not config:
        raise ValueError(f"Unknown entity type: {entity_type.value}")

    # Start with data copy
    entity_data = dict(data)

    # Remove YAML-only metadata fields. ``created_at`` is deliberately NOT here:
    # an authored creation date is content, not sync bookkeeping, and stripping it
    # made it unauthorable. ``updated_at`` IS stripped — it always means "when this
    # sync ran", which the write layer stamps.
    for field in ("version", "type", "updated_at"):
        entity_data.pop(field, None)

    # Inject entity_type property for Entity-labeled nodes.
    # The YAML "type" field was just stripped; entity_type must be set as a node
    # property so queries filtering by n.entity_type find ingested nodes the same
    # way they find nodes created via the CRUD path (where Entity.entity_type is
    # serialized automatically). NonKuDomain types (Finance/Expense) don't carry
    # entity_type — they have no :Entity base label.
    if isinstance(entity_type, EntityType):
        entity_data["entity_type"] = entity_type.value

    # Handle UID. An empty ``uid:`` line (YAML → None or "") must NOT silently
    # fall back to a generated UID — the author started declaring an identity;
    # guessing one behind their back invites split identities on the fix-up
    # sync. Fail with the reason instead (the batch door classifies this as
    # ignored-with-reason, not a sync error). Non-string values (``uid: 5``)
    # are stringified rather than crashing normalize_uid.
    if "uid" in entity_data:
        raw_uid = entity_data["uid"]
        if raw_uid is None or not str(raw_uid).strip():
            raise ValueError(
                "'uid:' field is present but empty — fill it in "
                "(e.g. 'uid: ku:my-concept') or remove the line to auto-generate "
                "from the filename"
            )
        entity_data["uid"] = normalize_uid(str(raw_uid))
    else:
        entity_data["uid"] = generate_uid(entity_type, file_path)

    # Handle content for markdown files (type-safe check).
    # Only set body content if it's non-empty — an empty body means all content
    # is in the frontmatter (e.g. content: | in the YAML), and overwriting with ""
    # would erase the frontmatter-provided content before chunking.
    if body and config.extracts_body_content:
        entity_data["content"] = body

    # MOC edge pass (parse half): ``moc: true`` on ANY ingestible file turns
    # its body links into ordered ORGANIZES edges post-persist. The extracted
    # suffixes ride the transient ``_moc_links`` key — both ingest doors pop it
    # before node persistence (it must never become a node property; the plain
    # ``moc`` field itself flows through as an inert, human-visible property).
    # An empty body yields [] so an emptied MOC still drops its stale edges.
    if data.get("moc") is True:
        entity_data["_moc_links"] = extract_moc_link_suffixes(body)

    # Singular → plural consolidation (runs first; normalization pass follows)
    for singular_field, plural_field in config.uid_singular_to_plural_fields:
        single_uid = entity_data.pop(singular_field, None)
        if single_uid:
            normalized = normalize_uid(single_uid)
            existing = [normalize_uid(u) for u in entity_data.get(plural_field, [])]
            if normalized not in existing:
                entity_data.setdefault(plural_field, []).insert(0, normalized)

    # List UID normalization
    for field in config.uid_normalization_fields:
        if field in entity_data and isinstance(entity_data[field], list):
            entity_data[field] = [normalize_uid(uid) for uid in entity_data[field]]

    name_field = config.primary_name_field
    alt_field = "name" if name_field == "title" else "title"
    if alt_field in entity_data and name_field not in entity_data:
        entity_data[name_field] = entity_data.pop(alt_field)
    if name_field not in entity_data:
        entity_data[name_field] = file_path.stem.replace("-", " ").title()

    # Apply default values
    if config.default_values:
        for key, value in config.default_values.items():
            if key not in entity_data:
                entity_data[key] = value

    # Canonicalize authored enum values (the enum sibling of normalize_uid's
    # colon→dot rewrite — "plain English in, working code out")
    canonicalize_enum_values(entity_data)

    # Stamp the owner for multi-tenant entity types. When ``owner_is_authoritative``
    # (descriptor-governed ingestion), the vault-resolved owner WINS over any
    # file-supplied ``user_uid`` — otherwise a personal-vault file could claim
    # ``user_uid: someone_else`` and spoof ownership, bypassing the
    # surface-independent model. When not governed (tests / minimal composes), the
    # legacy default-only behavior stands (explicit ``user_uid`` preserved). Route
    # through to_user_uid so a non-canonical owner can never be persisted — the
    # validator rejects bad explicit values earlier; this is the storage-side
    # last line of defense.
    if config.requires_user_uid:
        raw_user_uid = (
            default_user_uid
            if owner_is_authoritative
            else entity_data.get("user_uid", default_user_uid)
        )
        entity_data["user_uid"] = TypeConverter.to_user_uid(str(raw_user_uid))

    if config.owner_uid_from_user_uid:
        owner_uid = entity_data.pop("owner_uid", None) or entity_data.pop("user_uid", None)
        if owner_uid:
            entity_data["owner_uid"] = owner_uid

    # Flatten relationship data for the bulk-upsert backend
    # Format: "connections.requires" -> flat key in metadata
    # Target UIDs must be normalized (colon -> dot) to match stored UIDs
    connections = entity_data.pop("connections", {})
    if connections:
        for key, value in connections.items():
            if value:
                if isinstance(value, list):
                    value = [normalize_uid(v) if isinstance(v, str) else v for v in value]
                elif isinstance(value, str):
                    value = normalize_uid(value)
                entity_data[f"connections.{key}"] = value

    # Flatten contains/recommends for organizing KUs
    contains = entity_data.pop("contains", {})
    if contains:
        for key, value in contains.items():
            if value:
                entity_data[f"contains.{key}"] = value

    recommends = entity_data.pop("recommends", {})
    if recommends:
        for key, value in recommends.items():
            if value:
                entity_data[f"recommends.{key}"] = value

    # Add timestamps. ``created_at`` is stamped ONLY by the write layer's
    # ``ON CREATE`` branch — stamping "now" here put it inside ``props``, so the
    # upsert's ``ON MATCH SET n += props`` overwrote the real creation date on
    # every re-sync (one ``--force`` run reset the whole corpus). An AUTHORED
    # created_at survives from frontmatter and deliberately wins.
    entity_data["updated_at"] = datetime.now().isoformat()

    return entity_data


def prepare_edge_data(
    data: dict[str, Any],
    file_path: Path | None = None,
) -> dict[str, Any]:
    """
    Prepare edge data for ingestion into Neo4j.

    Normalizes from/to UIDs and extracts evidence properties.

    Args:
        data: Parsed edge YAML data (already validated)
        file_path: Optional source file path for provenance

    Returns:
        Dict with from_uid, to_uid, relationship, and evidence properties
    """
    now = datetime.now().isoformat()

    edge_data: dict[str, Any] = {
        "from_uid": normalize_uid(data["from"]),
        "to_uid": normalize_uid(data["to"]),
        "relationship": data["relationship"],
    }

    # Evidence properties (stored on the relationship edge)
    props: dict[str, Any] = {
        "created_at": now,
        "updated_at": now,
    }

    # Optional evidence fields (+ locator: free-string citation anchor on
    # CITES_RESOURCE, e.g. "ch. 4", "pp. 210-214", "12:30", "sailboat metaphor")
    for field in (
        "evidence",
        "confidence",
        "polarity",
        "temporality",
        "source",
        "observed_at",
        "locator",
    ):
        if field in data and data[field] is not None:
            props[field] = data[field]

    if "tags" in data and isinstance(data["tags"], list):
        props["tags"] = data["tags"]

    if file_path:
        props["source_file"] = str(file_path)

    edge_data["properties"] = props
    return edge_data


__all__ = [
    "canonicalize_enum_values",
    "generate_uid",
    "normalize_uid",
    "prepare_edge_data",
    "prepare_entity_data",
]
