"""
Quick analysis of KU UIDs in the database
==========================================

Simple script to check what KU UIDs exist and which ones are hierarchical.
Uses encrypted credential store for Neo4j password.

Usage:
    uv run python scripts/migrations/analyze_ku_uids.py
"""

import asyncio
from pathlib import Path

from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection


async def analyze():
    """Analyze KU UIDs in database."""
    # Load .env file
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent.parent.parent / ".env"
        load_dotenv(env_path)
    except ImportError:
        pass  # dotenv not required

    # Get connection from environment
    conn = Neo4jConnection()
    await conn.connect()
    driver = conn.driver

    print("=" * 80)
    print("KU UID Analysis")
    print("=" * 80)
    print(f"Connecting to: {conn.uri}")
    print()

    try:
        await driver.verify_connectivity()
        print("✅ Connected to Neo4j")
        print()

        # Count total KUs
        result = await driver.execute_query(
            "MATCH (ku:Ku) RETURN count(ku) as total",
            routing_="r"
        )
        total = result.records[0]["total"] if result.records else 0
        print(f"Total KUs in database: {total}")

        if total == 0:
            print("\n✅ No KUs found - database is empty or KU nodes use different label")
            return

        print()

        # Analyze UID formats
        flat_query = """
        MATCH (ku:Ku)
        WHERE ku.uid CONTAINS '_'
        RETURN count(ku) as count
        """

        hierarchical_query = """
        MATCH (ku:Ku)
        WHERE ku.uid CONTAINS '.'
        AND size(split(ku.uid, '.')) > 2
        RETURN count(ku) as count, collect(ku.uid)[0..5] as examples
        """

        dot_simple_query = """
        MATCH (ku:Ku)
        WHERE ku.uid CONTAINS '.'
        AND size(split(ku.uid, '.')) = 2
        RETURN count(ku) as count, collect(ku.uid)[0..5] as examples
        """

        flat_result = await driver.execute_query(flat_query, routing_="r")
        hierarchical_result = await driver.execute_query(hierarchical_query, routing_="r")
        dot_simple_result = await driver.execute_query(dot_simple_query, routing_="r")

        flat_count = flat_result.records[0]["count"] if flat_result.records else 0
        hierarchical_count = hierarchical_result.records[0]["count"] if hierarchical_result.records else 0
        dot_simple_count = dot_simple_result.records[0]["count"] if dot_simple_result.records else 0

        print("UID Format Breakdown:")
        print(f"  Flat UIDs (underscore):         {flat_count}")
        print(f"  Simple dot notation (ku.name):  {dot_simple_count}")
        print(f"  Hierarchical UIDs (ku.x.y.z):   {hierarchical_count} ⚠️ NEEDS MIGRATION")
        print()

        if hierarchical_count > 0:
            print("Hierarchical UID Examples (need flattening):")
            examples = hierarchical_result.records[0]["examples"]
            for uid in examples:
                print(f"  - {uid}")
            print()

            # Show depth distribution
            depth_query = """
            MATCH (ku:Ku)
            WHERE ku.uid CONTAINS '.'
            AND size(split(ku.uid, '.')) > 2
            WITH size(split(ku.uid, '.')) as depth, count(*) as count
            RETURN depth, count
            ORDER BY depth
            """
            depth_result = await driver.execute_query(depth_query, routing_="r")

            print("Depth Distribution:")
            for record in depth_result.records:
                depth = record["depth"]
                count = record["count"]
                print(f"  Depth {depth}: {count} KUs")
            print()

        if dot_simple_count > 0:
            print("Simple Dot Notation Examples (ku.name format):")
            examples = dot_simple_result.records[0]["examples"]
            for uid in examples[:5]:
                print(f"  - {uid}")
            print()

        # Check for ORGANIZES relationships
        organizes_query = """
        MATCH ()-[r:ORGANIZES]->()
        RETURN count(r) as count
        """
        organizes_result = await driver.execute_query(organizes_query, routing_="r")
        organizes_count = organizes_result.records[0]["count"] if organizes_result.records else 0

        print(f"Existing ORGANIZES relationships: {organizes_count}")
        print()

        # Summary
        print("=" * 80)
        print("SUMMARY")
        print("=" * 80)

        if hierarchical_count == 0:
            print("✅ No hierarchical KU UIDs found!")
            print("   All KUs already use flat UIDs - migration not needed.")
        else:
            print(f"⚠️  {hierarchical_count} hierarchical KU UIDs need migration")
            print(f"   {flat_count + dot_simple_count} KUs already use flat format")
            print()
            print("Next Steps:")
            print("  1. Review migration plan in /docs/migrations/")
            print("  2. Backup database")
            print("  3. Run: uv run python scripts/migrations/flatten_ku_uids.py --dry-run")
            print("  4. If plan looks good: --execute")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure Neo4j is running and credentials are correct:")
        print("  NEO4J_URI=neo4j://localhost:7687")
        print("  NEO4J_USERNAME=neo4j")
        print("  NEO4J_PASSWORD=yourpass")

    finally:
        await conn.close()

    print()
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(analyze())
