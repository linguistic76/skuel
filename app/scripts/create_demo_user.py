#!/usr/bin/env python3
"""
Create demo_user in Neo4j for testing.
"""

import asyncio

from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection
from core.utils.logging import get_logger

logger = get_logger("skuel.scripts.create_demo_user")


async def create_demo_user():
    """Create demo_user in Neo4j."""
    # Use default connection (reads from environment automatically)
    connection = Neo4jConnection()
    await connection.connect()

    driver = connection.driver
    if not driver:
        logger.error("Failed to connect to Neo4j")
        return

    query = """
    MERGE (u:User {uid: $uid})
    ON CREATE SET
        u.username = $username,
        u.email = $email,
        u.display_name = $display_name,
        u.created_at = datetime(),
        u.updated_at = datetime()
    ON MATCH SET
        u.updated_at = datetime()
    RETURN u
    """

    params = {
        "uid": "demo_user",
        "username": "demo",
        "email": "demo@example.com",
        "display_name": "Demo User",
    }

    try:
        async with driver.session() as session:
            result = await session.run(query, params)
            record = await result.single()

            if record:
                logger.info(f"✅ Demo user created/updated: {params['uid']}")
                logger.info(f"   Username: {params['username']}")
                logger.info(f"   Email: {params['email']}")
            else:
                logger.error("Failed to create demo user")

    except Exception as e:
        logger.error(f"Error creating demo user: {e}")

    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(create_demo_user())
