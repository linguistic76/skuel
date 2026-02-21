"""
Seed Search Test Data
======================

Populates the database with test data for simple search demonstration.

Creates sample data across all domains:
- Knowledge units (with SEL categories, learning levels, content types)
- Tasks
- Events
- Habits
- Goals
- Choices
- Principles

Run with:
    poetry run python scripts/seed_search_test_data.py
"""

import asyncio
from datetime import date, datetime, timedelta

from neo4j import AsyncGraphDatabase

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums import (
    ContentType,
    Domain,
    EducationalLevel,
    KuStatus,
    LearningLevel,
    Priority,
    RecurrencePattern,
    SELCategory,
)
from core.models.enums.ku_enums import KuType
from core.models.ku.ku import Ku
from core.models.ku.ku_habit import HabitKu as Habit
from core.models.ku.ku_task import TaskKu as Task
from core.utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================================
# TEST DATA DEFINITIONS
# ============================================================================

KNOWLEDGE_UNITS = [
    {
        "uid": "ku.self_awareness.meditation_basics",
        "title": "Introduction to Meditation",
        "content": "Learn the foundational practices of mindfulness meditation for developing self-awareness.",
        "sel_category": SELCategory.SELF_AWARENESS,
        "learning_level": LearningLevel.BEGINNER,
        "content_type": ContentType.CONCEPT,
        "educational_level": EducationalLevel.HIGH_SCHOOL,
        "domain": Domain.KNOWLEDGE,
        "created_at": datetime.now(),
    },
    {
        "uid": "ku.self_awareness.emotional_intelligence",
        "title": "Understanding Emotional Intelligence",
        "content": "Explore the five components of emotional intelligence and how they contribute to self-awareness.",
        "sel_category": SELCategory.SELF_AWARENESS,
        "learning_level": LearningLevel.INTERMEDIATE,
        "content_type": ContentType.THEORY,
        "educational_level": EducationalLevel.COLLEGE,
        "domain": Domain.KNOWLEDGE,
        "created_at": datetime.now(),
    },
    {
        "uid": "ku.self_awareness.journaling_practice",
        "title": "Daily Journaling for Self-Discovery",
        "content": "Practice reflective journaling to develop deeper self-awareness and emotional clarity.",
        "sel_category": SELCategory.SELF_AWARENESS,
        "learning_level": LearningLevel.BEGINNER,
        "content_type": ContentType.PRACTICE,
        "educational_level": EducationalLevel.HIGH_SCHOOL,
        "domain": Domain.KNOWLEDGE,
        "created_at": datetime.now(),
    },
    {
        "uid": "ku.self_management.goal_setting",
        "title": "SMART Goal Setting Framework",
        "content": "Learn how to set Specific, Measurable, Achievable, Relevant, and Time-bound goals.",
        "sel_category": SELCategory.SELF_MANAGEMENT,
        "learning_level": LearningLevel.BEGINNER,
        "content_type": ContentType.CONCEPT,
        "educational_level": EducationalLevel.HIGH_SCHOOL,
        "domain": Domain.KNOWLEDGE,
        "created_at": datetime.now(),
    },
    {
        "uid": "ku.self_management.time_blocking",
        "title": "Time Blocking Techniques",
        "content": "Master the art of time blocking to manage your schedule effectively and boost productivity.",
        "sel_category": SELCategory.SELF_MANAGEMENT,
        "learning_level": LearningLevel.INTERMEDIATE,
        "content_type": ContentType.PRACTICE,
        "educational_level": EducationalLevel.PROFESSIONAL,
        "domain": Domain.KNOWLEDGE,
        "created_at": datetime.now(),
    },
    {
        "uid": "ku.social_awareness.active_listening",
        "title": "Active Listening Skills",
        "content": "Develop active listening skills to better understand others and build stronger relationships.",
        "sel_category": SELCategory.SOCIAL_AWARENESS,
        "learning_level": LearningLevel.BEGINNER,
        "content_type": ContentType.PRACTICE,
        "educational_level": EducationalLevel.HIGH_SCHOOL,
        "domain": Domain.KNOWLEDGE,
        "created_at": datetime.now(),
    },
    {
        "uid": "ku.relationship_skills.conflict_resolution",
        "title": "Conflict Resolution Strategies",
        "content": "Learn effective strategies for resolving conflicts and maintaining healthy relationships.",
        "sel_category": SELCategory.RELATIONSHIP_SKILLS,
        "learning_level": LearningLevel.INTERMEDIATE,
        "content_type": ContentType.CONCEPT,
        "educational_level": EducationalLevel.COLLEGE,
        "domain": Domain.KNOWLEDGE,
        "created_at": datetime.now(),
    },
    {
        "uid": "ku.decision_making.pros_cons_analysis",
        "title": "Pros and Cons Analysis",
        "content": "A systematic approach to evaluating options and making responsible decisions.",
        "sel_category": SELCategory.RESPONSIBLE_DECISION_MAKING,
        "learning_level": LearningLevel.BEGINNER,
        "content_type": ContentType.PRACTICE,
        "educational_level": EducationalLevel.MIDDLE_SCHOOL,
        "domain": Domain.KNOWLEDGE,
        "created_at": datetime.now(),
    },
]

TASKS = [
    {
        "uid": "task.001",
        "title": "Complete meditation practice",
        "description": "15-minute morning meditation session",
        "status": KuStatus.ACTIVE,
        "priority": Priority.HIGH,
        "due_date": date.today() + timedelta(days=1),
        "created_at": datetime.now(),
    },
    {
        "uid": "task.002",
        "title": "Review goal progress",
        "description": "Weekly review of personal development goals",
        "status": KuStatus.SCHEDULED,
        "priority": Priority.MEDIUM,
        "due_date": date.today() + timedelta(days=3),
        "created_at": datetime.now(),
    },
    {
        "uid": "task.003",
        "title": "Practice active listening",
        "description": "Apply active listening techniques in today's meetings",
        "status": KuStatus.DRAFT,
        "priority": Priority.LOW,
        "due_date": date.today(),
        "created_at": datetime.now(),
    },
]

EVENTS = [
    {
        "uid": "event.001",
        "title": "Mindfulness Workshop",
        "description": "Learn mindfulness techniques for stress reduction",
        "start_time": datetime.now() + timedelta(days=7),
        "end_time": datetime.now() + timedelta(days=7, hours=2),
        "status": KuStatus.SCHEDULED,
        "priority": Priority.HIGH,
        "created_at": datetime.now(),
    },
    {
        "uid": "event.002",
        "title": "Team Building Exercise",
        "description": "Collaborative activities to strengthen team relationships",
        "start_time": datetime.now() + timedelta(days=14),
        "end_time": datetime.now() + timedelta(days=14, hours=3),
        "status": KuStatus.SCHEDULED,
        "priority": Priority.MEDIUM,
        "created_at": datetime.now(),
    },
]

HABITS = [
    {
        "uid": "habit.001",
        "name": "Morning Meditation",
        "description": "Daily 10-minute meditation practice",
        "frequency": RecurrencePattern.DAILY,
        "status": KuStatus.ACTIVE,
        "current_streak": 15,
        "best_streak": 30,
        "created_at": datetime.now(),
    },
    {
        "uid": "habit.002",
        "name": "Evening Journaling",
        "description": "Reflect on the day through journaling",
        "frequency": RecurrencePattern.DAILY,
        "status": KuStatus.ACTIVE,
        "current_streak": 8,
        "best_streak": 12,
        "created_at": datetime.now(),
    },
]

GOALS = [
    {
        "uid": "goal.001",
        "name": "Develop Emotional Intelligence",
        "description": "Improve self-awareness and emotional regulation skills",
        "status": KuStatus.ACTIVE,
        "priority": Priority.HIGH,
        "target_date": date.today() + timedelta(days=90),
        "progress_percentage": 35.0,
        "created_at": datetime.now(),
    },
    {
        "uid": "goal.002",
        "name": "Build Better Relationships",
        "description": "Strengthen connections through active listening and empathy",
        "status": KuStatus.ACTIVE,
        "priority": Priority.MEDIUM,
        "target_date": date.today() + timedelta(days=180),
        "progress_percentage": 20.0,
        "created_at": datetime.now(),
    },
]

CHOICES = [
    {
        "uid": "choice.001",
        "name": "Choose meditation over social media",
        "description": "Decision to start the day with meditation instead of scrolling",
        "decision_date": date.today(),
        "outcome_quality": 4,
        "created_at": datetime.now(),
    },
]

PRINCIPLES = [
    {
        "uid": "principle.001",
        "title": "Practice mindfulness daily",
        "description": "Commit to being present and aware in each moment",
        "ku_type": KuType.PRINCIPLE.value,
        "domain": Domain.PERSONAL,
        "created_at": datetime.now(),
    },
]


# ============================================================================
# SEEDING FUNCTIONS
# ============================================================================


async def seed_knowledge_units(driver):
    """Seed knowledge units with SEL categories"""
    backend = UniversalNeo4jBackend(driver, "Ku", Ku)

    logger.info("Seeding knowledge units...")
    for ku_data in KNOWLEDGE_UNITS:
        ku = Ku(**ku_data)
        result = await backend.create(ku)
        if result.is_ok:
            logger.info(f"  ✓ Created: {ku.title}")
        else:
            logger.error(f"  ✗ Failed: {ku.title} - {result.error}")

    logger.info(f"Seeded {len(KNOWLEDGE_UNITS)} knowledge units")


async def seed_tasks(driver):
    """Seed sample tasks"""
    backend = UniversalNeo4jBackend(driver, "Task", Task)

    logger.info("Seeding tasks...")
    for task_data in TASKS:
        task = Task(**task_data)
        result = await backend.create(task)
        if result.is_ok:
            logger.info(f"  ✓ Created: {task.title}")
        else:
            logger.error(f"  ✗ Failed: {task.title} - {result.error}")

    logger.info(f"Seeded {len(TASKS)} tasks")


async def seed_events(driver):
    """Seed sample events"""
    backend = UniversalNeo4jBackend(driver, "Event", Ku)

    logger.info("Seeding events...")
    for event_data in EVENTS:
        event = Ku(**event_data)
        result = await backend.create(event)
        if result.is_ok:
            logger.info(f"  ✓ Created: {event.title}")
        else:
            logger.error(f"  ✗ Failed: {event.title} - {result.error}")

    logger.info(f"Seeded {len(EVENTS)} events")


async def seed_habits(driver):
    """Seed sample habits"""
    backend = UniversalNeo4jBackend(driver, "Habit", Habit)

    logger.info("Seeding habits...")
    for habit_data in HABITS:
        habit = Habit(**habit_data)
        result = await backend.create(habit)
        if result.is_ok:
            logger.info(f"  ✓ Created: {habit.title}")
        else:
            logger.error(f"  ✗ Failed: {habit.title} - {result.error}")

    logger.info(f"Seeded {len(HABITS)} habits")


async def seed_goals(driver):
    """Seed sample goals"""
    backend = UniversalNeo4jBackend(driver, "Goal", Ku)

    logger.info("Seeding goals...")
    for goal_data in GOALS:
        goal = Ku(**goal_data)
        result = await backend.create(goal)
        if result.is_ok:
            logger.info(f"  ✓ Created: {goal.title}")
        else:
            logger.error(f"  ✗ Failed: {goal.title} - {result.error}")

    logger.info(f"Seeded {len(GOALS)} goals")


async def seed_choices(driver):
    """Seed sample choices"""
    backend = UniversalNeo4jBackend(driver, "Ku", Ku, default_filters={"ku_type": "choice"})

    logger.info("Seeding choices...")
    for choice_data in CHOICES:
        choice_data["ku_type"] = "choice"
        choice = Ku(**choice_data)
        result = await backend.create(choice)
        if result.is_ok:
            logger.info(f"  ✓ Created: {choice.title}")
        else:
            logger.error(f"  ✗ Failed: {choice.title} - {result.error}")

    logger.info(f"Seeded {len(CHOICES)} choices")


async def seed_principles(driver):
    """Seed sample principles"""
    backend = UniversalNeo4jBackend(driver, "Ku", Ku, default_filters={"ku_type": "principle"})

    logger.info("Seeding principles...")
    for principle_data in PRINCIPLES:
        principle = Ku(**principle_data)
        result = await backend.create(principle)
        if result.is_ok:
            logger.info(f"  ✓ Created: {principle.title}")
        else:
            logger.error(f"  ✗ Failed: {principle.title} - {result.error}")

    logger.info(f"Seeded {len(PRINCIPLES)} principles")


async def main():
    """Main seeding function"""
    logger.info("=" * 60)
    logger.info("SKUEL Search Test Data Seeder")
    logger.info("=" * 60)

    # Neo4j connection
    neo4j_uri = "bolt://localhost:7687"
    neo4j_user = "neo4j"
    neo4j_password = "skuelneo4j"

    logger.info(f"\nConnecting to Neo4j at {neo4j_uri}...")

    try:
        driver = AsyncGraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

        # Seed all domains
        await seed_knowledge_units(driver)
        await seed_tasks(driver)
        await seed_events(driver)
        await seed_habits(driver)
        await seed_goals(driver)
        await seed_choices(driver)
        await seed_principles(driver)

        logger.info("\n" + "=" * 60)
        logger.info("✅ Seeding Complete!")
        logger.info("=" * 60)
        logger.info("\nTest the search at: http://localhost:8000/simple-search")

        await driver.close()

    except Exception as e:
        logger.error(f"\n❌ Seeding failed: {e}")
        logger.error("\nMake sure Neo4j is running and credentials are correct.")


if __name__ == "__main__":
    asyncio.run(main())
