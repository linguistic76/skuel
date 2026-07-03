"""
Integration Tests - Curriculum MEGA-QUERY Rich Context
======================================================

Validates that the UserContext MEGA-QUERY (`get_rich_unified_context`) includes
curriculum rich data — enrolled_paths_rich and active_path_steps_rich populated
with full entities and graph neighborhoods.

Per-domain `.core.get_with_context` rich-context overrides for PS/LP were removed
when all curriculum domains converged onto mechanism B for graph context
(intent-traversal ↔ registry convergence, Phase 3); curriculum context is now
served by `.intelligence.get_with_context` via `/api/{path-steps,pathways}/context`.

Date: 2025-11-24
"""

import asyncio

import pytest

from core.models.curriculum_dto import CurriculumDTO
from core.models.enums import Domain
from core.models.enums.entity_enums import EntityType
from core.models.goal.goal_dto import GoalDTO
from core.models.pathways.learning_path_dto import LearningPathDTO
from core.models.pathways.path_step_dto import PathStepDTO
from core.utils.uid_generator import UIDGenerator


@pytest.mark.integration
class TestCurriculumRichContext:
    """Test MEGA-QUERY curriculum rich data in UserContext."""

    async def test_mega_query_curriculum_integration(self, services, test_user):
        """
        Test that MEGA-QUERY includes curriculum rich data in UserContext.

        Validates that enrolled_paths_rich and active_path_steps_rich are
        properly populated with full entities and graph neighborhoods.
        """
        # Create learning path
        learning_path = LearningPathDTO(
            uid=UIDGenerator.generate_random_uid("lp"),
            title="Python Mastery",
            description="Complete Python curriculum",
            domain=Domain.TECH,
        )
        await services.lp.core.backend.create(learning_path)

        # Create path step
        path_step = PathStepDTO(
            uid=UIDGenerator.generate_random_uid("ps"),
            title="Functions Deep Dive",
            intent="Master Python functions",
            description="Master Python functions",
        )
        await services.ps.core.backend.create(path_step)

        # Create goal for alignment
        goal = GoalDTO.create_goal(
            user_uid=test_user.uid,
            title="Master Python",
            domain=Domain.TECH,
        )
        await services.goals.core.backend.create(goal)

        # Create knowledge for step
        ku = CurriculumDTO(
            uid=UIDGenerator.generate_random_uid("ku"),
            title="Python Functions",
            entity_type=EntityType.PATH_STEP,
            domain=Domain.TECH,
        )
        await services.ps.core.backend.create(ku.to_dict())

        # Wait for persistence
        await asyncio.sleep(0.1)

        # Add secondary labels so MEGA-QUERY can find nodes
        # MEGA-QUERY expects :LearningPath, :PathStep, :Goal labels
        await services.lp.core.backend.driver.execute_query(
            """
            MATCH (lp:Entity {uid: $lp_uid}) SET lp:LearningPath
            WITH lp
            MATCH (ps:Entity {uid: $ps_uid}) SET ps:PathStep
            WITH ps
            MATCH (goal:Entity {uid: $goal_uid}) SET goal:Goal
            """,
            {
                "lp_uid": learning_path.uid,
                "ps_uid": path_step.uid,
                "goal_uid": goal.uid,
            },
        )

        # Create relationships
        await services.lp.core.backend.driver.execute_query(
            """
            // Enroll user in path
            MATCH (user:User {uid: $user_uid})
            MATCH (lp:LearningPath {uid: $lp_uid})
            CREATE (user)-[:ENROLLED_IN]->(lp)

            // Add step to path
            WITH lp
            MATCH (ps:PathStep {uid: $ps_uid})
            CREATE (lp)-[:CONTAINS_STEP {sequence: 1}]->(ps)

            // Align path with goal
            WITH lp, ps
            MATCH (goal:Goal {uid: $goal_uid})
            CREATE (lp)-[:ALIGNED_WITH_GOAL]->(goal)

            // Step teaches knowledge
            WITH ps
            MATCH (ku:Entity {uid: $ku_uid})
            CREATE (ps)-[:CONTAINS_KNOWLEDGE]->(ku)

            // User actively studying step — IN_PROGRESS is the edge the PS
            // enrollment door writes (PsMasteryService)
            WITH ps
            MATCH (user:User {uid: $user_uid})
            CREATE (user)-[:IN_PROGRESS]->(ps)
            SET ps.status = 'active'
            """,
            {
                "user_uid": test_user.uid,
                "lp_uid": learning_path.uid,
                "ps_uid": path_step.uid,
                "goal_uid": goal.uid,
                "ku_uid": ku.uid,
            },
        )

        # TEST: Get rich unified context (MEGA-QUERY)
        result = await services.users.get_rich_unified_context(test_user.uid)

        assert result.is_ok, f"Failed to get rich context: {result.error}"

        context = result.value

        # ====================================================================
        # Validate curriculum rich fields are populated
        # ====================================================================

        # Validate enrolled_paths_rich
        assert hasattr(context, "enrolled_paths_rich"), "enrolled_paths_rich missing"
        assert len(context.enrolled_paths_rich) > 0, "No enrolled paths found"

        path_rich = context.enrolled_paths_rich[0]
        assert "path" in path_rich, "path properties missing"
        assert "graph_context" in path_rich, "path graph_context missing"

        # Validate path properties
        path_props = path_rich["path"]
        assert path_props["uid"] == learning_path.uid
        assert path_props.get("name", path_props.get("title")) == learning_path.title

        # Validate path graph context
        path_context = path_rich["graph_context"]
        assert "steps" in path_context
        assert "aligned_goals" in path_context
        assert "total_steps" in path_context
        assert "progress_percentage" in path_context

        # Check that step was included
        assert len(path_context["steps"]) == 1
        assert path_context["steps"][0]["uid"] == path_step.uid

        # Check that goal was included
        assert len(path_context["aligned_goals"]) == 1
        assert path_context["aligned_goals"][0]["uid"] == goal.uid

        # Validate active_path_steps_rich
        assert hasattr(context, "active_path_steps_rich"), "active_path_steps_rich missing"
        assert len(context.active_path_steps_rich) > 0, "No active steps found"

        step_rich = context.active_path_steps_rich[0]
        assert "step" in step_rich, "step properties missing"
        assert "graph_context" in step_rich, "step graph_context missing"

        # Validate step properties
        step_props = step_rich["step"]
        assert step_props["uid"] == path_step.uid
        assert step_props["title"] == path_step.title

        # Validate step graph context
        step_context = step_rich["graph_context"]
        assert "knowledge_relationships" in step_context
        assert "learning_path" in step_context
        assert "is_sequenced" in step_context

        # Check that knowledge relationship was included
        assert len(step_context["knowledge_relationships"]) == 1
        assert step_context["knowledge_relationships"][0]["uid"] == ku.uid

        # Check that parent path was included
        assert step_context["learning_path"] is not None
        assert step_context["learning_path"]["uid"] == learning_path.uid
        assert step_context["is_sequenced"] is True

        print("✅ MEGA-QUERY curriculum integration complete")
        print(f"   - {len(context.enrolled_paths_rich)} learning paths with rich data")
        print(f"   - {len(context.active_path_steps_rich)} path steps with rich data")
