"""
Two-phase bulk ingest templates — nodes first, relationships second.

Relationship Cypher MATCHes targets (no stub nodes), so edges to entities
persisted later in the same sync would silently drop — and under incremental
sync the unchanged source file is never retried, losing the edge forever.
These tests pin the split templates plus the registry-driven ``order_property``
support (HAS_STEP ``sequence``, ORGANIZES ``order``) that persists YAML list
order onto edges.
"""

from __future__ import annotations

from adapters.persistence.neo4j.bulk_upsert_backend import (
    build_node_upsert_template,
    build_relationship_template,
)
from core.ingestion.ingestion_types import RelationshipConfig
from core.models.enums.entity_enums import EntityType
from core.services.ingestion.config import generate_ingestion_relationship_config


class TestNodeUpsertTemplate:
    def test_node_template_uses_filtered_props_and_no_edges(self) -> None:
        template = build_node_upsert_template("PathStep", "Entity")

        assert "item._node_props" in template.template
        assert "MERGE (n:Entity:PathStep {uid: item.uid})" in template.template
        assert "MATCH (target" not in template.template


class TestRelationshipTemplate:
    def test_relationships_template_matches_source_node(self) -> None:
        """Phase 2 MATCHes the already-upserted node — it never re-writes props."""
        config = {
            "uses_kus": RelationshipConfig(
                rel_type="USES_KU", target_label="Ku", direction="outgoing"
            ),
        }
        template = build_relationship_template("PathStep", "Entity", config)

        assert "MATCH (n:Entity:PathStep {uid: item.uid})" in template.template
        assert "MERGE (n)-[_r:USES_KU]->(target)" in template.template
        assert "ON CREATE SET" not in template.template

    def test_unordered_field_has_no_order_set(self) -> None:
        config = {
            "uses_kus": RelationshipConfig(
                rel_type="USES_KU", target_label="Ku", direction="outgoing"
            ),
        }
        template = build_relationship_template("PathStep", "Entity", config)

        assert "SET _r." not in template.template
        assert "range(" not in template.template

    def test_ordered_field_persists_list_index(self) -> None:
        """order_property fields write the 0-based YAML list index on the edge."""
        config = {
            "connections.contains_steps": RelationshipConfig(
                rel_type="HAS_STEP",
                target_label="Entity",
                direction="outgoing",
                order_property="sequence",
            ),
        }
        template = build_relationship_template("LearningPath", "Entity", config)

        assert "UNWIND range(0, size(_target_uids) - 1) AS _idx" in template.template
        assert "SET _r.`sequence` = _idx" in template.template

    def test_incoming_direction_points_back_to_source(self) -> None:
        config = {
            "learning_path_uids": RelationshipConfig(
                rel_type="HAS_STEP", target_label="Entity", direction="incoming"
            ),
        }
        template = build_relationship_template("PathStep", "Entity", config)

        assert "MERGE (n)<-[_r:HAS_STEP]-(target)" in template.template


class TestRegistryOrderPropertyPassthrough:
    def test_lp_contains_steps_carries_sequence(self) -> None:
        """The registry's order_by_property reaches the ingestion config."""
        config = generate_ingestion_relationship_config(EntityType.LEARNING_PATH)

        assert config is not None
        steps = config["connections.contains_steps"]
        assert steps["rel_type"] == "HAS_STEP"
        assert steps["order_property"] == "sequence"

    def test_unordered_fields_omit_order_property(self) -> None:
        config = generate_ingestion_relationship_config(EntityType.LEARNING_PATH)

        assert config is not None
        required = config["connections.required_knowledge"]
        assert "order_property" not in required
