"""
Debug test to verify relationship properties are being stored.
"""

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums import Domain, SELCategory
from core.models.curriculum.curriculum import Curriculum


@pytest.mark.asyncio
class TestRelationshipPropertiesDebug:
    """Debug tests for relationship property persistence."""

    @pytest_asyncio.fixture
    async def ku_backend(self, neo4j_driver, clean_neo4j):
        """Create KU backend with clean database."""
        return UniversalNeo4jBackend[Curriculum](neo4j_driver, "Entity", Curriculum)

    async def test_relationship_properties_are_stored(self, ku_backend):
        """Verify that relationship properties are actually persisted."""
        # Create two KUs
        ku1 = Curriculum(
            uid="ku:test1",
            title="Test 1",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_MANAGEMENT,
        )
        ku2 = Curriculum(
            uid="ku:test2",
            title="Test 2",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_MANAGEMENT,
        )

        result = await ku_backend.create(ku1)
        assert result.is_ok, f"Setup failed: Could not create Ku1: {result.error}"
        result = await ku_backend.create(ku2)
        assert result.is_ok, f"Setup failed: Could not create Ku2: {result.error}"

        # Create relationship with properties
        # Note: Ku entities use REQUIRES_KNOWLEDGE for prerequisites (not PREREQUISITE)
        result = await ku_backend.create_relationships_batch(
            [
                (
                    "ku:test1",
                    "ku:test2",
                    "REQUIRES_KNOWLEDGE",
                    {"strength": 0.9, "prerequisite_type": "foundational"},
                )
            ]
        )

        assert result.is_ok
        assert result.value == 1  # One relationship created

        # Query the relationship directly to check properties
        query = """
        MATCH (a:Entity {uid: $from_uid})-[r:REQUIRES_KNOWLEDGE]->(b:Entity {uid: $to_uid})
        RETURN r.strength as strength, r.prerequisite_type as prereq_type
        """

        result = await ku_backend.execute_query(
            query, {"from_uid": "ku:test1", "to_uid": "ku:test2"}
        )

        assert result.is_ok
        assert len(result.value) == 1

        record = result.value[0]
        print(
            f"Relationship properties: strength={record.get('strength')}, type={record.get('prereq_type')}"
        )

        # Verify properties are actually stored
        assert record.get("strength") == 0.9, f"Expected strength 0.9, got {record.get('strength')}"
        assert record.get("prereq_type") == "foundational", (
            f"Expected 'foundational', got {record.get('prereq_type')}"
        )
