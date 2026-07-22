"""
SKUEL Constants - Single Source of Truth
=========================================

Centralized numeric constants for graph operations, thresholds, and limits.
This module follows the "Dynamic Enum Pattern" philosophy from shared_enums.py
but for numeric constants rather than enumerations.

Core Principle: "Constants define behavior, services consume them"

All hardcoded magic numbers should live here, organized by concern.
When you need to tune a threshold or limit, edit this file once,
and the entire codebase updates.

Last updated: 2026-01-24
"""

from typing import Final

from core.models.type_hints import UserUID

__version__ = "1.0.0"


# ============================================================================
# USER IDENTIFIERS
# ============================================================================

# The canonical user-id format is underscore: ``user_<name>`` (enforced by
# TypeConverter.to_user_uid). SYSTEM_USER_UID is the single source of truth for
# the infrastructure "system" owner — used by the user service AND as the
# ingestion default — so the same logical user is never spelled two ways
# (the prior `user:system` vs `user_system` split).
SYSTEM_USER_UID: Final[UserUID] = UserUID("user_system")


# ============================================================================
# GRAPH TRAVERSAL DEPTHS
# ============================================================================


class GraphDepth:
    """
    Standard depth values for Neo4j graph traversal.

    Philosophy: Different traversal patterns require different depths.
    - Shallow (depth=1): Direct relationships only
    - Medium (depth=2): Neighborhood context
    - Default (depth=3): Rich bi-directional context (SKUEL standard)
    - Deep (depth=5): Prerequisite chains
    - Maximum (depth=10): Shortest path queries

    See: CLAUDE.md - "Pattern-Based Queries Over Property Queries"
    """

    # Direct relationships only (fast, use sparingly)
    DIRECT: Final = 1

    # Neighborhood context (moderate depth)
    NEIGHBORHOOD: Final = 2

    # Default depth for semantic queries (SKUEL standard)
    DEFAULT: Final = 3

    # Extended context (richer than default, less than full chains)
    EXTENDED: Final = 4

    # Prerequisite chains and learning paths
    PREREQUISITE_CHAIN: Final = 5

    # Maximum depth for shortest path queries
    MAXIMUM: Final = 10

    @classmethod
    def get_description(cls, depth: int) -> str:
        """Get human-readable description of depth level."""
        descriptions = {
            cls.DIRECT: "Direct relationships only (shallow)",
            cls.NEIGHBORHOOD: "Neighborhood context (moderate)",
            cls.DEFAULT: "Rich bi-directional context (default)",
            cls.EXTENDED: "Extended context (richer than default)",
            cls.PREREQUISITE_CHAIN: "Prerequisite chains (deep)",
            cls.MAXIMUM: "Shortest path (maximum allowed)",
        }
        return descriptions.get(depth, f"Custom depth ({depth} hops)")


# ============================================================================
# CONFIDENCE THRESHOLDS
# ============================================================================


class ConfidenceLevel:
    """
    Relationship confidence thresholds (0.0 - 1.0).

    Confidence indicates the strength of a semantic relationship:
    - 0.95: Very high confidence (expert knowledge)
    - 0.9: High confidence (strong connection)
    - 0.85: Good confidence (validated relationship)
    - 0.8: Standard confidence (default minimum)
    - 0.7: Medium confidence (useful but uncertain)
    - 0.6: Low confidence (exploratory)

    Usage: Filter relationships by minimum confidence level.
    """

    # Very high confidence - expert knowledge
    VERY_HIGH: Final = 0.95

    # High confidence - strong connection
    HIGH: Final = 0.9

    # Good confidence - validated relationship
    GOOD: Final = 0.85

    # Standard confidence - default minimum for most queries
    STANDARD: Final = 0.8

    # Medium confidence - useful but uncertain
    MEDIUM: Final = 0.7

    # Low confidence - exploratory relationships
    LOW: Final = 0.6

    # Minimum acceptable confidence for reliable prerequisites
    MIN_RELIABLE: Final = 0.9

    # Default for general relationship queries
    DEFAULT: Final = 0.8

    @classmethod
    def get_label(cls, confidence: float) -> str:
        """Get human-readable label for confidence value."""
        if confidence >= cls.VERY_HIGH:
            return "Very High"
        if confidence >= cls.HIGH:
            return "High"
        if confidence >= cls.GOOD:
            return "Good"
        if confidence >= cls.STANDARD:
            return "Standard"
        if confidence >= cls.MEDIUM:
            return "Medium"
        if confidence >= cls.LOW:
            return "Low"
        return "Very Low"


# ============================================================================
# MASTERY THRESHOLDS
# ============================================================================


class MasteryLevel:
    """
    Knowledge mastery thresholds (0.0 - 1.0).

    Mastery indicates how well a user has learned a knowledge unit:
    - 0.9: Expert level - can teach others
    - 0.8: Proficient - comfortable application
    - 0.7: Competent - basic understanding and application
    - 0.5: Beginner - familiar but not confident

    See: CLAUDE.md - "Knowledge Substance Philosophy"
    """

    # Expert level - can teach others
    EXPERT: Final = 0.9

    # Proficient - comfortable application
    PROFICIENT: Final = 0.8

    # Competent - basic understanding (default threshold)
    COMPETENT: Final = 0.7

    # Beginner - familiar but not confident
    BEGINNER: Final = 0.5

    # Default threshold for "mastered" status
    DEFAULT: Final = 0.7

    @classmethod
    def get_label(cls, mastery: float) -> str:
        """Get human-readable label for mastery value."""
        if mastery >= cls.EXPERT:
            return "Expert"
        if mastery >= cls.PROFICIENT:
            return "Proficient"
        if mastery >= cls.COMPETENT:
            return "Competent"
        if mastery >= cls.BEGINNER:
            return "Beginner"
        return "Novice"


# ============================================================================
# QUERY LIMITS
# ============================================================================


class QueryLimit:
    """
    Standard result set limits for database queries.

    Philosophy: Different UI contexts need different result limits.
    - PREVIEW: Quick previews (5 items)
    - SMALL: Widget displays (10 items)
    - MEDIUM: List pages (20 items)
    - STANDARD: Default pagination (50 items)
    - LARGE: Comprehensive results (100 items)
    - BULK: Bulk operations (1000 items)

    See: CLAUDE.md - "Unified Query Pattern for Meta-Services"
    """

    # Quick previews (dashboard widgets)
    PREVIEW: Final = 5

    # Small lists (sidebar, dropdowns)
    SMALL: Final = 10

    # Medium lists (search results)
    MEDIUM: Final = 20

    # Large lists (full page listings)
    LARGE: Final = 25

    # Default pagination size
    DEFAULT: Final = 50

    # Comprehensive results
    COMPREHENSIVE: Final = 100

    # Bulk operations (use with caution)
    BULK: Final = 1000

    # Maximum allowed (for admin/debug only)
    MAXIMUM: Final = 10000

    @classmethod
    def get_description(cls, limit: int) -> str:
        """Get human-readable description of limit."""
        descriptions = {
            cls.PREVIEW: "Preview (quick glance)",
            cls.SMALL: "Small list (widgets)",
            cls.MEDIUM: "Medium list (search results)",
            cls.LARGE: "Large list (full page)",
            cls.DEFAULT: "Default pagination",
            cls.COMPREHENSIVE: "Comprehensive results",
            cls.BULK: "Bulk operations",
            cls.MAXIMUM: "Maximum (admin only)",
        }
        return descriptions.get(limit, f"Custom limit ({limit} items)")


# ============================================================================
# INTELLIGENCE THRESHOLDS
# ============================================================================


class IntelligenceThreshold:
    """
    AI/ML confidence thresholds for intelligent features.

    Used by: Intelligence services, recommendations, auto-generation
    - AUTO_PUBLISH: Auto-publish threshold (0.8)
    - HIGH_CONFIDENCE: High confidence insights (0.75-0.87)
    - STYLE_MATCHING: Learning style confidence (0.6)
    - CROSS_DOMAIN: Cross-domain relationship threshold (0.6)
    """

    # Auto-publish generated content
    AUTO_PUBLISH: Final = 0.8

    # High confidence insights
    HIGH_CONFIDENCE_MIN: Final = 0.75
    HIGH_CONFIDENCE_MAX: Final = 0.87

    # Learning style matching
    STYLE_CONFIDENCE: Final = 0.6

    # Cross-domain relationships
    CROSS_DOMAIN: Final = 0.6

    # Minimum confidence for recommendations
    MIN_RECOMMENDATION: Final = 0.7


class AskesisTokenBudget:
    """
    Character budgets for Askesis LLM context construction.

    Askesis builds context from multiple sources (UserContext, curriculum content,
    activity reports) before sending to the LLM. Without truncation, a rich
    UserContext or a bundle with many PathSteps can exceed the LLM context window
    or waste tokens on low-value content.

    These budgets use characters (~4 chars ≈ 1 token) as a practical proxy.
    Truncation preserves sentence boundaries where possible.

    March 2026: Added to prevent unbounded context growth in RAG pipeline.
    """

    # Maximum characters for curriculum content injected from PsBundle.
    # ~2500 tokens — enough for 2-3 PathSteps' worth of learning content.
    MAX_CURRICULUM_CHARS: Final = 10000

    # Maximum characters for the full LLM context built by ResponseGenerator.
    # ~3000 tokens — covers UserContext summary + curriculum + activity report.
    MAX_LLM_CONTEXT_CHARS: Final = 12000

    # Maximum characters for the user prompt (curriculum context + question)
    # sent to the LLM in the guided pipeline.
    # ~2500 tokens — curriculum is reference material, not the focus.
    MAX_USER_PROMPT_CURRICULUM_CHARS: Final = 10000


class AskesisPipelineTimeout:
    """
    Timeout limits for the Askesis RAG pipeline.

    A typical pipeline (MEGA-QUERY + intent + extraction + bundle + LLM)
    completes in 5-7 seconds. The timeout prevents infinite hangs from
    slow Neo4j queries, unresponsive LLM APIs, or network issues.

    March 2026: Added to prevent unbounded pipeline execution.
    """

    # Maximum seconds for the complete answer_user_question() pipeline.
    ANSWER_QUESTION_SECONDS: Final = 30

    # Maximum seconds for the complete process_query_with_context() pipeline.
    PROCESS_QUERY_SECONDS: Final = 30


class QueryProcessorConfidence:
    """
    Confidence scoring for QueryProcessor RAG pipeline responses.

    Confidence is calculated dynamically based on:
    - Base confidence (starting point)
    - Context availability (entities found, relevant context)
    - Citation availability (source and evidence)
    - Entity extraction success

    Philosophy: Confidence reflects how much supporting data was available
    to generate the response, not a measure of correctness.

    January 2026: Added to replace hardcoded 0.85 confidence values.
    """

    # Base confidence when minimal context is available
    BASE: Final = 0.70

    # Bonus when relevant context was retrieved
    CONTEXT_BONUS: Final = 0.10

    # Bonus when citations are included
    CITATION_BONUS: Final = 0.05

    # Bonus when entities were extracted from query
    ENTITY_BONUS: Final = 0.05

    # Maximum confidence cap
    MAX: Final = 0.95

    @classmethod
    def calculate(
        cls,
        has_context: bool = False,
        has_citations: bool = False,
        has_entities: bool = False,
    ) -> float:
        """
        Calculate confidence score based on available factors.

        Args:
            has_context: Whether relevant context was retrieved
            has_citations: Whether citations were included
            has_entities: Whether entities were extracted from query

        Returns:
            Confidence score (0.70 - 0.95)
        """
        confidence = cls.BASE
        if has_context:
            confidence += cls.CONTEXT_BONUS
        if has_citations:
            confidence += cls.CITATION_BONUS
        if has_entities:
            confidence += cls.ENTITY_BONUS
        return min(confidence, cls.MAX)


# ============================================================================
# ANALYSIS PERIODS
# ============================================================================


class AnalysisPeriod:
    """
    Standard time periods for analytics and reporting.

    Philosophy: Consistent period definitions across all analytics.
    """

    # Short-term analysis
    DAILY: Final = "daily"
    WEEKLY: Final = "weekly"

    # Medium-term analysis
    MONTHLY: Final = "monthly"
    QUARTERLY: Final = "quarterly"

    # Long-term analysis
    YEARLY: Final = "yearly"
    ALL_TIME: Final = "all_time"

    # Intelligence-specific periods
    DAYS_30: Final = "30_days"
    DAYS_90: Final = "90_days"
    DAYS_180: Final = "180_days"


# ============================================================================
# FEEDBACK TIME PERIODS
# ============================================================================


class ReportTimePeriod:
    """
    Valid time period strings for activity reports and review.

    Used by: ActivityReportService, ProgressReportGenerator, ProgressScheduleService
    Both services share the same API-facing period vocabulary ("7d", "14d", etc.)
    and the corresponding day counts for datetime arithmetic.
    """

    WEEK: Final = "7d"
    TWO_WEEKS: Final = "14d"
    MONTH: Final = "30d"
    QUARTER: Final = "90d"
    DEFAULT: Final = "7d"
    DEFAULT_DAYS: Final = 7

    DAYS: Final[dict[str, int]] = {
        "7d": 7,
        "14d": 14,
        "30d": 30,
        "90d": 90,
    }

    # Minimum cooldown between on-demand (user-triggered) report generations.
    # Prevents rapid-fire LLM calls from the /api/reports/progress/generate endpoint.
    MIN_REPORT_COOLDOWN_MINUTES: Final = 60

    # Minimum interval between automatic (scheduled) report generations.
    # Prevents schedule misconfiguration from flooding a user with low-value reports.
    MIN_AUTO_REPORT_INTERVAL_HOURS: Final = 24


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

if __name__ == "__main__":
    # Example: Graph traversal depth
    print(f"Default depth: {GraphDepth.DEFAULT}")
    print(f"Description: {GraphDepth.get_description(GraphDepth.DEFAULT)}")

    # Example: Confidence filtering
    print(f"\nStandard confidence: {ConfidenceLevel.STANDARD}")
    print(f"Label: {ConfidenceLevel.get_label(0.85)}")

    # Example: Mastery levels
    print(f"\nDefault mastery: {MasteryLevel.DEFAULT}")
    print(f"Label: {MasteryLevel.get_label(0.75)}")

    # Example: Query limits
    print(f"\nPreview limit: {QueryLimit.PREVIEW}")
    print(f"Description: {QueryLimit.get_description(QueryLimit.PREVIEW)}")


# ============================================================================
# KU NAMESPACES — Controlled vocabulary for atomic Knowledge Unit grouping
# ============================================================================

# ============================================================================
# LEARNING LOOP CONSTANTS (ADR-048)
# ============================================================================


class LearningLoop:
    """
    Constants for the adaptive learning loop (ADR-048).

    Controls exponential moving average (EMA) rates, cold-start thresholds,
    and clamping bounds for per-user learning state persisted on Neo4j nodes.
    """

    # Task duration calibration
    MIN_SAMPLES_TASK_DURATION: Final = 5
    EMA_ALPHA_TASK_DURATION: Final = 0.3
    MAX_DURATION_RATIO: Final = 3.0
    MIN_DURATION_RATIO: Final = 0.2
    DEFAULT_DURATION_RATIO: Final = 1.0
    DEFAULT_COMPLETION_RATE: Final = 0.5

    # Habit scheduling learning
    MIN_SAMPLES_HABIT_SCHEDULING: Final = 7
    EMA_ALPHA_HABIT_TIMING: Final = 0.2

    # Feedback turnaround calibration
    MIN_SAMPLES_FEEDBACK: Final = 3
    EMA_ALPHA_FEEDBACK: Final = 0.3
    FEEDBACK_FAST_RATIO: Final = 0.5  # <50% of EMA = unusually fast
    FEEDBACK_SLOW_RATIO: Final = 2.0  # >200% of EMA = unusually slow
    DEFAULT_FEEDBACK_HOURS: Final = 48.0

    # Submission iteration thresholds
    PERSISTENT_ITERATION_THRESHOLD: Final = 3
    EXTENDED_EFFORT_THRESHOLD: Final = 5


# ============================================================================
# ZPD WEIGHTS (zpd_service.py)
# ============================================================================


class ZPDWeights:
    """
    Weights and thresholds for the Zone of Proximal Development model.

    Organised by computation stage so the model can be tuned in one place
    as SKUEL accumulates real learning-outcome data.

    See: core/services/zpd/zpd_service.py
    See: docs/roadmap/zpd-service-architecture.md
    """

    # Minimum KUs in the curriculum graph before ZPD runs. Below this the
    # proximal zone is too sparse to produce meaningful recommendations.
    MIN_KU_THRESHOLD: Final = 3

    # Blocking-gap KUs are always high-priority — they unlock territory.
    UNBLOCK_PRIORITY: Final = 0.9

    # Possible signal types per KU (task / habit / entry / submission).
    # Normalises signal_count -> signal_strength (0.0-1.0).
    SIGNAL_TYPE_COUNT: Final = 4

    # Behavioral readiness when both intelligence services are unavailable.
    BEHAVIORAL_NEUTRAL_DEFAULT: Final = 0.5

    # Learn action: readiness * W + alignment * W + behavioral * W
    LEARN_READINESS: Final = 0.5
    LEARN_ALIGNMENT: Final = 0.3
    LEARN_BEHAVIORAL: Final = 0.2

    # Reinforce action: gap * W + alignment * W + behavioral * W
    REINFORCE_GAP: Final = 0.4
    REINFORCE_ALIGNMENT: Final = 0.3
    REINFORCE_BEHAVIORAL: Final = 0.3

    # ── Behavioral readiness — top-level combine ───────────────────────────
    BEHAVIORAL_CHOICES_WEIGHT: Final = 0.65
    BEHAVIORAL_HABITS_WEIGHT: Final = 0.35

    # ── Behavioral readiness — choices sub-weights ─────────────────────────
    CHOICES_ADHERENCE: Final = 0.35
    CHOICES_CONSISTENCY: Final = 0.35
    CHOICES_QUALITY: Final = 0.20
    CHOICES_CONFLICT_PENALTY_PER: Final = 0.05
    CHOICES_CONFLICT_PENALTY_CAP: Final = 0.25

    # ── Behavioral readiness — habits sub-weights ──────────────────────────
    HABITS_AT_RISK_PENALTY_PER: Final = 0.05
    HABITS_AT_RISK_PENALTY_CAP: Final = 0.20


# ============================================================================
# EXERCISE TIME ESTIMATES (daily planning)
# ============================================================================


class ExerciseTimeEstimate:
    """Default per-exercise time budgets used by DailyPlanningMixin via
    ExerciseService.get_actionable_exercises_for_user /
    get_pending_revisions_for_user.

    Revisions are tighter than fresh submissions because the teacher has
    already narrowed the gap — the student responds to specific feedback
    rather than constructing a full answer from scratch.
    """

    FRESH_SUBMISSION_MINUTES: Final = 60
    REVISION_MINUTES: Final = 45


# ============================================================================
# PRIORITY SCORING WEIGHTS (analytics_engine.py)
# ============================================================================


class PriorityScoringWeight:
    """
    Component weights for knowledge-aware task priority scoring.

    Used by: KnowledgeAnalyticsEngine.calculate_knowledge_aware_priority()

    The five component weights must sum to 1.0:
    BASE + KNOWLEDGE + LEARNING + MASTERY + CROSS_DOMAIN = 1.0
    """

    # Component weights (sum to 1.0)
    BASE: Final = 0.3
    KNOWLEDGE: Final = 0.25
    LEARNING: Final = 0.2
    MASTERY: Final = 0.15
    CROSS_DOMAIN: Final = 0.1

    # Priority label → numeric score
    PRIORITY_LEVEL: Final[dict[str, float]] = {
        "LOW": 0.2,
        "MEDIUM": 0.5,
        "HIGH": 0.8,
        "CRITICAL": 1.0,
    }
    DEFAULT_PRIORITY: Final = 0.5


# ============================================================================
# KNOWLEDGE ENHANCEMENT SCORES (analytics_engine.py)
# ============================================================================


class KnowledgeEnhancementScore:
    """
    Scoring constants for knowledge enhancement, mastery progression,
    and urgency calculations.

    Used by: KnowledgeAnalyticsEngine priority sub-calculators
    """

    # Knowledge enhancement potential
    NEW_KNOWLEDGE_POTENTIAL: Final = 0.8
    DEFAULT_ENHANCEMENT: Final = 0.5
    NO_KNOWLEDGE_BASELINE: Final = 0.1

    # Priority boosts for knowledge enhancement
    CRITICAL_PRIORITY_BOOST: Final = 0.2
    HIGH_PRIORITY_BOOST: Final = 0.1

    # Mastery progression weights
    VELOCITY_WEIGHT: Final = 0.6
    MASTERY_ROOM_WEIGHT: Final = 0.4
    NEW_AREA_PROGRESSION: Final = 0.6
    NO_PROGRESSION_FALLBACK: Final = 0.3

    # Urgency boosts (due date proximity)
    VERY_URGENT_BOOST: Final = 0.15
    URGENT_BOOST: Final = 0.10

    # Next difficulty calculation
    DIFFICULTY_STEP: Final = 0.2
    INITIAL_DIFFICULTY: Final = 0.3


# ============================================================================
# CROSS-DOMAIN IMPACT SCORES (analytics_engine.py)
# ============================================================================


class CrossDomainImpactScore:
    """
    Scoring constants for cross-domain knowledge impact assessment.

    Used by: KnowledgeAnalyticsEngine._calculate_cross_domain_impact_score(),
             learning pattern detection methods,
             CrossDomainQueryService principle-alignment scoring
    """

    # Number of aligned connections (goals + habits) that represents full
    # principle alignment — the divisor in CrossDomainQueryService's
    # alignment score: min(1.0, connection_count / FULL_ALIGNMENT_CONNECTION_COUNT).
    FULL_ALIGNMENT_CONNECTION_COUNT: Final = 5.0

    # Domain count scoring
    SINGLE_DOMAIN_SCORE: Final = 0.2
    PER_DOMAIN_SCORE: Final = 0.2
    MAX_DOMAIN_SCORE: Final = 0.8

    # Pattern alignment
    ALIGNMENT_PER_OVERLAP: Final = 0.2

    # Cross-domain priority and tag boosts
    CROSS_DOMAIN_PRIORITY_BOOST: Final = 0.15
    CROSS_DOMAIN_TAG_BOOST: Final = 0.1

    # Growth indicators for learning patterns
    NEUTRAL_GROWTH: Final = 0.5
    REINFORCEMENT_GROWTH: Final = 0.3
    SPECIALIZATION_GROWTH: Final = 0.7
    BRIDGING_GROWTH: Final = 0.6

    # Specialization detection
    SPECIALIZATION_RATIO_THRESHOLD: Final = 0.3


# ============================================================================
# INSIGHT THRESHOLDS (analytics_engine.py)
# ============================================================================


class InsightThreshold:
    """
    Threshold constants for generating learning insights and rationale.

    Used by: KnowledgeAnalyticsEngine insight generators and priority rationale
    """

    # Learning velocity thresholds
    STRONG_GROWTH: Final = 0.5
    NEGATIVE_GROWTH: Final = -0.2

    # Application effectiveness thresholds
    HIGH_COMPLETION_RATE: Final = 0.8
    HIGH_COMPLEXITY: Final = 0.6

    # Mastery validation thresholds
    STRONG_VALIDATION_RATE: Final = 0.8
    WEAK_VALIDATION_RATE: Final = 0.5

    # Priority rationale thresholds
    HIGH_SCORE: Final = 0.7
    LOW_SCORE: Final = 0.3

    # Learning gap detection
    LEARNING_GAP_DAYS: Final = 7


# ============================================================================
# INFERENCE CONFIDENCE (entity_inference_service.py)
# ============================================================================


class InferenceConfidence:
    """
    Confidence scoring constants for the knowledge inference engine.

    Used by: EntityInferenceService content analysis and scoring methods
    """

    # Keyword detection confidence tiers
    DIRECT_KEYWORD: Final = 0.8
    CONTEXTUAL_KEYWORD: Final = 0.6
    ADVANCED_KEYWORD: Final = 0.9

    # Multi-match boosting
    MULTI_MATCH_BOOST_PER: Final = 0.1
    MULTI_MATCH_CAP: Final = 0.95

    # Phrase pattern confidence
    PHRASE_BASE: Final = 0.7
    PHRASE_PER_EVIDENCE: Final = 0.05
    PHRASE_CAP: Final = 0.85

    # Pattern merge boosting
    MERGE_BOOST: Final = 0.05
    MERGE_CAP: Final = 0.95

    # Evidence quality scoring
    EVIDENCE_QUALITY_PER_ITEM: Final = 0.05
    EVIDENCE_QUALITY_CAP: Final = 0.25

    # Domain expertise
    DOMAIN_EXPERTISE_BOOST: Final = 0.1

    # Pattern type reliability bonuses. Keys are KuPattern.pattern_type values
    # as they leave _merge_similar_patterns: singletons keep their detector
    # type; "merged" applies only when several detectors corroborated the same
    # knowledge UID (hence the highest bonus). Types without an entry
    # (e.g. "contextual_learning" — the weakest signal) deliberately get 0.0
    # via the lookup default.
    PATTERN_RELIABILITY: Final[dict[str, float]] = {
        "phrase_pattern": 0.1,
        "keyword_enhanced": 0.05,
        "contextual_integration": 0.08,
        "complexity_based": 0.12,
        "merged": 0.15,
    }


class DualTrackCheckin:
    """
    Constants for dual-track perception-gap check-in persistence (ADR-030).

    Check-ins are an append-only log on the entity's ``dual_track_checkins``
    field. HISTORY_LIMIT caps the retained snapshots so the JSON property does
    not grow unbounded; TREND_WINDOW is how many recent snapshots the per-entity
    card and aggregator inspect when reporting direction-of-travel.
    """

    # Max snapshots retained per entity (oldest dropped on overflow)
    HISTORY_LIMIT: Final = 20

    # Recent snapshots inspected for the simple trend signal
    TREND_WINDOW: Final = 5


# ============================================================================
# INGESTION MASS-DELETION VALVE (ingestion_tracker.py)
# ============================================================================

# Floor for the threshold mass-deletion valve: below this many pending entity/
# edge deletions the valve never fires, so small vaults and small cleanups
# (deleting a handful of files) always propagate without friction.
MASS_DELETION_MIN_COUNT: Final = 10

# Fraction ceiling for the threshold mass-deletion valve: refusing when MORE
# than this share of ALL tracked files under the directory would be deleted in
# one sync — a majority wipe looks like accidental data loss (bulk vault
# deletion, misconfigured root), not authoring. Escape hatch: delete explicitly
# via the ingestion dashboard, or sync in smaller batches.
MASS_DELETION_MAX_FRACTION: Final = 0.5


# ============================================================================
# CANON RETRIEVAL (canon_retrieval_service.py — Phase 3 journaling companion)
# ============================================================================

# How many canon :ReferenceChunk passages to draw into a summoned journal stage.
# Small by design: the passages voice-infuse the LLM's reasoning as system-prompt
# context, they are not a search result set — a handful of the most resonant
# passages is enough to color the response without drowning the entry.
CANON_RETRIEVAL_LIMIT: Final = 4

# Cosine-similarity floor for a passage to count as "resonant" with the entry.
# Deliberately permissive (the journal is associative, not a precision search) —
# below this the passage is noise and is dropped. Tunable once we measure.
CANON_RETRIEVAL_MIN_SCORE: Final = 0.3


# ============================================================================
# LP KNOWLEDGE-SCOPE COMPLEXITY (lp_intelligence_service.analyze_path_knowledge_scope)
# ============================================================================


class LpKnowledgeScopeComplexity:
    """Weights and saturation caps for a learning path's structural complexity.

    Complexity is a v1 STRUCTURAL score — derived only from graph facts we know
    exist (how many KUs the path covers, how deep their prerequisite chains run),
    not from authored difficulty fields (sparsely populated) or an importance
    weighting (deferred to a later arc). It is a blend of two saturating axes:

    - **Breadth** — the count of unique KUs the path teaches. A path covering
      many concepts is broader, hence more complex.
    - **Depth** — the longest REQUIRES_KNOWLEDGE prerequisite chain among those
      KUs. Deeply-dependent knowledge is harder than the same number of
      independent facts.

    Each axis saturates (``min(value / cap, 1.0)``) so a very large path does not
    push the score past 1.0, then the two are combined by the weights below
    (which sum to 1.0). All five numbers are deliberately tunable — measure real
    paths before treating them as anything but a reasonable first cut.
    """

    # A path covering this many unique KUs is treated as maximally broad.
    KU_BREADTH_SATURATION: Final = 30

    # A prerequisite chain this many hops deep is treated as maximally deep.
    PREREQUISITE_DEPTH_SATURATION: Final = 5

    # Blend weights (sum to 1.0) — breadth leads, depth refines.
    BREADTH_WEIGHT: Final = 0.6
    DEPTH_WEIGHT: Final = 0.4


class KnowledgeHealth:
    """Thresholds and weights for the knowledge-subgraph structural-health gauge.

    The Horizon-1 GDS-readiness instrument (ADR-080). Five structural signals are
    each normalized to 0.0-1.0 and blended by the weights below (which sum to 1.0)
    into a composite ``gds_readiness_score``. A graph is deemed GDS-ready once the
    score crosses ``GDS_READY_THRESHOLD`` — the point at which centrality /
    shortest-path / community detection would compute something meaningful.

    Every number here is a deliberate first cut against the 2026-07-22 dev graph
    (121 Kus, avg degree 2.17, 17 orphans, a 9-edge prerequisite DAG, no ORGANIZES
    → score well below the threshold, as intended). Measure a denser corpus before
    treating any of them as settled — the gauge exists precisely to tell us when
    that day arrives.
    """

    # A knowledge subgraph at or above this composite score is treated as dense
    # enough for GDS to say something (the Horizon-2 activation gate, ADR-080).
    GDS_READY_THRESHOLD: Final = 0.6

    # Saturation targets — the value of each raw signal that counts as "fully
    # healthy" (normalized contribution saturates at 1.0 there).
    TARGET_AVG_DEGREE: Final = 6.0  # mean incident edges per Ku
    TARGET_LATERAL_DENSITY: Final = 1.0  # lateral edges per Ku

    # Composite blend weights (sum to 1.0). Connectivity and a real prerequisite
    # DAG lead; ORGANIZES/MOC and lateral refine; orphans penalize.
    WEIGHT_CONNECTIVITY: Final = 0.25  # avg degree vs TARGET_AVG_DEGREE
    WEIGHT_NON_ORPHAN: Final = 0.20  # 1 - orphan_fraction
    WEIGHT_DAG_COVERAGE: Final = 0.25  # fraction of Kus in the prerequisite DAG
    WEIGHT_ORGANIZES_COVERAGE: Final = 0.15  # fraction of Kus under an ORGANIZES edge
    WEIGHT_LATERAL_DENSITY: Final = 0.15  # lateral edges/Ku vs TARGET_LATERAL_DENSITY

    # Authoring-flag trigger thresholds (surface a content-gap flag below these).
    ORPHAN_FLAG_FRACTION: Final = 0.05  # flag when >5% of Kus are orphaned
    MIN_HEALTHY_DAG_COVERAGE: Final = 0.25  # flag a near-empty prerequisite DAG below this
    MIN_HEALTHY_COMPOSITION_COVERAGE: Final = 0.5  # flag under-composed Kus below this
    MIN_HEALTHY_PRACTICE_COVERAGE: Final = 0.5  # flag PathSteps missing exercises below this

    # Safety bound on the prerequisite-DAG depth walk (matches the LP mixin cap).
    PREREQUISITE_DEPTH_CAP: Final = 15


# ============================================================================
# TELEMETRY RETENTION (ADR-080 Horizon 0 — AuraDB Free node-cap safety)
# ============================================================================


class TelemetryRetention:
    """Age windows and batch size for the one-shot telemetry-retention prune.

    AuraDB Free is node-capped, and the unbounded-growth telemetry types dwarf
    the curriculum (AuthEvent/Session run into the thousands while the whole
    knowledge subgraph is ~150 nodes — ADR-080 Horizon 0). ``./dev
    telemetry-retention`` age-prunes them so the graph stays cap-safe. It is a
    deliberate, human-run one-shot (no background loop — the CORE "no background
    workers" guarantee holds).

    Each type gets its own default window. Pure system telemetry (auth, search,
    interactions, learner VIEWED edges) prunes on a shorter horizon than
    saved discussions, which are deliberately-kept user content (ADR-078) and so
    default to the most conservative window. ``--days N`` on the CLI overrides
    every window uniformly; expired sessions/reset-tokens are pruned on their own
    stored ``expires_at`` (not age-based, so ``--days`` does not apply to them).
    """

    # Per-type default age windows, in days. A row older than its window is a
    # prune candidate; ``--days N`` overrides all of these to N.
    AUTH_EVENT_DAYS: Final = 90  # security audit trail — 90d covers lockout forensics
    SEARCH_EVENT_DAYS: Final = 90  # discovery-analytics log (matches the 90d gap window)
    INTERACTION_DAYS: Final = 365  # situated learning-loop events feed ZPD/analytics
    VIEWED_DAYS: Final = 365  # stale learner VIEWED edges (last_viewed_at)
    CONVERSATION_DAYS: Final = 365  # saved discussions = user content — most conservative

    # Batch size for the delete loop. Each batch is its own transaction (the
    # executor auto-commits per query), so a large prune never holds one giant
    # transaction open — safe on a managed instance with a per-tx ceiling.
    BATCH_SIZE: Final = 500


# ============================================================================
# NEO4J STARTUP CONNECT-RETRY (ADR-080 Horizon 0 — paused/waking AuraDB Free)
# ============================================================================


class Neo4jConnectRetry:
    """Bounded exponential-backoff bounds for the initial Neo4j connectivity probe.

    AuraDB Free auto-pauses on inactivity and takes a few seconds to resume on
    the next connection. Without retry, bootstrap would crash with a bare
    ``ServiceUnavailable`` stacktrace the moment it hits a paused instance. The
    startup probe (``Neo4jAdapter.connect``) retries the ``RETURN 1`` check with
    exponential backoff so a waking instance is tolerated; after the bound it
    fails with one clear, actionable error. This is startup-only — deep
    live-request reconnect/circuit-breaker across query sites is deliberately
    deferred (ADR-080 "When to Revisit").

    Defaults: 6 attempts → 5 backoffs of 1+2+4+8+16 = ~31s total patience
    (plus per-attempt probe time) — comfortably longer than a Free-tier resume,
    short enough to fail fast on a genuine misconfiguration. ``MAX_DELAY_SECONDS``
    caps the growth (only reached if ``MAX_ATTEMPTS`` is raised well past 6).
    """

    MAX_ATTEMPTS: Final = 6
    BASE_DELAY_SECONDS: Final = 1.0
    MAX_DELAY_SECONDS: Final = 30.0
