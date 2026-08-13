"""Life Path alignment dashboard rendering."""

from typing import Any

from fasthtml.common import Div, P, Span

from core.models.enums.principle_enums import AlignmentLevel
from ui.components import Card, CardBody, CardHeader, CardTitle
from ui.patterns.empty_state import EmptyState
from ui.patterns.page_header import PageHeader
from ui.patterns.stats_grid import StatCard, StatItem, StatsGrid
from ui.tokens import Container


def render_life_path_alignment_dashboard(alignment_data: dict[str, Any]) -> Any:
    """
    Render Life Path alignment dashboard.

    Shows alignment score, knowledge embodiment breakdown,
    domain contributions, gaps, and recommendations.
    """
    if not alignment_data or not alignment_data.get("life_path_uid"):
        return EmptyState(
            title="No Life Path Yet",
            description="Set your Life Path to track alignment.",
            action_text="Set Life Path",
            action_href="/lifepath",
            icon="\U0001f9ed",
        )

    life_path_title = alignment_data.get("life_path_title", "Unknown")
    alignment_score = alignment_data.get("alignment_score", 0.0)
    knowledge_count = alignment_data.get("knowledge_count", 0)
    embodied = alignment_data.get("embodied_knowledge", 0)
    theoretical = alignment_data.get("theoretical_knowledge", 0)
    domain_contributions = alignment_data.get("domain_contributions", {})
    gaps = alignment_data.get("gaps", [])
    recommendations = alignment_data.get("recommendations", [])

    score_color = AlignmentLevel.from_score(alignment_score).get_color()
    score_percentage = int(alignment_score * 100)

    return Div(
        PageHeader(f"Life Path: {life_path_title}"),
        StatCard(label="Alignment Score", value=f"{score_percentage}%", color=score_color),
        # Knowledge Breakdown
        Card(
            CardHeader(CardTitle("Knowledge Embodiment")),
            CardBody(
                StatsGrid(
                    [
                        StatItem(label="Total Knowledge", value=str(knowledge_count)),
                        # Band edges transcribed from the service's own
                        # thresholds (EMBODIED_THRESHOLD / APPLIED_THRESHOLD) —
                        # the label used to read "<0.5" over a count the service
                        # computed at <0.3.
                        StatItem(label="Embodied (0.8+)", value=str(embodied)),
                        StatItem(label="Theoretical (<0.3)", value=str(theoretical)),
                    ],
                    cols=3,
                ),
            ),
            cls="mb-6",
        ),
        # Channel Contributions — where this learner's substance comes from
        Card(
            CardHeader(CardTitle("Where Your Alignment Comes From")),
            CardBody(
                Div(
                    *[
                        _render_domain_contribution_bar(domain, contribution)
                        for domain, contribution in domain_contributions.items()
                    ],
                    cls="space-y-3",
                )
                if domain_contributions
                else EmptyState(title="No domain activity detected"),
            ),
            cls="mb-6",
        ),
        # Gaps
        Card(
            CardHeader(CardTitle("Knowledge Gaps")),
            CardBody(
                Div(
                    *[_render_gap_item(gap) for gap in gaps[:5]],
                    cls="space-y-2",
                )
                if gaps
                else P("No gaps detected - excellent embodiment!", cls="text-success"),
            ),
            cls="mb-6",
        ),
        # Recommendations
        Card(
            CardHeader(CardTitle("Recommendations")),
            CardBody(
                Div(*[P(f"• {rec}", cls="mb-2") for rec in recommendations], cls="space-y-1")
                if recommendations
                else P("Keep up the great work!", cls="text-success"),
            ),
        ),
        cls=f"{Container.NARROW} p-6",
    )


def _render_domain_contribution_bar(domain: str, contribution: float) -> Any:
    """Render single domain contribution bar."""
    contribution_percentage = int(contribution * 100)
    bar_width = f"{contribution_percentage}%"

    return Div(
        Div(
            Span(domain.title(), cls="font-medium"),
            Span(f"{contribution_percentage}%", cls="ml-auto text-muted-foreground"),
            cls="flex justify-between mb-1",
        ),
        Div(
            Div(cls="bg-primary h-2 rounded-sm", style=f"width: {bar_width}"),
            cls="bg-muted h-2 rounded-sm overflow-hidden",
        ),
    )


def _render_gap_item(gap: dict[str, Any]) -> Any:
    """Render single knowledge gap item."""
    title = gap.get("title", "Unknown")
    substance = gap.get("substance", 0.0)

    return Div(
        Span(title, cls="font-medium"),
        Span(f"({substance:.1f} substance)", cls="ml-2 text-muted-foreground text-sm"),
        cls="p-2 bg-error/10 rounded-sm",
    )
