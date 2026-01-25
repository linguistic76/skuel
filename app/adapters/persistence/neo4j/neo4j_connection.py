"""
Neo4j Connection Wrapper
========================

Simple connection wrapper for Neo4j database operations.
Used by migration and index scripts.
"""

__version__ = "1.0"


import os
from typing import Any

from neo4j import AsyncGraphDatabase, Record

from core.config.settings import get_settings

# Protocols
from core.utils.logging import get_logger

logger = get_logger(__name__)

_connection_instance = None


class Neo4jConnection:
    """
    Simple Neo4j connection wrapper for script operations.
    """

    def __init__(
        self, uri: str | None = None, username: str | None = None, password: str | None = None
    ) -> None:
        """
        Initialize Neo4j connection.

        Args:
            uri: Neo4j URI (defaults to env/settings)
            username: Neo4j username (defaults to env/settings)
            password: Neo4j password (defaults to encrypted credential store)
        """
        from core.config.credential_store import get_credential

        settings = get_settings()
        db_config = getattr(settings, "database", settings)

        self.uri = (
            uri
            or getattr(db_config, "neo4j_uri", None)
            or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        )
        self.username = (
            username
            or getattr(db_config, "neo4j_username", None)
            or os.getenv("NEO4J_USER", "neo4j")
        )

        # Use encrypted credential store for password (with env fallback for migration)
        self.password = (
            password
            or getattr(db_config, "neo4j_password", None)
            or get_credential("NEO4J_PASSWORD", fallback_to_env=True)
        )

        self.driver = None

    async def connect(self):
        """Establish connection to Neo4j."""
        if not self.driver:
            self.driver = AsyncGraphDatabase.driver(self.uri, auth=(self.username, self.password))
            logger.info(f"Connected to Neo4j at {self.uri}")

    async def close(self):
        """Close the connection."""
        if self.driver:
            await self.driver.close()
            self.driver = None
            logger.info("Closed Neo4j connection")

    async def test_connection(self) -> bool:
        """
        Test if the connection is working.

        Returns:
            True if connection is successful, False otherwise
        """
        try:
            await self.connect()
            if self.driver is None:
                return False
            async with self.driver.session() as session:
                result = await session.run("RETURN 1 as test")
                data = await result.single()
                return data and data["test"] == 1
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False

    async def execute_query(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[Record] | None:
        """
        Execute a Cypher query.

        Args:
            query: Cypher query string,
            params: Query parameters

        Returns:
            List of Neo4j Record objects, or None if error
        """
        try:
            await self.connect()
            if self.driver is None:
                return None

            async with self.driver.session() as session:
                result = await session.run(query, params or {})
                # Collect all records as Record objects
                return [record async for record in result]

        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            logger.error(f"Query: {query[:200]}...")
            return None


async def get_connection() -> Neo4jConnection:
    """
    Get or create a singleton Neo4j connection.

    Returns:
        Neo4jConnection instance
    """
    global _connection_instance

    if _connection_instance is None:
        _connection_instance = Neo4jConnection()
        await _connection_instance.connect()

    return _connection_instance
