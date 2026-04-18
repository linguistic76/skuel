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

from core.models.enums import Domain
from core.models.ku.ku import Ku
from core.models.ku.ku_dto import KuDTO
from core.models.type_hints import UserUID
from core.ports.query_types import KuUserSubstanceResult
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.intelligence import _CoreIntelligenceMixin
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
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

        self._init_context_loader(
            get_entity=self.backend.get,
            dto_class=KuDTO,
            model_class=Ku,
            domain=Domain.KNOWLEDGE,
            model_name="Ku",
        )

    # ========================================================================
    # INTELLIGENCEOPERATIONS PROTOCOL METHODS
    # `get_with_context()` is inherited from `_CoreIntelligenceMixin[Ku]` —
    # typed return, one delegation.
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

        # Count by namespace
        namespaces: dict[str, int] = {}
        for ku in all_kus:
            ns = getattr(ku, "namespace", None) or "unassigned"
            namespaces[ns] = namespaces.get(ns, 0) + 1

        return Result.ok(
            {
                "user_uid": user_uid,
                "period_days": period_days,
                "total_kus": total,
                "by_namespace": namespaces,
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
                "namespace": ku.namespace,
                "ku_category": ku.ku_category,
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
        - Journals: 0.07 per entry, max 0.20 (metacognition)
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
        # Journals not yet tracked in UserContext — post-ADR-054 they are UserEntry rows
        # with pipeline=TRANSCRIBE_AND_STRUCTURE; MEGA_QUERY doesn't collect journal→KU yet
        journal_count = 0

        # Apply Knowledge Substance Philosophy weights with per-channel caps
        task_score = min(0.25, len(task_uids) * 0.05)
        habit_score = min(0.30, len(habit_uids) * 0.10)
        event_score = min(0.25, len(event_uids) * 0.05)
        journal_score = min(0.20, journal_count * 0.07)
        choice_score = min(0.15, len(choice_uids) * 0.07)
        principle_score = min(0.15, len(principle_uids) * 0.07)

        user_substance_score = min(
            1.0,
            task_score + habit_score + event_score + journal_score + choice_score + principle_score,
        )

        breakdown = {
            "tasks": round(task_score, 3),
            "habits": round(habit_score, 3),
            "events": round(event_score, 3),
            "journals": round(journal_score, 3),
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
