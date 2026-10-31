"""LifePath vision capture and recommendations pages."""

from fasthtml.common import FT, H3, Div, Form, Input, P, Span

from core.ports.query_types import LpMatchResult, SavedVision
from ui.components import Button, ButtonT, Card
from ui.feedback import Badge, BadgeT
from ui.forms import Label, Textarea
from ui.layout import Size
from ui.patterns.csrf import csrf_hidden_input
from ui.patterns.empty_state import EmptyState
from ui.patterns.page_header import PageHeader
from ui.patterns.section_header import SectionHeader
from ui.primitives import ButtonLink
from ui.tokens import Container


def render_vision_form(existing_vision: str = "", refusal: FT | None = None) -> FT:
    """Build the vision capture form; a refused submission comes back with its
    banner above the field and the learner's text still in it."""
    return Div(
        PageHeader(
            "Express Your Vision",
            subtitle="What do you want to become? Express your life vision in your own words.",
        ),
        Card(
            Div(
                Form(
                    csrf_hidden_input(),
                    refusal,
                    Div(
                        Label("Your Vision", for_="vision"),
                        Textarea(
                            existing_vision or "",
                            id="vision",
                            name="vision_statement",
                            placeholder="I want to become a mindful technical leader who builds products that matter and makes a positive impact on the world...",
                            cls="w-full h-48 p-4 border rounded-lg",
                            required=True,
                        ),
                        P(
                            "Be specific about who you want to become, not just what you want to achieve.",
                            cls="text-sm text-muted-foreground mt-2",
                        ),
                        cls="mb-6",
                    ),
                    Button(
                        "Extract Themes & Get Recommendations",
                        type="submit",
                        cls=(ButtonT.primary, "w-full"),
                    ),
                    method="post",
                    action="/lifepath/vision",
                    cls="space-y-4",
                ),
                cls="p-6",
            ),
            cls=Container.NARROW,
        ),
        cls="container mx-auto",
    )


def render_recommendations_page(vision: SavedVision, recommendations: FT) -> FT:
    """The recommendations page: the saved vision, its themes, and what was found
    for them — the cards, an empty state, or a failed read's banner."""
    return Div(
        PageHeader("Choose Your Life Path"),
        P(f'Your vision: "{vision["statement"]}"', cls="text-muted-foreground italic mb-2"),
        P(
            f"Themes extracted: {', '.join(vision['themes']) or 'none'}",
            cls="text-sm text-muted-foreground mb-8",
        ),
        SectionHeader("Recommended Learning Paths"),
        recommendations,
        cls=f"container mx-auto {Container.NARROW}",
    )


def render_recommendation_cards(
    recommendations: list[LpMatchResult], current_path_uid: str | None
) -> FT:
    """One card per recommended path, each its own native form choosing it — but
    the learner's current path, which says so in place of the button."""
    if not recommendations:
        return EmptyState(
            title="No Matching Learning Paths",
            description="No matching Learning Paths found.",
            action_text="Browse Learning Paths",
            action_href="/learning-paths",
        )
    return Div(
        *[
            _recommendation_card(rec, is_current=rec["lp_uid"] == current_path_uid)
            for rec in recommendations
        ],
        cls="space-y-4",
    )


def render_no_themes() -> FT:
    """What a vision with no themes gets in place of recommendations: nothing to
    match paths against, and the way back to revise it."""
    return EmptyState(
        title="No themes found in your vision",
        description="Say more about who you want to become, and Learning Paths can be matched to it.",
        action_text="Revise your vision",
        action_href="/lifepath/vision",
    )


def _recommendation_card(rec: LpMatchResult, *, is_current: bool) -> FT:
    summary = Div(
        H3(rec["lp_name"], cls="font-semibold text-lg"),
        P(
            f"Match: {int(rec['match_score'] * 100)}%",
            cls="text-sm text-muted-foreground",
        ),
        Div(
            *[
                Badge(t, variant=BadgeT.primary, size=Size.sm, cls="mr-1")
                for t in rec["matching_themes"][:3]
            ],
            cls="mt-2",
        ),
        cls="p-4",
    )
    if is_current:
        return Card(
            summary,
            Div(
                Span("Your current path", cls="text-sm font-medium text-foreground"), cls="p-4 pt-0"
            ),
        )
    return Card(
        Form(
            summary,
            Div(
                Button(
                    "Choose This Path",
                    type="submit",
                    cls=ButtonT.primary,
                    size="sm",
                ),
                cls="p-4 pt-0",
            ),
            csrf_hidden_input(),
            Input(type="hidden", name="life_path_uid", value=rec["lp_uid"]),
            method="post",
            action="/lifepath/designate",
        ),
    )


def render_designation_refused(refusal: FT) -> FT:
    """The page a refused designation answers: its banner, and the way back to the
    recommendations it was chosen from."""
    return Div(
        refusal,
        ButtonLink(
            "Back to your recommendations",
            href="/lifepath/vision/recommendations",
            cls=(ButtonT.primary, "self-start"),
        ),
        cls="flex flex-col gap-4",
    )
