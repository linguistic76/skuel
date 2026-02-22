"""
Integration test for Askesis RAG /api/askesis/ask endpoint.

Tests the complete RAG pipeline:
- HTTP validation (sync TestClient — no DB needed)
- RAG pipeline success, entity extraction, semantic search (async — direct service calls)

NOTE: These tests require:
1. Running Neo4j instance with GenAI plugin
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


def _genai_plugin_available(skuel_app) -> bool:
    """Check if Neo4j GenAI plugin is available in the test environment."""
    embeddings = getattr(skuel_app.state.services, "embeddings_service", None)
    return bool(embeddings and getattr(embeddings, "_plugin_available", False))


def test_ask_endpoint_validation(skuel_app):
    """Test that /api/askesis/ask validates required parameters."""
    from starlette.testclient import TestClient

    # Test unauthenticated access (no session) → 401
    with TestClient(skuel_app) as unauthenticated_client:
        response = unauthenticated_client.get("/api/askesis/ask?question=What should I learn?")
        assert response.status_code == 401, "Should reject unauthenticated access"

        # Test missing question also returns 401 (auth check happens first)
        response = unauthenticated_client.get("/api/askesis/ask")
        assert response.status_code == 401, "Should reject unauthenticated access even without question"


@pytest.mark.asyncio
async def test_ask_endpoint_success(skuel_app, populated_test_data):
    """Test successful RAG question answering with populated data."""
    if not _genai_plugin_available(skuel_app):
        pytest.skip("Requires Neo4j GenAI plugin for intent classification")
    askesis = skuel_app.state.services.askesis
    user_uid = populated_test_data["user_uid"]

    result = await askesis.answer_user_question(user_uid, "What should I learn next?")

    assert result.is_ok, f"RAG pipeline failed: {result.error}"
    data = result.value

    # Verify response structure matches query_processor.py output
    assert "answer" in data, "Response should include answer field"
    assert "context_used" in data, "Response should include context_used field"
    assert "suggested_actions" in data, "Response should include suggested_actions field"
    assert "confidence" in data, "Response should include confidence field"
    assert "mode" in data, "Response should include mode field"
    assert "has_citations" in data, "Response should include has_citations field"

    # Verify types
    assert isinstance(data["answer"], str), "Answer should be a string"
    assert len(data["answer"]) > 0, "Answer should not be empty"
    assert isinstance(data["suggested_actions"], list), "Suggested actions should be a list"
    assert isinstance(data["confidence"], int | float), "Confidence should be numeric"
    assert 0.0 <= data["confidence"] <= 1.0, "Confidence should be between 0 and 1"
    assert data["mode"] == "llm_generated", "Mode should be llm_generated"


@pytest.mark.asyncio
async def test_ask_endpoint_entity_extraction(skuel_app, populated_test_data):
    """Test that entity extraction works with populated knowledge units."""
    if not _genai_plugin_available(skuel_app):
        pytest.skip("Requires Neo4j GenAI plugin for intent classification")
    askesis = skuel_app.state.services.askesis
    user_uid = populated_test_data["user_uid"]

    result = await askesis.answer_user_question(
        user_uid, "What prerequisites do I need for async programming?"
    )

    assert result.is_ok, f"RAG pipeline failed: {result.error}"
    data = result.value

    # Verify standard response structure
    assert "answer" in data, "Response should include answer field"
    assert "context_used" in data, "Response should include context_used field"
    assert isinstance(data["answer"], str), "Answer should be a string"
    assert len(data["answer"]) > 0, "Answer should not be empty"

    # Context may include mentioned_entities if entity extractor found matches
    context = data["context_used"]
    if "mentioned_entities" in context:
        entities = context["mentioned_entities"]
        assert isinstance(entities, dict), "Mentioned entities should be a dict"


@pytest.mark.asyncio
async def test_ask_endpoint_semantic_search(skuel_app, populated_test_data):
    """Test that semantic search pathway works (question without exact keyword match)."""
    if not _genai_plugin_available(skuel_app):
        pytest.skip("Requires Neo4j GenAI plugin for intent classification")
    askesis = skuel_app.state.services.askesis
    user_uid = populated_test_data["user_uid"]

    # Ask question without exact keyword match — tests semantic understanding
    result = await askesis.answer_user_question(user_uid, "How do I make my code run concurrently?")

    assert result.is_ok, f"RAG pipeline failed: {result.error}"
    data = result.value

    # Verify standard response structure
    assert "answer" in data, "Response should include answer field"
    assert isinstance(data["answer"], str), "Answer should be a string"
    assert len(data["answer"]) > 0, "Answer should not be empty"
    assert "context_used" in data, "Response should include context_used field"
    assert isinstance(data["context_used"], dict), "Context used should be a dict"
