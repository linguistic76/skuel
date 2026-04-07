"""LifePath vision capture and recommendations pages."""

from typing import Any

from fasthtml.common import H2, H3, Div, Form, P

from core.models.type_hints import UserUID
from ui.buttons import Button, ButtonT
from ui.cards import Card
from ui.feedback import Badge, BadgeT
from ui.forms import Label, Textarea
from ui.layout import Size
from ui.patterns.empty_state import EmptyState
from ui.patterns.page_header import PageHeader
from ui.tokens import Container


def render_vision_form(existing_vision: str = "") -> Any:
    """Build the vision capture form."""
    return Div(
        PageHeader(
            "Express Your Vision",
            subtitle="What do you want to become? Express your life vision in your own words.",
        ),
        Card(
            Div(
                Form(
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
                        variant=ButtonT.primary,
                        cls="w-full",
                    ),
                    method="post",
                    action="/lifepath/vision",
                    cls="space-y-4",
                ),
                cls="p-6",
            ),
            cls=Container.NARROW,
        ),
        cls="container mx-auto px-4 py-8",
    )


def render_recommendations_page(data: dict, user_uid: UserUID) -> Any:
    """Build recommendations page after vision capture."""
    vision = data.get("vision", {})
    recommendations = data.get("recommendations", [])

    rec_cards = [
        Card(
            Form(
                Div(
                    H3(rec.get("lp_name", "Unknown"), cls="font-semibold text-lg"),
                    P(
                        f"Match: {int(rec.get('match_score', 0) * 100)}%",
                        cls="text-sm text-muted-foreground",
                    ),
                    Div(
                        *[
                            Badge(t, variant=BadgeT.primary, size=Size.sm, cls="mr-1")
                            for t in rec.get("matching_themes", [])[:3]
                        ],
                        cls="mt-2",
                    ),
                    cls="p-4",
                ),
                Div(
                    Button(
                        "Choose This Path",
                        type="submit",
                        variant=ButtonT.primary,
                        size=Size.sm,
                    ),
                    cls="p-4 pt-0",
                ),
                method="post",
                action="/lifepath/designate",
                **{
                    "hx-post": "/lifepath/designate",
                    "hx-vals": f'{{"life_path_uid": "{rec.get("lp_uid", "")}"}}',
                },
            ),
            cls="mb-4",
        )
        for rec in recommendations
    ]

    return Div(
        PageHeader("Choose Your Life Path"),
        P(f'Your vision: "{vision.get("statement", "")}"', cls="text-muted-foreground italic mb-2"),
        P(
            f"Themes extracted: {', '.join(vision.get('themes', []))}",
            cls="text-sm text-muted-foreground mb-8",
        ),
        H2("Recommended Learning Paths", cls="text-xl font-semibold mb-4"),
        *rec_cards
        if rec_cards
        else [
            EmptyState(
                title="No Matching Learning Paths",
                description="No matching Learning Paths found.",
                action_text="Create one",
                action_href="/learning-paths",
            )
        ],
        cls=f"container mx-auto px-4 py-8 {Container.NARROW}",
    )
