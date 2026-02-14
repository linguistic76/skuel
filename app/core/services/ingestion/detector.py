"""
Ingestion Detector - Format and Type Detection
===============================================

Classification logic for file formats and domain types.
Maps file extensions and content to KuType/NonKuDomain enums.

Extracted from unified_ingestion_service.py for separation of concerns.
"""

from pathlib import Path
from typing import Any

from core.models.enums.entity_enums import NonKuDomain
from core.models.enums.ku_enums import KuType

# ============================================================================
# TYPE MAPPING
# ============================================================================

# Map YAML type values to KuType/NonKuDomain (handles aliases)
TYPE_MAPPING: dict[str, KuType | NonKuDomain] = {
    # Knowledge Units
    "ku": KuType.CURRICULUM,
    "knowledge": KuType.CURRICULUM,
    "knowledgeunit": KuType.CURRICULUM,
    # Maps of Content
    "moc": KuType.MOC,
    "mapofcontent": KuType.MOC,
    # Activity domains
    "task": KuType.TASK,
    "goal": KuType.GOAL,
    "habit": KuType.HABIT,
    "event": KuType.EVENT,
    "choice": KuType.CHOICE,
    "principle": KuType.PRINCIPLE,
    # Curriculum domains
    "lp": KuType.LEARNING_PATH,
    "learningpath": KuType.LEARNING_PATH,
    "ls": KuType.LEARNING_STEP,
    "learningstep": KuType.LEARNING_STEP,
    # Finance
    "expense": NonKuDomain.FINANCE,
    "finance": NonKuDomain.FINANCE,
    # Content/Processing (journal maps to ASSIGNMENT since Feb 2026 merge)
    "journal": KuType.ASSIGNMENT,
    "report": KuType.ASSIGNMENT,
    # Destination
    "lifepath": KuType.LIFE_PATH,
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


def detect_entity_type(data: dict[str, Any], file_path: Path) -> KuType | NonKuDomain:
    """
    Detect domain type from file content.

    For YAML: Uses explicit 'type' field
    For MD: Uses 'type' field in frontmatter, or defaults based on flags

    Args:
        data: Parsed file data (frontmatter for MD, full content for YAML)
        file_path: Path to file (for logging)

    Returns:
        KuType or NonKuDomain enum value (type-safe!)

    Raises:
        ValueError: If domain type cannot be determined
    """
    # Check for explicit type field
    explicit_type = data.get("type", "").lower().strip()
    if explicit_type:
        if explicit_type in TYPE_MAPPING:
            return TYPE_MAPPING[explicit_type]

        # Try KuType.from_string() as fallback (handles aliases)
        ku_type = KuType.from_string(explicit_type)
        if ku_type:
            return ku_type

        # Try NonKuDomain.from_string() as secondary fallback
        non_ku = NonKuDomain.from_string(explicit_type)
        if non_ku:
            return non_ku

    # Check for MOC flag (markdown convention)
    if data.get("moc") is True:
        return KuType.MOC

    # Default to CURRICULUM for markdown files without explicit type
    if file_path.suffix.lower() == ".md":
        return KuType.CURRICULUM

    raise ValueError(f"Cannot determine entity type for {file_path}")


__all__ = [
    "TYPE_MAPPING",
    "detect_entity_type",
    "detect_format",
]
