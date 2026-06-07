"""
Perception Intelligence Mixin
=============================

Cross-domain synthesis of dual-track perception gaps (ADR-030).

The per-entity dual-track surface (Goals/Habits/Principles detail pages) lets a
user rate themselves and persists each check-in to the entity's
``dual_track_checkins`` log. This mixin reads the latest check-in per entity
across those domains and synthesizes a user-level picture: where the user
systematically over-rates themselves, where they under-rate (doing better than
they think), and where self-perception is accurate.

This is the cross-domain aggregator ADR-030 deferred as "Future":
    "You consistently underestimate yourself across Goals and Habits"
    "Your self-perception is accurate for Principles but optimistic for Tasks"

Analytics-tier (reads stored graph data, no AI) — available at INTELLIGENCE_TIER=core.
"""

from __future__ import annotations

from operator import itemgetter
from typing import Any

from core.constants import QueryLimit
from core.services.user.intelligence._base import IntelligenceMixinBase
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger("skuel.services.user.perception")

# Per-entity dual-track domains and their display labels. Tasks/Events/Choices
# are user-level (assessed on the Self Check-In page, not per entity) and have no
# persisted per-entity check-ins to aggregate here.
_DOMAIN_LABELS: dict[str, str] = {
    "goals": "Goals",
    "habits": "Habits",
    "principles": "Principles",
}

_DIRECTIONS: tuple[str, ...] = ("user_higher", "system_higher", "aligned")


def _join_labels(labels: list[str]) -> str:
    """`['Goals', 'Habits']` -> `'Goals and Habits'` (Oxford comma for 3+)."""
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return ", ".join(labels[:-1]) + f", and {labels[-1]}"


class PerceptionIntelligenceMixin(IntelligenceMixinBase):
    """Cross-domain perception-gap synthesis for UserContextIntelligence."""

    async def get_cross_domain_perception_analysis(self) -> Result[dict[str, Any]]:
        """
        Synthesize dual-track perception gaps across Goals, Habits, and Principles.

        For each domain, loads the user's entities, takes the most recent
        dual-track check-in per entity (``dual_track_checkins[-1]``), and buckets
        its ``gap_direction``. A domain's dominant direction classifies it as
        over-rated (user rates higher than the data), under-rated (doing better
        than they think), or accurate.

        Returns:
            Result[dict] with:
            - per_domain: {domain: {label, assessed_count, direction_counts,
              avg_gap, dominant_direction}}
            - over_rated_domains / under_rated_domains / accurate_domains: labels
            - total_assessed_entities: int
            - insights: list[str] — natural-language cross-domain synthesis
            - has_data: bool — False when no check-ins exist yet
        """
        user_uid = self.context.user_uid
        services: dict[str, Any] = {
            "goals": self.goals,
            "habits": self.habits,
            "principles": self.principles,
        }

        per_domain: dict[str, dict[str, Any]] = {}
        over_rated: list[str] = []
        under_rated: list[str] = []
        accurate: list[str] = []
        total_assessed = 0

        for domain, service in services.items():
            label = _DOMAIN_LABELS[domain]
            direction_counts: dict[str, int] = {d: 0 for d in _DIRECTIONS}
            gaps: list[float] = []

            entities_result = await service.backend.find_by(
                user_uid=user_uid, limit=QueryLimit.COMPREHENSIVE
            )
            if entities_result.is_error:
                # A single domain read failing shouldn't sink the whole analysis;
                # record it as empty and continue (the others still contribute).
                logger.warning(
                    "Perception analysis: %s read failed: %s",
                    domain,
                    entities_result.expect_error().message,
                )
                entities: list[Any] = []
            else:
                entities = entities_result.value or []

            for entity in entities:
                checkins = getattr(entity, "dual_track_checkins", ()) or ()
                if not checkins:
                    continue
                latest = checkins[-1]
                direction = str(latest.get("gap_direction", "aligned"))
                if direction not in direction_counts:
                    direction = "aligned"
                direction_counts[direction] += 1
                gap = latest.get("perception_gap")
                if isinstance(gap, int | float):
                    gaps.append(float(gap))

            assessed = sum(direction_counts.values())
            total_assessed += assessed
            dominant: str | None = None
            if assessed:
                dominant = max(direction_counts.items(), key=itemgetter(1))[0]
                if dominant == "user_higher":
                    over_rated.append(label)
                elif dominant == "system_higher":
                    under_rated.append(label)
                else:
                    accurate.append(label)

            per_domain[domain] = {
                "label": label,
                "assessed_count": assessed,
                "direction_counts": direction_counts,
                "avg_gap": round(sum(gaps) / len(gaps), 3) if gaps else 0.0,
                "dominant_direction": dominant,
            }

        insights = self._synthesize_perception_insights(over_rated, under_rated, accurate)

        return Result.ok(
            {
                "per_domain": per_domain,
                "over_rated_domains": over_rated,
                "under_rated_domains": under_rated,
                "accurate_domains": accurate,
                "total_assessed_entities": total_assessed,
                "insights": insights,
                "has_data": total_assessed > 0,
            }
        )

    @staticmethod
    def _synthesize_perception_insights(
        over_rated: list[str], under_rated: list[str], accurate: list[str]
    ) -> list[str]:
        """Turn per-domain direction classifications into plain-English insights."""
        if not (over_rated or under_rated or accurate):
            return [
                "No self-assessments recorded yet. Rate your progress, consistency, or "
                "alignment on a goal, habit, or principle to see where your "
                "self-perception and your tracked actions diverge."
            ]

        insights: list[str] = []
        if over_rated:
            insights.append(
                f"You tend to rate yourself higher than your tracked actions on "
                f"{_join_labels(over_rated)}. Consider whether expressing activity is "
                "going untracked — or whether there's a blind spot to close."
            )
        if under_rated:
            insights.append(
                f"You're doing better than you think on {_join_labels(under_rated)} — your "
                "actions show more than your self-rating. Acknowledge the progress; "
                "self-recognition sustains momentum."
            )
        if accurate:
            insights.append(
                f"Your self-perception matches the data on {_join_labels(accurate)} — "
                "healthy self-awareness."
            )
        if over_rated and under_rated:
            insights.append(
                f"Your calibration isn't uniform: you under-rate yourself on "
                f"{_join_labels(under_rated)} but over-rate on {_join_labels(over_rated)}."
            )
        return insights
