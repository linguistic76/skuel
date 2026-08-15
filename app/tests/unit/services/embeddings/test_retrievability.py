"""Unit tests for the embedding-coverage (retrievability) domain module.

Pure logic only — the totals fold, the chunk/entity split, remedy assignment,
and the JSON-safe report shape. The count Cypher itself is exercised against a
real graph in ``tests/integration/test_knowledge_health_instrument.py``.
"""

from __future__ import annotations

from core.services.embeddings.retrievability import (
    BACKFILL_COMMAND,
    REFERENCE_CHUNK_LABEL,
    REFERENCE_CHUNK_REMEDY,
    EmbeddingCoverage,
    LabelCoverage,
    label_backfill,
    remedy_text,
)


def _cov(label: str, total: int, missing: int) -> LabelCoverage:
    return LabelCoverage(label=label, total=total, missing=missing, backfill=label_backfill(label))


class TestLabelBackfill:
    def test_entity_and_content_chunk_labels_name_the_dev_target(self) -> None:
        assert label_backfill("Ku") == BACKFILL_COMMAND
        assert label_backfill("ContentChunk") == BACKFILL_COMMAND

    def test_reference_chunk_has_no_backfill_path(self) -> None:
        assert label_backfill(REFERENCE_CHUNK_LABEL) is None


class TestFromLabelCounts:
    def test_totals_and_chunk_entity_split(self) -> None:
        coverage = EmbeddingCoverage.from_label_counts(
            (
                _cov("Ku", 100, 4),
                _cov("Task", 50, 0),
                _cov("ContentChunk", 1143, 200),
                _cov("ReferenceChunk", 351, 12),
            )
        )
        assert coverage.total == 1644
        assert coverage.missing == 216
        assert coverage.missing_chunks == 212
        assert coverage.missing_entities == 4
        assert coverage.is_complete is False

    def test_empty_graph_is_complete(self) -> None:
        coverage = EmbeddingCoverage.from_label_counts(())
        assert coverage.total == 0
        assert coverage.missing == 0
        assert coverage.is_complete is True

    def test_fully_embedded_corpus_is_complete(self) -> None:
        coverage = EmbeddingCoverage.from_label_counts(
            (_cov("Ku", 10, 0), _cov("ContentChunk", 20, 0))
        )
        assert coverage.is_complete is True


class TestRemedyText:
    def test_backfillable_gap_names_the_dev_target(self) -> None:
        coverage = EmbeddingCoverage.from_label_counts((_cov("Ku", 10, 3),))
        assert remedy_text(coverage) == f"run {BACKFILL_COMMAND}"

    def test_reference_chunk_gap_names_canon_reingest(self) -> None:
        coverage = EmbeddingCoverage.from_label_counts((_cov("ReferenceChunk", 351, 5),))
        assert remedy_text(coverage) == REFERENCE_CHUNK_REMEDY

    def test_both_gap_kinds_joined(self) -> None:
        coverage = EmbeddingCoverage.from_label_counts(
            (_cov("Ku", 10, 1), _cov("ReferenceChunk", 351, 5))
        )
        assert remedy_text(coverage) == f"run {BACKFILL_COMMAND}; {REFERENCE_CHUNK_REMEDY}"

    def test_complete_coverage_has_no_remedy(self) -> None:
        coverage = EmbeddingCoverage.from_label_counts((_cov("Ku", 10, 0),))
        assert remedy_text(coverage) == ""


class TestAsReport:
    def test_report_shape_mirrors_dataclass(self) -> None:
        coverage = EmbeddingCoverage.from_label_counts(
            (_cov("Ku", 10, 2), _cov("ReferenceChunk", 5, 1))
        )
        report = coverage.as_report()
        assert report["by_label"] == [
            {"label": "Ku", "total": 10, "missing": 2, "backfill": BACKFILL_COMMAND},
            {"label": "ReferenceChunk", "total": 5, "missing": 1, "backfill": None},
        ]
        assert report["total"] == 15
        assert report["missing"] == 3
        assert report["missing_chunks"] == 1
        assert report["missing_entities"] == 2
        assert report["is_complete"] is False
        assert report["remedy"] == f"run {BACKFILL_COMMAND}; {REFERENCE_CHUNK_REMEDY}"

    def test_report_is_json_serializable(self) -> None:
        import json

        coverage = EmbeddingCoverage.from_label_counts((_cov("ReferenceChunk", 5, 1),))
        assert json.loads(json.dumps(coverage.as_report()))["missing"] == 1
