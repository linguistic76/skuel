"""
Tests for Principle.needs_review() and days_until_review_needed()
===================================================================

Validates principle-specific review logic: alignment drift detection,
strength-based cadence, grace period for new principles, and dormancy.
"""

from datetime import date, datetime, timedelta

import pytest

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.principle_enums import AlignmentLevel, PrincipleStrength
from core.models.principle.principle import Principle


def _make_principle(**overrides) -> Principle:
    """Create a Principle with sensible defaults, overridable by kwargs."""
    defaults = {
        "entity_type": EntityType.PRINCIPLE,
        "uid": "principle_test_abc123",
        "user_uid": "user_test",
        "title": "Test Principle",
        "is_active": True,
        "current_alignment": AlignmentLevel.ALIGNED,
        "strength": PrincipleStrength.MODERATE,
        "adopted_date": date.today() - timedelta(days=60),
        "last_review_date": date.today() - timedelta(days=5),
    }
    defaults.update(overrides)
    return Principle(**defaults)


# =========================================================================
# DORMANT / INACTIVE — should never need review
# =========================================================================


class TestDormantPrinciples:
    def test_inactive_principle_no_review(self):
        p = _make_principle(is_active=False)
        assert p.needs_review() is False

    def test_archived_principle_no_review(self):
        p = _make_principle(status=EntityStatus.ARCHIVED)
        assert p.needs_review() is False

    def test_paused_principle_no_review(self):
        p = _make_principle(status=EntityStatus.PAUSED)
        assert p.needs_review() is False


# =========================================================================
# ALIGNMENT DRIFT — always triggers review
# =========================================================================


class TestAlignmentDrift:
    def test_drifting_triggers_review(self):
        p = _make_principle(
            current_alignment=AlignmentLevel.DRIFTING,
            last_review_date=date.today(),
        )
        assert p.needs_review() is True

    def test_misaligned_triggers_review(self):
        p = _make_principle(
            current_alignment=AlignmentLevel.MISALIGNED,
            last_review_date=date.today(),
        )
        assert p.needs_review() is True

    def test_drifting_overrides_recent_review(self):
        """Even if reviewed today, alignment drift forces review."""
        p = _make_principle(
            current_alignment=AlignmentLevel.DRIFTING,
            last_review_date=date.today(),
            strength=PrincipleStrength.CORE,
        )
        assert p.needs_review() is True


# =========================================================================
# UNKNOWN / UNASSESSED ALIGNMENT
# =========================================================================


class TestUnassessedAlignment:
    def test_unknown_alignment_past_grace_triggers_review(self):
        p = _make_principle(
            current_alignment=AlignmentLevel.UNKNOWN,
            adopted_date=date.today() - timedelta(days=30),
        )
        assert p.needs_review() is True

    def test_none_alignment_past_grace_triggers_review(self):
        p = _make_principle(
            current_alignment=None,
            adopted_date=date.today() - timedelta(days=30),
        )
        assert p.needs_review() is True

    def test_unknown_alignment_within_grace_no_review(self):
        p = _make_principle(
            current_alignment=AlignmentLevel.UNKNOWN,
            adopted_date=date.today() - timedelta(days=3),
        )
        assert p.needs_review() is False


# =========================================================================
# GRACE PERIOD — new principles get 7-day pass
# =========================================================================


class TestGracePeriod:
    def test_never_reviewed_within_grace_no_review(self):
        p = _make_principle(
            last_review_date=None,
            adopted_date=date.today() - timedelta(days=3),
        )
        assert p.needs_review() is False

    def test_never_reviewed_past_grace_triggers_review(self):
        p = _make_principle(
            last_review_date=None,
            adopted_date=date.today() - timedelta(days=14),
        )
        assert p.needs_review() is True

    def test_grace_uses_created_at_when_no_adopted_date(self):
        p = _make_principle(
            last_review_date=None,
            adopted_date=None,
            created_at=datetime.now() - timedelta(days=3),
        )
        assert p.needs_review() is False

    def test_grace_uses_created_at_default_when_no_adopted_date(self):
        """No adopted_date → created_at is auto-set by __post_init__ (brand new = within grace)."""
        p = _make_principle(
            last_review_date=None,
            adopted_date=None,
            # created_at=None → __post_init__ sets to now() → within grace
        )
        assert p.needs_review() is False


# =========================================================================
# TIME-BASED CADENCE
# =========================================================================


class TestTimeCadence:
    def test_recently_reviewed_no_review(self):
        p = _make_principle(
            strength=PrincipleStrength.MODERATE,
            last_review_date=date.today() - timedelta(days=10),
        )
        assert p.needs_review() is False

    def test_overdue_moderate_triggers_review(self):
        """MODERATE cadence = 30 days."""
        p = _make_principle(
            strength=PrincipleStrength.MODERATE,
            last_review_date=date.today() - timedelta(days=31),
        )
        assert p.needs_review() is True

    def test_exactly_at_cadence_triggers_review(self):
        """At exactly the cadence boundary, review is needed."""
        p = _make_principle(
            strength=PrincipleStrength.MODERATE,
            last_review_date=date.today() - timedelta(days=30),
        )
        assert p.needs_review() is True

    def test_one_day_before_cadence_no_review(self):
        p = _make_principle(
            strength=PrincipleStrength.MODERATE,
            last_review_date=date.today() - timedelta(days=29),
        )
        assert p.needs_review() is False


# =========================================================================
# STRENGTH-BASED CADENCE VALUES
# =========================================================================


class TestStrengthCadence:
    @pytest.mark.parametrize(
        ("strength", "cadence_days"),
        [
            (PrincipleStrength.EXPLORING, 14),
            (PrincipleStrength.DEVELOPING, 21),
            (PrincipleStrength.MODERATE, 30),
            (PrincipleStrength.STRONG, 45),
            (PrincipleStrength.CORE, 60),
        ],
    )
    def test_cadence_by_strength(self, strength, cadence_days):
        """Each strength level has its own review cadence."""
        # Overdue by 1 day
        p = _make_principle(
            strength=strength,
            last_review_date=date.today() - timedelta(days=cadence_days + 1),
        )
        assert p.needs_review() is True

        # 1 day before cadence
        p2 = _make_principle(
            strength=strength,
            last_review_date=date.today() - timedelta(days=cadence_days - 1),
        )
        assert p2.needs_review() is False

    def test_none_strength_defaults_to_30(self):
        p = _make_principle(
            strength=None,
            last_review_date=date.today() - timedelta(days=31),
        )
        assert p.needs_review() is True

        p2 = _make_principle(
            strength=None,
            last_review_date=date.today() - timedelta(days=29),
        )
        assert p2.needs_review() is False


# =========================================================================
# WELL-ALIGNED + RECENTLY REVIEWED — the "happy path"
# =========================================================================


class TestHappyPath:
    def test_well_aligned_recently_reviewed_no_review(self):
        """Confirms scoring path: well-aligned + recent review = 0 score."""
        p = _make_principle(
            current_alignment=AlignmentLevel.ALIGNED,
            strength=PrincipleStrength.CORE,
            last_review_date=date.today() - timedelta(days=10),
        )
        assert p.needs_review() is False

    def test_flourishing_recently_reviewed_no_review(self):
        p = _make_principle(
            current_alignment=AlignmentLevel.FLOURISHING,
            strength=PrincipleStrength.STRONG,
            last_review_date=date.today() - timedelta(days=5),
        )
        assert p.needs_review() is False


# =========================================================================
# days_until_review_needed()
# =========================================================================


class TestDaysUntilReview:
    def test_inactive_returns_none(self):
        p = _make_principle(is_active=False)
        assert p.days_until_review_needed() is None

    def test_archived_returns_none(self):
        p = _make_principle(status=EntityStatus.ARCHIVED)
        assert p.days_until_review_needed() is None

    def test_overdue_returns_zero(self):
        p = _make_principle(
            strength=PrincipleStrength.MODERATE,
            last_review_date=date.today() - timedelta(days=35),
        )
        assert p.days_until_review_needed() == 0

    def test_alignment_drift_returns_zero(self):
        p = _make_principle(current_alignment=AlignmentLevel.DRIFTING)
        assert p.days_until_review_needed() == 0

    def test_days_remaining(self):
        p = _make_principle(
            strength=PrincipleStrength.MODERATE,
            last_review_date=date.today() - timedelta(days=20),
        )
        assert p.days_until_review_needed() == 10

    def test_just_reviewed_returns_full_cadence(self):
        p = _make_principle(
            strength=PrincipleStrength.EXPLORING,
            last_review_date=date.today(),
        )
        assert p.days_until_review_needed() == 14

    def test_never_reviewed_within_grace_returns_none(self):
        """No last_review_date and within grace → not applicable yet."""
        p = _make_principle(
            last_review_date=None,
            adopted_date=date.today() - timedelta(days=3),
        )
        assert p.days_until_review_needed() is None

    def test_never_reviewed_past_grace_returns_zero(self):
        p = _make_principle(
            last_review_date=None,
            adopted_date=date.today() - timedelta(days=30),
        )
        assert p.days_until_review_needed() == 0
