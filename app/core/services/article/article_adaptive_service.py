"""
KU Adaptive Curriculum Service
==============================

Personalized KU curriculum delivery based on user readiness, prerequisites,
and learning velocity. Absorbed from AdaptiveSELService — SEL is a navigation
lens over KUs, not a separate domain.

Algorithm:
1. Load user's learning intelligence (masteries, paths, velocity)
2. Query KUs filtered by SEL category
3. Filter by readiness (not mastered, prerequisites met, level appropriate)
4. Rank by learning value (enables future KUs, difficulty match, time fit)
5. Return top N recommendations

See: /docs/architecture/CURRICULUM_GROUPING_PATTERNS.md
"""

import contextlib
from datetime import datetime
from typing import TYPE_CHECKING

from core.models.article.article import Article
from core.models.curriculum import Curriculum
from core.models.enums import Domain, LearningLevel, SELCategory
from core.models.pathways.learning_path import LearningPath
from core.models.pathways.learning_progress import CurriculumProgress, LearningJourney
from core.models.pathways.mastery import (
    ContentPreference,
    LearningPreference,
    LearningVelocity,
    Mastery,
    MasteryLevel,
)
from core.models.relationship_names import RelationshipName
from core.models.user.user_intelligence import IntelligenceSource, UserLearningIntelligence
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports import BackendOperations

logger = get_logger("skuel.services.article.adaptive")


class ArticleAdaptiveService:
    """
    Personalized KU curriculum delivery.

    Analyzes user's learning journey and delivers personalized
    Knowledge Units based on readiness, prerequisites, and learning velocity.

    Sub-service of ArticleService facade — SEL categories are a property of KUs,
    not a separate domain.
    """

    def __init__(
        self,
        ku_backend: "BackendOperations[Article]",
        user_service=None,
    ) -> None:
        if not ku_backend:
            raise ValueError("ku_backend is required")

        self.ku_backend = ku_backend
        self.user_service = user_service
        self.logger = logger

    # ==========================================================================
    # PERSONALIZED CURRICULUM DELIVERY
    # ==========================================================================

    @with_error_handling(error_type="system", operation="get_personalized_curriculum")
    async def get_personalized_curriculum(
        self, user_uid: str, sel_category: SELCategory, limit: int = 10
    ) -> Result[list[Article]]:
        """
        Get personalized curriculum for user in an SEL category.

        Algorithm:
        1. Load user's learning intelligence
        2. Query all KUs in this SEL category
        3. Filter by readiness (prerequisites + level)
        4. Rank by learning value
        5. Return top N recommendations
        """
        # 1. Load user intelligence
        user_intel = await self._load_user_intelligence(user_uid)
        if not user_intel:
            self.logger.warning(f"No user intelligence for {user_uid}, using defaults")
            user_intel = self._create_default_intelligence(user_uid)

        # 2. Query KUs for this SEL category
        all_kus_result = await self.ku_backend.find_by(sel_category=sel_category.value)
        if all_kus_result.is_error:
            return Result.fail(all_kus_result.expect_error())
        all_kus = all_kus_result.value or []

        # 3. Filter by readiness
        ready_kus = [ku for ku in all_kus if await self._is_user_ready(user_intel, ku)]

        # 4. Rank by learning value
        ranked_kus = await self._rank_by_learning_value(user_intel, ready_kus)

        # 5. Return top N
        return Result.ok(ranked_kus[:limit])

    async def _is_user_ready(self, user_intel: UserLearningIntelligence, ku: Article) -> bool:
        """Check if user is ready for this KU (not mastered, prereqs met, level ok)."""
        if ku.uid in user_intel.current_masteries:
            return False

        prereqs_met = await self._check_prerequisites_met(user_intel, ku)
        if not prereqs_met:
            return False

        if not isinstance(ku, Curriculum):
            return True  # Non-curriculum types skip level-based filtering

        if ku.sel_category is None:
            return True  # No SEL category = no level-based filtering
        user_level = self._determine_user_level(user_intel, ku.sel_category)
        return ku.is_appropriate_for_level(user_level)

    async def _check_prerequisites_met(
        self, user_intel: UserLearningIntelligence, ku: Article
    ) -> bool:
        """Check if user has mastered all prerequisites for this KU."""
        try:
            prereq_result = await self.ku_backend.get_related_uids(
                ku.uid, RelationshipName.REQUIRES_KNOWLEDGE, "outgoing"
            )
            if prereq_result.is_error:
                return True  # Fail open
            prereq_uids = prereq_result.value or []
            return all(uid in user_intel.current_masteries for uid in prereq_uids)
        except AttributeError:
            return True
        except Exception as e:
            self.logger.warning(
                "Error checking prerequisites - failing open",
                extra={"ku_uid": ku.uid, "error": str(e)},
            )
            return True

    def _determine_user_level(
        self, user_intel: UserLearningIntelligence, sel_category: SELCategory
    ) -> LearningLevel:
        """Determine user's current learning level in this SEL category."""
        category_masteries = 0
        for ku_uid in user_intel.current_masteries:
            if ku_uid.startswith(f"ku.{sel_category.value}"):
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
        self, user_intel: UserLearningIntelligence, kus: list[Article]
    ) -> list[Article]:
        """Rank KUs by learning value for this user (highest first)."""
        ku_scores = []
        for ku in kus:
            score = await self._calculate_learning_value(user_intel, ku)
            ku_scores.append((ku, score))

        from core.utils.sort_functions import get_result_score

        sorted_ku_scores = sorted(ku_scores, key=get_result_score, reverse=True)
        return [ku for ku, _score in sorted_ku_scores]

    async def _calculate_learning_value(
        self, user_intel: UserLearningIntelligence, ku: Article
    ) -> float:
        """
        Calculate learning value score for a KU.

        Factors:
        - Enables many future KUs (high leverage) x 10
        - Matches user's preferred difficulty x 20
        - Time fits user's availability x 15
        - Foundational (no prerequisites) x 5
        - Quick wins x 10
        """
        score = 0.0

        # Factor 1: Enables many future KUs (high leverage)
        enables_count = await self._count_enables(ku)
        score += enables_count * 10

        # Curriculum-specific scoring requires Curriculum fields
        if isinstance(ku, Curriculum):
            # Factor 2: Matches user's preferred difficulty
            user_velocity = user_intel.get_dominant_learning_velocity()
            if (
                (user_velocity == LearningVelocity.FAST and ku.difficulty_rating > 0.7)
                or (
                    user_velocity == LearningVelocity.MODERATE
                    and 0.4 <= ku.difficulty_rating <= 0.7
                )
                or (user_velocity == LearningVelocity.SLOW and ku.difficulty_rating < 0.4)
            ):
                score += 20

            # Factor 3: Time investment matches availability
            available_minutes = getattr(user_intel, "available_minutes", 30)
            if ku.estimated_time_minutes <= available_minutes:
                score += 15

            # Factor 5: Quick wins
            if ku.is_quick_win():
                score += 10

        # Factor 4: Foundational KUs (no prerequisites)
        prereq_count = await self._count_prerequisites(ku)
        if prereq_count == 0:
            score += 5

        return score

    async def _count_enables(self, ku: Article) -> int:
        """Count how many KUs this one enables."""
        try:
            enables_result = await self.ku_backend.get_related_uids(
                ku.uid, RelationshipName.ENABLES_KNOWLEDGE, "outgoing"
            )
            enables_uids = enables_result.value if enables_result.is_ok else []
            return len(enables_uids)
        except (AttributeError, Exception):
            return 0

    async def _count_prerequisites(self, ku: Article) -> int:
        """Count how many prerequisites this KU has."""
        try:
            prereq_result = await self.ku_backend.get_related_uids(
                ku.uid, RelationshipName.REQUIRES_KNOWLEDGE, "outgoing"
            )
            prereq_uids = prereq_result.value if prereq_result.is_ok else []
            return len(prereq_uids)
        except (AttributeError, Exception):
            return 0

    # ==========================================================================
    # SEL JOURNEY TRACKING
    # ==========================================================================

    @with_error_handling(error_type="system", operation="get_sel_journey")
    async def get_sel_journey(self, user_uid: str) -> Result[LearningJourney]:
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
        self, user_uid: str, category: SELCategory
    ) -> CurriculumProgress:
        """Calculate progress in one SEL category."""
        try:
            all_kus_result = await self.ku_backend.find_by(sel_category=category.value)
            if all_kus_result.is_error:
                all_kus = []
            else:
                all_kus = all_kus_result.value or []

            total = len(all_kus)

            user_intel = await self._load_user_intelligence(user_uid)
            if not user_intel:
                user_intel = self._create_default_intelligence(user_uid)

            mastered = sum(1 for ku in all_kus if ku.uid in user_intel.current_masteries)

            return CurriculumProgress(
                user_uid=user_uid,
                sel_category=category,
                articles_mastered=mastered,
                total_articles=total,
            )

        except Exception as e:
            self.logger.warning(
                "Error calculating category progress - returning empty",
                extra={"user_uid": user_uid, "category": category.value, "error": str(e)},
            )
            return CurriculumProgress(
                user_uid=user_uid, sel_category=category, articles_mastered=0, total_articles=0
            )

    # ==========================================================================
    # COMPLETION TRACKING
    # ==========================================================================

    async def track_curriculum_completion(
        self, user_uid: str, ku_uid: str, completion_time_minutes: int = 30
    ) -> Result[None]:
        """Track when user completes a KU — creates/updates MASTERED relationship."""
        try:
            query = """
            MATCH (u:User {uid: $user_uid}), (k:Entity {uid: $ku_uid})
            MERGE (u)-[m:MASTERED]->(k)
            ON CREATE SET
                m.mastery_level = 'introduced',
                m.created_at = datetime(),
                m.time_to_mastery_hours = $completion_time_minutes / 60.0,
                m.source = 'curriculum'
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
            result = await self.ku_backend.execute_query(query, params)
            if result.is_error:
                return Result.fail(result.expect_error())
            self.logger.info(f"Tracked curriculum completion: {user_uid} -> {ku_uid}")
            return Result.ok(None)
        except Exception as e:
            self.logger.error(f"Failed to track completion: {e}")
            return Result.fail(
                Errors.database("track_curriculum_completion", f"Failed to track completion: {e}")
            )

    # ==========================================================================
    # USER INTELLIGENCE LOADING
    # ==========================================================================

    async def _load_user_intelligence(self, user_uid: str) -> UserLearningIntelligence | None:
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

            intelligence.learning_velocity_by_domain = self._calculate_learning_velocities(
                masteries
            )
            intelligence.learning_preferences = await self._load_learning_preferences(user_uid)
            intelligence.recent_search_queries = []
            intelligence.knowledge_recommendations = []
            intelligence.intelligence_sources = [
                IntelligenceSource.KNOWLEDGE_MASTERY,
                IntelligenceSource.RELATIONSHIP_ANALYSIS,
            ]

            data_points = len(masteries) + len(active_paths)
            intelligence.intelligence_confidence = min(1.0, data_points / 20.0)

            return intelligence

        except Exception as e:
            self.logger.error(
                "Error loading user intelligence - returning None",
                extra={"user_uid": user_uid, "error": str(e)},
            )
            return None

    def _create_default_intelligence(self, user_uid: str) -> UserLearningIntelligence:
        """Create default user intelligence for users without data."""
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
    # INTELLIGENCE QUERY HELPERS
    # ==========================================================================

    async def _query_user_masteries(self, user_uid: str) -> dict[str, Mastery]:
        """Query user's MASTERED relationships from graph."""
        try:
            query = """
            MATCH (u:User {uid: $user_uid})-[m:MASTERED]->(k:Entity)
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
            query_result = await self.ku_backend.execute_query(query, {"user_uid": user_uid})
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
                except (ValueError, KeyError):
                    mastery_level = MasteryLevel.INTRODUCED

                velocity_str = record.get("learning_velocity", "moderate")
                try:
                    learning_velocity = LearningVelocity(velocity_str)
                except (ValueError, KeyError):
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

                mastery = Mastery(
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

            return masteries

        except Exception as e:
            self.logger.warning(
                "Error querying user masteries - returning empty",
                extra={"user_uid": user_uid, "error": str(e)},
            )
            return {}

    async def _query_active_learning_paths(self, user_uid: str) -> list[LearningPath]:
        """Query user's active learning paths."""
        try:
            query = """
            MATCH (u:User {uid: $user_uid})-[:ENROLLED_IN]->(lp:Lp)
            WHERE lp.status = 'active' OR lp.status = 'in_progress'
            RETURN lp
            """
            query_result = await self.ku_backend.execute_query(query, {"user_uid": user_uid})
            if query_result.is_error:
                return []

            from core.utils.neo4j_mapper import from_neo4j_node

            learning_paths = []
            for record in query_result.value or []:
                lp_node = record.get("lp")
                if lp_node:
                    try:
                        learning_path = from_neo4j_node(lp_node, LearningPath)
                        learning_paths.append(learning_path)
                    except Exception:
                        continue

            return learning_paths

        except Exception:
            return []

    async def _query_completed_learning_paths(self, user_uid: str) -> list[str]:
        """Query UIDs of completed learning paths."""
        try:
            query = """
            MATCH (u:User {uid: $user_uid})-[:COMPLETED]->(lp:Lp)
            RETURN lp.uid as lp_uid
            """
            query_result = await self.ku_backend.execute_query(query, {"user_uid": user_uid})
            if query_result.is_error:
                return []

            return [
                record["lp_uid"] for record in (query_result.value or []) if record.get("lp_uid")
            ]

        except Exception:
            return []

    def _calculate_learning_velocities(
        self, masteries: dict[str, Mastery]
    ) -> dict[Domain, LearningVelocity]:
        """Calculate learning velocity by domain from mastery patterns."""
        domain_masteries: dict[Domain, list[Mastery]] = {}
        for ku_uid, mastery in masteries.items():
            domain = self._extract_domain_from_uid(ku_uid)
            if domain not in domain_masteries:
                domain_masteries[domain] = []
            domain_masteries[domain].append(mastery)

        velocities: dict[Domain, LearningVelocity] = {}
        for domain, domain_mastery_list in domain_masteries.items():
            if not domain_mastery_list:
                velocities[domain] = LearningVelocity.MODERATE
                continue

            velocity_counts: dict[LearningVelocity, int] = {}
            for mastery in domain_mastery_list:
                vel = mastery.learning_velocity
                velocity_counts[vel] = velocity_counts.get(vel, 0) + 1

            if velocity_counts:
                dominant_vel = max(velocity_counts.keys(), key=velocity_counts.get)
                velocities[domain] = dominant_vel
            else:
                velocities[domain] = LearningVelocity.MODERATE

        return velocities

    def _extract_domain_from_uid(self, knowledge_uid: str) -> Domain:
        """Extract domain from knowledge UID."""
        parts = knowledge_uid.split(".")
        if len(parts) >= 2:
            domain_str = parts[1].upper()
            try:
                return Domain[domain_str]
            except KeyError:
                return Domain.KNOWLEDGE
        return Domain.KNOWLEDGE

    async def _load_learning_preferences(self, user_uid: str) -> LearningPreference | None:
        """Load user's learning preferences if available."""
        try:
            query = """
            MATCH (u:User {uid: $user_uid})-[:HAS_PREFERENCE]->(pref:LearningPreference)
            RETURN pref
            LIMIT 1
            """
            result = await self.ku_backend.execute_query(query, {"user_uid": user_uid})

            if result.is_error or not result.value:
                return None

            record = result.value[0]

            from core.utils.neo4j_mapper import from_neo4j_node

            pref_node = record.get("pref")
            if pref_node:
                try:
                    return from_neo4j_node(pref_node, LearningPreference)
                except Exception:
                    return None

            return None

        except Exception:
            return None
