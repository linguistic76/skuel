"""
Integration test for Askesis RAG pipeline wiring.

Tests that all RAG dependencies are properly wired in bootstrap.

NOTE: These tests require:
1. OPENAI_API_KEY environment variable (or encrypted credential)
2. Running Neo4j instance

Tests are automatically skipped if credentials are missing.
"""

import os

import pytest

# Skip condition: requires OPENAI_API_KEY for bootstrap
_has_openai_key = bool(os.getenv("OPENAI_API_KEY"))
_skip_without_credentials = pytest.mark.skipif(
    not _has_openai_key,
    reason="Requires OPENAI_API_KEY environment variable for full app bootstrap",
)


@_skip_without_credentials
@pytest.mark.asyncio
async def test_askesis_service_wiring(skuel_app):
    """Test that askesis service is created with all RAG dependencies.

    NOTE: Requires running Neo4j instance. If this test fails with connection
    errors, ensure Neo4j is running: docker start neo4j
    """

    # Get services from bootstrapped app
    services = skuel_app.state.services

    # Verify askesis service exists
    assert services.askesis is not None, "Askesis service not created"

    # Verify askesis has all RAG dependencies
    askesis = services.askesis

    # Phase 1 dependencies (RAG Orchestration)
    assert hasattr(askesis, "user_service"), "Askesis missing user_service (Phase 1: UserContext)"
    assert hasattr(askesis, "llm_service"), "Askesis missing llm_service (Phase 1: LLM generation)"

    # Phase 2 dependencies (Semantic Search)
    assert hasattr(askesis, "embeddings_service"), (
        "Askesis missing embeddings_service (Phase 2: Semantic search)"
    )
    assert hasattr(askesis, "knowledge_service"), (
        "Askesis missing knowledge_service (Phase 2.5: Entity extraction)"
    )

    # Verify dependencies are not None (actually wired)
    assert askesis.user_service is not None, "user_service is None (not wired in bootstrap)"
    assert askesis.llm_service is not None, "llm_service is None (not wired in bootstrap)"
    assert askesis.embeddings_service is not None, (
        "embeddings_service is None (not wired in bootstrap)"
    )
    assert askesis.knowledge_service is not None, (
        "knowledge_service is None (not wired in bootstrap)"
    )

    # Verify RAG method exists
    assert hasattr(askesis, "answer_user_question"), "Askesis missing answer_user_question method"
    assert callable(askesis.answer_user_question), "answer_user_question is not callable"

    print("✅ Askesis RAG wiring verified:")
    print(f"   - user_service: {type(askesis.user_service).__name__}")
    print(f"   - llm_service: {type(askesis.llm_service).__name__}")
    print(f"   - embeddings_service: {type(askesis.embeddings_service).__name__}")
    print(f"   - knowledge_service: {type(askesis.knowledge_service).__name__}")
    print("   - answer_user_question: Available")


@_skip_without_credentials
@pytest.mark.asyncio
async def test_askesis_answer_method_signature(skuel_app):
    """Test that answer_user_question has correct signature.

    NOTE: Requires running Neo4j instance.
    """

    services = skuel_app.state.services
    askesis = services.askesis

    # Check method signature
    import inspect

    sig = inspect.signature(askesis.answer_user_question)
    params = list(sig.parameters.keys())

    # Should accept (self, user_uid, question)
    assert "user_uid" in params, "answer_user_question missing user_uid parameter"
    assert "question" in params, "answer_user_question missing question parameter"

    print("✅ answer_user_question signature verified:")
    print(f"   Parameters: {params}")


@_skip_without_credentials
@pytest.mark.asyncio
async def test_askesis_rag_pipeline_end_to_end(skuel_app, populated_test_data):
    """End-to-end test of RAG pipeline with populated data."""
    embeddings = getattr(skuel_app.state.services, "embeddings_service", None)
    if not (embeddings and getattr(embeddings, "_plugin_available", False)):
        pytest.skip("Requires Neo4j GenAI plugin for intent classification")
    services = skuel_app.state.services
    askesis = services.askesis

    question = "What do I need to learn before async programming?"
    user_uid = populated_test_data["user_uid"]

    # Call RAG pipeline
    answer_result = await askesis.answer_user_question(user_uid, question)

    # Verify response structure
    assert answer_result.is_ok, f"RAG pipeline failed: {answer_result.error}"
    answer_data = answer_result.value

    # Verify expected fields match query_processor.py output
    assert "answer" in answer_data, "Response missing 'answer' field"
    assert "context_used" in answer_data, "Response missing 'context_used' field"
    assert "suggested_actions" in answer_data, "Response missing 'suggested_actions' field"
    assert "confidence" in answer_data, "Response missing 'confidence' field"
    assert "mode" in answer_data, "Response missing 'mode' field"
    assert "has_citations" in answer_data, "Response missing 'has_citations' field"

    # Verify types
    assert isinstance(answer_data["answer"], str), "Answer should be a string"
    assert len(answer_data["answer"]) > 0, "Answer should not be empty"
    assert isinstance(answer_data["suggested_actions"], list), "Suggested actions should be a list"
    assert answer_data["mode"] == "llm_generated", "Mode should be llm_generated"
