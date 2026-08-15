"""
Embedding coverage — retrievability measured in the graph, not inferred from config.

A node is *retrievable* by vector search only when it carries an embedding.
Whether embeddings actually got written depends on runtime state no config
flag can see: CORE-tier periods persist chunks with ``embedding = NULL``, a
missing ``OPENAI_API_KEY`` stalls the backfill, the background worker may
never have started, or an embedding API can die mid-batch. This module is the
domain vocabulary for measuring that state directly: which labels to scan,
which per-label scope filters apply, what the remedy for a gap is, and the
frozen result shapes the probe returns.

The probe itself is one CORE-safe count query —
``EmbeddingCoverageBackend.measure_embedding_coverage`` (curriculum_backends).
No LLM or embedding client involved, which is exactly why the gauge still
works when the capability that fills the gap is off.

Consumers: ``KnowledgeHealthService`` (report block + authoring flag),
``scripts/generate_embeddings_batch.py`` (the backfill shares these label
maps so gauge and remedy can never drift apart).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.events.embedding_publisher import EMBEDDING_NODE_LABELS
from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.enums.pipeline import Pipeline

if TYPE_CHECKING:
    from core.ports.query_types import EmbeddingCoverageReport, EmbeddingLabelCoverage

# Neo4j label → EntityType, inverted from the chokepoint's one label map —
# no hand-maintained mirror (the map itself is guarded against
# EMBEDDING_EVENT_TYPES drift by test_post_persist_embedding.py).
EMBEDDABLE_LABELS: dict[str, EntityType] = {
    label: entity_type for entity_type, label in EMBEDDING_NODE_LABELS.items()
}

CONTENT_CHUNK_LABEL = NeoLabel.CONTENT_CHUNK.value
REFERENCE_CHUNK_LABEL = NeoLabel.REFERENCE_CHUNK.value

# Chunk labels carry embeddings but are not entities (no EntityType) — the
# coverage split (missing_chunks vs missing_entities) keys off this set.
CHUNK_SCAN_LABELS: frozenset[str] = frozenset({CONTENT_CHUNK_LABEL, REFERENCE_CHUNK_LABEL})

# Every label the coverage probe scans: the embeddable entity labels (inverted
# from the chokepoint map, never hand-mirrored) plus the two chunk labels.
# Guarded against drift by test_post_persist_embedding.py.
EMBEDDING_SCAN_LABELS: tuple[str, ...] = (
    *EMBEDDABLE_LABELS,
    CONTENT_CHUNK_LABEL,
    REFERENCE_CHUNK_LABEL,
)

# Per-label extra WHERE clauses, ANDed into every candidate query (all backfill
# modes + hash stamping) AND both coverage counts. UserEntry embedding is
# pipeline-scoped: only knowledge entries embed (the event path gates in
# UserEntryService) — without this the backfill would embed every entry,
# including exercise turn-ins and teacher-review submissions the event path
# deliberately never publishes. Private notes never embed either (canon P3) —
# no vector may exist for them, so the gauge must not count them as missing.
LABEL_EXTRA_FILTERS: dict[str, str] = {
    NeoLabel.USER_ENTRY.value: (
        f"n.pipeline = '{Pipeline.KNOWLEDGE.value}' AND coalesce(n.private, false) = false"
    ),
}

# The remedy for a coverage gap on labels the backstop script covers.
BACKFILL_COMMAND = "./dev embed-backfill"

# ReferenceChunk has no backstop mode (generate_embeddings_batch covers the
# entity labels + ContentChunk only) — its sole recovery is re-ingesting.
REFERENCE_CHUNK_REMEDY = "re-run scripts/ingest_canon_book.py"


def label_backfill(label: str) -> str | None:
    """The backfill command for a label, or ``None`` when no backfill path exists.

    ``None`` currently means ReferenceChunk — see :data:`REFERENCE_CHUNK_REMEDY`
    for the manual recovery its renderers should name instead.
    """
    return None if label == REFERENCE_CHUNK_LABEL else BACKFILL_COMMAND


@dataclass(frozen=True, slots=True)
class LabelCoverage:
    """One label's embedding coverage: total scanned nodes vs nodes lacking a vector."""

    label: str
    total: int
    missing: int
    backfill: str | None  # remedy command, or None when no backfill path exists


@dataclass(frozen=True, slots=True)
class EmbeddingCoverage:
    """Corpus-wide embedding coverage, measured in the graph.

    ``missing`` splits into ``missing_chunks`` (ContentChunk/ReferenceChunk)
    and ``missing_entities`` (the embeddable entity labels) because their
    remedies differ — see :func:`remedy_text`.
    """

    by_label: tuple[LabelCoverage, ...]
    total: int
    missing: int
    missing_chunks: int
    missing_entities: int

    @property
    def is_complete(self) -> bool:
        """True when every scanned node carries an embedding."""
        return self.missing == 0

    @classmethod
    def from_label_counts(cls, by_label: tuple[LabelCoverage, ...]) -> EmbeddingCoverage:
        """Fold per-label counts into corpus totals (chunk vs entity split)."""
        missing = sum(c.missing for c in by_label)
        missing_chunks = sum(c.missing for c in by_label if c.label in CHUNK_SCAN_LABELS)
        return cls(
            by_label=by_label,
            total=sum(c.total for c in by_label),
            missing=missing,
            missing_chunks=missing_chunks,
            missing_entities=missing - missing_chunks,
        )

    def as_report(self) -> EmbeddingCoverageReport:
        """JSON-safe TypedDict shape for ``KnowledgeHealthReport`` / renderers."""
        rows: list[EmbeddingLabelCoverage] = [
            {
                "label": c.label,
                "total": c.total,
                "missing": c.missing,
                "backfill": c.backfill,
            }
            for c in self.by_label
        ]
        return {
            "by_label": rows,
            "total": self.total,
            "missing": self.missing,
            "missing_chunks": self.missing_chunks,
            "missing_entities": self.missing_entities,
            "is_complete": self.is_complete,
            "remedy": remedy_text(self),
        }


def remedy_text(coverage: EmbeddingCoverage) -> str:
    """The remedy line for a coverage gap — names the real command(s).

    Empty when coverage is complete. Joins the backfill command with the
    ReferenceChunk manual recovery when both kinds of gap are present.
    """
    remedies: list[str] = []
    if any(c.missing and c.backfill for c in coverage.by_label):
        remedies.append(f"run {BACKFILL_COMMAND}")
    if any(c.missing and c.backfill is None for c in coverage.by_label):
        remedies.append(REFERENCE_CHUNK_REMEDY)
    return "; ".join(remedies)
