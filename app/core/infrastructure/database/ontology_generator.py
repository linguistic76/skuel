"""
Ontology Generator from Pydantic Schemas
========================================

Generates semantic ontologies from Pydantic schemas without requiring RDF tools.
This creates a formal definition of your domain that can be used for validation,
documentation, and consistency enforcement.

The ontology defines:
- What entity types exist (Classes)
- What properties they have (DataProperties)
- What relationships are valid between them (ObjectProperties)
- Constraints and validation rules (Restrictions)
"""

import inspect
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
from core.services.protocols import (
    GeConstraint,
    GtConstraint,
    LeConstraint,
    LtConstraint,
    MaxItemsConstraint,
    MaxLenConstraint,
    MinLenConstraint,
    PydanticFieldInfo,
)
from core.utils.logging import get_logger

logger = get_logger("skuel.infrastructure.ontology")


@dataclass
class PropertyDefinition:
    """Defines a property in the ontology."""

    name: str
    property_type: str  # data type or reference type
    is_required: bool
    is_list: bool = False
    min_value: Any | None = None
    max_value: Any | None = None
    allowed_values: list[Any] = field(default_factory=list)
    description: str = ""
    constraints: dict[str, Any] = field(default_factory=dict)


@dataclass
class ClassDefinition:
    """Defines a class (entity type) in the ontology."""

    name: str
    base_class: str | None = None
    properties: list[PropertyDefinition] = field(default_factory=list)
    valid_relationships: list[str] = field(default_factory=list)
    description: str = ""
    constraints: dict[str, Any] = field(default_factory=dict)

    def get_required_properties(self) -> list[PropertyDefinition]:
        """Get all required properties."""
        return [p for p in self.properties if p.is_required]

    def get_reference_properties(self) -> list[PropertyDefinition]:
        """Get properties that reference other entities."""
        return [p for p in self.properties if p.property_type.endswith("_uid")]


@dataclass
class RelationshipDefinition:
    """Defines valid relationships between classes."""

    from_class: str
    relationship_type: str
    to_class: str
    cardinality: str = "many-to-many"  # one-to-one, one-to-many, many-to-many
    is_required: bool = False
    inverse_relationship: str | None = None
    constraints: dict[str, Any] = field(default_factory=dict)


@dataclass
class Ontology:
    """
    Complete ontology definition for the domain.

    This represents the formal structure of your knowledge graph,
    generated from Pydantic schemas.
    """

    namespace: str = "http://skuel.xyz/ontology#"
    classes: dict[str, ClassDefinition] = field(default_factory=dict)
    relationships: list[RelationshipDefinition] = field(default_factory=list)
    enums: dict[str, list[str]] = field(default_factory=dict)
    version: str = "1.0"

    def add_class(self, class_def: ClassDefinition) -> None:
        """Add a class definition to the ontology."""
        self.classes[class_def.name] = class_def

    def add_relationship(self, rel_def: RelationshipDefinition) -> None:
        """Add a relationship definition."""
        self.relationships.append(rel_def)

    def get_class_hierarchy(self) -> dict[str, list[str]]:
        """Get the class hierarchy as parent -> children mapping."""
        hierarchy = {}
        for name, class_def in self.classes.items():
            if class_def.base_class:
                if class_def.base_class not in hierarchy:
                    hierarchy[class_def.base_class] = []
                hierarchy[class_def.base_class].append(name)
        return hierarchy

    def to_cypher_constraints(self) -> list[str]:
        """
        Generate Cypher constraint statements for Neo4j.

        These ensure data integrity in the graph database.
        """
        constraints = []

        for class_name, class_def in self.classes.items():
            # Unique constraint on uid
            constraints.append(
                f"CREATE CONSTRAINT {class_name}_uid_unique IF NOT EXISTS "
                f"ON (n:{class_name}) ASSERT n.uid IS UNIQUE"
            )

            # Required property constraints
            constraints.extend(
                [
                    f"CREATE CONSTRAINT {class_name}_{prop.name}_exists IF NOT EXISTS "
                    f"ON (n:{class_name}) ASSERT n.{prop.name} IS NOT NULL"
                    for prop in class_def.get_required_properties()
                ]
            )

        return constraints

    def to_validation_rules(self) -> dict[str, list[str]]:
        """
        Generate validation rules for each class.

        These can be used to validate data before insertion.
        """
        rules = {}

        for class_name, class_def in self.classes.items():
            class_rules = []

            for prop in class_def.properties:
                if prop.is_required:
                    class_rules.append(f"{prop.name} is required")

                if prop.min_value is not None:
                    class_rules.append(f"{prop.name} >= {prop.min_value}")

                if prop.max_value is not None:
                    class_rules.append(f"{prop.name} <= {prop.max_value}")

                if prop.allowed_values:
                    class_rules.append(f"{prop.name} in {prop.allowed_values}")

            rules[class_name] = class_rules

        return rules


class PydanticOntologyGenerator:
    """
    Generates ontology from Pydantic schemas.

    This creates a formal domain definition that can be used for:
    - Validation
    - Documentation
    - Query optimization
    - Consistency enforcement
    """

    def __init__(self) -> None:
        self.ontology = Ontology()
        self._processed_models: set = set()

    def generate_from_model(self, model_class: type[BaseModel]) -> ClassDefinition:
        """
        Generate class definition from a Pydantic model.

        This introspects the model to extract:
        - Properties and their types
        - Validation constraints
        - Relationships to other models
        """
        if model_class.__name__ in self._processed_models:
            return self.ontology.classes[model_class.__name__]

        self._processed_models.add(model_class.__name__)

        # Create class definition
        class_def = ClassDefinition(
            name=model_class.__name__,
            description=model_class.__doc__ or "",
            base_class=self._get_base_class(model_class),
        )

        # Extract properties from model fields
        for field_name, field_info in model_class.model_fields.items():
            prop_def = self._create_property_definition(field_name, field_info)
            class_def.properties.append(prop_def)

            # Detect relationships
            if field_name.endswith("_uid") or field_name.endswith("_uids"):
                self._infer_relationship(class_def.name, field_name)

        # Add to ontology
        self.ontology.add_class(class_def)

        return class_def

    def _create_property_definition(self, name: str, field_info: Any) -> PropertyDefinition:
        """Create property definition from Pydantic field."""
        from pydantic.fields import FieldInfo

        # Get type information
        field_type = str(field_info.annotation)
        is_required = field_info.is_required()
        is_list = "list" in field_type.lower() or "List" in field_type

        # Extract constraints from field info
        constraints = {}
        min_value = None
        max_value = None
        allowed_values = []
        description = ""

        if isinstance(field_info, FieldInfo):
            if field_info.description:
                description = field_info.description

            # Extract constraints from metadata (Pydantic v2 pattern)
            if isinstance(field_info, PydanticFieldInfo):
                for constraint in field_info.metadata:
                    # Numeric constraints
                    if isinstance(constraint, GeConstraint):
                        min_value = constraint.ge
                    # Only set gt if ge not already set
                    elif isinstance(constraint, GtConstraint) and min_value is None:
                        min_value = constraint.gt

                    if isinstance(constraint, LeConstraint):
                        max_value = constraint.le
                    # Only set lt if le not already set
                    elif isinstance(constraint, LtConstraint) and max_value is None:
                        max_value = constraint.lt

                    # String constraints
                    if isinstance(constraint, MinLenConstraint):
                        constraints["min_length"] = constraint.min_length
                    if isinstance(constraint, MaxLenConstraint):
                        constraints["max_length"] = constraint.max_length

                    # List constraints
                    if isinstance(constraint, MaxItemsConstraint):
                        constraints["max_items"] = constraint.max_items

        return PropertyDefinition(
            name=name,
            property_type=field_type,
            is_required=is_required,
            is_list=is_list,
            min_value=min_value,
            max_value=max_value,
            allowed_values=allowed_values,
            description=description,
            constraints=constraints,
        )

    def _get_base_class(self, model_class: type[BaseModel]) -> str | None:
        """Get the base class name if it's also a BaseModel."""
        for base in model_class.__bases__:
            if base != BaseModel and issubclass(base, BaseModel):
                return base.__name__
        return None

    def _infer_relationship(self, from_class: str, field_name: str) -> None:
        """Infer relationship from field name."""
        # Remove _uid or _uids suffix
        if field_name.endswith("_uids"):
            to_class = field_name[:-5].title()
            cardinality = "one-to-many"
        else:
            to_class = field_name[:-4].title()
            cardinality = "one-to-one"

        # Map to semantic relationship type
        if "parent" in field_name:
            rel_type = SemanticRelationshipType.CHILD_OF.value
        elif "prerequisite" in field_name:
            rel_type = SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING.value
        elif "dependency" in field_name:
            rel_type = SemanticRelationshipType.REQUIRES_CONCEPTUAL_FOUNDATION.value
        else:
            rel_type = SemanticRelationshipType.RELATED_TO.value

        rel_def = RelationshipDefinition(
            from_class=from_class,
            relationship_type=rel_type,
            to_class=to_class,
            cardinality=cardinality,
        )

        self.ontology.add_relationship(rel_def)

    def generate_from_module(self, module: Any) -> Ontology:
        """
        Generate ontology from all Pydantic models in a module.

        This scans a module for all BaseModel subclasses and generates
        a complete ontology.
        """
        for _name, obj in inspect.getmembers(module):
            if inspect.isclass(obj) and issubclass(obj, BaseModel) and obj != BaseModel:
                self.generate_from_model(obj)

        return self.ontology

    def to_documentation(self) -> str:
        """
        Generate human-readable documentation of the ontology.

        This can be displayed in UI or exported as markdown.
        """
        doc = f"# SKUEL Ontology v{self.ontology.version}\n\n"
        doc += f"Namespace: {self.ontology.namespace}\n\n"

        doc += "## Classes\n\n"
        for class_name, class_def in self.ontology.classes.items():
            doc += f"### {class_name}\n"
            if class_def.description:
                doc += f"{class_def.description}\n\n"

            if class_def.base_class:
                doc += f"**Extends:** {class_def.base_class}\n\n"

            doc += "**Properties:**\n"
            for prop in class_def.properties:
                required = "required" if prop.is_required else "optional"
                doc += f"- `{prop.name}` ({prop.property_type}) - {required}"
                if prop.description:
                    doc += f" - {prop.description}"
                doc += "\n"
            doc += "\n"

        doc += "## Relationships\n\n"
        for rel in self.ontology.relationships:
            doc += f"- {rel.from_class} --[{rel.relationship_type}]--> {rel.to_class}"
            doc += f" ({rel.cardinality})\n"

        doc += "\n## Validation Rules\n\n"
        for class_name, rules in self.ontology.to_validation_rules().items():
            if rules:
                doc += f"**{class_name}:**\n"
                for rule in rules:
                    doc += f"- {rule}\n"
                doc += "\n"

        return doc


# ============================================================================
# USAGE EXAMPLE
# ============================================================================


def generate_skuel_ontology():
    """
    Generate the complete SKUEL ontology from existing Pydantic schemas.

    This creates a formal definition of the entire domain.
    """
    generator = PydanticOntologyGenerator()

    # Import all schema modules (request files contain Pydantic schemas)
    from core.models.event import event_request
    from core.models.habit import habit_request
    from core.models.task import task_request

    # Generate from each module
    for module in [task_request, event_request, habit_request]:
        generator.generate_from_module(module)

    ontology = generator.ontology

    # Add domain-specific relationships
    ontology.add_relationship(
        RelationshipDefinition(
            from_class="TaskCreateSchema",
            relationship_type=SemanticRelationshipType.IMPLEMENTS_VIA_TASK.value,
            to_class="LearningPathSchema",
            cardinality="many-to-many",
        )
    )

    ontology.add_relationship(
        RelationshipDefinition(
            from_class="HabitCreateSchema",
            relationship_type=SemanticRelationshipType.PRACTICES_VIA_HABIT.value,
            to_class="LearningPathSchema",
            cardinality="many-to-many",
        )
    )

    return ontology


def apply_ontology_to_neo4j(ontology: Ontology, session: Any) -> None:
    """
    Apply ontology constraints to Neo4j database.

    This ensures the graph follows the formal structure.
    """
    constraints = ontology.to_cypher_constraints()

    for constraint in constraints:
        try:
            session.run(constraint)
        except Exception as e:
            logger.warning("Constraint already exists or failed", error=str(e))
