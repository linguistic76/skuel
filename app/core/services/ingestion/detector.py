"""
Ingestion Detector - Format and Type Detection
===============================================

Classification logic for file formats and entity types.
Maps file extensions and content to EntityType enums.

Extracted from unified_ingestion_service.py for separation of concerns.
"""

from pathlib import Path
from typing import Any

from core.models.shared_enums import EntityType

# ============================================================================
# TYPE MAPPING
# ============================================================================

# Map YAML type values to EntityType (handles aliases)
TYPE_MAPPING: dict[str, EntityType] = {
    # Knowledge Units
    "ku": EntityType.KU,
    "knowledge": EntityType.KU,
    "knowledgeunit": EntityType.KU,
    # Maps of Content
    "moc": EntityType.MOC,
    "mapofcontent": EntityType.MOC,
    # Activity domains
    "task": EntityType.TASK,
    "goal": EntityType.GOAL,
    "habit": EntityType.HABIT,
    "event": EntityType.EVENT,
    "choice": EntityType.CHOICE,
    "principle": EntityType.PRINCIPLE,
    # Curriculum domains
    "lp": EntityType.LP,
    "learningpath": EntityType.LP,
    "ls": EntityType.LS,
    "learningstep": EntityType.LS,
    # Finance
    "expense": EntityType.FINANCE,
    "finance": EntityType.FINANCE,
    # Content/Processing (journal maps to REPORT since Feb 2026 merge)
    "journal": EntityType.REPORT,
    "report": EntityType.REPORT,
    # Destination
    "lifepath": EntityType.LIFEPATH,
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


def detect_entity_type(data: dict[str, Any], file_path: Path) -> EntityType:
    """
    Detect entity type from file content.

    For YAML: Uses explicit 'type' field
    For MD: Uses 'type' field in frontmatter, or defaults based on flags

    Args:
        data: Parsed file data (frontmatter for MD, full content for YAML)
        file_path: Path to file (for logging)

    Returns:
        EntityType enum value (type-safe!)

    Raises:
        ValueError: If entity type cannot be determined
    """
    # Check for explicit type field
    explicit_type = data.get("type", "").lower().strip()
    if explicit_type:
        if explicit_type in TYPE_MAPPING:
            return TYPE_MAPPING[explicit_type]

        # Try EntityType.from_string() as fallback
        entity_type = EntityType.from_string(explicit_type)
        if entity_type:
            return entity_type.get_canonical()

    # Check for MOC flag (markdown convention)
    if data.get("moc") is True:
        return EntityType.MOC

    # Default to KU for markdown files without explicit type
    if file_path.suffix.lower() == ".md":
        return EntityType.KU

    raise ValueError(f"Cannot determine entity type for {file_path}")


__all__ = [
    "TYPE_MAPPING",
    "detect_entity_type",
    "detect_format",
]
