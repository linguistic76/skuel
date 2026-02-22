"""
Integration Tests for GraphQL Type Contracts
=============================================

Tests verify that:
1. Service return types match GraphQL expectations
2. DTO conversion layer works correctly
3. Protocol satisfaction is maintained
4. Type safety is preserved end-to-end

Test Coverage:
- LearningPath service returns properly typed Ls objects
- Knowledge service returns properly typed Ku objects
- Protocol satisfaction (LearningStepLike, KnowledgeUnitLike)
- DTO conversion (from_domain() methods)

Run with:
    poetry run pytest tests/integration/test_graphql_type_contracts.py -v
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from neo4j import AsyncGraphDatabase

from core.models.enums.ku_enums import StepDifficulty
from core.models.ku.entity import Entity
from core.models.ku.ku_dto import KuDTO
from core.models.ku.learning_step import LearningStep
from core.services.lp_service import LpService
from core.services.ls_service import LsService
from routes.graphql.types import LearningStep

if TYPE_CHECKING:
    from routes.graphql.protocols import KnowledgeUnitLike, LearningStepLike

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def type_contract_test_data(neo4j_container, clean_neo4j, ensure_test_users):
    """
    Create test data for type contract testing.

    Creates:
    - 3 Knowledge Units (with prerequisite chain)
    - 3 Learning Steps
    - 1 Learning Path with those steps
    """
    uri = neo4j_container.get_connection_url()
    driver = AsyncGraphDatabase.driver(uri)

    async with driver.session() as session:
        # Create test user
        await session.run(
            """
            MERGE (u:User {uid: $user_uid})
            ON CREATE SET u.created_at = datetime()
            RETURN u
            """,
            user_uid="user.type_contract_test",
        )

        # Create knowledge units
        knowledge_units = [
            {
                "uid": "ku.type_test_basics",
                "title": "Type Testing Basics",
                "summary": "Introduction to type testing",
                "content": "Type testing ensures code correctness...",
                "domain": "TECH",  # Uppercase to match Domain enum
                "quality_score": 0.9,
                "tags": ["testing", "types"],
                "metadata": {},
            },
            {
                "uid": "ku.type_test_advanced",
                "title": "Advanced Type Testing",
                "summary": "Advanced type testing patterns",
                "content": "Advanced patterns include protocol testing...",
                "domain": "TECH",  # Uppercase to match Domain enum
                "quality_score": 0.85,
                "tags": ["testing", "types", "advanced"],
                "metadata": {"deprecated": False, "outdated": False},
            },
            {
                "uid": "ku.type_test_deprecated",
                "title": "Deprecated Type Testing",
                "summary": "Old type testing approach",
                "content": "This approach is deprecated...",
                "domain": "TECH",  # Uppercase to match Domain enum
                "quality_score": 0.6,
                "tags": ["testing", "deprecated"],
                "metadata": {"deprecated": True, "outdated": True},
            },
        ]

        for ku in knowledge_units:
            # Convert metadata dict to JSON string for Neo4j storage
            ku_params = ku.copy()
            if ku_params["metadata"]:
                ku_params["metadata"] = json.dumps(ku_params["metadata"])
            else:
                ku_params["metadata"] = None

            await session.run(
                """
                MERGE (k:Ku {uid: $uid})
                SET k.title = $title,
                    k.summary = $summary,
                    k.content = $content,
                    k.domain = $domain,
                    k.quality_score = $quality_score,
                    k.tags = $tags,
                    k.metadata = $metadata,
                    k.created_at = datetime()
                RETURN k
                """,
                **ku_params,
            )

        # Create prerequisite relationship
        await session.run(
            """
            MATCH (basic:Ku {uid: 'ku.type_test_basics'})
            MATCH (advanced:Ku {uid: 'ku.type_test_advanced'})
            MERGE (advanced)-[:REQUIRES_KNOWLEDGE]->(basic)
            """
        )

        # Create learning steps
        # Unified Ku model: primary_knowledge_uids is a list property
        learning_steps = [
            {
                "uid": "ls.type_test_step_1",
                "title": "Learn Type Testing Basics",
                "intent": "Master basic type testing concepts",
                "primary_knowledge_uids": ["ku.type_test_basics"],
                "sequence": 1,
                "mastery_threshold": 0.7,
                "estimated_hours": 2.0,
            },
            {
                "uid": "ls.type_test_step_2",
                "title": "Advanced Type Testing",
                "intent": "Learn advanced type testing patterns",
                "primary_knowledge_uids": ["ku.type_test_advanced"],
                "sequence": 2,
                "mastery_threshold": 0.8,
                "estimated_hours": 3.0,
            },
            {
                "uid": "ls.type_test_step_3",
                "title": "Type Testing Best Practices",
                "intent": "Apply type testing in production",
                "primary_knowledge_uids": ["ku.type_test_advanced"],
                "sequence": 3,
                "mastery_threshold": 0.85,
                "estimated_hours": 4.0,
            },
        ]

        for step in learning_steps:
            await session.run(
                """
                MERGE (s:Ku {uid: $uid})
                SET s.title = $title,
                    s.intent = $intent,
                    s.primary_knowledge_uids = $primary_knowledge_uids,
                    s.sequence = $sequence,
                    s.mastery_threshold = $mastery_threshold,
                    s.estimated_hours = $estimated_hours,
                    s.ku_type = 'learning_step',
                    s.created_at = datetime()
                RETURN s
                """,
                **step,
            )

        # Create learning path
        await session.run(
            """
            MERGE (p:Ku {uid: 'lp.type_test_path'})
            SET p.title = 'Type Testing Mastery',
                p.description = 'Comprehensive type testing learning path',
                p.total_steps = 3,
                p.estimated_hours = 9.0,
                p.difficulty = 'intermediate',
                p.domain = $domain,
                p.ku_type = 'learning_path',
                p.created_at = datetime()
            RETURN p
            """,
            domain="TECH",  # Uppercase to match Domain enum
        )

        # Create HAS_STEP relationships
        for i in range(1, 4):
            await session.run(
                """
                MATCH (p:Ku {uid: 'lp.type_test_path'})
                MATCH (s:Ku {uid: $step_uid})
                MERGE (p)-[r:HAS_STEP]->(s)
                SET r.sequence = $sequence
                """,
                step_uid=f"ls.type_test_step_{i}",
                sequence=i,
            )

    yield

    # Cleanup handled by clean_neo4j fixture
    await driver.close()


@pytest_asyncio.fixture
async def lp_service(neo4j_container):
    """Create LpService with necessary dependencies."""
    from unittest.mock import MagicMock

    uri = neo4j_container.get_connection_url()
    driver = AsyncGraphDatabase.driver(uri)

    # January 2026: graph_intel is REQUIRED for unified Curriculum architecture
    mock_graph_intel = MagicMock()

    # Create LsService (required by LpService)
    ls_service = LsService(driver=driver, graph_intel=mock_graph_intel, event_bus=None)

    # January 2026: LpIntelligenceService is now created internally by LpService
    # (see CLAUDE.md: "LpIntelligenceService (2026-01-11): LpService now creates intelligence internally")

    # Create LpService with REQUIRED dependencies
    service = LpService(
        driver=driver,
        ls_service=ls_service,
        ku_service=None,  # Optional
        progress_service=None,  # Optional
        graph_intelligence_service=mock_graph_intel,  # REQUIRED
        event_bus=None,  # Optional
    )

    yield service

    await driver.close()


# ============================================================================
# Service Type Contract Tests
# ============================================================================


@pytest.mark.asyncio
async def test_learning_path_service_returns_typed_steps(lp_service, type_contract_test_data):
    """
    Verify LpService.get_path_steps() returns properly typed Ls objects.

    Type Contract:
        - Returns Result[list[Ls]]
        - Each step is an Ls instance
        - Required fields are present and correctly typed
    """
    # Act
    result = await lp_service.get_path_steps("lp.type_test_path")

    # Assert - Result type
    assert result.is_ok, f"Expected success, got error: {result.error}"
    steps = result.value
    assert isinstance(steps, list), "Expected list of steps"
    assert len(steps) == 3, f"Expected 3 steps, got {len(steps)}"

    # Assert - Each step is properly typed
    for i, step in enumerate(steps, 1):
        # Core type check
        assert isinstance(step, Entity), f"Step {i} should be Entity instance, got {type(step)}"

        # Required string fields
        assert isinstance(step.uid, str), f"Step {i} uid should be string"
        assert len(step.uid) > 0, f"Step {i} uid should not be empty"

        assert isinstance(step.title, str), f"Step {i} title should be string"
        assert len(step.title) > 0, f"Step {i} title should not be empty"

        # Tuple fields (not None)
        assert step.primary_knowledge_uids is not None, (
            f"Step {i} primary_knowledge_uids should not be None"
        )
        assert len(step.primary_knowledge_uids) > 0, (
            f"Step {i} should have at least one primary knowledge UID"
        )

        # Numeric fields
        assert isinstance(step.mastery_threshold, float), (
            f"Step {i} mastery_threshold should be float"
        )
        assert 0.0 <= step.mastery_threshold <= 1.0, f"Step {i} mastery_threshold should be 0-1"

        assert isinstance(step.estimated_hours, float), f"Step {i} estimated_hours should be float"
        assert step.estimated_hours > 0, f"Step {i} estimated_hours should be positive"


@pytest.mark.asyncio
async def test_knowledge_service_returns_typed_ku(ku_service, type_contract_test_data):
    """
    Verify KuService returns properly typed KuDTO objects.

    Type Contract:
        - Returns Result[KuDTO | None]
        - KuDTO instance has required fields
        - Metadata field can be None or dict
    """
    # Act
    result = await ku_service.get("ku.type_test_basics")

    # Assert - Result type
    assert result.is_ok, f"Expected success, got error: {result.error}"
    ku = result.value
    assert ku is not None, "Expected knowledge unit to exist"

    # Assert - Core type (service returns KuDTO, not Ku)
    assert isinstance(ku, KuDTO), f"Expected KuDTO instance, got {type(ku)}"

    # Assert - Required fields
    assert isinstance(ku.uid, str), "uid should be string"
    assert len(ku.uid) > 0, "uid should not be empty"

    assert isinstance(ku.title, str), "title should be string"
    assert len(ku.title) > 0, "title should not be empty"

    # Assert - Metadata field (optional but present in our test data)
    assert ku.metadata is None or isinstance(ku.metadata, dict), "metadata should be None or dict"


# ============================================================================
# Protocol Satisfaction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_ls_satisfies_learning_step_like_protocol(lp_service, type_contract_test_data):
    """
    Verify that Ls domain model satisfies LearningStepLike protocol.

    Protocol Contract:
        - Has uid: str attribute
        - Has title: str attribute

    This enables structural typing - any object with these attributes
    can be used in functions expecting LearningStepLike.
    """
    # Arrange
    result = await lp_service.get_path_steps("lp.type_test_path")
    assert result.is_ok
    steps = result.value
    assert len(steps) > 0

    # Act - Assign to protocol type (this would fail at mypy check if protocol not satisfied)
    step: LearningStepLike = steps[0]

    # Assert - Protocol guarantees these attributes exist
    assert hasattr(step, "uid"), "LearningStepLike requires uid attribute"
    assert hasattr(step, "title"), "LearningStepLike requires title attribute"

    # Assert - Types match protocol
    assert isinstance(step.uid, str), "uid should be string"
    assert isinstance(step.title, str), "title should be string"


@pytest.mark.asyncio
async def test_ku_satisfies_knowledge_unit_like_protocol(ku_service, type_contract_test_data):
    """
    Verify that KuDTO satisfies KnowledgeUnitLike protocol.

    Protocol Contract:
        - Has uid: str attribute
        - Has title: str attribute
        - Has metadata: dict[str, Any] | None attribute
    """
    # Arrange
    result = await ku_service.get("ku.type_test_advanced")
    assert result.is_ok
    ku = result.value
    assert ku is not None

    # Act - Assign to protocol type (KuDTO satisfies KnowledgeUnitLike)
    knowledge: KnowledgeUnitLike = ku

    # Assert - Protocol guarantees these attributes exist
    assert hasattr(knowledge, "uid"), "KnowledgeUnitLike requires uid attribute"
    assert hasattr(knowledge, "title"), "KnowledgeUnitLike requires title attribute"
    assert hasattr(knowledge, "metadata"), "KnowledgeUnitLike requires metadata attribute"

    # Assert - Types match protocol
    assert isinstance(knowledge.uid, str), "uid should be string"
    assert isinstance(knowledge.title, str), "title should be string"
    assert knowledge.metadata is None or isinstance(knowledge.metadata, dict), (
        "metadata should be None or dict"
    )


# ============================================================================
# DTO Conversion Tests
# ============================================================================


@pytest.mark.asyncio
async def test_learning_step_from_domain_conversion(lp_service, type_contract_test_data):
    """
    Verify LearningStep.from_domain() correctly converts Ls to GraphQL DTO.

    Conversion Contract:
        - Takes Ls domain model + step_number
        - Returns LearningStep GraphQL DTO
        - Maps fields correctly:
          - uid: direct copy
          - title: direct copy
          - knowledge_uid: extract from primary_knowledge_uids[0]
          - mastery_threshold: direct copy
          - estimated_time: maps from estimated_hours
          - step_number: from parameter
    """
    # Arrange
    result = await lp_service.get_path_steps("lp.type_test_path")
    assert result.is_ok
    steps = result.value
    assert len(steps) > 0

    ls_domain_model = steps[0]
    step_number = 1

    # Act - Convert using from_domain()
    graphql_dto = LearningStep.from_domain(ls_domain_model, step_number)

    # Assert - DTO type
    assert isinstance(graphql_dto, LearningStep), "Should return LearningStep instance"

    # Assert - Field mappings
    assert graphql_dto.uid == ls_domain_model.uid, "uid should be copied directly"
    assert graphql_dto.title == ls_domain_model.title, "title should be copied directly"
    assert graphql_dto.step_number == step_number, "step_number should match parameter"

    # knowledge_uid extracted from primary_knowledge_uids[0]
    expected_knowledge_uid = (
        ls_domain_model.primary_knowledge_uids[0] if ls_domain_model.primary_knowledge_uids else ""
    )
    assert graphql_dto.knowledge_uid == expected_knowledge_uid, (
        "knowledge_uid should be extracted from primary_knowledge_uids"
    )

    # Direct numeric copies
    assert graphql_dto.mastery_threshold == ls_domain_model.mastery_threshold, (
        "mastery_threshold should be copied"
    )

    # Field rename: estimated_hours → estimated_time
    assert graphql_dto.estimated_time == ls_domain_model.estimated_hours, (
        "estimated_time should map from estimated_hours"
    )


@pytest.mark.asyncio
async def test_learning_step_from_domain_handles_empty_knowledge_uids(lp_service):
    """
    Verify from_domain() handles edge case of empty primary_knowledge_uids.

    Edge Case:
        - Ls with empty primary_knowledge_uids tuple
        - Should return empty string for knowledge_uid (not crash)
    """
    # Arrange - Create LearningStep with empty primary_knowledge_uids
    ls_with_no_knowledge = LearningStep(
        uid="ls.test_no_knowledge",
        title="Test Step With No Knowledge",
        intent="Test intent",
        description="Test description",
        primary_knowledge_uids=(),  # Empty tuple
        supporting_knowledge_uids=(),
        learning_path_uid="lp.test",
        sequence=1,
        mastery_threshold=0.7,
        estimated_hours=1.0,
        step_difficulty=StepDifficulty.EASY,
        status="active",
    )

    # Act
    graphql_dto = LearningStep.from_domain(ls_with_no_knowledge, 1)

    # Assert - Should gracefully handle empty tuple
    assert graphql_dto.knowledge_uid == "", (
        "Empty primary_knowledge_uids should map to empty string"
    )
    assert isinstance(graphql_dto.knowledge_uid, str), "knowledge_uid should always be string"


@pytest.mark.asyncio
async def test_learning_step_from_domain_preserves_step_number(lp_service, type_contract_test_data):
    """
    Verify from_domain() correctly uses step_number parameter for sequencing.

    Use Case:
        - When building list of steps for GraphQL query
        - Step number determines display order (1-indexed)
    """
    # Arrange
    result = await lp_service.get_path_steps("lp.type_test_path")
    assert result.is_ok
    steps = result.value
    assert len(steps) >= 3

    # Act - Convert all steps with enumerate
    graphql_steps = [LearningStep.from_domain(step, i + 1) for i, step in enumerate(steps)]

    # Assert - Step numbers are 1-indexed and sequential
    for i, graphql_step in enumerate(graphql_steps, 1):
        assert graphql_step.step_number == i, f"Step {i} should have step_number={i}"

    # Assert - All steps converted successfully
    assert len(graphql_steps) == len(steps), "All steps should be converted"
