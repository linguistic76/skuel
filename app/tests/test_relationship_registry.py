"""
Tests for RelationshipRegistry
===============================

Verifies that the relationship registry correctly provides relationship
configurations for all domains (Activity + Curriculum).

January 2026 Consolidation (ADR-026)
February 2026: Removed parallel config tests (generator functions deleted)
"""

from core.models.enums import Domain
from core.models.relationship_names import RelationshipName
from core.models.relationship_registry import (
    CHOICES_CONFIG,
    DOMAIN_CONFIGS,
    EVENTS_CONFIG,
    GOALS_CONFIG,
    HABITS_CONFIG,
    LABEL_CONFIGS,
    LESSON_CONFIG,
    LP_CONFIG,
    LS_CONFIG,
    PRINCIPLES_CONFIG,
    TASKS_CONFIG,
    DomainRelationshipConfig,
    UnifiedRelationshipDefinition,
    generate_enables_relationships,
    generate_graph_enrichment,
    generate_prerequisite_relationships,
    get_config_by_label,
    get_domain_config,
)


class TestUnifiedRegistry:
    """Test the unified registry structure."""

    def test_registry_has_all_domains(self):
        """Verify all domains are in the registry (6 Activity + 2 Curriculum primaries)."""
        # Note: Domain.KNOWLEDGE maps to KU, Domain.LEARNING maps to LS
        # LP and MOC are only accessible via LABEL_CONFIGS
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
        assert set(DOMAIN_CONFIGS.keys()) == expected_domains

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
            # Curriculum Domains (5) - MOC removed January 2026 (now KU-based)
            "Entity",
            "Ku",
            "Ls",
            "Lp",
            "Exercise",  # Instruction templates
            "RevisedExercise",  # Five-phase learning loop revision cycle
            # Note: MapOfContent and MOCSection removed - MOC is now KU with ORGANIZES relationships
            # Other entities
            "User",  # User entity relationships
            "PrincipleReflection",  # Principle sub-entity
        }
        assert set(LABEL_CONFIGS.keys()) == expected_labels

    def test_each_config_is_domain_relationship_config(self):
        """Verify all configs are DomainRelationshipConfig instances."""
        for label, config in LABEL_CONFIGS.items():
            assert isinstance(config, DomainRelationshipConfig)
            # entity_label may be "Entity" for unified domains while dict key keeps
            # the logical name (e.g. "Habit") for lookup purposes
            assert config.entity_label in (label, "Entity")


class TestUnifiedRelationshipDefinition:
    """Test individual relationship definitions."""

    def test_task_has_applies_knowledge_relationship(self):
        """Verify Task config has APPLIES_KNOWLEDGE relationship."""
        config = DOMAIN_CONFIGS[Domain.TASKS]
        rel_names = {r.relationship for r in config.relationships}
        assert RelationshipName.APPLIES_KNOWLEDGE in rel_names

    def test_goal_has_subgoal_relationship(self):
        """Verify Goal config has SUBGOAL_OF relationship."""
        config = DOMAIN_CONFIGS[Domain.GOALS]
        rel_names = {r.relationship for r in config.relationships}
        assert RelationshipName.SUBGOAL_OF in rel_names

    def test_to_graph_enrichment_tuple(self):
        """Verify relationship definition converts to graph enrichment tuple."""
        definition = UnifiedRelationshipDefinition(
            relationship=RelationshipName.APPLIES_KNOWLEDGE,
            target_label="Entity",
            direction="outgoing",
            context_field_name="applied_knowledge",
            method_key="knowledge",
        )
        result = definition.to_graph_enrichment_tuple()
        assert result == ("APPLIES_KNOWLEDGE", "Entity", "applied_knowledge", "outgoing")


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


class TestDomainRelationshipConfigMethods:
    """Test methods added to DomainRelationshipConfig for direct consumption."""

    def test_get_relationship_by_method_found(self):
        """Verify get_relationship_by_method returns matching definition."""
        rel = TASKS_CONFIG.get_relationship_by_method("knowledge")
        assert rel is not None
        assert rel.relationship == RelationshipName.APPLIES_KNOWLEDGE

    def test_get_relationship_by_method_not_found(self):
        """Verify get_relationship_by_method returns None for unknown key."""
        rel = TASKS_CONFIG.get_relationship_by_method("nonexistent")
        assert rel is None

    def test_get_all_relationship_methods(self):
        """Verify get_all_relationship_methods returns method keys."""
        methods = TASKS_CONFIG.get_all_relationship_methods()
        assert isinstance(methods, list)
        assert "knowledge" in methods
        assert len(methods) > 0

    def test_cross_domain_relationship_types_property(self):
        """Verify cross_domain_relationship_types returns unique rel type strings."""
        rel_types = TASKS_CONFIG.cross_domain_relationship_types
        assert isinstance(rel_types, list)
        assert len(rel_types) > 0
        # All should be strings (relationship name values)
        assert all(isinstance(rt, str) for rt in rel_types)


class TestHelperFunctions:
    """Test helper functions."""

    def test_get_domain_config(self):
        """Verify get_domain_config returns correct config."""
        config = get_domain_config(Domain.TASKS)
        assert config is not None
        assert config.domain == Domain.TASKS

    def test_get_config_by_label(self):
        """Verify get_config_by_label returns correct config."""
        config = get_config_by_label("Goal")
        assert config is not None
        # entity_label may be "Goal" or "Entity" (unified model)
        assert config.entity_label in ("Goal", "Entity")


class TestCurriculumDomains:
    """Test curriculum domain configurations."""

    def test_ku_config_is_shared_content(self):
        """Verify KU config has shared content settings."""
        config = get_config_by_label("Entity")
        assert config is not None
        assert config.is_shared_content is True
        assert config.ownership_relationship is None

    def test_ls_has_practice_patterns(self):
        """Verify LS config has practice pattern relationships."""
        config = get_config_by_label("Ls")
        rel_names = {r.relationship for r in config.relationships}
        assert RelationshipName.BUILDS_HABIT in rel_names
        assert RelationshipName.ASSIGNS_TASK in rel_names
        assert RelationshipName.SCHEDULES_EVENT in rel_names

    def test_lp_has_milestone_relationship(self):
        """Verify LP config has milestone event relationship."""
        config = get_config_by_label("Lp")
        rel_names = {r.relationship for r in config.relationships}
        assert RelationshipName.HAS_MILESTONE_EVENT in rel_names

    def test_ku_has_organizes_relationship(self):
        """Verify KU config has ORGANIZES relationship for MOC navigation.

        January 2026: MOC is now KU-based. A KU "is" a MOC when it has
        outgoing ORGANIZES relationships (emergent identity).
        """
        config = get_config_by_label("Entity")
        rel_names = {r.relationship for r in config.relationships}
        assert RelationshipName.ORGANIZES in rel_names


class TestNamedUnifiedConfigs:
    """Test named *_CONFIG configs are consistent with registry lookups."""

    def test_activity_unified_configs_match_registry(self):
        """Verify *_CONFIG configs match DOMAIN_CONFIGS entries."""
        assert TASKS_CONFIG is DOMAIN_CONFIGS[Domain.TASKS]
        assert GOALS_CONFIG is DOMAIN_CONFIGS[Domain.GOALS]
        assert HABITS_CONFIG is DOMAIN_CONFIGS[Domain.HABITS]
        assert EVENTS_CONFIG is DOMAIN_CONFIGS[Domain.EVENTS]
        assert CHOICES_CONFIG is DOMAIN_CONFIGS[Domain.CHOICES]
        assert PRINCIPLES_CONFIG is DOMAIN_CONFIGS[Domain.PRINCIPLES]

    def test_curriculum_unified_configs_match_label_registry(self):
        """Verify curriculum *_CONFIG configs match LABEL_CONFIGS entries."""
        assert LESSON_CONFIG is LABEL_CONFIGS["Entity"]
        assert LS_CONFIG is LABEL_CONFIGS["Ls"]
        assert LP_CONFIG is LABEL_CONFIGS["Lp"]

    def test_all_unified_configs_are_domain_relationship_config(self):
        """Verify all named configs are DomainRelationshipConfig."""
        for config in [
            TASKS_CONFIG,
            GOALS_CONFIG,
            HABITS_CONFIG,
            EVENTS_CONFIG,
            CHOICES_CONFIG,
            PRINCIPLES_CONFIG,
            LESSON_CONFIG,
            LS_CONFIG,
            LP_CONFIG,
        ]:
            assert isinstance(config, DomainRelationshipConfig)


class TestRegistryIntegration:
    """Test integration patterns that downstream consumers rely on."""

    def test_relationship_registry_generates_patterns_for_all_domains(self):
        """Verify generator functions produce patterns for all domains."""
        # Activity domains should have generated patterns
        assert len(generate_graph_enrichment("Task")) > 0
        assert len(generate_prerequisite_relationships("Task")) > 0
        assert len(generate_enables_relationships("Task")) > 0

        # Curriculum domains should also have generated patterns
        assert len(generate_graph_enrichment("Entity")) > 0
        assert len(generate_prerequisite_relationships("Entity")) > 0
        assert len(generate_enables_relationships("Entity")) > 0

        # All 9 domains should have enrichment patterns
        all_labels = [
            "Task",
            "Goal",
            "Habit",
            "Event",
            "Choice",
            "Principle",
            "Entity",
            "Ls",
            "Lp",
        ]
        for label in all_labels:
            assert len(generate_graph_enrichment(label)) > 0, f"{label} missing enrichment"

    def test_lp_steps_have_ordering(self):
        """Verify LP config has ordering on step relationships."""
        steps_rel = None
        for rel in LP_CONFIG.relationships:
            if rel.method_key == "steps":
                steps_rel = rel
                break
        assert steps_rel is not None
        assert steps_rel.order_by_property == "sequence"
        assert steps_rel.order_direction == "ASC"
        assert steps_rel.include_edge_properties == ("sequence", "completed")

    def test_ku_organizes_have_ordering(self):
        """Verify KU config has ordering on organizes relationships."""
        organizes_rel = None
        for rel in LESSON_CONFIG.relationships:
            if rel.method_key == "organizes":
                organizes_rel = rel
                break
        assert organizes_rel is not None
        assert organizes_rel.order_by_property == "order"
        assert organizes_rel.order_direction == "ASC"
        assert organizes_rel.include_edge_properties == ("order",)
