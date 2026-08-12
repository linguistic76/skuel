"""
PathStep Intelligence Service
===============================

Intelligence service for PathSteps - scoring, readiness, practice calculations.

**January 2026 - Unified Architecture:**
This service follows the Activity Domain pattern, extending BaseIntelligenceService.
Complex scoring and aggregation methods consolidated here from the former PsRelationshipService.

Methods:
- is_ready(): Check if step is ready based on prerequisite completion
- get_practice_summary(): Get practice opportunity counts
- practice_completeness_score(): Calculate practice completeness (0.0-1.0)
- calculate_guidance_strength(): Calculate guidance strength (0.0-1.0)
- has_prerequisites(): Check if step has prerequisites
- has_guidance(): Check if step has guidance
- has_practice_opportunities(): Check if step has practice opportunities

Architecture:
- Extends BaseAnalyticsService[BackendOperations[PathStep], PathStep]
- Uses direct Cypher for complex aggregation queries
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, Final, cast

from core.models.pathways.path_step import PathStep
from core.models.type_hints import UserUID
from core.ports.query_types import (
    PsDomainInsights,
    PsGuidanceCountsRow,
    PsPerformanceAnalytics,
    PsPracticeCountsRow,
    PsPracticeSummaryResult,
)
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.intelligence import _CoreIntelligenceMixin
from core.services.knowledge.user_substance import (
    SubstanceIndex,
    build_substance_index,
    build_substance_index_from_context,
    user_substance_score,
)
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports import BackendOperations, PsIntelligenceBackendOperations
    from core.services.user.unified_user_context import UserContext

logger = get_logger(__name__)


# The six activity-domain practice edges a PathStep can carry (the keys
# get_practice_summary returns, minus the derived ``total``). A step with all six
# present has "complete" practice; each contributes an equal 1/6 to completeness.
# This is the single source of truth for "what counts as practice" — reused by
# the PS per-step scorer AND LpIntelligenceService.identify_practice_gaps, so the
# two never fork competing definitions (One Path Forward).
PRACTICE_DOMAINS: Final = ("habits", "tasks", "events", "goals", "principles", "choices")


def _practice_counts(summary: PsPracticeSummaryResult) -> Mapping[str, int]:
    """View a practice summary as its underlying str→int count map.

    A summary IS a str→int mapping at runtime; the TypedDict is just a stricter
    view. Casting once lets the six domains be indexed by their runtime names
    (PRACTICE_DOMAINS) without a per-key string literal.
    """
    return cast("Mapping[str, int]", summary)


def practice_completeness_from_summary(summary: PsPracticeSummaryResult) -> float:
    """Fraction of the six practice domains present on a step (0.0-1.0).

    Pure computation over an already-fetched practice summary — lets a caller
    that already holds the summary (e.g. an LP-level rollup deriving both the
    score and the missing types) avoid re-running the count query.
    """
    counts = _practice_counts(summary)
    present = sum(1 for domain in PRACTICE_DOMAINS if counts[domain] > 0)
    return present / len(PRACTICE_DOMAINS)


def missing_practice_domains(summary: PsPracticeSummaryResult) -> list[str]:
    """The practice domains absent on a step, in canonical PRACTICE_DOMAINS order."""
    counts = _practice_counts(summary)
    return [domain for domain in PRACTICE_DOMAINS if counts[domain] == 0]


class PsIntelligenceService(
    _CoreIntelligenceMixin[PathStep],
    BaseAnalyticsService["BackendOperations[PathStep]", "PathStep"],
):
    """
    Intelligence service for PathSteps.

    NOTE: This service extends BaseAnalyticsService (ADR-030) and has NO AI dependencies.
    It uses pure graph queries and Python calculations - no LLM or embeddings.

    Provides:
    - Readiness assessment based on prerequisites
    - Practice opportunity analysis
    - Guidance strength calculation
    - Practice completeness scoring

    These methods require complex graph queries that don't fit the
    generic UnifiedRelationshipService pattern.
    """

    _service_name = "ps.intelligence"

    def __init__(
        self,
        backend: BackendOperations[PathStep],
        graph_intel: Any | None = None,
        relationship_service: Any | None = None,
        event_bus: Any | None = None,
        intelligence_backend: PsIntelligenceBackendOperations | None = None,
    ) -> None:
        """
        Initialize PsIntelligenceService.

        NOTE: No embeddings_service or llm_service parameters (ADR-030).
        """
        super().__init__(
            backend=backend,
            graph_intel=graph_intel,
            relationship_service=relationship_service,
            event_bus=event_bus,
        )

        # The executor-backed PsIntelligenceBackend (whose Cypher lives below the
        # boundary, ADR-044) is built at the composition root and injected — this
        # service never imports the adapter (SKUEL022). The executor is
        # encapsulated inside the backend; backend presence is the readiness gate.
        self._backend = intelligence_backend

    # ========================================================================
    # INTELLIGENCEOPERATIONS PROTOCOL METHODS (January 2026)
    # These methods implement the IntelligenceOperations protocol for use
    # with IntelligenceRouteFactory. `get_with_context()` is inherited from
    # `_CoreIntelligenceMixin[PathStep]` — typed return, one delegation.
    # ========================================================================

    async def get_performance_analytics(
        self, user_uid: UserUID, period_days: int = 30
    ) -> Result[PsPerformanceAnalytics]:
        """
        Get path step analytics for a user.

        Protocol method: Aggregates path step metrics.
        Used by IntelligenceRouteFactory for GET /api/path-steps/analytics route.

        Args:
            user_uid: User UID
            period_days: Number of days to analyze (default: 30)

        Returns:
            Result containing analytics data dict

        Note: PathSteps are shared curriculum content (no user ownership).
        This returns overall PS statistics rather than user-specific data.
        """
        # PS is shared content - get overall stats
        ps_result = await self.backend.find_by()
        if ps_result.is_error:
            return Result.fail(ps_result)

        all_steps = ps_result.value or []
        total_steps = len(all_steps)

        return Result.ok(
            {
                "user_uid": user_uid,
                "period_days": period_days,
                "total_path_steps": total_steps,
                "analytics": {
                    "total": total_steps,
                    "note": "PathSteps are shared curriculum content",
                },
            }
        )

    async def get_domain_insights(
        self, uid: str, min_confidence: float = 0.7
    ) -> Result[PsDomainInsights]:
        """
        Get domain-specific insights for a path step.

        Protocol method: Provides PS-specific intelligence.
        Used by IntelligenceRouteFactory for GET /api/path-steps/insights route.

        Args:
            uid: Learning Step UID
            min_confidence: Minimum confidence threshold (default: 0.7)

        Returns:
            Result containing insights data dict with practice analysis
        """
        # Get path step
        ps_result = await self.backend.get(uid)
        if ps_result.is_error:
            return Result.fail(ps_result)

        ps = ps_result.value
        if not ps:
            return Result.fail(Errors.not_found(resource="PathStep", identifier=uid))

        # Get practice summary
        practice_result = await self.get_practice_summary(uid)
        practice: PsPracticeSummaryResult = (
            practice_result.value
            if practice_result.is_ok
            else {
                "habits": 0,
                "tasks": 0,
                "events": 0,
                "goals": 0,
                "principles": 0,
                "choices": 0,
                "total": 0,
            }
        )

        # Get practice completeness score
        completeness_result = await self.practice_completeness_score(uid)
        completeness = completeness_result.value if completeness_result.is_ok else 0.0

        # Check for prerequisites
        has_prereqs_result = await self.has_prerequisites(uid)
        has_prerequisites = has_prereqs_result.value if has_prereqs_result.is_ok else False

        return Result.ok(
            {
                "ps_uid": uid,
                "ps_title": ps.title,
                "ps_intent": getattr(ps, "intent", None),
                "practice_summary": practice,
                "practice_completeness": completeness,
                "has_prerequisites": has_prerequisites,
                "min_confidence": min_confidence,
            }
        )

    def _require_backend(self) -> Result[PsIntelligenceBackendOperations]:
        """Fail-fast guard for backend (executor) availability."""
        if self._backend is None:
            return Result.fail(
                Errors.system(
                    message="GraphQueryExecutor not initialized - backend driver required",
                    operation="require_executor",
                )
            )
        return Result.ok(self._backend)

    # ========================================================================
    # READINESS ASSESSMENT
    # ========================================================================

    @with_error_handling("is_ready", error_type="database", uid_param="ps_uid")
    async def is_ready(self, ps_uid: str, completed_step_uids: set[str]) -> Result[bool]:
        """
        Check if path step is ready based on prerequisite completion.

        A step is ready when ALL its prerequisite steps (via REQUIRES_STEP
        relationship) have been completed.

        Args:
            ps_uid: UID of the path step
            completed_step_uids: Set of completed step UIDs

        Returns:
            Result[bool] - True if all prerequisites are met

        Example:
            result = await intelligence.is_ready(
                "ps:functions",
                {"ps:intro", "ps:syntax"}
            )
            if result.is_ok and result.value:
                print("Ready to learn functions!")
        """
        backend_result = self._require_backend()
        if backend_result.is_error:
            return Result.fail(backend_result)

        records_result = await backend_result.value.fetch_prerequisite_step_uids(ps_uid)
        if records_result.is_error:
            return Result.fail(records_result)

        records = records_result.value
        if not records:
            return Result.ok(True)  # No prerequisites = ready
        prereq_uids = set(records[0].get("prereq_uids") or [])
        return Result.ok(prereq_uids.issubset(completed_step_uids))

    # ========================================================================
    # PRACTICE ANALYSIS
    # ========================================================================

    @with_error_handling("get_practice_summary", error_type="database", uid_param="ps_uid")
    async def get_practice_summary(self, ps_uid: str) -> Result[PsPracticeSummaryResult]:
        """
        Get summary of practice opportunities for a path step.

        Counts all 6 activity
        domains: habits, tasks, events, goals, principles, choices.

        Args:
            ps_uid: UID of the path step

        Returns:
            Result[dict] with structure:
            {"habits": int, "tasks": int, "events": int,
             "goals": int, "principles": int, "choices": int, "total": int}

        Example:
            result = await intelligence.get_practice_summary("ps:functions")
            if result.is_ok:
                print(f"Total practice: {result.value['total']} items")
        """
        backend_result = self._require_backend()
        if backend_result.is_error:
            return Result.fail(backend_result)

        def _process_summary(records: list[PsPracticeCountsRow]) -> PsPracticeSummaryResult:
            if not records:
                return PsPracticeSummaryResult(
                    habits=0,
                    tasks=0,
                    events=0,
                    goals=0,
                    principles=0,
                    choices=0,
                    total=0,
                )

            habits = records[0].get("habits", 0)
            tasks = records[0].get("tasks", 0)
            events = records[0].get("events", 0)
            goals = records[0].get("goals", 0)
            principles = records[0].get("principles", 0)
            choices = records[0].get("choices", 0)
            total = habits + tasks + events + goals + principles + choices

            return PsPracticeSummaryResult(
                habits=habits,
                tasks=tasks,
                events=events,
                goals=goals,
                principles=principles,
                choices=choices,
                total=total,
            )

        counts_result = await backend_result.value.fetch_practice_counts(ps_uid)
        if counts_result.is_error:
            return Result.fail(counts_result)
        return Result.ok(_process_summary(counts_result.value))

    @with_error_handling("practice_completeness_score", error_type="database", uid_param="ps_uid")
    async def practice_completeness_score(self, ps_uid: str) -> Result[float]:
        """
        Calculate practice completeness (0.0-1.0).

        Full practice suite (all 6 activity domains) = 1.0.
        Each domain contributes 1/6 of the score.

        Args:
            ps_uid: UID of the path step

        Returns:
            Result[float] - Practice completeness score (0.0 to 1.0)

        Example:
            result = await intelligence.practice_completeness_score("ps:functions")
            if result.is_ok:
                print(f"Practice completeness: {result.value:.0%}")
        """
        summary_result = await self.get_practice_summary(ps_uid)
        if summary_result.is_error:
            return Result.fail(summary_result)

        return Result.ok(practice_completeness_from_summary(summary_result.value))

    # ========================================================================
    # GUIDANCE ANALYSIS
    # ========================================================================

    @with_error_handling("calculate_guidance_strength", error_type="database", uid_param="ps_uid")
    async def calculate_guidance_strength(self, ps_uid: str) -> Result[float]:
        """
        Calculate how well this step guides the learner (0.0-1.0).

        Scoring:
        - Principles provide values-based guidance (40% max)
        - Choices provide inspiration and options (60% max)

        Args:
            ps_uid: UID of the path step

        Returns:
            Result[float] - Guidance strength score (0.0 to 1.0)

        Example:
            result = await intelligence.calculate_guidance_strength("ps:functions")
            if result.is_ok:
                print(f"Guidance strength: {result.value:.0%}")
        """
        backend_result = self._require_backend()
        if backend_result.is_error:
            return Result.fail(backend_result)

        def _calculate_score(records: list[PsGuidanceCountsRow]) -> float:
            if not records:
                return 0.0

            principle_count = records[0].get("principle_count", 0)
            choice_count = records[0].get("choice_count", 0)

            score = 0.0

            # Principles provide values-based guidance (40% max)
            if principle_count > 0:
                score += min(0.4, principle_count * 0.15)

            # Choices provide inspiration and options (60% max)
            if choice_count > 0:
                score += min(0.6, choice_count * 0.2)

            return min(1.0, score)

        counts_result = await backend_result.value.fetch_guidance_counts(ps_uid)
        if counts_result.is_error:
            return Result.fail(counts_result)
        return Result.ok(_calculate_score(counts_result.value))

    # ========================================================================
    # EXISTENCE CHECKS (Compound)
    # ========================================================================

    @with_error_handling("has_prerequisites", error_type="database", uid_param="ps_uid")
    async def has_prerequisites(self, ps_uid: str) -> Result[bool]:
        """
        Check if path step has any prerequisites.

        Checks for both:
        - REQUIRES_STEP relationships (other steps)
        - REQUIRES_KNOWLEDGE relationships (KU prerequisites)

        Args:
            ps_uid: UID of the path step

        Returns:
            Result[bool] - True if step has prerequisites

        Example:
            result = await intelligence.has_prerequisites("ps:functions")
            if result.is_ok and result.value:
                print("This step has prerequisites")
        """
        if self._backend is None:
            return Result.fail(
                Errors.system(message="Query executor not available", operation="has_prerequisites")
            )

        return await self._backend.has_prerequisites(ps_uid)

    @with_error_handling("has_guidance", error_type="database", uid_param="ps_uid")
    async def has_guidance(self, ps_uid: str) -> Result[bool]:
        """
        Check if path step has guidance (principles or choices).

        Checks direct activity domain relationships.

        Args:
            ps_uid: UID of the path step

        Returns:
            Result[bool] - True if step has guidance

        Example:
            result = await intelligence.has_guidance("ps:functions")
            if result.is_ok and result.value:
                print("This step has guidance")
        """
        if self._backend is None:
            return Result.fail(
                Errors.system(message="Query executor not available", operation="has_guidance")
            )

        return await self._backend.has_guidance(ps_uid)

    @with_error_handling("has_practice_opportunities", error_type="database", uid_param="ps_uid")
    async def has_practice_opportunities(self, ps_uid: str) -> Result[bool]:
        """
        Check if path step has practice opportunities.

        Checks all 6 activity domain relationships.

        Args:
            ps_uid: UID of the path step

        Returns:
            Result[bool] - True if step has practice opportunities

        Example:
            result = await intelligence.has_practice_opportunities("ps:functions")
            if result.is_ok and result.value:
                print("This step has practice opportunities")
        """
        if self._backend is None:
            return Result.fail(
                Errors.system(
                    message="Query executor not available",
                    operation="has_practice_opportunities",
                )
            )

        return await self._backend.has_practice_opportunities(ps_uid)

    # ========================================================================
    # USER SUBSTANCE & CONTEXTUAL EVALUATION (Migrated Jan 2026)
    # ========================================================================

    @staticmethod
    def _mean_ku_substance(ku_uids: Sequence[str], index: SubstanceIndex) -> float:
        """A step's personal substance: the mean over the Kus it teaches.

        A step teaching no Ku scores 0.0 rather than being undefined — it is a
        step the learner cannot have substantiated through any channel, which is
        the same statement the score already makes for a step whose Kus the
        learner has never applied.
        """
        if not ku_uids:
            return 0.0
        return sum(user_substance_score(ku_uid, index) for ku_uid in ku_uids) / len(ku_uids)

    async def calculate_user_substance(
        self, ps_uid: str, user_context: UserContext
    ) -> Result[dict[str, Any]]:
        """
        Calculate how much a user has applied the knowledge taught by this PathStep.

        PathSteps are curriculum entities; their "substance" is derived by analyzing
        the user's application of the underlying atomic Knowledge Units (via USES_KU).

        Requires a RICH context — see the note on
        ``KuIntelligenceService.calculate_user_substance``: the standard build
        leaves the six channel maps empty, which scores every step a flat 0.0.
        """
        backend_result = self._require_backend()
        if backend_result.is_error:
            return Result.fail(backend_result)

        # 1. Find all KUs taught by this PathStep
        ku_rows_result = await backend_result.value.fetch_taught_ku_uids(ps_uid)
        if ku_rows_result.is_error:
            return Result.fail(ku_rows_result)

        ku_uids = [r["ku_uid"] for r in ku_rows_result.value if r.get("ku_uid")]

        # 2. Score each taught KU against the learner's own activity channels.
        #    The weights come from core.services.knowledge.user_substance — the
        #    single table this, KuIntelligenceService and the Layer-0 analytics
        #    metric all read, so they cannot drift apart.
        index = build_substance_index_from_context(user_context)
        total_substance = 0.0
        total_mastery = 0.0
        ku_details = []

        for ku_uid in ku_uids:
            substance = user_substance_score(ku_uid, index)
            mastery_score = user_context.knowledge_mastery.get(ku_uid, 0.0)

            total_substance += substance
            total_mastery += mastery_score
            ku_details.append(
                {
                    "ku_uid": ku_uid,
                    "substance_score": round(substance, 3),
                    "mastery_score": round(mastery_score, 3),
                    "is_ready_to_learn": ku_uid
                    in getattr(user_context, "ready_to_learn_uids", set()),
                }
            )

        avg_substance = total_substance / len(ku_uids) if ku_uids else 0.0
        avg_mastery = total_mastery / len(ku_uids) if ku_uids else 0.0

        is_ready = bool(ku_uids and all(ku["is_ready_to_learn"] for ku in ku_details))

        if avg_substance >= 0.7:
            status = "Deeply integrated in your lifestyle."
        elif avg_substance >= 0.4:
            status = "Actively applying these concepts."
        elif avg_substance > 0:
            status = "Starting to practice this material."
        else:
            status = "Theoretical only — apply this in practice."

        return Result.ok(
            {
                "ps_uid": ps_uid,
                "user_uid": user_context.user_uid,
                "overall_substance_score": round(avg_substance, 3),
                "overall_mastery_score": round(avg_mastery, 3),
                "is_ready_to_learn": is_ready,
                "taught_kus_count": len(ku_uids),
                "underlying_kus": ku_details,
                "status_message": status,
            }
        )

    async def calculate_user_substance_for_steps(
        self, ps_uids: Sequence[str], channels: Mapping[str, Mapping[str, Sequence[str]]]
    ) -> Result[dict[str, float]]:
        """Personal substance score for many PathSteps — one round trip.

        The aggregate form of :meth:`calculate_user_substance`, returning score
        only. An aggregate over a learner's engagement window can hold hundreds
        of steps, and the per-step method issues a query each; this resolves the
        whole step→Ku composition in one read and does the rest in Python.

        Every requested uid appears in the result. A step that teaches no Ku,
        or whose Kus the learner has never applied, maps to 0.0 — a real reading
        ("theoretical for me"), not a gap for the caller to guess at, so callers
        can index the result directly rather than defaulting a miss.

        Takes the six channel maps rather than a ``UserContext`` because the
        caller chooses the temporal semantics, and for an aggregate the answer is
        the UNWINDOWED source (``get_user_knowledge_channels``); a context's maps
        are window-bounded, which understates a cumulative figure. The per-step
        form keeps the context because a detail page already holds one.

        Backend: PsIntelligenceBackend.fetch_taught_ku_uids_for_steps
        """
        if not ps_uids:
            return Result.ok({})

        backend_result = self._require_backend()
        if backend_result.is_error:
            return Result.fail(backend_result)

        rows_result = await backend_result.value.fetch_taught_ku_uids_for_steps(list(ps_uids))
        if rows_result.is_error:
            return Result.fail(rows_result)

        taught: dict[str, list[str]] = {row["ps_uid"]: row["ku_uids"] for row in rows_result.value}
        index = build_substance_index(channels)
        # UNROUNDED. The caller bands these against 0.3 / 0.5 / 0.6 / 0.8 before
        # rendering anything, and a step composing enough Kus can have a mean
        # that rounds across a band it does not actually sit in — 20 Kus at 0.30
        # and one at 0.29 average 0.2995, which is theoretical, but rounds to
        # the 0.30 that reads as applied. Presentation rounds; scoring does not.
        return Result.ok(
            {ps_uid: self._mean_ku_substance(taught.get(ps_uid, []), index) for ps_uid in ps_uids}
        )
