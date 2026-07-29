"""
Validate ingestion relationship config derives from the registry.

Ingestion configs are generated from the Relationship Registry
(core/models/relationship_registry.py) — the single source of truth.
This eliminates the historical divergence where ingestion used different
relationship types than the runtime services.

Cross-reference: core/services/ingestion/config.py, ADR-026
"""

from core.models.enums.entity_enums import EntityType
from core.models.relationship_names import RelationshipName
from core.models.relationship_registry import ENTITY_TYPE_TO_LABEL, LABEL_CONFIGS
from core.services.ingestion.config import ENTITY_CONFIGS, generate_ingestion_relationship_config

# Curriculum entity types authored EXCLUSIVELY through ingestion: shared content
# built from YAML with no CRUD/API/service relationship authoring. For these,
# ingestion is the only writer, so an outgoing relationship without a
# yaml_field_path is a silent dead seam — it surfaces in graph_context reads but
# nothing in production ever writes it (the bug that hid in ALIGNED_WITH_GOAL,
# EMBODIES_PRINCIPLE, REQUIRES_KNOWLEDGE and HAS_MILESTONE_EVENT on LearningPath).
#
# Exercise is shared content too but is deliberately excluded: it is authored via
# the teacher API, which writes its REQUIRES_KNOWLEDGE edge through
# ExerciseBackend.link_to_curriculum — a real (non-ingestion) writer.
PURE_INGESTION_CURRICULUM = (
    EntityType.LEARNING_PATH,
    EntityType.PATH_STEP,
    EntityType.KU,
)

# Documented, deliberate exemptions: {EntityType: {RelationshipName.value, ...}}.
# Add here (with a code-comment reason) only if a pure-ingestion curriculum config
# ever gains an outgoing relationship written by some mechanism other than ingestion.
_NON_INGESTION_OUTGOING: dict[EntityType, set[str]] = {}


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

    def test_choice_requires_knowledge_for_decision_is_ingestible(self):
        """Choice YAML can author the REQUIRES_KNOWLEDGE_FOR_DECISION prerequisite edge.

        The edge was readable (CHOICE_QUERY_SPECS -> "required_knowledge") before it
        was authorable from frontmatter; #865 gave it a method_key, this gives it a
        yaml_field_path. The field name is deliberately NOT `requires_knowledge` —
        that is Goal's field for the different REQUIRES_KNOWLEDGE edge, and one
        authoring name meaning two edges is the bug shape this module already guards
        for principles (see test_choice_uses_informed_by_principle).
        """
        config = ENTITY_CONFIGS[EntityType.CHOICE].relationship_config
        assert config is not None
        required = config["connections.requires_knowledge_for_decision"]
        assert required["rel_type"] == RelationshipName.REQUIRES_KNOWLEDGE_FOR_DECISION.value
        assert required["target_label"] == "Entity"
        assert required["direction"] == "outgoing"
        # The Goal field of the similar name must still mean the other edge.
        goal_config = ENTITY_CONFIGS[EntityType.GOAL].relationship_config
        assert goal_config is not None
        assert (
            goal_config["connections.requires_knowledge"]["rel_type"]
            == RelationshipName.REQUIRES_KNOWLEDGE.value
        )

    def test_ps_uses_requires_knowledge(self):
        """PathStep ingestion uses REQUIRES_KNOWLEDGE for prerequisites."""
        config = ENTITY_CONFIGS[EntityType.PATH_STEP].relationship_config
        assert config is not None
        assert (
            config["prerequisite_knowledge_uids"]["rel_type"]
            == RelationshipName.REQUIRES_KNOWLEDGE.value
        )
        assert config["prerequisite_knowledge_uids"]["direction"] == "outgoing"

    def test_ku_uses_enables_knowledge(self):
        """KU ingestion uses ENABLES_KNOWLEDGE (unified with registry).

        Previously used ENABLES — accidental divergence from the registry.
        """
        config = ENTITY_CONFIGS[EntityType.PATH_STEP].relationship_config
        assert config is not None
        assert config["connections.enables"]["rel_type"] == RelationshipName.ENABLES_KNOWLEDGE.value

    def test_lp_aligns_with_goal_is_ingestible(self):
        """LP ingestion creates ALIGNED_WITH_GOAL edges from `connections.aligned_goals`.

        Without a yaml_field_path the LP->Goal seam was read in 4 places but never
        written outside tests — the reads could not return data in production.
        """
        config = ENTITY_CONFIGS[EntityType.LEARNING_PATH].relationship_config
        assert config is not None
        aligned = config["connections.aligned_goals"]
        assert aligned["rel_type"] == RelationshipName.ALIGNED_WITH_GOAL.value
        assert aligned["target_label"] == "Goal"
        assert aligned["direction"] == "outgoing"

    def test_lp_graph_context_relationships_are_ingestible(self):
        """All five LP graph-context members are authorable from LP YAML.

        unified_user_context documents the LP graph_context as
        {steps, prerequisite_knowledge, aligned_goals, embodied_principles,
        milestone_events}. Each is read in lp_core_service / _lp_step_mixin /
        user_context_queries, so each needs a production write path — a
        yaml_field_path — or the read returns nothing outside tests.
        """
        config = ENTITY_CONFIGS[EntityType.LEARNING_PATH].relationship_config
        assert config is not None
        expected = {
            "connections.contains_steps": RelationshipName.HAS_STEP,
            "connections.required_knowledge": RelationshipName.REQUIRES_KNOWLEDGE,
            "connections.aligned_goals": RelationshipName.ALIGNED_WITH_GOAL,
            "connections.embodied_principles": RelationshipName.EMBODIES_PRINCIPLE,
            "connections.milestone_events": RelationshipName.HAS_MILESTONE_EVENT,
        }
        for field_path, rel in expected.items():
            assert field_path in config, f"LP graph-context seam {field_path} is not ingestible"
            assert config[field_path]["rel_type"] == rel.value

    def test_pure_ingestion_curriculum_has_no_dead_outgoing_seams(self):
        """Regression guard: ingestion-only curriculum can't read a relationship it never writes.

        LearningPath / PathStep / Ku are built solely from YAML — ingestion is the
        only writer. An outgoing relationship without a yaml_field_path is therefore
        a dead seam: graph_context queries read it, but it can never hold data in
        production. This caught nothing the day it was written (all are wired); it
        exists so the next outgoing relationship added to these configs must declare
        a yaml_field_path or be explicitly exempted in _NON_INGESTION_OUTGOING.
        """
        dead_seams: dict[str, list[str]] = {}
        for entity_type in PURE_INGESTION_CURRICULUM:
            cfg = LABEL_CONFIGS[ENTITY_TYPE_TO_LABEL[entity_type]]
            exempt = _NON_INGESTION_OUTGOING.get(entity_type, set())
            dead = [
                rel.relationship.value
                for rel in cfg.relationships
                if rel.direction == "outgoing"
                and not rel.yaml_field_path
                and rel.relationship.value not in exempt
            ]
            if dead:
                dead_seams[entity_type.value] = dead

        assert not dead_seams, (
            "Dead seams — outgoing relationships read but never written on "
            f"ingestion-only curriculum: {dead_seams}. Add a yaml_field_path so "
            "ingestion creates the edge, or document a non-ingestion writer in "
            "_NON_INGESTION_OUTGOING."
        )

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
        config = ENTITY_CONFIGS[EntityType.PATH_STEP].relationship_config
        assert config is not None
        assert "organizes" in config
        assert config["organizes"]["rel_type"] == RelationshipName.ORGANIZES.value
