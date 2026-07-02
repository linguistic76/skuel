"""Post-persist embedding step (ADR-074) — publish contract for both ingest doors.

Ingestion never embeds inline: after persistence, ``UnifiedIngestionService.
_publish_embedding_requests`` publishes one ``*EmbeddingRequested`` event per
persisted embeddable entity through the shared chokepoint
(``core.events.embedding_publisher``). These tests pin:

- event selection + text recipe for embeddable EntityTypes
- the CORE-tier gate (``event_bus is None`` → silent no-op, no warnings)
- non-embeddable / NonKuDomain types never publish
- the batch engine invokes ``post_persist_fn`` only after a successful upsert
  and strips the ``_file_path`` bookkeeping key before persistence
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from core.events.embedding_events import (
    KuEmbeddingRequested,
    TaskEmbeddingRequested,
)
from core.events.embedding_publisher import (
    EMBEDDING_EVENT_TYPES,
    publish_embedding_requested,
)
from core.models.enums.entity_enums import EntityType, NonKuDomain
from core.services.ingestion.config import ENTITY_CONFIGS
from core.services.ingestion.unified_ingestion_service import UnifiedIngestionService
from core.utils.logging import get_logger

logger = get_logger("test.post_persist_embedding")


class _CapturingBus:
    """Minimal EventBusOperations stand-in that records published events."""

    def __init__(self) -> None:
        self.published: list[Any] = []

    async def publish_async(self, event: Any) -> None:
        self.published.append(event)


def _service(event_bus: Any) -> UnifiedIngestionService:
    """Bare service exposing only what _publish_embedding_requests touches."""
    service = object.__new__(UnifiedIngestionService)
    service.event_bus = event_bus
    service.logger = logger
    return service


# ---------------------------------------------------------------------------
# publish_embedding_requested — the shared chokepoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_helper_publishes_typed_event_with_built_text():
    bus = _CapturingBus()
    published = await publish_embedding_requested(
        bus,
        EntityType.TASK,
        {"uid": "task.t1", "title": "Fix bug", "description": "Login broken"},
        logger,
    )

    assert published is True
    assert len(bus.published) == 1
    event = bus.published[0]
    assert isinstance(event, TaskEmbeddingRequested)
    assert event.entity_uid == "task.t1"
    assert event.entity_type == "task"
    assert event.embedding_text == "Fix bug\nLogin broken"


@pytest.mark.asyncio
async def test_helper_no_text_no_event():
    bus = _CapturingBus()
    published = await publish_embedding_requested(bus, EntityType.TASK, {"uid": "task.t2"}, logger)
    assert published is False
    assert bus.published == []


@pytest.mark.asyncio
async def test_helper_unmapped_type_no_event():
    bus = _CapturingBus()
    published = await publish_embedding_requested(
        bus, EntityType.USER_ENTRY, {"uid": "ue_1", "title": "Journal"}, logger
    )
    assert published is False
    assert bus.published == []


@pytest.mark.asyncio
async def test_helper_changed_fields_gate_skips_irrelevant_updates():
    """A status/progress-only update must not enqueue a redundant re-embed."""
    bus = _CapturingBus()
    published = await publish_embedding_requested(
        bus,
        EntityType.GOAL,
        {"uid": "goal.g1", "title": "Run a marathon", "description": "26.2"},
        logger,
        changed_fields=["status", "progress"],
    )
    assert published is False
    assert bus.published == []


@pytest.mark.asyncio
async def test_helper_changed_fields_gate_publishes_on_text_change():
    bus = _CapturingBus()
    published = await publish_embedding_requested(
        bus,
        EntityType.GOAL,
        {"uid": "goal.g1", "title": "Run an ultramarathon", "description": "50k"},
        logger,
        changed_fields=["title", "status"],
    )
    assert published is True
    assert len(bus.published) == 1


def test_event_map_mirrors_worker_subscriptions():
    """EMBEDDING_EVENT_TYPES must cover exactly the 12 worker-subscribed types."""
    assert set(EMBEDDING_EVENT_TYPES) == {
        EntityType.TASK,
        EntityType.GOAL,
        EntityType.HABIT,
        EntityType.EVENT,
        EntityType.CHOICE,
        EntityType.PRINCIPLE,
        EntityType.KU,
        EntityType.RESOURCE,
        EntityType.EXERCISE,
        EntityType.PATH_STEP,
        EntityType.LEARNING_PATH,
        EntityType.REVISED_EXERCISE,
    }


def test_every_ingestible_embeddable_type_has_an_event_class():
    """ENTITY_CONFIGS.embeddable gates the ingestion step — each gated type must map."""
    for entity_type, config in ENTITY_CONFIGS.items():
        if config.embeddable:
            assert isinstance(entity_type, EntityType)
            assert entity_type in EMBEDDING_EVENT_TYPES, (
                f"{entity_type} is embeddable in ENTITY_CONFIGS but has no event class"
            )


# ---------------------------------------------------------------------------
# UnifiedIngestionService._publish_embedding_requests — the ingestion step
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingestion_step_publishes_per_entity():
    bus = _CapturingBus()
    service = _service(bus)

    await service._publish_embedding_requests(
        EntityType.KU,
        [
            {"uid": "ku.alpha", "title": "Alpha"},
            {"uid": "ku.beta", "title": "Beta"},
        ],
    )

    assert [type(e) for e in bus.published] == [KuEmbeddingRequested, KuEmbeddingRequested]
    assert [e.entity_uid for e in bus.published] == ["ku.alpha", "ku.beta"]


@pytest.mark.asyncio
async def test_ingestion_step_core_tier_is_silent_noop():
    """event_bus=None (CORE tier) must not publish and must not warn-per-entity."""
    service = _service(None)
    # Must simply return — no AttributeError, no publish_event warning path.
    await service._publish_embedding_requests(EntityType.KU, [{"uid": "ku.x", "title": "X"}])


@pytest.mark.asyncio
async def test_ingestion_step_skips_non_embeddable_and_non_entity_types():
    bus = _CapturingBus()
    service = _service(bus)

    # USER_ENTRY is ingestible but not embeddable-gated
    await service._publish_embedding_requests(
        EntityType.USER_ENTRY, [{"uid": "ue_1", "title": "Entry"}]
    )
    # NonKuDomain never publishes
    await service._publish_embedding_requests(
        NonKuDomain.GROUP, [{"uid": "group.g1", "name": "Group"}]
    )

    assert bus.published == []


# ---------------------------------------------------------------------------
# batch engine — post_persist_fn invocation + _file_path strip
# ---------------------------------------------------------------------------


class _FakeBulkBackend:
    """Records what reaches the bulk upsert (per-type), succeeding always."""

    def __init__(self) -> None:
        self.upserted: dict[str, list[dict[str, Any]]] = {}

    async def ensure_constraints(self, entity_label: str) -> None:
        return None

    async def upsert_with_relationships(
        self,
        entity_label: str,
        base_label: str | None,
        entities: list[dict[str, Any]],
        relationship_config: dict[str, Any],
        batch_size: int = 500,
    ) -> Any:
        from core.ingestion.ingestion_types import IngestionResult
        from core.utils.result_simplified import Result

        self.upserted[entity_label] = [dict(e) for e in entities]
        return Result.ok(
            IngestionResult(
                total_processed=len(entities),
                nodes_created=len(entities),
                nodes_updated=0,
                relationships_created=0,
                errors=[],
            )
        )


@pytest.mark.asyncio
async def test_batch_door_strips_file_path_and_calls_post_persist(tmp_path: Path):
    """The batch engine must never persist _file_path and must invoke the
    post-persist callback with the persisted entities after a successful upsert."""
    from core.services.ingestion.batch import ingest_directory

    ku_file = tmp_path / "batch-embed-test.md"
    ku_file.write_text(
        "---\ntype: ku\nuid: ku:batch-embed-test\ntitle: Batch Embed Test\n---\nBody.\n"
    )

    backend = _FakeBulkBackend()
    calls: list[tuple[Any, list[dict[str, Any]]]] = []

    async def post_persist(entity_type: Any, entities: list[dict[str, Any]]) -> None:
        calls.append((entity_type, entities))

    result = await ingest_directory(
        directory=tmp_path,
        bulk_backend=backend,
        post_persist_fn=post_persist,
    )

    assert result.is_ok, f"batch ingest failed: {result}"

    # _file_path never reaches the bulk backend (node-property leak guard)
    assert "Ku" in backend.upserted
    for entity in backend.upserted["Ku"]:
        assert "_file_path" not in entity

    # post-persist callback ran once for the Ku group with the persisted entities
    assert len(calls) == 1
    entity_type, entities = calls[0]
    assert entity_type == EntityType.KU
    assert [e["uid"] for e in entities] == ["ku.batch-embed-test"]
