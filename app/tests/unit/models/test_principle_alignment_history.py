"""``AlignmentAssessment`` carries its kind and round-trips through the stored record."""

from __future__ import annotations

from datetime import date

from core.models.enums.principle_enums import AlignmentLevel
from core.models.principle.principle import _to_alignment_assessment
from core.models.principle.principle_types import AlignmentAssessment


def test_record_round_trips_with_its_kind() -> None:
    reflection = AlignmentAssessment(
        assessed_date=date(2026, 9, 12),
        alignment_level=AlignmentLevel.ALIGNED,
        evidence="Held the line in a hard meeting",
        kind="reflection",
    )
    record = reflection.to_record()
    assert record == {
        "assessed_date": "2026-09-12",
        "alignment_level": "aligned",
        "evidence": "Held the line in a hard meeting",
        "reflection": None,
        "kind": "reflection",
    }
    assert _to_alignment_assessment(record) == reflection


def test_a_stored_record_without_a_kind_reads_as_an_assessment() -> None:
    stored = {
        "assessed_date": "2026-08-01",
        "alignment_level": "partial",
        "evidence": "Self-rated",
        "reflection": "Getting there",
    }
    entry = _to_alignment_assessment(stored)
    assert entry.kind == "assessment"
    assert entry.alignment_level is AlignmentLevel.PARTIAL
