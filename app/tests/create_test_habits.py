#!/usr/bin/env python3
import asyncio
import uuid
from datetime import datetime

from bootstrap import bootstrap_skuel, shutdown_skuel
from dotenv import load_dotenv

from core.models.task_pure import HabitCategory, HabitPolarity, TaskKind, TaskPure, TimeOfDay

__version__ = "1.0"
"""
Create test habits in the database for demonstration
"""
load_dotenv()


async def create_test_habits():
    """Create sample habits for testing"""
    print("🚀 Bootstrapping SKUEL...")
    container = await bootstrap_skuel()
    tasks_service = container.services.tasks
    test_habits = [
        {
            "title": "Morning Meditation",
            "description": "10 minutes of mindfulness practice to start the day",
            "kind": TaskKind.HABIT,
            "category": HabitCategory.MINDFULNESS,
            "polarity": HabitPolarity.BUILD,
            "time_of_day": TimeOfDay.MORNING,
            "priority": "high",
            "tags": ["wellness", "mental-health", "daily"],
        },
        {
            "title": "Exercise Routine",
            "description": "30 minutes of physical activity",
            "kind": TaskKind.HABIT,
            "category": HabitCategory.FITNESS,
            "polarity": HabitPolarity.BUILD,
            "time_of_day": TimeOfDay.MORNING,
            "priority": "high",
            "tags": ["fitness", "health", "daily"],
        },
        {
            "title": "Read for 20 Minutes",
            "description": "Read a book or educational material",
            "kind": TaskKind.HABIT,
            "category": HabitCategory.LEARNING,
            "polarity": HabitPolarity.BUILD,
            "time_of_day": TimeOfDay.EVENING,
            "priority": "medium",
            "tags": ["learning", "growth", "daily"],
        },
        {
            "title": "Drink 8 Glasses of Water",
            "description": "Stay hydrated throughout the day",
            "kind": TaskKind.HABIT,
            "category": HabitCategory.HEALTH,
            "polarity": HabitPolarity.BUILD,
            "time_of_day": TimeOfDay.ANYTIME,
            "priority": "medium",
            "tags": ["health", "hydration", "daily"],
        },
        {
            "title": "Write in Journal",
            "description": "Reflect on the day and write thoughts",
            "kind": TaskKind.HABIT,
            "category": HabitCategory.MINDFULNESS,
            "polarity": HabitPolarity.BUILD,
            "time_of_day": TimeOfDay.EVENING,
            "priority": "medium",
            "tags": ["reflection", "writing", "daily"],
        },
    ]
    print(f"📝 Creating {len(test_habits)} test habits...")
    created_habits = []
    for habit_data in test_habits:
        try:
            habit = TaskPure(
                uid=f"habit_{uuid.uuid4().hex[:8]}",
                title=habit_data["title"],
                description=habit_data["description"],
                kind=habit_data["kind"],
                category=habit_data.get("category"),
                polarity=habit_data.get("polarity"),
                time_of_day=habit_data.get("time_of_day"),
                priority=habit_data["priority"],
                tags=habit_data.get("tags", []),
                status="todo",
                context="personal",
                energy_level="medium",
                estimated_minutes=30,
                actual_minutes=0,
                is_recurring=True,  # Habits are recurring by nature
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            result = await tasks_service.create_task(habit)
            if result.is_ok:
                created_habits.append(result.value)
                print(f"✅ Created habit: {habit.title}")
            else:
                print(f"❌ Failed to create habit '{habit.title}': {result.error}")
        except Exception as e:
            print(f"❌ Error creating habit '{habit_data['title']}': {e}")
    print(f"\n🎉 Successfully created {len(created_habits)} habits!")
    if created_habits:
        print("\n📊 Adding some activity data...")
        for habit in created_habits[:2]:  # Add streaks to first 2 habits
            try:
                update_data = {
                    "labels": {
                        "current_streak": "7",
                        "best_streak": "14",
                        "completion_rate": "0.85",
                    }
                }
                result = await tasks_service.update_task(habit.uid, update_data)
                if result.is_ok:
                    print(f"✅ Added streak data to: {habit.title}")
            except Exception as e:
                print(f"⚠️ Could not add streak data: {e}")
    await shutdown_skuel(container)
    print("\n✨ Done!")


if __name__ == "__main__":
    asyncio.run(create_test_habits())
