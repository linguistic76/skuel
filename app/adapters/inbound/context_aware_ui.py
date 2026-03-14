"""
Context-Aware UI Routes - Component-Based Interface
==================================================

Clean component-based UI routes for context-aware functionality.

Uses ui/patterns/ components (StatCard, ProgressMetric, RecommendationCard, SettingToggle).
"""

from adapters.inbound.auth import require_authenticated_user

__version__ = "2.1"

from typing import Any

from fasthtml.common import H1, H3, Div, P, Span

from core.utils.logging import get_logger
from ui.cards import Card
from ui.patterns.progress_metric import ProgressMetric
from ui.patterns.recommendation_card import RecommendationCard
from ui.patterns.setting_toggle import SettingToggle
from ui.patterns.stats_grid import StatCard

logger = get_logger("skuel.routes.context_aware.ui")


# ============================================================================
# REUSABLE UI COMPONENTS
# ============================================================================


class ContextAwareUIComponents:
    """
    Reusable component library for context-aware interface.

    ✅ MIGRATION STATUS:
    - Architecture: Component-based ✅ (already established)
    - Forms: None (display-only file)
    - Cards: Manual composition (CardGenerator-ready)
    - Migration: Minimal changes (architecture already optimal)

    Note: This file demonstrates that well-organized component-based
    architecture requires minimal changes for compliance.
    """

    @staticmethod
    def render_context_dashboard(context_data=None, insights=None) -> Any:
        """Main context-aware dashboard component"""
        if not context_data:
            context_data = {}

        return Div(
            H1("🧠 Context Intelligence", cls="text-3xl font-bold mb-6"),
            P(
                "AI-powered insights from your unified context",
                cls="text-lg text-muted-foreground mb-8",
            ),
            # Context overview cards
            ContextAwareUIComponents.render_context_overview(context_data),
            # Quick insights
            ContextAwareUIComponents.render_quick_insights(insights),
            # AI recommendations
            ContextAwareUIComponents.render_ai_recommendations(
                context_data.get("recommendations", [])
            ),
            # Context health
            ContextAwareUIComponents.render_context_health(context_data.get("health", {})),
            cls="container mx-auto p-6",
        )

    @staticmethod
    def render_context_overview(context_data) -> Any:
        """Context overview cards component"""
        return Div(
            StatCard(
                label="Productivity Score",
                value=f"{context_data.get('productivity_score', 0):.0%}",
                change="Based on recent patterns",
                color="primary",
            ),
            StatCard(
                label="Energy Level",
                value=f"{context_data.get('energy_level', 0):.0%}",
                change="Current state",
                color="secondary",
            ),
            StatCard(
                label="Context Health",
                value=f"{context_data.get('context_health', 0):.0%}",
                change="Overall system health",
                color="success",
            ),
            cls="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8",
        )

    @staticmethod
    def render_quick_insights(insights=None) -> Any:
        """Quick insights component"""
        if not insights:
            insights = []

        # CONSOLIDATION: This generic insight display should converge with
        # ui/insights/insight_card.py (PersistedInsight-based) when context
        # intelligence features mature to produce typed insight models.
        def _insight_card(text: str, confidence: float, category: str) -> Div:
            return Div(
                Div(
                    Span("💡", cls="text-xl mr-3"),
                    Div(
                        P(text, cls="text-foreground mb-2"),
                        Div(
                            Span(f"Confidence: {confidence:.0%}", cls="text-muted-foreground"),
                            Span(category, cls="text-primary font-medium"),
                            cls="flex gap-4 text-sm",
                        ),
                        cls="flex-1",
                    ),
                    cls="flex items-start",
                ),
                cls="p-4 bg-muted rounded shadow-sm",
            )

        return Card(
            H3("🔍 AI Insights", cls="text-xl font-semibold mb-4"),
            P(
                "Intelligent analysis of your patterns and context",
                cls="text-muted-foreground mb-4",
            ),
            Div(
                [
                    _insight_card(
                        text=insight.get("text", ""),
                        confidence=insight.get("confidence", 0),
                        category=insight.get("category", "General"),
                    )
                    for insight in insights[:5]
                ]
                if insights
                else [
                    P(
                        "Gathering insights from your context...",
                        cls="text-muted-foreground text-center py-8",
                    )
                ],
                cls="space-y-3",
            ),
            cls="p-6 mb-8",
        )

    @staticmethod
    def render_ai_recommendations(recommendations=None) -> Any:
        """AI recommendations component using shared RecommendationCard"""
        if not recommendations:
            recommendations = []

        return Card(
            H3("🎯 Smart Recommendations", cls="text-xl font-semibold mb-4"),
            P("Context-aware suggestions for optimization", cls="text-muted-foreground mb-4"),
            Div(
                [
                    RecommendationCard(
                        title=rec.get("title", "Recommendation"),
                        description=rec.get("description", ""),
                        impact=rec.get("impact", "Medium"),
                        effort=rec.get("effort", "Medium"),
                        action_label="Apply",
                        learn_more=True,
                    )
                    for rec in recommendations[:4]
                ]
                if recommendations
                else [
                    P("No recommendations available", cls="text-muted-foreground text-center py-8")
                ],
                cls="space-y-4",
            ),
            cls="p-6 mb-8",
        )

    @staticmethod
    def render_context_health(health_data) -> Any:
        """Context health component using shared ProgressMetric"""
        return Card(
            H3("⚡ Context System Health", cls="text-xl font-semibold mb-4"),
            P(
                "Real-time health of your context intelligence system",
                cls="text-muted-foreground mb-4",
            ),
            Div(
                ProgressMetric("Data Quality", health_data.get("data_quality", 0.8)),
                ProgressMetric("Prediction Accuracy", health_data.get("prediction_accuracy", 0.85)),
                ProgressMetric("System Performance", health_data.get("performance", 0.9)),
                ProgressMetric("User Satisfaction", health_data.get("satisfaction", 0.82)),
                cls="space-y-4",
            ),
            cls="p-6",
        )

    @staticmethod
    def render_context_analytics() -> Any:
        """Context analytics view component using shared components"""
        return Div(
            H1("📊 Context Analytics", cls="text-3xl font-bold mb-6"),
            P(
                "Deep insights into your context patterns and intelligence",
                cls="text-lg text-muted-foreground mb-8",
            ),
            Card(
                H3("Intelligence Metrics", cls="text-xl font-semibold mb-4"),
                Div(
                    StatCard(label="Context Awareness", value="87%", color="primary"),
                    StatCard(label="Adaptive Learning", value="84%", color="secondary"),
                    StatCard(label="Prediction Quality", value="89%", color="success"),
                    StatCard(label="Optimization Impact", value="76%", color="accent"),
                    cls="grid grid-cols-1 md:grid-cols-2 gap-6",
                ),
                cls="p-6 mb-6",
            ),
            Card(
                H3("Usage Patterns", cls="text-xl font-semibold mb-4"),
                P(
                    "Coming soon: Detailed analytics on context usage, effectiveness, and optimization opportunities.",
                    cls="text-muted-foreground",
                ),
                cls="p-6",
            ),
            cls="container mx-auto p-6",
        )

    @staticmethod
    def render_intelligence_settings() -> Any:
        """Intelligence settings view component using shared SettingToggle"""
        return Div(
            H1("⚙️ Intelligence Settings", cls="text-3xl font-bold mb-6"),
            P(
                "Configure your context intelligence preferences",
                cls="text-lg text-muted-foreground mb-8",
            ),
            Card(
                H3("Automation Preferences", cls="text-xl font-semibold mb-4"),
                Div(
                    SettingToggle(
                        "Auto-scheduling", "Automatically schedule tasks based on context", True
                    ),
                    SettingToggle(
                        "Predictive notifications", "Receive AI-powered timing suggestions", True
                    ),
                    SettingToggle(
                        "Smart recommendations", "Get context-aware optimization suggestions", True
                    ),
                    SettingToggle(
                        "Context learning", "Allow system to learn from your patterns", True
                    ),
                    cls="space-y-4",
                ),
                cls="p-6 mb-6",
            ),
            Card(
                H3("Privacy Controls", cls="text-xl font-semibold mb-4"),
                Div(
                    SettingToggle("Data collection", "Collect usage data for intelligence", True),
                    SettingToggle("Pattern analysis", "Analyze patterns for insights", True),
                    SettingToggle("Collaborative insights", "Share anonymized insights", False),
                    SettingToggle(
                        "External integrations", "Enable external service connections", False
                    ),
                    cls="space-y-4",
                ),
                cls="p-6",
            ),
            cls="container mx-auto p-6",
        )


# ============================================================================
# UI ROUTES
# ============================================================================


def create_context_aware_ui_routes(
    _app, rt, context_service
):  # _app unused, signature compatibility
    """Create component-based UI routes for context-aware functionality."""

    def _transform_dashboard_to_ui_data(
        dashboard: dict[str, Any],
        summary: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """
        Transform service data to UI component format.

        Service responses are optimized for API consumers (comprehensive, nested).
        UI components expect flat, presentation-ready data. This bridges the gap.
        """
        # Calculate derived metrics
        workload = dashboard.get("capacity", {}).get("current_workload", 0.5)
        productivity_score = max(
            0.0, min(1.0, 1.0 - workload)
        )  # Inverse: lower workload = higher available productivity

        # Map energy enum to 0.0-1.0 scale
        energy_raw = dashboard.get("capacity", {}).get("energy_level")
        energy_map = {"low": 0.3, "medium": 0.6, "high": 0.9}
        energy_level = energy_map.get(energy_raw, 0.75) if energy_raw else 0.75

        # Calculate health from alerts (each alert reduces health by 15%)
        alerts = summary.get("alerts", []) if summary else []
        context_health = max(0.0, 1.0 - (len(alerts) * 0.15))

        # Build recommendations from service data
        recommendations = []

        # Learning recommendations from predictions
        predictions = dashboard.get("predictions", {})
        if predictions and "next_learning_steps" in predictions:
            recommendations.extend(
                [
                    {
                        "title": f"Learn: {step.get('title', 'Knowledge Unit')}",
                        "description": f"Priority score: {step.get('priority_score', 0.7):.0%}",
                        "impact": "High" if step.get("priority_score", 0) > 0.8 else "Medium",
                        "effort": "Medium",
                    }
                    for step in predictions["next_learning_steps"][:2]
                ]
            )

        # Overdue task recommendation
        overdue_count = dashboard.get("tasks", {}).get("overdue_count", 0)
        if overdue_count > 0:
            recommendations.append(
                {
                    "title": "Address overdue tasks",
                    "description": f"{overdue_count} tasks are past their due date",
                    "impact": "High",
                    "effort": "Low" if overdue_count <= 3 else "Medium",
                }
            )

        # Habit maintenance recommendation
        at_risk_count = dashboard.get("habits", {}).get("at_risk_count", 0)
        if at_risk_count > 0:
            recommendations.append(
                {
                    "title": "Maintain habit streaks",
                    "description": f"{at_risk_count} habits need attention",
                    "impact": "Medium",
                    "effort": "Low",
                }
            )

        # Build health metrics
        health = {
            "data_quality": context_health,
            "prediction_accuracy": 0.84,  # Static (could be ML-derived later)
            "performance": productivity_score,
            "satisfaction": min(1.0, productivity_score + 0.1),
        }

        # Build UI context_data structure
        context_data = {
            "productivity_score": productivity_score,
            "energy_level": energy_level,
            "context_health": context_health,
            "recommendations": recommendations,
            "health": health,
        }

        # Build insights from alerts
        insights = [
            {
                "text": alert.get("message", ""),
                "confidence": 0.9 if alert.get("severity") == "high" else 0.7,
                "category": alert.get("type", "General").replace("_", " ").title(),
            }
            for alert in alerts[:3]
        ]

        # Add learning alignment insight
        learning = dashboard.get("learning", {})
        alignment = learning.get("life_path_alignment", 0)
        if alignment > 0:
            insights.append(
                {
                    "text": f"Life path alignment: {alignment:.0%}",
                    "confidence": 0.85,
                    "category": "Learning",
                }
            )

        return context_data, insights

    logger.info("✅ Context-Aware UI routes registered (component-based)")

    @rt("/context")
    async def context_dashboard(request) -> Any:
        """Main context intelligence dashboard"""
        user_uid = require_authenticated_user(request)

        try:
            # Fetch dashboard data from service
            dashboard_result = await context_service.get_context_dashboard(
                user_uid=user_uid,
                include_predictions=True,
                time_window="7d",
            )

            # Handle service errors gracefully
            if dashboard_result.is_error:
                return Div(
                    H1("🧠 Context Intelligence", cls="text-3xl font-bold mb-6"),
                    Card(
                        P(
                            f"Failed to load context dashboard: {dashboard_result.expect_error().message}",
                            cls="text-error",
                        ),
                        cls="p-6",
                    ),
                    cls="container mx-auto p-6",
                )

            dashboard = dashboard_result.value

            # Fetch summary for insights (optional - enhances UI, but dashboard is sufficient)
            summary_result = await context_service.get_context_summary(
                user_uid=user_uid,
                include_insights=True,
            )
            summary = summary_result.value if not summary_result.is_error else None

            # Transform service data to UI format
            context_data, insights = _transform_dashboard_to_ui_data(dashboard, summary)

            # Render using existing UI components (no changes needed)
            return ContextAwareUIComponents.render_context_dashboard(context_data, insights)

        except Exception as e:
            logger.error(f"Unexpected error loading context dashboard: {e}")
            return Div(
                H1("🧠 Context Intelligence", cls="text-3xl font-bold mb-6"),
                Card(P(f"Unexpected error: {e!s}", cls="text-error"), cls="p-6"),
                cls="container mx-auto p-6",
            )

    # ========================================================================
    # PLACEHOLDER ROUTES - Pure UI components, no service integration needed
    # ========================================================================
    # These routes render static UI components. Future enhancement: wire
    # analytics service when requirements are clearer.

    @rt("/context/analytics")
    async def context_analytics(_request) -> Any:
        """Context analytics and metrics view"""
        # Intentionally uses _request - no user-specific data needed yet
        return ContextAwareUIComponents.render_context_analytics()

    @rt("/context/settings")
    async def context_settings(_request) -> Any:
        """Context intelligence settings"""
        # Intentionally uses _request - no user-specific data needed yet
        return ContextAwareUIComponents.render_intelligence_settings()

    @rt("/context/insights")
    async def context_insights(_request) -> Any:
        """Detailed context insights view"""
        # Intentionally uses _request - no user-specific data needed yet
        return Div(
            H1("🧠 Context Insights", cls="text-3xl font-bold mb-6"),
            P(
                "Deep dive into your context intelligence patterns",
                cls="text-lg text-muted-foreground mb-8",
            ),
            Card(
                H3("Learning Patterns", cls="text-xl font-semibold mb-4"),
                P(
                    "Your learning effectiveness varies throughout the day:",
                    cls="text-muted-foreground mb-4",
                ),
                Div(
                    P("🌅 Morning (9-11am): Peak comprehension and retention", cls="mb-2"),
                    P("☀️ Afternoon (2-4pm): Good for application and practice", cls="mb-2"),
                    P("🌙 Evening (7-9pm): Best for review and reflection", cls="mb-2"),
                    cls="bg-blue-50 p-4 rounded",
                ),
                cls="p-6 mb-6",
            ),
            Card(
                H3("Productivity Insights", cls="text-xl font-semibold mb-4"),
                P(
                    "Your productivity patterns show clear optimization opportunities:",
                    cls="text-muted-foreground mb-4",
                ),
                Div(
                    P(
                        "⚡ Energy management: Protect morning hours for high-cognitive tasks",
                        cls="mb-2",
                    ),
                    P(
                        "🔄 Context switching: 23% productivity loss when switching between unrelated tasks",
                        cls="mb-2",
                    ),
                    P(
                        "📅 Schedule optimization: Batch similar tasks for 31% efficiency gain",
                        cls="mb-2",
                    ),
                    cls="bg-green-50 p-4 rounded",
                ),
                cls="p-6",
            ),
            cls="container mx-auto p-6",
        )

    return []  # Routes registered via @rt() decorators (no objects returned)


# Export the route creation function
__all__ = ["create_context_aware_ui_routes"]
