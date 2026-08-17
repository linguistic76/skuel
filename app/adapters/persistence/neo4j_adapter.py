"""
Neo4j Repository Adapter
========================

Implements the repository port for Neo4j.
This can be swapped for any other graph database.
"""

__version__ = "1.0"


import logging
from typing import Any

from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection, get_connection
from core.utils.result_simplified import Result

# No longer using GraphRepositoryPort - Neo4jAdapter is a standalone concrete class

logger = logging.getLogger(__name__)

try:
    from neo4j import Record  # noqa: F401 - imported for availability check

    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    logger.warning("Neo4j driver not available")


class Neo4jSessionContext:
    """Async context manager for Neo4j sessions with proper resource cleanup"""

    def __init__(self, driver: Any) -> None:
        self.driver = driver
        self.session = None

    async def __aenter__(
        self,
    ) -> Any:  # skuel-lint: disable=SKUEL029 -- async context-manager protocol: `async with` awaits __aenter__
        """Create and return a Neo4j session"""
        if not self.driver:
            raise RuntimeError("Neo4j driver not available")
        self.session = self.driver.session()
        return self.session

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Close the session with proper cleanup"""
        if self.session:
            await self.session.close()
            self.session = None

        if exc_type:
            logger.error(f"Neo4j session context exit with exception: {exc_val}")


class Neo4jAdapter:
    """
    Neo4j adapter for graph database operations.
    Standalone implementation without legacy port inheritance.
    """

    def __init__(
        self, uri: str | None = None, user: str | None = None, password: str | None = None
    ) -> None:
        self._uri = uri
        self._user = user
        self._password = password
        self.connection: Any = None
        self.driver: Any = None  # Will be set from connection
        self._schema_service: Any = None
        # Initialize logger
        from core.utils.logging import get_logger

        self.logger = get_logger("neo4j_adapter")

    async def connect(self) -> None:
        """Establish connection to Neo4j using Neo4jConnection"""
        if not NEO4J_AVAILABLE:
            raise RuntimeError("Neo4j driver not installed. Run: uv sync")

        if self._uri or self._user or self._password:
            # Explicit credentials provided — create a dedicated connection
            self.connection = Neo4jConnection(
                uri=self._uri, username=self._user, password=self._password
            )
            self.connection.connect()
        else:
            # No explicit credentials — use the app-level singleton
            self.connection = get_connection()

        self.driver = self.connection.driver

        # Bounded exponential-backoff connectivity probe (ADR-080 Horizon 0):
        # tolerate a paused/waking AuraDB Free instance instead of crashing
        # bootstrap on a bare ServiceUnavailable. Single startup chokepoint —
        # every caller of adapter.connect() (app bootstrap + one-shot scripts)
        # inherits the resilience.
        from adapters.persistence.neo4j.neo4j_connection import connect_with_retry
        from core.constants import Neo4jConnectRetry

        await connect_with_retry(
            self.connection,
            max_attempts=Neo4jConnectRetry.MAX_ATTEMPTS,
            base_delay_seconds=Neo4jConnectRetry.BASE_DELAY_SECONDS,
            max_delay_seconds=Neo4jConnectRetry.MAX_DELAY_SECONDS,
        )
        logger.info(f"Connected to Neo4j at {self.connection.uri}")

    def get_driver(self) -> Any:
        """Get the Neo4j driver instance"""
        if not self.driver:
            raise RuntimeError("Neo4j driver not initialized. Call connect() first.")
        return self.driver

    def get_schema_service(self) -> Any:
        """Get schema service instance for database introspection"""
        if not self._schema_service:
            from adapters.persistence.neo4j.schema_service import Neo4jSchemaService

            self._schema_service = Neo4jSchemaService(self)
        return self._schema_service

    async def execute_query(self, query: str, params: dict[str, Any] | None = None) -> list[Any]:
        """Execute a Cypher query using Neo4jConnection"""
        if not self.connection:
            await self.connect()

        # Use the connection's execute_query which returns Record objects
        records = await self.connection.execute_query(query, params)
        if records is None:
            raise RuntimeError(f"Query execution failed: {query[:100]}...")
        return list(records)

    async def close(self) -> None:
        """Close the Neo4j connection"""
        if self.connection:
            await self.connection.close()
            logger.info("Neo4j connection closed")

    async def __aenter__(self) -> "Neo4jAdapter":
        """Async context manager entry"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit with automatic cleanup"""
        await self.close()
        if exc_type:
            logger.error(f"Neo4j adapter context exit with exception: {exc_val}")

    def session_context(self) -> Any:
        """Get an async context manager for Neo4j sessions"""
        return Neo4jSessionContext(self.driver) if self.driver else None

    # Schema Change Detection Methods
    def get_schema_change_detector(self) -> Any:
        """Get the schema change detection service"""
        if not getattr(self, "_schema_change_detector", None):
            from core.services.schema_change_detector import SchemaChangeDetector

            self._schema_change_detector = SchemaChangeDetector(self.get_schema_service())

        return self._schema_change_detector

    async def initialize_schema_monitoring(self, interval_seconds: int = 300) -> Any:
        """
        Initialize and start schema change monitoring.

        Args:
            interval_seconds: How often to check for changes (default: 5 minutes)

        Returns:
            Result[bool] indicating success
        """
        detector = self.get_schema_change_detector()

        # Initialize the detector
        init_result = await detector.initialize()
        if init_result.is_error:
            return init_result

        # Start monitoring
        return await detector.start_monitoring(interval_seconds)

    async def check_schema_changes(self) -> Any:
        """
        Manually check for schema changes.

        Returns:
            Result[SchemaChangeReport] with details of any changes
        """
        detector = self.get_schema_change_detector()
        return await detector.check_for_changes()

    async def stop_schema_monitoring(self) -> Any:
        """Stop schema change monitoring"""
        if getattr(self, "_schema_change_detector", None):
            return await self._schema_change_detector.stop_monitoring()
        return Result.ok(True)

    def get_schema_evolution_stats(self) -> Any:
        """Get statistics about schema evolution over time"""
        if getattr(self, "_schema_change_detector", None):
            return self._schema_change_detector.get_evolution_stats()
        return None
