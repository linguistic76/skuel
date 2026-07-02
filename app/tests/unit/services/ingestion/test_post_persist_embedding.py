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
- the batch door's PathStep chunk unification: ``content`` popped pre-upsert
  (never a node property), threaded to the shared chunk step
  (``_chunk_path_step_content``) which persists :Content/:ContentChunk and
  publishes ``ChunkEmbeddingRequested`` — chunks persist in CORE too, only
  the publish is tier-gated
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from core.events.chunk_events import ChunkEmbeddingRequested
from core.events.embedding_events import (
    KuEmbeddingRequested,
    PathStepEmbeddingRequested,
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
    calls: list[tuple[Any, list[dict[str, Any]], dict[str, Any]]] = []

    async def post_persist(
        entity_type: Any, entities: list[dict[str, Any]], chunk_sources: dict[str, Any]
    ) -> None:
        calls.append((entity_type, entities, chunk_sources))

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
    entity_type, entities, chunk_sources = calls[0]
    assert entity_type == EntityType.KU
    assert [e["uid"] for e in entities] == ["ku.batch-embed-test"]
    # Ku is not a chunked type — no chunk sources threaded
    assert chunk_sources == {}


@pytest.mark.asyncio
async def test_batch_door_pops_path_step_content_and_threads_chunk_source(tmp_path: Path):
    """PATH_STEP content must be popped pre-upsert (content lives on :Content,
    never the :Entity node — same shape as the single-file door), word_count
    set, and the popped body threaded to post_persist_fn keyed by uid."""
    from core.services.ingestion.batch import ingest_directory

    ps_file = tmp_path / "ps-chunk-test.md"
    body = "# Intro\n\nSome PathStep body content worth chunking.\n"
    ps_file.write_text(
        f"---\ntype: path_step\nuid: ps:test:chunk-unification\ntitle: Chunk Test\n---\n{body}"
    )

    backend = _FakeBulkBackend()
    calls: list[tuple[Any, list[dict[str, Any]], dict[str, Any]]] = []

    async def post_persist(
        entity_type: Any, entities: list[dict[str, Any]], chunk_sources: dict[str, Any]
    ) -> None:
        calls.append((entity_type, entities, chunk_sources))

    result = await ingest_directory(
        directory=tmp_path,
        bulk_backend=backend,
        post_persist_fn=post_persist,
    )

    assert result.is_ok, f"batch ingest failed: {result}"

    # content never reaches the bulk backend; word_count is set in its place
    assert "PathStep" in backend.upserted
    (persisted,) = backend.upserted["PathStep"]
    assert "content" not in persisted
    assert persisted["word_count"] == len(body.split())

    # the popped body is threaded to the callback keyed by uid
    assert len(calls) == 1
    _, _, chunk_sources = calls[0]
    assert set(chunk_sources) == {"ps.test.chunk-unification"}
    source = chunk_sources["ps.test.chunk-unification"]
    assert source.content.strip() == body.strip()
    assert source.file_format == "markdown"
    assert source.source_path == str(ps_file)


# ---------------------------------------------------------------------------
# _ingest_post_persist / _chunk_path_step_content — the shared chunk step
# ---------------------------------------------------------------------------


class _FakeContentAdapter:
    """Records store_content_with_chunks calls, succeeding always."""

    def __init__(self) -> None:
        self.stored: list[tuple[str, Any]] = []

    async def store_content_with_chunks(self, uid: str, content: Any) -> bool:
        self.stored.append((uid, content))
        return True


def _chunking_service(event_bus: Any, content_adapter: Any) -> UnifiedIngestionService:
    """Bare service exposing what the post-persist + chunk steps touch."""
    from core.services.entity_chunking_service import EntityChunkingService

    service = object.__new__(UnifiedIngestionService)
    service.event_bus = event_bus
    service.logger = logger
    service.chunking = EntityChunkingService()  # pure in-memory, real chunker
    service.content_adapter = content_adapter
    return service


_PS_BODY = (
    "# Introduction\n\nPathSteps compose Kus into learning content.\n\n"
    "## Detail\n\nChunk embeddings carry the body-content semantics.\n"
)


@pytest.mark.asyncio
async def test_ingest_post_persist_publishes_entity_event_and_chunk_event():
    """The batch callback must mirror ingest_file's post-persist sequence:
    entity *EmbeddingRequested first, then ChunkEmbeddingRequested carrying
    ALL persisted chunk ids."""
    from core.services.ingestion.types import PathStepChunkSource

    bus = _CapturingBus()
    adapter = _FakeContentAdapter()
    service = _chunking_service(bus, adapter)

    uid = "ps.test.batch-chunks"
    await service._ingest_post_persist(
        EntityType.PATH_STEP,
        [{"uid": uid, "title": "Batch Chunks", "word_count": len(_PS_BODY.split())}],
        {uid: PathStepChunkSource(content=_PS_BODY, file_format="markdown", source_path="x.md")},
    )

    # :Content + :ContentChunk persisted through the adapter
    assert [u for u, _ in adapter.stored] == [uid]
    _, content = adapter.stored[0]
    assert content.chunk_count >= 1

    # entity event first, then one chunk event carrying every chunk id
    assert isinstance(bus.published[0], PathStepEmbeddingRequested)
    assert bus.published[0].entity_uid == uid
    chunk_events = [e for e in bus.published if isinstance(e, ChunkEmbeddingRequested)]
    assert len(chunk_events) == 1
    assert chunk_events[0].parent_uid == uid
    assert set(chunk_events[0].chunk_uids) == {c.chunk_id for c in content.chunks}
    assert len(chunk_events[0].chunk_texts) == len(chunk_events[0].chunk_uids)


@pytest.mark.asyncio
async def test_chunk_step_core_tier_persists_chunks_without_publishing():
    """CORE tier (event_bus=None): chunks still generate and persist — the
    Analog behavior — but no embedding events publish."""
    from core.services.ingestion.types import PathStepChunkSource

    adapter = _FakeContentAdapter()
    service = _chunking_service(None, adapter)

    uid = "ps.test.core-chunks"
    await service._ingest_post_persist(
        EntityType.PATH_STEP,
        [{"uid": uid, "title": "Core Chunks"}],
        {uid: PathStepChunkSource(content=_PS_BODY, file_format="markdown", source_path="x.md")},
    )

    assert [u for u, _ in adapter.stored] == [uid]


@pytest.mark.asyncio
async def test_chunk_step_no_chunking_service_is_noop():
    """Graceful degradation: without a chunking service the shared step does
    nothing and reports no chunks."""
    bus = _CapturingBus()
    service = _service(bus)
    service.chunking = None
    service.content_adapter = None

    generated = await service._chunk_path_step_content("ps.x", _PS_BODY, "markdown", "x.md")
    assert generated is False
    assert bus.published == []
