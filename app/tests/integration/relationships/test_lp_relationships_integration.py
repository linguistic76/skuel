#!/usr/bin/env python3
"""
Integration Tests: LP Relationship Service (UnifiedRelationshipService)
========================================================================

Tests relationship methods with real Neo4j database.

**January 2026 Unified Architecture:**
LpService.relationships now uses UnifiedRelationshipService with generic API.
Tests use the config-driven relationship aliases from LP_CONFIG.

Methods tested (4):
1. has_relationship("milestones") - Check if learning path has milestone events
2. has_relationship("goals") - Check if learning path supports goals
3. has_relationship("principles") - Check if learning path embodies principles
4. get_related_uids("steps") - Get list of path step UIDs

Pattern: Real Neo4j testcontainer, generic relationship API. Every node carries the
labels the graph gives it (``:Entity:LearningPath``, ``:Entity:PathStep``, …) — the
keyed reads bind a uid by its label, so a node under a label nothing writes is no
anchor.
"""

import pytest

# ============================================================================
# TESTS: has_relationship("milestones") - milestone events
# ============================================================================


@pytest.mark.asyncio
async def test_has_milestone_events_true_integration(
    clean_neo4j, lp_relationship_service, create_relationship
):
    """Test has_relationship('milestones') returns True with real milestone events."""
    # Arrange - Create learning path with milestone events
    lp_uid = "lp.data-science"

    await create_relationship(
        from_uid=lp_uid,
        from_label="Entity:LearningPath",
        to_uid="event.complete-python-course",
        to_label="Entity:Event",
        rel_type="HAS_MILESTONE_EVENT",
    )

    await create_relationship(
        from_uid=lp_uid,
        from_label="Entity:LearningPath",
        to_uid="event.first-ml-project",
        to_label="Entity:Event",
        rel_type="HAS_MILESTONE_EVENT",
    )

    # Act - use generic API with alias from LP_CONFIG
    result = await lp_relationship_service.has_relationship("milestones", lp_uid)

    # Assert
    assert result.is_ok
    assert result.value is True


@pytest.mark.asyncio
async def test_has_milestone_events_false_integration(
    clean_neo4j, lp_relationship_service, create_relationship
):
    """Test has_relationship('milestones') returns False with no milestone events."""
    # Arrange - Create learning path with no milestone events
    lp_uid = "lp.no-milestones"

    # Create LP with other relationships (not HAS_MILESTONE_EVENT)
    await create_relationship(
        from_uid=lp_uid,
        from_label="Entity:LearningPath",
        to_uid="goal.master-ml",
        to_label="Entity:Goal",
        rel_type="ALIGNED_WITH_GOAL",
    )

    # Act
    result = await lp_relationship_service.has_relationship("milestones", lp_uid)

    # Assert
    assert result.is_ok
    assert result.value is False


@pytest.mark.asyncio
async def test_has_milestone_events_nonexistent_lp(clean_neo4j, lp_relationship_service):
    """Test has_relationship('milestones') with nonexistent learning path."""
    # Act
    result = await lp_relationship_service.has_relationship("milestones", "lp:nonexistent")

    # Assert
    assert result.is_ok
    assert result.value is False  # No node = no relationships


# ============================================================================
# TESTS: has_relationship("goals") - goal alignment
# ============================================================================


@pytest.mark.asyncio
async def test_supports_goals_true_integration(
    clean_neo4j, lp_relationship_service, create_relationship
):
    """Test has_relationship('goals') returns True with real goal alignment relationships."""
    # Arrange
    lp_uid = "lp.career-advancement"

    await create_relationship(
        from_uid=lp_uid,
        from_label="Entity:LearningPath",
        to_uid="goal.become-senior-dev",
        to_label="Entity:Goal",
        rel_type="ALIGNED_WITH_GOAL",
    )

    await create_relationship(
        from_uid=lp_uid,
        from_label="Entity:LearningPath",
        to_uid="goal.master-architecture",
        to_label="Entity:Goal",
        rel_type="ALIGNED_WITH_GOAL",
    )

    # Act
    result = await lp_relationship_service.has_relationship("goals", lp_uid)

    # Assert
    assert result.is_ok
    assert result.value is True


@pytest.mark.asyncio
async def test_supports_goals_false_integration(
    clean_neo4j, lp_relationship_service, create_relationship
):
    """Test has_relationship('goals') returns False with no goal alignment relationships."""
    # Arrange
    lp_uid = "lp.exploratory-learning"

    # Create LP with other relationships (not ALIGNED_WITH_GOAL)
    await create_relationship(
        from_uid=lp_uid,
        from_label="Entity:LearningPath",
        to_uid="principle.curiosity",
        to_label="Entity:Principle",
        rel_type="EMBODIES_PRINCIPLE",
    )

    # Act
    result = await lp_relationship_service.has_relationship("goals", lp_uid)

    # Assert
    assert result.is_ok
    assert result.value is False


@pytest.mark.asyncio
async def test_supports_goals_multiple_goals_integration(
    clean_neo4j, lp_relationship_service, create_relationship, count_relationships
):
    """Test has_relationship('goals') with multiple goals (verify count)."""
    # Arrange
    lp_uid = "lp.comprehensive-plan"

    # Create 4 goal alignment relationships
    for i in range(4):
        await create_relationship(
            from_uid=lp_uid,
            from_label="Entity:LearningPath",
            to_uid=f"goal.objective-{i}",
            to_label="Entity:Goal",
            rel_type="ALIGNED_WITH_GOAL",
        )

    # Act
    result = await lp_relationship_service.has_relationship("goals", lp_uid)

    # Assert
    assert result.is_ok
    assert result.value is True

    # Verify actual count in database
    actual_count = await count_relationships(lp_uid, "ALIGNED_WITH_GOAL")
    assert actual_count == 4


# ============================================================================
# TESTS: has_relationship("principles") - principle embodiment
# ============================================================================


@pytest.mark.asyncio
async def test_embodies_principles_true_integration(
    clean_neo4j, lp_relationship_service, create_relationship
):
    """Test has_relationship('principles') returns True with real principle relationships."""
    # Arrange
    lp_uid = "lp.ethical-ai"

    await create_relationship(
        from_uid=lp_uid,
        from_label="Entity:LearningPath",
        to_uid="principle.fairness",
        to_label="Entity:Principle",
        rel_type="EMBODIES_PRINCIPLE",
    )

    await create_relationship(
        from_uid=lp_uid,
        from_label="Entity:LearningPath",
        to_uid="principle.transparency",
        to_label="Entity:Principle",
        rel_type="EMBODIES_PRINCIPLE",
    )

    await create_relationship(
        from_uid=lp_uid,
        from_label="Entity:LearningPath",
        to_uid="principle.accountability",
        to_label="Entity:Principle",
        rel_type="EMBODIES_PRINCIPLE",
    )

    # Act
    result = await lp_relationship_service.has_relationship("principles", lp_uid)

    # Assert
    assert result.is_ok
    assert result.value is True


@pytest.mark.asyncio
async def test_embodies_principles_false_integration(
    clean_neo4j, lp_relationship_service, create_relationship
):
    """Test has_relationship('principles') returns False with no principle relationships."""
    # Arrange
    lp_uid = "lp.technical-skills-only"

    # Create LP with other relationships (not EMBODIES_PRINCIPLE)
    await create_relationship(
        from_uid=lp_uid,
        from_label="Entity:LearningPath",
        to_uid="goal.learn-coding",
        to_label="Entity:Goal",
        rel_type="ALIGNED_WITH_GOAL",
    )

    # Act
    result = await lp_relationship_service.has_relationship("principles", lp_uid)

    # Assert
    assert result.is_ok
    assert result.value is False


# ============================================================================
# TESTS: get_related_uids("steps") - path step UIDs
# ============================================================================


@pytest.mark.asyncio
async def test_get_step_uids_integration(clean_neo4j, lp_relationship_service, create_relationship):
    """Test get_related_uids('steps') returns all path step UIDs."""
    # Arrange
    lp_uid = "lp.python-fundamentals"

    # Create learning path with multiple steps (using HAS_STEP per LP_CONFIG)
    await create_relationship(
        from_uid=lp_uid,
        from_label="Entity:LearningPath",
        to_uid="ps.step-1-basics",
        to_label="Entity:PathStep",
        rel_type="HAS_STEP",
    )

    await create_relationship(
        from_uid=lp_uid,
        from_label="Entity:LearningPath",
        to_uid="ps.step-2-functions",
        to_label="Entity:PathStep",
        rel_type="HAS_STEP",
    )

    await create_relationship(
        from_uid=lp_uid,
        from_label="Entity:LearningPath",
        to_uid="ps.step-3-classes",
        to_label="Entity:PathStep",
        rel_type="HAS_STEP",
    )

    # Act - use generic API with alias from LP_CONFIG
    result = await lp_relationship_service.get_related_uids("steps", lp_uid)

    # Assert
    assert result.is_ok
    assert len(result.value) == 3
    assert "ps.step-1-basics" in result.value
    assert "ps.step-2-functions" in result.value
    assert "ps.step-3-classes" in result.value


@pytest.mark.asyncio
async def test_get_step_uids_empty_integration(clean_neo4j, lp_relationship_service):
    """Test get_related_uids('steps') returns empty list when LP has no steps."""
    # Arrange
    lp_uid = "lp.empty-path"

    # Act
    result = await lp_relationship_service.get_related_uids("steps", lp_uid)

    # Assert
    assert result.is_ok
    assert result.value == []


# ============================================================================
# INTEGRATION TEST SUMMARY
# ============================================================================

"""
Integration Test Coverage (January 2026 Unified Architecture):
==============================================================

Methods Tested via UnifiedRelationshipService Generic API:
- has_relationship("milestones") - ✅ 3 tests (HAS_MILESTONE_EVENT)
- has_relationship("goals") - ✅ 3 tests (ALIGNED_WITH_GOAL)
- has_relationship("principles") - ✅ 2 tests (EMBODIES_PRINCIPLE)
- get_related_uids("steps") - ✅ 2 tests (HAS_STEP)

Total Tests: 10 integration tests

Key Validations:
- Real Neo4j relationships created and queried via UnifiedRelationshipService
- Relationship types verified via config-driven aliases
- Multiple relationships handled correctly
- Nonexistent nodes return False (not errors)
- Database state verified with count_relationships helper

Architectural Note (January 2026):
- LpService.relationships is now UnifiedRelationshipService
- Uses LP_CONFIG with relationship aliases ("milestones", "goals", etc.)
- Generic API: has_relationship(alias, uid), get_related_uids(alias, uid)
- Unified with Activity Domains - same service, domain-specific config

Run: uv run pytest tests/integration/relationships/test_lp_relationships_integration.py -v
"""
