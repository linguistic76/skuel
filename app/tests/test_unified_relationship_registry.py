"""
Tests for UnifiedRelationshipRegistry
=====================================

Verifies that the unified registry correctly generates relationship
configurations for Activity domains.

January 2026 Consolidation (ADR-026)
"""

from core.models.relationship_names import RelationshipName
from core.models.shared_enums import Domain
from core.models.unified_relationship_registry import (
    UNIFIED_REGISTRY,
    UNIFIED_REGISTRY_BY_LABEL,
    DomainRelationshipConfig,
    UnifiedRelationshipDefinition,
    generate_enables_relationships,
    generate_graph_enrichment,
    generate_prerequisite_relationships,
    generate_relationship_config,
    generate_relationship_config_by_label,
    get_unified_config,
    get_unified_config_by_label,
)
from core.services.relationships.relationship_config import RelationshipConfig


class TestUnifiedRegistry:
    """Test the unified registry structure."""

    def test_registry_has_all_domains(self):
        """Verify all domains are in the registry (6 Activity + 2 Curriculum primaries)."""
        # Note: Domain.KNOWLEDGE maps to KU, Domain.LEARNING maps to LS
        # LP and MOC are only accessible via UNIFIED_REGISTRY_BY_LABEL
        expected_domains = {
            Domain.TASKS,
            Domain.GOALS,
            Domain.HABITS,
            Domain.EVENTS,
            Domain.CHOICES,
            Domain.PRINCIPLES,
            Domain.KNOWLEDGE,  # Maps to KU
            Domain.LEARNING,  # Maps to LS
        }
        assert set(UNIFIED_REGISTRY.keys()) == expected_domains

    def test_registry_by_label_has_all_labels(self):
        """Verify all domain labels are in the label registry."""
        expected_labels = {
            # Activity Domains (6)
            "Task",
            "Goal",
            "Habit",
            "Event",
            "Choice",
            "Principle",
            # Curriculum Domains (3) - MOC removed January 2026 (now KU-based)
            "Ku",
            "Ls",
            "Lp",
            # Note: MapOfContent and MOCSection removed - MOC is now KU with ORGANIZES relationships
            # Other entities
            "User",  # User entity relationships
            "PrincipleReflection",  # Principle sub-entity
        }
        assert set(UNIFIED_REGISTRY_BY_LABEL.keys()) == expected_labels

    def test_each_config_is_domain_relationship_config(self):
        """Verify all configs are DomainRelationshipConfig instances."""
        for label, config in UNIFIED_REGISTRY_BY_LABEL.items():
            assert isinstance(config, DomainRelationshipConfig)
            assert config.entity_label == label


class TestUnifiedRelationshipDefinition:
    """Test individual relationship definitions."""

    def test_task_has_applies_knowledge_relationship(self):
        """Verify Task config has APPLIES_KNOWLEDGE relationship."""
        config = UNIFIED_REGISTRY[Domain.TASKS]
        rel_names = {r.relationship for r in config.relationships}
        assert RelationshipName.APPLIES_KNOWLEDGE in rel_names

    def test_goal_has_subgoal_relationship(self):
        """Verify Goal config has SUBGOAL_OF relationship."""
        config = UNIFIED_REGISTRY[Domain.GOALS]
        rel_names = {r.relationship for r in config.relationships}
        assert RelationshipName.SUBGOAL_OF in rel_names

    def test_to_graph_enrichment_tuple(self):
        """Verify relationship definition converts to graph enrichment tuple."""
        definition = UnifiedRelationshipDefinition(
            relationship=RelationshipName.APPLIES_KNOWLEDGE,
            target_label="Ku",
            direction="outgoing",
            context_field_name="applied_knowledge",
            method_key="knowledge",
        )
        result = definition.to_graph_enrichment_tuple()
        assert result == ("APPLIES_KNOWLEDGE", "Ku", "applied_knowledge", "outgoing")


class TestGenerateGraphEnrichment:
    """Test graph enrichment pattern generation."""

    def test_generate_task_enrichment(self):
        """Verify Task graph enrichment patterns are generated."""
        patterns = generate_graph_enrichment("Task")
        assert len(patterns) > 0
        # Each pattern is a tuple of 4 strings
        for pattern in patterns:
            assert isinstance(pattern, tuple)
            assert len(pattern) == 4
            assert all(isinstance(s, str) for s in pattern)

    def test_generate_enrichment_for_unknown_label_returns_empty(self):
        """Verify unknown labels return empty list."""
        patterns = generate_graph_enrichment("Unknown")
        assert patterns == []

    def test_all_activity_domains_have_enrichment(self):
        """Verify all Activity domain labels generate enrichment patterns."""
        for label in ["Task", "Goal", "Habit", "Event", "Choice", "Principle"]:
            patterns = generate_graph_enrichment(label)
            assert len(patterns) > 0, f"{label} should have enrichment patterns"


class TestGeneratePrerequisiteRelationships:
    """Test prerequisite relationship generation."""

    def test_task_prerequisites(self):
        """Verify Task prerequisite relationships."""
        prereqs = generate_prerequisite_relationships("Task")
        assert "BLOCKED_BY" in prereqs
        assert "REQUIRES_TASK" in prereqs

    def test_goal_prerequisites(self):
        """Verify Goal prerequisite relationships."""
        prereqs = generate_prerequisite_relationships("Goal")
        assert "REQUIRES_KNOWLEDGE" in prereqs
        assert "DEPENDS_ON_GOAL" in prereqs


class TestGenerateEnablesRelationships:
    """Test enables relationship generation."""

    def test_task_enables(self):
        """Verify Task enables relationships."""
        enables = generate_enables_relationships("Task")
        assert "BLOCKS" in enables
        assert "ENABLES_TASK" in enables

    def test_principle_enables(self):
        """Verify Principle enables relationships."""
        enables = generate_enables_relationships("Principle")
        assert "GUIDES_GOAL" in enables
        assert "INSPIRES_HABIT" in enables
        assert "GUIDES_CHOICE" in enables


class TestGenerateRelationshipConfig:
    """Test RelationshipConfig generation."""

    def test_generate_task_config(self):
        """Verify Task RelationshipConfig is generated correctly."""
        config = generate_relationship_config(Domain.TASKS)
        assert config is not None
        assert isinstance(config, RelationshipConfig)
        assert config.domain == Domain.TASKS
        assert config.entity_label == "Task"

    def test_generated_config_has_outgoing_relationships(self):
        """Verify generated config has outgoing relationships."""
        config = generate_relationship_config(Domain.TASKS)
        assert len(config.outgoing_relationships) > 0
        assert "knowledge" in config.outgoing_relationships

    def test_generated_config_has_cross_domain_mappings(self):
        """Verify generated config has cross-domain mappings."""
        config = generate_relationship_config(Domain.GOALS)
        assert len(config.cross_domain_mappings) > 0

    def test_generated_config_has_scoring_weights(self):
        """Verify generated config has scoring weights."""
        config = generate_relationship_config(Domain.TASKS)
        assert len(config.scoring_weights) > 0
        assert "urgency" in config.scoring_weights

    def test_generate_config_for_unknown_domain_returns_none(self):
        """Verify unknown domains return None."""
        # Domain.FINANCE is not in UNIFIED_REGISTRY (intentional)
        config = generate_relationship_config(Domain.FINANCE)
        assert config is None


class TestHelperFunctions:
    """Test helper functions."""

    def test_get_unified_config(self):
        """Verify get_unified_config returns correct config."""
        config = get_unified_config(Domain.TASKS)
        assert config is not None
        assert config.domain == Domain.TASKS

    def test_get_unified_config_by_label(self):
        """Verify get_unified_config_by_label returns correct config."""
        config = get_unified_config_by_label("Goal")
        assert config is not None
        assert config.entity_label == "Goal"


class TestCurriculumDomains:
    """Test curriculum domain configurations (Phase 2)."""

    def test_ku_config_is_shared_content(self):
        """Verify KU config has shared content settings."""
        config = get_unified_config_by_label("Ku")
        assert config is not None
        assert config.is_shared_content is True
        assert config.ownership_relationship is None

    def test_ls_has_practice_patterns(self):
        """Verify LS config has practice pattern relationships."""
        config = get_unified_config_by_label("Ls")
        rel_names = {r.relationship for r in config.relationships}
        assert RelationshipName.BUILDS_HABIT in rel_names
        assert RelationshipName.ASSIGNS_TASK in rel_names
        assert RelationshipName.SCHEDULES_EVENT in rel_names

    def test_lp_has_milestone_relationship(self):
        """Verify LP config has milestone event relationship."""
        config = get_unified_config_by_label("Lp")
        rel_names = {r.relationship for r in config.relationships}
        assert RelationshipName.HAS_MILESTONE_EVENT in rel_names

    def test_ku_has_organizes_relationship(self):
        """Verify KU config has ORGANIZES relationship for MOC navigation.

        January 2026: MOC is now KU-based. A KU "is" a MOC when it has
        outgoing ORGANIZES relationships (emergent identity).
        """
        config = get_unified_config_by_label("Ku")
        rel_names = {r.relationship for r in config.relationships}
        assert RelationshipName.ORGANIZES in rel_names


class TestActivityDomainIntegration:
    """Test integration with Activity domain services."""

    def test_registry_integration_with_domain_configs(self):
        """Verify generated configs work with domain_configs module."""
        from core.services.relationships.domain_configs import (
            ACTIVITY_DOMAIN_CONFIGS,
            TASK_CONFIG,
            get_config_for_domain,
        )

        # TASK_CONFIG should be a RelationshipConfig
        assert isinstance(TASK_CONFIG, RelationshipConfig)
        assert TASK_CONFIG.domain == Domain.TASKS

        # get_config_for_domain should return configs
        config = get_config_for_domain(Domain.GOALS)
        assert config is not None
        assert config.domain == Domain.GOALS

        # All Activity domains should be in the registry
        assert len(ACTIVITY_DOMAIN_CONFIGS) == 6

    def test_relationship_registry_integration(self):
        """Verify generator functions produce patterns for all domains."""
        from core.models.unified_relationship_registry import (
            generate_enables_relationships,
            generate_graph_enrichment,
            generate_prerequisite_relationships,
        )

        # Activity domains should have generated patterns
        assert len(generate_graph_enrichment("Task")) > 0
        assert len(generate_prerequisite_relationships("Task")) > 0
        assert len(generate_enables_relationships("Task")) > 0

        # Curriculum domains should also have generated patterns
        assert len(generate_graph_enrichment("Ku")) > 0
        assert len(generate_prerequisite_relationships("Ku")) > 0
        assert len(generate_enables_relationships("Ku")) > 0

        # All 9 domains should have enrichment patterns
        # Note: MOC removed January 2026 (now KU-based)
        all_labels = [
            "Task",
            "Goal",
            "Habit",
            "Event",
            "Choice",
            "Principle",
            "Ku",
            "Ls",
            "Lp",
        ]
        for label in all_labels:
            assert len(generate_graph_enrichment(label)) > 0, f"{label} missing enrichment"


class TestGenerateRelationshipConfigByLabel:
    """Test curriculum config generation via generate_relationship_config_by_label()."""

    def test_generate_ku_config(self):
        """Verify KU config is generated from label-based lookup."""
        config = generate_relationship_config_by_label("Ku")
        assert config is not None
        assert isinstance(config, RelationshipConfig)
        assert config.entity_label == "Ku"
        assert config.domain == Domain.KNOWLEDGE

    def test_generate_ls_config(self):
        """Verify LS config is generated from label-based lookup."""
        config = generate_relationship_config_by_label("Ls")
        assert config is not None
        assert isinstance(config, RelationshipConfig)
        assert config.entity_label == "Ls"
        assert config.domain == Domain.LEARNING

    def test_generate_lp_config(self):
        """Verify LP config is generated from label-based lookup."""
        config = generate_relationship_config_by_label("Lp")
        assert config is not None
        assert isinstance(config, RelationshipConfig)
        assert config.entity_label == "Lp"
        assert config.domain == Domain.LEARNING

    def test_generate_unknown_label_returns_none(self):
        """Verify unknown labels return None."""
        config = generate_relationship_config_by_label("Unknown")
        assert config is None

    def test_lp_steps_have_ordering(self):
        """Verify LP config has order_by_property on steps spec."""
        config = generate_relationship_config_by_label("Lp")
        assert config is not None
        steps_spec = config.outgoing_relationships["steps"]
        assert steps_spec.order_by_property == "sequence"
        assert steps_spec.order_direction == "ASC"
        assert steps_spec.include_edge_properties == ("sequence", "completed")

    def test_ku_organizes_have_ordering(self):
        """Verify KU config has order_by_property on organizes spec."""
        config = generate_relationship_config_by_label("Ku")
        assert config is not None
        organizes_spec = config.outgoing_relationships["organizes"]
        assert organizes_spec.order_by_property == "order"
        assert organizes_spec.order_direction == "ASC"
        assert organizes_spec.include_edge_properties == ("order",)

    def test_ls_has_expected_method_keys(self):
        """Verify LS config has all expected outgoing method_keys."""
        config = generate_relationship_config_by_label("Ls")
        assert config is not None
        expected_outgoing = {
            "knowledge",
            "prerequisite_steps",
            "prerequisite_knowledge",
            "principles",
            "choices",
            "practice_habits",
            "practice_tasks",
            "practice_events",
        }
        assert set(config.outgoing_relationships.keys()) == expected_outgoing

    def test_ls_has_incoming_in_paths(self):
        """Verify LS config has in_paths incoming relationship."""
        config = generate_relationship_config_by_label("Ls")
        assert config is not None
        assert "in_paths" in config.incoming_relationships

    def test_ku_has_expected_outgoing_keys(self):
        """Verify KU config outgoing relationship keys."""
        config = generate_relationship_config_by_label("Ku")
        assert config is not None
        # Outgoing: requires, enables, related, organizes
        assert "requires" in config.outgoing_relationships
        assert "enables" in config.outgoing_relationships
        assert "organizes" in config.outgoing_relationships

    def test_ku_has_expected_incoming_keys(self):
        """Verify KU config incoming relationship keys."""
        config = generate_relationship_config_by_label("Ku")
        assert config is not None
        assert "required_by" in config.incoming_relationships
        assert "in_steps" in config.incoming_relationships
        assert "enabled_by" in config.incoming_relationships
        assert "organized_by" in config.incoming_relationships

    def test_lp_has_expected_outgoing_keys(self):
        """Verify LP config outgoing relationship keys."""
        config = generate_relationship_config_by_label("Lp")
        assert config is not None
        expected_outgoing = {"steps", "prerequisites", "goals", "principles", "milestones"}
        assert set(config.outgoing_relationships.keys()) == expected_outgoing

    def test_lp_has_expected_incoming_keys(self):
        """Verify LP config incoming relationship keys."""
        config = generate_relationship_config_by_label("Lp")
        assert config is not None
        assert "opened_by" in config.incoming_relationships

    def test_curriculum_configs_match_domain_configs(self):
        """Verify generated curriculum configs match domain_configs module."""
        from core.services.relationships.domain_configs import (
            KU_CONFIG,
            LP_CONFIG,
            LS_CONFIG,
        )

        assert isinstance(KU_CONFIG, RelationshipConfig)
        assert isinstance(LS_CONFIG, RelationshipConfig)
        assert isinstance(LP_CONFIG, RelationshipConfig)

        # Should have same structure as direct generation
        ku_direct = generate_relationship_config_by_label("Ku")
        assert KU_CONFIG.entity_label == ku_direct.entity_label
        assert set(KU_CONFIG.outgoing_relationships.keys()) == set(
            ku_direct.outgoing_relationships.keys()
        )
