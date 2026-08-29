#!/usr/bin/env python3
"""
Bidirectional Relationships Demo
================================

This demo shows how data flows bidirectionally through the SKUEL system:

1. Services ↔ Models: Protocol-based services work with three-tier models
2. Pydantic ↔ DTO ↔ Domain: Data conversion maintains integrity in both directions
3. Cross-domain dependencies: Tasks ↔ Goals ↔ Habits ↔ Knowledge (graph edges)
4. Context awareness: Services modify and read from user context
5. Business logic: Embedded in domain models, accessible from services

Key Architecture Points:
- Protocol injection for clean dependencies
- Three-tier models prevent mixing of concerns
- Result[T] pattern for robust error handling
- GRAPH-NATIVE relationships: multi-UID links (applies_knowledge_uids,
  reinforces_habit_uid, prerequisites) live as Neo4j edges created by the
  service layer — they are NOT persisted node properties on TaskDTO/Task.
"""

import asyncio
from datetime import date, datetime
from typing import Any

from core.models.enums import Priority
from core.models.relationship_names import RelationshipName
from core.models.task.task import Task as Task
from core.models.task.task_dto import TaskDTO
from core.models.task.task_request import TaskCreateRequest
from core.services.tasks.tasks_core_service import TasksCoreService
from core.services.tasks.tasks_scheduling_service import TasksSchedulingService
from core.services.user import UserContext
from core.utils.result_simplified import Errors, Result


class BiDirectionalDemo:
    """Demonstrates bidirectional relationships in SKUEL"""

    def __init__(self) -> None:
        self.created_items: list[Any] = []

    async def demonstrate_full_flow(self):
        """Show complete bidirectional flow through the system"""
        print("🔄 BIDIRECTIONAL RELATIONSHIPS DEMONSTRATION")
        print("=" * 55)

        # 1. Show three-tier bidirectional conversion
        self._demo_three_tier_flow()

        # 2. Show protocol-based service interaction
        await self._demo_protocol_flow()

        # 3. Show cross-domain relationships
        self._demo_cross_domain_flow()

        # 4. Show context-aware operations
        self._demo_context_flow()

        # 5. Show business logic integration
        self._demo_business_logic_flow()

        print("\n" + "=" * 55)
        print("✅ DEMONSTRATION COMPLETE")
        print("\nKey Achievements:")
        print("• Data integrity maintained through all transformations")
        print("• Services interact cleanly through protocols")
        print("• Cross-domain relationships work seamlessly")
        print("• Business logic is accessible and testable")
        print("• Error handling provides rich debugging context")

    def _demo_three_tier_flow(self) -> Any:
        """Demonstrate three-tier model flow"""
        print("\n🏗️  THREE-TIER MODEL FLOW")
        print("-" * 30)

        # External → Transfer → Core → Transfer → External
        print("1. Creating Pydantic request model (External Tier)")
        request = TaskCreateRequest(
            title="Master Advanced Python",
            description="Deep dive into advanced Python concepts",
            priority=Priority.HIGH,
            due_date=date.today(),
            duration_minutes=240,
            project="Learning",
            tags=["python", "advanced", "programming"],
            fulfills_goal_uid="goal_python_mastery",
            applies_knowledge_uids=["ku_decorators", "ku_metaclasses", "ku_async"],
            goal_progress_contribution=0.5,
            knowledge_mastery_check=True,
        )

        print(f"   ✓ Request: {request.title} (Priority: {request.priority.value})")
        print(
            f"      - Relationship-typed fields ({len(request.applies_knowledge_uids)} "
            "knowledge UIDs) become graph edges, not node properties"
        )

        print("2. Converting to DTO (Transfer Tier — persisted node properties only)")
        dto = TaskDTO(
            uid="task_demo_001",
            user_uid="demo_user",
            title=request.title,
            description=request.description,
            priority=request.priority,
            due_date=request.due_date,
            duration_minutes=request.duration_minutes,
            project=request.project,
            tags=request.tags,
            fulfills_goal_uid=request.fulfills_goal_uid,
            source_path_step_uid="ps.python.advanced-concepts",
            goal_progress_contribution=request.goal_progress_contribution,
            knowledge_mastery_check=request.knowledge_mastery_check,
        )

        print(f"   ✓ DTO: {dto.uid} (Mutable, ready for database)")

        print("3. Converting to Domain Model (Core Tier)")
        task = Task.from_dto(dto)

        print(f"   ✓ Domain: {task.uid} (Immutable, with business logic)")
        print(f"      - Learning Alignment: {task.learning_alignment_score():.2f}")
        print(f"      - Source Path Step: {task.source_path_step_uid}")
        print(f"      - Mastery Check: {task.knowledge_mastery_check}")

        print("4. Bidirectional conversion test")
        # Domain → DTO → Dict → DTO → Domain
        dto_back = task.to_dto()
        dict_form = dto_back.to_dict()
        dto_restored = TaskDTO.from_dict(dict_form)
        task_restored = Task.from_dto(dto_restored)

        # Verify integrity
        assert task.title == task_restored.title
        assert task.priority == task_restored.priority
        assert task.fulfills_goal_uid == task_restored.fulfills_goal_uid
        assert task.source_path_step_uid == task_restored.source_path_step_uid
        assert (
            abs(task.learning_alignment_score() - task_restored.learning_alignment_score()) < 0.01
        )

        print("   ✅ Bidirectional integrity verified!")

        return task

    async def _demo_protocol_flow(self) -> Any:
        """Demonstrate protocol-based service interaction"""
        print("\n🔌 PROTOCOL-BASED SERVICE FLOW")
        print("-" * 35)

        print("1. Creating protocol-compliant mock backend")

        class MockTaskBackend:
            def __init__(self) -> None:
                self.tasks: dict[str, dict[str, Any]] = {}
                self.edges: list[tuple[str, str, str, dict[str, Any] | None]] = []

            async def create(
                self, model: Task
            ) -> Result[
                Task
            ]:  # skuel-lint: disable=SKUEL029 -- mock impl of async backend protocol; TasksCoreService awaits it
                task_data = model.to_dto().to_dict()
                task_data.setdefault("created_at", datetime.now().isoformat())
                self.tasks[model.uid] = task_data
                # The real backend returns the round-tripped DOMAIN MODEL
                return Result.ok(model)

            async def create_relationships_batch(
                self, relationships: list[tuple[str, str, str, dict[str, Any] | None]]
            ) -> Result[
                int
            ]:  # skuel-lint: disable=SKUEL029 -- mock impl of async backend protocol; TasksCoreService awaits it
                self.edges.extend(relationships)
                return Result.ok(len(relationships))

            async def get_owner_uids_batch(
                self, uids: list[str]
            ) -> Result[
                dict[str, list[str]]
            ]:  # skuel-lint: disable=SKUEL029 -- mock impl of async backend protocol; the admission guard awaits it
                # Empty map = every UID owned by nobody (shared) → linkable
                return Result.ok({})

            async def get_node_labels_batch(
                self, uids: list[str]
            ) -> Result[
                dict[str, list[str]]
            ]:  # skuel-lint: disable=SKUEL029 -- mock impl of async backend protocol; the admission guard awaits it
                # Every UID carries every label the link fields accept
                return Result.ok(
                    {uid: ["Entity", "Habit", "Ku", "Principle", "Task"] for uid in uids}
                )

            async def get(
                self, task_id: str
            ) -> Result[
                dict[str, Any]
            ]:  # skuel-lint: disable=SKUEL029 -- mock impl of async backend protocol; TasksSchedulingService awaits it
                if task_id in self.tasks:
                    return Result.ok(self.tasks[task_id])
                return Result.fail(Errors.not_found("Task", task_id))

            async def create_task(
                self, data: dict[str, Any]
            ) -> Result[
                dict[str, Any]
            ]:  # skuel-lint: disable=SKUEL029 -- mock impl of async backend protocol; LearningAlignmentBridge awaits it
                self.tasks[data["uid"]] = data
                return Result.ok(data)

            async def get_user_tasks(
                self, user_uid: str
            ) -> Result[
                list
            ]:  # skuel-lint: disable=SKUEL029 -- mock impl of async backend protocol; LearningAlignmentBridge awaits it
                user_tasks = [t for t in self.tasks.values() if t.get("user_uid") == user_uid]
                return Result.ok(user_tasks)

        backend = MockTaskBackend()
        print("   ✓ Mock backend satisfies protocol")

        print("2. Injecting protocol into service")

        service = TasksSchedulingService(
            backend=backend, core=TasksCoreService(backend=backend, event_bus=None)
        )
        print("   ✓ Service created with protocol injection")

        print("3. Service operations through protocol")

        # Create a context with completed prerequisites
        context = UserContext(
            user_uid="demo_user",
            username="demo_user",
            email="demo@example.com",
            display_name="Demo User",
        )
        context.prerequisites_completed = {"ku_python_basics"}

        # Create task through service — relationship-typed fields become edges
        request = TaskCreateRequest(
            title="Protocol Demo Task",
            description="Testing protocol interactions",
            priority=Priority.MEDIUM,
            fulfills_goal_uid="goal_protocol_demo",
            reinforces_habit_uid="habit_daily_code",
            applies_knowledge_uids=["ku_protocols", "ku_dependency_injection"],
            prerequisite_knowledge_uids=["ku_python_basics"],
        )

        result = await service.create_task_with_context(request, context)

        if result.is_ok:
            task = result.value
            print(f"   ✓ Task created: {task.uid}")
            print("      - Through protocol interface")
            print("      - With O(1) prerequisite validation from context")
            print(f"      - Goal: {task.fulfills_goal_uid}")
            print(f"      - GRAPH-NATIVE edges written: {len(backend.edges)}")
            for _from_uid, to_uid, rel_name, _props in backend.edges:
                print(f"        • -[:{rel_name}]-> {to_uid}")
        else:
            print(f"   ❌ Error: {result.error}")

        return service, backend

    def _demo_cross_domain_flow(self) -> Any:
        """Demonstrate cross-domain relationships"""
        print("\n🌐 CROSS-DOMAIN RELATIONSHIP FLOW")
        print("-" * 40)

        print("1. Setting up interconnected domain data")

        # Create user context with cross-domain relationships
        context = UserContext(
            user_uid="cross_domain_user",
            username="cross_domain_user",
            email="cross@example.com",
            display_name="Cross Domain User",
        )

        # Populate with cross-domain data
        context.active_goal_uids = ["goal_learn_python", "goal_build_app"]
        context.active_habit_uids = ["habit_daily_code", "habit_read_docs"]
        context.prerequisites_completed = {"ku_python_basics", "ku_git_basics"}
        context.completed_task_uids = {"task_setup_env", "task_hello_world"}

        print("   ✓ Context populated with cross-domain data")
        print(f"      - {len(context.active_goal_uids)} active goals")
        print(f"      - {len(context.active_habit_uids)} active habits")
        print(f"      - {len(context.prerequisites_completed)} knowledge prerequisites")
        print(f"      - {len(context.completed_task_uids)} completed tasks")

        print("2. Creating task with cross-domain dependencies")

        request = TaskCreateRequest(
            title="Build REST API",
            description="Create a REST API using FastAPI",
            priority=Priority.HIGH,
            fulfills_goal_uid="goal_build_app",  # Links to goal (node property)
            reinforces_habit_uid="habit_daily_code",  # Links to habit (graph edge)
            applies_knowledge_uids=["ku_fastapi", "ku_databases"],  # Graph edges
            prerequisite_knowledge_uids=["ku_python_basics"],  # Graph edges
            goal_progress_contribution=0.3,  # Contributes to goal progress
            knowledge_mastery_check=True,  # Will update knowledge on completion
        )

        print("   ✓ Task request with cross-domain links created")
        print(f"      - Goal: {request.fulfills_goal_uid}")
        print(f"      - Habit: {request.reinforces_habit_uid}")
        print(f"      - Knowledge: {len(request.applies_knowledge_uids)} units")
        print(f"      - Prerequisites: {request.prerequisite_knowledge_uids}")

        print("3. Validating cross-domain relationships")

        # Convert to domain model via the production factory. Only persisted
        # node properties land on Task; relationship-typed request fields are
        # written as graph edges by the service layer after construction.
        task = Task.from_request(request, user_uid=context.user_uid)

        edge_specs: list[tuple[str, list[str]]] = [
            (
                RelationshipName.REINFORCES_HABIT.value,
                [request.reinforces_habit_uid] if request.reinforces_habit_uid else [],
            ),
            (RelationshipName.APPLIES_KNOWLEDGE.value, list(request.applies_knowledge_uids)),
            (RelationshipName.REQUIRES_KNOWLEDGE.value, list(request.prerequisite_knowledge_uids)),
        ]

        has_goal_link = bool(task.fulfills_goal_uid)
        edge_count = sum(len(targets) for _name, targets in edge_specs)

        print("   ✓ Cross-domain validation complete")
        print(f"      - Goal linkage (node property): {'✓' if has_goal_link else '✗'}")
        print(f"      - GRAPH-NATIVE edges to be written: {edge_count}")
        for rel_name, targets in edge_specs:
            for target in targets:
                print(f"        • ({task.uid})-[:{rel_name}]->({target})")

        return task, context

    def _demo_context_flow(self) -> Any:
        """Demonstrate context-aware operations"""
        print("\n🧠 CONTEXT-AWARE OPERATION FLOW")
        print("-" * 40)

        print("1. Creating rich user context")

        context = UserContext(
            user_uid="context_demo_user",
            username="context_demo",
            email="context@example.com",
            display_name="Context Demo User",
        )

        # Simulate rich context state
        context.active_task_uids = ["task_001", "task_002", "task_003"]
        context.completed_task_uids = {"task_completed_001", "task_completed_002"}
        context.active_goal_uids = ["goal_primary", "goal_secondary"]
        context.goal_progress = {"goal_primary": 0.6, "goal_secondary": 0.3}
        context.active_habit_uids = ["habit_exercise", "habit_read"]
        context.habit_streaks = {"habit_exercise": 15, "habit_read": 8}
        context.prerequisites_completed = {"ku_basics", "ku_intermediate"}
        context.knowledge_mastery = {"ku_basics": 0.9, "ku_intermediate": 0.7}

        print("   ✓ Rich context created")
        print(f"      - Active tasks: {len(context.active_task_uids)}")
        print(f"      - Goal progress: {len([g for g in context.goal_progress.values() if g > 0])}")
        print(f"      - Habit streaks: {max(context.habit_streaks.values())}")
        print(f"      - Knowledge mastery: {len(context.knowledge_mastery)}")

        print("2. Context-driven priority calculation")

        # Create task and calculate priority using context
        dto = TaskDTO(
            uid="task_context_demo",
            user_uid="context_demo_user",
            title="Context-Aware Task",
            priority=Priority.MEDIUM,
            fulfills_goal_uid="goal_primary",
            source_path_step_uid="ps.demo.context-awareness",
        )

        task = Task.from_dto(dto)
        alignment = task.learning_alignment_score()

        print(f"   ✓ Task learning alignment: {alignment:.2f}")
        print("      - Path step linkage (0.7 weight)")
        print("      - Knowledge mastery check (0.3 weight)")

        return context

    def _demo_business_logic_flow(self) -> Any:
        """Demonstrate business logic integration"""
        print("\n⚡ BUSINESS LOGIC INTEGRATION FLOW")
        print("-" * 42)

        print("1. Business logic in domain models")

        # Create task with knowledge intelligence data
        dto = TaskDTO(
            uid="task_business_logic",
            user_uid="business_logic_user",
            title="Advanced Algorithm Implementation",
            priority=Priority.HIGH,
            duration_minutes=180,
            fulfills_goal_uid="goal_algorithm_mastery",
            source_path_step_uid="ps.cs.algorithms",
            goal_progress_contribution=0.4,
            knowledge_mastery_check=True,
            knowledge_confidence_scores={
                "ku_algorithms": 0.6,
                "ku_data_structures": 0.8,
                "ku_complexity": 0.4,
            },
            learning_opportunities_count=2,
        )

        task = Task.from_dto(dto)

        print("   ✓ Domain model created with business logic")

        # Test business logic methods
        alignment = task.learning_alignment_score()
        complexity = task.calculate_knowledge_complexity()
        learning_impact = task.calculate_learning_impact()
        will_update_goal = task.validates_knowledge_mastery()

        print(f"      - Learning alignment: {alignment:.2f}")
        print(f"      - Knowledge complexity: {complexity:.2f}")
        print(f"      - Learning impact: {learning_impact:.2f}")
        print(f"      - Validates mastery: {will_update_goal}")

        print("2. Business rules validation")

        # Prerequisite validation is context-based set arithmetic — the same
        # O(1) check create_task_with_context runs against UserContext.
        required_prereqs = {"ku_basic_programming"}
        user_completed_prereqs = {"ku_basic_programming", "ku_python_basics"}
        missing_prereqs = required_prereqs - user_completed_prereqs

        if not missing_prereqs:
            print("   ✓ Prerequisites satisfied - task can start")
        else:
            print(f"   ⚠️  Missing prerequisites: {missing_prereqs}")

        print("3. Complex business calculations")

        # Calculate learning velocity impact from knowledge intelligence data
        knowledge_units = len(task.knowledge_confidence_scores or {})
        goal_contribution = task.goal_progress_contribution
        duration_hours = (task.duration_minutes or 60) / 60

        learning_velocity = (knowledge_units * goal_contribution) / duration_hours
        print(f"   ✓ Learning velocity: {learning_velocity:.2f} units/hour")

        # Calculate completion cascades
        if task.knowledge_mastery_check:
            mastery_increase = 0.1 * knowledge_units  # 10% per unit
            print(f"   ✓ Will increase mastery by: {mastery_increase:.1%}")

        print("4. Service integration with business logic")

        # Show how services use business logic
        alignment_score = task.learning_alignment_score()

        if alignment_score > 0.7:
            scheduling_priority = "HIGH"
        elif alignment_score > 0.4:
            scheduling_priority = "MEDIUM"
        else:
            scheduling_priority = "LOW"

        print(f"   ✓ Scheduling priority: {scheduling_priority}")
        print("      - Calculated from domain model business logic")
        print("      - Used by service for smart scheduling")

        return task


async def main():
    """Run the bidirectional relationships demonstration"""
    demo = BiDirectionalDemo()
    await demo.demonstrate_full_flow()


if __name__ == "__main__":
    asyncio.run(main())
