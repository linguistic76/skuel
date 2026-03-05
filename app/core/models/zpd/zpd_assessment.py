"""
ZPD Assessment Model
=====================

Frozen dataclass representing a user's Zone of Proximal Development snapshot.

Produced by ZPDService.assess_zone() and consumed by:
- UserContextIntelligence.get_optimal_next_learning_steps() — primary ranking signal
- AskesisService — populates askesis_scaffold_entry and askesis_ku_bridge prompt slots

See: core/services/zpd/zpd_service.py
See: docs/roadmap/zpd-service-deferred.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class ZPDAssessment:
    """
    Snapshot of a user's Zone of Proximal Development.

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
        Mapping of ku_uid → readiness score (0.0–1.0) for each proximal KU.
        Score = fraction of the KU's prerequisites that are in current_zone.
        A KU with no prerequisites scores 1.0 (fully ready).

    blocking_gaps : list[str]
        ku_uids that are unmet prerequisites blocking further progress.
        These are prerequisite KUs not yet in current_zone that gate proximal KUs.

    behavioral_readiness : float
        Aggregate behavioral readiness score (0.0–1.0) derived from:
        - ChoicesIntelligence.get_zpd_behavioral_signals(): principle adherence,
          decision consistency, conflict count, high-quality decision rate
        - HabitsIntelligence.get_zpd_knowledge_signals(): reinforcement strength
        Defaults to 0.5 when behavioral intelligence is unavailable.

    assessed_at : datetime
        UTC timestamp of assessment. ZPDService is stateless — this is
        the creation time, not a cached value.
    """

    current_zone: list[str]
    proximal_zone: list[str]
    engaged_paths: list[str]
    readiness_scores: dict[str, float]
    blocking_gaps: list[str]
    behavioral_readiness: float
    assessed_at: datetime = field(default_factory=_utcnow)

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
