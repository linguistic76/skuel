"""
LifePath Alignment Service
===========================

Calculates alignment between a user's life path and their actual behaviour.

This service answers: "Am I living my life path?"

**This service owns all five dimensions' scoring policy.** The backend returns
mastery and counts; the ratios, the weights, the momentum bands and the no-data
rule are decided here, in one place. Splitting it the other way is what produced
this metric's two live defects: per-instance substance weights hand-copied into
Cypher (a third copy of ``USER_SUBSTANCE_CHANNELS``, already drifted), and a
``CASE WHEN total = 0 THEN 0.5`` repeated in four queries.

Two rulings the arithmetic below encodes, both deliberate:

* **A level with no evidence scores 0.0, not 0.5.** Knowledge, activity, goal
  and principle are levels. The old neutral default made the metric INVERT — a
  learner's first life-path habit dropped the activity dimension from 0.50 to
  0.20, because the habit entered the denominator while the wrong read edge kept
  it out of the numerator.
* **Momentum keeps a neutral 0.5.** It measures a rate of change, and "no change
  data" genuinely is neutral there — unlike a level, where it is not evidence of
  being half-way.

See: /docs/architecture/knowledge_substance_philosophy.md
     /docs/technical_debt/LIFEPATH_ALIGNMENT_DEBT.md
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Final

from core.models.enums.principle_enums import AlignmentLevel
from core.models.type_hints import UserUID
from core.ports.query_types import LifePathAlignmentResult
from core.services.knowledge.user_substance import (
    SUBSTANCE_ACTIVITY_TYPES,
    build_substance_index,
    channel_maps_from_rows,
    channel_weight,
    user_substance_score,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.cross_domain_protocols import CrossDomainBackendOperations
    from core.ports.lifepath_protocols import LifePathBackendOperations
    from core.services.knowledge.user_substance import SubstanceIndex
    from core.services.lp_service import LpService
    from core.services.ps_service import PsService
    from core.services.user.unified_user_context import UserContext

logger = get_logger(__name__)

# The five dimension weights. Documented as 25/25/20/15/15 and asserted by
# tests/integration/test_lifepath_alignment_calculation.py.
_W_KNOWLEDGE: Final = 0.25
_W_ACTIVITY: Final = 0.25
_W_GOAL: Final = 0.20
_W_PRINCIPLE: Final = 0.15
_W_MOMENTUM: Final = 0.15

# How much of a Ku's knowledge score is mastery, the rest being what the learner
# has actually DONE with it. This one is a property of THIS metric — it says
# "knowing counts for 0.6 of knowing-and-living" — so it lives here. The
# per-instance substance weights it is added to do NOT: those belong to
# USER_SUBSTANCE_CHANNELS and are read from it.
_MASTERY_WEIGHT: Final = 0.6

# A dimension with nothing to measure. See the module docstring: levels get 0.0,
# the momentum derivative gets 0.5.
_NO_LEVEL_DATA: Final = 0.0
_NEUTRAL_MOMENTUM: Final = 0.5

# Momentum bands over recent÷previous. Growing fast, growing, holding, declining.
_MOMENTUM_BANDS: Final[tuple[tuple[float, float], ...]] = (
    (1.5, 1.0),
    (1.0, 0.7),
    (0.5, 0.5),
)
_MOMENTUM_DECLINING: Final = 0.3
# No previous week to divide by: any recent activity is a start, none is neutral.
_MOMENTUM_FROM_STANDSTILL: Final = 0.8

# Mastery bands for the embodied/theoretical split reported alongside the score.
_EMBODIED_AT: Final = 0.7
_THEORETICAL_BELOW: Final = 0.5


class LifePathAlignmentService:
    """
    Service for calculating life path alignment.

    Measures how well user's actual behavior (tracked in UserContext)
    aligns with their designated life path.

    Alignment Dimensions (5):
    1. Knowledge Alignment (25%): Mastery of life path knowledge
    2. Activity Alignment (25%): Tasks/habits supporting life path
    3. Goal Alignment (20%): Active goals contributing to life path
    4. Principle Alignment (15%): Values supporting life path direction
    5. Momentum (15%): Recent activity trend toward life path
    """

    def __init__(
        self,
        backend: LifePathBackendOperations | None = None,
        lp_service: LpService | None = None,
        ku_service: PsService | None = None,
        cross_domain_backend: CrossDomainBackendOperations | None = None,
    ) -> None:
        """
        Initialize alignment service.

        Args:
            backend: LifePathBackendOperations for database operations
            lp_service: LP service for path details
            ku_service: KU service for knowledge substance
            cross_domain_backend: source of the learner's six activity→knowledge
                channels. REQUIRED to score: without it the knowledge dimension
                would fall back to mastery alone under a substance-weighted
                heading, which is a confident wrong number rather than a missing
                one, so its absence refuses instead.
        """
        self.backend = backend
        self.lp_service = lp_service
        self.ku_service = ku_service
        self.cross_domain_backend = cross_domain_backend
        logger.info("LifePathAlignmentService initialized")

    async def calculate_alignment(self, context: UserContext) -> Result[LifePathAlignmentResult]:
        """
        Calculate comprehensive life path alignment.

        This is THE most important metric in SKUEL - measures whether
        user is LIVING their life path or just learning about it.

        A failed read PROPAGATES rather than degrading to a low score: every
        dimension's no-data reading is now a real number (0.0 for a level), so a
        silent fallback would be indistinguishable from a learner who has done
        nothing — and it would be persisted as one, onto ULTIMATE_PATH.

        Args:
            context: Pre-built UserContext for the subject user

        Returns:
            Result containing comprehensive alignment analysis
        """
        user_uid = context.user_uid
        logger.info(f"Calculating life path alignment for user {user_uid}")

        # Get user's life path
        life_path_uid = await self._get_user_life_path(user_uid)
        if not life_path_uid:
            return Result.ok(self._no_designation_response())

        # Get life path details
        lp_details = await self._get_life_path_details(life_path_uid)

        substance_result = await self._build_substance_index(user_uid)
        if substance_result.is_error:
            return Result.fail(substance_result)

        # Calculate each dimension
        knowledge_result = await self._calculate_knowledge_alignment(
            user_uid, life_path_uid, substance_result.value
        )
        if knowledge_result.is_error:
            return Result.fail(knowledge_result)
        knowledge_score, knowledge_stats = knowledge_result.value

        activity_result = await self._calculate_activity_alignment(user_uid, life_path_uid)
        if activity_result.is_error:
            return Result.fail(activity_result)
        activity_score = activity_result.value

        goal_result = await self._calculate_goal_alignment(user_uid, life_path_uid)
        if goal_result.is_error:
            return Result.fail(goal_result)
        goal_score = goal_result.value

        principle_result = await self._calculate_principle_alignment(user_uid, life_path_uid)
        if principle_result.is_error:
            return Result.fail(principle_result)
        principle_score = principle_result.value

        momentum_result = await self._calculate_momentum(user_uid, life_path_uid)
        if momentum_result.is_error:
            return Result.fail(momentum_result)
        momentum_score = momentum_result.value

        # Calculate weighted overall score
        overall_score = (
            knowledge_score * _W_KNOWLEDGE
            + activity_score * _W_ACTIVITY
            + goal_score * _W_GOAL
            + principle_score * _W_PRINCIPLE
            + momentum_score * _W_MOMENTUM
        )

        alignment_level = AlignmentLevel.from_score(overall_score)

        # Generate recommendations
        recommendations = self._generate_recommendations(
            knowledge_score=knowledge_score,
            activity_score=activity_score,
            goal_score=goal_score,
            principle_score=principle_score,
            momentum_score=momentum_score,
        )

        result: LifePathAlignmentResult = {
            "life_path_uid": life_path_uid,
            "life_path_title": lp_details.get("title", "Unknown"),
            "alignment_score": round(overall_score, 3),
            "alignment_level": alignment_level.value,
            "dimensions": {
                "knowledge": round(knowledge_score, 3),
                "activity": round(activity_score, 3),
                "goal": round(goal_score, 3),
                "principle": round(principle_score, 3),
                "momentum": round(momentum_score, 3),
            },
            "knowledge_stats": knowledge_stats,
            "recommendations": recommendations,
            "calculated_at": datetime.now().isoformat(),
        }

        logger.info(
            f"Alignment calculated for {user_uid}: {overall_score:.2f} ({alignment_level.value})"
        )

        return Result.ok(result)

    async def _get_user_life_path(self, user_uid: UserUID) -> str | None:
        """Get user's designated life path UID."""
        if not self.backend:
            return None

        result = await self.backend.get_user_life_path(user_uid)
        if result.is_error:
            logger.error(
                "Failed to get life path - returning None",
                extra={
                    "user_uid": user_uid,
                    "error_message": str(result.error),
                },
            )
            return None

        records = result.value or []
        if records:
            return records[0].get("life_path_uid")
        return None

    async def _get_life_path_details(self, life_path_uid: str) -> dict[str, str]:
        """Get life path title and metadata."""
        if self.lp_service:
            lp_result = await self.lp_service.core.get(life_path_uid)
            if lp_result.is_ok and lp_result.value:
                return {
                    "title": lp_result.value.title,
                    "description": lp_result.value.description or "",
                }
        return {"title": "Unknown", "description": ""}

    @staticmethod
    def _level(aligned: int, total: int) -> float:
        """A level dimension's ratio, with THE no-data ruling in one place.

        Nothing owned means nothing measured, and nothing measured is not
        half-aligned. The 0.5 this replaces was repeated in four dimension
        queries and is what let the metric invert: a learner's first habit moved
        the activity dimension DOWN, off the neutral default, while the read edge
        kept it out of the numerator.
        """
        return _NO_LEVEL_DATA if total <= 0 else aligned / total

    async def _build_substance_index(self, user_uid: UserUID) -> Result[SubstanceIndex]:
        """The learner's ku→channel-count index, from the UNWINDOWED source.

        Substance is cumulative — a habit you kept last year still reinforced the
        knowledge — so the channels come from
        ``get_user_knowledge_channels`` rather than from a UserContext, whose
        copies are bounded by the planning window (and unevenly: an ACTIVE habit
        is admitted at any age, an old event is not).

        Refuses when unwired. The fallback would be mastery alone reported under
        a substance-weighted heading; a metric that silently drops its applied
        half is the defect this service is being repaired for.
        """
        if not self.cross_domain_backend:
            return Result.fail(
                Errors.system(
                    "Cannot score life path alignment without a knowledge-channel source",
                    operation="calculate_alignment",
                )
            )

        rows = await self.cross_domain_backend.get_user_knowledge_channels(
            user_uid, list(SUBSTANCE_ACTIVITY_TYPES)
        )
        if rows.is_error:
            return Result.fail(rows)
        return Result.ok(build_substance_index(channel_maps_from_rows(rows.value or [])))

    async def _calculate_knowledge_alignment(
        self, user_uid: UserUID, life_path_uid: str, substance: SubstanceIndex
    ) -> Result[tuple[float, dict[str, int]]]:
        """
        Calculate knowledge dimension (25% weight), and the embodied/theoretical split.

        Per Ku the path teaches: mastery at ``_MASTERY_WEIGHT``, plus what the
        learner has DONE with it, scored by ``USER_SUBSTANCE_CHANNELS`` — the one
        weight table, with its per-channel caps, covering all six channels. The
        dimension is the mean over the path's Kus, so a Ku nobody has touched
        stays in the denominator.

        Returns the split alongside the score because both band the SAME mastery
        rows; computing them apart meant a second query over the identical
        traversal. The split remains a mastery proxy — no MASTERED writer sets a
        substance property, and a true ADR-046 Ku-grain rollup is roadmap work.
        """
        if not self.backend:
            return Result.fail(
                Errors.system("Backend not available", operation="knowledge_alignment")
            )

        result = await self.backend.get_life_path_ku_mastery(user_uid, life_path_uid)
        if result.is_error:
            return Result.fail(result)

        rows = result.value or []
        if not rows:
            return Result.ok((_NO_LEVEL_DATA, {"total": 0, "embodied": 0, "theoretical": 0}))

        scores = [
            min(
                1.0,
                row["mastery"] * _MASTERY_WEIGHT + user_substance_score(row["ku_uid"], substance),
            )
            for row in rows
        ]
        stats = {
            "total": len(rows),
            "embodied": sum(1 for row in rows if row["mastery"] >= _EMBODIED_AT),
            "theoretical": sum(1 for row in rows if row["mastery"] < _THEORETICAL_BELOW),
        }
        return Result.ok((sum(scores) / len(scores), stats))

    async def _calculate_activity_alignment(
        self, user_uid: UserUID, life_path_uid: str
    ) -> Result[float]:
        """
        Calculate activity dimension (25% weight).

        What share of the learner's tasks and habits point at the life path,
        blended in the proportion ``USER_SUBSTANCE_CHANNELS`` already assigns
        those two channels (0.05 : 0.10 → ⅓ : ⅔). Derived rather than asserted:
        a second, independent pair of numbers beside the table's is how the
        substance vocabulary drifts.

        Stays tasks-and-habits rather than widening to all six channels — goals
        and principles carry their own dimensions, and counting them here would
        score the same fact twice.
        """
        if not self.backend:
            return Result.fail(
                Errors.system("Backend not available", operation="activity_alignment")
            )

        result = await self.backend.get_life_path_activity_counts(user_uid, life_path_uid)
        if result.is_error:
            return Result.fail(result)

        counts = result.value
        task_weight = channel_weight("tasks")
        habit_weight = channel_weight("habits")
        task_share = task_weight / (task_weight + habit_weight)

        task_ratio = self._level(counts["aligned_tasks"], counts["total_tasks"])
        habit_ratio = self._level(counts["aligned_habits"], counts["total_habits"])
        return Result.ok(task_ratio * task_share + habit_ratio * (1.0 - task_share))

    async def _calculate_goal_alignment(
        self, user_uid: UserUID, life_path_uid: str
    ) -> Result[float]:
        """
        Calculate goal dimension (20% weight).

        What share of the learner's active goals SERVE the life path.
        """
        if not self.backend:
            return Result.fail(Errors.system("Backend not available", operation="goal_alignment"))

        result = await self.backend.get_life_path_goal_counts(user_uid, life_path_uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok(self._level(result.value["serving"], result.value["total"]))

    async def _calculate_principle_alignment(
        self, user_uid: UserUID, life_path_uid: str
    ) -> Result[float]:
        """
        Calculate principle dimension (15% weight).

        What share of the learner's active principles SERVE the life path.
        """
        if not self.backend:
            return Result.fail(
                Errors.system("Backend not available", operation="principle_alignment")
            )

        result = await self.backend.get_life_path_principle_counts(user_uid, life_path_uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok(self._level(result.value["serving"], result.value["total"]))

    async def _calculate_momentum(self, user_uid: UserUID, life_path_uid: str) -> Result[float]:
        """
        Calculate momentum dimension (15% weight).

        The rate at which the learner commits to NEW path-aligned work — tasks
        and habits alike — last 7 days against the 7 before. Committing to a
        habit that reinforces the path is momentum in the week it is made; a
        habit's ongoing practice is a different signal, carried by the knowledge
        dimension's substance term rather than counted again here.

        Unlike the four levels, this dimension keeps a NEUTRAL default: it
        measures a derivative, where no data really does mean "no trend", not
        "no progress".
        """
        if not self.backend:
            return Result.fail(Errors.system("Backend not available", operation="momentum"))

        now = datetime.now()
        result = await self.backend.get_life_path_momentum_counts(
            user_uid=user_uid,
            life_path_uid=life_path_uid,
            seven_days_ago=(now - timedelta(days=7)).isoformat(),
            fourteen_days_ago=(now - timedelta(days=14)).isoformat(),
        )
        if result.is_error:
            return Result.fail(result)

        recent = result.value["recent"]
        previous = result.value["previous"]
        if previous <= 0:
            return Result.ok(_MOMENTUM_FROM_STANDSTILL if recent > 0 else _NEUTRAL_MOMENTUM)

        ratio = recent / previous
        for threshold, score in _MOMENTUM_BANDS:
            if ratio >= threshold:
                return Result.ok(score)
        return Result.ok(_MOMENTUM_DECLINING)

    def _generate_recommendations(
        self,
        knowledge_score: float,
        activity_score: float,
        goal_score: float,
        principle_score: float,
        momentum_score: float,
    ) -> list[str]:
        """Generate actionable recommendations based on dimension scores."""
        recommendations = []

        if knowledge_score < 0.5:
            recommendations.append("Focus on mastering the knowledge units in your life path")

        if activity_score < 0.5:
            recommendations.append("Create habits that apply your life path knowledge daily")

        if goal_score < 0.5:
            recommendations.append("Set goals that directly contribute to your life path")

        if principle_score < 0.5:
            recommendations.append(
                "Align your principles more closely with your life path direction"
            )

        if momentum_score < 0.5:
            recommendations.append("Increase your daily activities toward your life path")

        if not recommendations:
            recommendations.append("Great work! Continue your current trajectory")

        return recommendations

    def _no_designation_response(self) -> LifePathAlignmentResult:
        """Response when user hasn't designated a life path."""
        return {
            "life_path_uid": None,
            "alignment_score": 0.0,
            "alignment_level": "undefined",
            "dimensions": {
                "knowledge": 0.0,
                "activity": 0.0,
                "goal": 0.0,
                "principle": 0.0,
                "momentum": 0.0,
            },
            "knowledge_stats": {"total": 0, "embodied": 0, "theoretical": 0},
            "recommendations": [
                "Express your vision to get started!",
                "Use the vision capture to articulate your life goals",
            ],
            "message": "No life path designated. Express your vision to begin.",
        }
