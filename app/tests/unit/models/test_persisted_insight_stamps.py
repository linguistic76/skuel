"""``PersistedInsight`` reads a stored node's stamps as Python ``datetime`` values.

The insight writer stores ``created_at`` as a native (``datetime($created_at)``) and
the dismiss / action writers stamp ``datetime()``, so a graph read hands
``from_dict`` neo4j ``DateTime`` values. A neo4j ``DateTime`` does not subtract from
a Python ``datetime`` (``TypeError``), so ``from_dict`` converts every stamp, and
``priority_score`` / ``is_expired`` compare through ``as_utc``. These tests build the
node dict the way the driver does (neo4j ``DateTime`` values) and pin the
arithmetic on both naive and aware stamps.

The real-graph proof is ``tests/integration/test_insight_native_stamps.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import neo4j.time

from core.models.insight.persisted_insight import InsightImpact, InsightType, PersistedInsight
from tests.helpers.forced_zone import forced_zone


def _native(moment: datetime) -> neo4j.time.DateTime:
    """A stamp as the driver returns a stored native."""
    return neo4j.time.DateTime.from_native(moment)


def _node(**stamps: Any) -> dict[str, Any]:  # boundary: a stored node's property dict
    return {
        "uid": "insight.difficulty_pattern.habit-x.20260927100000",
        "user_uid": "user_insight_stamps",
        "insight_type": InsightType.DIFFICULTY_PATTERN.value,
        "domain": "habits",
        "title": "Habit difficulty detected",
        "description": "Missed five of the last fourteen days.",
        "confidence": 0.8,
        "impact": InsightImpact.HIGH.value,
        "entity_uid": "habit.x",
        "dismissed": False,
        "actioned": False,
        **stamps,
    }


class TestNativeStampsBecomeDatetimes:
    def test_every_native_stamp_is_a_python_datetime(self) -> None:
        now = datetime.now(UTC)
        insight = PersistedInsight.from_dict(
            _node(
                created_at=_native(now - timedelta(hours=2)),
                expires_at=_native(now + timedelta(days=3)),
                dismissed_at=_native(now - timedelta(hours=1)),
                actioned_at=_native(now - timedelta(minutes=30)),
            )
        )
        for stamp in (
            insight.created_at,
            insight.expires_at,
            insight.dismissed_at,
            insight.actioned_at,
        ):
            assert type(stamp) is datetime
            assert stamp is not None and stamp.utcoffset() == timedelta(0)

    def test_a_native_created_at_serializes_without_raising(self) -> None:
        """The route's path: ``to_dict`` computes ``priority_score`` and ``is_active``."""
        insight = PersistedInsight.from_dict(
            _node(created_at=_native(datetime.now(UTC) - timedelta(hours=1)))
        )
        payload = insight.to_dict()
        assert payload["is_active"] is True
        assert 0 < payload["priority_score"] <= 3 * 0.8

    def test_to_dict_round_trips_through_from_dict(self) -> None:
        stored = PersistedInsight.from_dict(
            _node(
                created_at=_native(datetime.now(UTC) - timedelta(hours=1)),
                expires_at=_native(datetime.now(UTC) + timedelta(days=1)),
            )
        )
        again = PersistedInsight.from_dict(stored.to_dict())
        assert again.created_at == stored.created_at
        assert again.expires_at == stored.expires_at


class TestRecencyAcrossStampShapes:
    def test_a_naive_and_an_aware_stamp_of_one_moment_score_alike(self) -> None:
        """Under a zone west of UTC a naive local stamp is not read as UTC."""
        with forced_zone("America/Vancouver"):
            local_hour_ago = datetime.now() - timedelta(hours=1)
            aware_hour_ago = datetime.now(UTC) - timedelta(hours=1)
            naive_score = PersistedInsight.from_dict(
                _node(created_at=local_hour_ago.isoformat())
            ).priority_score()
            aware_score = PersistedInsight.from_dict(
                _node(created_at=_native(aware_hour_ago))
            ).priority_score()
        assert abs(naive_score - aware_score) < 0.001


class TestExpiryAcrossStampShapes:
    def test_a_future_native_expiry_is_not_expired(self) -> None:
        insight = PersistedInsight.from_dict(
            _node(
                created_at=_native(datetime.now(UTC)),
                expires_at=_native(datetime.now(UTC) + timedelta(hours=1)),
            )
        )
        assert insight.is_expired() is False
        assert insight.is_active() is True

    def test_a_past_native_expiry_is_expired(self) -> None:
        insight = PersistedInsight.from_dict(
            _node(
                created_at=_native(datetime.now(UTC) - timedelta(days=2)),
                expires_at=_native(datetime.now(UTC) - timedelta(hours=1)),
            )
        )
        assert insight.is_expired() is True
        assert insight.is_active() is False

    def test_a_naive_expiry_is_read_in_the_process_zone(self) -> None:
        with forced_zone("Asia/Bangkok"):
            insight = PersistedInsight.with_default_expiry(
                days=1,
                uid="insight.x",
                user_uid="user_insight_stamps",
                insight_type=InsightType.STREAK_PATTERN,
                domain="habits",
                title="t",
                description="d",
                confidence=0.5,
                impact=InsightImpact.LOW,
                entity_uid="habit.x",
            )
            assert insight.is_expired() is False
