"""Weekly life summary rendering across all architectural layers."""

from typing import Any

from fasthtml.common import H3, Div, P

from ui.components import Card, CardBody, CardHeader, CardTitle
from ui.patterns.empty_state import EmptyState
from ui.patterns.page_header import PageHeader
from ui.patterns.section_header import SectionHeader
from ui.patterns.stats_grid import StatCard, StatItem, StatsGrid
from ui.tokens import Container


def render_weekly_life_summary(summary_data: dict[str, Any]) -> Any:
    """
    Render weekly life summary across ALL 4 layers.

    Shows Layer 1 activity, Layer 0 knowledge, Layer 2 reflection,
    and cross-layer insights.
    """
    if not summary_data:
        return EmptyState(
            title="No Data Available",
            description="No data available for this period.",
        )

    period = summary_data.get("period", {})
    start_date = period.get("start", "")
    end_date = period.get("end", "")

    total_activity = summary_data.get("total_activity_score", 0.0)
    summary_text = summary_data.get("summary", "")

    layer0_knowledge = summary_data.get("layer_0_knowledge", {})
    layer2_reflection = summary_data.get("layer_2_reflection", {})
    cross_layer_insights = summary_data.get("cross_layer_insights", {})

    return Div(
        PageHeader("Weekly Life Summary", subtitle=f"{start_date} to {end_date}"),
        StatCard(label="Overall Activity", value=str(int(total_activity)), color="primary"),
        Card(
            SectionHeader("Summary"),
            P(summary_text, cls="text-muted-foreground"),
            cls="bg-background shadow-xs mb-6 p-6",
        ),
        _render_knowledge_layer_card(layer0_knowledge),
        _render_reflection_layer_card(layer2_reflection),
        _render_cross_layer_insights_card(cross_layer_insights),
        cls=f"{Container.NARROW} p-6",
    )


def _render_knowledge_layer_card(layer0_data: dict[str, Any]) -> Any:
    """Render Layer 0 knowledge metrics card."""
    if not layer0_data:
        return Div()

    substance_metrics = layer0_data.get("substance_metrics", {})
    curriculum_progress = layer0_data.get("curriculum_progress", {})

    avg_substance = substance_metrics.get("avg_substance_score", 0.0)
    embodied = substance_metrics.get("embodied_knowledge", 0)
    active_paths = curriculum_progress.get("active_learning_paths", 0)
    in_progress_steps = curriculum_progress.get("in_progress_path_steps", 0)

    return Card(
        CardHeader(CardTitle("Layer 0: Knowledge & Learning")),
        CardBody(
            StatsGrid(
                [
                    StatItem(label="Avg Substance", value=f"{int(avg_substance * 100)}%"),
                    StatItem(label="Embodied", value=str(embodied)),
                    StatItem(label="Active Paths", value=str(active_paths)),
                    StatItem(label="In-Progress Steps", value=str(in_progress_steps)),
                ]
            ),
        ),
        cls="mb-6",
    )


def _render_reflection_layer_card(layer2_data: dict[str, Any]) -> Any:
    """Render Layer 2 reflection metrics card."""
    if not layer2_data:
        return Div()

    entry_count = layer2_data.get("total_entries", 0)
    reflection_frequency = layer2_data.get("reflection_frequency", 0.0)
    metacognition_score = layer2_data.get("metacognition_score", 0.0)
    top_themes = layer2_data.get("top_themes", [])

    return Card(
        CardHeader(CardTitle("Layer 2: Reflection & Journals")),
        CardBody(
            StatsGrid(
                [
                    StatItem(label="Entries", value=str(entry_count)),
                    StatItem(label="Frequency", value=f"{reflection_frequency:.1f}/day"),
                    StatItem(label="Metacognition", value=f"{int(metacognition_score * 100)}%"),
                ],
                cols=3,
                cls="mb-4",
            ),
            Div(
                P("Top Themes:", cls="font-medium mb-2"),
                P(
                    ", ".join(top_themes[:3]) if top_themes else "None",
                    cls="text-muted-foreground",
                ),
            ),
        ),
        cls="mb-6",
    )


def _render_cross_layer_insights_card(insights: dict[str, Any]) -> Any:
    """Render cross-layer synthesis insights card."""
    if not insights:
        return Div()

    knowledge_correlation = insights.get("knowledge_activity_correlation", {})
    journal_impact = insights.get("journal_reflection_impact", {})
    learning_doing = insights.get("learning_doing_alignment", {})

    return Card(
        CardHeader(CardTitle("Cross-Layer Insights")),
        CardBody(
            P(
                "Synthesis across all architectural layers:",
                cls="text-sm text-muted-foreground mb-4",
            ),
            Div(
                H3("Knowledge -> Activity", cls="font-semibold mb-2"),
                P(
                    knowledge_correlation.get("insight", ""),
                    cls="text-sm text-muted-foreground mb-4",
                ),
            ),
            Div(
                H3("Reflection Impact", cls="font-semibold mb-2"),
                P(journal_impact.get("insight", ""), cls="text-sm text-muted-foreground mb-4"),
            ),
            Div(
                H3("Learning <-> Doing", cls="font-semibold mb-2"),
                P(learning_doing.get("insight", ""), cls="text-sm text-muted-foreground"),
            ),
        ),
        cls="mb-6",
    )
