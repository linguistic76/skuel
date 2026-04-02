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
    "ls": EntityType.PATH_STEP,  # backward-compat alias
    "learningstep": EntityType.PATH_STEP,  # backward-compat alias
    # Finance
    "expense": NonKuDomain.FINANCE,
    "finance": NonKuDomain.FINANCE,
    # Content/Processing
    "je_input": EntityType.JE_INPUT,
    "exercise_submission": EntityType.EXERCISE_SUBMISSION,
    # Interaction audit (User Interaction Contract)
    "interaction": EntityType.INTERACTION,
    "ia": EntityType.INTERACTION,  # UID prefix alias
    # Destination
    "lifepath": EntityType.LIFE_PATH,
}


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


def detect_entity_type(data: dict[str, Any], file_path: Path) -> EntityType | NonKuDomain:
    """
    Detect domain type from file content.

    For YAML: Uses explicit 'type' field
    For MD: Uses 'type' field in frontmatter, or defaults based on flags

    Args:
        data: Parsed file data (frontmatter for MD, full content for YAML)
        file_path: Path to file (for logging)

    Returns:
        EntityType or NonKuDomain enum value (type-safe!)

    Raises:
        ValueError: If domain type cannot be determined
    """
    # Check for explicit type field
    explicit_type = data.get("type", "").lower().strip()
    if explicit_type:
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

    # Require explicit type — no silent defaults (One Path Forward)
    if file_path.suffix.lower() == ".md":
        raise ValueError(
            f"Markdown file {file_path.name} has no 'type' field in frontmatter. "
            f"Add 'type: PathStep' or 'type: Ku' to the YAML frontmatter."
        )

    raise ValueError(f"Cannot determine entity type for {file_path}")


def is_edge_type(data: dict[str, Any]) -> bool:
    """Check if parsed YAML data represents a standalone edge (not an entity)."""
    return data.get("type", "").lower().strip() == "edge"


__all__ = [
    "TYPE_MAPPING",
    "detect_entity_type",
    "detect_format",
    "is_edge_type",
]
