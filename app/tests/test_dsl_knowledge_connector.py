"""
Tests for DSL Knowledge Graph Connector
=======================================

Tests the semantic graph connection planning from DSL-parsed activities.
"""

import pytest

from core.infrastructure.relationships.semantic_relationships import (
    SemanticRelationshipType,
)
from core.services.dsl import (
    DSLKnowledgeConnector,
    KnowledgeConnection,
    parse_journal_text,
    plan_activity_connections,
    plan_journal_connections,
)


class TestKnowledgeConnectionPlanning:
    """Test knowledge unit connection planning."""

    def test_plan_ku_connection(self):
        """@ku() tag creates knowledge connection."""
        result = parse_journal_text(
            "- [ ] Study Python decorators @context(task) @ku(ku:tech/python-decorators)"
        )
        assert result.is_ok

        activity = result.value.get_tasks()[0]
        plan = plan_activity_connections(activity)

        assert plan.has_knowledge_links
        assert len(plan.knowledge_connections) == 1

        conn = plan.knowledge_connections[0]
        assert conn.target_uid == "ku:tech/python-decorators"
        assert conn.confidence == 0.9  # Primary KU gets higher confidence

    def test_plan_multiple_ku_connections(self):
        """Multiple @link(ku:) tags create multiple connections."""
        result = parse_journal_text(
            "- [ ] Build API @context(task) @ku(ku:tech/rest) @link(ku:tech/python)"
        )
        assert result.is_ok

        activity = result.value.get_tasks()[0]
        plan = plan_activity_connections(activity)

        assert len(plan.knowledge_connections) == 2

        target_uids = {c.target_uid for c in plan.knowledge_connections}
        assert "ku:tech/rest" in target_uids
        assert "ku:tech/python" in target_uids

    def test_learning_context_uses_informed_by(self):
        """Learning context uses INFORMED_BY_KNOWLEDGE relationship."""
        result = parse_journal_text("- [ ] Learn async @context(task,learning) @ku(ku:tech/async)")
        assert result.is_ok

        activity = result.value.get_tasks()[0]
        plan = plan_activity_connections(activity)

        conn = plan.knowledge_connections[0]
        assert conn.relationship_type == SemanticRelationshipType.INFORMED_BY_KNOWLEDGE

    def test_habit_context_uses_reinforces(self):
        """Habit context uses REINFORCES_KNOWLEDGE relationship."""
        result = parse_journal_text(
            "- [ ] Practice meditation @context(habit) @ku(ku:wellness/meditation)"
        )
        assert result.is_ok

        activity = result.value.get_habits()[0]
        plan = plan_activity_connections(activity)

        conn = plan.knowledge_connections[0]
        assert conn.relationship_type == SemanticRelationshipType.REINFORCES_KNOWLEDGE

    def test_event_context_uses_practices_via(self):
        """Event context uses PRACTICES_VIA_EVENT relationship."""
        result = parse_journal_text("- [ ] Python meetup @context(event) @ku(ku:tech/python)")
        assert result.is_ok

        activity = result.value.get_events()[0]
        plan = plan_activity_connections(activity)

        conn = plan.knowledge_connections[0]
        assert conn.relationship_type == SemanticRelationshipType.PRACTICES_VIA_EVENT

    def test_task_context_uses_applies_to(self):
        """Task context uses APPLIES_KNOWLEDGE_TO relationship."""
        result = parse_journal_text("- [ ] Build feature @context(task) @ku(ku:tech/react)")
        assert result.is_ok

        activity = result.value.get_tasks()[0]
        plan = plan_activity_connections(activity)

        conn = plan.knowledge_connections[0]
        assert conn.relationship_type == SemanticRelationshipType.APPLIES_KNOWLEDGE_TO


class TestGoalConnectionPlanning:
    """Test goal connection planning."""

    def test_plan_goal_connection(self):
        """@link(goal:) creates goal connection."""
        result = parse_journal_text("- [ ] Exercise @context(task) @link(goal:health/fitness)")
        assert result.is_ok

        activity = result.value.get_tasks()[0]
        plan = plan_activity_connections(activity)

        assert plan.has_goal_links
        assert len(plan.goal_connections) == 1

        conn = plan.goal_connections[0]
        assert conn.goal_uid == "goal:health/fitness"
        assert conn.relationship_type == SemanticRelationshipType.CONTRIBUTES_TO_GOAL

    def test_goal_weight_based_on_priority(self):
        """Higher priority tasks have higher goal contribution weight."""
        # Priority 1 (critical) -> weight 2.0
        result = parse_journal_text(
            "- [ ] Critical task @context(task) @priority(1) @link(goal:test)"
        )
        activity = result.value.get_tasks()[0]
        plan = plan_activity_connections(activity)
        assert plan.goal_connections[0].contribution_weight == 2.0

        # Priority 3 (medium) -> weight 1.0
        result = parse_journal_text(
            "- [ ] Medium task @context(task) @priority(3) @link(goal:test)"
        )
        activity = result.value.get_tasks()[0]
        plan = plan_activity_connections(activity)
        assert plan.goal_connections[0].contribution_weight == 1.0

        # Priority 5 (low) -> weight 0.5
        result = parse_journal_text("- [ ] Low task @context(task) @priority(5) @link(goal:test)")
        activity = result.value.get_tasks()[0]
        plan = plan_activity_connections(activity)
        assert plan.goal_connections[0].contribution_weight == 0.5


class TestPrincipleConnectionPlanning:
    """Test principle connection planning."""

    def test_plan_principle_connection(self):
        """@link(principle:) creates principle connection."""
        result = parse_journal_text("- [ ] Meditate @context(habit) @link(principle:mindfulness)")
        assert result.is_ok

        activity = result.value.get_habits()[0]
        plan = plan_activity_connections(activity)

        assert len(plan.principle_connections) == 1

        conn = plan.principle_connections[0]
        assert conn.principle_uid == "principle:mindfulness"
        assert conn.relationship_type == SemanticRelationshipType.ALIGNS_WITH_PRINCIPLE


class TestJournalConnectionPlanning:
    """Test connection planning for full journals."""

    def test_plan_journal_connections(self):
        """Plan connections for entire journal."""
        journal = """
### Morning Focus

- [ ] Review architecture docs @context(task,learning) @ku(ku:tech/architecture) @link(goal:tech/mastery)
- [ ] Morning meditation @context(habit) @ku(ku:wellness/meditation) @link(principle:mindfulness)
- [ ] Team standup @context(event) @link(goal:work/collaboration)

Some other text without DSL tags...
"""
        result = parse_journal_text(journal)
        assert result.is_ok

        plans = plan_journal_connections(result.value)

        # Should have 3 plans (one per activity with connections)
        assert len(plans) == 3

        # Total connections across all plans
        total = sum(p.total_connections for p in plans)
        assert total == 5  # 2 + 2 + 1

    def test_empty_journal_returns_empty_plans(self):
        """Journal with no DSL activities returns empty list."""
        result = parse_journal_text("Just some regular text")
        assert result.is_ok

        plans = plan_journal_connections(result.value)
        assert plans == []


class TestConnectionPlanSerialization:
    """Test DSLConnectionPlan serialization."""

    def test_to_dict(self):
        """Connection plan serializes to dict."""
        result = parse_journal_text("- [ ] Task @context(task) @ku(ku:test) @link(goal:test-goal)")
        activity = result.value.get_tasks()[0]
        plan = plan_activity_connections(activity)

        d = plan.to_dict()

        assert d["activity"] == "Task"
        assert d["total_connections"] == 2
        assert len(d["knowledge_connections"]) == 1
        assert len(d["goal_connections"]) == 1
        assert d["knowledge_connections"][0]["target"] == "ku:test"
        assert d["goal_connections"][0]["goal"] == "goal:test-goal"


class TestDSLKnowledgeConnector:
    """Test DSLKnowledgeConnector class directly."""

    def test_connector_initialization(self):
        """Connector initializes properly."""
        connector = DSLKnowledgeConnector()
        assert connector is not None

    def test_plan_connections_with_source_uid(self):
        """Planning with source_uid sets it in connections."""
        result = parse_journal_text("- [ ] Task @context(task) @ku(ku:test)")
        activity = result.value.get_tasks()[0]

        connector = DSLKnowledgeConnector()
        plan = connector.plan_connections(activity, source_uid="task:123")

        conn = plan.knowledge_connections[0]
        assert conn.source_uid == "task:123"

    def test_plan_connections_without_source_uid(self):
        """Planning without source_uid uses placeholder."""
        result = parse_journal_text("- [ ] Task @context(task) @ku(ku:test)")
        activity = result.value.get_tasks()[0]

        connector = DSLKnowledgeConnector()
        plan = connector.plan_connections(activity)

        conn = plan.knowledge_connections[0]
        assert conn.source_uid == "pending:activity"


class TestKnowledgeConnectionDataClass:
    """Test KnowledgeConnection dataclass."""

    def test_to_cypher_params(self):
        """KnowledgeConnection generates Cypher parameters."""
        conn = KnowledgeConnection(
            source_uid="task:123",
            target_uid="ku:tech/python",
            relationship_type=SemanticRelationshipType.APPLIES_KNOWLEDGE_TO,
            confidence=0.9,
            metadata={"is_primary": True},
        )

        params = conn.to_cypher_params()

        assert params["source_uid"] == "task:123"
        assert params["target_uid"] == "ku:tech/python"
        assert params["rel_type"] == "cross:applies_knowledge_to"
        assert params["confidence"] == 0.9
        assert params["source"] == "dsl_parser"
        assert params["is_primary"] is True
        assert "created_at" in params


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
