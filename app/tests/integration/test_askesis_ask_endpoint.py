"""
Integration test for Askesis RAG /api/askesis/ask endpoint.

Tests the complete RAG pipeline via HTTP API.

NOTE: These tests require:
1. Running Neo4j instance
2. OPENAI_API_KEY environment variable (for full app bootstrap)
"""

import os

import pytest

# Skip if OPENAI_API_KEY not set (required for full app bootstrap)
_has_openai_key = bool(os.getenv("OPENAI_API_KEY"))
pytestmark = pytest.mark.skipif(
    not _has_openai_key,
    reason="Requires OPENAI_API_KEY environment variable for full app bootstrap",
)


def test_ask_endpoint_validation(authenticated_client_simple):
    """Test that /api/askesis/ask validates required parameters."""

    # Test missing user_uid
    response = authenticated_client_simple.get("/api/askesis/ask?question=What should I learn?")
    assert response.status_code == 400, "Should reject missing user_uid"
    data = response.json()
    assert "message" in data
    assert "user_uid" in data["message"].lower()

    # Test missing question
    response = authenticated_client_simple.get("/api/askesis/ask?user_uid=user.test")
    assert response.status_code == 400, "Should reject missing question"
    data = response.json()
    assert "message" in data
    assert "question" in data["message"].lower()


@pytest.mark.skip(reason="Requires populated Neo4j with user data and knowledge units")
def test_ask_endpoint_success(authenticated_client_simple, populated_test_data):
    """
    Test successful RAG question answering via API.

    SKIP: Requires:
    1. Neo4j populated with user data
    2. Knowledge units with titles
    3. User context available
    4. OpenAI API key configured

    Run this manually after data is loaded.
    """

    # Test successful question
    response = authenticated_client_simple.get(
        "/api/askesis/ask?user_uid=user.mike&question=What should I learn next?"
    )

    # Should return 200 OK
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    # Parse response
    data = response.json()

    # Verify response structure
    assert "answer" in data, "Response should include answer field"
    assert "context_used" in data, "Response should include context_used field"
    assert "suggested_actions" in data, "Response should include suggested_actions field"
    assert "entities_extracted" in data, "Response should include entities_extracted field"

    # Verify answer is non-empty
    assert len(data["answer"]) > 0, "Answer should not be empty"
    assert isinstance(data["answer"], str), "Answer should be a string"

    # Verify suggested actions is a list
    assert isinstance(data["suggested_actions"], list), "Suggested actions should be a list"

    # Verify entities extracted is a dict
    assert isinstance(data["entities_extracted"], dict), "Entities extracted should be a dict"

    print("✅ RAG API endpoint test passed:")
    print(f"   Answer: {data['answer'][:100]}...")
    print(f"   Entities: {data['entities_extracted']}")
    print(f"   Actions: {len(data['suggested_actions'])} suggestions")


@pytest.mark.skip(reason="Requires populated Neo4j with specific knowledge units")
def test_ask_endpoint_entity_extraction(authenticated_client_simple, populated_test_data):
    """
    Test that entity extraction works via API.

    SKIP: Requires specific knowledge units in Neo4j.
    """

    # Ask question mentioning specific entity
    response = authenticated_client_simple.get(
        "/api/askesis/ask?user_uid=user.mike&question=What prerequisites do I need for async programming?"
    )

    assert response.status_code == 200
    data = response.json()

    # Should extract "async programming" entity
    entities = data["entities_extracted"]
    assert "knowledge" in entities, "Should extract knowledge entities"

    knowledge_entities = entities["knowledge"]
    assert len(knowledge_entities) > 0, "Should find at least one knowledge entity"

    # Check if async programming was extracted
    titles = [e["title"].lower() for e in knowledge_entities]
    assert any("async" in title for title in titles), "Should extract async programming entity"

    print("✅ Entity extraction via API:")
    print(f"   Entities found: {knowledge_entities}")


@pytest.mark.skip(reason="Requires OpenAI API key and populated data")
def test_ask_endpoint_semantic_search(authenticated_client_simple, populated_test_data):
    """
    Test that semantic search works via API.

    SKIP: Requires OpenAI embeddings and populated knowledge base.
    """

    # Ask question without exact keyword match
    response = authenticated_client_simple.get(
        "/api/askesis/ask?user_uid=user.mike&question=How do I make my code run concurrently?"
    )

    assert response.status_code == 200
    data = response.json()

    # Should find semantically related content (async programming)
    context_used = data["context_used"]

    # Check if semantic search was used
    if "semantically_similar_knowledge" in context_used:
        similar = context_used["semantically_similar_knowledge"]
        assert len(similar) > 0, "Should find semantically similar knowledge"

        # Should find async-related content even without "async" keyword
        titles = [k["title"].lower() for k in similar]
        print("✅ Semantic search via API found:")
        print(f"   Similar knowledge: {titles}")
