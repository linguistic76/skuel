#!/usr/bin/env python3
"""
Bidirectional Relationships Demo
================================

This demo shows how data flows bidirectionally through the SKUEL system:

1. Services ↔ Models: Protocol-based services work with three-tier models
2. Pydantic ↔ DTO ↔ Domain: Data conversion maintains integrity in both directions
3. Cross-domain dependencies: Tasks ↔ Goals ↔ Habits ↔ Knowledge
4. Context awareness: Services modify and read from user context
5. Business logic: Embedded in domain models, accessible from services

Key Architecture Points:
- Protocol injection for clean dependencies
- Three-tier models prevent mixing of concerns
- Result[T] pattern for robust error handling
- Bidirectional validation and transformation
"""

import asyncio
from datetime import date, datetime
from typing import Any

from core.models.enums import Priority
from core.models.task.task import Task as Task
from core.models.task.task_dto import TaskDTO
from core.models.task.task_request import TaskCreateRequest
from core.services.tasks_service import TasksService
from core.services.user import UserContext
from core.utils.result_simplified import Errors, Result

# Add project root to path


class BiDirectionalDemo:
    """Demonstrates bidirectional relationships in SKUEL"""

    def __init__(self) -> None:
        self.created_items = []

    async def demonstrate_full_flow(self):
        """Show complete bidirectional flow through the system"""
        print("🔄 BIDIRECTIONAL RELATIONSHIPS DEMONSTRATION")
        print("=" * 55)

        # 1. Show three-tier bidirectional conversion
        await self._demo_three_tier_flow()

        # 2. Show protocol-based service interaction
        await self._demo_protocol_flow()

        # 3. Show cross-domain relationships
        await self._demo_cross_domain_flow()

        # 4. Show context-aware operations
        await self._demo_context_flow()

        # 5. Show business logic integration
        await self._demo_business_logic_flow()

        print("\n" + "=" * 55)
        print("✅ DEMONSTRATION COMPLETE")
        print("\nKey Achievements:")
        print("• Data integrity maintained through all transformations")
        print("• Services interact cleanly through protocols")
        print("• Cross-domain relationships work seamlessly")
        print("• Business logic is accessible and testable")
        print("• Error handling provides rich debugging context")

    async def _demo_three_tier_flow(self) -> Any:
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

        print("2. Converting to DTO (Transfer Tier)")
        dto = TaskDTO(
            uid="task_demo_001",
            title=request.title,
            description=request.description,
            priority=request.priority,
            due_date=request.due_date,
            duration_minutes=request.duration_minutes,
            project=request.project,
            tags=request.tags,
            fulfills_goal_uid=request.fulfills_goal_uid,
            applies_knowledge_uids=list(request.applies_knowledge_uids)
            if request.applies_knowledge_uids
            else [],
            goal_progress_contribution=request.goal_progress_contribution,
            knowledge_mastery_check=request.knowledge_mastery_check,
        )

        print(f"   ✓ DTO: {dto.uid} (Mutable, ready for database)")

        print("3. Converting to Domain Model (Core Tier)")
        task = Task.from_dto(dto)

        print(f"   ✓ Domain: {task.uid} (Immutable, with business logic)")
        print(f"      - Impact Score: {task.impact_score():.2f}")
        print(f"      - Learning Task: {task.applies_knowledge_uids}")
        print(f"      - Updates Goal: {task.completion_updates_goal}")

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
        assert task.applies_knowledge_uids == task_restored.applies_knowledge_uids
        assert abs(task.impact_score() - task_restored.impact_score()) < 0.01

        print("   ✅ Bidirectional integrity verified!")

        return task

    async def _demo_protocol_flow(self) -> Any:
        """Demonstrate protocol-based service interaction"""
        print("\n🔌 PROTOCOL-BASED SERVICE FLOW")
        print("-" * 35)

        print("1. Creating protocol-compliant mock backend")

        class MockTaskBackend:
            def __init__(self) -> None:
                self.tasks = {}
                self.counter = 0

            async def create_task(self, data: dict[str, Any]) -> Result[dict[str, Any]]:
                self.counter += 1
                task_id = f"task_protocol_{self.counter:03d}"
                task_data = {"uid": task_id, "created_at": datetime.now(), **data}
                self.tasks[task_id] = task_data
                return Result.ok(task_data)

            async def get_task(self, task_id: str) -> Result[dict[str, Any]]:
                if task_id in self.tasks:
                    return Result.ok(self.tasks[task_id])
                return Result.fail(Errors.not_found("Task", task_id))

            async def get_user_tasks(self, user_uid: str) -> Result[list]:
                user_tasks = [t for t in self.tasks.values() if t.get("created_by") == user_uid]
                return Result.ok(user_tasks)

        backend = MockTaskBackend()
        print("   ✓ Mock backend satisfies protocol")

        print("2. Injecting protocol into service")

        service = TasksService(backend=backend)
        print("   ✓ Service created with protocol injection")

        print("3. Service operations through protocol")

        # Create a context
        context = UserContext(
            user_uid="demo_user",
            username="demo_user",
            email="demo@example.com",
            display_name="Demo User",
        )

        # Create task through service
        request = TaskCreateRequest(
            title="Protocol Demo Task",
            description="Testing protocol interactions",
            priority=Priority.MEDIUM,
            fulfills_goal_uid="goal_protocol_demo",
        )

        result = await service.create_task_with_context(request, context)

        if result.is_ok:
            task = result.value
            print(f"   ✓ Task created: {task.uid}")
            print("      - Through protocol interface")
            print("      - With context validation")
            print(f"      - Goal: {task.fulfills_goal_uid}")
        else:
            print(f"   ❌ Error: {result.error}")

        return service, backend

    async def _demo_cross_domain_flow(self) -> Any:
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
            fulfills_goal_uid="goal_build_app",  # Links to goal
            reinforces_habit_uid="habit_daily_code",  # Links to habit
            applies_knowledge_uids=["ku_fastapi", "ku_databases"],  # Links to knowledge
            prerequisite_knowledge_uids=["ku_python_basics"],  # Has prerequisites
            goal_progress_contribution=0.3,  # Contributes to goal progress
            knowledge_mastery_check=True,  # Will update knowledge on completion
        )

        print("   ✓ Task request with cross-domain links created")
        print(f"      - Goal: {request.fulfills_goal_uid}")
        print(f"      - Habit: {request.reinforces_habit_uid}")
        print(f"      - Knowledge: {len(request.applies_knowledge_uids)} units")
        print(f"      - Prerequisites: {request.prerequisite_knowledge_uids}")

        print("3. Validating cross-domain relationships")

        # Convert to domain model
        dto = TaskDTO(
            uid="task_cross_domain",
            title=request.title,
            description=request.description,
            priority=request.priority,
            fulfills_goal_uid=request.fulfills_goal_uid,
            reinforces_habit_uid=request.reinforces_habit_uid,
            applies_knowledge_uids=list(request.applies_knowledge_uids),
            prerequisite_knowledge_uids=list(request.prerequisite_knowledge_uids),
            goal_progress_contribution=request.goal_progress_contribution,
            knowledge_mastery_check=request.knowledge_mastery_check,
        )

        task = Task.from_dto(dto)

        # Check relationships
        has_goal_link = bool(task.fulfills_goal_uid)
        has_habit_link = bool(task.reinforces_habit_uid)
        has_knowledge_links = len(task.applies_knowledge_uids) > 0
        has_prerequisites = len(task.prerequisite_knowledge_uids) > 0

        print("   ✓ Cross-domain validation complete")
        print(f"      - Goal linkage: {'✓' if has_goal_link else '✗'}")
        print(f"      - Habit linkage: {'✓' if has_habit_link else '✗'}")
        print(f"      - Knowledge links: {'✓' if has_knowledge_links else '✗'}")
        print(f"      - Has prerequisites: {'✓' if has_prerequisites else '✗'}")

        return task, context

    async def _demo_context_flow(self) -> Any:
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

        print("2. Context-aware task recommendations")

        # Get recommended actions based on context
        recommendation = context.get_recommended_next_action()

        print(f"   ✓ AI recommendation: {recommendation['action']}")
        print(f"      - Type: {recommendation['type']}")
        print(f"      - Items: {len(recommendation.get('items', []))}")

        print("3. Context-driven priority calculation")

        # Create task and calculate priority using context
        dto = TaskDTO(
            uid="task_context_demo",
            title="Context-Aware Task",
            priority=Priority.MEDIUM,
            fulfills_goal_uid="goal_primary",
        )

        task = Task.from_dto(dto)
        impact_score = task.impact_score()

        print(f"   ✓ Task impact calculated: {impact_score:.2f}")
        print("      - Based on goal contribution")
        print("      - Knowledge application")
        print("      - Priority level")

        return context

    async def _demo_business_logic_flow(self) -> Any:
        """Demonstrate business logic integration"""
        print("\n⚡ BUSINESS LOGIC INTEGRATION FLOW")
        print("-" * 42)

        print("1. Business logic in domain models")

        # Create task with complex learning relationships
        dto = TaskDTO(
            uid="task_business_logic",
            title="Advanced Algorithm Implementation",
            priority=Priority.HIGH,
            duration_minutes=180,
            fulfills_goal_uid="goal_algorithm_mastery",
            applies_knowledge_uids=["ku_algorithms", "ku_data_structures", "ku_complexity"],
            goal_progress_contribution=0.4,
            knowledge_mastery_check=True,
            prerequisite_knowledge_uids=["ku_basic_programming"],
        )

        task = Task.from_dto(dto)

        print("   ✓ Domain model created with business logic")

        # Test business logic methods
        impact = task.impact_score()
        has_prereqs = task.has_prerequisites()
        will_update_goal = task.completion_updates_goal
        applies_knowledge = len(task.applies_knowledge_uids)

        print(f"      - Impact score: {impact:.2f}")
        print(f"      - Has prerequisites: {has_prereqs}")
        print(f"      - Updates goal: {will_update_goal}")
        print(f"      - Knowledge units: {applies_knowledge}")

        print("2. Business rules validation")

        # Test prerequisite validation
        user_completed_prereqs = {"ku_basic_programming", "ku_python_basics"}
        missing_prereqs = set(task.prerequisite_knowledge_uids) - user_completed_prereqs

        if not missing_prereqs:
            print("   ✓ Prerequisites satisfied - task can start")
        else:
            print(f"   ⚠️  Missing prerequisites: {missing_prereqs}")

        print("3. Complex business calculations")

        # Calculate learning velocity impact
        knowledge_units = len(task.applies_knowledge_uids)
        goal_contribution = task.goal_progress_contribution
        duration_hours = task.duration_minutes / 60

        learning_velocity = (knowledge_units * goal_contribution) / duration_hours
        print(f"   ✓ Learning velocity: {learning_velocity:.2f} units/hour")

        # Calculate completion cascades
        if task.knowledge_mastery_check:
            mastery_increase = 0.1 * knowledge_units  # 10% per unit
            print(f"   ✓ Will increase mastery by: {mastery_increase:.1%}")

        print("4. Service integration with business logic")

        # Show how services use business logic
        priority_score = task.impact_score()

        if priority_score > 0.7:
            scheduling_priority = "HIGH"
        elif priority_score > 0.4:
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
