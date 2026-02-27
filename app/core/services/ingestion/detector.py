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
    # Knowledge Units
    "ku": EntityType.KU,
    "knowledge": EntityType.KU,
    "knowledgeunit": EntityType.KU,
    # Maps of Content (now CURRICULUM — MOC is emergent via ORGANIZES relationships)
    "moc": EntityType.KU,
    "mapofcontent": EntityType.KU,
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
    "ls": EntityType.LEARNING_STEP,
    "learningstep": EntityType.LEARNING_STEP,
    # Finance
    "expense": NonKuDomain.FINANCE,
    "finance": NonKuDomain.FINANCE,
    # Content/Processing (journal maps to SUBMISSION since Feb 2026 merge)
    "journal": EntityType.SUBMISSION,
    "report": EntityType.SUBMISSION,
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
        ku_type = EntityType.from_string(explicit_type)
        if ku_type:
            return ku_type

        # Try NonKuDomain.from_string() as secondary fallback
        non_ku = NonKuDomain.from_string(explicit_type)
        if non_ku:
            return non_ku

    # Check for MOC flag (markdown convention) — MOC is now CURRICULUM
    if data.get("moc") is True:
        return EntityType.KU

    # Default to CURRICULUM for markdown files without explicit type
    if file_path.suffix.lower() == ".md":
        return EntityType.KU

    raise ValueError(f"Cannot determine entity type for {file_path}")


__all__ = [
    "TYPE_MAPPING",
    "detect_entity_type",
    "detect_format",
]
