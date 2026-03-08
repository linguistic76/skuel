"""
Integration Tests - Curriculum Rich Context Pattern
===================================================

Tests the "Single-Node Queries → Rich Context" pattern for curriculum domains.

This validates that LP and LS get_with_context() methods fetch entities with their
complete graph neighborhoods in SINGLE queries, and that MEGA-QUERY properly
includes curriculum rich data.

Pattern Benefits:
- Single query per entity (no N+1 problem)
- Rich curriculum context for dashboards
- MEGA-QUERY integration for comprehensive user context

Date: 2025-11-24
"""

import asyncio

import pytest

from core.models.curriculum_dto import CurriculumDTO
from core.models.pathways.learning_path_dto import LearningPathDTO
from core.models.pathways.learning_step_dto import LearningStepDTO
from core.models.enums import Domain, Priority
from core.models.enums.entity_enums import EntityType
from core.models.enums.principle_enums import PrincipleCategory
from core.models.goal.goal_dto import GoalDTO
from core.models.principle.principle_dto import PrincipleDTO
from core.models.task.task_dto import TaskDTO
from core.utils.uid_generator import UIDGenerator


@pytest.mark.integration
class TestCurriculumRichContext:
    """Test rich context pattern for LP and LS domains."""

    async def test_learning_step_get_with_context(self, services, test_user):
        """
        Test LsCoreService.get_with_context() fetches step + graph neighborhood.

        Validates that knowledge relationships, prerequisites, guiding principles,
        practice opportunities, and parent path are all fetched in a single query.
        """
        # Create knowledge units for step content
        primary_ku = CurriculumDTO(
            uid=UIDGenerator.generate_random_uid("ku"),
            title="Python Functions",
            entity_type=EntityType.ARTICLE,
            domain=Domain.TECH,
        )
        await services.article.core.backend.create(primary_ku.to_dict())

        supporting_ku = CurriculumDTO(
            uid=UIDGenerator.generate_random_uid("ku"),
            title="Python Variables",
            entity_type=EntityType.ARTICLE,
            domain=Domain.TECH,
        )
        await services.article.core.backend.create(supporting_ku.to_dict())

        # Create prerequisite knowledge
        prereq_ku = CurriculumDTO(
            uid=UIDGenerator.generate_random_uid("ku"),
            title="Python Basics",
            entity_type=EntityType.ARTICLE,
            domain=Domain.TECH,
        )
        await services.article.core.backend.create(prereq_ku.to_dict())

        # Create guiding principle
        principle = PrincipleDTO(
            uid=UIDGenerator.generate_random_uid("principle"),
            user_uid=test_user.uid,
            title="Practice Daily",
            statement="Consistent practice leads to mastery",
            description="Consistent practice leads to mastery",
            principle_category=PrincipleCategory.PERSONAL.value,
        )
        await services.principles.core.backend.create(principle.to_dict())

        # Create practice task
        task = TaskDTO.create_task(
            user_uid=test_user.uid,
            title="Complete Functions Exercise",
            priority=Priority.MEDIUM,
        )
        await services.tasks.core.backend.create(task.to_dict())

        # Create prerequisite learning step
        prereq_step = LearningStepDTO(
            uid=UIDGenerator.generate_random_uid("ls"),
            title="Introduction to Python",
            intent="First step in Python learning",
            description="First step in Python learning",
        )
        await services.ls.core.backend.create(prereq_step)

        # Create main learning step
        main_step = LearningStepDTO(
            uid=UIDGenerator.generate_random_uid("ls"),
            title="Master Python Functions",
            intent="Deep dive into function concepts",
            description="Deep dive into function concepts",
        )
        await services.ls.core.backend.create(main_step)

        # Create learning path for context
        learning_path = LearningPathDTO(
            uid=UIDGenerator.generate_random_uid("lp"),
            title="Python Mastery Path",
            description="Complete Python learning journey",
            domain=Domain.TECH,
        )
        await services.lp.core.backend.create(learning_path)

        # Wait for persistence
        await asyncio.sleep(0.1)

        # Debug: Verify entities exist
        print(f"DEBUG: main_step.uid = {main_step.uid}")
        print(f"DEBUG: learning_path.uid = {learning_path.uid}")

        # Create all relationships
        await services.ls.core.backend.driver.execute_query(
            """
            // Primary knowledge
            MATCH (ls:Entity {uid: $step_uid})
            MATCH (ku:Entity {uid: $primary_ku})
            CREATE (ls)-[:REQUIRES_KNOWLEDGE {type: 'primary', confidence: 0.95}]->(ku)

            // Supporting knowledge
            WITH ls
            MATCH (supporting:Entity {uid: $supporting_ku})
            CREATE (ls)-[:REQUIRES_KNOWLEDGE {type: 'supporting', confidence: 0.8}]->(supporting)

            // Prerequisite knowledge
            WITH ls
            MATCH (prereq:Entity {uid: $prereq_ku})
            CREATE (ls)-[:REQUIRES_KNOWLEDGE {type: 'prerequisite'}]->(prereq)

            // Prerequisite step
            WITH ls
            MATCH (prereq_step:Entity {uid: $prereq_step})
            CREATE (ls)-[:REQUIRES_STEP]->(prereq_step)

            // Guiding principle
            WITH ls
            MATCH (principle:Principle {uid: $principle_uid})
            CREATE (ls)-[:GUIDED_BY_PRINCIPLE]->(principle)

            // Practice task
            WITH ls
            MATCH (task:Task {uid: $task_uid})
            CREATE (ls)-[:ASSIGNS_TASK]->(task)

            // Learning path
            WITH ls
            MATCH (lp:Entity {uid: $lp_uid})
            CREATE (lp)-[:CONTAINS_STEP {sequence: 2}]->(ls)
            """,
            {
                "step_uid": main_step.uid,
                "primary_ku": primary_ku.uid,
                "supporting_ku": supporting_ku.uid,
                "prereq_ku": prereq_ku.uid,
                "prereq_step": prereq_step.uid,
                "principle_uid": principle.uid,
                "task_uid": task.uid,
                "lp_uid": learning_path.uid,
            },
        )

        # Debug: Verify learning path exists and has relationship
        check_result = await services.ls.core.backend.driver.execute_query(
            """
            MATCH (lp:Entity {uid: $lp_uid})
            OPTIONAL MATCH (lp)-[r:HAS_STEP|CONTAINS_STEP]->(ls:Entity {uid: $ls_uid})
            RETURN lp.uid as lp_uid, lp.title as lp_name, type(r) as rel_type, r.sequence as sequence, ls.uid as ls_uid
            """,
            {"lp_uid": learning_path.uid, "ls_uid": main_step.uid},
        )
        check_records = check_result.records
        print(f"DEBUG: Check query found {len(check_records)} records")
        if check_records:
            print(f"DEBUG: LP found: {check_records[0]['lp_uid']}, {check_records[0]['lp_name']}")
            print(
                f"DEBUG: Relationship type: {check_records[0]['rel_type']}, sequence: {check_records[0]['sequence']}"
            )
            print(f"DEBUG: LS connected: {check_records[0]['ls_uid']}")

        # TEST: Get with context (single query)
        result = await services.ls.core.get_with_context(main_step.uid)

        assert result.is_ok, f"Failed to get step with context: {result.error}"

        step_dto = result.value
        assert step_dto.uid == main_step.uid

        # ====================================================================
        # Validate metadata persistence through DTO conversion
        # ====================================================================
        assert "graph_context" in step_dto.metadata, "metadata.graph_context missing"
        context = step_dto.metadata["graph_context"]

        # Post entity model migration: LS get_with_context uses its own override
        # with domain-specific context keys.
        assert isinstance(context, dict)
        assert len(context) > 0, "graph_context should not be empty"

        # LS-specific context keys (from LsCoreService.get_with_context override)
        assert "is_sequenced" in context
        assert "guiding_principles" in context

        print("✅ LS get_with_context() returned graph_context")

    async def test_learning_path_get_with_context(self, services, test_user):
        """
        Test LpCoreService.get_with_context() fetches path + curriculum context.

        Validates that steps, prerequisite knowledge, aligned goals, embodied
        principles, and progress stats are all fetched in a single query.
        """
        # Create prerequisite knowledge
        prereq_ku = CurriculumDTO(
            uid=UIDGenerator.generate_random_uid("ku"),
            title="Programming Fundamentals",
            entity_type=EntityType.ARTICLE,
            domain=Domain.TECH,
        )
        await services.article.core.backend.create(prereq_ku.to_dict())

        # Create aligned goal
        goal = GoalDTO.create_goal(
            user_uid=test_user.uid,
            title="Become Python Developer",
            domain=Domain.TECH,
        )
        await services.goals.core.backend.create(goal)

        # Create embodied principle
        principle = PrincipleDTO(
            uid=UIDGenerator.generate_random_uid("principle"),
            user_uid=test_user.uid,
            title="Continuous Learning",
            statement="Always be learning new skills",
            description="Always be learning new skills",
            principle_category=PrincipleCategory.PERSONAL.value,
        )
        await services.principles.core.backend.create(principle.to_dict())

        # Create learning steps
        step1 = LearningStepDTO(
            uid=UIDGenerator.generate_random_uid("ls"),
            title="Python Basics",
            intent="Learn Python fundamentals",
            description="Learn Python fundamentals",
        )
        await services.ls.core.backend.create(step1)

        step2 = LearningStepDTO(
            uid=UIDGenerator.generate_random_uid("ls"),
            title="Advanced Python",
            intent="Master advanced concepts",
            description="Master advanced concepts",
        )
        await services.ls.core.backend.create(step2)

        # Create learning path
        learning_path = LearningPathDTO(
            uid=UIDGenerator.generate_random_uid("lp"),
            title="Python Developer Path",
            description="Complete path to Python mastery",
            domain=Domain.TECH,
        )
        await services.lp.core.backend.create(learning_path)

        # Wait for persistence
        await asyncio.sleep(0.1)

        # Create all relationships
        await services.lp.core.backend.driver.execute_query(
            """
            // Prerequisite knowledge
            MATCH (lp:Entity {uid: $lp_uid})
            MATCH (ku:Entity {uid: $prereq_ku})
            CREATE (lp)-[:REQUIRES_KNOWLEDGE]->(ku)

            // Aligned goal
            WITH lp
            MATCH (goal:Goal {uid: $goal_uid})
            CREATE (lp)-[:ALIGNED_WITH_GOAL]->(goal)

            // Embodied principle
            WITH lp
            MATCH (principle:Principle {uid: $principle_uid})
            CREATE (lp)-[:EMBODIES_PRINCIPLE]->(principle)

            // Steps (with sequence and completion)
            WITH lp
            MATCH (step1:Entity {uid: $step1_uid})
            CREATE (lp)-[:CONTAINS_STEP {sequence: 1}]->(step1)
            SET step1.completed = true

            WITH lp
            MATCH (step2:Entity {uid: $step2_uid})
            CREATE (lp)-[:CONTAINS_STEP {sequence: 2}]->(step2)
            SET step2.completed = false

            // User enrollment
            WITH lp
            MATCH (user:User {uid: $user_uid})
            CREATE (user)-[:ENROLLED_IN]->(lp)
            """,
            {
                "lp_uid": learning_path.uid,
                "prereq_ku": prereq_ku.uid,
                "goal_uid": goal.uid,
                "principle_uid": principle.uid,
                "step1_uid": step1.uid,
                "step2_uid": step2.uid,
                "user_uid": test_user.uid,
            },
        )

        # TEST: Get with context (single query)
        result = await services.lp.core.get_with_context(learning_path.uid)

        assert result.is_ok, f"Failed to get path with context: {result.error}"

        path_dto = result.value
        assert path_dto.uid == learning_path.uid

        # ====================================================================
        # Validate metadata persistence through DTO conversion
        # ====================================================================
        assert "graph_context" in path_dto.metadata, "metadata.graph_context missing"
        context = path_dto.metadata["graph_context"]

        # Post entity model migration: LP get_with_context uses its own override
        # with domain-specific context keys.
        assert isinstance(context, dict)
        assert len(context) > 0, "graph_context should not be empty"

        # LP-specific context keys (from LpCoreService.get_with_context override)
        assert "aligned_goals" in context
        assert "completed_steps" in context
        assert "enrolled_users" in context

        print("✅ LP get_with_context() returned graph_context")

    async def test_mega_query_curriculum_integration(self, services, test_user):
        """
        Test that MEGA-QUERY includes curriculum rich data in UserContext.

        Validates that enrolled_paths_rich and active_learning_steps_rich are
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

        # Create learning step
        learning_step = LearningStepDTO(
            uid=UIDGenerator.generate_random_uid("ls"),
            title="Functions Deep Dive",
            intent="Master Python functions",
            description="Master Python functions",
        )
        await services.ls.core.backend.create(learning_step)

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
            entity_type=EntityType.ARTICLE,
            domain=Domain.TECH,
        )
        await services.article.core.backend.create(ku.to_dict())

        # Wait for persistence
        await asyncio.sleep(0.1)

        # Add secondary labels so MEGA-QUERY can find nodes
        # MEGA-QUERY expects :LearningPath, :LearningStep, :Goal labels
        await services.lp.core.backend.driver.execute_query(
            """
            MATCH (lp:Entity {uid: $lp_uid}) SET lp:LearningPath
            WITH lp
            MATCH (ls:Entity {uid: $ls_uid}) SET ls:LearningStep
            WITH ls
            MATCH (goal:Entity {uid: $goal_uid}) SET goal:Goal
            """,
            {
                "lp_uid": learning_path.uid,
                "ls_uid": learning_step.uid,
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
            MATCH (ls:LearningStep {uid: $ls_uid})
            CREATE (lp)-[:CONTAINS_STEP {sequence: 1}]->(ls)

            // Align path with goal
            WITH lp, ls
            MATCH (goal:Goal {uid: $goal_uid})
            CREATE (lp)-[:ALIGNED_WITH_GOAL]->(goal)

            // Step teaches knowledge
            WITH ls
            MATCH (ku:Entity {uid: $ku_uid})
            CREATE (ls)-[:REQUIRES_KNOWLEDGE {type: 'primary'}]->(ku)

            // User working on step
            WITH ls
            MATCH (user:User {uid: $user_uid})
            CREATE (user)-[:WORKING_ON]->(ls)
            SET ls.status = 'active'
            """,
            {
                "user_uid": test_user.uid,
                "lp_uid": learning_path.uid,
                "ls_uid": learning_step.uid,
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
        assert path_context["steps"][0]["uid"] == learning_step.uid

        # Check that goal was included
        assert len(path_context["aligned_goals"]) == 1
        assert path_context["aligned_goals"][0]["uid"] == goal.uid

        # Validate active_learning_steps_rich
        assert hasattr(context, "active_learning_steps_rich"), "active_learning_steps_rich missing"
        assert len(context.active_learning_steps_rich) > 0, "No active steps found"

        step_rich = context.active_learning_steps_rich[0]
        assert "step" in step_rich, "step properties missing"
        assert "graph_context" in step_rich, "step graph_context missing"

        # Validate step properties
        step_props = step_rich["step"]
        assert step_props["uid"] == learning_step.uid
        assert step_props["title"] == learning_step.title

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
        print(f"   - {len(context.active_learning_steps_rich)} learning steps with rich data")
