"""
Integration test for Askesis RAG pipeline wiring.

Tests that all RAG dependencies are properly wired in bootstrap.

NOTE: These tests require:
1. OPENAI_API_KEY environment variable (or encrypted credential)
2. Running Neo4j instance

Tests are automatically skipped if credentials are missing.
"""

import pytest

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier

# Skip condition: requires OPENAI_API_KEY (env or keychain) and FULL tier for Askesis
_has_openai_key = bool(get_credential("OPENAI_API_KEY"))
_tier = IntelligenceTier.from_env()
_skip_without_credentials = pytest.mark.skipif(
    not _has_openai_key or not _tier.ai_enabled,
    reason="Requires OPENAI_API_KEY (env or keychain) and INTELLIGENCE_TIER=full for Askesis tests",
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

    # Assert each dependency ON ITS CONSUMER, not on a facade field.
    # This used to check `askesis.embeddings_service` / `askesis.knowledge_service`,
    # which were copies AskesisService itself never read — so the assertions
    # passed whether or not the sub-service that actually uses them was wired,
    # and the copies survived only because this test named them. Asserting the
    # real holder is strictly stronger and keeps the test's original intent.

    # dependencies (RAG Orchestration) — called by the facade itself
    assert askesis.user_service is not None, "user_service is None (not wired in bootstrap)"
    assert askesis.llm_service is not None, "llm_service is None (not wired in bootstrap)"

    # dependencies (Semantic Search) — held by ContextRetriever
    assert askesis.context_retriever is not None, "context_retriever is None (Phase 2)"
    assert askesis.context_retriever.embeddings_service is not None, (
        "embeddings_service is None on ContextRetriever (Phase 2: Semantic search)"
    )

    # dependencies (Entity extraction) — held by EntityExtractor
    assert askesis.entity_extractor is not None, "entity_extractor is None (Phase 2.5)"
    assert askesis.entity_extractor.knowledge_service is not None, (
        "knowledge_service is None on EntityExtractor (Phase 2.5: Entity extraction)"
    )

    # Verify RAG method exists
    assert hasattr(askesis, "answer_user_question"), "Askesis missing answer_user_question method"
    assert callable(askesis.answer_user_question), "answer_user_question is not callable"

    print("✅ Askesis RAG wiring verified:")
    print(f"   - user_service: {type(askesis.user_service).__name__}")
    print(f"   - llm_service: {type(askesis.llm_service).__name__}")
    print(
        "   - embeddings_service: "
        f"{type(askesis.context_retriever.embeddings_service).__name__} (on ContextRetriever)"
    )
    print(
        "   - knowledge_service: "
        f"{type(askesis.entity_extractor.knowledge_service).__name__} (on EntityExtractor)"
    )
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
async def test_askesis_rag_pipeline_end_to_end(skuel_app, enrolled_user_with_lp):
    """End-to-end test of RAG pipeline for user enrolled in a Learning Path.

    Uses enrolled_user_with_lp so the pipeline runs past the LP enrollment gate.
    Mode will be 'guided' (PS bundle loaded) or 'llm_generated' (bundle unavailable).
    """
    embeddings = getattr(skuel_app.state.services, "embeddings_service", None)
    if not embeddings or getattr(embeddings, "_embedding_client", None) is None:
        pytest.skip("Requires embeddings service for intent classification")
    services = skuel_app.state.services
    askesis = services.askesis

    question = "What do I need to learn to progress in my current path?"
    user_uid = enrolled_user_with_lp["user_uid"]

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
    assert answer_data["mode"] in ("llm_generated", "guided"), (
        f"Mode should be llm_generated or guided for enrolled user, got: {answer_data['mode']}"
    )


# NOTE: ADR-059 engagement-bucketing tests moved to
# tests/unit/test_daily_planning_bucketing.py — the bucketing logic now lives
# in DailyPlanningMixin (where it actually runs) rather than in the orphaned
# AskesisService post-processing layer.
