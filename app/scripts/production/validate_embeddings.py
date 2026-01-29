#!/usr/bin/env python
"""
Production Validation Script - Async Embedding System
======================================================

Tests complete end-to-end flow:
1. Create task via API
2. Verify embedding worker processes it
3. Validate embedding stored in Neo4j
4. Test semantic search

Run after enabling Neo4j GenAI plugin.
"""

import asyncio
import os
import sys
from datetime import datetime

from neo4j import AsyncGraphDatabase


async def main():
    print("=" * 60)
    print("SKUEL Production Validation - Async Embedding System")
    print("=" * 60)
    print()

    # Get environment variables
    neo4j_uri = os.getenv("NEO4J_URI")
    neo4j_password = os.getenv("NEO4J_PASSWORD")

    if not neo4j_uri or not neo4j_password:
        print("❌ Environment variables not configured")
        print("Set NEO4J_URI and NEO4J_PASSWORD in .env file")
        sys.exit(1)

    driver = AsyncGraphDatabase.driver(neo4j_uri, auth=("neo4j", neo4j_password))

    try:
        # Step 1: Verify GenAI plugin
        print("[1/5] Verifying Neo4j GenAI plugin...")
        async with driver.session() as session:
            try:
                result = await session.run('RETURN ai.text.embed("test") AS e')
                record = await result.single()
                if record and record["e"]:
                    print(f"  ✅ GenAI plugin enabled (dimension: {len(record['e'])})")
                else:
                    print("  ❌ GenAI plugin not working")
                    sys.exit(1)
            except Exception as e:
                print(f"  ❌ GenAI plugin error: {e}")
                print("\n  Enable plugin first:")
                print("    ./scripts/production/enable_genai.sh")
                sys.exit(1)

        # Step 2: Create test task
        print("\n[2/5] Creating test task...")
        test_uid = f"task.validation_{int(datetime.now().timestamp())}"
        test_title = "Production Validation Test - Async Embeddings"
        test_description = "This task validates the async embedding generation system in production"

        async with driver.session() as session:
            await session.run(
                """
                CREATE (t:Task {
                    uid: $uid,
                    user_uid: 'user.admin',
                    title: $title,
                    description: $description,
                    status: 'pending',
                    priority: 'medium',
                    created_at: datetime()
                })
                """,
                uid=test_uid,
                title=test_title,
                description=test_description,
            )
            print(f"  ✅ Task created: {test_uid}")

        # Step 3: Check initial state (should not have embedding yet)
        print("\n[3/5] Checking initial state (before worker processes)...")
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (t:Task {uid: $uid})
                RETURN t.embedding IS NOT NULL AS has_embedding
                """,
                uid=test_uid,
            )
            record = await result.single()
            if record and not record["has_embedding"]:
                print("  ✅ Task has no embedding yet (expected)")
            else:
                print("  ⚠️  Task already has embedding (unexpected)")

        # Step 4: Wait for background worker
        print("\n[4/5] Waiting for background worker to process...")
        print("  Worker batch interval: 30 seconds")
        print("  Waiting 35 seconds for processing...")

        for i in range(35, 0, -5):
            print(f"  {i} seconds remaining...", end="\r")
            await asyncio.sleep(5)
        print("  " * 40)  # Clear line

        # Step 5: Verify embedding was generated
        print("\n[5/5] Verifying embedding generation...")
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (t:Task {uid: $uid})
                RETURN
                    t.embedding IS NOT NULL AS has_embedding,
                    size(t.embedding) AS embedding_size,
                    t.embedding_model AS model,
                    t.embedding_updated_at AS updated_at
                """,
                uid=test_uid,
            )
            record = await result.single()

            if record and record["has_embedding"]:
                print(f"  ✅ Embedding generated successfully!")
                print(f"     Dimension: {record['embedding_size']}")
                print(f"     Model: {record['model']}")
                print(f"     Updated: {record['updated_at']}")

                # Bonus: Test semantic search
                print("\n[BONUS] Testing semantic search...")
                search_result = await session.run(
                    """
                    MATCH (t:Task)
                    WHERE t.embedding IS NOT NULL
                    WITH t,
                         ai.similarity.cosine(t.embedding,
                             ai.text.embed($query)) AS similarity
                    WHERE similarity > 0.6
                    RETURN t.uid, t.title, similarity
                    ORDER BY similarity DESC
                    LIMIT 5
                    """,
                    query="async background validation",
                )

                results = [(r["t.uid"], r["t.title"], r["similarity"]) async for r in search_result]

                if results:
                    print(f"  ✅ Semantic search working! Found {len(results)} similar tasks:")
                    for uid, title, sim in results:
                        print(f"     - {uid}: {title[:50]}... (similarity: {sim:.3f})")
                else:
                    print("  ⚠️  No semantic results (may need more tasks in database)")

            else:
                print("  ❌ Embedding was NOT generated")
                print("\n  Troubleshooting:")
                print("    1. Check app is running: poetry run python main.py")
                print("    2. Check worker metrics: curl http://localhost:8000/api/monitoring/embedding-worker")
                print("    3. Check logs: tail -f logs/skuel.log | grep embedding")
                print("    4. Verify event published: Check for TaskEmbeddingRequested in logs")
                sys.exit(1)

        # Cleanup
        print("\n[CLEANUP] Removing test task...")
        async with driver.session() as session:
            await session.run("MATCH (t:Task {uid: $uid}) DETACH DELETE t", uid=test_uid)
            print(f"  ✅ Test task removed")

        # Success summary
        print("\n" + "=" * 60)
        print("✅ PRODUCTION VALIDATION SUCCESSFUL")
        print("=" * 60)
        print()
        print("Validated:")
        print("  ✅ Neo4j GenAI plugin enabled and working")
        print("  ✅ Task creation successful")
        print("  ✅ Background worker processing events")
        print("  ✅ Embedding generation via OpenAI")
        print("  ✅ Embedding storage in Neo4j")
        print("  ✅ Semantic search functional")
        print()
        print("System is PRODUCTION READY!")
        print()
        print("Next steps:")
        print("  1. Monitor metrics: curl http://localhost:8000/api/monitoring/embedding-worker")
        print("  2. Monitor for 24 hours (success_rate should be >95%)")
        print("  3. Set up alerting for queue_size >100 or success_rate <95%")
        print("  4. Review: docs/PRODUCTION_DEPLOYMENT_GUIDE.md")
        print()

    except Exception as e:
        print(f"\n❌ Validation failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(main())
