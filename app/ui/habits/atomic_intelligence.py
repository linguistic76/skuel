"""
Atomic Habits Intelligence Components
================================================

Implements intelligence features:
1. Pattern recognition (success/failure patterns)
2. System health diagnostics UI
3. Habit velocity tracking visualization
4. Goal impact analysis display

Uses backend intelligence methods from Goal and Habit domain models.
"""

from typing import Any

from fasthtml.common import H3, H4, Div, Li, P, Span, Tbody, Td, Th, Thead, Tr, Ul

from ui.buttons import Button, ButtonT
from ui.cards import Card, CardBody
from ui.data import Table
from ui.feedback import Progress


class AtomicHabitsIntelligence:
    """
    intelligence components for behavioral insights and analytics.
    """

    # ========================================================================
    # COMPONENT 1: PATTERN RECOGNITION
    # ========================================================================

    @staticmethod
    def render_pattern_recognition(habit_data: dict) -> Any:
        """
        Display AI-detected success and failure patterns.

        Args:
            habit_data: Dict with:
                - name: str
                - success_patterns: List[Dict] with 'pattern', 'confidence', 'recommendation'
                - failure_patterns: List[Dict] with 'pattern', 'confidence', 'recommendation'
                - total_completions: int
        """
        name = habit_data.get("name", "Habit")
        success_patterns = habit_data.get("success_patterns", [])
        failure_patterns = habit_data.get("failure_patterns", [])
        total_completions = habit_data.get("total_completions", 0)

        return Card(
            CardBody(
                H3("🧠 Pattern Recognition", cls="text-xl font-bold mb-4"),
                # Overview
                P(
                    f"{name} - {total_completions} completions analyzed",
                    cls="text-muted-foreground mb-6",
                ),
                # Success patterns
                Div(
                    H4("✅ SUCCESS PATTERNS", cls="text-lg font-semibold text-green-700 mb-3"),
                    (
                        Div(
                            *[
                                AtomicHabitsIntelligence._render_pattern(p, "success")
                                for p in success_patterns
                            ],
                            cls="space-y-3",
                        )
                        if success_patterns
                        else P(
                            "No success patterns detected yet. Complete more habits to build pattern data.",
                            cls="text-sm text-muted-foreground italic",
                        )
                    ),
                    cls="mb-6",
                ),
                # Failure patterns
                Div(
                    H4("⚠️ RISK PATTERNS", cls="text-lg font-semibold text-red-700 mb-3"),
                    (
                        Div(
                            *[
                                AtomicHabitsIntelligence._render_pattern(p, "failure")
                                for p in failure_patterns
                            ],
                            cls="space-y-3",
                        )
                        if failure_patterns
                        else P(
                            "No failure patterns detected yet.",
                            cls="text-sm text-muted-foreground italic",
                        )
                    ),
                    cls="mb-6",
                ),
                # Recommendations
                (
                    Div(
                        H4("💡 Recommended Adjustments:", cls="text-lg font-semibold mb-3"),
                        Ul(
                            *[
                                Li(rec, cls="text-sm")
                                for rec in AtomicHabitsIntelligence._extract_recommendations(
                                    success_patterns, failure_patterns
                                )
                            ],
                            cls="list-disc list-inside space-y-2 text-muted-foreground",
                        ),
                        cls="bg-yellow-50 p-4 rounded-lg",
                    )
                    if (success_patterns or failure_patterns)
                    else None
                ),
            ),
        )

    @staticmethod
    def _render_pattern(pattern: dict, pattern_type: str) -> Any:
        """Render a single pattern card"""
        text = pattern.get("pattern", "Unknown pattern")
        confidence = pattern.get("confidence", 0)
        recommendation = pattern.get("recommendation", "")

        bg_color = "bg-green-50" if pattern_type == "success" else "bg-red-50"
        border_color = (
            "border-l-4 border-green-500"
            if pattern_type == "success"
            else "border-l-4 border-red-500"
        )

        return Div(
            Div(
                P(text, cls="font-medium mb-1"),
                P(f"Confidence: {int(confidence * 100)}%", cls="text-xs text-muted-foreground"),
                cls="mb-2",
            ),
            (
                P(f"→ {recommendation}", cls="text-sm text-muted-foreground italic")
                if recommendation
                else None
            ),
            cls=f"p-3 {bg_color} rounded {border_color}",
        )

    @staticmethod
    def _extract_recommendations(
        success_patterns: list[dict], failure_patterns: list[dict]
    ) -> list[str]:
        """Extract unique recommendations from patterns"""
        recommendations = [
            p["recommendation"] for p in success_patterns if p.get("recommendation")
        ] + [p["recommendation"] for p in failure_patterns if p.get("recommendation")]
        return list(dict.fromkeys(recommendations))  # Remove duplicates while preserving order

    # ========================================================================
    # COMPONENT 2: SYSTEM HEALTH DIAGNOSTICS UI
    # ========================================================================

    @staticmethod
    def render_system_health_diagnostics(system_health: dict) -> Any:
        """
        Comprehensive system health diagnostics for a goal.

        Args:
            system_health: Dict from Goal.diagnose_system_health() with:
                - system_strength: float
                - diagnosis: str
                - warnings: List[str]
                - recommendations: List[str]
                - system_exists: bool
                - habit_breakdown: Dict
        """
        if not system_health.get("system_exists", False):
            return AtomicHabitsIntelligence._render_no_system_warning()

        strength = system_health.get("system_strength", 0)
        diagnosis = system_health.get("diagnosis", "Unknown")
        warnings = system_health.get("warnings", [])
        recommendations = system_health.get("recommendations", [])
        breakdown = system_health.get("habit_breakdown", {})

        # Determine severity
        if strength >= 0.8:
            severity_color = "green"
            severity_icon = "🎉"
            severity_bg = "bg-green-50"
        elif strength >= 0.6:
            severity_color = "blue"
            severity_icon = "👍"
            severity_bg = "bg-blue-50"
        elif strength >= 0.4:
            severity_color = "yellow"
            severity_icon = "⚠️"
            severity_bg = "bg-yellow-50"
        else:
            severity_color = "red"
            severity_icon = "❌"
            severity_bg = "bg-red-50"

        return Card(
            CardBody(
                H3("🏥 System Health Diagnostics", cls="text-xl font-bold mb-4"),
                # Overall diagnosis
                Div(
                    Div(
                        Span(
                            f"{severity_icon} {int(strength * 100)}%",
                            cls=f"text-3xl font-bold text-{severity_color}-700",
                        ),
                        P("System Strength", cls="text-sm text-muted-foreground"),
                        cls="text-center",
                    ),
                    P(diagnosis, cls="text-center text-muted-foreground font-medium mt-2"),
                    cls=f"p-6 {severity_bg} rounded-lg mb-6",
                ),
                # Warnings (if any)
                (
                    Div(
                        H4("⚠️ WARNINGS", cls="text-lg font-semibold text-red-700 mb-3"),
                        Ul(
                            *[Li(warning, cls="text-sm") for warning in warnings],
                            cls="list-disc list-inside space-y-2 text-red-700",
                        ),
                        cls="bg-red-50 p-4 rounded-lg mb-6",
                    )
                    if warnings
                    else None
                ),
                # Habit system breakdown
                Div(
                    H4("📊 Habit System Breakdown", cls="text-lg font-semibold mb-3"),
                    Table(
                        Thead(
                            Tr(
                                Th("Essentiality Level", cls="text-left"),
                                Th("Count", cls="text-center"),
                                Th("Status", cls="text-left"),
                            )
                        ),
                        Tbody(
                            Tr(
                                Td("🔴 ESSENTIAL", cls="font-medium"),
                                Td(str(breakdown.get("essential", 0)), cls="text-center font-bold"),
                                Td(
                                    Span("✅ Defined", cls="text-green-600")
                                    if breakdown.get("essential", 0) > 0
                                    else Span("❌ Missing", cls="text-red-600")
                                ),
                            ),
                            Tr(
                                Td("🟠 CRITICAL", cls="font-medium"),
                                Td(str(breakdown.get("critical", 0)), cls="text-center font-bold"),
                                Td(
                                    Span("✅ Defined", cls="text-green-600")
                                    if breakdown.get("critical", 0) > 0
                                    else Span("⚠️ Consider adding", cls="text-yellow-600")
                                ),
                            ),
                            Tr(
                                Td("🟡 SUPPORTING", cls="font-medium"),
                                Td(
                                    str(breakdown.get("supporting", 0)), cls="text-center font-bold"
                                ),
                                Td(
                                    Span(
                                        f"{breakdown.get('supporting', 0)} habits",
                                        cls="text-muted-foreground",
                                    )
                                ),
                            ),
                            Tr(
                                Td("🟢 OPTIONAL", cls="font-medium"),
                                Td(str(breakdown.get("optional", 0)), cls="text-center font-bold"),
                                Td(
                                    Span(
                                        f"{breakdown.get('optional', 0)} habits",
                                        cls="text-muted-foreground",
                                    )
                                ),
                            ),
                            Tr(
                                Td("TOTAL", cls="font-bold border-t-2"),
                                Td(
                                    str(breakdown.get("total", 0)),
                                    cls="text-center font-bold border-t-2",
                                ),
                                Td("", cls="border-t-2"),
                            ),
                            cls="divide-y",
                        ),
                        cls="w-full text-sm",
                    ),
                    cls="bg-muted p-4 rounded-lg mb-6",
                ),
                # Recommendations
                (
                    Div(
                        H4("💡 RECOMMENDATIONS", cls="text-lg font-semibold text-blue-700 mb-3"),
                        Ul(
                            *[Li(rec, cls="text-sm") for rec in recommendations],
                            cls="list-disc list-inside space-y-2 text-muted-foreground",
                        ),
                        cls="bg-blue-50 p-4 rounded-lg",
                    )
                    if recommendations
                    else None
                ),
            ),
        )

    @staticmethod
    def _render_no_system_warning() -> Any:
        """Warning shown when goal has no habit system"""
        return Card(
            CardBody(
                Div(
                    H3("❌ No Habit System Defined", cls="text-xl font-bold text-red-700 mb-4"),
                    P(
                        "This goal has no supporting habits. Without a system, achievement is wishful thinking.",
                        cls="text-muted-foreground mb-4",
                    ),
                    P(
                        '"You do not rise to the level of your goals. You fall to the level of your systems."',
                        cls="italic text-muted-foreground mb-4",
                    ),
                    P("— James Clear, Atomic Habits", cls="text-sm text-muted-foreground mb-6"),
                    Button(
                        "Define Essential Habits →",
                        variant=ButtonT.primary,
                        hx_get="/goals/habits/configure",
                        hx_target="#modal",
                    ),
                    cls="text-center",
                ),
            ),
            cls="bg-red-50",
        )

    # ========================================================================
    # COMPONENT 3: HABIT VELOCITY TRACKING
    # ========================================================================

    @staticmethod
    def render_velocity_tracking(velocity_data: dict) -> Any:
        """
        Visualize habit velocity over time.

        Args:
            velocity_data: Dict with:
                - current_velocity: float
                - velocity_trend: List[Dict] with 'week', 'velocity'
                - weighted_breakdown: Dict with 'essential', 'critical', 'supporting', 'optional'
                - total_weighted_completions: int
        """
        current = velocity_data.get("current_velocity", 0)
        trend = velocity_data.get("velocity_trend", [])
        breakdown = velocity_data.get("weighted_breakdown", {})
        total_weighted = velocity_data.get("total_weighted_completions", 0)

        # Velocity rating
        if current >= 100:
            rating = "EXCEPTIONAL"
            rating_icon = "🚀"
            rating_color = "text-green-700"
            rating_bg = "bg-green-50"
        elif current >= 50:
            rating = "HIGH"
            rating_icon = "⚡"
            rating_color = "text-blue-700"
            rating_bg = "bg-blue-50"
        elif current >= 20:
            rating = "STEADY"
            rating_icon = "📈"
            rating_color = "text-yellow-700"
            rating_bg = "bg-yellow-50"
        else:
            rating = "LOW"
            rating_icon = "📉"
            rating_color = "text-red-700"
            rating_bg = "bg-red-50"

        return Card(
            CardBody(
                H3("🚀 Habit Velocity Tracking", cls="text-xl font-bold mb-4"),
                # Current velocity gauge
                Div(
                    Div(
                        Span(f"{current:.1f}", cls=f"text-4xl font-bold {rating_color}"),
                        P("Current Velocity", cls="text-sm text-muted-foreground"),
                        cls="text-center mb-2",
                    ),
                    Div(
                        Span(
                            f"{rating_icon} {rating}", cls=f"text-lg font-semibold {rating_color}"
                        ),
                        cls="text-center",
                    ),
                    cls=f"p-6 {rating_bg} rounded-lg mb-6",
                ),
                # Velocity explanation
                Div(
                    H4("📊 Weighted Breakdown", cls="text-lg font-semibold mb-3"),
                    P(
                        "Velocity measures progress rate using weighted habit completions:",
                        cls="text-sm text-muted-foreground mb-3",
                    ),
                    Table(
                        Tbody(
                            Tr(
                                Td("🔴 Essential (3x weight)", cls="text-sm"),
                                Td(
                                    f"{breakdown.get('essential', 0)} completions",
                                    cls="text-sm text-right",
                                ),
                                Td(
                                    f"= {breakdown.get('essential', 0) * 3} points",
                                    cls="text-sm text-right font-semibold",
                                ),
                            ),
                            Tr(
                                Td("🟠 Critical (2x weight)", cls="text-sm"),
                                Td(
                                    f"{breakdown.get('critical', 0)} completions",
                                    cls="text-sm text-right",
                                ),
                                Td(
                                    f"= {breakdown.get('critical', 0) * 2} points",
                                    cls="text-sm text-right font-semibold",
                                ),
                            ),
                            Tr(
                                Td("🟡 Supporting (1x weight)", cls="text-sm"),
                                Td(
                                    f"{breakdown.get('supporting', 0)} completions",
                                    cls="text-sm text-right",
                                ),
                                Td(
                                    f"= {breakdown.get('supporting', 0)} points",
                                    cls="text-sm text-right font-semibold",
                                ),
                            ),
                            Tr(
                                Td("🟢 Optional (0.5x weight)", cls="text-sm"),
                                Td(
                                    f"{breakdown.get('optional', 0)} completions",
                                    cls="text-sm text-right",
                                ),
                                Td(
                                    f"= {breakdown.get('optional', 0) * 0.5} points",
                                    cls="text-sm text-right font-semibold",
                                ),
                            ),
                            Tr(
                                Td("TOTAL", cls="text-sm font-bold border-t-2"),
                                Td("", cls="border-t-2"),
                                Td(
                                    f"{total_weighted} points",
                                    cls="text-sm text-right font-bold border-t-2",
                                ),
                            ),
                            cls="divide-y",
                        ),
                        cls="w-full",
                    ),
                    P(
                        f"Velocity = Total Points / 2 = {total_weighted} / 2 = {current:.1f}",
                        cls="text-xs text-muted-foreground mt-3 italic text-right",
                    ),
                    cls="bg-muted p-4 rounded-lg mb-6",
                ),
                # Velocity trend (if available)
                (
                    Div(
                        H4("📈 Velocity Trend", cls="text-lg font-semibold mb-3"),
                        AtomicHabitsIntelligence._render_velocity_chart(trend),
                        cls="mb-6",
                    )
                    if trend
                    else None
                ),
                # Insights
                Div(
                    H4("💡 Velocity Insights", cls="text-lg font-semibold mb-3"),
                    Ul(
                        *[
                            Li(insight, cls="text-sm")
                            for insight in AtomicHabitsIntelligence._generate_velocity_insights(
                                current, breakdown
                            )
                        ],
                        cls="list-disc list-inside space-y-2 text-muted-foreground",
                    ),
                    cls="bg-blue-50 p-4 rounded-lg",
                ),
            ),
        )

    @staticmethod
    def _render_velocity_chart(trend: list[dict]) -> Any:
        """Render simple text-based velocity trend chart"""
        if not trend:
            return P("No trend data available yet", cls="text-sm text-muted-foreground italic")

        # Find max velocity for scaling
        max_velocity = max([t["velocity"] for t in trend], default=1)

        chart_rows = []
        for entry in trend[-8:]:  # Last 8 weeks
            week = entry.get("week", "Week")
            velocity = entry.get("velocity", 0)
            bar_width = int((velocity / max_velocity) * 100) if max_velocity > 0 else 0

            chart_rows.append(
                Div(
                    Span(week, cls="text-xs text-muted-foreground w-16"),
                    Div(
                        Div(style=f"width: {bar_width}%", cls="bg-blue-500 h-4 rounded"),
                        cls="flex-1 bg-secondary rounded h-4 mx-2",
                    ),
                    Span(
                        f"{velocity:.1f}",
                        cls="text-xs font-semibold text-muted-foreground w-12 text-right",
                    ),
                    cls="flex items-center mb-2",
                )
            )

        return Div(*chart_rows, cls="space-y-1")

    @staticmethod
    def _generate_velocity_insights(velocity: float, breakdown: dict) -> list[str]:
        """Generate insights based on velocity and breakdown"""
        insights = []

        if velocity >= 100:
            insights.append(
                "Exceptional momentum! You're executing your system at a very high level."
            )
        elif velocity >= 50:
            insights.append("Strong momentum. Your habit system is working well.")
        elif velocity >= 20:
            insights.append("Steady progress. Maintain consistency to increase velocity.")
        else:
            insights.append(
                "Low velocity detected. Focus on completing essential habits to build momentum."
            )

        essential = breakdown.get("essential", 0)
        critical = breakdown.get("critical", 0)

        if essential == 0:
            insights.append(
                "No essential habit completions this period - prioritize your most important habits."
            )
        elif essential > 0 and critical == 0:
            insights.append(
                "Essential habits are getting done. Consider adding critical habits for robustness."
            )

        return insights

    # ========================================================================
    # COMPONENT 4: GOAL IMPACT ANALYSIS
    # ========================================================================

    @staticmethod
    def render_goal_impact_analysis(impact_data: dict) -> Any:
        """
        Show how habits are impacting goal achievement probability.

        Args:
            impact_data: Dict with:
                - goal_title: str
                - habits: List[Dict] with 'name', 'essentiality', 'impact_score', 'consistency'
                - overall_impact: float
                - achievement_probability: float
        """
        title = impact_data.get("goal_title", "Goal")
        habits = impact_data.get("habits", [])
        overall = impact_data.get("overall_impact", 0)
        probability = impact_data.get("achievement_probability", 0)

        # Probability rating
        if probability >= 0.8:
            prob_color = "green"
            prob_icon = "🎯"
            prob_label = "HIGHLY LIKELY"
        elif probability >= 0.6:
            prob_color = "blue"
            prob_icon = "👍"
            prob_label = "LIKELY"
        elif probability >= 0.4:
            prob_color = "yellow"
            prob_icon = "⚠️"
            prob_label = "MODERATE"
        else:
            prob_color = "red"
            prob_icon = "❌"
            prob_label = "UNLIKELY"

        return Card(
            CardBody(
                H3("🎯 Goal Impact Analysis", cls="text-xl font-bold mb-4"),
                P(title, cls="text-lg text-muted-foreground mb-6"),
                # Achievement probability
                Div(
                    Div(
                        Span(
                            f"{int(probability * 100)}%",
                            cls=f"text-4xl font-bold text-{prob_color}-700",
                        ),
                        P("Achievement Probability", cls="text-sm text-muted-foreground"),
                        cls="text-center mb-2",
                    ),
                    Span(
                        f"{prob_icon} {prob_label}",
                        cls=f"text-lg font-semibold text-{prob_color}-700 text-center block",
                    ),
                    cls=f"p-6 bg-{prob_color}-50 rounded-lg mb-6",
                ),
                # Habit contributions
                Div(
                    H4("📊 Habit Contributions", cls="text-lg font-semibold mb-4"),
                    (
                        Div(
                            *[AtomicHabitsIntelligence._render_habit_impact(h) for h in habits],
                            cls="space-y-3",
                        )
                        if habits
                        else P(
                            "No habits linked to this goal yet.",
                            cls="text-sm text-muted-foreground italic",
                        )
                    ),
                    cls="mb-6",
                ),
                # Overall impact
                Div(
                    H4("💪 Overall Habit System Impact", cls="text-lg font-semibold mb-3"),
                    P(
                        f"Your habit system is contributing {int(overall * 100)}% toward goal achievement.",
                        cls="text-sm text-muted-foreground mb-3",
                    ),
                    Progress(value=int(overall * 100), cls="w-full"),
                    cls="bg-muted p-4 rounded-lg",
                ),
            ),
        )

    @staticmethod
    def _render_habit_impact(habit: dict) -> Any:
        """Render single habit's impact on goal"""
        name = habit.get("name", "Unknown Habit")
        essentiality = habit.get("essentiality", "supporting")
        impact = habit.get("impact_score", 0)
        consistency = habit.get("consistency", 0)

        # Essentiality colors
        from ui.badge_classes import essentiality_styled

        icon, border, bg = essentiality_styled(essentiality)

        return Div(
            Div(
                Span(f"{icon} {name}", cls="font-medium text-sm"),
                Span(essentiality.upper(), cls="text-xs text-muted-foreground"),
                cls="flex justify-between items-center mb-2",
            ),
            Div(
                P(f"Impact Score: {int(impact * 100)}%", cls="text-xs text-muted-foreground mb-1"),
                Progress(value=int(impact * 100), cls="w-full mb-1"),
                P(f"Consistency: {int(consistency * 100)}%", cls="text-xs text-muted-foreground"),
                cls="px-2",
            ),
            cls=f"p-3 {bg} rounded border-l-4 {border}",
        )


# Export
__all__ = ["AtomicHabitsIntelligence"]
