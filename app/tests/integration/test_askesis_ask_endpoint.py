"""
Integration test for Askesis RAG /api/askesis/ask endpoint.

Tests the complete RAG pipeline:
- HTTP validation (sync TestClient — no DB needed)
- RAG pipeline success, entity extraction, semantic search (async — direct service calls)

NOTE: These tests require:
1. Running Neo4j instance
2. OPENAI_API_KEY environment variable (for full app bootstrap)
3. HF_API_TOKEN environment variable (for embeddings)

LIVE-LATENCY NOTE: these tests exercise the live OpenAI API end-to-end, so they
can fail transiently (network, rate limits, nondeterministic LLM output). The
first live question of a process is the sensitive one — it pays every one-time
cost INSIDE `AskesisPipelineTimeout.ANSWER_QUESTION_SECONDS` (30s): the rich
UserContext build (~10s cold on the testcontainer: MEGA-QUERY first execution
plus the ZPD capstone) and the intent-exemplar embedding load (48 texts,
`EmbeddingFanOut.MAX_IN_FLIGHT` abreast, ~1s), before the ~3-5s of per-question work. The warm pipeline
runs in ~3s. `test_ask_endpoint_success` is that first question whenever this
module runs alone. A timeout here is therefore a cold-path budget question
first: measure the stages (`-s` shows the structlog stage lines, `--log-cli-level=INFO`
the httpx round-trips) before suspecting the pipeline. Policy stands: capture
the traceback BEFORE re-running; no blanket retry — it would mask a real
Askesis regression.
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

    # NOT `with TestClient(...)`: the context manager runs the ASGI lifespan, and
    # its shutdown closes the SESSION-scoped app's driver and event bus for every
    # test after this one (the neo4j driver still answers after close(), with a
    # deprecation warning, but every `_is_driver_closed()`-guarded backend read
    # silently returns nothing). The routes need no lifespan — the fixture already
    # bootstrapped the services.
    unauthenticated_client = TestClient(skuel_app)

    # Test unauthenticated access (no session) → 401
    response = unauthenticated_client.get("/api/askesis/ask?question=What should I learn?")
    assert response.status_code == 401, "Should reject unauthenticated access"

    # Test missing question also returns 401 (auth check happens first)
    response = unauthenticated_client.get("/api/askesis/ask")
    assert response.status_code == 401, "Should reject unauthenticated access even without question"


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
async def test_ask_endpoint_entity_extraction(
    skuel_app, populated_test_data, enrolled_user_with_lp
):
    """A prerequisite question that names the in-progress PathStep is MATCHED, and cited.

    Entity extraction scopes "knowledge" to the learner's `known_or_engaged_ku_uids`
    (mastered + in-progress targets) and matches their titles from the rich
    context. This learner is engaged with exactly one: the PathStep its
    `IN_PROGRESS` edge points at — `enrolled_user_with_lp["ps_uid"]`, titled
    "Test Guided PathStep". The fixture's Ku is not mastered (see
    `test_ask_endpoint_matches_a_mastered_ku` for that case), and
    `populated_test_data`'s corpus is what retrieval searches, not extraction.
    The question names that title and classifies PREREQUISITE, the intent whose
    citations branch runs only WITH a matched knowledge entity. That branch
    cites the step's evidenced `REQUIRES_KNOWLEDGE` prerequisite (seeded by the
    fixture): the answer carries the Sources & Evidence section naming it, and
    `has_citations` — true only when citation text was produced — says so.
    """
    if not await _embeddings_available(skuel_app):
        pytest.skip("Requires embeddings service for intent classification")
    askesis = skuel_app.state.services.askesis
    user_uid = enrolled_user_with_lp["user_uid"]

    result = await askesis.answer_user_question(
        user_uid, "What do I need to know before Test Guided PathStep?"
    )

    assert result.is_ok, f"RAG pipeline failed: {result.error}"
    data = result.value
    assert data["mode"] != "enrollment_gate", "enrolled learner must reach the pipeline"

    # Verify standard response structure
    assert "answer" in data, "Response should include answer field"
    assert "context_used" in data, "Response should include context_used field"
    assert isinstance(data["answer"], str), "Answer should be a string"
    assert len(data["answer"]) > 0, "Answer should not be empty"

    # The in-progress PathStep is the matched knowledge entity ...
    knowledge = data["context_used"]["mentioned_entities"]["knowledge"]
    assert any(k["uid"] == enrolled_user_with_lp["ps_uid"] for k in knowledge), (
        f"extraction did not match the in-progress PathStep; knowledge = {knowledge!r}"
    )
    # ... and the PREREQUISITE + matched-entity citations branch cited the step's
    # evidenced prerequisite — the answer ends with the Sources & Evidence section
    assert data["has_citations"] is True, "the citations branch produced no citation text"
    assert "Sources & Evidence" in data["answer"], data["answer"][-400:]
    assert "Test Guided Prerequisite" in data["answer"], data["answer"][-400:]


@pytest.mark.asyncio
async def test_ask_endpoint_matches_a_mastered_ku(
    skuel_app, populated_test_data, enrolled_user_with_lp
):
    """A prerequisite question naming a MASTERED Ku matches the Ku, typed as one.

    "Knowledge" extraction matches the question against the titles the rich
    context holds for every MASTERED | IN_PROGRESS target — the concept and the
    step alike — and each match carries the node's ``entity_type``, so a reader
    tells a Ku from a PathStep by that field, never by the uid's spelling
    (ADR-013). The fixture's Ku ("Test Guided Concept") is mastered here; its
    in-progress PathStep ("Test Guided PathStep") shares two title words with the
    question and is matched too, typed as a step.
    """
    if not await _embeddings_available(skuel_app):
        pytest.skip("Requires embeddings service for intent classification")
    services = skuel_app.state.services
    user_uid = enrolled_user_with_lp["user_uid"]
    ku_uid = enrolled_user_with_lp["ku_uid"]
    async with services.neo4j_driver.session() as session:
        await session.run(
            """
            MATCH (u:User {uid: $user_uid})
            MATCH (k:Entity {uid: $ku_uid})
            MERGE (u)-[r:MASTERED]->(k)
            SET r.mastery_score = 1.0, r.mastered_at = datetime()
            """,
            user_uid=user_uid,
            ku_uid=ku_uid,
        )
    # The rich context is cached per user across this module; the new edge must be read.
    await services.user.activity.invalidate_context(user_uid, immediate=True)

    result = await services.askesis.answer_user_question(
        user_uid, "What do I need to know before Test Guided Concept?"
    )

    assert result.is_ok, f"RAG pipeline failed: {result.error}"
    data = result.value
    assert data["mode"] != "enrollment_gate", "enrolled learner must reach the pipeline"
    knowledge = {k["uid"]: k for k in data["context_used"]["mentioned_entities"]["knowledge"]}
    assert ku_uid in knowledge, f"the mastered Ku was not matched; knowledge = {knowledge!r}"
    assert knowledge[ku_uid]["title"] == "Test Guided Concept"
    assert knowledge[ku_uid]["entity_type"] == "ku"
    assert knowledge[enrolled_user_with_lp["ps_uid"]]["entity_type"] == "path_step"


@pytest.mark.asyncio
async def test_ask_endpoint_semantic_search(skuel_app, populated_test_data, enrolled_user_with_lp):
    """A question with no keyword match runs the full pipeline for an enrolled learner.

    Same fixture pairing as `test_ask_endpoint_entity_extraction`, and its other
    half: that test proves the pipeline cites when extraction MATCHES; this one
    proves it still answers when extraction finds NOTHING (the question names
    no engaged entity) and retrieval alone carries the context.
    """
    if not await _embeddings_available(skuel_app):
        pytest.skip("Requires embeddings service for intent classification")
    askesis = skuel_app.state.services.askesis
    user_uid = enrolled_user_with_lp["user_uid"]

    # Ask question without exact keyword match — tests semantic understanding
    result = await askesis.answer_user_question(user_uid, "How do I make my code run concurrently?")

    assert result.is_ok, f"RAG pipeline failed: {result.error}"
    data = result.value
    assert data["mode"] != "enrollment_gate", "enrolled learner must reach the pipeline"

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
