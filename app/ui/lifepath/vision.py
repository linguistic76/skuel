"""LifePath vision capture and recommendations pages."""

from fasthtml.common import FT, H3, A, Div, Form, Input, P

from core.ports.query_types import LpMatches, LpMatchResult, SavedVision
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


def render_recommendations_page(vision: SavedVision, matches: FT) -> FT:
    """The recommendations page: the saved vision, its themes, and the paths
    matched to them — or a failed read's banner. A learner who has designated a
    path is told it is theirs; one who has not is asked to choose."""
    return Div(
        PageHeader("Your Life Path" if vision["life_path_uid"] else "Choose Your Life Path"),
        P(f'Your vision: "{vision["statement"]}"', cls="text-muted-foreground italic mb-2"),
        P(
            f"Themes extracted: {', '.join(vision['themes']) or 'none'}",
            cls="text-sm text-muted-foreground mb-8",
        ),
        matches,
        cls=f"container mx-auto {Container.NARROW}",
    )


def render_path_matches(matches: LpMatches, *, has_themes: bool) -> FT:
    """The learner's current path, when one is designated, then the paths the
    themes recommend: one card each, an empty state, or — with no themes — the
    way back to revise the vision. The current path is shown once, above them,
    whether the themes found it or not."""
    current = matches["current"]
    return Div(
        _current_path_card(current, has_themes=has_themes) if current else None,
        SectionHeader("Recommended Learning Paths"),
        _recommendation_cards(matches["others"]) if has_themes else _no_themes(),
    )


def _current_path_card(current: LpMatchResult, *, has_themes: bool) -> FT:
    """The designated path, linked to its page, with its match against the
    current themes — a match that has fallen to 0% says the path no longer fits
    the vision. With no themes there is nothing to match, and no percentage."""
    return Div(
        SectionHeader("Your current path"),
        Card(
            _match_summary(
                current,
                title=A(
                    current["lp_name"],
                    href=f"/lp/{current['lp_uid']}",
                    cls="text-primary hover:underline",
                ),
                show_score=has_themes,
            )
        ),
        cls="mb-8",
    )


def _recommendation_cards(recommendations: list[LpMatchResult]) -> FT:
    """One card per recommended path, each its own native form choosing it."""
    if not recommendations:
        return EmptyState(
            title="No Matching Learning Paths",
            description="No matching Learning Paths found.",
            action_text="Browse Learning Paths",
            action_href="/learning-paths",
        )
    return Div(*[_recommendation_card(rec) for rec in recommendations], cls="space-y-4")


def _no_themes() -> FT:
    """What a vision with no themes gets in place of recommendations: nothing to
    match paths against, and the way back to revise it."""
    return EmptyState(
        title="No themes found in your vision",
        description="Say more about who you want to become, and Learning Paths can be matched to it.",
        action_text="Revise your vision",
        action_href="/lifepath/vision",
    )


def _match_summary(rec: LpMatchResult, *, title: str | FT, show_score: bool = True) -> FT:
    return Div(
        H3(title, cls="font-semibold text-lg"),
        P(f"Match: {int(rec['match_score'] * 100)}%", cls="text-sm text-muted-foreground")
        if show_score
        else None,
        Div(
            *[
                Badge(t, variant=BadgeT.primary, size=Size.sm, cls="mr-1")
                for t in rec["matching_themes"][:3]
            ],
            cls="mt-2",
        )
        if rec["matching_themes"]
        else None,
        cls="p-4",
    )


def _recommendation_card(rec: LpMatchResult) -> FT:
    return Card(
        Form(
            _match_summary(rec, title=rec["lp_name"]),
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
