"""Execution test for compose_services() — the composition root actually runs.

Testing-gap roadmap item 3: compose.py (~2k lines) wires the whole app,
including _event_wiring.py's 45+ event subscriptions, but until this test it
was only ever *read as text* by a test (test_user_context_builder_wiring.py),
and the integration conftest builds services manually from adapters —
bypassing compose entirely. A compose-time TypeError (constructor signature
drift) or a dropped event subscription shipped green and only failed at
server boot.

This test CALLS compose_services() for real, in both intelligence tiers.
Every service constructor, every post-construction wire, and the full
_wire_event_subscribers() pass run against a real InMemoryEventBus. Only the
startup tasks that genuinely talk to Neo4j are patched (see
_patch_db_startup_seams) — the driver double raises on any other query
attempt, so new hidden I/O in the composition path fails loudly here.

compose_services re-raises TypeError/AttributeError/ImportError/NameError by
design ("programming errors must propagate"), so a wiring bug surfaces as the
original traceback, not a Result failure.
"""

import dataclasses
from typing import Any

import pytest

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.neo4j_schema_manager import Neo4jSchemaManager
from adapters.persistence.neo4j.session_backend import SessionBackend
from core.config.unified_config import UnifiedConfig
from core.services.performance_optimization_service import PerformanceOptimizationService
from core.services.user_service import UserService
from core.utils.result_simplified import Result
from services_bootstrap._container import Services
from services_bootstrap.compose import compose_services

# ---------------------------------------------------------------------------
# Golden subscription contract
# ---------------------------------------------------------------------------
# Every event type _wire_event_subscribers() must subscribe at least one
# handler to, in BOTH tiers. This list is the contract: removing a
# subscription from _event_wiring.py without updating it fails the test.
# (FULL tier additionally re-subscribes 5 of these for ZPD snapshots —
# already covered because they appear below.)


def _expected_event_subscriptions() -> tuple[type, ...]:
    """Import-fresh golden set (function keeps import errors inside the test run)."""
    from core.events import (
        CalendarEventCompleted,
        CalendarEventCreated,
        CalendarEventDeleted,
        CalendarEventRescheduled,
        CalendarEventUpdated,
        ChoiceCreated,
        ChoiceDeleted,
        ChoiceMade,
        ChoiceOutcomeRecorded,
        ChoiceUpdated,
        GoalAbandoned,
        GoalAchieved,
        GoalCreated,
        GoalMilestoneReached,
        GoalProgressUpdated,
        GoalUpdated,
        HabitCompleted,
        HabitCompletionBulk,
        HabitCreated,
        HabitMissed,
        HabitStreakBroken,
        HabitStreakMilestone,
        HabitUpdated,
        KnowledgeCreated,
        KnowledgeMastered,
        LearningPathCompleted,
        LearningPathProgressUpdated,
        LearningPathStarted,
        PathStepCompleted,
        PathStepCreated,
        PathStepDeleted,
        PathStepUpdated,
        PrincipleAlignmentAssessed,
        PrincipleCreated,
        PrincipleDeleted,
        PrincipleStrengthChanged,
        PrincipleUpdated,
        TaskCompleted,
        TaskCreated,
        TaskDeleted,
        TaskPriorityChanged,
        TasksBulkCompleted,
        TaskUpdated,
    )
    from core.events.curriculum_events import PathStepEnrolled
    from core.events.knowledge_substance_events import (
        KnowledgeAppliedInTask,
        KnowledgeBuiltIntoHabit,
        KnowledgeBulkAppliedInTask,
        KnowledgeBulkBuiltIntoHabit,
        KnowledgeBulkInformedChoice,
        KnowledgeInformedChoice,
        KnowledgePracticedInEvent,
        KnowledgeReflectedInEntry,
    )
    from core.events.learning_loop_events import (
        ReportSubmitted,
        RevisedExerciseCreated,
        UserEntryApproved,
        UserEntryRevisionRequested,
    )
    from core.events.principle_events import (
        PrincipleConflictRevealed,
        PrincipleReflectionRecorded,
    )
    from core.events.search_events import SearchExecuted
    from core.events.user_entry_events import (
        UserEntryCreated,
        UserEntryProcessingCompleted,
        UserEntryProcessingFailed,
        UserEntryProcessingStarted,
    )

    return (
        # Tasks
        TaskCreated,
        TaskCompleted,
        TaskUpdated,
        TaskDeleted,
        TaskPriorityChanged,
        TasksBulkCompleted,
        # Goals
        GoalCreated,
        GoalUpdated,
        GoalAchieved,
        GoalAbandoned,
        GoalMilestoneReached,
        GoalProgressUpdated,
        # Habits
        HabitCreated,
        HabitUpdated,
        HabitCompleted,
        HabitCompletionBulk,
        HabitMissed,
        HabitStreakBroken,
        HabitStreakMilestone,
        # Principles
        PrincipleCreated,
        PrincipleUpdated,
        PrincipleDeleted,
        PrincipleStrengthChanged,
        PrincipleAlignmentAssessed,
        PrincipleReflectionRecorded,
        PrincipleConflictRevealed,
        # Choices
        ChoiceCreated,
        ChoiceUpdated,
        ChoiceDeleted,
        ChoiceMade,
        ChoiceOutcomeRecorded,
        # Calendar events
        CalendarEventCreated,
        CalendarEventUpdated,
        CalendarEventCompleted,
        CalendarEventDeleted,
        CalendarEventRescheduled,
        # UserEntry lifecycle + learning loop
        UserEntryCreated,
        UserEntryProcessingStarted,
        UserEntryProcessingCompleted,
        UserEntryProcessingFailed,
        UserEntryApproved,
        UserEntryRevisionRequested,
        ReportSubmitted,
        RevisedExerciseCreated,
        # Curriculum / learning
        KnowledgeCreated,
        KnowledgeMastered,
        LearningPathStarted,
        LearningPathCompleted,
        LearningPathProgressUpdated,
        PathStepCreated,
        PathStepUpdated,
        PathStepDeleted,
        PathStepCompleted,
        PathStepEnrolled,
        # Knowledge substance tracking
        KnowledgeAppliedInTask,
        KnowledgePracticedInEvent,
        KnowledgeBuiltIntoHabit,
        KnowledgeInformedChoice,
        KnowledgeReflectedInEntry,
        KnowledgeBulkAppliedInTask,
        KnowledgeBulkBuiltIntoHabit,
        KnowledgeBulkInformedChoice,
        # Discovery analytics
        SearchExecuted,
    )


# ---------------------------------------------------------------------------
# Container completeness contract
# ---------------------------------------------------------------------------
# Services fields that legitimately compose to None. Everything else must be
# non-None after compose_services() — a field that silently composes to None
# is exactly the "ships green, 500s at runtime" gap this test closes.

NONE_OK_BOTH_TIERS = frozenset(
    {
        # This test passes prometheus_metrics=None (optional instrumentation).
        "prometheus_metrics",
    }
)

NONE_OK_CORE_TIER = NONE_OK_BOTH_TIERS | frozenset(
    {
        # Digital-layer services — legitimately absent at INTELLIGENCE_TIER=core
        # (ADR-043 graceful degradation).
        "embeddings_service",
        "vector_search_service",
        "embedding_worker",
        "askesis",
        "askesis_ai",
        "context_aware_ai",
        "journal",
        "transcription",
        "batch_transcription",
        "zpd_service",
    }
)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _NoDatabaseDriver:
    """Stands in for neo4j.AsyncDriver during composition.

    Composition must only *construct* services (constructors store the driver;
    they never query). Any real query attempt during compose is a bug — this
    double turns it into an immediate, attributable failure instead of a hang
    against a nonexistent database.
    """

    def session(self, **_session_config: Any) -> Any:
        raise AssertionError(
            "compose_services opened a Neo4j session during composition — "
            "startup DB work must go through a seam patched in "
            "_patch_db_startup_seams (see this test module)."
        )

    async def execute_query(self, *_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError(
            "compose_services executed a Neo4j query during composition — "
            "startup DB work must go through a seam patched in "
            "_patch_db_startup_seams (see this test module)."
        )

    async def close(self) -> None:
        return None


class _FakeNeo4jAdapter:
    """Minimal GraphPort-shaped adapter: compose only calls get_driver() on it."""

    def __init__(self, driver: _NoDatabaseDriver) -> None:
        self._driver = driver

    def get_driver(self) -> _NoDatabaseDriver:
        return self._driver


class _FakeConnection:
    """Stands in for the get_connection() singleton (content/chunk adapters store it)."""

    def __init__(self, driver: _NoDatabaseDriver) -> None:
        self.driver = driver


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def compose_config(tmp_path) -> UnifiedConfig:
    """Real UnifiedConfig with vault roots redirected into tmp_path.

    VaultConfig defaults are captured from the environment at import time, so
    the instance attributes are overridden directly — the test must never read
    or scan the developer's real vaults.
    """
    config = UnifiedConfig()

    personal = tmp_path / "personal_vault"
    content = tmp_path / "content_vault"
    user_vaults = tmp_path / "user_vaults"
    for root in (personal, content, user_vaults):
        root.mkdir()

    config.vault.vault_root = str(personal)
    config.vault.ingestion_root = str(content)
    config.vault.user_vaults_root = str(user_vaults)
    config.vault.vault_transport = "filesystem"

    # No background schema poll in a unit test.
    config.database.schema_monitoring_enabled = False

    return config


@pytest.fixture
def startup_calls(monkeypatch, tmp_path) -> dict[str, int]:
    """Patch the ONLY compose-time awaits that touch Neo4j; record each call.

    These are startup *tasks* (index DDL, cleanup sweeps, system-user upsert),
    not wiring — the wiring itself runs unpatched. The returned dict lets
    tests assert the tasks were actually invoked, so compose can't silently
    drop one either.
    """
    calls: dict[str, int] = {}

    def _record(name: str) -> None:
        calls[name] = calls.get(name, 0) + 1

    def _make_sync_stub(name: str):
        async def _fake_sync(self: Any, *args: Any, **kwargs: Any) -> Result[dict[str, Any]]:
            _record(name)
            return Result.ok({"created": [], "failed": []})

        return _fake_sync

    for sync_method in (
        "sync_auth_indexes",
        "sync_vector_indexes",
        "sync_domain_indexes",
        "sync_fulltext_indexes",
        "sync_conversation_indexes",
    ):
        monkeypatch.setattr(Neo4jSchemaManager, sync_method, _make_sync_stub(sync_method))

    async def _fake_drop_stale(self: Any) -> Result[dict[str, Any]]:
        _record("drop_stale_indexes")
        return Result.ok({"dropped": [], "failed": []})

    monkeypatch.setattr(Neo4jSchemaManager, "drop_stale_indexes", _fake_drop_stale)

    def _make_cleanup_stub(name: str):
        async def _fake_cleanup(self: Any) -> Result[int]:
            _record(name)
            return Result.ok(0)

        return _fake_cleanup

    monkeypatch.setattr(
        SessionBackend, "cleanup_expired_sessions", _make_cleanup_stub("cleanup_expired_sessions")
    )
    monkeypatch.setattr(
        SessionBackend, "cleanup_expired_tokens", _make_cleanup_stub("cleanup_expired_tokens")
    )

    async def _fake_ensure_system_user(self: Any) -> Result[Any]:
        _record("ensure_system_user")
        # compose only checks is_error; the User payload is never read there.
        return Result.ok(None)

    monkeypatch.setattr(UserService, "ensure_system_user", _fake_ensure_system_user)

    # initialize() starts background asyncio tasks — construction is what's
    # under test, so keep the loop clean.
    async def _fake_perf_initialize(self: Any) -> None:
        _record("performance_optimization.initialize")

    monkeypatch.setattr(PerformanceOptimizationService, "initialize", _fake_perf_initialize)

    # get_connection() lazily creates a REAL env-configured driver singleton;
    # keep the unit test hermetic (content/reference-chunk adapters only store it).
    fake_connection = _FakeConnection(_NoDatabaseDriver())

    def _fake_get_connection() -> _FakeConnection:
        return fake_connection

    monkeypatch.setattr(
        "adapters.persistence.neo4j.neo4j_connection.get_connection", _fake_get_connection
    )

    return calls


@pytest.fixture
def hermetic_credentials(monkeypatch) -> None:
    """Force get_credential() onto the pure env-fallback path.

    Without a master key the Fernet backend raises and get_credential falls
    straight to os.getenv — critically, WITHOUT the env→backend auto-migration
    that would otherwise write this test's fake API keys into the developer's
    real credential store.
    """
    monkeypatch.delenv("SKUEL_MASTER_KEY", raising=False)
    monkeypatch.setenv("SKUEL_CREDENTIAL_BACKEND", "fernet")
    monkeypatch.delenv("EMAIL_ENABLED", raising=False)


EXPECTED_STARTUP_CALLS_CORE = {
    "sync_auth_indexes",
    # sync_vector_indexes is FULL-tier only (no embeddings in CORE — ADR-043)
    "sync_domain_indexes",
    "sync_fulltext_indexes",
    "sync_conversation_indexes",
    "drop_stale_indexes",
    "cleanup_expired_sessions",
    "cleanup_expired_tokens",
    "ensure_system_user",
    "performance_optimization.initialize",
}
EXPECTED_STARTUP_CALLS_FULL = EXPECTED_STARTUP_CALLS_CORE | {"sync_vector_indexes"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def _compose(config: UnifiedConfig) -> tuple[Services, InMemoryEventBus]:
    event_bus = InMemoryEventBus()
    adapter = _FakeNeo4jAdapter(_NoDatabaseDriver())

    result = await compose_services(
        neo4j_adapter=adapter,
        event_bus=event_bus,
        config=config,
        prometheus_metrics=None,
        metrics_cache=None,
    )

    assert result.is_ok, f"compose_services failed: {result.error}"
    return result.value, event_bus


def _assert_container_complete(services: Services, none_ok: frozenset[str]) -> None:
    composed_none = [
        f.name
        for f in dataclasses.fields(Services)
        if f.name not in none_ok and getattr(services, f.name) is None
    ]
    assert not composed_none, (
        f"Services fields composed to None: {composed_none}. Either compose.py "
        f"stopped wiring them or they are newly tier-gated — if the latter, add "
        f"them to the NONE_OK sets in this test with the gating rationale."
    )


def _assert_subscriptions_wired(event_bus: InMemoryEventBus) -> None:
    unsubscribed = [
        event_type.__name__
        for event_type in _expected_event_subscriptions()
        if event_bus.get_handler_count(event_type) == 0
    ]
    assert not unsubscribed, (
        f"Event types with NO subscriber after compose_services: {unsubscribed}. "
        f"A handler subscription was dropped from services_bootstrap/_event_wiring.py "
        f"(or the intelligence hub) — that domain's event-driven behavior is dead."
    )


class TestComposeServicesExecution:
    """compose_services() must wire the full container in both tiers."""

    async def test_core_tier_composes_and_wires_events(
        self, monkeypatch, compose_config, startup_calls, hermetic_credentials
    ) -> None:
        monkeypatch.setenv("INTELLIGENCE_TIER", "core")
        # CORE must not require any AI credential — prove it by removing them.
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)

        services, event_bus = await _compose(compose_config)

        assert services.intelligence_tier is not None
        assert not services.intelligence_tier.ai_enabled
        _assert_container_complete(services, NONE_OK_CORE_TIER)
        _assert_subscriptions_wired(event_bus)
        assert set(startup_calls) == EXPECTED_STARTUP_CALLS_CORE

    async def test_full_tier_composes_and_wires_events(
        self, monkeypatch, compose_config, startup_calls, hermetic_credentials
    ) -> None:
        monkeypatch.setenv("INTELLIGENCE_TIER", "full")
        # Fake keys: FULL-tier compose constructs SDK clients but never calls
        # the vendor APIs (hermetic_credentials guarantees these fake values
        # cannot leak into a real credential store).
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-compose-execution-not-a-real-key")
        monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-test-compose-execution-not-a-real-key")
        # Anthropic is optional even in FULL — exercise the skip branch.
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        services, event_bus = await _compose(compose_config)

        assert services.intelligence_tier is not None
        assert services.intelligence_tier.ai_enabled
        _assert_container_complete(services, NONE_OK_BOTH_TIERS)
        _assert_subscriptions_wired(event_bus)
        assert set(startup_calls) == EXPECTED_STARTUP_CALLS_FULL
