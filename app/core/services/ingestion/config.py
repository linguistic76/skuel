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

from core.constants import SYSTEM_USER_UID
from core.ingestion.ingestion_types import RelationshipConfig
from core.models.enums.entity_enums import EntityType, NonKuDomain
from core.models.relationship_registry import (
    ENTITY_TYPE_TO_LABEL,
    LABEL_CONFIGS,
    LABEL_TO_DEFAULT_ENTITY_TYPE,
)
from core.models.type_hints import UserUID
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

        result[rel.yaml_field_path] = RelationshipConfig(
            rel_type=rel.relationship.value,
            target_label=rel.target_label,
            direction=rel.direction,  # type: ignore[typeddict-item]  # str validated at definition
        )

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
    primary_name_field: str = "title"
    uid_normalization_fields: tuple[str, ...] = ()
    uid_singular_to_plural_fields: tuple[tuple[str, str], ...] = ()
    owner_uid_from_user_uid: bool = False
    embeddable: bool = False


# ENTITY_CONFIGS — Ingestion Entity Configuration
#
# 15 configs: 13 of the 25 EntityTypes are file-ingestible, plus the two
# NonKuDomain types (FINANCE, GROUP). Not file-ingestible:
#   - REVISED_EXERCISE: Created via API as part of the feedback loop
#   - RESOURCE: Created via API with curated metadata
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
        embeddable=True,
    ),
    EntityType.KU: EntityIngestionConfig(
        entity_label="Ku",
        uid_prefix="ku",
        required_fields=("title",),
        relationship_config=generate_ingestion_relationship_config(EntityType.KU),
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
        uid_normalization_fields=(
            "uses_kus",
            "habit_uids",
            "task_uids",
            "event_template_uids",
            "goal_uids",
            "principle_uids",
            "choice_uids",
            "exercise_uids",
            "knowledge_uids",
            "trains_ku_uids",
            "prerequisite_step_uids",
            "prerequisite_knowledge_uids",
            "learning_path_uids",
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
# FILE COLLECTION
# ============================================================================


# Default allowed subdir when SKUEL_VAULT_SYNC_ALLOWED_DIRS is unset — SKUEL's
# canonical periodic-notes folder is the one folder meant to sync from a personal
# vault, so a fail-closed default of "only this" protects everything else (je_*
# staging, templates, loose notes) without requiring configuration.
_DEFAULT_SYNC_SUBDIR = "periodic_notes"

# Pipeline staging folders that are NEVER vault content, in any configuration.
# je_in/je_out/je_raw/je_pro hold journal transcription artifacts — je_out in
# particular holds generated transcripts that must never auto-sync. These are
# excluded UNCONDITIONALLY at the ingestion chokepoint, beneath and independent of
# the SyncAllowlist privacy wall, so they stay walled even in the single-vault
# fallback where no allowlist is built (build_sync_allowlist → None).
STAGING_EXCLUDED_DIRS: frozenset[str] = frozenset({"je_in", "je_out", "je_raw", "je_pro"})


def is_staging_path(path: Path, excluded: frozenset[str] = STAGING_EXCLUDED_DIRS) -> bool:
    """True if any path component names a pipeline staging folder (je_*).

    Component-exact match (``je_output`` does not match ``je_out``), mirroring the
    historical vault-sync exclusion. Keeps staging artifacts out of ingestion on
    every path, independent of the privacy allowlist.
    """
    return any(part in excluded for part in path.parts)


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
    directory scan (``collect_files`` → ``VaultReconciler.sync`` and
    ``/api/ingest/directory``) and single-file ingestion (``ingest_file`` →
    ``/api/ingest/file``) — so no code path can bypass it. ``governed_root`` and
    ``allowed_dirs`` are stored already-resolved (see ``build_sync_allowlist``) so
    the ``permits`` check is purely lexical after a single ``resolve()`` of the
    candidate.
    """

    governed_root: Path
    allowed_dirs: frozenset[Path]

    def permits(self, path: Path) -> bool:
        """Whether ``path`` is allowed by this wall (True = keep).

        Outside the governed root → always permitted (ungoverned tree — e.g. the
        admin content vault, including any folder there that happens to be *named*
        ``je_*``). Inside → walled if it is a ``je_*`` staging folder, else
        permitted only when nested under an allowed dir.

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
    content_root: Path | None = None,
) -> SyncAllowlist | None:
    """Build the fail-closed vault-sync allowlist for ``governed_root``.

    ``SKUEL_VAULT_SYNC_ALLOWED_DIRS`` is a colon-separated list of absolute
    directories under ``governed_root`` (the personal vault) that are the ONLY
    folders whose files may be ingested. Everything else under the root is walled
    off (never read into the graph, searched, or sent to an LLM).

    Fail-closed by default — the wall does NOT depend on the env var being set:

    - **Var set** → allowlist is exactly the listed dirs (``":"`` with no real
      entries is a deliberate "wall everything").
    - **Var unset** → default to a minimal wall allowing only
      ``governed_root/{_DEFAULT_SYNC_SUBDIR}`` (SKUEL's canonical periodic-notes
      folder). A folder that is not opted in stays private, matching the
      advertised boundary rather than silently ingesting the whole vault.

    ``content_root`` (the admin curriculum vault / ``INGESTION_PATH``) guards the
    degenerate single-vault case: when it is unset AND the content vault is the
    governed root (or nested under it), a default wall would break curriculum
    ingestion, so we return ``None`` (no wall) instead — there is no distinct
    personal vault to protect there. An explicit ``SKUEL_VAULT_SYNC_ALLOWED_DIRS``
    always wins over this guard.

    Configured dirs must be *strictly under* the governed root. An entry that is
    the root itself, an ancestor, or an unrelated path would make every file
    ``is_relative_to`` it and silently open the whole vault — the opposite of
    fail-closed — so such entries are dropped (with a warning). If that leaves no
    valid dirs, the result walls everything, which is the safe direction.
    """
    governed = governed_root.resolve()
    raw = os.getenv("SKUEL_VAULT_SYNC_ALLOWED_DIRS")
    if raw and raw.strip():
        configured = [Path(p.strip()).resolve() for p in raw.split(":") if p.strip()]
        valid = frozenset(d for d in configured if d.is_relative_to(governed) and d != governed)
        for dropped in (d for d in configured if d not in valid):
            logger.warning(
                "Ignoring SKUEL_VAULT_SYNC_ALLOWED_DIRS entry %s: not strictly under the "
                "vault root %s. Allow-dirs must be subfolders of the vault; an ancestor or "
                "outside path would defeat the fail-closed wall.",
                dropped,
                governed,
            )
        return SyncAllowlist(governed_root=governed, allowed_dirs=valid)

    # Unset: default to fail-closed, unless the governed root IS the content vault
    # (or an ancestor of it), where a default wall would wrongly starve curriculum
    # ingestion. Only a genuinely distinct personal vault gets the default wall.
    if content_root is not None:
        content = content_root.resolve()
        if content == governed or content.is_relative_to(governed):
            return None
    return SyncAllowlist(
        governed_root=governed,
        allowed_dirs=frozenset({governed / _DEFAULT_SYNC_SUBDIR}),
    )


def is_ingestible_path(path: Path, allowlist: SyncAllowlist | None) -> bool:
    """Whether a vault file is eligible for ingestion under the vault exclusions.

    The single policy predicate every ingestion path shares (``collect_files``,
    ``ingest_file``, and ``reconcile_deletions``), giving the invariant: a tracked
    graph row survives deletion reconciliation iff its file would still be
    collected for ingestion. Does NOT check on-disk existence — ``collect_files``
    globs existing files; ``reconcile_deletions`` checks existence separately.

    Three rules, in order:

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
    """
    if path.is_symlink():
        return False
    if allowlist is not None:
        return allowlist.permits(path)
    return not is_staging_path(path)


def _file_mtime(path: Path) -> float:
    """Get file modification time for sorting."""
    return path.stat().st_mtime


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
    all_files: list[Path] = []

    if pattern in ("*", "**/*"):
        all_files.extend(directory.glob("**/*.md"))
        all_files.extend(directory.glob("**/*.yaml"))
        all_files.extend(directory.glob("**/*.yml"))
    elif pattern.endswith(".md") or pattern.endswith((".yaml", ".yml")):
        all_files.extend(directory.glob(f"**/{pattern}"))
    else:
        all_files.extend(directory.glob(f"**/{pattern}.md"))
        all_files.extend(directory.glob(f"**/{pattern}.yaml"))
        all_files.extend(directory.glob(f"**/{pattern}.yml"))

    # Vault exclusions: the always-on je_* staging floor plus the optional
    # fail-closed privacy allowlist. reconcile_deletions applies the SAME predicate
    # so a tracked row survives iff its file would still be collected here.
    all_files = [f for f in all_files if is_ingestible_path(f, allowlist)]

    return sorted(all_files, key=_file_mtime, reverse=True)


__all__ = [
    "DEFAULT_MAX_CONCURRENT_PARSING",
    "DEFAULT_MAX_FILE_SIZE_BYTES",
    "DEFAULT_USER_UID",
    "ENTITY_CONFIGS",
    "EntityIngestionConfig",
    "STAGING_EXCLUDED_DIRS",
    "SyncAllowlist",
    "build_sync_allowlist",
    "collect_files",
    "generate_ingestion_relationship_config",
    "is_ingestible_path",
    "is_staging_path",
]
