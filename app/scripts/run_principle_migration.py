#!/usr/bin/env python3
"""
Run the Principle name → title migration.

This script migrates all Principle nodes in Neo4j from using 'name' to 'title'.
"""

import asyncio
from neo4j import GraphDatabase

# Neo4j connection details (update if different)
URI = "bolt://localhost:7687"
USER = "neo4j"
PASSWORD = "skuel-local-dev-2026"


def run_migration():
    """Run the Principle name → title migration."""
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

    try:
        with driver.session() as session:
            print("=" * 70)
            print("PRINCIPLE MIGRATION: name → title")
            print("=" * 70)
            print()

            # Step 1: Check current state
            print("Step 1: Checking current state...")
            result = session.run("""
                MATCH (p:Principle)
                WHERE p.name IS NOT NULL
                WITH count(p) as principle_count
                RETURN principle_count
            """)
            record = result.single()
            count = record["principle_count"] if record else 0
            print(f"✓ Found {count} Principle nodes with 'name' property")
            print()

            if count == 0:
                print("⚠ No principles found with 'name' property.")
                print("  Migration may have already been run, or no data exists.")
                print()

            # Step 2: Run the migration
            print("Step 2: Running migration (name → title)...")
            result = session.run("""
                MATCH (p:Principle)
                WHERE p.name IS NOT NULL
                SET p.title = p.name
                REMOVE p.name
                RETURN count(p) as updated_count
            """)
            record = result.single()
            updated = record["updated_count"] if record else 0
            print(f"✓ Updated {updated} Principle nodes")
            print()

            # Step 3: Verify migration
            print("Step 3: Verifying migration...")
            result = session.run("""
                MATCH (p:Principle)
                WITH
                    count(p) as total_principles,
                    count(CASE WHEN p.title IS NOT NULL THEN 1 END) as with_title,
                    count(CASE WHEN p.name IS NOT NULL THEN 1 END) as with_name
                RETURN total_principles, with_title, with_name
            """)
            record = result.single()
            if record:
                total = record["total_principles"]
                with_title = record["with_title"]
                with_name = record["with_name"]

                print(f"  Total principles: {total}")
                print(f"  With 'title' property: {with_title}")
                print(f"  With 'name' property: {with_name}")
                print()

                if with_name == 0 and with_title == total:
                    print("✅ Migration successful!")
                else:
                    print("❌ Migration incomplete!")
                    print(f"   Expected {total} with title, 0 with name")
                    print(f"   Got {with_title} with title, {with_name} with name")
            print()

            # Step 4: Create index
            print("Step 4: Creating index on title field...")
            session.run("""
                CREATE INDEX principle_title_idx IF NOT EXISTS
                FOR (p:Principle) ON (p.title)
            """)
            print("✓ Index created (or already exists)")
            print()

            print("=" * 70)
            print("MIGRATION COMPLETE")
            print("=" * 70)

    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    finally:
        driver.close()

    return True


if __name__ == "__main__":
    success = run_migration()
    exit(0 if success else 1)
