#!/usr/bin/env python3
"""
Development User Seeding Script
================================

Seeds the development database with test users for local development.

One path forward: Same code in all environments, different data.

Usage:
    poetry run python scripts/seed_dev_users.py

Created users:
- user.dev (ADMIN) - Primary development user
- user.alice (MEMBER) - Standard member for testing
- user.bob (TEACHER) - Teacher role for curriculum testing
"""

import asyncio
import os
import sys
from pathlib import Path

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from core.models.user import UserPreferences, create_user
from core.utils.logging import get_logger
from neo4j import AsyncGraphDatabase

logger = get_logger("skuel.scripts.seed_dev_users")


async def seed_development_users():
    """
    Seed development database with test users.

    Creates three test users with different roles:
    - user.dev (ADMIN) - For general development
    - user.alice (MEMBER) - For standard user testing
    - user.bob (TEACHER) - For teacher/curriculum testing
    """
    # Get Neo4j connection info from environment
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "password")

    logger.info(f"Connecting to Neo4j at {neo4j_uri}")

    driver = AsyncGraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

    try:
        # Define test users
        test_users = [
            {
                "uid": "user.dev",
                "username": "dev",
                "email": "dev@skuel.local",
                "display_name": "Dev User",
                "role": "ADMIN",
            },
            {
                "uid": "user.alice",
                "username": "alice",
                "email": "alice@skuel.local",
                "display_name": "Alice Member",
                "role": "MEMBER",
            },
            {
                "uid": "user.bob",
                "username": "bob",
                "email": "bob@skuel.local",
                "display_name": "Bob Teacher",
                "role": "TEACHER",
            },
        ]

        for user_data in test_users:
            # Check if user already exists
            check_query = """
            MATCH (u:User {uid: $uid})
            RETURN u.uid as uid
            """
            records, _, _ = await driver.execute_query(
                check_query, uid=user_data["uid"]
            )

            if records:
                logger.info(f"✓ User {user_data['uid']} already exists, skipping")
                continue

            # Create user with default preferences
            preferences = UserPreferences()
            user = create_user(
                uid=user_data["uid"],
                username=user_data["username"],
                email=user_data["email"],
                display_name=user_data["display_name"],
                role=user_data["role"],
                preferences=preferences,
            )

            # Create user node in Neo4j
            create_query = """
            CREATE (u:User {
                uid: $uid,
                username: $username,
                email: $email,
                display_name: $display_name,
                role: $role,
                created_at: datetime(),
                updated_at: datetime()
            })
            SET u.preferences = $preferences
            RETURN u.uid as uid
            """

            await driver.execute_query(
                create_query,
                uid=user.uid,
                username=user.username,
                email=user.email,
                display_name=user.display_name,
                role=user.role,
                preferences={
                    "learning_level": preferences.learning_level,
                    "preferred_modalities": preferences.preferred_modalities,
                    "preferred_subjects": preferences.preferred_subjects,
                    "preferred_time_of_day": preferences.preferred_time_of_day,
                    "available_minutes_daily": preferences.available_minutes_daily,
                    "enable_reminders": preferences.enable_reminders,
                    "reminder_minutes_before": preferences.reminder_minutes_before,
                    "daily_summary_time": preferences.daily_summary_time,
                    "theme": preferences.theme,
                    "language": preferences.language,
                    "timezone": preferences.timezone,
                    "weekly_task_goal": preferences.weekly_task_goal,
                    "daily_habit_goal": preferences.daily_habit_goal,
                    "monthly_learning_hours": preferences.monthly_learning_hours,
                },
            )

            logger.info(
                f"✓ Created user {user_data['uid']} ({user_data['role']})"
            )

        logger.info("✓ Development user seeding complete")
        logger.info("")
        logger.info("Available test users:")
        logger.info("  - user.dev (ADMIN) - dev@skuel.local")
        logger.info("  - user.alice (MEMBER) - alice@skuel.local")
        logger.info("  - user.bob (TEACHER) - bob@skuel.local")

    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(seed_development_users())
