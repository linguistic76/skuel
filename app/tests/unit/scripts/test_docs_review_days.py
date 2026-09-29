"""The docs tools count days since a review as calendar days, in the app default zone.

A ``last_reviewed`` frontmatter value is a YAML date or an ISO string, with or
without a time and an offset. The count is today's day less the review's day,
both in ``SKUEL_TIMEZONE``: a moment is the day it falls on there, and a value
with an offset counts like any other. An unreadable value reads as never
reviewed.

See: /docs/roadmap/utc-instants-arc.md § PR 6
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from docs_freshness import (  # type: ignore[import-not-found]
    StalenessConfig,
    check_conceptual_freshness,
)
from docs_review_scheduler import calculate_review_status  # type: ignore[import-not-found]

from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import default_zone

REVIEWED = date(2026, 9, 1)


@pytest.fixture
def doc(tmp_path: Path) -> Path:
    path = tmp_path / "docs" / "CONCEPT.md"
    path.parent.mkdir()
    path.write_text("# Concept\n", encoding="utf-8")
    return path


def _days_since_review() -> int:
    return (today_in(default_zone()) - REVIEWED).days


@pytest.mark.parametrize(
    "last_reviewed",
    [REVIEWED, "2026-09-01", "2026-09-01T12:00:00+00:00", "2026-09-01T12:00:00Z"],
)
class TestDaysSinceReview:
    def test_freshness_counts_calendar_days(self, doc: Path, last_reviewed: object) -> None:
        result = check_conceptual_freshness(
            doc, {"last_reviewed": last_reviewed}, StalenessConfig()
        )
        assert result.days_since_review == _days_since_review()

    def test_the_scheduler_counts_calendar_days(
        self, doc: Path, tmp_path: Path, last_reviewed: object
    ) -> None:
        status = calculate_review_status(
            doc, {"tracking": "conceptual", "last_reviewed": last_reviewed}, tmp_path
        )
        assert status is not None
        assert status.days_since_review == _days_since_review()


def test_an_unreadable_review_date_reads_as_never_reviewed(doc: Path, tmp_path: Path) -> None:
    freshness = check_conceptual_freshness(
        doc, {"last_reviewed": "early September"}, StalenessConfig()
    )
    status = calculate_review_status(
        doc, {"tracking": "conceptual", "last_reviewed": "early September"}, tmp_path
    )
    assert freshness.days_since_review == 999 and freshness.review_overdue
    assert status is not None and status.days_since_review == 999
