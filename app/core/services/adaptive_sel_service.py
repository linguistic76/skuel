"""
Adaptive SEL Service
===================

Core service for adaptive SEL (Social Emotional Learning) curriculum delivery.

This service analyzes a user's learning journey and delivers personalized
Knowledge Units based on:
- Prerequisites mastered
- Current learning level
- Learning velocity
- Time availability
- Knowledge gaps

Following SKUEL's architecture:
- Returns Result[T] for all operations
- No lambda functions (explicit iteration)
- Protocol-based dependencies
- Graph-native relationship queries
"""

import contextlib
from datetime import datetime

from core.models.ku.ku import Ku
from core.models.ku.ku_intelligence import (
    ContentPreference,
    KuMastery,
    KuRecommendation,
    LearningPreference,
    LearningVelocity,
    MasteryLevel,
)
from core.models.lp.lp import LearningPath
from core.models.relationship_names import RelationshipName
from core.models.sel import SELCategoryProgress, SELJourney
from core.models.shared_enums import Domain, LearningLevel, SELCategory
from core.models.user.user_intelligence import IntelligenceSource, UserLearningIntelligence
from core.services.protocols import BackendOperations
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

# Type alias for the Ku backend
KuBackend = BackendOperations[Ku]


class AdaptiveSELService:
    """
    Core service for adaptive SEL curriculum delivery.

    Analyzes user's learning journey and delivers personalized
    Knowledge Units based on readiness, prerequisites, and learning velocity.


    Source Tag: "adaptive_sel_service_explicit"
    - Format: "adaptive_sel_service_explicit" for user-created relationships
    - Format: "adaptive_sel_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from adaptive_sel metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    def __init__(self, ku_backend: KuBackend, user_service) -> None:
        """
        Initialize adaptive SEL service.

        Args:
            ku_backend: Ku backend implementing BackendOperations[Ku]
            user_service: User service for loading user intelligence
        """
        if not ku_backend:
            raise ValueError("ku_backend is required")
        if not user_service:
            raise ValueError("user_service is required")

        self.ku_backend: KuBackend = ku_backend
        self.user_service = user_service
        self.logger = get_logger(__name__)

    # ==========================================================================
    # PERSONALIZED CURRICULUM DELIVERY
    # ==========================================================================

    @with_error_handling(error_type="system", operation="get_personalized_curriculum")
    async def get_personalized_curriculum(
        self, user_uid: str, sel_category: SELCategory, limit: int = 10
    ) -> Result[list[Ku]]:
        """
        Get personalized curriculum for user in this SEL category.

        Algorithm:
        1. Load user's learning intelligence
        2. Query all KUs in this SEL category
        3. Filter by readiness (prerequisites + level)
        4. Rank by learning value
        5. Return top N recommendations

        Args:
            user_uid: User's unique identifier,
            sel_category: SEL category to get curriculum for,
            limit: Maximum number of KUs to return

        Returns:
            Result[List[Ku]]: Personalized curriculum for this user
        """
        # 1. Load user intelligence
        user_intel = await self._load_user_intelligence(user_uid)
        if not user_intel:
            self.logger.warning(f"No user intelligence for {user_uid}, using defaults")
            user_intel = self._create_default_intelligence(user_uid)

        # 2. Query KUs for this SEL category
        all_kus_result = await self.ku_backend.find_by(sel_category=sel_category.value)

        # BackendOperations.find_by always returns Result[list[T]]
        if all_kus_result.is_error:
            return Result.fail(all_kus_result.expect_error())
        all_kus = all_kus_result.value or []

        # 3. Filter by readiness
        ready_kus = [ku for ku in all_kus if await self._is_user_ready(user_intel, ku)]

        # 4. Rank by learning value
        ranked_kus = await self._rank_by_learning_value(user_intel, ready_kus)

        # 5. Return top N
        return Result.ok(ranked_kus[:limit])

    async def _is_user_ready(self, user_intel: UserLearningIntelligence, ku: Ku) -> bool:
        """
        Check if user is ready for this KU.

        Criteria:
        - Not already mastered
        - Prerequisites mastered
        - Learning level appropriate

        Args:
            user_intel: User's learning intelligence,
            ku: Ku unit to check

        Returns:
            True if user is ready for this KU
        """
        # Already mastered? Skip
        # current_masteries is Dict[str, KnowledgeMastery]
        if ku.uid in user_intel.current_masteries:
            return False

        # Check prerequisites via graph
        prereqs_met = await self._check_prerequisites_met(user_intel, ku)
        if not prereqs_met:
            return False

        # Check learning level
        user_level = self._determine_user_level(user_intel, ku.sel_category)
        return ku.is_appropriate_for_level(user_level)

    async def _check_prerequisites_met(self, user_intel: UserLearningIntelligence, ku: Ku) -> bool:
        """
        Check if user has mastered all prerequisites for this KU.

        Uses graph-native approach: queries RelationshipName.PREREQUISITE relationships.

        Args:
            user_intel: User's learning intelligence,
            ku: Ku unit to check

        Returns:
            True if all prerequisites are mastered
        """
        try:
            # Query prerequisite UIDs from graph
            prereq_result = await self.ku_backend.get_related_uids(
                ku.uid, RelationshipName.PREREQUISITE, "incoming"
            )

            # BackendOperations.get_related_uids returns Result[list[str]]
            if prereq_result.is_error:
                # If query fails, assume no prerequisites
                return True
            prereq_uids = prereq_result.value or []

            # Check if all prerequisites are mastered
            return all(prereq_uid in user_intel.current_masteries for prereq_uid in prereq_uids)

        except AttributeError:
            # Backend doesn't support get_related_uids, assume no prerequisites
            self.logger.debug(
                f"Backend doesn't support prerequisite queries for {ku.uid}",
                extra={"ku_uid": ku.uid, "reason": "missing_get_related_uids"},
            )
            return True
        except Exception as e:
            self.logger.warning(
                "Error checking prerequisites - failing open",
                extra={
                    "ku_uid": ku.uid,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return True  # Fail open

    def _determine_user_level(
        self, user_intel: UserLearningIntelligence, sel_category: SELCategory
    ) -> LearningLevel:
        """
        Determine user's current learning level in this SEL category.

        Based on mastery count and progress in this category.

        Args:
            user_intel: User's learning intelligence,
            sel_category: SEL category to check

        Returns:
            LearningLevel for this user in this category
        """
        # Count masteries in this SEL category
        # current_masteries is Dict[str, KnowledgeMastery]
        category_masteries = 0
        for ku_uid in user_intel.current_masteries:
            if ku_uid.startswith(f"ku.{sel_category.value}"):
                category_masteries += 1

        # Determine level based on mastery count
        if category_masteries >= 20:
            return LearningLevel.EXPERT
        elif category_masteries >= 12:
            return LearningLevel.ADVANCED
        elif category_masteries >= 5:
            return LearningLevel.INTERMEDIATE
        else:
            return LearningLevel.BEGINNER

    async def _rank_by_learning_value(
        self, user_intel: UserLearningIntelligence, kus: list[Ku]
    ) -> list[Ku]:
        """
        Rank KUs by learning value for this specific user.

        Factors:
        - Enables many future KUs (high leverage)
        - Matches user's learning velocity
        - Fills knowledge gaps
        - Time investment matches availability

        Uses named function for sorting.

        Args:
            user_intel: User's learning intelligence,
            kus: Ku units to rank

        Returns:
            List of KUs sorted by learning value (highest first)
        """
        # Calculate score for each KU
        ku_scores = []
        for ku in kus:
            score = await self._calculate_learning_value(user_intel, ku)
            ku_scores.append((ku, score))

        # Sort by score (highest first) using named function
        from core.utils.sort_functions import get_result_score

        sorted_ku_scores = sorted(ku_scores, key=get_result_score, reverse=True)

        # Extract just the KUs
        return [ku for ku, score in sorted_ku_scores]

    async def _calculate_learning_value(
        self, user_intel: UserLearningIntelligence, ku: Ku
    ) -> float:
        """
        Calculate learning value score for a KU.

        Args:
            user_intel: User's learning intelligence,
            ku: Ku unit to score

        Returns:
            Float score (higher = more valuable)
        """
        score = 0.0

        # Factor 1: Enables many future KUs (high leverage)
        enables_count = await self._count_enables(ku)
        score += enables_count * 10

        # Factor 2: Matches user's preferred difficulty
        user_velocity = user_intel.get_dominant_learning_velocity()
        if user_velocity == LearningVelocity.FAST and ku.difficulty_rating > 0.7:
            score += 20  # Challenge for fast learners
        elif user_velocity == LearningVelocity.MODERATE and 0.4 <= ku.difficulty_rating <= 0.7:
            score += 20  # Moderate for average learners
        elif user_velocity == LearningVelocity.SLOW and ku.difficulty_rating < 0.4:
            score += 20  # Easy for slow learners

        # Factor 3: Time investment matches user's availability
        available_minutes = getattr(user_intel, "available_minutes", 30)
        if ku.estimated_time_minutes <= available_minutes:
            score += 15

        # Factor 4: Priority boost for foundational KUs (no prerequisites)
        prereq_count = await self._count_prerequisites(ku)
        if prereq_count == 0:
            score += 5

        # Factor 5: Quick wins get bonus
        if ku.is_quick_win():
            score += 10

        return score

    async def _count_enables(self, ku: Ku) -> int:
        """Count how many KUs this one enables."""
        try:
            enables_result = await self.ku_backend.get_related_uids(
                ku.uid, RelationshipName.ENABLES, "outgoing"
            )

            # BackendOperations.get_related_uids returns Result[list[str]]
            enables_uids = enables_result.value if enables_result.is_ok else []
            return len(enables_uids)
        except AttributeError:
            # Backend doesn't support get_related_uids
            return 0
        except Exception:
            # Silently return 0 - this is just for ranking, not critical
            return 0

    async def _count_prerequisites(self, ku: Ku) -> int:
        """Count how many prerequisites this KU has."""
        try:
            prereq_result = await self.ku_backend.get_related_uids(
                ku.uid, RelationshipName.PREREQUISITE, "incoming"
            )

            # BackendOperations.get_related_uids returns Result[list[str]]
            prereq_uids = prereq_result.value if prereq_result.is_ok else []
            return len(prereq_uids)
        except AttributeError:
            # Backend doesn't support get_related_uids
            return 0
        except Exception:
            # Silently return 0 - this is just for ranking, not critical
            return 0

    # ==========================================================================
    # SEL JOURNEY TRACKING
    # ==========================================================================

    @with_error_handling(error_type="system", operation="get_sel_journey")
    async def get_sel_journey(self, user_uid: str) -> Result[SELJourney]:
        """
        Get user's complete SEL journey across all categories.

        Args:
            user_uid: User's unique identifier

        Returns:
            Result[SELJourney]: Complete journey with progress in all categories
        """
        category_progress = {}

        for category in SELCategory:
            progress = await self._calculate_category_progress(user_uid, category)
            category_progress[category] = progress

        # Calculate overall completion
        total_progress = sum(p.completion_percentage for p in category_progress.values())
        overall = total_progress / len(SELCategory)

        return Result.ok(
            SELJourney(
                user_uid=user_uid,
                category_progress=category_progress,
                overall_completion=overall,
            )
        )

    async def _calculate_category_progress(
        self, user_uid: str, category: SELCategory
    ) -> SELCategoryProgress:
        """
        Calculate progress in one SEL category.

        Args:
            user_uid: User's unique identifier,
            category: SEL category to calculate progress for

        Returns:
            SELCategoryProgress for this category
        """
        try:
            # Query all KUs in category
            all_kus_result = await self.ku_backend.find_by(sel_category=category.value)

            # With typed ku_backend: KuBackend, find_by() always returns Result[list[Ku]]
            if all_kus_result.is_error:
                self.logger.warning(
                    f"Error querying KUs for {category.value}: {all_kus_result.error}"
                )
                all_kus = []
            else:
                all_kus = all_kus_result.value or []

            total = len(all_kus)

            # Query user's masteries
            user_intel = await self._load_user_intelligence(user_uid)
            if not user_intel:
                user_intel = self._create_default_intelligence(user_uid)

            # Count mastered KUs
            # current_masteries is Dict[str, KnowledgeMastery]
            mastered = 0
            for ku in all_kus:
                if ku.uid in user_intel.current_masteries:
                    mastered += 1

            # Create progress object
            return SELCategoryProgress(
                user_uid=user_uid, sel_category=category, kus_mastered=mastered, total_kus=total
            )

        except Exception as e:
            self.logger.warning(
                "Error calculating category progress - returning empty",
                extra={
                    "user_uid": user_uid,
                    "category": category.value,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            # Return empty progress
            return SELCategoryProgress(
                user_uid=user_uid, sel_category=category, kus_mastered=0, total_kus=0
            )

    # ==========================================================================
    # INTERACTION TRACKING
    # ==========================================================================

    async def track_page_view(
        self, user_uid: str, category: SELCategory | None = None
    ) -> Result[None]:
        """
        Track when user views SEL page.

        Creates/updates view count properties on User node.

        Args:
            user_uid: User identifier
            category: SEL category (None for overview)

        Returns:
            Result[None]: Success or error
        """
        try:
            category_str = category.value if category else "overview"

            query = """
            MATCH (u:User {uid: $user_uid})
            SET u.sel_last_viewed = datetime(),
                u.sel_view_count = coalesce(u.sel_view_count, 0) + 1
            WITH u
            SET u['sel_' + $category + '_views'] = coalesce(u['sel_' + $category + '_views'], 0) + 1
            RETURN u.uid
            """

            params = {"user_uid": user_uid, "category": category_str}

            await self.ku_backend.driver.execute_query(query, params)

            self.logger.info(f"Tracked SEL page view: {user_uid} -> {category_str}")
            return Result.ok(None)

        except Exception as e:
            self.logger.error(f"Failed to track page view: {e}")
            return Result.fail(Errors.database("track_page_view", f"Failed to track page view: {e}"))

    async def track_curriculum_completion(
        self, user_uid: str, ku_uid: str, completion_time_minutes: int = 30
    ) -> Result[None]:
        """
        Track when user completes KU from SEL curriculum.

        Creates MASTERED relationship if not exists.

        Args:
            user_uid: User identifier
            ku_uid: Knowledge unit identifier
            completion_time_minutes: Time spent (default: 30)

        Returns:
            Result[None]: Success or error
        """
        try:
            query = """
            MATCH (u:User {uid: $user_uid}), (k:Ku {uid: $ku_uid})
            MERGE (u)-[m:MASTERED]->(k)
            ON CREATE SET
                m.mastery_level = 'introduced',
                m.created_at = datetime(),
                m.time_to_mastery_hours = $completion_time_minutes / 60.0,
                m.source = 'sel_curriculum'
            ON MATCH SET
                m.mastery_level = 'proficient',
                m.updated_at = datetime()
            RETURN m
            """

            params = {
                "user_uid": user_uid,
                "ku_uid": ku_uid,
                "completion_time_minutes": completion_time_minutes,
            }

            await self.ku_backend.driver.execute_query(query, params)

            self.logger.info(f"Tracked curriculum completion: {user_uid} -> {ku_uid}")
            return Result.ok(None)

        except Exception as e:
            self.logger.error(f"Failed to track completion: {e}")
            return Result.fail(Errors.database("track_curriculum_completion", f"Failed to track completion: {e}"))

    # ==========================================================================
    # HELPER METHODS
    # ==========================================================================

    async def _load_user_intelligence(self, user_uid: str) -> UserLearningIntelligence | None:
        """
        Load user's learning intelligence from Neo4j and user service.

        Aggregates:
        1. Knowledge masteries (from graph MASTERED relationships)
        2. Learning paths (active and completed)
        3. Learning velocity by domain
        4. Learning preferences (if available)

        Args:
            user_uid: User's unique identifier

        Returns:
            UserLearningIntelligence or None if not available
        """
        try:
            # Initialize intelligence object
            intelligence = UserLearningIntelligence(user_uid=user_uid)

            # 1. Load knowledge masteries from user service
            user_result = await self.user_service.get_user(user_uid)
            if user_result.is_error or not user_result.value:
                self.logger.debug(f"User {user_uid} not found, returning empty intelligence")
                return intelligence

            # 2. Query MASTERED relationships from graph
            masteries = await self._query_user_masteries(user_uid)
            intelligence.current_masteries = masteries

            # 3. Query active learning paths
            active_paths = await self._query_active_learning_paths(user_uid)
            intelligence.active_learning_paths = active_paths

            # 4. Query completed learning paths
            completed_paths = await self._query_completed_learning_paths(user_uid)
            intelligence.completed_learning_paths = completed_paths

            # 5. Calculate learning velocity by domain from masteries
            intelligence.learning_velocity_by_domain = self._calculate_learning_velocities(
                masteries
            )

            # 6. Load learning preferences if available
            intelligence.learning_preferences = await self._load_learning_preferences(user_uid)

            # 7. Recent search queries (deprecated - removed)
            intelligence.recent_search_queries = []

            # 8. Generate knowledge recommendations based on masteries
            intelligence.knowledge_recommendations = self._generate_knowledge_recommendations(
                masteries, active_paths
            )

            # Mark intelligence sources
            intelligence.intelligence_sources = [
                IntelligenceSource.KNOWLEDGE_MASTERY,
                IntelligenceSource.RELATIONSHIP_ANALYSIS,
            ]

            # Calculate confidence based on data availability
            data_points = (
                len(masteries) + len(active_paths) + len(intelligence.recent_search_queries)
            )
            intelligence.intelligence_confidence = min(1.0, data_points / 20.0)

            self.logger.info(
                f"Loaded intelligence for {user_uid}: "
                f"{len(masteries)} masteries, "
                f"{len(active_paths)} active paths, "
                f"confidence={intelligence.intelligence_confidence:.2f}"
            )

            return intelligence

        except Exception as e:
            self.logger.error(
                "Error loading user intelligence - returning None",
                extra={
                    "user_uid": user_uid,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return None

    def _create_default_intelligence(self, user_uid: str) -> UserLearningIntelligence:
        """
        Create default user intelligence for users without data.

        Args:
            user_uid: User's unique identifier

        Returns:
            Default UserLearningIntelligence
        """
        return UserLearningIntelligence(
            user_uid=user_uid,
            current_masteries={},
            learning_velocity_by_domain={},
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
    # INTELLIGENCE LOADING HELPERS
    # ==========================================================================

    async def _query_user_masteries(self, user_uid: str) -> dict[str, KuMastery]:
        """
        Query user's knowledge masteries from graph.

        Queries MASTERED relationships: (User)-[:MASTERED]->(Ku)

        Returns:
            Dict mapping knowledge_uid to KuMastery
        """
        try:
            # Direct Neo4j query for MASTERED relationships
            query = """
            MATCH (u:User {uid: $user_uid})-[m:MASTERED]->(k:Ku)
            RETURN
                k.uid as ku_uid,
                m.mastery_level as mastery_level,
                m.confidence_score as confidence_score,
                m.mastery_score as mastery_score,
                m.learning_velocity as learning_velocity,
                m.time_to_mastery_hours as time_to_mastery_hours,
                m.review_frequency_days as review_frequency_days,
                m.mastery_evidence as mastery_evidence,
                m.last_reviewed as last_reviewed,
                m.last_practiced as last_practiced,
                m.learning_path_context as learning_path_context,
                m.difficulty_experienced as difficulty_experienced,
                m.preferred_learning_method as preferred_learning_method,
                m.created_at as created_at,
                m.updated_at as updated_at
            """

            # Execute query via ku_backend's driver
            async with self.ku_backend.driver.session() as session:
                result = await session.run(query, {"user_uid": user_uid})
                records = await result.data()

            # Convert to KuMastery objects
            masteries = {}
            for record in records:
                ku_uid = record.get("ku_uid")
                if not ku_uid:
                    continue

                # Parse enum values safely
                mastery_level_str = record.get("mastery_level", "introduced")
                try:
                    mastery_level = MasteryLevel(mastery_level_str)
                except (ValueError, KeyError):
                    mastery_level = MasteryLevel.INTRODUCED

                velocity_str = record.get("learning_velocity", "moderate")
                try:
                    learning_velocity = LearningVelocity(velocity_str)
                except (ValueError, KeyError):
                    learning_velocity = LearningVelocity.MODERATE

                # Parse preferred learning method
                pref_method_str = record.get("preferred_learning_method")
                preferred_method = None
                if pref_method_str:
                    with contextlib.suppress(ValueError, KeyError):
                        preferred_method = ContentPreference(pref_method_str)

                # Parse timestamps
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

                mastery = KuMastery(
                    uid=f"mastery_{user_uid}_{ku_uid}",
                    user_uid=user_uid,
                    knowledge_uid=ku_uid,
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

            self.logger.debug(f"Loaded {len(masteries)} masteries for user {user_uid}")
            return masteries

        except Exception as e:
            self.logger.warning(
                "Error querying user masteries - returning empty",
                extra={
                    "user_uid": user_uid,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return {}

    async def _query_active_learning_paths(self, user_uid: str) -> list[LearningPath]:
        """
        Query user's active learning paths.

        Returns:
            List of active LearningPath objects
        """
        try:
            # Direct Neo4j query for active learning paths
            query = """
            MATCH (u:User {uid: $user_uid})-[:ENROLLED_IN]->(lp:Lp)
            WHERE lp.status = 'active' OR lp.status = 'in_progress'
            RETURN lp
            """

            # Execute query via ku_backend's driver
            async with self.ku_backend.driver.session() as session:
                result = await session.run(query, {"user_uid": user_uid})
                records = await result.data()

            # Convert to LearningPath objects
            from core.utils.neo4j_mapper import from_neo4j_node

            learning_paths = []
            for record in records:
                lp_node = record.get("lp")
                if lp_node:
                    try:
                        learning_path = from_neo4j_node(dict(lp_node), LearningPath)
                        learning_paths.append(learning_path)
                    except Exception as parse_error:
                        self.logger.warning(f"Failed to parse learning path: {parse_error}")
                        continue

            self.logger.debug(
                f"Loaded {len(learning_paths)} active learning paths for user {user_uid}"
            )
            return learning_paths

        except Exception as e:
            self.logger.warning(
                "Error querying active learning paths - returning empty",
                extra={
                    "user_uid": user_uid,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return []

    async def _query_completed_learning_paths(self, user_uid: str) -> list[str]:
        """
        Query UIDs of completed learning paths.

        Returns:
            List of completed learning path UIDs
        """
        try:
            # Direct Neo4j query for completed learning paths
            query = """
            MATCH (u:User {uid: $user_uid})-[:COMPLETED]->(lp:Lp)
            RETURN lp.uid as lp_uid
            """

            # Execute query via ku_backend's driver
            async with self.ku_backend.driver.session() as session:
                result = await session.run(query, {"user_uid": user_uid})
                records = await result.data()

            # Extract UIDs
            completed_uids = [record["lp_uid"] for record in records if record.get("lp_uid")]

            self.logger.debug(
                f"Loaded {len(completed_uids)} completed learning paths for user {user_uid}"
            )
            return completed_uids

        except Exception as e:
            self.logger.warning(
                "Error querying completed learning paths - returning empty",
                extra={
                    "user_uid": user_uid,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return []

    def _calculate_learning_velocities(
        self, masteries: dict[str, KuMastery]
    ) -> dict[Domain, LearningVelocity]:
        """
        Calculate learning velocity by domain from mastery patterns.

        Analyzes how quickly user masters concepts in each domain.

        Args:
            masteries: Dict of KuMastery objects

        Returns:
            Dict mapping Domain to LearningVelocity
        """
        velocities = {}

        # Group masteries by domain
        domain_masteries = {}
        for ku_uid, mastery in masteries.items():
            # Extract domain from UID (e.g., "ku.tech.python" -> Domain.TECH)
            domain = self._extract_domain_from_uid(ku_uid)
            if domain not in domain_masteries:
                domain_masteries[domain] = []
            domain_masteries[domain].append(mastery)

        # Calculate velocity for each domain
        for domain, domain_mastery_list in domain_masteries.items():
            if not domain_mastery_list:
                velocities[domain] = LearningVelocity.MODERATE
                continue

            # Use mastery learning_velocity if available
            velocity_counts = {}
            for mastery in domain_mastery_list:
                vel = mastery.learning_velocity
                velocity_counts[vel] = velocity_counts.get(vel, 0) + 1

            # Get dominant velocity
            if velocity_counts:
                dominant_vel = max(velocity_counts.keys(), key=velocity_counts.get)
                velocities[domain] = dominant_vel
            else:
                velocities[domain] = LearningVelocity.MODERATE

        return velocities

    def _extract_domain_from_uid(self, knowledge_uid: str) -> Domain:
        """Extract domain from knowledge UID."""
        # Knowledge UIDs follow pattern: ku.domain.specific_topic
        # e.g., "ku.tech.python" -> Domain.TECH
        parts = knowledge_uid.split(".")
        if len(parts) >= 2:
            domain_str = parts[1].upper()
            try:
                return Domain[domain_str]
            except KeyError:
                return Domain.KNOWLEDGE
        return Domain.KNOWLEDGE

    async def _load_learning_preferences(self, user_uid: str) -> LearningPreference | None:
        """
        Load user's learning preferences if available.

        Returns:
            LearningPreference or None
        """
        try:
            # Direct Neo4j query for learning preferences
            query = """
            MATCH (u:User {uid: $user_uid})-[:HAS_PREFERENCE]->(pref:LearningPreference)
            RETURN pref
            LIMIT 1
            """

            # Execute query via ku_backend's driver
            async with self.ku_backend.driver.session() as session:
                result = await session.run(query, {"user_uid": user_uid})
                record = await result.single()

            if not record:
                self.logger.debug(f"No learning preferences found for user {user_uid}")
                return None

            # Convert to LearningPreference object
            from core.utils.neo4j_mapper import from_neo4j_node

            pref_node = record.get("pref")
            if pref_node:
                try:
                    learning_pref = from_neo4j_node(dict(pref_node), LearningPreference)
                    self.logger.debug(f"Loaded learning preferences for user {user_uid}")
                    return learning_pref
                except Exception as parse_error:
                    self.logger.warning(f"Failed to parse learning preferences: {parse_error}")
                    return None

            return None

        except Exception as e:
            self.logger.warning(
                "Error loading learning preferences - returning None",
                extra={
                    "user_uid": user_uid,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return None

    # NOTE: _query_recent_searches() removed - deprecated search_archive dependency
    # Search history tracking should be reimplemented using new SearchRequest model if needed

    def _generate_knowledge_recommendations(
        self, _masteries: dict[str, KuMastery], _active_paths: list[LearningPath]
    ) -> list[KuRecommendation]:
        """
        Generate knowledge recommendations based on current state.

        Args:
            masteries: Current knowledge masteries,
            active_paths: Active learning paths

        Returns:
            List of KuRecommendation objects
        """
        return []

        # For now, return empty list
        # Full implementation would analyze mastery gaps and suggest next KUs
