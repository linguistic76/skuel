"""
PathStep Adaptive Curriculum Service
=====================================

Personalized path step curriculum delivery based on user readiness, prerequisites,
and learning velocity.

Algorithm:
1. Load user's learning intelligence (masteries, paths, velocity)
2. Query path steps filtered by SEL category
3. Filter by readiness (not mastered, prerequisites met, level appropriate)
4. Rank by learning value (enables future path steps, difficulty match, time fit)
5. Return top N recommendations

See: /docs/architecture/CURRICULUM_GROUPING_PATTERNS.md
"""

import contextlib
from datetime import datetime
from typing import Any

from core.models.curriculum import Curriculum
from core.models.enums import LearningLevel, SELCategory
from core.models.pathways.learning_path import LearningPath
from core.models.pathways.learning_progress import CurriculumProgress, LearningJourney
from core.models.pathways.mastery import (
    ContentPreference,
    LearningVelocity,
    Mastery,
    MasteryLevel,
)
from core.models.pathways.path_step import PathStep
from core.models.relationship_names import RelationshipName
from core.models.type_hints import UserUID
from core.models.user.user_intelligence import IntelligenceSource, UserLearningIntelligence
from core.utils.decorators import with_error_handling
from core.utils.exception_types import DATA_CONVERSION_EXCEPTIONS, NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.services.ps.adaptive")


class PsAdaptiveService:
    """
    Personalized path step curriculum delivery.

    Analyzes user's learning journey and delivers personalized
    path steps based on readiness, prerequisites, and learning velocity.

    Sub-service of PsService facade — SEL categories are a property of path steps,
    not a separate domain.
    """

    def __init__(
        self,
        backend: Any,  # PS backend operations
        user_service: Any = None,
    ) -> None:
        if not backend:
            raise ValueError("backend is required")

        self.backend = backend
        self.user_service = user_service
        self.logger = logger

    # ==========================================================================
    # PERSONALIZED CURRICULUM DELIVERY
    # ==========================================================================

    @with_error_handling(error_type="system", operation="get_personalized_curriculum")
    async def get_personalized_curriculum(
        self, user_uid: UserUID, sel_category: SELCategory, limit: int = 10
    ) -> Result[list[PathStep]]:
        """
        Get personalized curriculum for user in an SEL category.

        Algorithm:
        1. Load user's learning intelligence
        2. Query all path steps in this SEL category
        3. Filter by readiness (prerequisites + level)
        4. Rank by learning value
        5. Return top N recommendations
        """
        # 1. Load user intelligence
        user_intel = await self._load_user_intelligence(user_uid)
        if not user_intel:
            self.logger.warning(f"No user intelligence for {user_uid}, using defaults")
            user_intel = self._create_default_intelligence(user_uid)

        # 2. Query path steps for this SEL category
        all_ps_result = await self.backend.find_by(sel_category=sel_category.value)
        if all_ps_result.is_error:
            return Result.fail(all_ps_result)
        all_ps = all_ps_result.value or []

        # 3. Filter by readiness
        ready_ps = [ps for ps in all_ps if await self._is_user_ready(user_intel, ps)]

        # 4. Rank by learning value
        ranked_ps = await self._rank_by_learning_value(user_intel, ready_ps)

        # 5. Return top N
        return Result.ok(ranked_ps[:limit])

    async def _is_user_ready(self, user_intel: UserLearningIntelligence, ps: PathStep) -> bool:
        """Check if user is ready for this path step (not mastered, prereqs met, level ok)."""
        if ps.uid in user_intel.current_masteries:
            return False

        prereqs_met = await self._check_prerequisites_met(user_intel, ps)
        if not prereqs_met:
            return False

        if not isinstance(ps, Curriculum):
            return True  # Non-curriculum types skip level-based filtering

        if ps.sel_category is None:
            return True  # No SEL category = no level-based filtering
        user_level = self._determine_user_level(user_intel, ps.sel_category)
        return ps.is_appropriate_for_level(user_level)

    async def _check_prerequisites_met(
        self, user_intel: UserLearningIntelligence, ps: PathStep
    ) -> bool:
        """Check if user has mastered all prerequisites for this path step."""
        try:
            prereq_result = await self.backend.get_related_uids(
                ps.uid, RelationshipName.REQUIRES_KNOWLEDGE, "outgoing"
            )
            if prereq_result.is_error:
                return True  # Fail open
            prereq_uids = prereq_result.value or []
            return all(uid in user_intel.current_masteries for uid in prereq_uids)
        except AttributeError:
            return True
        except NEO4J_EXCEPTIONS as e:
            self.logger.warning(
                "Error checking prerequisites - failing open",
                extra={"ps_uid": ps.uid, "error": str(e)},
            )
            return True

    def _determine_user_level(
        self, user_intel: UserLearningIntelligence, sel_category: SELCategory
    ) -> LearningLevel:
        """Determine user's current learning level in this SEL category.

        Counts masteries by the mastered node's ``sel_category`` FIELD
        (carried on Mastery from the backend query) — uid strings are
        opaque and never encode a category (ADR-013 never-sniff), so
        authored and generated uids both count.
        """
        category_masteries = 0
        for mastery in user_intel.current_masteries.values():
            if mastery.sel_category == sel_category.value:
                category_masteries += 1

        if category_masteries >= 20:
            return LearningLevel.EXPERT
        elif category_masteries >= 12:
            return LearningLevel.ADVANCED
        elif category_masteries >= 5:
            return LearningLevel.INTERMEDIATE
        else:
            return LearningLevel.BEGINNER

    async def _rank_by_learning_value(
        self, user_intel: UserLearningIntelligence, path_steps: list[PathStep]
    ) -> list[PathStep]:
        """Rank path steps by learning value for this user (highest first)."""
        ps_scores = []
        for ps in path_steps:
            score = await self._calculate_learning_value(user_intel, ps)
            ps_scores.append((ps, score))

        from core.utils.sort_functions import get_result_score

        sorted_ps_scores = sorted(ps_scores, key=get_result_score, reverse=True)
        return [ps for ps, _score in sorted_ps_scores]

    async def _calculate_learning_value(
        self, user_intel: UserLearningIntelligence, ps: PathStep
    ) -> float:
        """
        Calculate learning value score for a path step.

        Factors:
        - Enables many future path steps (high leverage) x 10
        - Matches user's preferred difficulty x 20
        - Time fits user's availability x 15
        - Foundational (no prerequisites) x 5
        - Quick wins x 10
        """
        score = 0.0

        # Factor 1: Enables many future path steps (high leverage)
        enables_count = await self._count_enables(ps)
        score += enables_count * 10

        # Curriculum-specific scoring requires Curriculum fields
        if isinstance(ps, Curriculum):
            # Factor 2: Matches user's preferred difficulty
            user_velocity = user_intel.get_dominant_learning_velocity()
            if (
                (user_velocity == LearningVelocity.FAST and ps.difficulty_rating > 0.7)
                or (
                    user_velocity == LearningVelocity.MODERATE
                    and 0.4 <= ps.difficulty_rating <= 0.7
                )
                or (user_velocity == LearningVelocity.SLOW and ps.difficulty_rating < 0.4)
            ):
                score += 20

            # Factor 3: Time investment matches availability
            available_minutes = getattr(user_intel, "available_minutes", 30)
            if ps.estimated_time_minutes <= available_minutes:
                score += 15

            # Factor 5: Quick wins
            if ps.is_quick_win():
                score += 10

        # Factor 4: Foundational path steps (no prerequisites)
        prereq_count = await self._count_prerequisites(ps)
        if prereq_count == 0:
            score += 5

        return score

    async def _count_enables(self, ps: PathStep) -> int:
        """Count how many path steps this one enables."""
        try:
            enables_result = await self.backend.get_related_uids(
                ps.uid, RelationshipName.ENABLES_KNOWLEDGE, "outgoing"
            )
            enables_uids = enables_result.value if enables_result.is_ok else []
            return len(enables_uids)
        except (AttributeError, *NEO4J_EXCEPTIONS):
            return 0

    async def _count_prerequisites(self, ps: PathStep) -> int:
        """Count how many prerequisites this path step has."""
        try:
            prereq_result = await self.backend.get_related_uids(
                ps.uid, RelationshipName.REQUIRES_KNOWLEDGE, "outgoing"
            )
            prereq_uids = prereq_result.value if prereq_result.is_ok else []
            return len(prereq_uids)
        except (AttributeError, *NEO4J_EXCEPTIONS):
            return 0

    # ==========================================================================
    # SEL JOURNEY TRACKING
    # ==========================================================================

    @with_error_handling(error_type="system", operation="get_sel_journey")
    async def get_sel_journey(self, user_uid: UserUID) -> Result[LearningJourney]:
        """Get user's complete SEL journey across all categories."""
        category_progress = {}

        for category in SELCategory:
            progress = await self._calculate_category_progress(user_uid, category)
            category_progress[category] = progress

        total_progress = sum(p.completion_percentage for p in category_progress.values())
        overall = total_progress / len(SELCategory)

        return Result.ok(
            LearningJourney(
                user_uid=user_uid,
                category_progress=category_progress,
                overall_completion=overall,
            )
        )

    async def _calculate_category_progress(
        self, user_uid: UserUID, category: SELCategory
    ) -> CurriculumProgress:
        """Calculate progress in one SEL category."""
        try:
            all_ps_result = await self.backend.find_by(sel_category=category.value)
            if all_ps_result.is_error:
                all_ps: list[PathStep] = []
            else:
                all_ps = all_ps_result.value or []

            total = len(all_ps)

            user_intel = await self._load_user_intelligence(user_uid)
            if not user_intel:
                user_intel = self._create_default_intelligence(user_uid)

            mastered = sum(ps.uid in user_intel.current_masteries for ps in all_ps)

            return CurriculumProgress(
                user_uid=user_uid,
                sel_category=category,
                steps_mastered=mastered,
                total_steps=total,
            )

        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
            self.logger.warning(
                "Error calculating category progress - returning empty",
                extra={"user_uid": user_uid, "category": category.value, "error": str(e)},
            )
            return CurriculumProgress(
                user_uid=user_uid, sel_category=category, steps_mastered=0, total_steps=0
            )

    # ==========================================================================
    # COMPLETION TRACKING
    # ==========================================================================

    async def track_curriculum_completion(
        self, user_uid: UserUID, ps_uid: str, completion_time_minutes: int = 30
    ) -> Result[None]:
        """Track when user completes a path step — creates/updates MASTERED relationship."""
        try:
            result = await self.backend.track_mastery_completion(
                user_uid, ps_uid, completion_time_minutes
            )
            if result.is_error:
                return Result.fail(result)
            self.logger.info(f"Tracked curriculum completion: {user_uid} -> {ps_uid}")
            return Result.ok(None)
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to track completion: {e}")
            return Result.fail(
                Errors.database("track_curriculum_completion", f"Failed to track completion: {e}")
            )

    # ==========================================================================
    # USER INTELLIGENCE LOADING
    # ==========================================================================

    async def _load_user_intelligence(self, user_uid: UserUID) -> UserLearningIntelligence | None:
        """
        Load user's learning intelligence from Neo4j.

        Aggregates masteries, learning paths, velocities, and preferences.
        """
        try:
            intelligence = UserLearningIntelligence(user_uid=user_uid)

            user_result = await self.user_service.get_user(user_uid)
            if user_result.is_error or not user_result.value:
                return intelligence

            masteries = await self._query_user_masteries(user_uid)
            intelligence.current_masteries = masteries

            active_paths = await self._query_active_learning_paths(user_uid)
            intelligence.active_learning_paths = active_paths

            completed_paths = await self._query_completed_learning_paths(user_uid)
            intelligence.completed_learning_paths = completed_paths

            # intelligence.learning_preferences stays at its UserLearningIntelligence
            # default (None): its only source was a :LearningPreference node nothing
            # ever wrote (SKUEL030 tranche 3).
            intelligence.recent_search_queries = []
            intelligence.knowledge_recommendations = []
            intelligence.intelligence_sources = [
                IntelligenceSource.KNOWLEDGE_MASTERY,
                IntelligenceSource.RELATIONSHIP_ANALYSIS,
            ]

            data_points = len(masteries) + len(active_paths)
            intelligence.intelligence_confidence = min(1.0, data_points / 20.0)

            return intelligence

        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
            self.logger.error(
                "Error loading user intelligence - returning None",
                extra={"user_uid": user_uid, "error": str(e)},
            )
            return None

    def _create_default_intelligence(self, user_uid: UserUID) -> UserLearningIntelligence:
        """Create default user intelligence for users without data."""
        return UserLearningIntelligence(
            user_uid=user_uid,
            current_masteries={},
            learning_preferences=None,
            knowledge_recommendations=[],
            active_learning_paths=[],
            completed_learning_paths=[],
            recent_search_queries=[],
            search_interests={},
            search_intent_patterns={},
            knowledge_to_learning_transfers=[],
            learning_to_search_patterns=[],
            search_to_knowledge_discoveries=[],
            intelligence_sources=[],
        )

    # ==========================================================================
    # INTELLIGENCE QUERY HELPERS
    # ==========================================================================

    async def _query_user_masteries(self, user_uid: UserUID) -> dict[str, Mastery]:
        """Query user's MASTERED relationships from graph."""
        try:
            query_result = await self.backend.query_user_masteries(user_uid)
            if query_result.is_error:
                return {}
            records = query_result.value or []

            masteries = {}
            for record in records:
                ku_uid = record.get("ku_uid")
                if not ku_uid:
                    continue

                mastery_level_str = record.get("mastery_level", "introduced")
                try:
                    mastery_level = MasteryLevel(mastery_level_str)
                except (ValueError, KeyError):  # fmt: skip
                    mastery_level = MasteryLevel.INTRODUCED

                velocity_str = record.get("learning_velocity", "moderate")
                try:
                    learning_velocity = LearningVelocity(velocity_str)
                except (ValueError, KeyError):  # fmt: skip
                    learning_velocity = LearningVelocity.MODERATE

                pref_method_str = record.get("preferred_learning_method")
                preferred_method = None
                if pref_method_str:
                    with contextlib.suppress(ValueError, KeyError):
                        preferred_method = ContentPreference(pref_method_str)

                last_reviewed_str = record.get("last_reviewed")
                last_reviewed = (
                    datetime.fromisoformat(last_reviewed_str)
                    if last_reviewed_str
                    else datetime.now()
                )

                last_practiced_str = record.get("last_practiced")
                last_practiced = (
                    datetime.fromisoformat(last_practiced_str) if last_practiced_str else None
                )

                created_at_str = record.get("created_at")
                created_at = (
                    datetime.fromisoformat(created_at_str) if created_at_str else datetime.now()
                )

                updated_at_str = record.get("updated_at")
                updated_at = (
                    datetime.fromisoformat(updated_at_str) if updated_at_str else datetime.now()
                )

                sel_category_raw = record.get("sel_category")
                sel_category = str(sel_category_raw) if sel_category_raw else None

                mastery = Mastery(
                    uid=f"mastery_{user_uid}_{ku_uid}",
                    user_uid=user_uid,
                    knowledge_uid=ku_uid,
                    sel_category=sel_category,
                    mastery_level=mastery_level,
                    confidence_score=float(record.get("confidence_score", 0.5)),
                    mastery_score=float(record.get("mastery_score", 0.0)),
                    learning_velocity=learning_velocity,
                    time_to_mastery_hours=record.get("time_to_mastery_hours"),
                    review_frequency_days=record.get("review_frequency_days"),
                    mastery_evidence=record.get("mastery_evidence", []),
                    last_reviewed=last_reviewed,
                    last_practiced=last_practiced,
                    learning_path_context=record.get("learning_path_context"),
                    difficulty_experienced=record.get("difficulty_experienced"),
                    preferred_learning_method=preferred_method,
                    created_at=created_at,
                    updated_at=updated_at,
                )
                masteries[ku_uid] = mastery

            return masteries

        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
            self.logger.warning(
                "Error querying user masteries - returning empty",
                extra={"user_uid": user_uid, "error": str(e)},
            )
            return {}

    async def _query_active_learning_paths(self, user_uid: UserUID) -> list[LearningPath]:
        """Query user's active learning paths (backend returns typed models)."""
        try:
            query_result = await self.backend.query_active_learning_paths(user_uid)
            if query_result.is_error:
                return []
            return query_result.value or []

        except NEO4J_EXCEPTIONS:
            return []

    async def _query_completed_learning_paths(self, user_uid: UserUID) -> list[str]:
        """Query UIDs of completed learning paths."""
        try:
            query_result = await self.backend.query_completed_learning_paths(user_uid)
            if query_result.is_error:
                return []

            return [
                record["lp_uid"] for record in (query_result.value or []) if record.get("lp_uid")
            ]

        except NEO4J_EXCEPTIONS:
            return []
