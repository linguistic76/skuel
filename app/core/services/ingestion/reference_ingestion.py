"""
Reference Ingestion Service
===========================

The reusable, domain-agnostic capability behind the canon reference-book
ingest door (Phase 2 of the canon journaling companion). Reads a walled
``0vault/Resources/*.md`` book, chunks it (prose-tuned), persists
:ReferenceChunk nodes under a pre-existing Resource, and (FULL tier) publishes
a ReferenceChunkEmbeddingRequested event so the shared background worker embeds
them onto their OWN vector index.

Deliberately NOT inside JournalService — this is a curriculum-agnostic ingest
capability, reused by an admin CLI today and any future caller. Returns
``Result[T]`` throughout and holds NO Cypher (SKUEL021): all persistence goes
through the injected Neo4jReferenceChunkAdapter.

Tier behaviour (ADR-043 / ADR-074):
- FULL: event_bus present → chunks persisted, embedding event published, worker
  drains and fills vectors.
- CORE: event_bus is None → chunks persisted (shelf membership holds),
  embedding publish is a no-op; vectors fill on a later FULL run (fail-soft).
"""

__version__ = "1.0"


from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.models.ps_content.content_chunks import (
    ChunkingParams,
    ContentChunk,
    ContentChunkingStrategy,
    chunk_version_tag,
)
from core.ports.infrastructure_protocols import EventBusOperations
from core.services.ingestion.config import REFERENCE_CHUNKING_PARAMS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.resource_service import ResourceService

logger = get_logger("skuel.services.ingestion.reference")

# Chunks per embedding event. The whole book in ONE event is all-or-nothing: a
# ~100k-word book's chunks can't embed inside a single drain pass (it times out
# and stores nothing). Slicing lets the shared worker store incrementally — one
# ReferenceChunkEmbeddingRequested per slice, each an independent unit of work.
REFERENCE_EMBED_BATCH = 100


@dataclass(frozen=True)
class ReferenceIngestReport:
    """Outcome of a single book ingest — printed by the CLI, asserted in tests."""

    resource_uid: str
    chunks_written: int
    embed_requested: bool


def _strip_frontmatter(markdown_text: str) -> str:
    """Drop a single leading YAML frontmatter block before chunking.

    The reference cleaner emits provenance frontmatter
    (``source_epub``/``generated_by``/``resource_uid``) that must never enter
    chunk text. Only a block starting on the very first line is stripped;
    ``---`` rules elsewhere in the body are left untouched.
    """
    if not markdown_text.startswith("---"):
        return markdown_text
    # Split off the opening fence, then the closing fence.
    parts = markdown_text.split("\n", 1)
    if len(parts) < 2:
        return markdown_text
    rest = parts[1]
    end = rest.find("\n---")
    if end == -1:
        return markdown_text
    after = rest[end + len("\n---") :]
    # Consume to end of the closing fence line.
    newline = after.find("\n")
    return after[newline + 1 :] if newline != -1 else ""


def _fragment_trail(chunk: ContentChunk) -> list[str]:
    """The chunk's full location path: ancestor breadcrumb + its own heading."""
    parts = chunk.section_path.split(" > ") if chunk.section_path else []
    if chunk.heading:
        parts = [*parts, chunk.heading]
    return parts


def _common_location(group: list[ContentChunk]) -> tuple[str | None, str | None]:
    """Deepest heading + ancestor path that contains EVERY fragment in the group.

    A consolidation group is packed by word count and may cross heading
    boundaries, so a single merged passage can span sibling sections. Citing the
    whole passage by any one fragment's location would mis-attribute a quote taken
    from another section inside it (Codex #572 P2). Instead the passage is cited by
    the **longest common ancestor** of its fragments — the deepest section that
    truly contains all of it, always correct for whatever the chunk spans. Returns
    ``(heading, section_path)`` where ``heading`` is the last common element and
    ``section_path`` its ancestors; both ``None`` when the group spans the whole book.
    """
    trails = [_fragment_trail(c) for c in group]
    common: list[str] = []
    for level in zip(*trails, strict=False):
        if len(set(level)) == 1:
            common.append(level[0])
        else:
            break
    if not common:
        return None, None
    heading = common[-1]
    section_path = " > ".join(common[:-1]) if len(common) > 1 else None
    return heading, section_path


def _consolidate_chunks(
    chunks: list[ContentChunk], resource_uid: str, params: ChunkingParams
) -> list[ContentChunk]:
    """Merge the chunker's fine structural splits into prose-grain passages.

    The shared ``ContentChunkingStrategy`` splits per structural unit (heading,
    paragraph, code fence) and never enforces ``min_chunk_size`` (an inert knob),
    so a long book shatters into thousands of ~30-word fragments — far too
    granular for canon voice-infusion and too many to embed in one pass. This
    packs consecutive fragments up to ``max_chunk_size`` words into coherent
    passages, re-sequencing ``chunk_index`` so every ``chunk_id`` stays unique,
    and drops blank/heading-only fragments. Reference-path only — curriculum
    chunking is untouched. Merged chunks carry ``chunk_version_tag(params)`` so
    their staleness is isolated from the ``v1`` curriculum corpus.
    """
    target = params.max_chunk_size
    version = chunk_version_tag(params)

    groups: list[list[ContentChunk]] = []
    current: list[ContentChunk] = []
    words = 0
    for c in chunks:
        if not c.text.strip():
            continue  # drop blank / heading-only fragments
        c_words = c.word_count or len(c.text.split())
        if current and words + c_words > target:
            groups.append(current)
            current, words = [], 0
        current.append(c)
        words += c_words
    if current:
        groups.append(current)

    merged: list[ContentChunk] = []
    index = 0
    for group in groups:
        text = "\n\n".join(c.text.strip() for c in group)
        if not text.strip():
            continue
        # Cite the merged passage by the deepest section that contains ALL of it
        # (longest common ancestor), so a quote from anywhere inside it is never
        # attributed to a sibling section it merely sits next to (Codex #572 P2).
        merged_heading, merged_section_path = _common_location(group)
        merged.append(
            ContentChunk(
                parent_uid=resource_uid,
                chunk_index=index,
                chunk_type=group[0].chunk_type,
                text=text,
                context_before=group[0].context_before,
                context_after=group[-1].context_after,
                heading=merged_heading,
                section_path=merged_section_path,
                chunking_version=version,
            )
        )
        index += 1
    return merged


class ReferenceIngestionService:
    """
    Ingest a canon reference book into :ReferenceChunk nodes.

    Backend: Neo4jReferenceChunkAdapter (all Cypher). Embeddings: published as a
    ReferenceChunkEmbeddingRequested event through the shared worker (never
    inline — ADR-074).
    """

    def __init__(
        self,
        reference_chunk_adapter: Any,  # boundary: Neo4jReferenceChunkAdapter (persistence)
        event_bus: EventBusOperations | None = None,
        resource_service: "ResourceService | None" = None,
        logger: Any = logger,
    ) -> None:
        """
        Args:
            reference_chunk_adapter: Persistence adapter for the Resource/
                ReferenceChunk subtree
            event_bus: Event bus for post-persist embedding requests; None in
                CORE tier (chunks-only, fail-soft)
            resource_service: Optional ResourceService for the pre-existence
                check; when omitted, the adapter's zero-created guard still
                catches a missing Resource
            logger: Logger (defaults to the module logger)
        """
        self.reference_chunk_adapter = reference_chunk_adapter
        self.event_bus = event_bus
        self.resource_service = resource_service
        self.logger = logger

    async def ingest_book(
        self,
        resource_uid: str,
        markdown_text: str,
        *,
        params: ChunkingParams = REFERENCE_CHUNKING_PARAMS,
    ) -> Result[ReferenceIngestReport]:
        """
        Chunk + persist a book, then request embeddings (FULL tier).

        The Resource must pre-exist — this door validates and fails if absent;
        it never creates Resources (a governed curriculum-ingestion concern).

        Args:
            resource_uid: The pre-existing Resource UID (explicit — never
                slug-matched from the filename)
            markdown_text: Full book markdown (leading frontmatter stripped)
            params: Chunking grain (defaults to REFERENCE_CHUNKING_PARAMS)

        Returns:
            Result[ReferenceIngestReport] — not_found if the Resource is
            absent, database error if the write fails, else the ingest report.
        """
        # 1. Resource pre-existence check (when a service is wired).
        if self.resource_service is not None:
            found = await self.resource_service.get(resource_uid)
            if found.is_error:
                return Result.fail(found)
            if found.value is None:
                return Result.fail(Errors.not_found(resource="resource", identifier=resource_uid))

        # 2. Strip provenance frontmatter before chunking.
        body = _strip_frontmatter(markdown_text)

        # 3. Prose-tuned chunking (reuses the curriculum chunker), then
        #    consolidate its fine structural splits into prose-grain passages.
        raw_chunks = ContentChunkingStrategy.chunk_markdown(
            body, parent_uid=resource_uid, params=params
        )
        chunks = _consolidate_chunks(raw_chunks, resource_uid, params)
        self.logger.info(
            f"Chunked {resource_uid}: {len(raw_chunks)} raw fragments → "
            f"{len(chunks)} consolidated passages (target {params.max_chunk_size}w)"
        )

        # 3b. Refuse a zero-chunk ingest. store_reference_chunks is delete-then-
        #     create, so persisting [] would delete an already-shelved book's
        #     HAS_REFERENCE_CHUNK subtree and report success — a bad/empty input
        #     file silently unshelving a book. Unshelving must be explicit
        #     (delete_reference_chunks), never a side effect of ingest.
        if not chunks:
            return Result.fail(
                Errors.validation(
                    f"No chunks produced for {resource_uid} — the file is empty, "
                    "frontmatter-only, or every fragment was dropped. Refusing to "
                    "persist: a zero-chunk write would unshelve the existing book. "
                    "Use delete_reference_chunks to unshelve explicitly.",
                    field="markdown_text",
                )
            )

        # 4. Persist chunks (delete-then-create; embedding carry-over inside).
        stored = await self.reference_chunk_adapter.store_reference_chunks(resource_uid, chunks)
        if not stored:
            return Result.fail(
                Errors.database(
                    operation="store_reference_chunks",
                    message=(
                        f"Failed to persist {len(chunks)} reference chunks for "
                        f"{resource_uid} (Resource missing or write error)"
                    ),
                )
            )

        # 5. Request embeddings post-persist (no-op + warn when event_bus is
        #    None — CORE tier). publish_event returns False on no bus.
        from core.events import ReferenceChunkEmbeddingRequested, publish_event

        # Publish in slices so the worker stores incrementally — one all-or-nothing
        # event for a whole book times out and stores zero (REFERENCE_EMBED_BATCH).
        embed_requested = False
        requested_at = datetime.now()
        for start in range(0, len(chunks), REFERENCE_EMBED_BATCH):
            batch = chunks[start : start + REFERENCE_EMBED_BATCH]
            published = await publish_event(
                self.event_bus,
                ReferenceChunkEmbeddingRequested(
                    parent_uid=resource_uid,
                    chunk_uids=tuple(c.chunk_id for c in batch),
                    chunk_texts=tuple(c.context_window for c in batch),
                    requested_at=requested_at,
                ),
                self.logger,
            )
            embed_requested = embed_requested or published

        self.logger.info(
            f"Ingested {len(chunks)} reference chunks for {resource_uid} "
            f"(embed_requested={embed_requested})"
        )
        return Result.ok(
            ReferenceIngestReport(
                resource_uid=resource_uid,
                chunks_written=len(chunks),
                embed_requested=embed_requested,
            )
        )
