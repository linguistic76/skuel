"""
Validate ingestion relationship config correctness.

Prevents future regressions like the Goal/Choice principle relationship swap
where GUIDED_BY_PRINCIPLE and ALIGNED_WITH_PRINCIPLE were cross-wired.

Cross-reference: core/services/ingestion/config.py
"""

from core.models.relationship_names import RelationshipName
from core.models.shared_enums import EntityType
from core.services.ingestion.config import ENTITY_CONFIGS


class TestIngestionRelationshipConfig:
    """Verify ingestion config rel_types match what service layer expects."""

    def test_goal_uses_guided_by_principle(self):
        """Goals use GUIDED_BY_PRINCIPLE for Goal->Principle edges.

        Service layer references:
          - goal.py:144, goals_recommendation_service.py:169, GOALS_UNIFIED registry
        """
        config = ENTITY_CONFIGS[EntityType.GOAL].relationship_config
        assert config is not None
        assert (
            config["connections.aligned_with_principle"]["rel_type"]
            == RelationshipName.GUIDED_BY_PRINCIPLE.value
        )

    def test_choice_uses_aligned_with_principle(self):
        """Choices use ALIGNED_WITH_PRINCIPLE for Choice->Principle edges.

        Service layer references:
          - choice.py:149, choices_search_service.py:484, CHOICES_UNIFIED registry
        """
        config = ENTITY_CONFIGS[EntityType.CHOICE].relationship_config
        assert config is not None
        assert (
            config["connections.guided_by_principle"]["rel_type"]
            == RelationshipName.ALIGNED_WITH_PRINCIPLE.value
        )

    def test_ku_uses_prerequisite_not_requires_knowledge(self):
        """KU ingestion intentionally uses PREREQUISITE (KU-to-KU), not REQUIRES_KNOWLEDGE (cross-domain).

        PREREQUISITE is queried by: adaptive_sel_service, user_progress_service,
        jupyter_neo4j_sync, lp_intelligence_service, batch_operation_helper.
        """
        config = ENTITY_CONFIGS[EntityType.KU].relationship_config
        assert config is not None
        assert (
            config["connections.requires"]["rel_type"]
            == RelationshipName.PREREQUISITE.value
        )

    def test_ku_uses_enables_not_enables_knowledge(self):
        """KU ingestion intentionally uses ENABLES (KU-to-KU), not ENABLES_KNOWLEDGE (cross-domain).

        ENABLES is queried by: adaptive_sel_service, search_router, search config,
        jupyter_neo4j_sync, lp_intelligence_service.
        """
        config = ENTITY_CONFIGS[EntityType.KU].relationship_config
        assert config is not None
        assert (
            config["connections.enables"]["rel_type"]
            == RelationshipName.ENABLES.value
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
