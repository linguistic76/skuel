"""
Ingestion Configuration - Entity Configs and Constants
=======================================================

Data-driven configuration for all entity types.
Defines required fields, relationship configs, and ingestion behavior.

Relationship configs are derived from the Relationship Registry
(core/models/relationship_registry.py) — the single source of truth
for all Neo4j edge definitions. See: ADR-026.

The ``generate_ingestion_relationship_config`` translation function lives
here (not in the registry) to keep the model layer free of ingestion concerns.

Extracted from unified_ingestion_service.py for separation of concerns.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from core.constants import SYSTEM_USER_UID
from core.ingestion.ingestion_types import RelationshipConfig
from core.models.enums.entity_enums import EntityStatus, EntityType, NonKuDomain
from core.models.enums.pipeline import JeUse
from core.models.ps_content.content_chunks import (
    DEFAULT_CHUNKING_PARAMS,
    ChunkingParams,
    chunk_version_tag,
)
from core.models.relationship_registry import (
    ENTITY_TYPE_TO_LABEL,
    LABEL_CONFIGS,
    LABEL_TO_DEFAULT_ENTITY_TYPE,
)
from core.models.type_hints import UserUID
from core.utils.frontmatter import parse_frontmatter, split_frontmatter
from core.utils.logging import get_logger

logger = get_logger("skuel.services.ingestion.config")

# ============================================================================
# FILE SIZE LIMITS
# ============================================================================

# Default maximum file size: 10 MB
# Prevents OOM on very large files
DEFAULT_MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

# ============================================================================
# CONCURRENCY LIMITS
# ============================================================================

# Default max concurrent file parsing operations
# Balances parallelism with resource usage (file handles, memory)
DEFAULT_MAX_CONCURRENT_PARSING = 20

# ============================================================================
# REFERENCE CHUNKING (canon reference-book ingest door)
# ============================================================================

# Prose-tuned grain for canon reference books (:ReferenceChunk), distinct from
# the curriculum default (DEFAULT_CHUNKING_PARAMS). Larger windows suit
# long-form prose over lesson bodies. chunk_version_tag() fingerprints only
# max_chunk_size + context_size, so this yields "v1:1000-150" — isolating
# reference-chunk staleness from curriculum chunks ("v1"). Passed explicitly by
# the reference-ingest door; the RESOURCE EntityIngestionConfig stays
# chunk-free (descriptor ingest is not chunked).
REFERENCE_CHUNKING_PARAMS = ChunkingParams(
    min_chunk_size=100, max_chunk_size=1000, context_size=150
)

# ============================================================================
# USER CONFIGURATION
# ============================================================================

# Default user UID for entities without explicit user_uid.
# Configurable via SKUEL_DEFAULT_USER_UID; defaults to the canonical SYSTEM_USER_UID
# (`user_system`). Must stay canonical (`user_<name>`) — the ingestion boundary rejects
# non-canonical owners. See core.constants.SYSTEM_USER_UID.
DEFAULT_USER_UID: UserUID = UserUID(os.environ.get("SKUEL_DEFAULT_USER_UID", SYSTEM_USER_UID))


# ============================================================================
# INGESTION RELATIONSHIP CONFIG GENERATION
# ============================================================================


def generate_ingestion_relationship_config(
    entity_type: EntityType,
) -> dict[str, RelationshipConfig] | None:
    """
    Generate ingestion relationship config from the registry (single source of truth).

    Extracts UnifiedRelationshipDefinitions that have yaml_field_path set,
    filtered by entity_type for disambiguation when multiple EntityTypes share a label.

    Args:
        entity_type: The EntityType to generate config for

    Returns:
        Dict mapping yaml_field_path -> RelationshipConfig, or None if no relationships.
        Each value is a TypedDict with rel_type, target_label, direction.

    See: /docs/decisions/ADR-026-unified-relationship-registry.md
    """
    entity_label = ENTITY_TYPE_TO_LABEL.get(entity_type)
    if not entity_label:
        return None

    config = LABEL_CONFIGS.get(entity_label)
    if not config:
        return None

    default_type = LABEL_TO_DEFAULT_ENTITY_TYPE.get(entity_label)
    result: dict[str, RelationshipConfig] = {}

    for rel in config.relationships:
        if rel.yaml_field_path is None:
            continue

        # Filter by ingestion_entity_type:
        # - If set, only include for that specific EntityType
        # - If None, only include for the default EntityType for the label
        if rel.ingestion_entity_type is not None:
            if rel.ingestion_entity_type != entity_type:
                continue
        elif entity_type != default_type:
            continue

        rel_entry = RelationshipConfig(
            rel_type=rel.relationship.value,
            target_label=rel.target_label,
            direction=rel.direction,  # type: ignore[typeddict-item]  # str validated at definition
        )
        if rel.order_by_property:
            rel_entry["order_property"] = rel.order_by_property
        result[rel.yaml_field_path] = rel_entry

    return result if result else None


# ============================================================================
# ENTITY INGESTION CONFIGURATION
# ============================================================================


@dataclass
class EntityIngestionConfig:
    """Configuration for ingesting a specific entity type."""

    entity_label: str  # Neo4j domain label (e.g., "PathStep", "Task")
    uid_prefix: str  # UID prefix (e.g., "ku", "task")
    relationship_config: dict[str, RelationshipConfig] | None = None
    required_fields: tuple[str, ...] = ()
    default_values: dict[str, Any] | None = None
    requires_user_uid: bool = False  # Whether this entity type needs user_uid for multi-tenancy
    base_label: str | None = (
        "Entity"  # Multi-label base (e.g., :Entity:Task). None for non-Entity types.
    )
    extracts_body_content: bool = False
    # Body → :Content/:ContentChunk subtree (both ingest doors): the body is
    # popped off the entity pre-upsert and chunked post-persist; the entity
    # vector covers frontmatter fields only (ADR-074). Requires
    # extracts_body_content. False → the body stays wherever
    # extracts_body_content put it (e.g. Resource's inline `content`).
    chunks_body_content: bool = False
    # Per-domain chunk-size knobs for the chunking strategy. None → the shared
    # DEFAULT_CHUNKING_PARAMS (ships zero behavior change). A domain that later
    # needs a different grain sets this; chunk_version_tag then isolates its
    # staleness so only that domain re-chunks. Resolved via resolve_chunking_params.
    chunking_params: ChunkingParams | None = None
    primary_name_field: str = "title"
    uid_normalization_fields: tuple[str, ...] = ()
    uid_singular_to_plural_fields: tuple[tuple[str, str], ...] = ()
    owner_uid_from_user_uid: bool = False
    embeddable: bool = False

    def __post_init__(self) -> None:
        # chunks_body_content consumes the `content` key that only
        # extracts_body_content sets — a chunked type without extraction
        # would silently ingest every body as empty (stale-clear path).
        if self.chunks_body_content and not self.extracts_body_content:
            raise ValueError(
                f"{self.entity_label}: chunks_body_content requires extracts_body_content"
            )


# ENTITY_CONFIGS — Ingestion Entity Configuration
#
# 16 configs: 14 of the 25 EntityTypes are file-ingestible, plus the two
# NonKuDomain types (FINANCE, GROUP). Not file-ingestible:
#   - REVISED_EXERCISE: Created via API as part of the feedback loop
#   - FORM_TEMPLATE/FORM_SUBMISSION: Created via API
#   - ENTRY_REPORT/ACTIVITY_REPORT: Created via report generation pipeline
#   - The six Activity Templates: PS-owned, spawned on engagement
# USER_ENTRY is ingestible via ``type: user_entry`` + an explicit ``pipeline:``;
# the legacy ``je_input``/``exercise_submission`` type strings are rejected
# by the detector with a pointer to ADR-054 (no silent aliasing).
#
# NOTE on title vs name: prepare_entity_data renames ``name`` -> ``title``
# (except GROUP), so required_fields must say "title" — requiring "name"
# is unsatisfiable after preparation (2026-06-12 vault-audit bug).
#
# Relationship configs are derived from the Relationship Registry via
# generate_ingestion_relationship_config(). Only entries with yaml_field_path
# set in the registry generate ingestion relationships.
#
# Note: generate_ingestion_relationship_config() takes EntityType.
# NonKuDomain entries (FINANCE, GROUP) have no relationship configs.
#
# See: core/models/relationship_registry.py (single source of truth)
# See: /docs/decisions/ADR-026-unified-relationship-registry.md
ENTITY_CONFIGS: dict[EntityType | NonKuDomain, EntityIngestionConfig] = {
    EntityType.EXERCISE: EntityIngestionConfig(
        entity_label="Exercise",
        uid_prefix="ex",
        required_fields=("title", "instructions"),
        relationship_config=generate_ingestion_relationship_config(EntityType.EXERCISE),
        # File-ingested exercises are shared curriculum content — no user OWNS
        # edge, so PERSONAL/ASSIGNED/ASSESSMENT (all owner- or group-bound) are
        # rejected by validate_entity_data. Absent scope defaults here, NOT to
        # the Exercise model default (PERSONAL), which would silently create an
        # ownerless "personal" exercise no view can surface.
        default_values={"scope": "curriculum"},
        embeddable=True,
    ),
    EntityType.KU: EntityIngestionConfig(
        entity_label="Ku",
        uid_prefix="ku",
        required_fields=("title",),
        relationship_config=generate_ingestion_relationship_config(EntityType.KU),
        uid_normalization_fields=("resource_uids",),
        # Kus carry lesson bodies (stubs → lessons, 2026-07-06): same recipe
        # as PathStep — body popped pre-upsert, chunked to :Content subtree,
        # entity vector stays frontmatter-only (title/summary/description).
        extracts_body_content=True,
        chunks_body_content=True,
        embeddable=True,
    ),
    # Curated reference content (Arc D, ruling 2026-07-03): vault-ingested
    # descriptor files carry the metadata (author, publisher, media_type, ...);
    # raw book texts stay walled on disk (compose.py Resources/ exclusion is a
    # deliberate permanent wall, not a stopgap). Citations point AT resources
    # via `resource_uids:` on PathStep/Ku YAML — Resource itself has no
    # outgoing YAML edges. Descriptor body → `content` (short annotation; the
    # entity embedding covers it via EMBEDDING_FIELD_MAPS — no chunking, which
    # is PATH_STEP-gated).
    EntityType.RESOURCE: EntityIngestionConfig(
        entity_label="Resource",
        uid_prefix="resource",
        required_fields=("title",),
        relationship_config=generate_ingestion_relationship_config(EntityType.RESOURCE),
        extracts_body_content=True,
        embeddable=True,
    ),
    EntityType.TASK: EntityIngestionConfig(
        entity_label="Task",
        uid_prefix="task",
        required_fields=("title",),
        requires_user_uid=True,
        relationship_config=generate_ingestion_relationship_config(EntityType.TASK),
        embeddable=True,
    ),
    EntityType.GOAL: EntityIngestionConfig(
        entity_label="Goal",
        uid_prefix="goal",
        required_fields=("title",),
        requires_user_uid=True,
        relationship_config=generate_ingestion_relationship_config(EntityType.GOAL),
        embeddable=True,
    ),
    EntityType.HABIT: EntityIngestionConfig(
        entity_label="Habit",
        uid_prefix="habit",
        required_fields=("title",),
        requires_user_uid=True,
        relationship_config=generate_ingestion_relationship_config(EntityType.HABIT),
        embeddable=True,
    ),
    EntityType.EVENT: EntityIngestionConfig(
        entity_label="Event",
        uid_prefix="event",
        required_fields=("title",),
        requires_user_uid=True,
        relationship_config=generate_ingestion_relationship_config(EntityType.EVENT),
        embeddable=True,
    ),
    EntityType.CHOICE: EntityIngestionConfig(
        entity_label="Choice",
        uid_prefix="choice",
        required_fields=("title",),
        requires_user_uid=True,
        relationship_config=generate_ingestion_relationship_config(EntityType.CHOICE),
        embeddable=True,
    ),
    EntityType.PRINCIPLE: EntityIngestionConfig(
        entity_label="Principle",
        uid_prefix="principle",
        # "title", not "name": the preparer renames name -> title before the
        # post-prepare validate_entity_data() check, so requiring "name" was
        # unsatisfiable for any file that didn't redundantly carry both.
        required_fields=("title", "statement"),
        requires_user_uid=True,
        relationship_config=generate_ingestion_relationship_config(EntityType.PRINCIPLE),
        embeddable=True,
    ),
    EntityType.LEARNING_PATH: EntityIngestionConfig(
        entity_label="LearningPath",
        uid_prefix="lp",
        # "title", not "name" — same name->title rename constraint as PRINCIPLE.
        required_fields=("title",),
        relationship_config=generate_ingestion_relationship_config(EntityType.LEARNING_PATH),
        embeddable=True,
    ),
    EntityType.PATH_STEP: EntityIngestionConfig(
        entity_label="PathStep",
        uid_prefix="ps",
        required_fields=("title",),
        relationship_config=generate_ingestion_relationship_config(EntityType.PATH_STEP),
        extracts_body_content=True,
        chunks_body_content=True,
        # G17 write side (Arc E): vault PathSteps historically carried NO
        # status, and the MEGA-QUERY active-path filter reads it — stamp an
        # explicit ACTIVE default at ingestion (an authored ``status:`` wins;
        # defaults only fill absent keys). The Arc B NULL-tolerant read stays
        # as the guard for graphs that have not re-synced under this code yet.
        default_values={"status": EntityStatus.ACTIVE.value},
        uid_normalization_fields=(
            "uses_kus",
            "habit_uids",
            "task_uids",
            "event_template_uids",
            "goal_uids",
            "principle_uids",
            "choice_uids",
            "exercise_uids",
            "resource_uids",
            "knowledge_uids",
            "trains_ku_uids",
            "prerequisite_step_uids",
            "prerequisite_knowledge_uids",
            "learning_path_uids",
            # Was missing (latent): a colon-authored ``organizes:`` target kept
            # its colons and the edge MATCH silently missed the dot-stored uid.
            # Also load-bearing for the MOC pass, which spares frontmatter-
            # authored ORGANIZES targets from its stale-edge refresh.
            "organizes",
        ),
        uid_singular_to_plural_fields=(
            ("learning_path_uid", "learning_path_uids"),
            ("knowledge_uid", "knowledge_uids"),
        ),
        embeddable=True,
    ),
    NonKuDomain.FINANCE: EntityIngestionConfig(
        entity_label="Expense",
        uid_prefix="expense",
        required_fields=("description", "amount"),
        requires_user_uid=True,
        base_label=None,  # Expense is not an Entity type
    ),
    NonKuDomain.GROUP: EntityIngestionConfig(
        entity_label="Group",
        uid_prefix="group",
        required_fields=("name",),
        requires_user_uid=True,  # Upload user becomes owner_uid (see preparer)
        base_label=None,  # Group is not an Entity type
        primary_name_field="name",
        owner_uid_from_user_uid=True,
        default_values={"is_active": True},
    ),
    EntityType.USER_ENTRY: EntityIngestionConfig(
        entity_label="UserEntry",
        uid_prefix="ue",
        required_fields=("title",),
        requires_user_uid=True,
        extracts_body_content=True,
    ),
    EntityType.INTERACTION: EntityIngestionConfig(
        entity_label="Interaction",
        uid_prefix="ia",
        required_fields=("interaction_type", "target_uid"),
        requires_user_uid=True,
        # No YAML-driven relationships — context relationships are created
        # programmatically by InteractionService.create_interaction().
    ),
    EntityType.LIFE_PATH: EntityIngestionConfig(
        entity_label="LifePath",
        uid_prefix="lifepath",
        required_fields=("user_uid",),
    ),
}


# ============================================================================
# CHUNKING PARAMETER RESOLUTION
# ============================================================================


def resolve_chunking_params(entity_type: EntityType | NonKuDomain) -> ChunkingParams:
    """Per-domain chunk-size knobs for ``entity_type`` (ingest door).

    Reads the domain's ``EntityIngestionConfig.chunking_params``; falls back to
    the shared ``DEFAULT_CHUNKING_PARAMS`` when the type is unknown or has not
    diverged. Single source of truth so both ingest doors resolve identically.
    """
    cfg = ENTITY_CONFIGS.get(entity_type)
    return cfg.chunking_params if cfg and cfg.chunking_params else DEFAULT_CHUNKING_PARAMS


def resolve_chunking_params_for_label(label: str | None) -> ChunkingParams:
    """Per-domain chunk-size knobs for a Neo4j domain ``label`` (batch door).

    Maps the label to its default EntityType via the relationship registry, then
    defers to ``resolve_chunking_params``. Keeps the registry dependency here so
    the batch-chunking service needs no registry import. Unknown/absent label →
    ``DEFAULT_CHUNKING_PARAMS``.
    """
    entity_type = LABEL_TO_DEFAULT_ENTITY_TYPE.get(label) if label else None
    return resolve_chunking_params(entity_type) if entity_type else DEFAULT_CHUNKING_PARAMS


def clears_inline_body_for_label(label: str | None) -> bool:
    """Batch door: may persisting a re-chunk clear the parent's inline body?

    ``True`` only for ``chunks_body_content`` domains (PathStep, Ku) — their
    body was popped at ingest, so the :Content subtree is THE source of truth
    and a lingering inline ``content`` property is legacy to remove. Every
    other chunked parent (UserEntry — canon P3 additive substrate) keeps
    ``Entity.content`` load-bearing, so a re-chunk must never strip it.
    Unknown/absent label → ``False`` (preserve; never destroy data for a
    parent we can't classify).
    """
    entity_type = LABEL_TO_DEFAULT_ENTITY_TYPE.get(label) if label else None
    cfg = ENTITY_CONFIGS.get(entity_type) if entity_type else None
    return bool(cfg and cfg.chunks_body_content)


def diverged_chunk_version_by_label() -> dict[str, str]:
    """Neo4j domain label → expected chunk-version tag, for domains whose
    ``ChunkingParams`` diverge from the default.

    Feeds the batch-door staleness predicate so candidate *selection* honors the
    same per-domain tag the ingest door stamps. Domains on default params are
    omitted — the backend falls back to the bare ``CHUNKING_ALGORITHM_VERSION``
    for any label not in the map — so today this is empty and batch staleness
    detection is byte-for-byte unchanged (zero churn). When a domain diverges,
    its label maps to the suffixed tag ``chunk_version_tag`` would stamp, so its
    default-tagged chunks read as stale (re-chunk once) and its own-tagged chunks
    read as current (no infinite re-chunk). See [[chunk_version_tag]].
    """
    return {
        cfg.entity_label: chunk_version_tag(cfg.chunking_params)
        for cfg in ENTITY_CONFIGS.values()
        if cfg.chunks_body_content and cfg.chunking_params is not None
    }


# ============================================================================
# FILE COLLECTION
# ============================================================================


# Code-defined "doorway" folders — the SINGLE SOURCE OF TRUTH for what a personal
# vault syncs (no env knob; sourcing this from ambient env let a stale exported var
# shadow .env). The deliberate "what I want SKUEL to know" channel (ADR-073). These
# are the ONLY folders a personal vault syncs; everything else (je_in/je_out/
# je_raw staging, templates, loose notes) stays walled off without any
# configuration, fail-closed. je_pro is a doorway folder but a CONDITIONAL one:
# collection includes it, and the per-file ingestion gate (explicit ``pipeline:``
# frontmatter + compatible ``je_use:``) decides what actually ingests.
_DEFAULT_SYNC_SUBDIRS: tuple[str, ...] = (
    "periodic_notes",
    "personal_notes",
    "activity_notes",
    "knowledge",
    "je_pro",
)

# Pipeline staging folders that are NEVER vault content, in any configuration.
# je_in/je_out/je_raw hold journal transcription artifacts — je_out in
# particular holds generated transcripts that must never auto-sync. These are
# excluded UNCONDITIONALLY at the ingestion chokepoint, beneath and independent of
# the SyncAllowlist privacy wall, so they stay walled even in the single-vault
# fallback where no allowlist is built (build_sync_allowlist → None).
# je_pro is NOT here (ADR-073 amendment): it is a conditional doorway — files
# there ingest only with explicit ``pipeline:`` frontmatter and a compatible
# ``je_use:``; the gate lives in the per-file ingestion path, not the path wall.
STAGING_EXCLUDED_DIRS: frozenset[str] = frozenset({"je_in", "je_out", "je_raw"})


def is_staging_path(path: Path, excluded: frozenset[str] = STAGING_EXCLUDED_DIRS) -> bool:
    """True if any path component names a pipeline staging folder (je_in/je_out/je_raw).

    Component-exact match (``je_output`` does not match ``je_out``), mirroring the
    historical vault-sync exclusion. Keeps staging artifacts out of ingestion on
    every path, independent of the privacy allowlist. je_pro is not staging — it
    is a frontmatter-gated doorway (see ``STAGING_EXCLUDED_DIRS``).
    """
    return any(part in excluded for part in path.parts)


_JE_PRO_DIRNAME = "je_pro"

# Bounded read window for the je_pro consent gate: generous for any real
# frontmatter block, tiny next to the parser's 10 MB file cap — the gate runs
# per-file per-sync and must never load a huge exemplar wholesale.
_JE_PRO_GATE_READ_CHARS = 64 * 1024


def _in_je_pro_scope(path: Path, allowlist: "SyncAllowlist | None") -> bool:
    """Whether the je_pro consent gate applies to ``path``.

    Personal vaults only. With an allowlist, the gate applies inside the
    governed root — and only when the allowlist gates je_pro at all: the
    CONTENT vault's own allowlist sets ``gates_je_pro=False`` (Codex #608),
    so a curriculum folder that happens to be named ``je_pro`` ingests
    normally under its own descriptor — the same posture as paths outside
    a personal wall. Without an allowlist (single-vault fallback)
    the whole vault is personal, so any ``je_pro`` component counts.
    """
    if allowlist is None:
        return _JE_PRO_DIRNAME in path.parts
    if not allowlist.gates_je_pro:
        return False
    located = path.parent.resolve() / path.name
    if not located.is_relative_to(allowlist.governed_root):
        return False
    return _JE_PRO_DIRNAME in located.relative_to(allowlist.governed_root).parts


def je_pro_skip_reason(path: Path) -> str | None:
    """Frontmatter consent verdict for a ``je_pro/`` doorway file (ADR-073).

    je_pro is a CONDITIONAL doorway: placement alone is not consent. A file
    ingests only when its frontmatter declares an explicit ``pipeline:`` AND
    its ``je_use:`` is not exemplar-only. Returns ``None`` when the file may
    ingest, else a human-readable per-file reason for the sync warning surface.

    Because this feeds ``is_ingestible_path`` — the predicate deletion
    reconciliation shares — a stored je_pro entry whose file later loses its
    ``pipeline:`` or flips to ``je_use: exemplar`` reads as not-collectible and
    is retracted on the next sync (consent narrowing is honored).

    An unreadable file is NOT a consent verdict: we defer to the parse-level
    error surface rather than skip, so deletion reconciliation never retracts
    a stored entry over a transient I/O failure.

    The read is BOUNDED (Codex #608): this runs for every je_pro file on every
    sync, before the parser's file-size guard, so a huge exemplar must never be
    fully loaded here. Consent frontmatter lives in the first bytes; a file
    whose frontmatter does not close inside the window cannot legitimately
    carry consent, so it fails closed (with an explicit reason).
    """
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            text = fh.read(_JE_PRO_GATE_READ_CHARS)
    except OSError:
        return None
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            loaded = yaml.safe_load(text)
        except yaml.YAMLError:
            # Includes truncation of an oversized YAML entry — a je_pro YAML
            # that large is pathological; fail closed, the warning says why.
            loaded = None
        data: dict[str, Any] = loaded if isinstance(loaded, dict) else {}
    else:
        if text.startswith("---") and split_frontmatter(text)[0] is None:
            return (
                "frontmatter block does not close within the first "
                f"{_JE_PRO_GATE_READ_CHARS // 1024} KB — consent cannot be read "
                "(fail-closed); fix or shrink the frontmatter"
            )
        data, _ = parse_frontmatter(text)
    raw_pipeline = data.get("pipeline")
    if raw_pipeline is None or not str(raw_pipeline).strip():
        return (
            "no explicit 'pipeline:' frontmatter — the file stays a style "
            "exemplar only; add 'type: user_entry' + 'pipeline: knowledge' "
            "frontmatter (the knowledge/ contract) to promote it into "
            "SKUEL's understanding"
        )
    je_use = JeUse.from_string(data.get("je_use"))
    if je_use is None:
        return (
            f"unrecognized 'je_use: {data.get('je_use')}' — expected one of: "
            f"{', '.join(u.value for u in JeUse)}. Treated as no consent (fail-closed)"
        )
    if je_use is JeUse.EXEMPLAR:
        reason = "'je_use: exemplar' — style exemplar only, never ingested"
        if not _has_je_raw_twin(path):
            # Gentle nudge, not silence: an exemplar-only file with no
            # stem-matched je_raw twin is used in NEITHER direction.
            reason += (
                "; note: no je_raw file shares this stem, so it will not be "
                "used as a style exemplar either until you add its raw twin"
            )
        return reason
    return None


def _has_je_raw_twin(path: Path) -> bool:
    """Whether a je_pro file has a stem-matched je_raw sibling (exemplar pair).

    Mirrors the exemplar loader's pairing rule (filename stem, text
    extensions). Unscannable/absent je_raw reads as no twin.
    """
    parts = path.parts
    if _JE_PRO_DIRNAME not in parts:
        return False
    je_raw_dir = Path(*parts[: parts.index(_JE_PRO_DIRNAME)]) / "je_raw"
    try:
        entries = list(je_raw_dir.iterdir()) if je_raw_dir.is_dir() else []
    except OSError:
        return False
    return any(
        p.stem == path.stem and p.suffix.lower() in {".txt", ".md", ".rst"} and p.is_file()
        for p in entries
    )


@dataclass(frozen=True)
class SyncAllowlist:
    """Fail-closed folder allowlist for vault ingestion.

    Scopes a privacy wall to a single governed vault root (the user's personal
    vault). A file under ``governed_root`` is ingested only when it also sits
    under one of ``allowed_dirs``; every other folder under the root is walled
    off. Files outside ``governed_root`` (e.g. the admin content vault) are
    unaffected, so the same service can ingest a fully-open curriculum vault and
    a fail-closed personal vault.

    Fail-closed: an empty ``allowed_dirs`` walls the *entire* governed root — the
    default posture is "not synced", so a folder created later is silent until it
    is explicitly opted in. ``build_sync_allowlist`` also defaults to a wall (not
    to "open") when the env var is unset, so the fail-closed posture does not
    depend on configuration being present.

    ``permits`` is the single predicate every ingestion path inherits — both the
    directory scan (``collect_files`` → ``VaultReconciler.sync``) and single-file
    ingestion (``ingest_file`` → ``/api/ingest/file``) — so no code path can
    bypass it. ``governed_root`` and
    ``allowed_dirs`` are stored already-resolved (see ``build_sync_allowlist``) so
    the ``permits`` check is purely lexical after a single ``resolve()`` of the
    candidate.
    """

    governed_root: Path
    allowed_dirs: frozenset[Path]
    # Explicit walls *inside* an otherwise-allowed tree. Used for the content
    # vault's raw reference library (``Resources/`` — book texts with no
    # ``type:`` frontmatter): the whole-vault allowlist would sweep them into
    # every sync attempt. Checked before allowed_dirs, so an excluded dir wins
    # even when nested under an allowed one.
    excluded_dirs: frozenset[Path] = frozenset()
    # Whether the je_pro frontmatter consent gate applies inside this governed
    # root. True for personal vaults (the ADR-073 doorway); the CONTENT vault's
    # allowlist sets False so a curriculum folder merely named ``je_pro``
    # ingests normally under its own descriptor (Codex #608).
    gates_je_pro: bool = True

    def permits(self, path: Path) -> bool:
        """Whether ``path`` is allowed by this wall (True = keep).

        Outside the governed root → always permitted (ungoverned tree — e.g. the
        admin content vault, including any folder there that happens to be *named*
        ``je_*``). Inside → walled if it is a ``je_*`` staging folder or sits
        under an ``excluded_dirs`` entry, else permitted only when nested under
        an allowed dir.

        The wall judges a file by *where it sits in the vault*, not where a
        symlink target points: we canonicalize the directory chain
        (``parent.resolve()`` — collapses ``..`` and resolves real vault dirs) but
        keep the leaf name in place. Leaf symlinks are rejected earlier by
        ``is_ingestible_path`` (their target may be external); this method only
        decides allowlist membership.
        """
        located = path.parent.resolve() / path.name
        if not located.is_relative_to(self.governed_root):
            return True
        # Staging floor, scoped to the vault-relative portion so a governed_root
        # prefix component can't false-positive and so it never touches unrelated
        # trees (a content-vault "je_out/" is handled by the branch above).
        if is_staging_path(located.relative_to(self.governed_root)):
            return False
        if any(located.is_relative_to(excluded) for excluded in self.excluded_dirs):
            return False
        return any(located.is_relative_to(allowed) for allowed in self.allowed_dirs)

    def governs(self, directory: Path) -> bool:
        """Whether the wall restricts files under ``directory``.

        True when the scanned tree intersects the governed vault (``directory`` is
        under the vault root, or the vault root is under ``directory``). Used to
        decide when a full-mode ingestion must still reconcile deletions so
        now-walled rows are retracted rather than left searchable.
        """
        resolved = directory.resolve()
        return resolved.is_relative_to(self.governed_root) or self.governed_root.is_relative_to(
            resolved
        )


def build_sync_allowlist(
    governed_root: Path,
    *,
    allowed_dirs: str | None = None,
    content_root: Path | None = None,
    excluded_dirs: frozenset[Path] = frozenset(),
    gates_je_pro: bool = True,
) -> SyncAllowlist:
    """Build the fail-closed vault-sync allowlist for ``governed_root``.

    Always returns a ``SyncAllowlist`` (never ``None``): the ``je_*`` staging
    floor and — when configured — a fail-closed allowlist always apply, and the
    wall must carry the governed root so callers (e.g. the full→smart upgrade) can
    ask ``governs()`` in every configuration.

    ``allowed_dirs`` is an explicit colon-separated list of absolute directories
    under ``governed_root`` — the ONLY folders whose files may be ingested — passed
    in by the caller. This is deliberately **not** read from the ambient process
    environment: a stale exported ``SKUEL_VAULT_SYNC_ALLOWED_DIRS`` used to shadow
    ``.env`` (python-dotenv loads with ``override=False``) and silently wall off a
    folder deep in the call stack. The code-level doorway defaults
    (``_DEFAULT_SYNC_SUBDIRS``) are now the single source of truth for a personal
    vault, so the common case needs no configuration at all.

    - **``allowed_dirs`` set** → allowlist is exactly the listed dirs (``":"`` with
      no real entries is a deliberate "wall everything"). Dirs must be *strictly
      under* the governed root; the root itself, an ancestor, or an unrelated path
      would make every file ``is_relative_to`` it and silently open the vault, so
      such entries are dropped (with a warning) — fail-closed on misconfiguration.
    - **``allowed_dirs`` unset, distinct personal vault** → a minimal wall allowing
      only the default doorway folders (``_DEFAULT_SYNC_SUBDIRS`` under
      ``governed_root`` — periodic/personal/activity notes + knowledge + je_pro),
      so an un-opted-in folder stays private without configuration.
    - **``allowed_dirs`` unset, single-vault** (``content_root`` is / is under the
      governed root) → allow the *whole vault* (``allowed_dirs = {governed_root}``)
      so curriculum still ingests; only the ``je_*`` staging floor (scoped inside
      ``permits``) applies. ``governs()`` is still true here, so full-mode
      reprocesses retract stale staging rows like the routine incremental paths.

    ``gates_je_pro``: pass ``False`` when building the CONTENT vault's own
    allowlist — the je_pro consent gate is a personal-vault concept and must
    not gate a curriculum folder that happens to share the name (Codex #608).
    A combined personal+content root keeps the default (its je_pro IS the
    personal doorway).
    """
    governed = governed_root.resolve()
    resolved_excluded = frozenset(d.resolve() for d in excluded_dirs)
    raw = allowed_dirs
    if raw and raw.strip():
        configured = [Path(p.strip()).resolve() for p in raw.split(":") if p.strip()]
        valid = frozenset(d for d in configured if d.is_relative_to(governed) and d != governed)
        for dropped in (d for d in configured if d not in valid):
            logger.warning(
                "Ignoring allowed-dirs entry %s: not strictly under the "
                "vault root %s. Allow-dirs must be subfolders of the vault; an ancestor or "
                "outside path would defeat the fail-closed wall.",
                dropped,
                governed,
            )
        return SyncAllowlist(
            governed_root=governed,
            allowed_dirs=valid,
            excluded_dirs=resolved_excluded,
            gates_je_pro=gates_je_pro,
        )

    # Var unset. Single-vault (content vault is / is under the governed root):
    # allow the whole vault so curriculum isn't starved — the staging floor still
    # excludes je_* and governs() still holds, so retraction works there too.
    if content_root is not None:
        content = content_root.resolve()
        if content == governed or content.is_relative_to(governed):
            return SyncAllowlist(
                governed_root=governed,
                allowed_dirs=frozenset({governed}),
                excluded_dirs=resolved_excluded,
                gates_je_pro=gates_je_pro,
            )
    # Distinct personal vault: fail-closed default to the doorway folders only.
    return SyncAllowlist(
        governed_root=governed,
        allowed_dirs=frozenset(governed / subdir for subdir in _DEFAULT_SYNC_SUBDIRS),
        excluded_dirs=resolved_excluded,
        gates_je_pro=gates_je_pro,
    )


def is_ingestible_path(path: Path, allowlist: SyncAllowlist | None) -> bool:
    """Whether a vault file is eligible for ingestion under the vault exclusions.

    The single policy predicate every ingestion path shares (``collect_files``,
    ``ingest_file``, and ``reconcile_deletions``), giving the invariant: a tracked
    graph row survives deletion reconciliation iff its file would still be
    collected for ingestion. Does NOT check on-disk existence — ``collect_files``
    globs existing files; ``reconcile_deletions`` checks existence separately.

    Four rules, in order:

    1. **No symlinks.** A symlink's target may resolve outside the vault, so the
       link's in-vault name is not a safe proxy for its content. Rejecting them
       closes both the walled-folder escape (a link out of ``je_raw``) and the
       allowed-folder external read (a link in ``periodic_notes`` whose target is
       read by the parser and sent downstream).
    2. **Allowlist active** → defer to ``permits`` (which applies the ``je_*``
       staging floor scoped to the governed vault, then allowlist membership), so
       an unrelated content tree is unaffected.
    3. **No allowlist** (single-vault fallback — no distinct content tree) → the
       whole vault is personal, so the ``je_*`` staging floor applies globally.
    4. **je_pro consent gate** (``je_pro_skip_reason``): a personal-vault file
       under ``je_pro/`` ingests only with explicit consent frontmatter. Living
       here — in the shared predicate — is what makes consent narrowing work:
       a stored entry whose file withdraws consent reads as not-collectible and
       deletion reconciliation retracts it. This rule reads the file's
       frontmatter (the one content-aware rule); the docstring caveat above
       still holds — a missing file falls through the gate's I/O guard.
    """
    if path.is_symlink():
        return False
    if allowlist is not None:
        if not allowlist.permits(path):
            return False
    elif is_staging_path(path):
        return False
    return not (_in_je_pro_scope(path, allowlist) and je_pro_skip_reason(path) is not None)


def _file_mtime(path: Path) -> float:
    """Get file modification time for sorting."""
    return path.stat().st_mtime


@dataclass(frozen=True)
class FileCollectionSkips:
    """Skip-reason bookkeeping for a directory scan (G10 honest counts).

    ``walled``: files matching the supported patterns that the vault
    exclusions rejected (allowlist wall, je_* staging floor, symlink, or the
    je_pro consent gate).
    ``unsupported``: non-hidden files in the tree whose extension the
    ingestion engine does not read at all (only counted for the recursive
    all-files patterns — a targeted pattern scan makes no claim about the
    rest of the tree).
    ``warnings``: per-file actionable messages for skips the author should
    hear about (today: je_pro files missing consent frontmatter) — merged
    into sync-stats warnings by the batch door so they reach the UI/API.
    """

    walled: int = 0
    unsupported: int = 0
    warnings: tuple[str, ...] = ()


_SUPPORTED_SUFFIXES = frozenset({".md", ".yaml", ".yml"})


def _is_hidden(path: Path, root: Path) -> bool:
    """Whether any path component under ``root`` is dotfile-hidden (.obsidian etc.)."""
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    return any(part.startswith(".") for part in relative.parts)


def collect_files_detailed(
    directory: Path,
    pattern: str = "*",
    allowlist: SyncAllowlist | None = None,
) -> tuple[list[Path], FileCollectionSkips]:
    """``collect_files`` plus skip-reason bookkeeping (G10).

    Same collection semantics; additionally counts what the scan saw but did
    not collect, so sync stats can report walled/unsupported files instead of
    letting them vanish from the totals (#500 residue).
    """
    matched: list[Path] = []

    if pattern in ("*", "**/*"):
        matched.extend(directory.glob("**/*.md"))
        matched.extend(directory.glob("**/*.yaml"))
        matched.extend(directory.glob("**/*.yml"))
    elif pattern.endswith(".md") or pattern.endswith((".yaml", ".yml")):
        matched.extend(directory.glob(f"**/{pattern}"))
    else:
        matched.extend(directory.glob(f"**/{pattern}.md"))
        matched.extend(directory.glob(f"**/{pattern}.yaml"))
        matched.extend(directory.glob(f"**/{pattern}.yml"))

    # Vault exclusions: the always-on je_* staging floor plus the optional
    # fail-closed privacy allowlist. reconcile_deletions applies the SAME predicate
    # so a tracked row survives iff its file would still be collected here.
    collected = [f for f in matched if is_ingestible_path(f, allowlist)]
    walled = sum(1 for f in matched if not _is_hidden(f, directory)) - sum(
        1 for f in collected if not _is_hidden(f, directory)
    )

    # je_pro consent skips get a per-file actionable warning: unlike a walled
    # folder (deliberately silent), a bare je_pro file is one frontmatter line
    # away from ingesting — tell the author how. Only files that passed every
    # PATH wall qualify, so the warning never fires for path-rejected files.
    collected_set = set(collected)
    je_pro_warnings: list[str] = []
    for f in matched:
        if f in collected_set or not _in_je_pro_scope(f, allowlist):
            continue
        if f.is_symlink() or (allowlist is not None and not allowlist.permits(f)):
            continue
        reason = je_pro_skip_reason(f)
        if reason is not None:
            try:
                display = f.relative_to(directory).as_posix()
            except ValueError:
                display = f.name
            je_pro_warnings.append(f"je_pro file skipped ({display}): {reason}")

    unsupported = 0
    if pattern in ("*", "**/*"):
        unsupported = sum(
            1
            for f in directory.glob("**/*")
            if f.is_file()
            and f.suffix.lower() not in _SUPPORTED_SUFFIXES
            and not _is_hidden(f, directory)
        )

    return (
        sorted(collected, key=_file_mtime, reverse=True),
        FileCollectionSkips(
            walled=walled, unsupported=unsupported, warnings=tuple(je_pro_warnings)
        ),
    )


def collect_files(
    directory: Path,
    pattern: str = "*",
    allowlist: SyncAllowlist | None = None,
) -> list[Path]:
    """
    Collect all supported files (MD, YAML, YML) from a directory.

    Simplifies pattern matching with clear semantics:
    - "*" or "**/*" -> all supported files recursively
    - "*.md" -> only markdown files recursively
    - "specific-name" -> files with that exact stem

    Args:
        directory: Directory to search
        pattern: Glob pattern (default "*" for all files)
        allowlist: Optional fail-closed folder allowlist. When provided, files
            under the allowlist's governed root are kept only if they also sit
            under an allowed dir (see ``SyncAllowlist.permits``); files outside
            the governed root are unaffected. ``None`` = no privacy wall (but the
            je_* staging floor below still applies).

    Returns:
        List of file paths sorted by modification time (newest first)
    """
    files, _ = collect_files_detailed(directory, pattern, allowlist)
    return files


__all__ = [
    "DEFAULT_MAX_CONCURRENT_PARSING",
    "DEFAULT_MAX_FILE_SIZE_BYTES",
    "DEFAULT_USER_UID",
    "ENTITY_CONFIGS",
    "EntityIngestionConfig",
    "FileCollectionSkips",
    "REFERENCE_CHUNKING_PARAMS",
    "STAGING_EXCLUDED_DIRS",
    "SyncAllowlist",
    "build_sync_allowlist",
    "collect_files",
    "collect_files_detailed",
    "generate_ingestion_relationship_config",
    "is_ingestible_path",
    "is_staging_path",
    "je_pro_skip_reason",
    "diverged_chunk_version_by_label",
    "resolve_chunking_params",
    "resolve_chunking_params_for_label",
]
