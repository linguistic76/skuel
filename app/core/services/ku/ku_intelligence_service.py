"""
Ku Intelligence Service
========================

Intelligence service for atomic Knowledge Units — graph analytics, no AI.

Provides:
- Graph context retrieval (get_with_context)
- Performance analytics (get_performance_analytics)
- Domain insights (get_domain_insights)
- Usage summary (path steps using, path steps training, organized children)
- Organization depth (ORGANIZES tree traversal)

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.enums import MasteryLevel
from core.models.ku.ku import Ku
from core.models.shared.dual_track import DualTrackResult
from core.models.type_hints import UserUID
from core.ports.query_types import KuUserSubstanceResult
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.intelligence import _CoreIntelligenceMixin
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from core.ports import BackendOperations
    from core.services.user import UserContext

logger = get_logger(__name__)


class KuIntelligenceService(
    _CoreIntelligenceMixin[Ku],
    BaseAnalyticsService["BackendOperations[Ku]", "Ku"],
):
    """
    Intelligence service for atomic Knowledge Units.

    Extends BaseAnalyticsService (ADR-030) — NO AI dependencies.
    Pure graph queries and Python calculations.

    Provides:
    - Usage analysis: how many path steps reference this Ku (USES_KU, TRAINS_KU)
    - Organization analysis: ORGANIZES tree depth and child count
    - Existence checks: is_trained, is_organized
    """

    _service_name = "ku.intelligence"

    def __init__(
        self,
        backend: BackendOperations[Ku],
        graph_intel: Any | None = None,
        relationship_service: Any | None = None,
        event_bus: Any | None = None,
    ) -> None:
        super().__init__(
            backend=backend,
            graph_intel=graph_intel,
            relationship_service=relationship_service,
            event_bus=event_bus,
        )

    # ========================================================================
    # INTELLIGENCEOPERATIONS PROTOCOL METHODS
    # `get_with_context()` is inherited from `_CoreIntelligenceMixin[Ku]` —
    # mechanism B (registry-sourced), typed return.
    # ========================================================================

    async def get_performance_analytics(
        self, user_uid: UserUID, period_days: int = 30
    ) -> Result[dict[str, Any]]:
        """Get overall Ku statistics (shared content, not user-specific)."""
        ku_result = await self.backend.find_by()
        if ku_result.is_error:
            return Result.fail(ku_result)

        all_kus = ku_result.value or []
        total = len(all_kus)

        # Count by NOUS topic (multi-topic: a Ku counts once per topic;
        # empty nous = deliberately unassigned, rawness principle)
        topics: dict[str, int] = {}
        for ku in all_kus:
            ku_topics = getattr(ku, "nous", ()) or ("unassigned",)
            for topic in ku_topics:
                topics[topic] = topics.get(topic, 0) + 1

        return Result.ok(
            {
                "user_uid": user_uid,
                "period_days": period_days,
                "total_kus": total,
                "by_nous": topics,
                "analytics": {
                    "total": total,
                    "note": "Kus are shared curriculum content",
                },
            }
        )

    async def get_domain_insights(
        self, uid: str, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        """Get domain-specific insights for a Ku."""
        ku_result = await self.backend.get(uid)
        if ku_result.is_error:
            return Result.fail(ku_result)

        ku = ku_result.value
        if not ku:
            return Result.fail(Errors.not_found(resource="Ku", identifier=uid))

        usage_result = await self.get_usage_summary(uid)
        usage = usage_result.value if usage_result.is_ok else {}

        depth_result = await self.get_organization_depth(uid)
        org_depth = depth_result.value if depth_result.is_ok else 0

        return Result.ok(
            {
                "ku_uid": uid,
                "ku_title": ku.title,
                "alias_count": len(ku.aliases),
                "usage": usage,
                "organization_depth": org_depth,
                "min_confidence": min_confidence,
            }
        )

    # ========================================================================
    # DOMAIN-SPECIFIC METHODS
    # ========================================================================

    @with_error_handling("get_usage_summary", error_type="database", uid_param="ku_uid")
    async def get_usage_summary(self, ku_uid: str) -> Result[dict[str, int]]:
        """Count path steps using (USES_KU), training (TRAINS_KU), and organized children (ORGANIZES)."""
        result = await self.backend.get_usage_summary(ku_uid)  # type: ignore[attr-defined]
        if result.is_error:
            return Result.fail(result)

        records = result.value or []
        if not records:
            return Result.ok(
                {"path_steps_using": 0, "path_steps_training": 0, "organized_children": 0}
            )

        row = records[0]
        return Result.ok(
            {
                "path_steps_using": row.get("path_steps_using", 0),
                "path_steps_training": row.get("path_steps_training", 0),
                "organized_children": row.get("organized_children", 0),
            }
        )

    @with_error_handling("is_trained", error_type="database", uid_param="ku_uid")
    async def is_trained(self, ku_uid: str) -> Result[bool]:
        """Check if any Learning Step trains this Ku via TRAINS_KU."""
        result = await self.backend.is_trained(ku_uid)  # type: ignore[attr-defined]
        if result.is_error:
            return Result.fail(result)

        records = result.value or []
        return Result.ok(records[0].get("trained", False) if records else False)

    @with_error_handling("is_organized", error_type="database", uid_param="ku_uid")
    async def is_organized(self, ku_uid: str) -> Result[bool]:
        """Check if this Ku has ORGANIZES children (acts as MOC)."""
        result = await self.backend.is_organized(ku_uid)  # type: ignore[attr-defined]
        if result.is_error:
            return Result.fail(result)

        records = result.value or []
        return Result.ok(records[0].get("organized", False) if records else False)

    async def calculate_user_substance(
        self, ku_uid: str, user_context: UserContext
    ) -> Result[KuUserSubstanceResult]:
        """Calculate how much a user has applied a Ku's knowledge in their life.

        Reads activity channel data from UserContext and applies Knowledge Substance
        Philosophy weights to produce a per-user substance score for this Ku.

        Weights (from CLAUDE.md Knowledge Substance Philosophy):
        - Habits: 0.10 per habit, max 0.30 (lifestyle integration)
        - Entries: 0.07 per reflective entry, max 0.20 (metacognition — ADR-069)
        - Choices: 0.07 per choice, max 0.15 (decision-making)
        - Principles: 0.07 per principle, max 0.15 (value embodiment)
        - Events: 0.05 per event, max 0.25 (dedicated practice)
        - Tasks: 0.05 per task, max 0.25 (practical application)

        See: /docs/architecture/knowledge_substance_philosophy.md
        """
        # Fetch Ku for global substance score and mastery state
        ku_result = await self.backend.get(ku_uid)
        if ku_result.is_error:
            return Result.fail(ku_result)

        ku = ku_result.value
        if not ku:
            return Result.fail(Errors.not_found(resource="Ku", identifier=ku_uid))

        # Count activity associations per channel from UserContext
        task_uids = [
            uid for uid, ku_list in user_context.task_knowledge_applied.items() if ku_uid in ku_list
        ]
        habit_uids = [
            uid
            for uid, ku_list in user_context.habit_knowledge_applied.items()
            if ku_uid in ku_list
        ]
        event_uids = [
            uid
            for uid, ku_list in user_context.event_knowledge_applied.items()
            if ku_uid in ku_list
        ]
        choice_uids = [
            uid
            for uid, ku_list in user_context.choice_knowledge_informed.items()
            if ku_uid in ku_list
        ]
        principle_uids = [
            uid
            for uid, ku_list in user_context.principle_knowledge_grounded.items()
            if ku_uid in ku_list
        ]
        entry_uids = [
            uid
            for uid, ku_list in user_context.entry_knowledge_applied.items()
            if ku_uid in ku_list
        ]

        # Apply Knowledge Substance Philosophy weights with per-channel caps
        task_score = min(0.25, len(task_uids) * 0.05)
        habit_score = min(0.30, len(habit_uids) * 0.10)
        event_score = min(0.25, len(event_uids) * 0.05)
        entry_score = min(0.20, len(entry_uids) * 0.07)
        choice_score = min(0.15, len(choice_uids) * 0.07)
        principle_score = min(0.15, len(principle_uids) * 0.07)

        user_substance_score = min(
            1.0,
            task_score + habit_score + event_score + entry_score + choice_score + principle_score,
        )

        breakdown = {
            "tasks": round(task_score, 3),
            "habits": round(habit_score, 3),
            "events": round(event_score, 3),
            "entries": round(entry_score, 3),
            "choices": round(choice_score, 3),
            "principles": round(principle_score, 3),
        }

        # Global substance score from the Ku node itself
        global_substance_score: float | None = getattr(ku, "substance_score", None)
        if callable(global_substance_score):
            global_substance_score = global_substance_score()

        # Mastery level from UserContext (0.0-1.0 float from [:MASTERED] relationships)
        mastery_score = user_context.knowledge_mastery.get(ku_uid, 0.0)
        if mastery_score >= 0.8:
            mastery_level = "mastered"
        elif mastery_score >= 0.5:
            mastery_level = "in_progress"
        elif mastery_score > 0.0:
            mastery_level = "started"
        else:
            mastery_level = "unstarted"

        # Readiness: meaningful engagement in at least one channel
        is_ready_to_learn = user_substance_score >= 0.05

        # Per-channel recommendations for empty channels
        recommendations: list[str] = []
        if not task_uids:
            recommendations.append(f"Create a task that applies '{ku.title}' in your work")
        if not habit_uids:
            recommendations.append(f"Build a habit that reinforces '{ku.title}' daily")
        if not event_uids:
            recommendations.append(f"Schedule a practice session to deepen '{ku.title}'")
        if not choice_uids:
            recommendations.append(f"Record a choice informed by '{ku.title}'")
        if not principle_uids:
            recommendations.append(f"Write a principle grounded in '{ku.title}'")
        if not entry_uids:
            recommendations.append(f"Write an entry reflecting on '{ku.title}'")

        # Status message based on score range
        if user_substance_score >= 0.7:
            status_message = "Deep integration — this knowledge is woven into your life"
        elif user_substance_score >= 0.4:
            status_message = "Active engagement — you are applying this knowledge regularly"
        elif user_substance_score >= 0.1:
            status_message = "Beginning to apply — keep connecting this to your activities"
        else:
            status_message = "Theoretical only — try applying this knowledge in daily life"

        result: KuUserSubstanceResult = {
            "user_substance_score": round(user_substance_score, 3),
            "global_substance_score": (
                round(float(global_substance_score), 3)
                if global_substance_score is not None
                else None
            ),
            "breakdown": breakdown,
            "mastery_level": mastery_level,
            "is_ready_to_learn": is_ready_to_learn,
            "recommendations": recommendations[:3],
            "status_message": status_message,
        }
        return Result.ok(result)

    # ========================================================================
    # DUAL-TRACK: KNOWLEDGE MASTERY (ADR-030)
    # ========================================================================

    async def assess_mastery_dual_track(
        self,
        user_uid: UserUID,
        ku_uid: str,
        user_level: MasteryLevel,
        user_evidence: str,
        user_context: UserContext,
        user_reflection: str | None = None,
        store_callback: (
            Callable[[str, DualTrackResult[MasteryLevel]], Awaitable[None]] | None
        ) = None,
    ) -> Result[DualTrackResult[MasteryLevel]]:
        """Dual-track mastery assessment for a Ku (ADR-030 — Knowledge dimension).

        Compares the user's self-rated mastery (``MasteryLevel``) with the
        system-measured **substance score** — how much they have actually applied
        this Ku across their life (``calculate_user_substance``) — to surface the
        perception gap ("I've mastered this" vs the lived evidence).

        Unlike the per-entity dimensions (Goals/Habits/Principles), a Ku is SHARED/
        public curriculum, so this is per-(user, Ku): ``user_context`` supplies the
        user's activity→Ku channels the substance score is computed from, and the
        check-in persists per-user (keyed by ``ku_uid``) via ``store_callback``, not
        on the shared ``:Ku`` node.

        Args:
            user_uid: The user making the assessment.
            ku_uid: The Ku being self-rated.
            user_level: User's self-reported mastery level.
            user_evidence: User's evidence for the rating (free text).
            user_context: The user's built context — source of the substance score.
            user_reflection: Optional reflection.
            store_callback: Optional ``(ku_uid, result)`` persistence hook
                (Ku detail route binds ``UserService.append_knowledge_checkin``).

        Returns:
            Result[DualTrackResult[MasteryLevel]] — the perception-gap result.
        """

        async def _system_calculator(
            _entity: Any, _user_uid: str
        ) -> tuple[MasteryLevel, float, list[str]]:
            """System side: substance score → (MasteryLevel, score, evidence)."""
            sub_result = await self.calculate_user_substance(ku_uid, user_context)
            if sub_result.is_error:
                # Surface the failure through the template's safety-net, which converts
                # it to a Result.fail (propagate, don't silently degrade to score=0).
                raise RuntimeError(sub_result.expect_error().message)
            sub = sub_result.value
            score = float(sub["user_substance_score"])
            evidence: list[str] = [sub["status_message"]]
            evidence.extend(
                f"{channel.title()} applied: {contribution:.0%}"
                for channel, contribution in sub["breakdown"].items()
                if contribution > 0
            )
            return MasteryLevel.from_score(score), score, evidence

        return await self._dual_track_assessment(
            uid=ku_uid,
            user_uid=user_uid,
            user_level=user_level,
            user_evidence=user_evidence,
            user_reflection=user_reflection,
            system_calculator=_system_calculator,
            level_scorer=MasteryLevel.to_score,
            entity_type="ku",
            require_entity=True,
            store_callback=store_callback,
        )

    @with_error_handling("get_organization_depth", error_type="database", uid_param="ku_uid")
    async def get_organization_depth(self, ku_uid: str) -> Result[int]:
        """Get depth of the ORGANIZES tree below this Ku."""
        result = await self.backend.get_organization_depth(ku_uid)  # type: ignore[attr-defined]
        if result.is_error:
            return Result.fail(result)

        records = result.value or []
        if not records or records[0].get("max_depth") is None:
            return Result.ok(0)

        return Result.ok(records[0]["max_depth"])
