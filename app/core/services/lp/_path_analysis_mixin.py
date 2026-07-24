"""
Path Analysis Mixin — LpIntelligenceService
===========================================

Directly-implemented path-analysis operations: prerequisite validation,
blocker identification, optimal-path recommendation, knowledge-scope
analysis, and practice-gap detection, plus the two module-level helpers
that serve only this block.

Part of lp_intelligence_service.py decomposition (July 2026).
See: /docs/patterns/SERVICE_DECOMPOSITION_RULE.md
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.constants import LpKnowledgeScopeComplexity
from core.ports.query_types import LpPracticeGap
from core.services.ps.ps_intelligence_service import (
    missing_practice_domains,
    practice_completeness_from_summary,
)
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.type_hints import UserUID
    from core.ports.query_types import (
        LpBlockerAnalysis,
        LpPathRecommendation,
        LpPracticeGapAnalysis,
        LpPrerequisiteValidation,
    )
    from core.services.ps.ps_intelligence_service import PsIntelligenceService


def _structural_complexity_score(total_unique_kus: int, max_prerequisite_depth: int) -> float:
    """Blend a path's KU breadth and prerequisite depth into a 0.0-1.0 score.

    A v1 STRUCTURAL score (see `LpKnowledgeScopeComplexity`): each axis
    saturates, then the two combine by weight. Deliberately uses only graph
    facts — no authored difficulty field, no importance weighting (both
    deferred). Interpreting the raw scope facts belongs here at the service
    layer, not in the measuring backend query.
    """
    c = LpKnowledgeScopeComplexity
    breadth = min(total_unique_kus / c.KU_BREADTH_SATURATION, 1.0)
    depth = min(max_prerequisite_depth / c.PREREQUISITE_DEPTH_SATURATION, 1.0)
    return round(breadth * c.BREADTH_WEIGHT + depth * c.DEPTH_WEIGHT, 4)


def _build_practice_recommendations(total_steps: int, gaps: list[LpPracticeGap]) -> list[str]:
    """Human-facing summary of a path's practice gaps.

    Same shape as the validation/blocker analyses: a headline count plus a
    callout for any step that has no practice at all (the worst case — a pure
    reading step). Empty gaps yields a single "all complete" line.
    """
    if not gaps:
        if total_steps == 0:
            return ["Path has no steps to analyze for practice."]
        return [f"All {total_steps} steps have complete practice opportunities."]

    recommendations = [f"{len(gaps)} of {total_steps} steps lack complete practice opportunities."]
    recommendations.extend(
        f"{gap['step_title']} has no practice at all — add a task or habit."
        for gap in gaps
        if gap["practice_completeness"] == 0.0
    )
    return recommendations


class _PathAnalysisMixin:
    """
    Path validation, blocker, scope, and practice-gap analysis for
    LpIntelligenceService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by LpIntelligenceService.__init__ / BaseAnalyticsService
    backend: Any
    logger: Any
    ps_intelligence: PsIntelligenceService | None

    # ========================================================================
    # VALIDATION OPERATIONS (January 2026 - Consolidated from LpValidationService)
    # ========================================================================

    @with_error_handling("validate_path_prerequisites", error_type="database", uid_param="path_uid")
    async def validate_path_prerequisites(self, path_uid: str) -> Result[LpPrerequisiteValidation]:
        """
        Validate prerequisite ordering in learning path.

        Ensures:
        - Each step's prerequisites are met by earlier steps
        - No circular dependencies
        - Optimal step ordering
        - Knowledge prerequisite alignment

        Args:
            path_uid: Learning path identifier

        Returns:
            Validation results with issues and recommendations
        """
        result = await self.backend.validate_path_prerequisites(path_uid)

        if result.is_error:
            return result

        records = result.value or []
        validations = [r["validation"] for r in records]

        # Analyze validation results
        issues = [v for v in validations if v.get("has_issues")]
        is_valid = len(issues) == 0

        recommendations = []
        if issues:
            recommendations.append("Reorder steps to ensure prerequisites are met")
            for issue in issues[:3]:  # Top 3 issues
                unmet = issue.get("unmet_prerequisites", [])
                recommendations.append(f"Step {issue['sequence']}: Add prerequisites {unmet[:2]}")

        validation_result: LpPrerequisiteValidation = {
            "path_uid": path_uid,
            "is_valid": is_valid,
            "total_steps": len(validations),
            "steps_with_issues": len(issues),
            "issues": issues,
            "recommendations": recommendations,
            "validated_at": datetime.now().isoformat(),
        }

        self.logger.info(
            f"Path validation for {path_uid}: {'VALID' if is_valid else 'INVALID'} ({len(issues)} issues)"
        )
        return Result.ok(validation_result)

    @with_error_handling("identify_path_blockers", error_type="database", uid_param="path_uid")
    async def identify_path_blockers(
        self, path_uid: str, user_uid: UserUID
    ) -> Result[LpBlockerAnalysis]:
        """
        Identify blockers in learning path for a specific user.

        Finds:
        - Steps blocked by unmet prerequisites
        - Knowledge gaps preventing progress
        - Recommended next actions
        - Alternative learning paths

        Args:
            path_uid: Learning path identifier
            user_uid: User identifier

        Returns:
            Blocker analysis with recommendations
        """
        result = await self.backend.identify_path_blockers(path_uid, user_uid)

        if result.is_error:
            return result

        records = result.value or []
        record = records[0] if records else None
        if not record:
            return Result.ok(
                {
                    "recommendations": [],
                    "status": "ready",
                    "blocker_count": 0,
                    "analyzed_at": datetime.now().isoformat(),
                }
            )
        analysis = record["blocker_analysis"]

        # Generate recommendations
        recommendations = []
        first_blocker = analysis.get("first_blocker")

        if first_blocker:
            blocking_prereqs = first_blocker.get("blocking_prerequisites", [])
            if blocking_prereqs:
                recommendations.append(f"Focus on mastering: {blocking_prereqs[0]}")
                recommendations.append(f"This will unblock step {first_blocker['sequence']}")
        else:
            recommendations.append("No blockers - continue with next step!")

        blocked_count = len(analysis.get("blocked_steps", []))

        enhanced_analysis: LpBlockerAnalysis = {
            **analysis,
            "recommendations": recommendations,
            "status": "blocked" if blocked_count > 0 else "ready",
            "blocker_count": blocked_count,
            "analyzed_at": datetime.now().isoformat(),
        }

        self.logger.info(f"Blocker analysis for {path_uid}: {blocked_count} blockers")
        return Result.ok(enhanced_analysis)

    @with_error_handling(
        "get_optimal_path_recommendation", error_type="database", uid_param="user_uid"
    )
    async def get_optimal_path_recommendation(
        self, user_uid: UserUID, goal_domain: str | None = None
    ) -> Result[LpPathRecommendation]:
        """
        Get optimal learning path recommendation for a user.

        Analyzes:
        - User's current knowledge state
        - Available learning paths
        - Prerequisite readiness
        - Goal alignment
        - Estimated completion time

        Args:
            user_uid: User identifier
            goal_domain: Optional domain filter

        Returns:
            Optimal path recommendation
        """
        result = await self.backend.get_optimal_path_recommendations(user_uid, goal_domain)

        if result.is_error:
            return result

        records = result.value or []
        record = records[0] if records else None
        recommendations = record["recommendations"]["recommended_paths"] if record else []

        # Format recommendation
        recommendation: LpPathRecommendation
        if recommendations:
            top_rec = recommendations[0]
            recommendation = {
                "recommended_path_uid": top_rec["path"]["uid"],
                "path_name": top_rec["path"]["name"],
                "readiness_score": top_rec["readiness_score"],
                "estimated_hours": top_rec["estimated_hours"],
                "reason": top_rec["reason"],
                "alternatives": recommendations[1:3],  # Top 3 alternatives
                "recommended_at": datetime.now().isoformat(),
            }
        else:
            recommendation = {
                "recommended_path_uid": None,
                "reason": "No suitable paths found - consider creating a custom path",
                "alternatives": [],
            }

        self.logger.info(
            f"Path recommendation for {user_uid}: {recommendation.get('path_name', 'None')}"
        )
        return Result.ok(recommendation)

    # ========================================================================
    # ANALYSIS OPERATIONS (January 2026 - Consolidated from LpAnalysisService)
    # ========================================================================

    async def analyze_path_knowledge_scope(self, path_uid: str) -> Result[dict[str, Any]]:
        """
        Analyze the knowledge scope of a learning path.

        Aggregates the path's KU coverage from the graph: the distinct KUs it
        teaches across the ``HAS_STEP`` → ``USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU``
        fan-out, how they distribute across steps, and a structural
        ``complexity_score`` blending KU breadth with prerequisite depth.
        Knowledge scope is core LP identity, not an add-on — this fills the
        ``LpOperations`` KNOWLEDGE AGGREGATION contract.

        Backend: LpBackend.get_knowledge_scope_summary + get_all_knowledge_uids.

        Args:
            path_uid: Learning path identifier

        Returns:
            Result[dict]: total_steps, total_unique_kus, kus_per_step,
            max_prerequisite_depth, complexity_score, all_knowledge_uids,
            practice_coverage.
        """
        if not self.backend:
            return Result.fail(
                Errors.system(
                    message="Learning backend not available",
                    operation="analyze_path_knowledge_scope",
                )
            )

        # Existence guard — a nonexistent path is not-found, not empty scope.
        path_result = await self.backend.get(path_uid)
        if path_result.is_error:
            return Result.fail(path_result)
        if not path_result.value:
            return Result.fail(Errors.not_found(resource="learning_path", identifier=path_uid))

        # Backend measures the graph facts; the service interprets them.
        summary_result = await self.backend.get_knowledge_scope_summary(path_uid)
        if summary_result.is_error:
            return Result.fail(summary_result)
        summary = summary_result.value

        uids_result = await self.backend.get_all_knowledge_uids(path_uid)
        if uids_result.is_error:
            return Result.fail(uids_result)

        analysis = {
            **summary,
            "path_uid": path_uid,
            "all_knowledge_uids": sorted(uids_result.value),
            "complexity_score": _structural_complexity_score(
                summary["total_unique_kus"], summary["max_prerequisite_depth"]
            ),
            "practice_coverage": await self._practice_coverage(path_uid),
            "analysis_timestamp": datetime.now().isoformat(),
        }

        self.logger.info(
            f"Knowledge scope analysis for {path_uid}: "
            f"{summary['total_unique_kus']} KUs across {summary['total_steps']} steps"
        )
        return Result.ok(analysis)

    async def _practice_coverage(self, path_uid: str) -> float | None:
        """Path-level mean practice completeness, or None if unavailable.

        Practice coverage is independent of the KU/complexity facts, so it must
        not fail the whole scope: if practice intelligence is unwired or the
        rollup errors, this degrades to None rather than propagating.
        """
        gaps_result = await self.identify_practice_gaps(path_uid)
        if gaps_result.is_error:
            self.logger.warning(
                f"practice_coverage unavailable for {path_uid}: "
                f"{gaps_result.expect_error().message}"
            )
            return None
        return gaps_result.value["overall_practice_coverage"]

    async def identify_practice_gaps(self, path_uid: str) -> Result[LpPracticeGapAnalysis]:
        """Find which steps of a learning path lack complete practice.

        Every step is scored by the canonical PS measure — the fraction of the
        six activity-domain practice edges (``BUILDS_HABIT``, ``ASSIGNS_TASK``,
        ``SCHEDULES_EVENT``, ``SUPPORTS_GOAL``, ``GUIDED_BY_PRINCIPLE``,
        ``INFORMS_CHOICE``) present on it. A step below 1.0 is a *practice gap*:
        the learner can read the concept but has an incomplete set of structured
        ways to embody it. Reuses ``PsIntelligenceService.get_practice_summary``
        per step so LP never forks a competing practice definition (One Path
        Forward); the path-level mean feeds ``practice_coverage`` in
        analyze_path_knowledge_scope.

        Backend: LpBackend.get_steps_raw (ordered steps) +
        PsIntelligenceService per-step practice reads.

        Args:
            path_uid: Learning path identifier

        Returns:
            Result[LpPracticeGapAnalysis]: total_steps, steps_with_gaps,
            overall_practice_coverage, gaps, recommendations.
        """
        if not self.backend:
            return Result.fail(
                Errors.system(
                    message="Learning backend not available",
                    operation="identify_practice_gaps",
                )
            )
        if self.ps_intelligence is None:
            return Result.fail(
                Errors.system(
                    message="PathStep intelligence not available for practice analysis",
                    operation="identify_practice_gaps",
                )
            )

        # Existence guard — a nonexistent path is not-found, not empty gaps.
        path_result = await self.backend.get(path_uid)
        if path_result.is_error:
            return Result.fail(path_result)
        if not path_result.value:
            return Result.fail(Errors.not_found(resource="learning_path", identifier=path_uid))

        steps_result = await self.backend.get_steps_raw(path_uid)
        if steps_result.is_error:
            return Result.fail(steps_result)
        steps = steps_result.value or []

        gaps: list[LpPracticeGap] = []
        completeness_scores: list[float] = []
        for step in steps:
            summary_result = await self.ps_intelligence.get_practice_summary(step.uid)
            if summary_result.is_error:
                return Result.fail(summary_result)
            summary = summary_result.value

            completeness = practice_completeness_from_summary(summary)
            completeness_scores.append(completeness)
            if completeness < 1.0:
                gaps.append(
                    LpPracticeGap(
                        step_uid=step.uid,
                        step_title=step.title or step.uid,
                        practice_completeness=round(completeness, 4),
                        missing_types=missing_practice_domains(summary),
                    )
                )

        overall = (
            round(sum(completeness_scores) / len(completeness_scores), 4)
            if completeness_scores
            else 0.0
        )

        analysis: LpPracticeGapAnalysis = {
            "path_uid": path_uid,
            "total_steps": len(steps),
            "steps_with_gaps": len(gaps),
            "overall_practice_coverage": overall,
            "gaps": gaps,
            "recommendations": _build_practice_recommendations(len(steps), gaps),
            "analysis_timestamp": datetime.now().isoformat(),
        }

        self.logger.info(
            f"Practice gap analysis for {path_uid}: "
            f"{len(gaps)}/{len(steps)} steps with practice gaps"
        )
        return Result.ok(analysis)
