"""
Schema Mapping Service
======================

Centralized service for safe enum/schema mappings to reduce adapter fragility.

Following SKUEL principles:
- ONE PATH FORWARD: Single source of truth for all enum mappings
- FAIL-FAST: Clear errors when mappings fail
- TYPE-SAFE: Proper enum handling with fallbacks

This service ensures adapters don't need to implement their own validation
heuristics or duplicate enum mapping logic.
"""

from enum import Enum
from typing import Any

from core.models.enums import Domain, KnowledgeStatus, Priority
from core.services.protocols import get_enum_value
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


class SchemaMappingService:
    """
    THE service for safe enum/schema mappings.

    Provides centralized, validated mapping logic to prevent adapters
    from duplicating enum conversion heuristics.


    Source Tag: "schema_mapping_service_explicit"
    - Format: "schema_mapping_service_explicit" for user-created relationships
    - Format: "schema_mapping_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from schema_mapping metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    def __init__(self) -> None:
        """Initialize schema mapping service."""
        self.logger = logger

        # Define default values for enums
        self._domain_default = Domain.KNOWLEDGE  # Default to knowledge domain
        self._status_default = KnowledgeStatus.DRAFT
        self._priority_default = Priority.MEDIUM

    # ========================================================================
    # DOMAIN MAPPING
    # ========================================================================

    def map_domain(self, raw_value: Any, default: Domain | None = None) -> Result[Domain]:
        """
        Safely map raw value to Domain enum.

        Args:
            raw_value: Raw value (string, enum, or None),
            default: Optional default if mapping fails

        Returns:
            Result containing Domain enum or error
        """
        if raw_value is None:
            return Result.ok(default or self._domain_default)

        # If already a Domain enum
        if isinstance(raw_value, Domain):
            return Result.ok(raw_value)

        # Try to convert string to Domain
        try:
            value_str = str(raw_value).upper()

            # Handle common variations
            value_str = self._normalize_domain_name(value_str)

            domain = Domain[value_str]
            return Result.ok(domain)

        except (KeyError, ValueError, AttributeError) as e:
            self.logger.warning(f"Failed to map domain '{raw_value}': {e}")

            if default:
                return Result.ok(default)

            return Result.fail(
                Errors.validation(
                    f"Invalid domain value: '{raw_value}'",
                    field="domain",
                    user_message=f"Domain '{raw_value}' is not recognized. Using default.",
                )
            )

    def _normalize_domain_name(self, value: str) -> str:
        """Normalize domain names to handle variations."""
        # Handle common variations
        normalization_map = {
            "TECH": "TECHNOLOGY",
            "SCI": "SCIENCE",
            "BIZ": "BUSINESS",
            "FIN": "FINANCE",
            "ENG": "ENGINEERING",
        }
        return normalization_map.get(value, value)

    # ========================================================================
    # KNOWLEDGE STATUS MAPPING
    # ========================================================================

    def map_knowledge_status(
        self, raw_value: Any, default: KnowledgeStatus | None = None
    ) -> Result[KnowledgeStatus]:
        """
        Safely map raw value to KnowledgeStatus enum.

        Args:
            raw_value: Raw value (string, enum, or None),
            default: Optional default if mapping fails

        Returns:
            Result containing KnowledgeStatus enum or error
        """
        if raw_value is None:
            return Result.ok(default or self._status_default)

        # If already KnowledgeStatus enum
        if isinstance(raw_value, KnowledgeStatus):
            return Result.ok(raw_value)

        # Try to convert string to KnowledgeStatus
        try:
            value_str = str(raw_value).upper()

            # Handle common variations
            value_str = self._normalize_status_name(value_str)

            status = KnowledgeStatus[value_str]
            return Result.ok(status)

        except (KeyError, ValueError, AttributeError) as e:
            self.logger.warning(f"Failed to map knowledge status '{raw_value}': {e}")

            if default:
                return Result.ok(default)

            return Result.fail(
                Errors.validation(
                    f"Invalid knowledge status: '{raw_value}'",
                    field="status",
                    user_message=f"Status '{raw_value}' is not recognized. Using default.",
                )
            )

    def _normalize_status_name(self, value: str) -> str:
        """Normalize status names to handle variations."""
        normalization_map = {
            "IN_PROGRESS": "IN_PROGRESS",
            "INPROGRESS": "IN_PROGRESS",
            "COMPLETE": "COMPLETED",
            "DONE": "COMPLETED",
            "ACTIVE": "PUBLISHED",
            "WIP": "IN_PROGRESS",
        }
        return normalization_map.get(value, value)

    # ========================================================================
    # PRIORITY MAPPING
    # ========================================================================

    def map_priority(self, raw_value: Any, default: Priority | None = None) -> Result[Priority]:
        """
        Safely map raw value to Priority enum.

        Args:
            raw_value: Raw value (string, enum, int, or None),
            default: Optional default if mapping fails

        Returns:
            Result containing Priority enum or error
        """
        if raw_value is None:
            return Result.ok(default or self._priority_default)

        # If already Priority enum
        if isinstance(raw_value, Priority):
            return Result.ok(raw_value)

        # Try to convert to Priority
        try:
            # Handle numeric priority (1=HIGH, 2=MEDIUM, 3=LOW)
            if isinstance(raw_value, int):
                priority_map = {1: Priority.HIGH, 2: Priority.MEDIUM, 3: Priority.LOW}
                if raw_value in priority_map:
                    return Result.ok(priority_map[raw_value])

            # Handle string
            value_str = str(raw_value).upper()
            value_str = self._normalize_priority_name(value_str)

            priority = Priority[value_str]
            return Result.ok(priority)

        except (KeyError, ValueError, AttributeError) as e:
            self.logger.warning(f"Failed to map priority '{raw_value}': {e}")

            if default:
                return Result.ok(default)

            return Result.fail(
                Errors.validation(
                    f"Invalid priority value: '{raw_value}'",
                    field="priority",
                    user_message=f"Priority '{raw_value}' is not recognized. Using default.",
                )
            )

    def _normalize_priority_name(self, value: str) -> str:
        """Normalize priority names to handle variations."""
        normalization_map = {
            "URGENT": "HIGH",
            "IMPORTANT": "HIGH",
            "NORMAL": "MEDIUM",
            "STANDARD": "MEDIUM",
            "MINOR": "LOW",
        }
        return normalization_map.get(value, value)

    # ========================================================================
    # GENERIC ENUM MAPPING
    # ========================================================================

    def map_enum(
        self, enum_class: type[Enum], raw_value: Any, default: Enum | None = None
    ) -> Result[Enum]:
        """
        Generic safe enum mapping.

        Args:
            enum_class: The enum class to map to,
            raw_value: Raw value to map,
            default: Optional default value

        Returns:
            Result containing enum value or error
        """
        if raw_value is None:
            if default:
                return Result.ok(default)
            return Result.fail(
                Errors.validation(
                    "Enum value is None and no default provided", field="enum_mapping"
                )
            )

        # If already the correct enum type
        if isinstance(raw_value, enum_class):
            return Result.ok(raw_value)

        # Try string conversion
        try:
            value_str = str(raw_value).upper()
            enum_value = enum_class[value_str]
            return Result.ok(enum_value)

        except (KeyError, ValueError, AttributeError) as e:
            self.logger.warning(f"Failed to map to {enum_class.__name__}: '{raw_value}' - {e}")

            if default:
                return Result.ok(default)

            return Result.fail(
                Errors.validation(
                    f"Invalid {enum_class.__name__} value: '{raw_value}'",
                    field="enum_value",
                    user_message=f"Value '{raw_value}' is not a valid {enum_class.__name__}",
                )
            )

    # ========================================================================
    # BATCH MAPPING
    # ========================================================================

    def map_batch(
        self, mappings: dict[str, tuple[type[Enum], Any, Enum | None]]
    ) -> Result[dict[str, Enum]]:
        """
        Map multiple enum values in batch.

        Args:
            mappings: Dict of {field_name: (enum_class, raw_value, default)}

        Returns:
            Result containing dict of mapped enums or first error encountered
        """
        results = {}

        for field_name, (enum_class, raw_value, default) in mappings.items():
            result = self.map_enum(enum_class, raw_value, default)

            if result.is_error:
                return Result.fail(result.error)

            results[field_name] = result.value

        return Result.ok(results)

    # ========================================================================
    # EXTRACTION HELPERS
    # ========================================================================

    def extract_enum_value(self, enum_or_value: Any) -> Any:
        """
        Extract the actual value from an enum or return as-is.

        Uses the standard get_enum_value protocol.

        Args:
            enum_or_value: Enum instance or regular value

        Returns:
            The enum's value or the original value
        """
        return get_enum_value(enum_or_value)


# ============================================================================
# MODULE EXPORTS
# ============================================================================

__all__ = [
    "SchemaMappingService",
]
