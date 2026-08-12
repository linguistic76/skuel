"""
Analytics Life Path Service
============================

Life Path alignment tracking and analytics for Layer 3 meta-analysis.

This service provides the CRITICAL missing piece for Analytics to become
true Layer 3: calculating how well user's activities align with their
ultimate life goal (Life Path).

Core Philosophy: "Everything flows toward the life path"

This service answers:
- "Am I living my life path?" → Alignment score (0.0-1.0)
- "What knowledge do I actually use?" → Substance metrics
- "Which activities drive alignment?" → Channel contribution breakdown
- "Where should I focus?" → Gap identification + recommendations

Part of the 4-service Analytics architecture:
- AnalyticsService: Facade orchestrating all analytics
- AnalyticsMetricsService: Domain-specific statistics
- AnalyticsAggregationService: Cross-domain synthesis
- AnalyticsLifePathService: Life Path alignment tracking (this file)

Implementation Date: October 24, 2025
"""

from datetime import date, datetime, timedelta
from typing import Any, TypedDict

from core.models.type_hints import UserUID
from core.ports.query_types import LifePathStepRow, StepSubstance
from core.services.knowledge.user_substance import (
    SUBSTANCE_ACTIVITY_TYPES,
    USER_SUBSTANCE_CHANNELS,
    channel_maps_from_rows,
)
from core.utils.exception_types import DATA_CONVERSION_EXCEPTIONS, NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

_LIFE_PATH_EXCEPTIONS = (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS)

logger = get_logger(__name__)

# Band edges for the personal substance score, shared with
# AnalyticsMetricsService.calculate_knowledge_metrics. The same learner's same
# step must not read "embodied" on one analytics surface and "practiced" on the
# other; the two surfaces score identically, so they band identically. These
# match the Substance Scale in knowledge_substance_philosophy.md.
EMBODIED_THRESHOLD = 0.8
PRACTICED_THRESHOLD = 0.6
APPLIED_THRESHOLD = 0.3

# A step below this is under-substantiated for this learner — the threshold
# Curriculum.needs_review() uses, and the one calculate_knowledge_metrics ranks
# review_recommendations against.
GAP_THRESHOLD = 0.5

MAX_GAPS_REPORTED = 10


class KnowledgeSubstanceInfo(TypedDict):
    """Type definition for knowledge substance analysis data."""

    ku_uid: str  # PathStep UID (historical key spelling — see the method docstring)
    title: str  # PathStep title
    substance: float  # THIS learner's substance score (0.0-1.0)


def _substance_of(gap: KnowledgeSubstanceInfo) -> float:
    """Sort key for gap ranking (named, not a lambda — SKUEL012)."""
    return gap["substance"]


class AnalyticsLifePathService:
    """
    Life Path alignment tracking and analysis.

    This service calculates how well user's activities (Layer 1) serve
    their ultimate life goal (Life Path from Layer 0).

    Substance tracking measures whether knowledge is LIVED, not just learned —
    and lived BY THIS LEARNER. Every magnitude here is scored from the user's
    own six activity→knowledge channels, never from the counters
    ``KuBackend.increment_substance`` writes onto the shared curriculum node.
    """

    def __init__(
        self,
        ku_service: Any,
        lifepath_service: Any = None,
        cross_domain_backend: Any = None,
    ) -> None:
        """
        Initialize Life Path analytics service.

        Args:
            ku_service: PsService — batched per-learner substance scoring
            lifepath_service: LifePathService — designation, path composition,
                and alignment snapshot history
            cross_domain_backend: CrossDomainBackend — the learner's activity
                channels, which substance is scored against per-user rather
                than against the shared curriculum node's counters

        There is deliberately no ``user_service`` and no ``lp_service``:

        * ``UserService.get_user_context`` was the old source of
          ``life_path_uid``, and the STANDARD context never populates that field
          (``populate_life_path`` is called only from ``build_rich_user_context``),
          so the designation now comes from ``LifePathService``, one row.
        * ``LpService.get`` was the old source of the path title and steps.
          Designation flips a LearningPath node's ``entity_type`` to
          ``'life_path'`` in place, so reading a designated path through the LP
          service raises on ``LearningPath``'s honest-leaf-identity guard.
        """
        self.ku_service = ku_service
        self.lifepath_service = lifepath_service
        self.cross_domain_backend = cross_domain_backend

    async def calculate_life_path_alignment(self, user_uid: UserUID) -> Result[dict[str, Any]]:
        """
        Calculate user's alignment with their ultimate life goal.

        This is THE most important metric in SKUEL - measures whether
        user is LIVING their life path or just learning about it.

        THE SUBJECT IS THE WHOLE DESIGNATED PATH, not the part of it the learner
        has engaged with. A life path is a declaration of who they want to
        become; its composition IS the denominator. Scoring only the engaged part
        would make alignment RISE as a learner ignores most of their path, which
        inverts the question. This is the same ruling
        ``calculate_knowledge_metrics`` makes one level down for an engaged step
        with no application — the denominator is what you committed to, not what
        you touched. (That metric's selection is engagement-scoped because it
        asks a different question: how the learner did with what they took up in
        one WEEK.)

        MAGNITUDES ARE PER-LEARNER. Every score comes from
        ``PsService.get_user_substance_breakdowns``, which counts THIS learner's
        six activity channels. It deliberately does NOT use
        ``Curriculum.substance_score()``: that reads counters
        ``increment_substance`` writes onto the shared node with no ``user_uid``,
        so on a multi-tenant instance it reports every learner's activity on the
        material this one happens to have on their path.

        The channels are read UNWINDOWED, from
        ``CrossDomainBackend.get_user_knowledge_channels`` rather than from a
        ``UserContext``. A rich context would carry the same six maps, but the
        MEGA-QUERY builds them for PLANNING — a row enters only if it is open or
        was touched inside the window, and unevenly (an ACTIVE habit at any age,
        an event only inside the window). Alignment is cumulative: a habit built
        eight months ago that reinforces life-path knowledge is still
        substantiating it.

        Args:
            user_uid: User identifier

        Returns:
            Result containing comprehensive alignment analysis:
            {
                "life_path_uid": "lp.mindful-software-engineer",
                "life_path_title": "Become a Mindful Software Engineer",
                "alignment_score": 0.73, # 0.0-1.0, mean over the path's steps
                "knowledge_count": 15,
                "embodied_knowledge": 8, # substance >= 0.8
                "practiced_knowledge": 3, # 0.6-0.8
                "applied_knowledge": 2, # 0.3-0.6
                "theoretical_knowledge": 2, # < 0.3
                "domain_contributions": {
                    "tasks": 0.20, "habits": 0.40, "events": 0.10,
                    "entries": 0.15, "choices": 0.10, "principles": 0.05
                },
                "gaps": [
                    {"ku_uid": "ps.meditation", "title": "...", "substance": 0.3}
                ],
                "trends": {
                    "7_days_ago": 0.68,
                    "30_days_ago": 0.61,
                    "direction": "improving"
                },
                "recommendations": [...]
            }

            ``gaps`` lists the path's steps whose PERSONAL substance sits under
            the 0.5 review threshold, least-substantiated first, capped at 10 —
            the same rule and threshold ``review_recommendations`` uses, so the
            two analytics surfaces cannot disagree about what needs work.

            The ``ku_uid`` / ``knowledge_count`` keys are historical spelling:
            the values are PathStep uids and counts. A step's personal substance
            already averages its Kus', so scoring the Kus alongside it would
            count the same applications twice. Renaming the keys is an API change
            for the report templates and the alignment dashboard, so the names
            stay and this says what they carry.
        """
        if not self.lifepath_service:
            return Result.fail(
                Errors.system(
                    "LifePathService not available — the designation and the path's "
                    "composition cannot be read",
                    operation="calculate_life_path_alignment",
                )
            )
        if not self.ku_service:
            return Result.fail(
                Errors.system(
                    "PsService not available — path steps cannot be scored",
                    operation="calculate_life_path_alignment",
                )
            )
        if not self.cross_domain_backend:
            return Result.fail(
                Errors.system(
                    "CrossDomainBackend not available — the learner's activity channels "
                    "cannot be read, so substance has no per-learner source",
                    operation="calculate_life_path_alignment",
                )
            )

        try:
            logger.info(f"Calculating Life Path alignment for user {user_uid}")

            # Step 1: The designation. NOT off a UserContext — the standard
            # build leaves life_path_uid unset, which does not raise: it reads
            # as "this user has designated nothing", for every user.
            designation_result = await self.lifepath_service.get_designated_life_path_uid(user_uid)
            if designation_result.is_error:
                return Result.fail(designation_result)

            life_path_uid = designation_result.value
            if not life_path_uid:
                return Result.ok(
                    self._empty_alignment(
                        life_path_uid=None,
                        life_path_title=None,
                        recommendation="Designate a Life Path to track alignment",
                        message="No Life Path designated yet",
                    )
                )

            # Step 2: The path's title and the steps it composes, one read.
            composition_result = await self.lifepath_service.get_life_path_composition(
                life_path_uid
            )
            if composition_result.is_error:
                return Result.fail(composition_result)
            if not composition_result.value:
                return Result.fail(Errors.not_found(resource="Life Path", identifier=life_path_uid))

            composition = composition_result.value
            life_path_title = composition["life_path_title"]
            steps: list[LifePathStepRow] = composition["steps"]

            if not steps:
                return Result.ok(
                    self._empty_alignment(
                        life_path_uid=life_path_uid,
                        life_path_title=life_path_title,
                        recommendation="Add path steps to your Life Path",
                        message="Life Path has no path steps yet",
                    )
                )

            # Step 3: The learner's own activity channels, read ONCE and
            # UNWINDOWED — see the class docstring for why not a UserContext.
            channels_result = await self.cross_domain_backend.get_user_knowledge_channels(
                user_uid, list(SUBSTANCE_ACTIVITY_TYPES)
            )
            if channels_result.is_error:
                return Result.fail(channels_result)

            # Step 4: Score every step of the path against those channels, with
            # the per-channel parts, in one round trip.
            #
            # A failed scoring pass is NOT a learner who applied nothing: that
            # reading is plausible enough to be persisted as a real report, which
            # is exactly what makes it dangerous.
            substance_result = await self.ku_service.get_user_substance_breakdowns(
                [step["ps_uid"] for step in steps],
                channel_maps_from_rows(channels_result.value or []),
            )
            if substance_result.is_error:
                return Result.fail(substance_result)
            substance: dict[str, StepSubstance] = substance_result.value

            knowledge_analysis = self._analyze_knowledge_substance(steps, substance)
            alignment_score = knowledge_analysis["avg_substance"]
            domain_contributions = self._analyze_domain_contributions(steps, substance)
            gaps = knowledge_analysis["gaps"]
            trends = await self._calculate_alignment_trends(user_uid, life_path_uid)
            recommendations = self._generate_recommendations(
                knowledge_analysis, domain_contributions, gaps
            )

            return Result.ok(
                {
                    "life_path_uid": life_path_uid,
                    "life_path_title": life_path_title,
                    "alignment_score": round(alignment_score, 2),
                    "knowledge_count": knowledge_analysis["total_count"],
                    "embodied_knowledge": knowledge_analysis["embodied_count"],
                    "practiced_knowledge": knowledge_analysis["practiced_count"],
                    "applied_knowledge": knowledge_analysis["applied_count"],
                    "theoretical_knowledge": knowledge_analysis["theoretical_count"],
                    "domain_contributions": domain_contributions,
                    "gaps": gaps,
                    "trends": trends,
                    "recommendations": recommendations,
                    "user_uid": user_uid,
                    "calculated_at": datetime.now().isoformat(),
                }
            )

        except _LIFE_PATH_EXCEPTIONS as e:
            return Result.fail(
                Errors.system(
                    f"Failed to calculate Life Path alignment: {e!s}",
                    operation="calculate_life_path_alignment",
                    exception=e,
                )
            )
        except Exception as e:  # safety-net: catch unexpected errors
            logger.error(
                f"Unexpected error calculating Life Path alignment: {type(e).__name__}: {e}"
            )
            return Result.fail(
                Errors.system(
                    f"Failed to calculate Life Path alignment: {e!s}",
                    operation="calculate_life_path_alignment",
                    exception=e,
                )
            )

    @staticmethod
    def _empty_alignment(
        *,
        life_path_uid: str | None,
        life_path_title: str | None,
        recommendation: str,
        message: str,
    ) -> dict[str, Any]:
        """The nothing-to-score payload, in the shape consumers already read.

        One builder for both empty cases (no designation, designated path with no
        steps) so the two cannot drift into emitting different key sets — the
        alignment dashboard and the progress report both index this shape.
        """
        return {
            "life_path_uid": life_path_uid,
            "life_path_title": life_path_title,
            "alignment_score": 0.0,
            "knowledge_count": 0,
            "embodied_knowledge": 0,
            "practiced_knowledge": 0,
            "applied_knowledge": 0,
            "theoretical_knowledge": 0,
            "domain_contributions": {},
            "gaps": [],
            "trends": {},
            "recommendations": [recommendation],
            "message": message,
        }

    def _analyze_knowledge_substance(
        self, steps: list[LifePathStepRow], substance: dict[str, StepSubstance]
    ) -> dict[str, Any]:
        """
        Band this learner's substance across the path's steps.

        - Embodied (0.8+): Lifestyle-integrated
        - Practiced (0.6-0.8): Regular use
        - Applied (0.3-0.6): Some practice
        - Theoretical (<0.3): No real-world application

        EVERY step of the path is banded, including one the learner has never
        engaged with and one they engaged with but never applied. Both score 0.0
        and both stay in the denominator: 0.0 is not a missing value here, it is
        the reading "on my path, not yet in my life", which is precisely what
        this metric exists to surface. Dropping them would make alignment climb
        as a learner adds material and does nothing with it.

        Args:
            steps: The path's composed steps, in order
            substance: Per-step personal substance, keyed by step uid

        Returns:
            Dict with substance analysis
        """
        total_substance = 0.0
        embodied: list[KnowledgeSubstanceInfo] = []  # >= 0.8
        practiced: list[KnowledgeSubstanceInfo] = []  # 0.6-0.8
        applied: list[KnowledgeSubstanceInfo] = []  # 0.3-0.6
        theoretical: list[KnowledgeSubstanceInfo] = []  # < 0.3

        for step in steps:
            # Indexed, not .get()-ed: the batched scorer returns a row for every
            # requested uid, so a missing key is a contract break and must not be
            # absorbed as "this learner applied nothing".
            score = substance[step["ps_uid"]]["score"]
            total_substance += score

            info: KnowledgeSubstanceInfo = {
                "ku_uid": step["ps_uid"],
                "title": step["title"],
                "substance": round(score, 2),
            }

            if score >= EMBODIED_THRESHOLD:
                embodied.append(info)
            elif score >= PRACTICED_THRESHOLD:
                practiced.append(info)
            elif score >= APPLIED_THRESHOLD:
                applied.append(info)
            else:
                theoretical.append(info)

        count = len(steps)
        avg_substance = total_substance / count if count > 0 else 0.0

        # Under the review threshold, least-substantiated first, so the cap keeps
        # the ten that most need work rather than the first ten in path order.
        gaps = sorted(
            (
                info
                for info in (*theoretical, *applied, *practiced, *embodied)
                if info["substance"] < GAP_THRESHOLD
            ),
            key=_substance_of,
        )[:MAX_GAPS_REPORTED]

        return {
            "total_count": count,
            "avg_substance": avg_substance,
            "embodied_count": len(embodied),
            "practiced_count": len(practiced),
            "applied_count": len(applied),
            "theoretical_count": len(theoretical),
            "embodied": embodied,
            "practiced": practiced,
            "applied": applied,
            "theoretical": theoretical,
            "gaps": gaps,
        }

    @staticmethod
    def _analyze_domain_contributions(
        steps: list[LifePathStepRow], substance: dict[str, StepSubstance]
    ) -> dict[str, float]:
        """
        Which of the six substance channels this learner's alignment comes from.

        Sums each step's per-channel substance across the path and normalises to
        proportions, so "40% of my alignment is coming from habits" is a claim
        about this learner's own activity — the same six weights and caps that
        produced the headline score, decomposed rather than recomputed.

        SIX channels, not five. The node counters have no principles field, so
        the corpus-global figure never saw ``GROUNDED_IN_KNOWLEDGE``; the
        personal one does.

        Normalised against the breakdown's own total, never against the sum of
        the step scores: ``user_substance_score`` caps each Ku at 1.0 while the
        six channels contribute up to 1.30 raw, so for a heavily-applied Ku the
        parts total more than the capped score. Proportions of the uncapped
        decomposition are the meaningful reading; the cap belongs to the score.

        Returns all six keys even when the learner has no activity at all, zeroed
        — an absent channel and an empty one are the same fact to every consumer,
        and the dashboard renders a bar per key.
        """
        # Both sides are keyed off USER_SUBSTANCE_CHANNELS, so an unknown name
        # here means the table and the scorer have diverged. Indexed rather than
        # membership-guarded so that raises (KeyError → a failed Result) instead
        # of silently dropping a channel's substance, which would under-report
        # every other channel's proportion without any sign that it had.
        totals = {channel.name: 0.0 for channel in USER_SUBSTANCE_CHANNELS}
        for step in steps:
            for name, value in substance[step["ps_uid"]]["breakdown"].items():
                totals[name] += value

        grand_total = sum(totals.values())
        if grand_total <= 0:
            return totals
        return {name: round(value / grand_total, 2) for name, value in totals.items()}

    async def _calculate_alignment_trends(
        self, user_uid: UserUID, life_path_uid: str
    ) -> dict[str, Any]:
        """
        Calculate alignment trends over time.

        Shows whether alignment is improving, declining, or stable.

        ⚠ Snapshots recorded before 2026-08-12 are on the old corpus-global
        basis and are not comparable to ones recorded after — the direction they
        imply across that boundary is an artefact of the fix, not of the
        learner's behaviour.

        Args:
            user_uid: User identifier
            life_path_uid: Life Path UID

        Returns:
            Dict with historical alignment scores and trend direction
        """
        snapshots_result = await self.lifepath_service.get_alignment_trend_data(user_uid=user_uid)
        if snapshots_result.is_error or not snapshots_result.value:
            return {
                "user_uid": user_uid,
                "life_path_uid": life_path_uid,
                "7_days_ago": None,
                "30_days_ago": None,
                "direction": "unknown",
                "snapshot_count": 0,
            }

        snapshots = snapshots_result.value  # newest first
        today = date.today()
        cutoff_7d = today - timedelta(days=7)
        cutoff_30d = today - timedelta(days=30)

        current_score: float | None = snapshots[0]["score"] if snapshots else None
        score_7d: float | None = None
        score_30d: float | None = None

        for snap in snapshots:
            snap_date = date.fromisoformat(snap["date_str"])
            if score_7d is None and snap_date <= cutoff_7d:
                score_7d = snap["score"]
            if score_30d is None and snap_date <= cutoff_30d:
                score_30d = snap["score"]
            if score_7d is not None and score_30d is not None:
                break

        direction = "unknown"
        if current_score is not None and score_7d is not None:
            diff = current_score - score_7d
            if diff > 0.05:
                direction = "improving"
            elif diff < -0.05:
                direction = "declining"
            else:
                direction = "stable"

        return {
            "user_uid": user_uid,
            "life_path_uid": life_path_uid,
            "7_days_ago": round(score_7d, 3) if score_7d is not None else None,
            "30_days_ago": round(score_30d, 3) if score_30d is not None else None,
            "direction": direction,
            "snapshot_count": len(snapshots),
        }

    @staticmethod
    def _generate_recommendations(
        knowledge_analysis: dict[str, Any],
        domain_contributions: dict[str, float],
        gaps: list[KnowledgeSubstanceInfo],
    ) -> list[str]:
        """
        Generate actionable recommendations based on alignment analysis.

        The per-channel prompts come from ``USER_SUBSTANCE_CHANNELS`` rather than
        a hand-written branch per channel: the table is where the six channels
        are declared, so a seventh gets a recommendation by construction. The old
        branch covered three of the six and silently said nothing about entries,
        choices or principles.

        Args:
            knowledge_analysis: Substance analysis from _analyze_knowledge_substance
            domain_contributions: Per-channel proportions of this learner's substance
            gaps: Path steps whose personal substance is under the review threshold

        Returns:
            List of recommendation strings
        """
        recommendations = []

        if gaps:
            recommendations.extend(
                [
                    f"Increase substance for: {gap['title']} (currently {gap['substance']})"
                    for gap in gaps[:3]
                ]
            )

        # A channel the learner has not used AT ALL on this path. Contributions
        # are proportions, so 0.0 here means no activity of that kind touches any
        # of the path's knowledge — the concrete thing to change.
        recommendations.extend(
            [
                channel.recommendation.format(title="your Life Path")
                for channel in USER_SUBSTANCE_CHANNELS
                if domain_contributions.get(channel.name, 0.0) <= 0.0
            ]
        )

        avg_substance = knowledge_analysis["avg_substance"]
        if avg_substance < APPLIED_THRESHOLD:
            recommendations.append(
                "Overall alignment is low - focus on applying Life Path knowledge daily"
            )
        elif avg_substance >= EMBODIED_THRESHOLD:
            recommendations.append("Excellent alignment! Life Path knowledge is well-practiced")

        if not recommendations:
            recommendations.append("Alignment looks good - keep up the practice!")

        return recommendations
