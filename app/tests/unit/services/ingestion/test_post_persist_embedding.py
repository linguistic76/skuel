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
  (``_chunk_entity_content``) which persists :Content/:ContentChunk and
  publishes ``ChunkEmbeddingRequested`` — chunks persist in CORE too, only
  the publish is tier-gated
- the empty-body clear path (ADR-074): an emptied body reaches the shared
  step in both doors, deletes the stale :Content subtree, and writes
  word_count=0 through the upsert
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
    EMBEDDING_NODE_LABELS,
    publish_embedding_requested,
)
from core.models.enums.entity_enums import EntityType, NonKuDomain
from core.models.ps_content.content_chunks import DEFAULT_CHUNKING_PARAMS
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
    """A type with a field map but no event class (ENTRY_REPORT) never publishes."""
    bus = _CapturingBus()
    published = await publish_embedding_requested(
        bus, EntityType.ENTRY_REPORT, {"uid": "er_1", "title": "Report"}, logger
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
    """EMBEDDING_EVENT_TYPES must cover exactly the 13 worker-subscribed types."""
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
        EntityType.USER_ENTRY,
    }


def test_node_label_map_mirrors_event_map():
    """EMBEDDING_NODE_LABELS (worker storage + backfill queries) must cover
    exactly the EMBEDDING_EVENT_TYPES types — the two maps extend together."""
    assert set(EMBEDDING_NODE_LABELS) == set(EMBEDDING_EVENT_TYPES)
    # Labels are the Neo4j node labels — non-empty, unique, PascalCase-shaped.
    labels = list(EMBEDDING_NODE_LABELS.values())
    assert len(set(labels)) == len(labels)
    assert all(label and label[0].isupper() for label in labels)


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

    # USER_ENTRY has an event class but is deliberately NOT embeddable-gated
    # in ENTITY_CONFIGS: its ONE publisher is UserEntryService (pipeline-scoped
    # to knowledge entries) — the ingestion step must never double-publish.
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

    async def upsert_nodes(
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

    async def create_relationships(
        self,
        entity_label: str,
        base_label: str | None,
        entities: list[dict[str, Any]],
        relationship_config: dict[str, Any],
        batch_size: int = 500,
    ) -> Any:
        from core.ingestion.ingestion_types import IngestionResult
        from core.utils.result_simplified import Result

        return Result.ok(
            IngestionResult(
                total_processed=len(entities),
                nodes_created=0,
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
    # Ku is a chunks_body_content type (stubs → lessons): body popped
    # pre-upsert and threaded to the chunk step, word_count in its place —
    # same recipe as PathStep.
    (persisted,) = backend.upserted["Ku"]
    assert "content" not in persisted
    assert persisted["word_count"] == 1
    assert set(chunk_sources) == {"ku.batch-embed-test"}
    assert chunk_sources["ku.batch-embed-test"].content.strip() == "Body."


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
# _ingest_post_persist / _chunk_entity_content — the shared chunk step
# ---------------------------------------------------------------------------


class _FakeContentAdapter:
    """Records store and clear calls, succeeding always."""

    def __init__(self) -> None:
        self.stored: list[tuple[str, Any]] = []
        self.cleared: list[str] = []
        self.clear_inline_flags: list[bool] = []

    async def store_content_with_chunks(
        self, uid: str, content: Any, *, clear_inline_body: bool = True
    ) -> bool:
        self.stored.append((uid, content))
        self.clear_inline_flags.append(clear_inline_body)
        return True

    async def delete_content_subtree(self, uid: str) -> bool:
        self.cleared.append(uid)
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
    from core.services.ingestion.types import ChunkSource

    bus = _CapturingBus()
    adapter = _FakeContentAdapter()
    service = _chunking_service(bus, adapter)

    uid = "ps.test.batch-chunks"
    await service._ingest_post_persist(
        EntityType.PATH_STEP,
        [{"uid": uid, "title": "Batch Chunks", "word_count": len(_PS_BODY.split())}],
        {uid: ChunkSource(content=_PS_BODY, file_format="markdown", source_path="x.md")},
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
    from core.services.ingestion.types import ChunkSource

    adapter = _FakeContentAdapter()
    service = _chunking_service(None, adapter)

    uid = "ps.test.core-chunks"
    await service._ingest_post_persist(
        EntityType.PATH_STEP,
        [{"uid": uid, "title": "Core Chunks"}],
        {uid: ChunkSource(content=_PS_BODY, file_format="markdown", source_path="x.md")},
    )

    assert [u for u, _ in adapter.stored] == [uid]


@pytest.mark.asyncio
async def test_chunk_step_default_clears_inline_body():
    """Popped-body domains (Ku/PS): the store carries clear_inline_body=True —
    the :Content subtree is the body source of truth."""
    adapter = _FakeContentAdapter()
    service = _chunking_service(None, adapter)

    generated = await service._chunk_entity_content(
        "ps.x", _PS_BODY, "markdown", "x.md", DEFAULT_CHUNKING_PARAMS
    )
    assert generated is True
    assert adapter.clear_inline_flags == [True]


@pytest.mark.asyncio
async def test_chunk_step_preserve_entity_body_keeps_inline_content():
    """UserEntry (canon P3): preserve_entity_body=True must reach the adapter
    as clear_inline_body=False — the inline body stays load-bearing for
    /gradebook and the journal digest (Codex P1 #615)."""
    adapter = _FakeContentAdapter()
    service = _chunking_service(None, adapter)

    generated = await service._chunk_entity_content(
        "ue_note",
        _PS_BODY,
        "markdown",
        "x.md",
        DEFAULT_CHUNKING_PARAMS,
        preserve_entity_body=True,
    )
    assert generated is True
    assert adapter.clear_inline_flags == [False]


@pytest.mark.asyncio
async def test_chunk_step_no_chunking_service_is_noop():
    """Graceful degradation: without a chunking service the shared step does
    nothing and reports no chunks."""
    bus = _CapturingBus()
    service = _service(bus)
    service.chunking = None
    service.content_adapter = None

    generated = await service._chunk_entity_content(
        "ps.x", _PS_BODY, "markdown", "x.md", DEFAULT_CHUNKING_PARAMS
    )
    assert generated is False
    assert bus.published == []


# ---------------------------------------------------------------------------
# empty-body clear path (ADR-074) — both doors route through the shared step
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chunk_step_empty_body_clears_content_subtree():
    """An emptied body must delete the previous body's :Content subtree —
    stale chunk vectors must not survive the re-ingest — and publish nothing."""
    bus = _CapturingBus()
    adapter = _FakeContentAdapter()
    service = _chunking_service(bus, adapter)

    generated = await service._chunk_entity_content(
        "ps.cleared", "", "markdown", "x.md", DEFAULT_CHUNKING_PARAMS
    )

    assert generated is False
    assert adapter.cleared == ["ps.cleared"]
    assert adapter.stored == []
    assert bus.published == []


@pytest.mark.asyncio
async def test_chunk_step_empty_body_clears_even_without_chunker():
    """The clear needs only the content adapter — a missing chunking service
    must not leave the stale subtree behind."""
    adapter = _FakeContentAdapter()
    service = _chunking_service(None, adapter)
    service.chunking = None

    generated = await service._chunk_entity_content(
        "ps.cleared2", "", "markdown", "x.md", DEFAULT_CHUNKING_PARAMS
    )

    assert generated is False
    assert adapter.cleared == ["ps.cleared2"]


@pytest.mark.asyncio
async def test_chunk_step_empty_body_without_adapter_is_noop():
    service = _chunking_service(None, None)

    generated = await service._chunk_entity_content(
        "ps.x", "", "markdown", "x.md", DEFAULT_CHUNKING_PARAMS
    )
    assert generated is False


@pytest.mark.asyncio
async def test_batch_door_empty_body_writes_zero_word_count_and_threads_clear(tmp_path: Path):
    """Batch door, emptied body: word_count=0 must reach the upsert (`n +=
    props` never removes omitted keys — a skipped write keeps the stale count)
    and the empty source must still thread through so the shared step clears."""
    from core.services.ingestion.batch import ingest_directory

    ps_file = tmp_path / "ps-emptied.md"
    ps_file.write_text("---\ntype: path_step\nuid: ps:test:emptied\ntitle: Emptied\n---\n")

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

    (persisted,) = backend.upserted["PathStep"]
    assert "content" not in persisted
    assert persisted["word_count"] == 0

    assert len(calls) == 1
    _, _, chunk_sources = calls[0]
    assert set(chunk_sources) == {"ps.test.emptied"}
    assert chunk_sources["ps.test.emptied"].content == ""


@pytest.mark.asyncio
async def test_batch_door_null_content_frontmatter_is_treated_as_empty(tmp_path: Path):
    """YAML `content:` with no value parses to None — must normalize to the
    empty-body clear path, not crash on None.split() (Kody #489 finding)."""
    from core.services.ingestion.batch import ingest_directory

    ps_file = tmp_path / "ps-null-content.yaml"
    ps_file.write_text(
        "type: path_step\nuid: ps:test:null-content\ntitle: Null Content\ncontent:\n"
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
    (persisted,) = backend.upserted["PathStep"]
    assert persisted["word_count"] == 0
    assert calls[0][2]["ps.test.null-content"].content == ""


@pytest.mark.asyncio
async def test_ingest_post_persist_empty_source_clears_without_chunk_events():
    """The batch callback with an empty-body source: entity event still
    publishes (frontmatter vector), subtree cleared, no chunk events."""
    from core.services.ingestion.types import ChunkSource

    bus = _CapturingBus()
    adapter = _FakeContentAdapter()
    service = _chunking_service(bus, adapter)

    uid = "ps.test.emptied-callback"
    await service._ingest_post_persist(
        EntityType.PATH_STEP,
        [{"uid": uid, "title": "Emptied", "word_count": 0}],
        {uid: ChunkSource(content="", file_format="markdown", source_path="x.md")},
    )

    assert adapter.cleared == [uid]
    assert adapter.stored == []
    assert [type(e) for e in bus.published] == [PathStepEmbeddingRequested]
