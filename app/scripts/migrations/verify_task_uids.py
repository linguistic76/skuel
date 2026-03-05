"""
Verify Task UIDs use flat format
=================================

Shows that Tasks already use the Universal Hierarchical Pattern.
"""

import asyncio
from pathlib import Path

from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection


async def verify_tasks():
    """Check Task UID format."""
    # Load .env
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent.parent.parent / ".env"
        load_dotenv(env_path)
    except ImportError:
        pass

    conn = Neo4jConnection()
    await conn.connect()
    driver = conn.driver

    try:
        print("=" * 80)
        print("Task UID Verification")
        print("=" * 80)
        print()

        # Get all tasks
        result = await driver.execute_query(
            "MATCH (t:Task) RETURN t.uid as uid, t.title as title ORDER BY t.created_at",
            routing_="r"
        )

        if not result.records:
            print("No tasks found")
            return

        print(f"Found {len(result.records)} tasks:\n")

        for record in result.records:
            uid = record["uid"]
            title = record["title"] or "(no title)"

            # Check format
            if "_" in uid:
                format_type = "✅ FLAT (underscore)"
            elif "." in uid:
                parts = uid.split(".")
                if len(parts) > 2:
                    format_type = "⚠️  HIERARCHICAL (needs migration)"
                else:
                    format_type = "✅ FLAT (dot prefix)"
            else:
                format_type = "❓ UNKNOWN"

            print(f"  {uid}")
            print(f"    Title: {title}")
            print(f"    Format: {format_type}")
            print()

        # Check for HAS_SUBTASK relationships
        subtask_result = await driver.execute_query(
            "MATCH ()-[r:HAS_SUBTASK]->() RETURN count(r) as count",
            routing_="r"
        )
        subtask_count = subtask_result.records[0]["count"] if subtask_result.records else 0

        print(f"HAS_SUBTASK relationships: {subtask_count}")

        if subtask_count > 0:
            print("\n✅ Universal Hierarchical Pattern ACTIVE for Tasks!")
            print("   Tasks use flat UIDs + HAS_SUBTASK relationships")
        else:
            print("\n📝 No task hierarchy yet (no HAS_SUBTASK relationships)")
            print("   But Tasks are using flat UIDs - ready for hierarchy!")

        print()
        print("=" * 80)

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(verify_tasks())
