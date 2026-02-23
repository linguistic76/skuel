"""
Create Test User Data for Migration
====================================

Creates sample User nodes with legacy array/string properties to test migration.

This script creates:
- Users with learning_paths arrays
- Users with completed_paths arrays
- Users with mastery_data strings
- LearningPath nodes
- Knowledge nodes

After running this, you can test the migration script.

Usage:
    python scripts/create_test_user_data.py
"""

import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase

from core.config.credential_store import get_credential_store
from core.utils.logging import get_logger

# Add project root to path
project_root = Path(__file__).parent.parent

load_dotenv()

logger = get_logger(__name__)


async def create_test_data(driver):
    """Create test users with legacy data format."""

    logger.info("🔧 Creating test data for migration...")

    async with driver.session() as session:
        # Step 1: Create LearningPath nodes
        logger.info("📚 Creating LearningPath nodes...")
        await session.run("""
            // Create learning paths
            CREATE (p1:Lp {
                uid: 'path.python.fundamentals',
                title: 'Python Fundamentals',
                created_at: datetime()
            })
            CREATE (p2:Lp {
                uid: 'path.python.advanced',
                title: 'Advanced Python',
                created_at: datetime()
            })
            CREATE (p3:Lp {
                uid: 'path.javascript.basics',
                title: 'JavaScript Basics',
                created_at: datetime()
            })
            CREATE (p4:Lp {
                uid: 'path.data.science',
                title: 'Data Science Essentials',
                created_at: datetime()
            })
        """)
        logger.info("  ✅ Created 4 LearningPath nodes")

        # Step 2: Create Knowledge nodes
        logger.info("🧠 Creating Knowledge nodes...")
        await session.run("""
            // Create knowledge units
            CREATE (k1:Entity {
                uid: 'ku.python.variables',
                title: 'Python Variables',
                level: 'beginner',
                created_at: datetime()
            })
            CREATE (k2:Entity {
                uid: 'ku.python.functions',
                title: 'Python Functions',
                level: 'intermediate',
                created_at: datetime()
            })
            CREATE (k3:Entity {
                uid: 'ku.python.decorators',
                title: 'Python Decorators',
                level: 'advanced',
                created_at: datetime()
            })
            CREATE (k4:Entity {
                uid: 'ku.javascript.async',
                title: 'JavaScript Async/Await',
                level: 'intermediate',
                created_at: datetime()
            })
            CREATE (k5:Entity {
                uid: 'ku.sql.queries',
                title: 'SQL Queries',
                level: 'intermediate',
                created_at: datetime()
            })
        """)
        logger.info("  ✅ Created 5 Knowledge nodes")

        # Step 3: Create test users with LEGACY data format
        logger.info("👥 Creating test User nodes with legacy data...")

        # User 1: Has all types of legacy data
        await session.run("""
            CREATE (u1:User {
                uid: 'test_user_001',
                title: 'TestUser1',
                display_name: 'Test User 1',
                email: 'test1@example.com',
                created_at: datetime(),
                // LEGACY DATA - arrays and strings
                learning_paths: ['path.python.fundamentals', 'path.javascript.basics'],
                completed_paths: ['path.data.science'],
                mastery_data: 'ku.python.variables:expert;ku.python.functions:advanced;ku.sql.queries:proficient;'
            })
        """)
        logger.info("  ✅ Created test_user_001 (full legacy data)")

        # User 2: Only has learning paths
        await session.run("""
            CREATE (u2:User {
                uid: 'test_user_002',
                title: 'TestUser2',
                display_name: 'Test User 2',
                email: 'test2@example.com',
                created_at: datetime(),
                // LEGACY DATA
                learning_paths: ['path.python.advanced']
            })
        """)
        logger.info("  ✅ Created test_user_002 (learning paths only)")

        # User 3: Only has mastery data
        await session.run("""
            CREATE (u3:User {
                uid: 'test_user_003',
                title: 'TestUser3',
                display_name: 'Test User 3',
                email: 'test3@example.com',
                created_at: datetime(),
                // LEGACY DATA
                mastery_data: 'ku.python.decorators:intermediate;ku.javascript.async:beginner;'
            })
        """)
        logger.info("  ✅ Created test_user_003 (mastery data only)")

        # User 4: Has completed paths and mastery
        await session.run("""
            CREATE (u4:User {
                uid: 'test_user_004',
                title: 'TestUser4',
                display_name: 'Test User 4',
                email: 'test4@example.com',
                created_at: datetime(),
                // LEGACY DATA
                completed_paths: ['path.python.fundamentals', 'path.javascript.basics'],
                mastery_data: 'ku.python.variables:expert;ku.python.functions:expert;'
            })
        """)
        logger.info("  ✅ Created test_user_004 (completed + mastery)")

        # User 5: Empty/no legacy data (should be skipped by migration)
        await session.run("""
            CREATE (u5:User {
                uid: 'test_user_005',
                title: 'TestUser5',
                display_name: 'Test User 5',
                email: 'test5@example.com',
                created_at: datetime()
                // NO LEGACY DATA
            })
        """)
        logger.info("  ✅ Created test_user_005 (no legacy data)")

        logger.info("\n" + "=" * 60)
        logger.info("✨ Test Data Creation Complete!")
        logger.info("=" * 60)

        # Display summary
        result = await session.run("""
            MATCH (u:User)
            RETURN
                count(u) as user_count,
                count(u.learning_paths) as with_learning_paths,
                count(u.completed_paths) as with_completed_paths,
                count(u.mastery_data) as with_mastery_data
        """)
        record = await result.single()

        logger.info("\n📊 Summary:")
        logger.info(f"  Total Users: {record['user_count']}")
        logger.info(f"  Users with learning_paths: {record['with_learning_paths']}")
        logger.info(f"  Users with completed_paths: {record['with_completed_paths']}")
        logger.info(f"  Users with mastery_data: {record['with_mastery_data']}")

        logger.info("\n🎯 Next Steps:")
        logger.info("  1. Run dry-run migration:")
        logger.info("     python scripts/migrate_user_knowledge_relationships.py")
        logger.info("\n  2. Review the output")
        logger.info("\n  3. Execute migration:")
        logger.info("     python scripts/migrate_user_knowledge_relationships.py --execute")
        logger.info("\n  4. Verify relationships created:")
        logger.info("     Match (u:User)-[r]->(target) return u.uid, type(r), target")


async def cleanup_test_data(driver):
    """Remove all test data."""
    logger.info("🧹 Cleaning up test data...")

    async with driver.session() as session:
        # Delete test users and their relationships
        await session.run("""
            MATCH (u:User)
            WHERE u.uid STARTS WITH 'test_user_'
            DETACH DELETE u
        """)

        # Delete test learning paths
        await session.run("""
            MATCH (p:Lp)
            WHERE p.uid STARTS WITH 'path.'
            DETACH DELETE p
        """)

        # Delete test knowledge
        await session.run("""
            MATCH (k:Entity)
            WHERE k.uid STARTS WITH 'ku.'
            DETACH DELETE k
        """)

        logger.info("✅ Cleanup complete!")


async def main():
    """Main entry point."""

    parser = argparse.ArgumentParser(description="Create test data for User-Knowledge migration")
    parser.add_argument(
        "--cleanup", action="store_true", help="Remove test data instead of creating it"
    )
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687", help="Neo4j connection URI")
    parser.add_argument("--neo4j-user", default="neo4j", help="Neo4j username")
    parser.add_argument(
        "--neo4j-password",
        default=None,
        help="Neo4j password (if not provided, will use credential store)",
    )

    args = parser.parse_args()

    # Get Neo4j password from credential store or args
    neo4j_password = args.neo4j_password
    if not neo4j_password:
        try:
            store = get_credential_store()
            neo4j_password = store.get("NEO4J_PASSWORD")
            if neo4j_password:
                logger.info("✅ Using Neo4j password from credential store")
            else:
                logger.error("❌ NEO4J_PASSWORD not found in credential store")
                logger.error("Please run: python -m core.config.credential_setup")
                sys.exit(1)
        except Exception as e:
            logger.error(f"❌ Failed to get password from credential store: {e}")
            logger.error("Please provide --neo4j-password or set up credentials")
            sys.exit(1)

    # Connect to Neo4j
    driver = AsyncGraphDatabase.driver(args.neo4j_uri, auth=(args.neo4j_user, neo4j_password))

    try:
        if args.cleanup:
            await cleanup_test_data(driver)
        else:
            await create_test_data(driver)
    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(main())
