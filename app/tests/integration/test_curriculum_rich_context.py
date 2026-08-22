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

        # Create knowledge for step: a related PathStep (CONTAINS_KNOWLEDGE
        # target) plus a genuine Ku (USES_KU target) so knowledge_relationships
        # carries BOTH kinds and the entity_type discriminator can be pinned.
        related_step = CurriculumDTO(
            uid=UIDGenerator.generate_random_uid("ps"),
            title="Python Functions",
            entity_type=EntityType.PATH_STEP,
            domain=Domain.TECH,
        )
        await services.ps.core.backend.create(related_step.to_dict())

        ku = CurriculumDTO(
            uid=UIDGenerator.generate_random_uid("ku"),
            title="First-Class Functions",
            entity_type=EntityType.KU,
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

        # Create relationships — PRODUCTION edge names only. HAS_STEP is the one
        # LP→PS containment edge (RelationshipName.HAS_STEP; written by ingestion
        # and the LP step mixin) and USES_KU is THE composition edge. A fixture
        # writing a phantom edge (the old CONTAINS_STEP here) makes a broken
        # reader look green — the WORKING_ON trap Arc B fixed, again.
        await services.lp.core.backend.driver.execute_query(
            """
            // Enroll user in path
            MATCH (user:User {uid: $user_uid})
            MATCH (lp:LearningPath {uid: $lp_uid})
            CREATE (user)-[:ENROLLED_IN]->(lp)

            // Add step to path
            WITH lp
            MATCH (ps:PathStep {uid: $ps_uid})
            CREATE (lp)-[:HAS_STEP {sequence: 1}]->(ps)

            // Align path with goal
            WITH lp, ps
            MATCH (goal:Goal {uid: $goal_uid})
            CREATE (lp)-[:ALIGNED_WITH_GOAL]->(goal)

            // Step references a related PathStep's knowledge
            WITH ps
            MATCH (related:Entity {uid: $related_step_uid})
            CREATE (ps)-[:CONTAINS_KNOWLEDGE]->(related)

            // Step composes an atomic Ku
            WITH ps
            MATCH (ku:Entity {uid: $ku_uid})
            CREATE (ps)-[:USES_KU]->(ku)

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
                "related_step_uid": related_step.uid,
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

        # Both knowledge edges (USES_KU + CONTAINS_KNOWLEDGE) surface, each
        # carrying the target's entity_type — the label-derived discriminator
        # consumers use to split Ku from PathStep (ADR-013 never-sniff rule) —
        # and rel_type, which separates composition edges from prerequisite/
        # enabled neighbors (bundle.kus takes composition only).
        knowledge_by_uid = {kr["uid"]: kr for kr in step_context["knowledge_relationships"]}
        assert set(knowledge_by_uid) == {ku.uid, related_step.uid}
        assert knowledge_by_uid[ku.uid]["entity_type"] == EntityType.KU.value
        assert knowledge_by_uid[ku.uid]["rel_type"] == "USES_KU"
        assert knowledge_by_uid[related_step.uid]["entity_type"] == EntityType.PATH_STEP.value
        assert knowledge_by_uid[related_step.uid]["rel_type"] == "CONTAINS_KNOWLEDGE"

        # Parent path comes from the HAS_STEP edge; name is read from the
        # Entity `title` property (LP nodes have no `name` property).
        assert step_context["learning_path"] is not None
        assert step_context["learning_path"]["uid"] == learning_path.uid
        assert step_context["learning_path"]["name"] == learning_path.title
        assert step_context["is_sequenced"] is True

        print("✅ MEGA-QUERY curriculum integration complete")
        print(f"   - {len(context.enrolled_paths_rich)} learning paths with rich data")
        print(f"   - {len(context.active_path_steps_rich)} path steps with rich data")

    async def test_practice_projections_scope_to_the_anchored_user(self, services, test_user):
        """ADR-085 G2 pin — practice_habits/practice_tasks re-tie to the anchor.

        A PathStep is SHARED curriculum, so its BUILDS_HABIT/ASSIGNS_TASK edges
        can point at ANY user's activities (the vault-authored habit stamped
        user_admin was the live instance). The nested projections must carry
        `user_uid = user.uid` — another user's habit/task behaves exactly like
        no habit/task at all.

        Fixtures mirror the live writer shapes: activities persist `user_uid`
        as a plain string alongside `:Entity:<Domain>` labels (the CRUD create
        door), and BUILDS_HABIT/ASSIGNS_TASK are the ingestion door's practice
        edges from `habit_uids`/`task_uids` frontmatter.
        """
        driver = services.lp.core.backend.driver
        ps_uid = UIDGenerator.generate_random_uid("ps")
        mine_habit = UIDGenerator.generate_random_uid("habit")
        foreign_habit = UIDGenerator.generate_random_uid("habit")
        mine_task = UIDGenerator.generate_random_uid("task")
        foreign_task = UIDGenerator.generate_random_uid("task")
        fixture_uids = [ps_uid, mine_habit, foreign_habit, mine_task, foreign_task]

        try:
            await driver.execute_query(
                """
                CREATE (ps:Entity:PathStep {uid: $ps_uid, title: 'Shared Lesson',
                                            entity_type: 'path_step'})
                CREATE (mh:Entity:Habit {uid: $mine_habit, title: 'My Practice',
                                         entity_type: 'habit', user_uid: $user_uid})
                CREATE (fh:Entity:Habit {uid: $foreign_habit, title: 'Author Habit',
                                         entity_type: 'habit', user_uid: 'user_someone_else'})
                CREATE (mt:Entity:Task {uid: $mine_task, title: 'My Drill',
                                        entity_type: 'task', user_uid: $user_uid})
                CREATE (ft:Entity:Task {uid: $foreign_task, title: 'Author Task',
                                        entity_type: 'task', user_uid: 'user_someone_else'})
                CREATE (ps)-[:BUILDS_HABIT]->(mh)
                CREATE (ps)-[:BUILDS_HABIT]->(fh)
                CREATE (ps)-[:ASSIGNS_TASK]->(mt)
                CREATE (ps)-[:ASSIGNS_TASK]->(ft)
                WITH ps
                MATCH (user:User {uid: $user_uid})
                CREATE (user)-[:IN_PROGRESS]->(ps)
                SET ps.status = 'active'
                """,
                {
                    "ps_uid": ps_uid,
                    "mine_habit": mine_habit,
                    "foreign_habit": foreign_habit,
                    "mine_task": mine_task,
                    "foreign_task": foreign_task,
                    "user_uid": test_user.uid,
                },
            )

            result = await services.users.get_rich_unified_context(test_user.uid)
            assert result.is_ok, f"Failed to get rich context: {result.error}"
            context = result.value

            steps = {s["step"]["uid"]: s["graph_context"] for s in context.active_path_steps_rich}
            assert ps_uid in steps, "fixture PathStep missing from active steps"
            graph_context = steps[ps_uid]

            habit_uids = {
                h["uid"] for h in graph_context["practice_habits"] if h.get("uid") is not None
            }
            task_uids = {
                t["uid"] for t in graph_context["practice_tasks"] if t.get("uid") is not None
            }

            # Positive control first: the owner's own practice IS projected —
            # without it, an over-broad predicate that drops everything would
            # green the foreign assertions below.
            assert habit_uids == {mine_habit}, f"expected only own habit, got {habit_uids}"
            assert task_uids == {mine_task}, f"expected only own task, got {task_uids}"
        finally:
            await driver.execute_query(
                "MATCH (n:Entity) WHERE n.uid IN $uids DETACH DELETE n",
                {"uids": fixture_uids},
            )
