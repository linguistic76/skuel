"""
Tests for ZPD Assessment model — ZoneEvidence, ZPDAction, ZPDAssessment.

Covers:
- ZoneEvidence compound mastery logic (is_confirmed, signal_count)
- ZPDAction sorting by priority
- ZPDAssessment methods: top_recommended_actions, confirmed_zone_uids, is_empty
- Integration of new fields (life_path_alignment, zone_evidence, submission_scores)
"""

from __future__ import annotations

from core.models.zpd.zpd_assessment import ZoneEvidence, ZPDAction, ZPDAssessment

# ============================================================================
# ZoneEvidence
# ============================================================================


class TestZoneEvidence:
    """Compound mastery requires 2+ signal types."""

    def test_no_signals(self) -> None:
        ev = ZoneEvidence(ku_uid="ku_1")
        assert ev.signal_count == 0
        assert not ev.is_confirmed

    def test_single_signal_not_confirmed(self) -> None:
        ev = ZoneEvidence(ku_uid="ku_1", task_application=True)
        assert ev.signal_count == 1
        assert not ev.is_confirmed

    def test_submission_alone_not_confirmed(self) -> None:
        """Single strong submission doesn't confirm — needs 2+ signal types."""
        ev = ZoneEvidence(ku_uid="ku_1", submission_count=5, best_submission_score=0.95)
        assert ev.signal_count == 1
        assert not ev.is_confirmed

    def test_two_signals_confirmed(self) -> None:
        ev = ZoneEvidence(ku_uid="ku_1", task_application=True, habit_reinforcement=True)
        assert ev.signal_count == 2
        assert ev.is_confirmed

    def test_three_signals_confirmed(self) -> None:
        ev = ZoneEvidence(
            ku_uid="ku_1",
            submission_count=1,
            task_application=True,
            journal_application=True,
        )
        assert ev.signal_count == 3
        assert ev.is_confirmed

    def test_all_four_signals(self) -> None:
        ev = ZoneEvidence(
            ku_uid="ku_1",
            submission_count=2,
            habit_reinforcement=True,
            task_application=True,
            journal_application=True,
        )
        assert ev.signal_count == 4
        assert ev.is_confirmed


# ============================================================================
# ZPDAction
# ============================================================================


class TestZPDAction:
    """Actions have entity_uid, priority, and action_type."""

    def test_basic_action(self) -> None:
        action = ZPDAction(
            entity_uid="ku_1",
            entity_type="article",
            action_type="learn",
            priority=0.8,
            rationale="all prerequisites met",
            ku_uid="ku_1",
        )
        assert action.priority == 0.8
        assert action.action_type == "learn"
        assert action.ku_uid == "ku_1"

    def test_action_without_ku(self) -> None:
        action = ZPDAction(
            entity_uid="task_1",
            entity_type="task",
            action_type="practice",
            priority=0.5,
            rationale="Apply knowledge",
        )
        assert action.ku_uid is None


# ============================================================================
# ZPDAssessment
# ============================================================================


def _make_assessment(**kwargs: object) -> ZPDAssessment:
    """Helper to create ZPDAssessment with defaults."""
    defaults: dict = {
        "current_zone": ["ku_a", "ku_b"],
        "proximal_zone": ["ku_c", "ku_d"],
        "engaged_paths": ["lp_1"],
        "readiness_scores": {"ku_c": 0.8, "ku_d": 1.0},
        "blocking_gaps": [],
        "behavioral_readiness": 0.6,
    }
    defaults.update(kwargs)
    return ZPDAssessment(**defaults)


class TestZPDAssessmentEmpty:
    def test_empty_when_no_zones(self) -> None:
        a = _make_assessment(current_zone=[], proximal_zone=[])
        assert a.is_empty()

    def test_not_empty_with_current_zone(self) -> None:
        a = _make_assessment()
        assert not a.is_empty()


class TestTopProximalKuUids:
    def test_returns_sorted_by_readiness(self) -> None:
        a = _make_assessment(
            proximal_zone=["ku_c", "ku_d", "ku_e"],
            readiness_scores={"ku_c": 0.3, "ku_d": 1.0, "ku_e": 0.7},
        )
        result = a.top_proximal_ku_uids(2)
        assert result == ["ku_d", "ku_e"]

    def test_respects_limit(self) -> None:
        a = _make_assessment()
        result = a.top_proximal_ku_uids(1)
        assert len(result) == 1


class TestTopRecommendedActions:
    def test_sorts_by_priority_descending(self) -> None:
        actions = (
            ZPDAction("ku_a", "article", "learn", 0.3, "low"),
            ZPDAction("ku_b", "article", "learn", 0.9, "high"),
            ZPDAction("ku_c", "article", "learn", 0.6, "mid"),
        )
        a = _make_assessment(recommended_actions=actions)
        top = a.top_recommended_actions(2)
        assert len(top) == 2
        assert top[0].entity_uid == "ku_b"
        assert top[1].entity_uid == "ku_c"

    def test_empty_actions(self) -> None:
        a = _make_assessment()
        assert a.top_recommended_actions() == []


class TestConfirmedZoneUids:
    def test_returns_confirmed_only(self) -> None:
        evidence = {
            "ku_a": ZoneEvidence(ku_uid="ku_a", task_application=True, habit_reinforcement=True),
            "ku_b": ZoneEvidence(ku_uid="ku_b", task_application=True),  # not confirmed
        }
        a = _make_assessment(zone_evidence=evidence)
        confirmed = a.confirmed_zone_uids()
        assert confirmed == ["ku_a"]

    def test_empty_evidence(self) -> None:
        a = _make_assessment()
        assert a.confirmed_zone_uids() == []


class TestNewFields:
    def test_life_path_fields(self) -> None:
        a = _make_assessment(life_path_alignment=0.85, life_path_uid="lp_life_1")
        assert a.life_path_alignment == 0.85
        assert a.life_path_uid == "lp_life_1"

    def test_submission_scores(self) -> None:
        a = _make_assessment(submission_scores={"ku_a": 0.9, "ku_b": 0.7})
        assert a.submission_scores["ku_a"] == 0.9

    def test_defaults(self) -> None:
        a = _make_assessment()
        assert a.life_path_alignment == 0.0
        assert a.life_path_uid is None
        assert a.recommended_actions == ()
        assert a.zone_evidence == {}
        assert a.submission_scores == {}
