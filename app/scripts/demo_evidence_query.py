#!/usr/bin/env python3
"""
Demo: Query and Display Evidence from Knowledge Graph
"""

import asyncio
import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase

from core.config.credential_store import get_credential

load_dotenv()


async def demo_evidence_query():
    """Query a relationship and display its evidence."""
    # Get credentials
    neo4j_uri = get_credential("NEO4J_URI") or os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = get_credential("NEO4J_USER") or os.getenv("NEO4J_USERNAME", "neo4j")
    neo4j_password = get_credential("NEO4J_PASSWORD", fallback_to_env=True)

    if neo4j_uri.startswith("neo4j://"):
        neo4j_uri = neo4j_uri.replace("neo4j://", "bolt://")

    driver = AsyncGraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

    try:
        async with driver.session() as session:
            # Query a high-quality relationship with evidence
            query = """
            MATCH (from:Entity)-[r:REQUIRES]->(to:Entity)
            WHERE size(r.evidence) > 0
            RETURN
                from.uid as from_uid,
                from.title as from_title,
                to.uid as to_uid,
                to.title as to_title,
                r.source as source,
                r.confidence as confidence,
                r.strength as strength,
                r.evidence as evidence,
                r.notes as notes
            ORDER BY r.confidence DESC
            LIMIT 3
            """

            result = await session.run(query)

            print("=" * 80)
            print("EVIDENCE-BACKED RELATIONSHIPS")
            print("=" * 80)
            print()

            count = 0
            async for record in result:
                count += 1
                print(f"{count}. {record['from_title']}")
                print(f"   REQUIRES → {record['to_title']}")
                print(f"   Source: {record['source']}")
                print(
                    f"   Confidence: {record['confidence']:.2f} | Strength: {record['strength']:.2f}"
                )
                print(f"   Evidence ({len(record['evidence'])} citations):")
                for i, citation in enumerate(record["evidence"], 1):
                    print(f"     {i}. {citation}")
                if record["notes"]:
                    print(f"   Note: {record['notes']}")
                print()

            print("=" * 80)

            # Show evidence statistics
            stats_query = """
            MATCH ()-[r:REQUIRES]->()
            WHERE size(r.evidence) > 0
            RETURN
                count(r) as total_with_evidence,
                avg(r.confidence) as avg_confidence,
                avg(size(r.evidence)) as avg_citations,
                max(size(r.evidence)) as max_citations,
                min(size(r.evidence)) as min_citations
            """

            result = await session.run(stats_query)
            stats = await result.single()

            print("EVIDENCE STATISTICS")
            print("=" * 80)
            print(f"Total relationships with evidence: {stats['total_with_evidence']}")
            print(f"Average confidence: {stats['avg_confidence']:.2f}")
            print(f"Average citations per relationship: {stats['avg_citations']:.1f}")
            print(f"Citations range: {stats['min_citations']}-{stats['max_citations']}")
            print("=" * 80)

    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(demo_evidence_query())
