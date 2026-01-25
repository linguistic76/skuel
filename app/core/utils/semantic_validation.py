"""
Semantic Validation Utilities
==============================

Utilities for validating entities against domain ontologies and schemas.
"""

from typing import Any

from core.infrastructure.database.ontology_generator import (
    Ontology,
    PropertyDefinition,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result


class OntologyValidator:
    """Validates entities against domain ontologies."""

    def __init__(self, ontology: Ontology) -> None:
        """Initialize with domain ontology."""
        self.ontology = ontology
        self.logger = get_logger("skuel.ontology.validator")

    def validate_entity(self, entity: Any, class_name: str) -> Result[bool]:
        """Validate an entity against its class definition."""
        if class_name not in self.ontology.classes:
            return Result.fail(
                Errors.validation(f"Unknown class: {class_name}", field="class_name")
            )

        class_def = self.ontology.classes[class_name]

        # Check required properties
        for prop in class_def.get_required_properties():
            # Try to get the property value
            try:
                value = getattr(entity, prop.name, None)
                if value is None and prop.name not in entity.__dict__:
                    return Result.fail(
                        Errors.validation(
                            f"Missing required property: {prop.name}", field=prop.name
                        )
                    )
            except AttributeError:
                return Result.fail(
                    Errors.validation(f"Missing required property: {prop.name}", field=prop.name)
                )

            # Validate property type
            if not self._validate_property_type(value, prop):
                return Result.fail(
                    Errors.validation(f"Invalid type for property {prop.name}", field=prop.name)
                )

        return Result.ok(True)

    def validate_relationship(self, from_class: str, rel_type: str, to_class: str) -> Result[bool]:
        """Validate a relationship against the ontology."""
        # Check if relationship is defined
        valid_rel = None
        for rel in self.ontology.relationships:
            if (
                rel.from_class == from_class
                and rel.relationship_type == rel_type
                and rel.to_class == to_class
            ):
                valid_rel = rel
                break

        if not valid_rel:
            return Result.fail(
                Errors.validation(
                    f"Invalid relationship: {from_class} -{rel_type}-> {to_class}",
                    field="relationship",
                )
            )

        return Result.ok(True)

    def _validate_property_type(self, value: Any, prop: PropertyDefinition) -> bool:
        """Validate a property value against its definition."""
        # Check if value is None and property is not required
        if value is None:
            return not prop.is_required

        # Check if list when expected
        if prop.is_list:
            if not isinstance(value, list):
                return False
            # Validate each item
            return all(self._validate_single_value(item, prop) for item in value)

        return self._validate_single_value(value, prop)

    def _validate_single_value(self, value: Any, prop: PropertyDefinition) -> bool:
        """Validate a single value."""
        # Check allowed values
        if prop.allowed_values and value not in prop.allowed_values:
            return False

        # Check min/max constraints
        if prop.min_value is not None and value < prop.min_value:
            return False
        return not (prop.max_value is not None and value > prop.max_value)
