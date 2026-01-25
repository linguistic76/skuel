"""
Personalized Knowledge Discovery Adapter
========================================

THE intelligence-enabling adapter for personalized knowledge discovery in SKUEL.

Integrates:
- User's complete knowledge journey (UserContext)
- Semantic intelligence (KuRetrieval with vector + graph)
- Personal learning patterns and readiness

Core Principle: Intelligence manifests through specific, trust-based connections
rather than generic search results. Each discovery is framed through the lens
of the user's unique knowledge state, learning style, and cognitive readiness.

Historical Context:
This adapter represents evolution from SearchUserAdapter, which was
removed in the architectural consolidation of 2025-10-02.

Key architectural shifts:
1. Personal knowledge profile frames discovery (not just filters results)
2. Cognitive readiness assessment drives personalization
3. Learning acceleration and gap analysis built-in
4. Actionable insights generated per user's journey
5. Intelligence manifests through specific connections

Following SKUEL architecture:
- ONE PATH FORWARD: No backwards compatibility, no alternative approaches
- FAIL-FAST: Require complete system, no graceful degradation
- PROTOCOL-BASED: Depend on protocols, not implementations
- RESULT[T]: Internal error handling with boundary conversion
"""

__version__ = "2.0"  # Complete evolution from mock to real implementation

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from neo4j import AsyncDriver

from core.errors import ConfigurationError
from core.models.ku import Ku
from core.services.ku_retrieval import EnhancedResult, KuRetrieval
from core.services.schema_mapping_service import SchemaMappingService
from core.services.user import UserContext
from core.services.user_progress_service import UserKnowledgeProfile as GraphUserProfile
from core.services.user_progress_service import UserProgressService
from core.services.user_service import UserService
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_discovery_score

logger = get_logger("skuel.adapters.personalized_knowledge_discovery")


# ============================================================================
# PERSONALIZED DISCOVERY DATA STRUCTURES
# ============================================================================


@dataclass
class PersonalKnowledgeProfile:
    """
    User's complete knowledge profile that frames all discovery.

    This is the intelligence lens - the specific understanding of THIS user's
    journey, readiness, and learning patterns. Not generic, but deeply personal.
    """

    user_uid: str
    username: str

    # Knowledge state - what they know and at what level
    mastery_levels: dict[str, float] = field(default_factory=dict)
    mastered_knowledge_uids: set[str] = field(default_factory=set)
    in_progress_knowledge_uids: set[str] = field(default_factory=set)

    # Learning journey - where they've been and where they're going
    active_learning_paths: list[str] = field(default_factory=list)
    completed_paths: set[str] = field(default_factory=set)
    learning_goals: list[str] = field(default_factory=list)

    # Cognitive readiness - what they're ready to learn
    prerequisites_completed: set[str] = field(default_factory=set)
    prerequisites_needed: dict[str, list[str]] = field(default_factory=dict)

    # Personal learning patterns
    interests: list[str] = field(default_factory=list)
    learning_level: str = "INTERMEDIATE"
    current_domain_uid: str | None = None
    available_time_minutes: int = 60

    # Knowledge gaps identified
    knowledge_gaps: list[dict[str, Any]] = field(default_factory=list)

    def calculate_readiness_for(self, knowledge_uid: str) -> float:
        """
        Calculate cognitive readiness for specific knowledge.
        Returns 0.0-1.0 based on prerequisites and current state.
        """
        # Already mastered? Readiness is low (they've moved past it)
        if knowledge_uid in self.mastered_knowledge_uids:
            return 0.2

        # Currently learning? Readiness is high
        if knowledge_uid in self.in_progress_knowledge_uids:
            return 0.9

        # Check prerequisites
        prereqs = self.prerequisites_needed.get(knowledge_uid, [])
        if not prereqs:
            return 0.7  # No prerequisites, moderately ready

        # Calculate how many prereqs are met
        prereqs_met = sum(1 for p in prereqs if p in self.prerequisites_completed)
        return prereqs_met / len(prereqs)

    def identify_knowledge_gap(self, gap_type: str, target_uid: str, urgency: float) -> None:
        """Add an identified knowledge gap."""
        self.knowledge_gaps.append(
            {
                "gap_type": gap_type,
                "target_uid": target_uid,
                "urgency": urgency,
                "identified_at": datetime.now().isoformat(),
            }
        )


@dataclass
class PersonalizedDiscoveryResult:
    """
    A knowledge discovery enhanced with personal learning context.

    This represents the connection between knowledge and the individual -
    not just "what was found" but "what this means for THIS learner."
    """

    knowledge_unit: Ku

    # Personal relevance scores
    personal_relevance_score: float  # How relevant to user's journey
    learning_style_alignment: float  # How well it matches learning preferences
    cognitive_readiness_match: float  # How ready user is for this knowledge

    # Retrieval intelligence
    vector_score: float  # Semantic similarity
    graph_score: float  # Graph-based relevance
    final_score: float  # Combined intelligence score

    # Personal context
    graph_context: dict[str, Any] = field(default_factory=dict)
    knowledge_gaps_addressed: list[str] = field(default_factory=list)
    learning_acceleration_potential: float = 0.0

    # Actionable insights
    why_relevant: str = ""
    next_steps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            # Knowledge unit data
            "uid": self.knowledge_unit.uid,
            "title": self.knowledge_unit.title,
            "description": self.knowledge_unit.content,  # Use content field
            "level": self.knowledge_unit.learning_level.value,  # Use learning_level enum
            "domain_uids": [
                self.knowledge_unit.domain.value
            ],  # Use domain (singular), wrap in list
            "tags": self.knowledge_unit.tags,
            # Personal scores
            "personal_relevance_score": self.personal_relevance_score,
            "learning_style_alignment": self.learning_style_alignment,
            "cognitive_readiness_match": self.cognitive_readiness_match,
            # Intelligence scores
            "vector_score": self.vector_score,
            "graph_score": self.graph_score,
            "final_score": self.final_score,
            # Context
            "graph_context": self.graph_context,
            "knowledge_gaps_addressed": self.knowledge_gaps_addressed,
            "learning_acceleration_potential": self.learning_acceleration_potential,
            # Insights
            "why_relevant": self.why_relevant,
            "next_steps": self.next_steps,
        }


# ============================================================================
# PERSONALIZED KNOWLEDGE DISCOVERY ADAPTER
# ============================================================================


class PersonalizedKnowledgeDiscoveryAdapter:
    """
    THE adapter for intelligence-enabled personalized knowledge discovery.

    This is not search - this is discovery framed through the lens of
    individual intelligence and readiness. It connects:

    1. WHO the user is (UserContext - their complete knowledge state)
    2. WHAT exists (KuRetrieval - semantic + graph intelligence)
    3. HOW they learn (Personal patterns and cognitive readiness)

    Result: Discoveries that enable intelligence to manifest, not just
    transactions that return generic results.

    Following SKUEL principles:
    - No backwards compatibility (requires full system)
    - No graceful degradation (fails fast if services missing)
    - Protocol-based dependencies (not concrete implementations)
    - Result[T] error handling (exceptions at boundaries only)
    """

    def __init__(
        self,
        user_service: UserService,
        ku_retrieval: KuRetrieval,
        driver: AsyncDriver,
        user_progress_service: UserProgressService | None = None,
    ) -> None:
        """
        Initialize with required services. No alternatives, no fallbacks.

        Args:
            user_service: Service for user management (required),
            ku_retrieval: THE unified retrieval service (required),
            driver: Neo4j async driver for graph operations (required),
            user_progress_service: Optional UserProgressService (will be created if not provided)

        Raises:
            ConfigurationError: If any required service is missing
        """
        if not user_service:
            raise ConfigurationError(
                "UserService is required for personalized discovery. "
                "SKUEL requires complete user context - no fallback available."
            )

        if not ku_retrieval:
            raise ConfigurationError(
                "KuRetrieval is required for personalized discovery. "
                "SKUEL requires semantic + graph intelligence - no alternatives."
            )

        if not driver:
            raise ConfigurationError(
                "Neo4j driver is required for personalized discovery. "
                "SKUEL requires direct graph access for user-knowledge relationships - no alternatives."
            )

        self.user_service = user_service
        self.retrieval = ku_retrieval
        self.driver = driver
        self.user_progress = user_progress_service or UserProgressService(driver)
        # Note: unified_progress DELETED (January 2026) - use user_progress
        self.schema_mapper = SchemaMappingService()  # Centralized enum mapping
        self.logger = logger

        logger.info(
            "✅ PersonalizedKnowledgeDiscoveryAdapter initialized with graph intelligence, schema mapping"
        )

    async def discover(
        self, user_uid: str, query: str, limit: int = 25, update_activity: bool = True
    ) -> Result[dict[str, Any]]:
        """
        THE method for personalized knowledge discovery.

        Discovery Flow (Intelligence-First):
        1. Build personal knowledge profile (who is this learner?)
        2. Retrieve with semantic + graph intelligence (what exists?)
        3. Frame through personal lens (what does it mean for THEM?)
        4. Identify learning opportunities (how can they grow?)
        5. Generate actionable insights (what should they do next?)

        Args:
            user_uid: User performing discovery,
            query: Discovery query (intent, not just keywords),
            limit: Maximum discoveries to return,
            update_activity: Whether to track this discovery in user history

        Returns:
            Result[Dict]: Personalized discoveries with learning context
        """
        start_time = time.time()

        try:
            self.logger.info(f"🧠 Starting personalized discovery for user {user_uid}: '{query}'")

            # Step 1: Build personal knowledge profile
            profile_result = await self._build_personal_profile(user_uid)
            if profile_result.is_error:
                return Result.fail(profile_result.error)

            personal_profile = profile_result.value

            # Step 2: Build unified user context for retrieval
            context_result = await self._get_unified_context(user_uid)
            if context_result.is_error:
                return Result.fail(context_result.error)

            unified_context = context_result.value

            # Step 3: Retrieve with semantic + graph intelligence
            retrieval_result = await self.retrieval.retrieve(
                query=query,
                context=unified_context,
                limit=limit * 2,  # Get more for filtering
            )

            if retrieval_result.is_error:
                return Result.fail(retrieval_result.error)

            retrieval_data = retrieval_result.value

            # Step 4: Frame through personal lens (with graph-enhanced context)
            personalized_results = await self._personalize_results(
                retrieval_data.results,
                personal_profile,
                query,
                user_uid,  # Pass user_uid for graph context enhancement
            )

            # Step 5: Rank by personal relevance and limit
            final_results = self._rank_by_personal_relevance(personalized_results, limit)

            # Step 6: Generate learning insights
            learning_insights = self._generate_learning_insights(final_results, personal_profile)

            # Step 7: Update activity if requested
            if update_activity:
                await self._track_discovery_activity(user_uid, query, final_results)

            discovery_time_ms = int((time.time() - start_time) * 1000)

            self.logger.info(
                f"✅ Personalized discovery completed: {len(final_results)} results "
                f"in {discovery_time_ms}ms"
            )

            return Result.ok(
                {
                    "discoveries": [r.to_dict() for r in final_results],
                    "learning_insights": learning_insights,
                    "personal_profile_summary": {
                        "user_uid": personal_profile.user_uid,
                        "username": personal_profile.username,
                        "mastered_count": len(personal_profile.mastered_knowledge_uids),
                        "in_progress_count": len(personal_profile.in_progress_knowledge_uids),
                        "active_paths": len(personal_profile.active_learning_paths),
                        "knowledge_gaps": len(personal_profile.knowledge_gaps),
                    },
                    "query_analysis": {
                        "query": query,
                        "intent": retrieval_data.query_analysis.intent.value
                        if retrieval_data.query_analysis.intent
                        else "unknown",
                        "keywords": retrieval_data.query_analysis.keywords,
                    },
                    "metadata": {
                        "total_found": len(final_results),
                        "discovery_time_ms": discovery_time_ms,
                        "personalized": True,
                        "timestamp": datetime.now().isoformat(),
                    },
                }
            )

        except Exception as e:
            self.logger.error(f"❌ Personalized discovery failed: {e}")
            return Result.fail(
                Errors.system(
                    f"Discovery error: {e!s}", service="PersonalizedKnowledgeDiscoveryAdapter"
                )
            )

    async def _build_personal_profile(self, user_uid: str) -> Result[PersonalKnowledgeProfile]:
        """
        Build complete personal knowledge profile from Neo4j graph.

        This now uses UserProgressService to query actual User-Knowledge relationships,
        providing real mastery data, prerequisites, and learning state.
        """
        try:
            # Step 1: Build graph-based profile from Neo4j
            graph_profile_result = await self.user_progress.build_user_knowledge_profile(user_uid)
            if graph_profile_result.is_error:
                return Result.fail(graph_profile_result.expect_error())

            graph_profile = graph_profile_result.value

            # Step 2: Get user preferences from user service
            user_result = await self.user_service.get_user(user_uid)
            if user_result.is_error or not user_result.value:
                return Result.fail(Errors.not_found("resource", f"User {user_uid} not found"))

            user = user_result.value

            # Step 3: Merge graph data with user preferences
            profile = PersonalKnowledgeProfile(
                user_uid=graph_profile.user_uid,
                username=graph_profile.username,
                # REAL mastery data from graph
                mastery_levels={
                    m.knowledge_uid: m.mastery_score for m in graph_profile.mastered_knowledge
                },
                mastered_knowledge_uids=graph_profile.mastered_uids,
                in_progress_knowledge_uids=graph_profile.in_progress_uids,
                # REAL prerequisite data from graph
                prerequisites_completed=graph_profile.completed_prerequisites,
                prerequisites_needed=graph_profile.prerequisite_map,
                # Learning path data from graph
                active_learning_paths=graph_profile.active_learning_paths,
                completed_paths=graph_profile.completed_paths,
                learning_goals=[],  # NOTE: Goals service integration not connected
                # User preferences
                interests=getattr(user, "interests", []),
                learning_level=getattr(user, "learning_level", "INTERMEDIATE"),
                current_domain_uid=getattr(user, "current_domain_uid", None),
                available_time_minutes=getattr(user, "available_time_minutes", 60),
                # Knowledge gaps from graph
                knowledge_gaps=self._build_knowledge_gaps_from_graph(graph_profile),
            )

            # Note: unified_progress enhancement DELETED (January 2026)
            # Learning level determined from graph_profile mastery_levels

            self.logger.info(
                f"✅ Built profile with REAL graph data: "
                f"{len(graph_profile.mastered_uids)} mastered, "
                f"{len(graph_profile.in_progress_uids)} in-progress, "
                f"{len(graph_profile.completed_prerequisites)} prereqs completed"
            )

            return Result.ok(profile)

        except Exception as e:
            self.logger.error(f"❌ Failed to build personal profile: {e}")
            return Result.fail(Errors.system(f"Failed to build personal profile: {e!s}"))

    async def _get_unified_context(self, user_uid: str) -> Result[UserContext]:
        """Get or build unified user context for retrieval."""
        try:
            user_result = await self.user_service.get_user(user_uid)
            if user_result.is_error or not user_result.value:
                return Result.fail(Errors.not_found("resource", f"User {user_uid} not found"))

            user = user_result.value

            # Build UserContext from user data
            context = UserContext(
                user_uid=user.uid,
                username=user.display_name or "User",
                email=user.email or "",
                learning_level=user.preferences.learning_level if user.preferences else None,
                available_minutes_daily=user.preferences.available_minutes_daily
                if user.preferences
                else 60,
            )

            return Result.ok(context)

        except Exception as e:
            return Result.fail(Errors.system(f"Failed to get unified context: {e!s}"))

    def _build_knowledge_gaps_from_graph(
        self, graph_profile: GraphUserProfile
    ) -> list[dict[str, Any]]:
        """Build knowledge gaps from graph profile."""
        gaps = []

        # Struggling knowledge as gaps
        gaps.extend(
            [
                {
                    "gap_type": "struggling",
                    "target_uid": uid,
                    "urgency": 0.8,
                    "identified_at": datetime.now().isoformat(),
                }
                for uid in graph_profile.struggling_uids
            ]
        )

        # Needs review as gaps
        gaps.extend(
            [
                {
                    "gap_type": "needs_review",
                    "target_uid": uid,
                    "urgency": 0.6,
                    "identified_at": datetime.now().isoformat(),
                }
                for uid in graph_profile.needs_review_uids
            ]
        )

        # In-progress without recent activity as potential gaps
        for progress in graph_profile.in_progress_knowledge:
            days_since_access = (datetime.now() - progress.last_accessed).days
            if days_since_access > 7:
                gaps.append(
                    {
                        "gap_type": "stalled_progress",
                        "target_uid": progress.knowledge_uid,
                        "urgency": 0.5,
                        "identified_at": datetime.now().isoformat(),
                    }
                )

        return gaps

    def _determine_learning_level(
        self, learning_progress: dict[str, Any], mastery_levels: dict[str, float]
    ) -> str:
        """
        Determine learning level based on mastery data.

        Uses mastery levels to classify the user's learning level across
        four categories: BEGINNER, INTERMEDIATE, ADVANCED, EXPERT.

        Args:
            learning_progress: Learning data dict (deprecated, use mastery_levels),
            mastery_levels: User's mastery levels for knowledge units (uid -> score)

        Returns:
            Learning level string (BEGINNER, INTERMEDIATE, ADVANCED, EXPERT)
        """
        # Calculate average mastery score
        if not mastery_levels:
            return "BEGINNER"

        avg_mastery = sum(mastery_levels.values()) / len(mastery_levels)
        knowledge_count = len(mastery_levels)

        # Extract learning progress metrics
        completed_paths = learning_progress.get("completed_paths", 0)
        learning_progress.get("active_paths", 0)
        total_learning_time = learning_progress.get("total_time_hours", 0)

        # Multi-factor classification
        # Factor 1: Mastery score (0.0-1.0)
        mastery_factor = avg_mastery

        # Factor 2: Ku breadth (number of units mastered)
        # Scale: 0-10 units = beginner, 10-30 = intermediate, 30-60 = advanced, 60+ = expert
        if knowledge_count < 10:
            breadth_factor = 0.2
        elif knowledge_count < 30:
            breadth_factor = 0.4
        elif knowledge_count < 60:
            breadth_factor = 0.6
        else:
            breadth_factor = 0.8

        # Factor 3: Learning path completion
        # Completed paths indicate depth of learning
        if completed_paths == 0:
            path_factor = 0.2
        elif completed_paths < 3:
            path_factor = 0.4
        elif completed_paths < 6:
            path_factor = 0.6
        else:
            path_factor = 0.8

        # Factor 4: Total learning time (hours invested)
        if total_learning_time < 10:
            time_factor = 0.2
        elif total_learning_time < 50:
            time_factor = 0.4
        elif total_learning_time < 100:
            time_factor = 0.6
        else:
            time_factor = 0.8

        # Weighted combination
        # Mastery is most important (40%), breadth (30%), paths (20%), time (10%)
        composite_score = (
            mastery_factor * 0.4 + breadth_factor * 0.3 + path_factor * 0.2 + time_factor * 0.1
        )

        # Classify based on composite score
        if composite_score < 0.3:
            level = "BEGINNER"
        elif composite_score < 0.5:
            level = "INTERMEDIATE"
        elif composite_score < 0.7:
            level = "ADVANCED"
        else:
            level = "EXPERT"

        self.logger.debug(
            f"Determined learning level: {level} "
            f"(composite={composite_score:.2f}, mastery={mastery_factor:.2f}, "
            f"breadth={knowledge_count}, paths={completed_paths})"
        )

        return level

    async def _personalize_results(
        self,
        retrieval_results: list[EnhancedResult],
        profile: PersonalKnowledgeProfile,
        query: str,
        user_uid: str,
    ) -> list[PersonalizedDiscoveryResult]:
        """
        Transform retrieval results into personalized discoveries.

        Now enhanced with graph-based user context for each result.
        """
        personalized = []

        for result in retrieval_results:
            # Calculate personal relevance
            relevance = self._calculate_personal_relevance(result.unit, profile, query)

            # Calculate cognitive readiness using GRAPH-BASED calculation
            readiness_result = await self.user_progress.calculate_readiness_for_knowledge(
                user_uid=user_uid,
                knowledge_uid=result.unit.uid,
                profile=None,  # Service will use cached profile if available
            )
            readiness = readiness_result.value if readiness_result.is_ok else 0.5

            # Enhance graph context with user-specific relationships
            enhanced_graph_context = await self._enhance_graph_context_with_user(
                result.graph_context, user_uid, result.unit.uid
            )
            result.graph_context = enhanced_graph_context

            # Identify knowledge gaps addressed
            gaps_addressed = self._identify_gaps_addressed(result.unit, profile)

            # Calculate learning acceleration potential
            acceleration = self._calculate_acceleration_potential(result, profile, readiness)

            # Generate why relevant
            why_relevant = self._generate_relevance_explanation(
                result, profile, relevance, readiness
            )

            # Generate next steps
            next_steps = self._generate_next_steps(result.unit, profile, readiness)

            # Create personalized discovery
            discovery = PersonalizedDiscoveryResult(
                knowledge_unit=result.unit,
                personal_relevance_score=relevance,
                learning_style_alignment=0.8,  # NOTE: Uses default - learning style calculation not implemented
                cognitive_readiness_match=readiness,
                vector_score=result.vector_score,
                graph_score=result.graph_score,
                final_score=result.final_score,
                graph_context=result.graph_context,
                knowledge_gaps_addressed=gaps_addressed,
                learning_acceleration_potential=acceleration,
                why_relevant=why_relevant,
                next_steps=next_steps,
            )

            personalized.append(discovery)

        return personalized

    async def _enhance_graph_context_with_user(
        self, base_graph_context: dict[str, Any], user_uid: str, knowledge_uid: str
    ) -> dict[str, Any]:
        """
        Enhance graph context with user-specific relationship data.

        This is THE key method for combining knowledge graph with user progress graph.
        Queries:
        - User's relationship to this knowledge (MASTERED, IN_PROGRESS, etc.)
        - Prerequisites user has completed
        - Related knowledge user is learning
        - Knowledge connections through learning paths
        """
        try:
            async with self.driver.session() as session:
                # Query user's relationship to this knowledge and related user context
                result = await session.run(
                    """
                    MATCH (k:Ku {uid: $knowledge_uid})
                    MATCH (u:User {uid: $user_uid})

                    // User's direct relationship to this knowledge
                    OPTIONAL MATCH (u)-[user_rel:MASTERED|IN_PROGRESS|INTERESTED_IN|BOOKMARKED|STRUGGLING_WITH|NEEDS_REVIEW]->(k)

                    // Prerequisites and their user relationships
                    OPTIONAL MATCH (k)-[:REQUIRES]->(prereq:Ku)
                    OPTIONAL MATCH (u)-[prereq_rel:MASTERED]->(prereq)
                    WITH k, u, user_rel,
                         collect(DISTINCT {
                             uid: prereq.uid,
                             title: prereq.title,
                             user_mastered: prereq_rel IS NOT NULL
                         }) as prerequisites

                    // Next steps (knowledge this enables) and user relationships
                    OPTIONAL MATCH (k)-[:ENABLES]->(next:Ku)
                    OPTIONAL MATCH (u)-[next_rel:INTERESTED_IN|IN_PROGRESS]->(next)
                    WITH k, u, user_rel, prerequisites,
                         collect(DISTINCT {
                             uid: next.uid,
                             title: next.title,
                             user_interested: next_rel IS NOT NULL,
                             rel_type: type(next_rel)
                         }) as next_steps

                    // Related knowledge user is currently learning
                    OPTIONAL MATCH (k)-[:RELATED_TO|HAS_NARROWER|HAS_BROADER]-(related:Ku)
                    OPTIONAL MATCH (u)-[related_rel:IN_PROGRESS|MASTERED]->(related)
                    WHERE related_rel IS NOT NULL
                    WITH k, u, user_rel, prerequisites, next_steps,
                         collect(DISTINCT {
                             uid: related.uid,
                             title: related.title,
                             relationship: 'related',
                             user_status: type(related_rel)
                         }) as user_learning_connections

                    // Learning paths containing this knowledge
                    OPTIONAL MATCH (path:Lp)-[:CONTAINS]->(k)
                    OPTIONAL MATCH (u)-[enrolled:ENROLLED]->(path)
                    WITH k, u, user_rel, prerequisites, next_steps, user_learning_connections,
                         collect(DISTINCT {
                             uid: path.uid,
                             title: path.title,
                             user_enrolled: enrolled IS NOT NULL
                         }) as learning_paths

                    RETURN
                        type(user_rel) as user_relationship,
                        user_rel.mastery_score as mastery_score,
                        user_rel.progress as progress,
                        prerequisites,
                        next_steps,
                        user_learning_connections,
                        learning_paths
                """,
                    {"user_uid": user_uid, "knowledge_uid": knowledge_uid},
                )

                record = await result.single()

                if record:
                    # Merge with base context
                    return {
                        **base_graph_context,
                        # User-specific data
                        "user_relationship": record["user_relationship"],
                        "user_mastery_score": record["mastery_score"],
                        "user_progress": record["progress"],
                        # Prerequisite context
                        "prerequisites": record["prerequisites"],
                        "prerequisites_completed": sum(
                            1 for p in record["prerequisites"] if p["user_mastered"]
                        ),
                        "prerequisites_total": len(record["prerequisites"]),
                        # Next steps context
                        "next_steps": record["next_steps"],
                        "next_steps_user_interested": sum(
                            1 for n in record["next_steps"] if n["user_interested"]
                        ),
                        # Learning connections
                        "user_learning_connections": record["user_learning_connections"],
                        "learning_paths": record["learning_paths"],
                        "user_enrolled_paths": sum(
                            1 for p in record["learning_paths"] if p["user_enrolled"]
                        ),
                        # Graph intelligence flags
                        "has_user_context": True,
                        "personalized": True,
                    }

                else:
                    # No user context found, return base context
                    return {**base_graph_context, "has_user_context": False, "personalized": False}

        except Exception as e:
            self.logger.warning(f"Failed to enhance graph context: {e}")
            # Return base context on error
            return {**base_graph_context, "has_user_context": False, "error": str(e)}

    def _calculate_personal_relevance(
        self, knowledge: Ku, profile: PersonalKnowledgeProfile, _query: str
    ) -> float:
        """Calculate how relevant this knowledge is to user's personal journey."""
        relevance = 0.5  # Base relevance

        # Boost for interest alignment
        for interest in profile.interests:
            if interest.lower() in knowledge.title.lower():
                relevance += 0.2
            if interest.lower() in knowledge.content.lower():
                relevance += 0.1

        # Boost for domain alignment
        if (
            profile.current_domain_uid
            and knowledge.domain
            and profile.current_domain_uid == knowledge.domain.value
        ):
            relevance += 0.3

        # Reduce if already mastered
        if knowledge.uid in profile.mastered_knowledge_uids:
            relevance *= 0.3

        # Boost if in progress
        if knowledge.uid in profile.in_progress_knowledge_uids:
            relevance += 0.4

        return min(1.0, relevance)

    def _identify_gaps_addressed(
        self, knowledge: Ku, profile: PersonalKnowledgeProfile
    ) -> list[str]:
        """Identify which knowledge gaps this addresses."""
        return [
            gap["gap_type"] for gap in profile.knowledge_gaps if gap["target_uid"] == knowledge.uid
        ]

    def _calculate_acceleration_potential(
        self, result: EnhancedResult, _profile: PersonalKnowledgeProfile, readiness: float
    ) -> float:
        """Calculate potential for accelerating user's learning."""
        # High readiness + high graph score = high acceleration
        acceleration = (readiness * 0.5) + (result.graph_score * 0.3) + (result.vector_score * 0.2)
        return min(1.0, acceleration)

    def _generate_relevance_explanation(
        self,
        result: EnhancedResult,
        profile: PersonalKnowledgeProfile,
        relevance: float,
        readiness: float,
    ) -> str:
        """Generate human-readable explanation of why this is relevant."""
        reasons = []

        if readiness > 0.8:
            reasons.append("You're ready to learn this now")
        elif readiness < 0.3:
            reasons.append("This requires more prerequisites")

        if relevance > 0.7:
            reasons.append("Highly aligned with your interests")

        if result.graph_score > 0.7:
            reasons.append("Strongly connected to your current knowledge")

        if result.unit.uid in profile.in_progress_knowledge_uids:
            reasons.append("You're currently learning this")

        return "; ".join(reasons) if reasons else "Relevant to your query"

    def _generate_next_steps(
        self, knowledge: Ku, profile: PersonalKnowledgeProfile, readiness: float
    ) -> list[str]:
        """Generate actionable next steps for this knowledge."""
        steps = []

        if readiness > 0.8:
            steps.append("Start learning this topic")
            steps.append(f"Review: {knowledge.title}")
        elif readiness < 0.5:
            # Check prerequisites
            prereqs = profile.prerequisites_needed.get(knowledge.uid, [])
            if prereqs:
                steps.append(f"Complete prerequisites first: {', '.join(prereqs[:3])}")
        else:
            steps.append("Add to your learning path")

        return steps

    def _rank_by_personal_relevance(
        self, discoveries: list[PersonalizedDiscoveryResult], limit: int
    ) -> list[PersonalizedDiscoveryResult]:
        """Rank discoveries by personal relevance and limit."""
        # Sort by combination of personal relevance and cognitive readiness
        sorted_discoveries = sorted(discoveries, key=get_discovery_score, reverse=True)

        return sorted_discoveries[:limit]

    def _generate_learning_insights(
        self, discoveries: list[PersonalizedDiscoveryResult], _profile: PersonalKnowledgeProfile
    ) -> dict[str, Any]:
        """Generate learning insights from discoveries."""
        return {
            "ready_to_learn_count": sum(
                1 for d in discoveries if d.cognitive_readiness_match > 0.8
            ),
            "needs_prerequisites_count": sum(
                1 for d in discoveries if d.cognitive_readiness_match < 0.5
            ),
            "high_acceleration_count": sum(
                1 for d in discoveries if d.learning_acceleration_potential > 0.7
            ),
            "gaps_addressed_count": sum(len(d.knowledge_gaps_addressed) for d in discoveries),
            "recommended_focus": (discoveries[0].knowledge_unit.uid if discoveries else None),
        }

    async def _track_discovery_activity(
        self, user_uid: str, query: str, results: list[PersonalizedDiscoveryResult]
    ) -> None:
        """Track discovery activity in user history."""
        try:
            await self.user_service.add_conversation_message(
                user_uid=user_uid,
                role="user",
                content=f"discovery: {query}",
                metadata={
                    "type": "personalized_discovery",
                    "query": query,
                    "results_count": len(results),
                    "timestamp": datetime.now().isoformat(),
                },
            )
        except Exception as e:
            self.logger.error(f"Failed to track discovery activity: {e}")


# ============================================================================
# FACTORY FUNCTION
# ============================================================================


def create_personalized_knowledge_discovery_adapter(
    user_service: UserService,
    ku_retrieval: KuRetrieval,
    driver: AsyncDriver,
    user_progress_service: UserProgressService | None = None,
) -> PersonalizedKnowledgeDiscoveryAdapter:
    """
    Factory function to create THE personalized knowledge discovery adapter.

    Args:
        user_service: User service for context (required),
        ku_retrieval: THE unified retrieval service (required),
        driver: Neo4j async driver for graph operations (required),
        user_progress_service: Optional UserProgressService (will be created if not provided)

    Returns:
        PersonalizedKnowledgeDiscoveryAdapter instance

    Raises:
        ConfigurationError: If requirements are not met
    """
    return PersonalizedKnowledgeDiscoveryAdapter(
        user_service=user_service,
        ku_retrieval=ku_retrieval,
        driver=driver,
        user_progress_service=user_progress_service,
    )


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "PersonalKnowledgeProfile",
    "PersonalizedDiscoveryResult",
    "PersonalizedKnowledgeDiscoveryAdapter",
    "create_personalized_knowledge_discovery_adapter",
]
