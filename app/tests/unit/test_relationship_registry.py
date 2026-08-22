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
    ENTRY_REPORT_CONFIG,
    EVENTS_CONFIG,
    GOALS_CONFIG,
    HABITS_CONFIG,
    KU_CONFIG,
    LABEL_CONFIGS,
    LP_CONFIG,
    PRINCIPLES_CONFIG,
    PS_CONFIG,
    TASKS_CONFIG,
    USER_ENTRY_CONFIG,
    DomainRelationshipConfig,
    UnifiedRelationshipDefinition,
    generate_graph_enrichment,
    generate_prerequisite_relationships,
    get_config_by_label,
    get_domain_config,
)


class TestUnifiedRegistry:
    """Test the unified registry structure."""

    def test_registry_has_all_domains(self):
        """Verify all domains are in the registry (6 Activity + 2 Curriculum primaries)."""
        # Note: Domain.KNOWLEDGE maps to KU, Domain.LEARNING maps to PS
        # LP and MOC are only accessible via LABEL_CONFIGS
        expected_domains = {
            Domain.TASKS,
            Domain.GOALS,
            Domain.HABITS,
            Domain.EVENTS,
            Domain.CHOICES,
            Domain.PRINCIPLES,
            Domain.KNOWLEDGE,  # Maps to KU
            Domain.LEARNING,  # Maps to PS
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
            # Curriculum Domains — correct Neo4j label keys
            "Ku",
            "PathStep",
            "LearningPath",
            "Exercise",
            "RevisedExercise",
            # Backward-compat aliases (old label keys)
            "Lesson",  # backward-compat alias -> PS_CONFIG
            "Ls",
            "Lp",
            # Other entities
            "User",
            "PrincipleReflection",
            "UserEntry",
            "EntryReport",
            "Interaction",
        }
        assert set(LABEL_CONFIGS.keys()) == expected_labels

    def test_each_config_is_domain_relationship_config(self):
        """Verify all configs are DomainRelationshipConfig instances."""
        for config in LABEL_CONFIGS.values():
            assert isinstance(config, DomainRelationshipConfig)


class TestEntryReportConfig:
    """Test the learning-loop Phase 3 (EntryReport) registry config."""

    def test_entry_report_registered_by_label(self):
        """Verify EntryReport resolves to ENTRY_REPORT_CONFIG."""
        assert ENTRY_REPORT_CONFIG is LABEL_CONFIGS["EntryReport"]

    def test_entry_report_has_loop_relationships(self):
        """Verify the report edges of the learning loop are declared.

        The student a report is about is its OWNER (universal :OWNS + user_uid),
        not a separate targeting edge — ASSESSMENT_OF was deleted in the C1
        report-visibility convergence (feedback-loop UX arc).
        """
        rel_names = {r.relationship for r in ENTRY_REPORT_CONFIG.relationships}
        assert rel_names == {
            RelationshipName.REPORT_FOR,
            RelationshipName.RESPONDS_TO_REPORT,
        }

    def test_report_for_is_single_outgoing(self):
        """Every EntryReport evaluates exactly one UserEntry (lifecycle rule 2)."""
        report_for = next(
            r
            for r in ENTRY_REPORT_CONFIG.relationships
            if r.relationship is RelationshipName.REPORT_FOR
        )
        assert report_for.direction == "outgoing"
        assert report_for.single is True
        assert report_for.target_label == "UserEntry"

    def test_user_entry_projects_incoming_reports(self):
        """A UserEntry projects its reports (1-to-many: AI + teacher)."""
        report_for = next(
            r
            for r in USER_ENTRY_CONFIG.relationships
            if r.relationship is RelationshipName.REPORT_FOR
        )
        assert report_for.direction == "incoming"
        assert report_for.single is False


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
        assert RelationshipName.BLOCKED_BY in prereqs
        assert RelationshipName.REQUIRES_TASK in prereqs

    def test_goal_prerequisites(self):
        """Verify Goal prerequisite relationships."""
        prereqs = generate_prerequisite_relationships("Goal")
        assert RelationshipName.REQUIRES_KNOWLEDGE in prereqs
        assert RelationshipName.DEPENDS_ON_GOAL in prereqs

    def test_unknown_label_returns_empty(self):
        """Labels outside LABEL_CONFIGS generate no prerequisites."""
        assert generate_prerequisite_relationships("NotARealLabel") == []


class TestEnablesRelationshipNames:
    """Registry-side enables declarations (consumed by the graph contract)."""

    def test_task_enables(self):
        """Verify Task enables relationship declarations."""
        enables = LABEL_CONFIGS["Task"].enables_relationship_names
        assert RelationshipName.BLOCKS in enables
        assert RelationshipName.ENABLES_TASK in enables

    def test_principle_enables(self):
        """Verify Principle enables relationship declarations."""
        enables = LABEL_CONFIGS["Principle"].enables_relationship_names
        assert RelationshipName.GUIDES_GOAL in enables
        assert RelationshipName.INSPIRES_HABIT in enables
        assert RelationshipName.GUIDES_CHOICE in enables


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
        """Verify PathStep (curriculum content) has shared content settings."""
        config = get_config_by_label("PathStep")
        assert config is not None
        assert config.is_shared_content is True

    def test_ls_has_knowledge_relationships(self):
        """Verify PS config has knowledge and step relationships (activity wiring moved to Lessons)."""
        config = get_config_by_label("Ls")
        assert config is not None
        rel_names = {r.relationship for r in config.relationships}
        assert RelationshipName.CONTAINS_KNOWLEDGE in rel_names
        assert RelationshipName.TRAINS_KU in rel_names
        assert RelationshipName.REQUIRES_STEP in rel_names

    def test_lp_has_milestone_relationship(self):
        """Verify LP config has milestone event relationship."""
        config = get_config_by_label("Lp")
        assert config is not None
        rel_names = {r.relationship for r in config.relationships}
        assert RelationshipName.HAS_MILESTONE_EVENT in rel_names

    def test_pathstep_has_organizes_relationship(self):
        """Verify PathStep config has ORGANIZES relationship for MOC navigation.

        An Entity "is" a MOC when it has outgoing ORGANIZES relationships
        (emergent identity). PathStep is the curriculum content entity that
        wires this up in the registry.
        """
        config = get_config_by_label("PathStep")
        assert config is not None
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
        assert PS_CONFIG is LABEL_CONFIGS["PathStep"]
        assert LP_CONFIG is LABEL_CONFIGS["LearningPath"]
        # Backward-compat aliases still work
        assert PS_CONFIG is LABEL_CONFIGS["Lesson"]  # Lesson merged into PathStep
        assert PS_CONFIG is LABEL_CONFIGS["Ls"]
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
            KU_CONFIG,
            PS_CONFIG,
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
        assert len(LABEL_CONFIGS["Task"].enables_relationship_names) > 0

        # Curriculum domains should also have generated patterns
        assert len(generate_graph_enrichment("PathStep")) > 0
        assert len(generate_prerequisite_relationships("PathStep")) > 0
        assert len(LABEL_CONFIGS["PathStep"].enables_relationship_names) > 0

        # All 9 domains should have enrichment patterns
        all_labels = [
            "Task",
            "Goal",
            "Habit",
            "Event",
            "Choice",
            "Principle",
            "PathStep",
            "LearningPath",
            "Ku",
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

    def test_ku_organizes_exists(self):
        """Verify KU config has organizes in bidirectional relationships."""
        organizes_rel = None
        for rel in KU_CONFIG.bidirectional_relationships:
            if isinstance(rel, UnifiedRelationshipDefinition) and rel.method_key == "organizes":
                organizes_rel = rel
                break
        assert organizes_rel is not None
        assert organizes_rel.relationship == RelationshipName.ORGANIZES
        assert organizes_rel.target_label == "Ku"
        assert organizes_rel.direction == "outgoing"
