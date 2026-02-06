"""
Analytics Aggregation Service
==============================

Cross-layer synthesis and pattern detection for Life Analytics.

Version: 2.0.0 (October 24, 2025) - Phase 3: Cross-Layer Synthesis

This service provides holistic analytics that synthesize insights across
ALL 4 architectural layers:
- Layer 0: Curriculum (Knowledge, Learning Paths)
- Layer 1: Activities (7 domains: Tasks, Habits, Goals, Events, Finance, Choices, Principles)
- Layer 2: Pipeline (Journals - reflection and metacognition)
- Layer 3: Meta-Analysis (Life Path alignment)

NEW in v2.0.0: Cross-Layer Synthesis
- Knowledge-activity correlations: "Which activities drive knowledge embodiment?"
- Journal-reflection impact: "How does reflection affect alignment?"
- Curriculum progress integration: "Am I learning what I'm practicing?"
- Complete 4-layer holistic view

Life Analytics answer questions like:
- "Show me my weekly life summary across ALL layers"
- "Which activities are driving my Life Path alignment?"
- "How is reflection impacting my growth?"
- "What patterns exist across knowledge, activities, and reflection?"
- "Am I learning what I'm living?"

Part of the 4-service Analytics architecture:
- AnalyticsMetricsService: ALL layers metrics (0, 1, 2)
- AnalyticsAggregationService: Cross-layer synthesis (this file)
- AnalyticsLifePathService: Life Path alignment tracking
- AnalyticsService: Facade orchestrating all services

Philosophy: "Everything flows toward the life path"
"""

import operator
from datetime import date
from typing import Any

from core.models.shared_enums import Domain
from core.utils.logging import get_logger

logger = get_logger(__name__)


class AnalyticsAggregationService:
    """
    Cross-layer aggregation and pattern detection for Life Analytics.

    Version 2.0.0: Synthesizes data from ALL 4 layers to generate
    holistic insights about the user's life, learning, and growth.

    Cross-layer synthesis capabilities:
    - Layer 0 + Layer 1: Knowledge-activity correlations
    - Layer 2 + Layer 1: Journal-reflection impact on activities
    - Layer 0 + Layer 2: Learning-reflection patterns
    - Layer 3: Life Path alignment synthesis (via AnalyticsLifePathService)


    Source Tag: "analytics_aggregation_explicit"
    - Format: "analytics_aggregation_explicit" for user-created relationships
    - Format: "analytics_aggregation_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from reports metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    def __init__(self, metrics_service: Any) -> None:
        """
        Initialize with metrics service.

        Args:
            metrics_service: AnalyticsMetricsService for domain statistics
        """
        self.metrics = metrics_service
        self.logger = logger
        logger.info("AnalyticsAggregationService initialized")

    # ========================================================================
    # LIFE SUMMARIES (ALL 7 DOMAINS)
    # ========================================================================

    async def aggregate_weekly_life_summary(
        self, user_uid: str, start_date: date, end_date: date
    ) -> dict[str, Any]:
        """
        Generate weekly life summary across ALL 4 layers.

        NEW in v2.0.0: Includes Layer 0 (knowledge), Layer 2 (journals),
        and cross-layer synthesis in addition to Layer 1 (7 domains).

        Returns comprehensive view of user's week showing:
        - Layer 1: Activity across 7 domains
        - Layer 0: Knowledge substance and curriculum progress
        - Layer 2: Journal reflections and themes
        - Cross-layer: Knowledge-activity correlations, reflection impact
        """
        self.logger.info(f"Generating weekly life summary (ALL layers) for user {user_uid}")

        # Layer 1: Collect metrics from all 7 activity domains
        tasks_metrics = await self.metrics.calculate_task_metrics(user_uid, start_date, end_date)
        habits_metrics = await self.metrics.calculate_habit_metrics(user_uid, start_date, end_date)
        goals_metrics = await self.metrics.calculate_goal_metrics(user_uid, start_date, end_date)
        events_metrics = await self.metrics.calculate_event_metrics(user_uid, start_date, end_date)
        finance_metrics = await self.metrics.calculate_finance_metrics(
            user_uid, start_date, end_date
        )
        choices_metrics = await self.metrics.calculate_choice_metrics(
            user_uid, start_date, end_date
        )
        principles_metrics = await self.metrics.calculate_principle_metrics(
            user_uid, start_date, end_date
        )

        # Layer 0: Knowledge and curriculum metrics (NEW - Phase 3)
        knowledge_metrics = await self.metrics.calculate_knowledge_metrics(
            user_uid, start_date, end_date
        )
        curriculum_metrics_result = await self.metrics.calculate_curriculum_metrics(user_uid)
        curriculum_metrics = (
            curriculum_metrics_result.value if curriculum_metrics_result.is_ok else {}
        )

        # Layer 2: Journal reflection metrics (NEW - Phase 3)
        journal_metrics = await self.metrics.calculate_journal_metrics(
            user_uid, start_date, end_date
        )

        # Layer 1: Aggregate activity statistics
        layer1_domains = {
            "tasks": tasks_metrics,
            "habits": habits_metrics,
            "goals": goals_metrics,
            "events": events_metrics,
            "finance": finance_metrics,
            "choices": choices_metrics,
            "principles": principles_metrics,
        }

        total_activity = self._calculate_total_activity(layer1_domains)
        domain_activity_ranking = self._rank_domains_by_activity(layer1_domains)

        # Layer 1: Cross-domain patterns (existing)
        layer1_patterns = self._detect_basic_patterns(layer1_domains)

        # NEW: Cross-layer synthesis (Phase 3)
        cross_layer_insights = self._synthesize_cross_layer_insights(
            layer1_domains=layer1_domains,
            knowledge_metrics=knowledge_metrics,
            journal_metrics=journal_metrics,
            curriculum_metrics=curriculum_metrics,
        )

        return {
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "total_activity_score": total_activity,
            "domain_rankings": domain_activity_ranking,
            # Layer 1: Activity domains
            "layer_1_activities": layer1_domains,
            # Layer 0: Curriculum and knowledge (NEW)
            "layer_0_knowledge": {
                "substance_metrics": knowledge_metrics,
                "curriculum_progress": curriculum_metrics,
            },
            # Layer 2: Journals and reflection (NEW)
            "layer_2_reflection": journal_metrics,
            # Cross-layer synthesis (NEW)
            "cross_layer_insights": cross_layer_insights,
            # Legacy keys for backward compatibility
            "domains": layer1_domains,
            "cross_domain_patterns": layer1_patterns,
            # Enhanced summary with all layers
            "summary": self._generate_cross_layer_summary_text(
                domain_activity_ranking, knowledge_metrics, journal_metrics, cross_layer_insights
            ),
        }

    async def aggregate_monthly_life_review(
        self, user_uid: str, start_date: date, end_date: date
    ) -> dict[str, Any]:
        """
        Generate monthly life review across ALL 7 domains.

        Deeper analysis than weekly summary, includes trends and
        monthly patterns.
        """
        self.logger.info(f"Generating monthly life review for user {user_uid}")

        # Reuse weekly aggregation logic
        weekly_data = await self.aggregate_weekly_life_summary(user_uid, start_date, end_date)

        # Add monthly-specific analysis
        monthly_trends = self._analyze_monthly_trends(weekly_data["domains"])
        goal_progress = self._analyze_goal_progress(weekly_data["domains"]["goals"])

        return {
            **weekly_data,
            "monthly_trends": monthly_trends,
            "goal_progress_analysis": goal_progress,
            "summary": self._generate_monthly_review_text(
                weekly_data["domain_rankings"], monthly_trends, goal_progress
            ),
        }

    async def aggregate_quarterly_progress(
        self, user_uid: str, start_date: date, end_date: date
    ) -> dict[str, Any]:
        """
        Generate quarterly progress report across ALL 7 domains.

        Long-term trends and strategic assessment.
        """
        self.logger.info(f"Generating quarterly progress for user {user_uid}")

        # Collect domain metrics
        monthly_data = await self.aggregate_monthly_life_review(user_uid, start_date, end_date)

        # Add quarterly analysis
        strategic_insights = self._analyze_strategic_progress(monthly_data["domains"])

        return {
            **monthly_data,
            "strategic_insights": strategic_insights,
            "quarter_summary": self._generate_quarterly_summary_text(
                monthly_data["domain_rankings"], strategic_insights
            ),
        }

    async def aggregate_yearly_review(
        self, user_uid: str, start_date: date, end_date: date
    ) -> dict[str, Any]:
        """
        Generate yearly review across ALL 7 domains.

        Annual retrospective and forward-looking assessment.
        """
        self.logger.info(f"Generating yearly review for user {user_uid}")

        # Collect domain metrics
        quarterly_data = await self.aggregate_quarterly_progress(user_uid, start_date, end_date)

        # Add yearly analysis
        year_achievements = self._analyze_year_achievements(quarterly_data["domains"])
        growth_areas = self._identify_growth_opportunities(quarterly_data["domains"])

        return {
            **quarterly_data,
            "year_achievements": year_achievements,
            "growth_opportunities": growth_areas,
            "year_summary": self._generate_yearly_summary_text(
                quarterly_data["domain_rankings"], year_achievements, growth_areas
            ),
        }

    # ========================================================================
    # PATTERN DETECTION
    # ========================================================================

    async def detect_cross_domain_patterns(
        self, user_uid: str, start_date: date, end_date: date
    ) -> dict[str, Any]:
        """
        Detect patterns and relationships across domains.

        Examples:
        - Do high-expense periods correlate with low task completion?
        - Are choices aligned with principles?
        - Do goals have supporting habits?
        """
        self.logger.info(f"Detecting cross-domain patterns for user {user_uid}")

        # Collect all domain metrics
        tasks_metrics = await self.metrics.calculate_task_metrics(user_uid, start_date, end_date)
        habits_metrics = await self.metrics.calculate_habit_metrics(user_uid, start_date, end_date)
        goals_metrics = await self.metrics.calculate_goal_metrics(user_uid, start_date, end_date)
        events_metrics = await self.metrics.calculate_event_metrics(user_uid, start_date, end_date)
        finance_metrics = await self.metrics.calculate_finance_metrics(
            user_uid, start_date, end_date
        )
        choices_metrics = await self.metrics.calculate_choice_metrics(
            user_uid, start_date, end_date
        )
        principles_metrics = await self.metrics.calculate_principle_metrics(
            user_uid, start_date, end_date
        )

        # Detect patterns
        return {
            "expense_productivity_correlation": self._correlate_expenses_productivity(
                finance_metrics, tasks_metrics
            ),
            "choice_principle_alignment": self._analyze_choice_principle_alignment(
                choices_metrics, principles_metrics
            ),
            "goal_habit_support": self._analyze_goal_habit_support(goals_metrics, habits_metrics),
            "time_allocation": self._analyze_time_allocation(
                events_metrics, tasks_metrics, habits_metrics
            ),
            "domain_balance": self._assess_domain_balance(
                {
                    "tasks": tasks_metrics,
                    "habits": habits_metrics,
                    "goals": goals_metrics,
                    "events": events_metrics,
                    "finance": finance_metrics,
                    "choices": choices_metrics,
                    "principles": principles_metrics,
                }
            ),
        }

    # ========================================================================
    # ANALYSIS HELPERS
    # ========================================================================

    def _calculate_total_activity(self, domains: dict[str, dict]) -> float:
        """Calculate overall activity score across all domains"""
        scores = []

        # Tasks activity (0-100 based on completion rate)
        if "total_count" in domains["tasks"]:
            scores.append(min(domains["tasks"]["total_count"] * 10, 100))

        # Habits activity (0-100 based on active habits)
        if "total_active" in domains["habits"]:
            scores.append(min(domains["habits"]["total_active"] * 15, 100))

        # Goals activity (0-100 based on active goals)
        if "total_active" in domains["goals"]:
            scores.append(min(domains["goals"]["total_active"] * 20, 100))

        # Events activity (0-100 based on scheduled hours)
        if "total_hours_scheduled" in domains["events"]:
            scores.append(min(domains["events"]["total_hours_scheduled"] * 2, 100))

        # Finance activity (0-100 based on expense count)
        if "total_expenses" in domains["finance"]:
            # Use non-zero expenses as activity indicator
            expense_activity = 50 if domains["finance"]["total_expenses"] > 0 else 0
            scores.append(expense_activity)

        # Choices activity (0-100 based on choice count)
        if "total_choices" in domains["choices"]:
            scores.append(min(domains["choices"]["total_choices"] * 25, 100))

        # Principles activity (0-100 based on active principles)
        if "active_principles" in domains["principles"]:
            scores.append(min(domains["principles"]["active_principles"] * 15, 100))

        return round(sum(scores) / len(scores), 1) if scores else 0.0

    def _rank_domains_by_activity(self, domains: dict[str, dict]) -> list[dict[str, Any]]:
        """Rank domains by activity level"""
        rankings = []

        for domain_name, metrics in domains.items():
            activity_score = 0

            if domain_name == Domain.TASKS.value:
                activity_score = metrics.get("total_count", 0)
            elif domain_name == Domain.HABITS.value:
                activity_score = metrics.get("total_active", 0) * 2
            elif domain_name == Domain.GOALS.value:
                activity_score = metrics.get("total_active", 0) * 3
            elif domain_name == Domain.EVENTS.value:
                activity_score = metrics.get("total_count", 0)
            elif domain_name == Domain.FINANCE.value:
                activity_score = 10 if metrics.get("total_expenses", 0) > 0 else 0
            elif domain_name == Domain.CHOICES.value:
                activity_score = metrics.get("total_choices", 0) * 2
            elif domain_name == Domain.PRINCIPLES.value:
                activity_score = metrics.get("active_principles", 0) * 2

            rankings.append({"domain": domain_name, "activity_score": activity_score})

        # Sort by activity score descending
        from core.utils.sort_functions import get_activity_score

        rankings.sort(key=get_activity_score, reverse=True)

        return rankings

    def _detect_basic_patterns(self, domains: dict[str, dict]) -> dict[str, Any]:
        """Detect basic cross-domain patterns"""
        patterns = {}

        # Check if high expenses with low task completion
        tasks_rate = domains["tasks"].get("completion_rate", 0)
        expenses = domains["finance"].get("total_expenses", 0)

        if expenses > 1000 and tasks_rate < 50:
            patterns["high_expenses_low_productivity"] = {
                "detected": True,
                "expense_amount": expenses,
                "task_completion_rate": tasks_rate,
            }

        # Check principle-choice alignment
        principles_count = domains["principles"].get("active_principles", 0)
        choices_count = domains["choices"].get("total_choices", 0)

        if principles_count > 0 and choices_count > 0:
            patterns["principle_guided_decisions"] = {
                "detected": True,
                "principles": principles_count,
                "choices": choices_count,
            }

        return patterns

    def _analyze_monthly_trends(self, domains: dict[str, dict]) -> dict[str, Any]:
        """Analyze trends over the month"""
        return {
            "completion_trends": {
                "tasks": domains["tasks"].get("completion_rate", 0),
                "habits": domains["habits"].get("completion_rate", 0),
                "goals": domains["goals"].get("avg_progress_percentage", 0),
            },
            "activity_distribution": self._rank_domains_by_activity(domains),
        }

    def _analyze_goal_progress(self, goal_metrics: dict) -> dict[str, Any]:
        """Analyze goal progress for monthly review"""
        return {
            "on_track": goal_metrics.get("on_track_count", 0),
            "at_risk": goal_metrics.get("at_risk_count", 0),
            "avg_progress": goal_metrics.get("avg_progress_percentage", 0),
            "completion_rate": goal_metrics.get("completion_rate", 0),
        }

    def _analyze_strategic_progress(self, domains: dict[str, dict]) -> dict[str, Any]:
        """Strategic analysis for quarterly review"""
        return {
            "goal_achievement": domains["goals"].get("completion_rate", 0),
            "habit_consistency": domains["habits"].get("consistency_rate", 0),
            "principle_alignment": domains["principles"].get("alignment_score", 0),
            "recommendation": "Focus on maintaining habit consistency to support goal progress",
        }

    def _analyze_year_achievements(self, domains: dict[str, dict]) -> dict[str, Any]:
        """Analyze year achievements"""
        return {
            "goals_completed": domains["goals"].get("total_completed", 0),
            "habits_established": domains["habits"].get("total_active", 0),
            "principles_defined": domains["principles"].get("total_principles", 0),
            "key_decisions": domains["choices"].get("total_choices", 0),
        }

    def _identify_growth_opportunities(self, domains: dict[str, dict]) -> list[str]:
        """Identify areas for growth"""
        opportunities = []

        # Check goal completion rate
        if domains["goals"].get("completion_rate", 0) < 50:
            opportunities.append(
                "Improve goal achievement rate - consider breaking goals into smaller milestones"
            )

        # Check habit consistency
        if domains["habits"].get("consistency_rate", 0) < 70:
            opportunities.append("Strengthen habit consistency - focus on keystone habits")

        # Check principle alignment
        if domains["principles"].get("alignment_score", 0) < 70:
            opportunities.append("Align choices more closely with core principles")

        return opportunities

    def _correlate_expenses_productivity(
        self, finance_metrics: dict, tasks_metrics: dict
    ) -> dict[str, Any]:
        """Analyze correlation between expenses and productivity"""
        return {
            "correlation": "negative"
            if (
                finance_metrics.get("total_expenses", 0) > 1000
                and tasks_metrics.get("completion_rate", 0) < 50
            )
            else "neutral",
            "expense_level": finance_metrics.get("total_expenses", 0),
            "productivity_level": tasks_metrics.get("completion_rate", 0),
        }

    def _analyze_choice_principle_alignment(
        self, choices_metrics: dict, principles_metrics: dict
    ) -> dict[str, Any]:
        """Analyze how well choices align with principles"""
        return {
            "alignment_score": principles_metrics.get("alignment_score", 0),
            "choices_count": choices_metrics.get("total_choices", 0),
            "principles_count": principles_metrics.get("active_principles", 0),
        }

    def _analyze_goal_habit_support(
        self, goals_metrics: dict, habits_metrics: dict
    ) -> dict[str, Any]:
        """Analyze if habits support goals"""
        return {
            "goals_active": goals_metrics.get("total_active", 0),
            "habits_active": habits_metrics.get("total_active", 0),
            "support_ratio": habits_metrics.get("total_active", 0)
            / max(goals_metrics.get("total_active", 1), 1),
        }

    def _analyze_time_allocation(
        self, events_metrics: dict, tasks_metrics: dict, habits_metrics: dict
    ) -> dict[str, Any]:
        """Analyze how time is allocated"""
        return {
            "total_scheduled_hours": events_metrics.get("total_hours_scheduled", 0),
            "tasks_count": tasks_metrics.get("total_count", 0),
            "habits_count": habits_metrics.get("total_active", 0),
        }

    def _assess_domain_balance(self, domains: dict[str, dict]) -> dict[str, Any]:
        """Assess balance across domains"""
        activity_levels = self._rank_domains_by_activity(domains)

        # Check if any domain is significantly more active than others
        if len(activity_levels) > 0:
            top_activity = activity_levels[0]["activity_score"]
            bottom_activity = (
                activity_levels[-1]["activity_score"] if len(activity_levels) > 1 else 0
            )

            imbalance = top_activity > (bottom_activity * 3) if bottom_activity > 0 else False

            return {
                "balanced": not imbalance,
                "most_active_domain": activity_levels[0]["domain"],
                "least_active_domain": activity_levels[-1]["domain"]
                if len(activity_levels) > 1
                else None,
                "recommendation": "Consider increasing activity in underutilized domains"
                if imbalance
                else "Good balance across domains",
            }

        return {"balanced": True, "recommendation": "No activity detected"}

    # ========================================================================
    # CROSS-LAYER SYNTHESIS (Phase 3 - NEW)
    # ========================================================================

    def _synthesize_cross_layer_insights(
        self,
        layer1_domains: dict[str, dict],
        knowledge_metrics: dict[str, Any],
        journal_metrics: dict[str, Any],
        curriculum_metrics: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Synthesize insights across ALL 4 architectural layers.

        This is the core Phase 3 enhancement - identifies patterns and
        correlations that span multiple layers.

        Returns:
            dict with cross-layer insights:
            - knowledge_activity_correlation: Which activities drive embodiment?
            - journal_reflection_impact: How does reflection affect alignment?
            - learning_doing_alignment: Am I practicing what I'm learning?
            - curriculum_activity_mapping: Which domains support which learning paths?
        """
        return {
            "knowledge_activity_correlation": self._correlate_knowledge_activities(
                knowledge_metrics, layer1_domains
            ),
            "journal_reflection_impact": self._analyze_journal_impact(
                journal_metrics, layer1_domains, knowledge_metrics
            ),
            "learning_doing_alignment": self._assess_learning_doing_alignment(
                curriculum_metrics, layer1_domains
            ),
            "curriculum_activity_mapping": self._map_curriculum_to_activities(
                curriculum_metrics, knowledge_metrics, layer1_domains
            ),
        }

    def _correlate_knowledge_activities(
        self, knowledge_metrics: dict[str, Any], layer1_domains: dict[str, dict]
    ) -> dict[str, Any]:
        """
        Analyze which Layer 1 activities drive knowledge embodiment (Layer 0).

        This answers: "Which activities are making my knowledge REAL?"

        Returns correlation between activity levels and substance scores.
        """
        avg_substance = knowledge_metrics.get("avg_substance_score", 0.0)
        embodied_count = knowledge_metrics.get("embodied_knowledge", 0)
        total_knowledge = knowledge_metrics.get("total_knowledge_units", 0)

        # Calculate activity intensity for domains that drive substance
        habits_activity = layer1_domains["habits"].get("total_active", 0)
        tasks_activity = layer1_domains["tasks"].get("total_count", 0)
        events_activity = layer1_domains["events"].get("total_count", 0)

        # Substance-driving domains ranked by weight (from substance philosophy)
        # Habits: 0.10, Journals: 0.07, Choices: 0.07, Events: 0.05, Tasks: 0.05
        substance_drivers = {
            "habits": {
                "activity_level": habits_activity,
                "weight": 0.10,
                "contribution_estimate": habits_activity * 0.10,
            },
            "tasks": {
                "activity_level": tasks_activity,
                "weight": 0.05,
                "contribution_estimate": tasks_activity * 0.05,
            },
            "events": {
                "activity_level": events_activity,
                "weight": 0.05,
                "contribution_estimate": events_activity * 0.05,
            },
        }

        # Identify highest-contributing domain
        from core.utils.sort_functions import get_contribution_estimate

        top_driver = max(
            substance_drivers.items(), key=get_contribution_estimate, default=(None, {})
        )

        return {
            "avg_substance_score": round(avg_substance, 2),
            "embodiment_rate": round(embodied_count / max(total_knowledge, 1), 2),
            "substance_drivers": substance_drivers,
            "top_substance_driver": top_driver[0] if top_driver[0] else "none",
            "insight": self._generate_knowledge_activity_insight(
                avg_substance, substance_drivers, top_driver[0]
            ),
        }

    def _analyze_journal_impact(
        self,
        journal_metrics: dict[str, Any],
        layer1_domains: dict[str, dict],
        knowledge_metrics: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Analyze how Layer 2 (journals/reflection) impacts Layer 0 and Layer 1.

        This answers: "How is reflection helping me grow?"

        Correlates reflection frequency with knowledge substance and activity quality.
        """
        reflection_frequency = journal_metrics.get("reflection_frequency", 0.0)
        entry_count = journal_metrics.get("total_entries", 0)
        metacognition_score = journal_metrics.get("metacognition_score", 0.0)

        avg_substance = knowledge_metrics.get("avg_substance_score", 0.0)
        layer1_domains["tasks"].get("completion_rate", 0)
        habit_consistency = layer1_domains["habits"].get("consistency_rate", 0)

        # Estimate journal contribution to substance (weight: 0.07)
        journal_substance_contribution = entry_count * 0.07

        # Simple correlation heuristic:
        # Higher reflection frequency should correlate with higher substance & consistency
        reflection_quality = (
            "low"
            if reflection_frequency < 0.3
            else "medium"
            if reflection_frequency < 0.7
            else "high"
        )

        return {
            "reflection_frequency": round(reflection_frequency, 2),
            "reflection_quality": reflection_quality,
            "metacognition_score": round(metacognition_score, 2),
            "estimated_substance_contribution": round(journal_substance_contribution, 2),
            "correlations": {
                "reflection_to_substance": "positive"
                if (reflection_frequency > 0.5 and avg_substance > 0.5)
                else "neutral",
                "reflection_to_consistency": "positive"
                if (reflection_frequency > 0.5 and habit_consistency > 70)
                else "neutral",
            },
            "insight": self._generate_journal_impact_insight(
                reflection_frequency, reflection_quality, metacognition_score
            ),
        }

    def _assess_learning_doing_alignment(
        self, curriculum_metrics: dict[str, Any], layer1_domains: dict[str, dict]
    ) -> dict[str, Any]:
        """
        Assess alignment between what user is learning (Layer 0) and doing (Layer 1).

        This answers: "Am I practicing what I'm learning?"

        Compares active learning paths with activity patterns.
        """
        active_paths = curriculum_metrics.get("active_learning_paths", 0)
        in_progress_steps = curriculum_metrics.get("in_progress_learning_steps", 0)
        mastered_kus = curriculum_metrics.get("mastered_knowledge_units", 0)

        # Activity in knowledge-application domains
        tasks_count = layer1_domains["tasks"].get("total_count", 0)
        habits_count = layer1_domains["habits"].get("total_active", 0)
        events_count = layer1_domains["events"].get("total_count", 0)

        # Heuristic: If learning actively (steps > 0), expect corresponding activity
        learning_activity_ratio = (tasks_count + habits_count + events_count) / max(
            in_progress_steps, 1
        )

        alignment_status = (
            "high"
            if learning_activity_ratio >= 5
            else "medium"
            if learning_activity_ratio >= 2
            else "low"
        )

        return {
            "active_learning_paths": active_paths,
            "in_progress_steps": in_progress_steps,
            "mastered_knowledge": mastered_kus,
            "activity_levels": {
                "tasks": tasks_count,
                "habits": habits_count,
                "events": events_count,
            },
            "learning_activity_ratio": round(learning_activity_ratio, 1),
            "alignment_status": alignment_status,
            "insight": self._generate_learning_doing_insight(
                in_progress_steps, learning_activity_ratio, alignment_status
            ),
        }

    def _map_curriculum_to_activities(
        self,
        curriculum_metrics: dict[str, Any],
        knowledge_metrics: dict[str, Any],
        layer1_domains: dict[str, dict],
    ) -> dict[str, Any]:
        """
        Map Layer 0 curriculum elements to Layer 1 activity domains.

        This answers: "Which domains support which learning paths?"

        Shows how different activity types contribute to curriculum progress.
        """
        knowledge_by_domain = knowledge_metrics.get("knowledge_by_domain", {})
        curriculum_metrics.get("active_learning_paths", 0)

        # For each domain, estimate contribution to curriculum
        domain_curriculum_contributions = {}

        for domain_name, domain_metrics in layer1_domains.items():
            activity_count = 0

            if domain_name == Domain.TASKS.value:
                activity_count = domain_metrics.get("total_count", 0)
            elif domain_name == Domain.HABITS.value:
                activity_count = domain_metrics.get("total_active", 0)
            elif domain_name == Domain.EVENTS.value:
                activity_count = domain_metrics.get("total_count", 0)
            elif domain_name == Domain.CHOICES.value:
                activity_count = domain_metrics.get("total_choices", 0)

            # Simple contribution heuristic
            contribution_level = (
                "high" if activity_count >= 10 else "medium" if activity_count >= 5 else "low"
            )

            domain_curriculum_contributions[domain_name] = {
                "activity_count": activity_count,
                "contribution_level": contribution_level,
            }

        return {
            "knowledge_by_domain": knowledge_by_domain,
            "domain_contributions": domain_curriculum_contributions,
            "insight": "Activity patterns show learning is being applied across multiple domains",
        }

    # Helper methods for generating cross-layer insights

    def _generate_knowledge_activity_insight(
        self, avg_substance: float, substance_drivers: dict, top_driver: str | None
    ) -> str:
        """
        Generate insight about knowledge-activity correlation.

        Uses substance_drivers dict to show detailed breakdown of how different
        activity types contribute to knowledge embodiment.
        """
        if not top_driver:
            return "No significant activity detected for knowledge embodiment"

        # Build detailed breakdown from substance_drivers
        breakdown_parts = []
        for driver_type, contribution in sorted(
            substance_drivers.items(), key=operator.itemgetter(1), reverse=True
        ):
            if contribution > 0:
                percentage = contribution * 100
                breakdown_parts.append(f"{driver_type.title()}: {percentage:.0f}%")

        breakdown_text = ", ".join(breakdown_parts) if breakdown_parts else "no breakdown available"

        if avg_substance >= 0.7:
            return f"Excellent embodiment (avg: {avg_substance:.2f})! Primary drivers: {breakdown_text}"
        elif avg_substance >= 0.5:
            return f"Good progress (avg: {avg_substance:.2f}). Activity breakdown: {breakdown_text}. Focus more on {top_driver} to increase embodiment"
        else:
            return f"Low embodiment (avg: {avg_substance:.2f}). Current drivers: {breakdown_text}. Prioritize {top_driver} activities to make knowledge real"

    def _generate_journal_impact_insight(
        self, reflection_frequency: float, reflection_quality: str, metacognition_score: float
    ) -> str:
        """
        Generate insight about journal reflection impact.

        Incorporates metacognition_score to assess depth of self-awareness from journaling.
        """
        # Assess metacognition level
        meta_level = (
            "strong"
            if metacognition_score >= 0.7
            else "developing"
            if metacognition_score >= 0.4
            else "emerging"
        )

        if reflection_frequency >= 0.7:
            return f"High reflection frequency ({reflection_quality}, metacognition: {meta_level} at {metacognition_score:.2f}) is supporting growth. Your self-awareness is {'well-developed' if metacognition_score >= 0.7 else 'growing'}"
        elif reflection_frequency >= 0.3:
            return f"Regular reflection detected ({reflection_quality}, metacognition: {meta_level}). Increase frequency and depth for deeper insights (current meta-score: {metacognition_score:.2f})"
        else:
            return f"Low reflection activity (metacognition: {meta_level} at {metacognition_score:.2f}). Journaling can accelerate learning, alignment, and self-awareness"

    def _generate_learning_doing_insight(
        self, in_progress_steps: int, learning_activity_ratio: float, alignment_status: str
    ) -> str:
        """
        Generate insight about learning-doing alignment.

        Uses learning_activity_ratio to assess balance between theory and practice:
        - ~1.0: Balanced learning and application
        - >1.5: Theory-heavy (more learning than doing)
        - <0.7: Practice-heavy (more doing than structured learning)
        """
        if in_progress_steps == 0:
            return "No active learning paths. Consider starting a learning journey"

        # Assess learning-doing balance
        if learning_activity_ratio > 1.5:
            balance = "theory-heavy (more learning than practice)"
        elif learning_activity_ratio < 0.7:
            balance = "practice-heavy (more doing than structured learning)"
        else:
            balance = "well-balanced"

        if alignment_status == "high":
            return f"Great alignment! Activities match {in_progress_steps} active learning steps. Learning-doing ratio: {learning_activity_ratio:.2f} ({balance})"
        elif alignment_status == "medium":
            return f"Moderate alignment with {in_progress_steps} learning steps (ratio: {learning_activity_ratio:.2f}, {balance}). {'Apply knowledge more in practice' if learning_activity_ratio > 1.5 else 'Add structured learning to guide practice' if learning_activity_ratio < 0.7 else 'Increase application activities'}"
        else:
            return f"Low alignment. {in_progress_steps} learning steps need more practical application (current ratio: {learning_activity_ratio:.2f}, {balance}). {'Balance theory with practice' if learning_activity_ratio > 1.5 else 'Add learning structure to guide your practice'}"

    # ========================================================================
    # TEXT GENERATION
    # ========================================================================

    def _generate_cross_layer_summary_text(
        self,
        rankings: list[dict],
        knowledge_metrics: dict[str, Any],
        journal_metrics: dict[str, Any],
        cross_layer_insights: dict[str, Any],
    ) -> str:
        """
        Generate human-readable summary including ALL layers.

        NEW in Phase 3: Includes Layer 0 (knowledge), Layer 2 (journals),
        and cross-layer synthesis.
        """
        if not rankings:
            return "No activity detected across layers."

        # Layer 1 summary
        most_active = rankings[0]["domain"]
        summary = f"Most active domain: {most_active}. "

        # Layer 0 summary
        avg_substance = knowledge_metrics.get("avg_substance_score", 0.0)
        embodied = knowledge_metrics.get("embodied_knowledge", 0)
        summary += f"Knowledge embodiment: {int(avg_substance * 100)}% ({embodied} embodied). "

        # Layer 2 summary
        reflection_freq = journal_metrics.get("reflection_frequency", 0.0)
        entry_count = journal_metrics.get("total_entries", 0)
        summary += f"Reflection: {entry_count} entries ({round(reflection_freq, 1)}/day). "

        # Cross-layer insights
        knowledge_correlation = cross_layer_insights.get("knowledge_activity_correlation", {})
        top_driver = knowledge_correlation.get("top_substance_driver", "unknown")
        summary += f"Top substance driver: {top_driver}."

        return summary

    # ========================================================================
    # TEXT GENERATION (Layer 1 only - original methods)
    # ========================================================================

    def _generate_life_summary_text(self, rankings: list[dict], patterns: dict) -> str:
        """Generate human-readable life summary"""
        if not rankings:
            return "No activity detected across domains."

        most_active = rankings[0]["domain"]
        summary = f"Most active domain: {most_active}. "

        if patterns:
            summary += f"Detected {len(patterns)} cross-domain patterns. "

        return summary

    def _generate_monthly_review_text(
        self, rankings: list[dict], trends: dict, goal_progress: dict
    ) -> str:
        """
        Generate monthly review summary.

        Uses trends dict to show month-over-month changes in activity patterns.
        Trends typically contain direction indicators (improving/declining/stable)
        for various metrics.
        """
        summary = self._generate_life_summary_text(rankings, {})

        # Add trend insights if available
        if trends:
            trend_parts = []
            for metric, direction in trends.items():
                if isinstance(direction, str) and direction in ["improving", "declining", "stable"]:
                    trend_parts.append(f"{metric}: {direction}")

            if trend_parts:
                summary += f"Trends: {', '.join(trend_parts)}. "

        summary += f"Goal progress: {goal_progress['avg_progress']}%. "
        summary += f"On track: {goal_progress['on_track']}, At risk: {goal_progress['at_risk']}."
        return summary

    def _generate_quarterly_summary_text(self, rankings: list[dict], strategic: dict) -> str:
        """
        Generate quarterly summary.

        Uses rankings to show top-performing domains in the quarter,
        providing context for strategic metrics.
        """
        summary = ""

        # Add domain ranking context
        if rankings:
            top_domains = [r["domain"] for r in rankings[:3]]  # Top 3 domains
            summary += f"Top domains this quarter: {', '.join(top_domains)}. "

        summary += f"Goal achievement: {strategic['goal_achievement']}%. "
        summary += f"Habit consistency: {strategic['habit_consistency']}%. "
        summary += strategic["recommendation"]
        return summary

    def _generate_yearly_summary_text(
        self, rankings: list[dict], achievements: dict, opportunities: list[str]
    ) -> str:
        """
        Generate yearly summary.

        Uses rankings to show year-long domain activity patterns,
        highlighting areas of sustained focus and achievements.
        """
        summary = ""

        # Add year-long domain activity context
        if rankings:
            top_domains = [r["domain"] for r in rankings[:3]]  # Top 3 domains for the year
            summary += f"Year's focus areas: {', '.join(top_domains)}. "

        summary += f"Goals completed: {achievements['goals_completed']}. "
        summary += f"Habits established: {achievements['habits_established']}. "
        if opportunities:
            summary += f"Growth opportunities: {len(opportunities)}."
        return summary
