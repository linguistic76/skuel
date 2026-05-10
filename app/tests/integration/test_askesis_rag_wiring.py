"""
Integration test for Askesis RAG pipeline wiring.

Tests that all RAG dependencies are properly wired in bootstrap.

NOTE: These tests require:
1. OPENAI_API_KEY environment variable (or encrypted credential)
2. Running Neo4j instance

Tests are automatically skipped if credentials are missing.
"""

import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.config.intelligence_tier import IntelligenceTier
from core.models.context_types import DailyWorkPlan
from core.services.askesis_service import AskesisService
from core.services.ps_engagement.engagement import Engagement
from core.utils.result_simplified import Errors, Result

# Skip condition: requires OPENAI_API_KEY and FULL tier for Askesis
_has_openai_key = bool(os.getenv("OPENAI_API_KEY"))
_tier = IntelligenceTier.from_env()
_skip_without_credentials = pytest.mark.skipif(
    not _has_openai_key or not _tier.ai_enabled,
    reason="Requires OPENAI_API_KEY and INTELLIGENCE_TIER=full for Askesis tests",
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

    # dependencies (RAG Orchestration)
    assert hasattr(askesis, "user_service"), "Askesis missing user_service (Phase 1: UserContext)"
    assert hasattr(askesis, "llm_service"), "Askesis missing llm_service (Phase 1: LLM generation)"

    # dependencies (Semantic Search)
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
    if not embeddings or embeddings._client is None:
        pytest.skip("Requires embeddings service for intent classification")
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


# ============================================================================
# ADR-059 — Engagement-aware daily plan bucketing
# ============================================================================
#
# These tests exercise AskesisService.get_daily_work_plan's post-processing
# layer: it takes the flat plan from UserContextIntelligence and folds in
# engagement state from PsEngagementService. The core bucketing logic is
# pure, so the tests stub the two collaborators and assert the resulting
# DailyWorkPlan shape — no Neo4j or LLM dependencies.


def _engagement(
    ps_uid: str,
    spawned: tuple[str, ...] = (),
    state: str = "engaged",
) -> Engagement:
    return Engagement(
        student_uid="user_1",
        ps_uid=ps_uid,
        state=state,  # type: ignore[arg-type]
        since=datetime(2026, 5, 3, 10, 0, tzinfo=UTC),
        spawned_instance_uids=spawned,
    )


def _user_context(ps_uids_in_active: tuple[str, ...] = (), user_uid: str = "user_1") -> MagicMock:
    ctx = MagicMock()
    ctx.user_uid = user_uid
    ctx.active_path_steps_rich = [
        {"step": {"uid": uid}, "graph_context": {}} for uid in ps_uids_in_active
    ]
    return ctx


def _askesis_with_stubbed_plan(
    plan: DailyWorkPlan,
    engagements: list[Engagement] | None,
    list_engaged_ok: bool = True,
) -> AskesisService:
    """Build an AskesisService with intelligence_factory and ps_engagement_service stubbed."""
    askesis = AskesisService.__new__(AskesisService)  # bypass __init__ wiring

    intelligence = MagicMock()
    intelligence.get_ready_to_work_on_today = AsyncMock(return_value=Result.ok(plan))
    factory = MagicMock()
    factory.create = MagicMock(return_value=intelligence)
    askesis.intelligence_factory = factory

    ps_eng = MagicMock()
    if list_engaged_ok:
        ps_eng.list_engaged = AsyncMock(return_value=Result.ok(engagements or []))
    else:
        ps_eng.list_engaged = AsyncMock(
            return_value=Result.fail(Errors.database(operation="list_engaged", message="boom"))
        )
    askesis.ps_engagement_service = ps_eng

    return askesis


@pytest.mark.asyncio
async def test_daily_plan_buckets_engaged_with_pending_spawned_activities() -> None:
    """An engaged PS with spawned tasks/habits surfaces those UIDs in the group."""
    plan = DailyWorkPlan(
        tasks=("task_a", "task_b", "task_orphan"),
        habits=("habit_a",),
        events=(),
    )
    eng = _engagement("ps:algebra", spawned=("task_a", "habit_a", "task_completed_yesterday"))
    askesis = _askesis_with_stubbed_plan(plan, [eng])
    ctx = _user_context()  # nothing extra in active_path_steps_rich

    result = await askesis.get_daily_work_plan(ctx)

    assert result.is_ok
    out = result.value
    assert len(out.engaged_ps_groups) == 1
    group = out.engaged_ps_groups[0]
    assert group.ps_uid == "ps:algebra"
    assert group.engagement is eng
    # Intersection only — task_orphan stays in flat list, not in group
    assert group.pending_task_uids == ("task_a",)
    assert group.pending_habit_uids == ("habit_a",)
    # Flat lists are preserved (bucketing is additive)
    assert out.tasks == ("task_a", "task_b", "task_orphan")
    # Nothing engaged → no available_to_start additions
    assert out.available_to_start == ()


@pytest.mark.asyncio
async def test_daily_plan_surfaces_available_to_start_when_no_engagements() -> None:
    """Touched PSes with no active engagement land in available_to_start."""
    plan = DailyWorkPlan(tasks=("task_x",))
    askesis = _askesis_with_stubbed_plan(plan, engagements=[])
    ctx = _user_context(ps_uids_in_active=("ps:touched_a", "ps:touched_b"))

    result = await askesis.get_daily_work_plan(ctx)

    assert result.is_ok
    out = result.value
    assert out.engaged_ps_groups == ()
    assert out.available_to_start == ("ps:touched_a", "ps:touched_b")


@pytest.mark.asyncio
async def test_daily_plan_excludes_abandoned_engagements() -> None:
    """list_engaged returns only state='engaged' edges; abandoned ones never reach the bucketer.

    This test pins the contract at the AskesisService boundary: even if a PS
    that was once engaged is now abandoned (and so absent from list_engaged's
    output), it must not show up as an engaged_ps_group, AND if the user has
    ``active_path_steps_rich`` membership for it, it correctly falls into
    ``available_to_start`` (touched, not currently engaged).
    """
    plan = DailyWorkPlan(tasks=("task_a",))
    # Only one ACTIVE engagement; the abandoned PS is omitted by the gateway.
    active_eng = _engagement("ps:current", spawned=("task_a",))
    askesis = _askesis_with_stubbed_plan(plan, [active_eng])
    # User's UserContext still lists the abandoned PS as touched.
    ctx = _user_context(ps_uids_in_active=("ps:current", "ps:abandoned"))

    result = await askesis.get_daily_work_plan(ctx)

    assert result.is_ok
    out = result.value
    engaged_uids = {g.ps_uid for g in out.engaged_ps_groups}
    assert engaged_uids == {"ps:current"}
    # Abandoned PS is touched-but-not-engaged → available_to_start.
    # Active engagement's PS is filtered out of available_to_start.
    assert out.available_to_start == ("ps:abandoned",)


@pytest.mark.asyncio
async def test_daily_plan_returns_unbucketed_plan_on_engagement_query_failure() -> None:
    """If list_engaged fails, the flat plan still returns — no engagement degrades the surface."""
    plan = DailyWorkPlan(tasks=("task_a",))
    askesis = _askesis_with_stubbed_plan(plan, engagements=None, list_engaged_ok=False)
    ctx = _user_context(ps_uids_in_active=("ps:touched",))

    result = await askesis.get_daily_work_plan(ctx)

    assert result.is_ok
    # Buckets are empty (post-processing skipped) but the underlying plan is intact.
    assert result.value.tasks == ("task_a",)
    assert result.value.engaged_ps_groups == ()
    assert result.value.available_to_start == ()
