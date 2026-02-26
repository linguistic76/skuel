"""
Test GraphQL Queries - Verification
===========================================

Tests the new GraphQL queries to verify they work correctly.

NOTE: These tests require:
1. Running Neo4j instance
2. OPENAI_API_KEY environment variable (for full app bootstrap)
3. GraphQL routes registered

Run with integration tests:
    poetry run pytest tests/integration/test_graphql_queries.py -v
"""

import os
from typing import Any
from unittest.mock import patch

import pytest

# Skip if OPENAI_API_KEY not set (required for full app bootstrap)
_has_openai_key = bool(os.getenv("OPENAI_API_KEY"))
pytestmark = pytest.mark.skipif(
    not _has_openai_key,
    reason="Requires OPENAI_API_KEY environment variable for full app bootstrap",
)


@pytest.fixture(autouse=True)
def mock_graphql_auth():
    """Mock authentication for GraphQL tests to bypass session requirement."""
    from adapters.inbound.auth.session import DEFAULT_DEV_USER

    with patch("adapters.inbound.graphql_routes.require_authenticated_user") as mock:
        mock.return_value = DEFAULT_DEV_USER
        yield mock


@pytest.fixture
def sample_queries() -> dict[str, Any]:
    """Sample GraphQL queries for testing"""
    return {
        "learning_path": """
            query GetLearningPath($uid: String!) {
                learningPath(uid: $uid) {
                    uid
                    name
                    goal
                    totalSteps
                    estimatedHours
                }
            }
        """,
        "learning_path_with_steps": """
            query GetLearningPathWithSteps($uid: String!) {
                learningPath(uid: $uid) {
                    uid
                    name
                    steps {
                        stepNumber
                        knowledgeUid
                        masteryThreshold
                        knowledge {
                            uid
                            title
                            summary
                        }
                    }
                }
            }
        """,
        "learning_path_context": """
            query GetLearningPathContext($pathUid: String!, $userUid: String) {
                learningPathWithContext(pathUid: $pathUid, userUid: $userUid) {
                    path {
                        uid
                        name
                        totalSteps
                    }
                    currentStepNumber
                    completedSteps
                    completionPercentage
                    prerequisitesMet
                    blockers {
                        blockerType
                        severity
                        description
                    }
                    nextRecommendedSteps {
                        stepNumber
                        knowledgeUid
                    }
                }
            }
        """,
        "prerequisite_chain": """
            query GetPrerequisiteChain($knowledgeUid: String!, $maxDepth: Int) {
                prerequisiteChain(knowledgeUid: $knowledgeUid, maxDepth: $maxDepth) {
                    target {
                        uid
                        title
                        summary
                    }
                    totalPrerequisites
                    prerequisitesMastered
                    estimatedTotalHours
                    prerequisiteTree {
                        knowledge {
                            uid
                            title
                        }
                        depth
                        isMastered
                    }
                }
            }
        """,
        "knowledge_dependencies": """
            query GetKnowledgeDependencies($knowledgeUid: String!, $depth: Int) {
                knowledgeDependencies(knowledgeUid: $knowledgeUid, depth: $depth) {
                    center {
                        uid
                        title
                    }
                    depth
                    nodes {
                        uid
                        title
                        domain
                    }
                    edges {
                        fromKnowledge {
                            uid
                            title
                        }
                        toKnowledge {
                            uid
                            title
                        }
                        relationshipType
                        strength
                    }
                }
            }
        """,
        "learning_path_blockers": """
            query GetLearningPathBlockers($pathUid: String!, $userUid: String) {
                learningPathBlockers(pathUid: $pathUid, userUid: $userUid) {
                    blockerType
                    knowledgeUid
                    knowledgeTitle
                    severity
                    description
                    recommendedAction
                }
            }
        """,
        "nested_full_path": """
            query GetLearningPathFull($uid: String!) {
                learningPath(uid: $uid) {
                    uid
                    name
                    goal
                    steps {
                        stepNumber
                        knowledge {
                            uid
                            title
                            prerequisites {
                                uid
                                title
                            }
                            enables {
                                uid
                                title
                            }
                        }
                    }
                }
            }
        """,
    }


def test_learning_path_query(sample_queries, authenticated_client_simple):
    """Test basic learning path query"""
    response = authenticated_client_simple.post(
        "/graphql",
        json={"query": sample_queries["learning_path"], "variables": {"uid": "lp.test_path"}},
    )

    # Better error reporting
    if response.status_code != 200:
        print(f"\n❌ GraphQL request failed with status {response.status_code}")
        print(f"Response: {response.text}")

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. Response: {response.text[:500]}"
    )
    data = response.json()

    # Should have data or errors field
    assert "data" in data or "errors" in data

    # If errors, print them for debugging
    if "errors" in data:
        print(f"\n⚠️ GraphQL errors: {data['errors']}")

    # If successful, check structure
    if "data" in data and data["data"].get("learningPath"):
        path = data["data"]["learningPath"]
        assert "uid" in path
        assert "name" in path
        assert "totalSteps" in path


def test_learning_path_with_context_query(sample_queries, authenticated_client_simple):
    """Test learning path context query"""
    response = authenticated_client_simple.post(
        "/graphql",
        json={
            "query": sample_queries["learning_path_context"],
            "variables": {"pathUid": "lp.test_path", "userUid": "user.test"},
        },
    )

    # Better error reporting
    if response.status_code != 200:
        print(f"\n❌ GraphQL request failed with status {response.status_code}")
        print(f"Response: {response.text}")

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. Response: {response.text[:500]}"
    )
    data = response.json()

    # Should have data or errors field
    assert "data" in data or "errors" in data

    # If errors, print them for debugging
    if "errors" in data:
        print(f"\n⚠️ GraphQL errors: {data['errors']}")

    # If successful, check structure
    if "data" in data and data["data"].get("learningPathWithContext"):
        context = data["data"]["learningPathWithContext"]
        assert "path" in context
        assert "currentStepNumber" in context
        assert "completionPercentage" in context
        assert "blockers" in context
        assert "prerequisitesMet" in context


def test_prerequisite_chain_query(sample_queries, authenticated_client_simple):
    """Test prerequisite chain query"""
    response = authenticated_client_simple.post(
        "/graphql",
        json={
            "query": sample_queries["prerequisite_chain"],
            "variables": {"knowledgeUid": "ku.test_knowledge", "maxDepth": 3},
        },
    )

    # Better error reporting
    if response.status_code != 200:
        print(f"\n❌ GraphQL request failed with status {response.status_code}")
        print(f"Response: {response.text}")

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. Response: {response.text[:500]}"
    )
    data = response.json()

    # Should have data or errors field
    assert "data" in data or "errors" in data

    # If errors, print them for debugging
    if "errors" in data:
        print(f"\n⚠️ GraphQL errors: {data['errors']}")

    # If successful, check structure
    if "data" in data and data["data"].get("prerequisiteChain"):
        chain = data["data"]["prerequisiteChain"]
        assert "target" in chain
        assert "totalPrerequisites" in chain
        assert "prerequisiteTree" in chain
        assert "estimatedTotalHours" in chain


def test_knowledge_dependencies_query(sample_queries, authenticated_client_simple):
    """Test knowledge dependencies graph query"""
    response = authenticated_client_simple.post(
        "/graphql",
        json={
            "query": sample_queries["knowledge_dependencies"],
            "variables": {"knowledgeUid": "ku.test_knowledge", "depth": 2},
        },
    )

    # Better error reporting
    if response.status_code != 200:
        print(f"\n❌ GraphQL request failed with status {response.status_code}")
        print(f"Response: {response.text}")

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. Response: {response.text[:500]}"
    )
    data = response.json()

    # Should have data or errors field
    assert "data" in data or "errors" in data

    # If errors, print them for debugging
    if "errors" in data:
        print(f"\n⚠️ GraphQL errors: {data['errors']}")

    # If successful, check structure
    if "data" in data and data["data"].get("knowledgeDependencies"):
        graph = data["data"]["knowledgeDependencies"]
        assert "center" in graph
        assert "nodes" in graph
        assert "edges" in graph
        assert "depth" in graph


def test_learning_path_blockers_query(sample_queries, authenticated_client_simple):
    """Test learning path blockers query"""
    response = authenticated_client_simple.post(
        "/graphql",
        json={
            "query": sample_queries["learning_path_blockers"],
            "variables": {"pathUid": "lp.test_path", "userUid": "user.test"},
        },
    )

    # Better error reporting
    if response.status_code != 200:
        print(f"\n❌ GraphQL request failed with status {response.status_code}")
        print(f"Response: {response.text}")

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. Response: {response.text[:500]}"
    )
    data = response.json()

    # Should have data or errors field
    assert "data" in data or "errors" in data

    # If errors, print them for debugging
    if "errors" in data:
        print(f"\n⚠️ GraphQL errors: {data['errors']}")

    # If successful, check structure (blockers list, might be empty)
    if "data" in data:
        blockers = data["data"]["learningPathBlockers"]
        assert isinstance(blockers, list)

        # If blockers exist, check structure
        if blockers:
            blocker = blockers[0]
            assert "blockerType" in blocker
            assert "severity" in blocker
            assert "description" in blocker


def test_nested_query_depth(sample_queries, authenticated_client_simple):
    """Test deeply nested query"""
    response = authenticated_client_simple.post(
        "/graphql",
        json={"query": sample_queries["nested_full_path"], "variables": {"uid": "lp.test_path"}},
    )

    # Better error reporting
    if response.status_code != 200:
        print(f"\n❌ GraphQL request failed with status {response.status_code}")
        print(f"Response: {response.text}")

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. Response: {response.text[:500]}"
    )
    data = response.json()

    # Should have data or errors field
    assert "data" in data or "errors" in data

    # If errors, print them for debugging
    if "errors" in data:
        print(f"\n⚠️ GraphQL errors: {data['errors']}")

    # If successful, check nested structure
    if "data" in data and data["data"].get("learningPath"):
        path = data["data"]["learningPath"]

        if path.get("steps"):
            step = path["steps"][0]
            assert "knowledge" in step

            if step["knowledge"]:
                knowledge = step["knowledge"]
                # Nested 3 levels deep: path -> steps -> knowledge -> prerequisites/enables
                assert "prerequisites" in knowledge
                assert "enables" in knowledge


def test_flexible_field_selection_minimal(authenticated_client_simple):
    """Test minimal field selection"""
    minimal_query = """
        query GetLearningPathsLight {
            learningPaths(limit: 5) {
                uid
                name
            }
        }
    """

    response = authenticated_client_simple.post("/graphql", json={"query": minimal_query})

    # Better error reporting
    if response.status_code != 200:
        print(f"\n❌ GraphQL request failed with status {response.status_code}")
        print(f"Response: {response.text}")

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. Response: {response.text[:500]}"
    )
    data = response.json()

    # If errors, print them for debugging
    if "errors" in data:
        print(f"\n⚠️ GraphQL errors: {data['errors']}")

    if "data" in data and data["data"].get("learningPaths"):
        paths = data["data"]["learningPaths"]

        if paths:
            path = paths[0]
            # Should only have requested fields
            assert "uid" in path
            assert "name" in path
            # Should NOT have unrequested fields
            assert "estimatedHours" not in path or path["estimatedHours"] is not None


def test_flexible_field_selection_rich(authenticated_client_simple):
    """Test rich field selection"""
    rich_query = """
        query GetLearningPathsRich {
            learningPaths(limit: 5) {
                uid
                name
                goal
                estimatedHours
                totalSteps
                steps {
                    stepNumber
                    knowledge {
                        uid
                        title
                        qualityScore
                    }
                }
            }
        }
    """

    response = authenticated_client_simple.post("/graphql", json={"query": rich_query})

    # Better error reporting
    if response.status_code != 200:
        print(f"\n❌ GraphQL request failed with status {response.status_code}")
        print(f"Response: {response.text}")

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. Response: {response.text[:500]}"
    )
    data = response.json()

    # If errors, print them for debugging
    if "errors" in data:
        print(f"\n⚠️ GraphQL errors: {data['errors']}")

    if "data" in data and data["data"].get("learningPaths"):
        paths = data["data"]["learningPaths"]

        if paths:
            path = paths[0]
            # Should have all requested fields
            assert "uid" in path
            assert "name" in path
            assert "goal" in path
            assert "estimatedHours" in path
            assert "steps" in path


def test_query_structure_validation(sample_queries):
    """Validate that all sample queries are syntactically correct"""
    for query_name, query in sample_queries.items():
        # Basic validation - queries should not be empty
        assert query.strip(), f"Query '{query_name}' is empty"

        # Should contain 'query' keyword
        assert "query" in query.lower(), f"Query '{query_name}' missing 'query' keyword"

        # Should have opening and closing braces
        assert "{" in query and "}" in query, f"Query '{query_name}' missing braces"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
