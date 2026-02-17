"""
100% Dynamic Architecture Example
==================================

This example demonstrates SKUEL's complete dynamic architecture where:
1. Model changes automatically ripple to query methods (DynamicQueryBuilder)
2. Field metadata automatically creates indexes (Neo4jSchemaManager)
3. Relationship declarations automatically generate methods (@relationship decorator)

NO MANUAL ADAPTER CODE NEEDED!
"""

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums import RelationshipType
from core.utils.relationship_decorator import add_relationships

# ============================================================================
# STEP 1: Define Your Domain Model
# ============================================================================


class Priority(str, Enum):
    """Example enum for demonstration"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class Task:
    """
    Domain model with index metadata.

    NOTICE: We use field(metadata={'index': True}) to declare indexes.
    The Neo4jSchemaManager will automatically create these indexes!
    """

    # Primary key - unique index
    uid: str = field(metadata={"index": True, "unique": True})

    # Commonly queried fields - regular indexes
    title: str
    priority: Priority = field(default=Priority.MEDIUM, metadata={"index": True})
    status: str = field(default="draft", metadata={"index": True})

    # Date fields - indexed for date-range queries
    due_date: date | None = field(default=None, metadata={"index": True})
    created_at: datetime = field(default_factory=datetime.now)

    # Regular fields - no index
    description: str | None = None
    estimated_hours: float | None = None  # NEW FIELD - instantly queryable!


@dataclass(frozen=True)
class Goal:
    """Goal model for relationship demonstration"""

    uid: str = field(metadata={"index": True, "unique": True})
    title: str
    target_date: date | None = None


# ============================================================================
# STEP 2: Set Up Backend with Relationship Methods
# ============================================================================


# ============================================================================
# 100% Dynamic Pattern - No Wrapper Classes Needed
# ============================================================================
# Create backend instance directly, then add relationships
def create_task_backend_dynamic(driver):
    """100% Dynamic Pattern - Direct instance with add_relationships()"""
    tasks_backend = UniversalNeo4jBackend[Task](driver, "Task", Task)

    # Add relationship methods to the instance
    return add_relationships(
        tasks_backend,
        (RelationshipType.CONTRIBUTES_TO_GOAL, "Goal", False, None),
        (RelationshipType.REQUIRES_KNOWLEDGE, "Ku", False, None),
    )

    # Now tasks_backend has: link_to_goal(), link_to_knowledge(), etc.


# ============================================================================
# STEP 3: Demonstrate Dynamic Query Building
# ============================================================================


async def demonstrate_dynamic_queries(driver):
    """
    Shows how DynamicQueryBuilder makes ANY field instantly queryable.
    """
    print("=" * 80)
    print("DYNAMIC QUERY DEMONSTRATION")
    print("=" * 80)

    # Use 100% dynamic pattern
    backend = create_task_backend_dynamic(driver)

    # Example 1: Simple equality filters
    print("\n1. Simple Equality Filters:")
    print("   Code: backend.find_by(priority='high', status='in_progress')")
    result = await backend.find_by(priority="high", status="in_progress")
    print(f"   Result: Found {len(result.value)} tasks")

    # Example 2: Comparison operators
    print("\n2. Comparison Operators:")
    print("   Code: backend.find_by(due_date__gte=date.today())")
    result = await backend.find_by(due_date__gte=date.today())
    print(f"   Result: Found {len(result.value)} upcoming tasks")

    # Example 3: NEW FIELD - instantly works!
    print("\n3. NEW FIELD (estimated_hours) - Instantly Queryable:")
    print("   Code: backend.find_by(estimated_hours__lt=5.0)")
    result = await backend.find_by(estimated_hours__lt=5.0)
    print(f"   Result: Found {len(result.value)} quick tasks")
    print("   ✅ NO ADAPTER CODE CHANGES NEEDED!")

    # Example 4: String matching
    print("\n4. String Matching:")
    print("   Code: backend.find_by(title__contains='urgent')")
    result = await backend.find_by(title__contains="urgent")
    print(f"   Result: Found {len(result.value)} urgent tasks")

    # Example 5: List membership
    print("\n5. List Membership:")
    print("   Code: backend.find_by(priority__in=['high', 'urgent'])")
    result = await backend.find_by(priority__in=["high", "urgent"])
    print(f"   Result: Found {len(result.value)} high-priority tasks")

    # Example 6: Count with filters
    print("\n6. Count with Dynamic Filters:")
    print("   Code: backend.count(status='completed')")
    result = await backend.count(status="completed")
    print(f"   Result: {result.value} completed tasks")


# ============================================================================
# STEP 4: Demonstrate Auto-Index Creation
# ============================================================================


async def demonstrate_auto_indexes(driver):
    """
    Shows how Neo4jSchemaManager creates indexes from field metadata.
    """
    print("\n" + "=" * 80)
    print("AUTO-INDEX DEMONSTRATION")
    print("=" * 80)

    from adapters.persistence.neo4j.neo4j_schema_manager import Neo4jSchemaManager

    schema_manager = Neo4jSchemaManager(driver)

    # Sync indexes for Task model
    print("\n1. Scanning Task model for index metadata...")
    result = await schema_manager.sync_indexes(Task, "Task")

    if result.is_ok:
        summary = result.value
        print(f"\n   ✅ Created indexes: {summary['created']}")
        print(f"   ℹ️  Existing indexes: {summary['existing']}")
        print(f"   ❌ Failed indexes: {summary['failed']}")
        print("\n   Indexes created automatically from field(metadata={'index': True})!")

    # List all Task indexes
    print("\n2. Listing all Task indexes:")
    result = await schema_manager.list_indexes("Task")
    if result.is_ok:
        for idx in result.value:
            print(f"   - {idx.get('name')}: {idx.get('labelsOrTypes')} on {idx.get('properties')}")


# ============================================================================
# STEP 5: Demonstrate Auto-Generated Relationship Methods
# ============================================================================


async def demonstrate_auto_relationships(driver):
    """
    Shows how add_relationships() dynamically adds relationship methods.
    """
    print("\n" + "=" * 80)
    print("AUTO-RELATIONSHIP DEMONSTRATION")
    print("=" * 80)

    task_backend = create_task_backend_dynamic(driver)
    goal_backend = UniversalNeo4jBackend[Goal](driver, "Goal", Goal)

    # Create test data
    print("\n1. Creating test task and goal...")
    task = Task(uid="task-001", title="Complete project milestone", priority=Priority.HIGH)
    goal = Goal(uid="goal-001", title="Finish Q4 objectives")

    await task_backend.create(task)
    await goal_backend.create(goal)
    print("   ✅ Created task and goal")

    # Use auto-generated link method
    print("\n2. Linking task to goal using dynamically added method:")
    print("   Code: task_backend.link_to_goal('task-001', 'goal-001')")
    result = await task_backend.link_to_goal("task-001", "goal-001")

    if result.is_ok:
        print("   ✅ Relationship created automatically!")
        print("   Method was added by add_relationships() - NO MANUAL CODE!")

    # Use auto-generated get relationships method
    print("\n3. Getting task's goal relationships:")
    print("   Code: task_backend.get_goal_relationships('task-001')")
    result = await task_backend.get_goal_relationships("task-001")

    if result.is_ok:
        goal_uids = result.value
        print(f"   ✅ Found {len(goal_uids)} goal relationships: {goal_uids}")

    # Use auto-generated unlink method
    print("\n4. Unlinking task from goal:")
    print("   Code: task_backend.unlink_from_goal('task-001', 'goal-001')")
    result = await task_backend.unlink_from_goal("task-001", "goal-001")

    if result.is_ok:
        print("   ✅ Relationship removed automatically!")


# ============================================================================
# STEP 6: Show the Complete Ripple Effect
# ============================================================================


async def demonstrate_ripple_effect(driver):
    """
    Shows how adding a field to the model instantly works everywhere.
    """
    print("\n" + "=" * 80)
    print("COMPLETE RIPPLE EFFECT DEMONSTRATION")
    print("=" * 80)

    print("\nScenario: We added 'estimated_hours' field to Task model")
    print("=" * 80)

    backend = create_task_backend_dynamic(driver)

    # Create task with new field
    print("\n1. Create task with new field:")
    task = Task(
        uid="task-ripple-001",
        title="Test ripple effect",
        priority=Priority.MEDIUM,
        estimated_hours=3.5,  # NEW FIELD
    )

    result = await backend.create(task)
    if result.is_ok:
        print("   ✅ Task created with estimated_hours=3.5")
        print("   Serialization: AUTOMATIC (introspection)")

    # Retrieve task - new field comes back
    print("\n2. Retrieve task:")
    result = await backend.get("task-ripple-001")
    if result.is_ok and result.value:
        retrieved_task = result.value
        print(f"   ✅ Retrieved task.estimated_hours = {retrieved_task.estimated_hours}")
        print("   Deserialization: AUTOMATIC (type hints)")

    # Query by new field
    print("\n3. Query by new field:")
    result = await backend.find_by(estimated_hours__lt=5.0)
    if result.is_ok:
        print(f"   ✅ Found {len(result.value)} tasks with estimated_hours < 5.0")
        print("   Query generation: AUTOMATIC (DynamicQueryBuilder)")

    # Count by new field
    print("\n4. Count by new field:")
    result = await backend.count(estimated_hours__lt=5.0)
    if result.is_ok:
        print(f"   ✅ Count: {result.value}")
        print("   Count query: AUTOMATIC (DynamicQueryBuilder)")

    print("\n" + "=" * 80)
    print("RIPPLE EFFECT SUMMARY")
    print("=" * 80)
    print("Added ONE field to Task model → Instantly works for:")
    print("  ✅ Storage (to_neo4j_node)")
    print("  ✅ Retrieval (from_neo4j_node)")
    print("  ✅ Queries (DynamicQueryBuilder)")
    print("  ✅ Filtering (find_by with operators)")
    print("  ✅ Counting (count)")
    print("\n  ZERO adapter code changes needed!")


# ============================================================================
# STEP 7: Main Execution
# ============================================================================


async def main():
    """
    Run all demonstrations.

    IMPORTANT: This requires a running Neo4j instance.
    Update connection details as needed.
    """
    from neo4j import AsyncGraphDatabase

    # Connect to Neo4j
    uri = "bolt://localhost:7687"
    username = "neo4j"
    password = "your-password"  # Update this

    driver = AsyncGraphDatabase.driver(uri, auth=(username, password))

    try:
        print("\n" + "=" * 80)
        print("SKUEL 100% DYNAMIC ARCHITECTURE DEMONSTRATION")
        print("=" * 80)
        print("\nThis demonstrates three enhancements for 100% dynamic architecture:")
        print("1. DynamicQueryBuilder - Auto-generates queries from model fields")
        print("2. Neo4jSchemaManager - Auto-creates indexes from field metadata")
        print("3. add_relationships() - Dynamically adds relationship methods")
        print("\n" + "=" * 80)

        # Run demonstrations
        await demonstrate_dynamic_queries(driver)
        await demonstrate_auto_indexes(driver)
        await demonstrate_auto_relationships(driver)
        await demonstrate_ripple_effect(driver)

        print("\n" + "=" * 80)
        print("CONCLUSION")
        print("=" * 80)
        print("SKUEL's architecture is now 100% dynamic:")
        print("  • Add field to model → Instantly queryable")
        print("  • Add index metadata → Automatically indexed")
        print("  • Call add_relationships() → Methods dynamically added")
        print("\n  The plant (models) grows freely on the lattice (adapters)!")
        print("=" * 80)

    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(main())
