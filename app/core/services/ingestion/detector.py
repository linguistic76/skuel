"""
Ingestion Detector - Format and Type Detection
===============================================

Classification logic for file formats and domain types.
Maps file extensions and content to EntityType/NonKuDomain enums.

Extracted from unified_ingestion_service.py for separation of concerns.
"""

from pathlib import Path
from typing import Any

from core.models.enums.entity_enums import EntityType, NonKuDomain

# ADR-054 retired ``ExerciseSubmission`` / ``JeInput`` / ``JeOutput`` in favour
# of a single ``UserEntry`` type discriminated by ``pipeline``. Legacy YAMLs
# carrying these type strings are rejected with a clear error rather than
# silently routed (which previously stamped ``pipeline=NONE`` because the
# inference code was never written). One Path Forward — no compat shims.
_LEGACY_USER_ENTRY_ALIASES: frozenset[str] = frozenset(
    {"je_input", "je_output", "exercise_submission"}
)

# ADR-052 Phase 5 demolished the native expense module: EXPENSE left NeoLabel and
# :Expense stopped being a writable label. The ingestion mapping outlived it by a
# quarter, so `type: expense` files kept minting constraint-less :Expense nodes
# nothing reads. Rejected explicitly rather than dropped from TYPE_MAPPING —
# NonKuDomain.from_string("finance") would otherwise resolve it right back.
_RETIRED_FINANCE_ALIASES: frozenset[str] = frozenset({"expense", "finance"})

# ============================================================================
# TYPE MAPPING
# ============================================================================

# Map YAML type values to EntityType/NonKuDomain (handles aliases)
TYPE_MAPPING: dict[str, EntityType | NonKuDomain] = {
    # PathStep (curriculum content — "lesson" is a backward-compat alias)
    "lesson": EntityType.PATH_STEP,
    # Atomic Ku (knowledge unit)
    "ku": EntityType.KU,
    # Exercises
    "exercise": EntityType.EXERCISE,
    # Curated reference content (books, talks, films — descriptor metadata;
    # raw texts stay walled on disk, see Arc D ruling 2026-07-03)
    "resource": EntityType.RESOURCE,
    # Activity domains
    "task": EntityType.TASK,
    "goal": EntityType.GOAL,
    "habit": EntityType.HABIT,
    "event": EntityType.EVENT,
    "choice": EntityType.CHOICE,
    "principle": EntityType.PRINCIPLE,
    # Curriculum domains
    "lp": EntityType.LEARNING_PATH,
    "learningpath": EntityType.LEARNING_PATH,
    "ps": EntityType.PATH_STEP,
    "pathstep": EntityType.PATH_STEP,
    "learningstep": EntityType.PATH_STEP,
    # Groups (teacher-student class management)
    "group": NonKuDomain.GROUP,
    # User-authored content (ADR-054: UserEntry is the unified domain).
    # YAMLs must declare ``type: user_entry`` + an explicit ``pipeline:``.
    # No backward-compat aliases — per SKUEL's One Path Forward principle,
    # legacy ``je_input`` / ``je_output`` / ``exercise_submission`` strings
    # are rejected with a clear error pointing at ADR-054.
    "user_entry": EntityType.USER_ENTRY,
    # Interaction audit (User Interaction Contract)
    "interaction": EntityType.INTERACTION,
    "ia": EntityType.INTERACTION,  # UID prefix alias
    # Destination
    "lifepath": EntityType.LIFE_PATH,
}

# Shown in the missing-type reason. TYPE_MAPPING accepts more spellings
# (aliases like lesson/pathstep/learningpath); this lists one canonical name
# per ingestible kind so the hint stays readable.
_ACCEPTED_TYPES_HINT = (
    "e.g. ku, ps, lp, exercise, resource, user_entry, "
    "task, goal, habit, event, choice, principle, group, lifepath"
)


def detect_format(file_path: Path) -> str:
    """
    Detect file format from extension.

    Args:
        file_path: Path to file

    Returns:
        Format string: "markdown" or "yaml"

    Raises:
        ValueError: If file extension is not supported
    """
    suffix = file_path.suffix.lower()
    if suffix == ".md":
        return "markdown"
    elif suffix in (".yaml", ".yml"):
        return "yaml"
    else:
        raise ValueError(f"Unsupported file format: {suffix}")


def detect_entity_type(data: dict[str, Any], _file_path: Path) -> EntityType | NonKuDomain:
    """
    Detect domain type from file content.

    For YAML: Uses explicit 'type' field
    For MD: Uses 'type' field in frontmatter, or defaults based on flags

    Args:
        data: Parsed file data (frontmatter for MD, full content for YAML)
        _file_path: Source file path (unused; error carriers add the path —
            keeping it out of the message avoids "path: filename has no type"
            duplication in per-file reports)

    Returns:
        EntityType or NonKuDomain enum value (type-safe!)

    Raises:
        ValueError: If domain type cannot be determined (missing/empty 'type:')
    """
    # Check for explicit type field. An empty ``type:`` line parses to None
    # (PyYAML), so ``data.get("type", "")`` returns None, not the default —
    # coerce before string ops. Non-string values (``type: 5``) get the same
    # treatment; ``str()`` keeps the raised message showing what was authored.
    raw_type = data.get("type")
    explicit_type = str(raw_type).lower().strip() if raw_type is not None else ""
    if explicit_type:
        if explicit_type in _LEGACY_USER_ENTRY_ALIASES:
            raise ValueError(
                f"Type '{explicit_type}' was retired by ADR-054. "
                "Use 'type: user_entry' with an explicit 'pipeline:' field "
                "(none | teacher_review | llm_summary)."
            )
        if explicit_type in _RETIRED_FINANCE_ALIASES:
            raise ValueError(
                f"Type '{explicit_type}' was retired by ADR-052 Phase 5 — the native "
                "expense module was demolished and :Expense is no longer a writable "
                "label. Finance lives in the Firefly III sidecar (admin-only), which "
                "is not vault-ingestible."
            )
        if explicit_type in TYPE_MAPPING:
            return TYPE_MAPPING[explicit_type]

        # Try EntityType.from_string() as fallback (handles aliases)
        entity_type = EntityType.from_string(explicit_type)
        if entity_type:
            return entity_type

        # Try NonKuDomain.from_string() as secondary fallback
        non_ku = NonKuDomain.from_string(explicit_type)
        if non_ku:
            return non_ku

    # Check for MOC flag (markdown convention) — MOC is PathStep
    if data.get("moc") is True:
        return EntityType.PATH_STEP

    # A declared-but-unrecognized type is a typo to fix, not a non-entity
    # note — say so instead of the misleading "no 'type:' field" it used to
    # fall through to.
    if explicit_type:
        raise ValueError(
            f"unknown type '{explicit_type}' — not an ingestible entity type. "
            f"Use an accepted type ({_ACCEPTED_TYPES_HINT})."
        )

    # Require explicit type — no silent defaults (One Path Forward). A file
    # without one is a deliberate non-entity note; an empty ``type:`` line is
    # called out separately so the author sees the half-finished opt-in.
    field_state = "'type:' field is present but empty" if "type" in data else "no 'type:' field"
    raise ValueError(
        f"{field_state} in frontmatter — treated as a non-entity note. "
        f"To ingest it, add a type ({_ACCEPTED_TYPES_HINT})."
    )


def is_edge_type(data: dict[str, Any]) -> bool:
    """Check if parsed YAML data represents a standalone edge (not an entity)."""
    raw_type = data.get("type")
    return raw_type is not None and str(raw_type).lower().strip() == "edge"


__all__ = [
    "TYPE_MAPPING",
    "detect_entity_type",
    "detect_format",
    "is_edge_type",
]
