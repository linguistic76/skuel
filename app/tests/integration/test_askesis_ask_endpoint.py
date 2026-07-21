"""
Integration test for Askesis RAG /api/askesis/ask endpoint.

Tests the complete RAG pipeline:
- HTTP validation (sync TestClient — no DB needed)
- RAG pipeline success, entity extraction, semantic search (async — direct service calls)

NOTE: These tests require:
1. Running Neo4j instance
2. OPENAI_API_KEY environment variable (for full app bootstrap)
3. HF_API_TOKEN environment variable (for embeddings)

KNOWN FLAKE: these tests exercise the live OpenAI API end-to-end, so they can
fail transiently (network, rate limits, nondeterministic LLM output). Observed
once 2026-07-20: test_ask_endpoint_success failed in a full-suite run, then
passed in isolation AND on the full re-run of the same commit (during the
neo4j 2026.06.0 bump — the bump was exonerated by exactly this pattern).
Policy: capture the traceback BEFORE re-running; add retry machinery only if
it recurs — a blanket retry could mask a real Askesis regression.
"""

import pytest

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier

# Skip if OPENAI_API_KEY not available (env or keychain) or INTELLIGENCE_TIER != full.
# Askesis requires FULL tier — no degraded mode.
_has_openai_key = bool(get_credential("OPENAI_API_KEY"))
_tier = IntelligenceTier.from_env()
pytestmark = pytest.mark.skipif(
    not _has_openai_key or not _tier.ai_enabled,
    reason="Requires OPENAI_API_KEY (env or keychain) and INTELLIGENCE_TIER=full for Askesis tests",
)


async def _embeddings_available(skuel_app) -> bool:
    """Check if embeddings service is available in the test environment."""
    embeddings = getattr(skuel_app.state.services, "embeddings_service", None)
    return embeddings is not None and getattr(embeddings, "_embedding_client", None) is not None


def test_ask_endpoint_validation(skuel_app):
    """Test that /api/askesis/ask validates required parameters."""
    from starlette.testclient import TestClient

    # Test unauthenticated access (no session) → 401
    with TestClient(skuel_app) as unauthenticated_client:
        response = unauthenticated_client.get("/api/askesis/ask?question=What should I learn?")
        assert response.status_code == 401, "Should reject unauthenticated access"

        # Test missing question also returns 401 (auth check happens first)
        response = unauthenticated_client.get("/api/askesis/ask")
        assert response.status_code == 401, (
            "Should reject unauthenticated access even without question"
        )


@pytest.mark.asyncio
async def test_ask_endpoint_success(skuel_app, enrolled_user_with_lp):
    """Test successful RAG question answering for user enrolled in a Learning Path.

    Uses enrolled_user_with_lp so the pipeline runs past the LP enrollment gate.
    Mode will be 'guided' (PS bundle loaded) or 'llm_generated' (bundle unavailable).
    """
    if not await _embeddings_available(skuel_app):
        pytest.skip("Requires embeddings service for intent classification")
    askesis = skuel_app.state.services.askesis
    user_uid = enrolled_user_with_lp["user_uid"]

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
    assert data["mode"] in ("llm_generated", "guided"), (
        f"Mode should be llm_generated or guided for enrolled user, got: {data['mode']}"
    )


@pytest.mark.asyncio
async def test_ask_endpoint_entity_extraction(skuel_app, populated_test_data):
    """Test that entity extraction works with populated knowledge units."""
    if not await _embeddings_available(skuel_app):
        pytest.skip("Requires embeddings service for intent classification")
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
    if not await _embeddings_available(skuel_app):
        pytest.skip("Requires embeddings service for intent classification")
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


@pytest.mark.asyncio
async def test_enrollment_gate_fires(skuel_app, populated_test_data):
    """User with neither an active PathStep nor an LP enrollment gets the gate response.

    populated_test_data has KUs but no IN_PROGRESS PathStep and no LearningPath
    enrollment, so both user_context.current_ps_uids and enrolled_path_uids are
    empty and the pipeline short-circuits before any LLM call (PS-first gate,
    systems-review Arc B).
    """
    if not await _embeddings_available(skuel_app):
        pytest.skip("Requires embeddings service for intent classification")
    askesis = skuel_app.state.services.askesis
    user_uid = populated_test_data["user_uid"]

    result = await askesis.answer_user_question(user_uid, "What should I learn?")

    assert result.is_ok, f"Pipeline should not error on enrollment gate: {result.error}"
    data = result.value

    assert data["mode"] == "enrollment_gate", (
        f"Expected enrollment_gate mode for user with no PS and no LP, got: {data['mode']}"
    )
    assert "Path Step" in data["answer"], (
        "Enrollment gate response should point at PathStep enrollment first"
    )


@pytest.mark.asyncio
async def test_guided_pipeline_activates(skuel_app, enrolled_user_with_lp):
    """Guided pipeline (ZPD + GuidanceMode) activates for enrolled user with active PathStep.

    This test exercises the path that was previously unverified: when a user is enrolled
    in an LP and has a non-mastered PathStep, Askesis should return mode='guided' and
    populate guidance_mode with one of the four modes (SOCRATIC/DIRECT/EXPLORATORY/ENCOURAGING).
    """
    if not await _embeddings_available(skuel_app):
        pytest.skip("Requires embeddings service for intent classification")
    askesis = skuel_app.state.services.askesis
    user_uid = enrolled_user_with_lp["user_uid"]

    result = await askesis.answer_user_question(
        user_uid, "Explain the concept I'm learning right now"
    )

    assert result.is_ok, f"Guided pipeline failed: {result.error}"
    data = result.value

    assert "answer" in data and len(data["answer"]) > 0, "Should return a non-empty answer"
    assert data["mode"] == "guided", (
        f"Expected guided mode for enrolled user with active PathStep, got: {data['mode']!r}. "
        f"Full response: {data}"
    )
    assert data.get("guidance_mode") is not None, (
        "guidance_mode should be set when pipeline runs in guided mode"
    )
