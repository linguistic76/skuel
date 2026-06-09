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
from core.models.enums import DualTrackDimension
from core.services.user.intelligence._base import IntelligenceMixinBase
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger("skuel.services.user.perception")

# Per-entity dual-track domains and their display labels. Each entity in these
# domains carries its own `dual_track_checkins` log (Goals/Habits/Principles).
_DOMAIN_LABELS: dict[str, str] = {
    "goals": "Goals",
    "habits": "Habits",
    "principles": "Principles",
}

# User-level dual-track dimensions (Tasks/Events/Choices) assess the user across
# all their entities of a kind, so their check-ins live on the :User node
# (context.dual_track_checkins), keyed by DualTrackDimension value — not per
# entity. They are folded into the same per_domain rollup below so the synthesis
# spans both per-entity and user-level perception gaps.
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
        Synthesize dual-track perception gaps across all assessable domains.

        Three sources are merged into one rollup:

        - **Per-entity** (Goals/Habits/Principles): loads the user's entities, takes
          the most recent dual-track check-in per entity (``dual_track_checkins[-1]``),
          and buckets each ``gap_direction``. A domain's dominant direction classifies
          it.
        - **User-level** (Productivity/Engagement/Decision Quality): reads the most
          recent check-in per dimension off ``context.dual_track_checkins`` (persisted
          on the :User node by the Self Check-In page) and buckets its direction.
        - **Knowledge** (per-Ku mastery): reads the latest check-in per Ku off
          ``context.knowledge_checkins`` (persisted per-(user, Ku) on the :User node by
          the Ku detail page) and aggregates them into a single "Knowledge" bucket.

        Each domain/dimension is classified as over-rated (user rates higher than the
        data), under-rated (doing better than they think), or accurate.

        Returns:
            Result[dict] with:
            - per_domain: {key: {label, assessed_count, direction_counts,
              avg_gap, dominant_direction}} — keys are domain names (goals/habits/
              principles), DualTrackDimension values (productivity/engagement/
              decision_quality), and "knowledge"
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

        # User-level dimensions (Tasks/Events/Choices) — one latest check-in per
        # dimension off the :User node (context.dual_track_checkins). Only emitted
        # when a check-in exists (there's no "entity count" to report at 0).
        user_checkins = getattr(self.context, "dual_track_checkins", {}) or {}
        for dimension in DualTrackDimension:
            log = user_checkins.get(dimension.value) or []
            if not log:
                continue
            latest = log[-1]
            direction = str(latest.get("gap_direction", "aligned"))
            if direction not in _DIRECTIONS:
                direction = "aligned"
            label = dimension.label()
            gap = latest.get("perception_gap")
            avg_gap = round(float(gap), 3) if isinstance(gap, int | float) else 0.0

            total_assessed += 1
            if direction == "user_higher":
                over_rated.append(label)
            elif direction == "system_higher":
                under_rated.append(label)
            else:
                accurate.append(label)

            per_domain[dimension.value] = {
                "label": label,
                "assessed_count": 1,
                "direction_counts": {d: (1 if d == direction else 0) for d in _DIRECTIONS},
                "avg_gap": avg_gap,
                "dominant_direction": direction,
            }

        # Knowledge dimension (per-Ku mastery, ADR-030) — aggregate the latest
        # check-in per Ku into one "Knowledge" bucket (analogous to a per-entity
        # domain) so the synthesis spans the Knowledge dimension too. A Ku is SHARED,
        # so its mastery check-ins live per-user on the :User node
        # (context.knowledge_checkins), keyed by Ku uid.
        knowledge_checkins = getattr(self.context, "knowledge_checkins", {}) or {}
        k_direction_counts: dict[str, int] = {d: 0 for d in _DIRECTIONS}
        k_gaps: list[float] = []
        for log in knowledge_checkins.values():
            if not log:
                continue
            latest = log[-1]
            direction = str(latest.get("gap_direction", "aligned"))
            if direction not in k_direction_counts:
                direction = "aligned"
            k_direction_counts[direction] += 1
            gap = latest.get("perception_gap")
            if isinstance(gap, int | float):
                k_gaps.append(float(gap))

        k_assessed = sum(k_direction_counts.values())
        if k_assessed:
            total_assessed += k_assessed
            k_dominant = max(k_direction_counts.items(), key=itemgetter(1))[0]
            if k_dominant == "user_higher":
                over_rated.append("Knowledge")
            elif k_dominant == "system_higher":
                under_rated.append("Knowledge")
            else:
                accurate.append("Knowledge")
            per_domain["knowledge"] = {
                "label": "Knowledge",
                "assessed_count": k_assessed,
                "direction_counts": k_direction_counts,
                "avg_gap": round(sum(k_gaps) / len(k_gaps), 3) if k_gaps else 0.0,
                "dominant_direction": k_dominant,
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
                "alignment on a goal, habit, or principle — or run a Self Check-In on "
                "your productivity, engagement, and decision quality — to see where your "
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
