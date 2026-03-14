"""
ZPD Assessment Model
=====================

Frozen dataclass representing a user's Zone of Proximal Development snapshot.

ZPD is the pedagogical gravity well — the capstone computation on UserContext
that synthesizes all prior fields into "what's most important, what advances
your life path most."

Produced by ZPDService.assess_zone() and consumed by:
- UserContext.zpd_assessment — computed as final step of build_rich()
- UserContextIntelligence.get_optimal_next_learning_steps() — primary ranking signal
- AskesisService — populates askesis_scaffold_entry and askesis_ku_bridge prompt slots
- DailyPlanningMixin.get_ready_to_work_on_today() — P5 learning priority

See: core/services/zpd/zpd_service.py
See: docs/roadmap/zpd-service-deferred.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class ZoneEvidence:
    """Compound evidence for why a KU is in current_zone.

    ZPD requires 2+ signal types to consider a KU "confirmed" in the current
    zone. A single strong submission alone doesn't move a KU to confirmed
    status — it needs compound evidence from different activity types.
    """

    ku_uid: str
    submission_count: int = 0
    best_submission_score: float = 0.0
    habit_reinforcement: bool = False
    task_application: bool = False
    journal_application: bool = False

    @property
    def signal_count(self) -> int:
        """Count distinct evidence types present."""
        return sum(
            [
                self.submission_count > 0,
                self.habit_reinforcement,
                self.task_application,
                self.journal_application,
            ]
        )

    @property
    def is_confirmed(self) -> bool:
        """True when 2+ evidence types present (compound mastery)."""
        return self.signal_count >= 2


@dataclass(frozen=True)
class ZPDAction:
    """A concrete recommended action from ZPD assessment.

    Actions bridge ZPD zone analysis to daily planning — each action
    targets a specific entity that advances the user's proximal zone.
    """

    entity_uid: str
    entity_type: str  # "exercise", "lesson", "task", "habit"
    action_type: str  # "learn", "submit", "reinforce", "practice"
    priority: float  # 0.0-1.0
    rationale: str
    ku_uid: str | None = None  # The KU this action advances


@dataclass(frozen=True)
class ZPDAssessment:
    """
    Snapshot of a user's Zone of Proximal Development.

    ZPD is the pedagogical gravity well — the capstone computation that
    synthesizes curriculum graph traversal, behavioral signals, life path
    alignment, and compound evidence into actionable learning priorities.

    Fields
    ------
    current_zone : list[str]
        ku_uids the user has meaningfully engaged — via APPLIES_KNOWLEDGE (Tasks,
        Journals), REINFORCES_KNOWLEDGE (Habits), or direct habit reinforcement.

    proximal_zone : list[str]
        ku_uids structurally adjacent to the current zone but not yet engaged.
        Derived via PREREQUISITE_FOR, COMPLEMENTARY_TO, and LP ORGANIZES
        traversal. These are the candidates for the user's next learning step.

    engaged_paths : list[str]
        lp_uids (Learning Path UIDs) that the user has partially traversed —
        i.e., paths that contain at least one current_zone KU.

    readiness_scores : dict[str, float]
        Mapping of ku_uid -> readiness score (0.0-1.0) for each proximal KU.
        Score = fraction of the KU's prerequisites that are in current_zone.
        A KU with no prerequisites scores 1.0 (fully ready).

    blocking_gaps : list[str]
        ku_uids that are unmet prerequisites blocking further progress.
        These are prerequisite KUs not yet in current_zone that gate proximal KUs.

    behavioral_readiness : float
        Aggregate behavioral readiness score (0.0-1.0) derived from:
        - ChoicesIntelligence.get_zpd_behavioral_signals(): principle adherence,
          decision consistency, conflict count, high-quality decision rate
        - HabitsIntelligence.get_zpd_knowledge_signals(): reinforcement strength
        Defaults to 0.5 when behavioral intelligence is unavailable.

    assessed_at : datetime
        UTC timestamp of assessment. ZPDService is stateless — this is
        the creation time, not a cached value.

    life_path_alignment : float
        Life path alignment score (0.0-1.0) from UserContext. Factors into
        recommended action priority.

    life_path_uid : str | None
        The user's life path UID, when available.

    recommended_actions : tuple[ZPDAction, ...]
        Concrete recommended actions derived from proximal zone analysis.
        Sorted by priority descending. Consumed by daily planning P5.

    zone_evidence : dict[str, ZoneEvidence]
        Per-KU compound evidence tracking. Maps ku_uid to ZoneEvidence.
        KUs with is_confirmed=True have 2+ signal types.

    submission_scores : dict[str, float]
        Best submission score per KU, derived from ExerciseSubmission
        scores linked via FULFILLS_EXERCISE -> APPLIES_KNOWLEDGE.
    """

    current_zone: list[str]
    proximal_zone: list[str]
    engaged_paths: list[str]
    readiness_scores: dict[str, float]
    blocking_gaps: list[str]
    behavioral_readiness: float
    assessed_at: datetime = field(default_factory=_utcnow)

    # Life path integration
    life_path_alignment: float = 0.0
    life_path_uid: str | None = None

    # Recommended actions (absorbs daily planning P5 learning)
    recommended_actions: tuple[ZPDAction, ...] = ()

    # Zone evidence tracking (compound mastery)
    zone_evidence: dict[str, ZoneEvidence] = field(default_factory=dict)

    # Submission-derived scores
    submission_scores: dict[str, float] = field(default_factory=dict)

    def is_empty(self) -> bool:
        """True when the curriculum graph lacks enough data for meaningful ZPD.

        ZPDService returns an empty assessment (not a failure) when the curriculum
        graph has fewer than 3 KUs or the user has no APPLIES_KNOWLEDGE relationships.
        Consumers should check this before using the assessment for recommendations.
        """
        return not self.current_zone and not self.proximal_zone

    def top_proximal_ku_uids(self, n: int = 5) -> list[str]:
        """Return the top-n proximal KUs ranked by readiness score (descending).

        Use this for recommendation ranking — highest-readiness KUs first.
        """

        def by_readiness(uid: str) -> float:
            return self.readiness_scores.get(uid, 0.0)

        return sorted(self.proximal_zone, key=by_readiness, reverse=True)[:n]

    def top_recommended_actions(self, n: int = 5) -> list[ZPDAction]:
        """Return top-n recommended actions sorted by priority descending."""

        def by_priority(action: ZPDAction) -> float:
            return action.priority

        return sorted(self.recommended_actions, key=by_priority, reverse=True)[:n]

    def confirmed_zone_uids(self) -> list[str]:
        """KU UIDs with compound-confirmed evidence (2+ signal types)."""
        return [uid for uid, evidence in self.zone_evidence.items() if evidence.is_confirmed]
