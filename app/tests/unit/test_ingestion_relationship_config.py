"""
Validate ingestion relationship config derives from the registry.

Ingestion configs are generated from the Relationship Registry
(core/models/relationship_registry.py) — the single source of truth.
This eliminates the historical divergence where ingestion used different
relationship types than the runtime services.

Cross-reference: core/services/ingestion/config.py, ADR-026
"""

from core.models.enums.ku_enums import EntityType
from core.models.relationship_names import RelationshipName
from core.models.relationship_registry import generate_ingestion_relationship_config
from core.services.ingestion.config import ENTITY_CONFIGS


class TestIngestionRelationshipConfig:
    """Verify ingestion config is derived from the relationship registry."""

    def test_goal_uses_guided_by_principle(self):
        """Goals use GUIDED_BY_PRINCIPLE for Goal->Principle edges (from registry)."""
        config = ENTITY_CONFIGS[EntityType.GOAL].relationship_config
        assert config is not None
        assert (
            config["connections.aligned_with_principle"]["rel_type"]
            == RelationshipName.GUIDED_BY_PRINCIPLE.value
        )

    def test_choice_uses_informed_by_principle(self):
        """Choices use INFORMED_BY_PRINCIPLE for Choice->Principle edges (from registry).

        Previously used ALIGNED_WITH_PRINCIPLE — this was a bug where ingested
        edges were invisible to the runtime relationship service.
        """
        config = ENTITY_CONFIGS[EntityType.CHOICE].relationship_config
        assert config is not None
        assert (
            config["connections.guided_by_principle"]["rel_type"]
            == RelationshipName.INFORMED_BY_PRINCIPLE.value
        )

    def test_ku_uses_requires_knowledge(self):
        """KU ingestion uses REQUIRES_KNOWLEDGE (unified with registry).

        Previously used PREREQUISITE — accidental divergence from the registry.
        Now unified: all services query REQUIRES_KNOWLEDGE for KU prerequisites.
        """
        config = ENTITY_CONFIGS[EntityType.CURRICULUM].relationship_config
        assert config is not None
        assert (
            config["connections.requires"]["rel_type"] == RelationshipName.REQUIRES_KNOWLEDGE.value
        )
        assert config["connections.requires"]["direction"] == "outgoing"

    def test_ku_uses_enables_knowledge(self):
        """KU ingestion uses ENABLES_KNOWLEDGE (unified with registry).

        Previously used ENABLES — accidental divergence from the registry.
        """
        config = ENTITY_CONFIGS[EntityType.CURRICULUM].relationship_config
        assert config is not None
        assert config["connections.enables"]["rel_type"] == RelationshipName.ENABLES_KNOWLEDGE.value

    def test_all_rel_types_are_valid_relationship_names(self):
        """Every rel_type in ingestion config must be a valid RelationshipName."""
        for entity_type, config in ENTITY_CONFIGS.items():
            if not config.relationship_config:
                continue
            for field_name, rel_config in config.relationship_config.items():
                assert RelationshipName.is_valid(rel_config["rel_type"]), (
                    f"{entity_type.value}.{field_name}: "
                    f"{rel_config['rel_type']} is not a valid RelationshipName"
                )

    def test_ingestion_config_derived_from_registry(self):
        """All ingestion configs are generated from the registry, not hardcoded."""
        for entity_type, config in ENTITY_CONFIGS.items():
            if not config.relationship_config:
                continue
            generated = generate_ingestion_relationship_config(entity_type)
            assert generated is not None, f"{entity_type}: no registry config generated"
            assert config.relationship_config == generated, (
                f"{entity_type}: ingestion config does not match registry"
            )

    def test_curriculum_gets_organizes_relationship(self):
        """CURRICULUM config includes ORGANIZES for organization functionality."""
        config = ENTITY_CONFIGS[EntityType.CURRICULUM].relationship_config
        assert config is not None
        assert "organizes" in config
        assert config["organizes"]["rel_type"] == RelationshipName.ORGANIZES.value
