#!/usr/bin/env python3
"""
Simple test to verify chunk storage in Neo4j
"""

import asyncio

from neo4j import AsyncGraphDatabase

from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection


async def verify_chunks():
    connection = Neo4jConnection()
    driver = AsyncGraphDatabase.driver(
        connection.uri, auth=(connection.username, connection.password)
    )

    # First, check what nodes and relationships exist
    query = """
    MATCH (n)
    RETURN DISTINCT labels(n) as labels, count(*) as count
    ORDER BY count DESC
    """

    print("\nNode types in database:")
    async with driver.session() as session:
        result = await session.run(query)
        records = await result.data()
        for record in records:
            print(f"  {record['labels']}: {record['count']} nodes")

    # Check for Content and ContentChunk specifically
    query2 = """
    MATCH (c:Content)
    OPTIONAL MATCH (c)-[:HAS_CHUNK]->(chunk)
    RETURN c.uid as content_uid,
           c.chunk_count as expected_chunks,
           count(chunk) as actual_chunks,
           collect(labels(chunk)[0]) as chunk_labels
    """

    print("\nContent and chunks:")
    async with driver.session() as session:
        result = await session.run(query2)
        records = await result.data()
        for record in records:
            print(f"  Content: {record['content_uid']}")
            print(f"    Expected chunks: {record['expected_chunks']}")
            print(f"    Actual chunks: {record['actual_chunks']}")
            print(f"    Chunk labels: {record['chunk_labels']}")

    # Check all relationships
    query3 = """
    MATCH ()-[r]->()
    RETURN DISTINCT type(r) as rel_type, count(*) as count
    ORDER BY count DESC
    """

    print("\nRelationship types:")
    async with driver.session() as session:
        result = await session.run(query3)
        records = await result.data()
        for record in records:
            print(f"  {record['rel_type']}: {record['count']} relationships")

    # Check for test knowledge
    query4 = """
    MATCH (k:Entity)
    WHERE k.uid CONTAINS 'test'
    RETURN k.uid as uid, k.title as title
    LIMIT 5
    """

    print("\nTest Knowledge nodes:")
    async with driver.session() as session:
        result = await session.run(query4)
        records = await result.data()
        for record in records:
            print(f"  {record['uid']}: {record['title']}")

    await driver.close()


if __name__ == "__main__":
    asyncio.run(verify_chunks())
